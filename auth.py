"""Password and Google OAuth authentication for SponsyBot.

Sessions use opaque random tokens stored only as SHA-256 hashes in MySQL.
The browser receives the token in an HttpOnly cookie. Google OAuth uses Authlib
and the signed Starlette session only to protect the OAuth state/nonce flow.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
from datetime import datetime, timedelta
from typing import Any

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from mysql.connector import Error, IntegrityError

from database import get_connection

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

router = APIRouter()
password_hash = PasswordHash.recommended()
SESSION_COOKIE = "sponsybot_session"
SESSION_TTL_DAYS = max(1, int(os.getenv("SESSION_TTL_DAYS", "7")))
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _cookie_secure() -> bool:
    configured = os.getenv("COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


def ensure_auth_schema() -> None:
    """Create session storage and add the optional Google subject column."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        if os.getenv("AUTH_AUTO_MIGRATE", "true").strip().lower() not in {"1", "true", "yes", "on"}:
            # In production, operators can run migrations/001_auth_sessions.sql
            # manually and use a database account without DDL privileges.
            _SCHEMA_READY = True
            return
        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute("SHOW COLUMNS FROM users LIKE 'google_sub'")
            if cursor.fetchone() is None:
                try:
                    cursor.execute("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255) NULL")
                except Error as error:
                    # Another worker may have completed the same DDL concurrently.
                    if getattr(error, "errno", None) != 1060:
                        raise
            cursor.execute("SHOW INDEX FROM users WHERE Key_name = %s", ("uq_users_google_sub",))
            if cursor.fetchone() is None:
                try:
                    cursor.execute("ALTER TABLE users ADD UNIQUE KEY uq_users_google_sub (google_sub)")
                except Error as error:
                    if getattr(error, "errno", None) != 1061:
                        raise
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token_hash CHAR(64) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_used_at DATETIME NULL,
                    INDEX idx_auth_sessions_user (user_id),
                    INDEX idx_auth_sessions_expiry (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            connection.commit()
            _SCHEMA_READY = True
        finally:
            connection.close()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> tuple[str, datetime]:
    ensure_auth_schema()
    token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS)
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
            (user_id, _hash_token(token), expires_at),
        )
        connection.commit()
    finally:
        connection.close()
    return token, expires_at


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def delete_session(token: str | None) -> None:
    if not token:
        return
    ensure_auth_schema()
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (_hash_token(token),))
        connection.commit()
    finally:
        connection.close()


def user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    ensure_auth_schema()
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT u.user_id, u.name, u.email, u.role, s.expires_at
            FROM auth_sessions AS s
            JOIN users AS u ON u.user_id = s.user_id
            WHERE s.token_hash = %s
            LIMIT 1
            """,
            (_hash_token(token),),
        )
        user = cursor.fetchone()
        if not user:
            return None
        expires = user.get("expires_at")
        if not expires or expires <= datetime.utcnow():
            cursor.execute("DELETE FROM auth_sessions WHERE token_hash = %s", (_hash_token(token),))
            connection.commit()
            return None
        cursor.execute(
            "UPDATE auth_sessions SET last_used_at = %s WHERE token_hash = %s",
            (datetime.utcnow(), _hash_token(token)),
        )
        connection.commit()
        user.pop("expires_at", None)
        return user
    finally:
        connection.close()


def authenticated_user_id(request: Request) -> int:
    try:
        user = user_for_token(request.cookies.get(SESSION_COOKIE))
    except Error as error:
        raise HTTPException(status_code=503, detail="Authentication database is unavailable.") from error
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return int(user["user_id"])


def page_user(request: Request) -> dict[str, Any] | None:
    try:
        return user_for_token(request.cookies.get(SESSION_COOKIE))
    except Error:
        return None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def _normalise_email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(value):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return value


def _safe_next_path(value: str | None) -> str:
    """Allow only same-site relative paths to prevent open redirects."""
    if not value or not value.startswith("/") or value.startswith("//") or value.startswith("/\\"):
        return "/"
    return value


def _open_session_response(user_id: int, next_path: str = "/") -> RedirectResponse:
    token, _ = create_session(user_id)
    response = RedirectResponse(url=_safe_next_path(next_path), status_code=303)
    set_session_cookie(response, token)
    return response


def _new_session_api_response(user_id: int) -> Response:
    token, _ = create_session(user_id)
    response = Response(content='{"authenticated":true}', media_type="application/json")
    set_session_cookie(response, token)
    return response


@router.post("/api/auth/register")
def register(payload: RegisterRequest) -> Response:
    ensure_auth_schema()
    email = _normalise_email(payload.email)
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must contain at least two characters.")
    encoded = password_hash.hash(payload.password)
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (name, email, encoded, "NAIVE_USER"),
        )
        user_id = int(cursor.lastrowid)
        connection.commit()
    except IntegrityError as error:
        connection.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
    except Error as error:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Could not create your account. Check the database configuration.") from error
    finally:
        connection.close()
    return _new_session_api_response(user_id)


@router.post("/api/auth/login")
def login(payload: LoginRequest) -> Response:
    ensure_auth_schema()
    email = _normalise_email(payload.email)
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT user_id, password_hash FROM users WHERE email = %s LIMIT 1", (email,))
        user = cursor.fetchone()
    except Error as error:
        raise HTTPException(status_code=503, detail="Could not sign in. Check the database configuration.") from error
    finally:
        connection.close()
    # Use the same public error for missing users and incorrect passwords.
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    try:
        valid = password_hash.verify(payload.password, user["password_hash"])
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return _new_session_api_response(int(user["user_id"]))


@router.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    user = page_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return {"authenticated": True, "user": {k: user.get(k) for k in ("user_id", "name", "email", "role")}}


@router.post("/api/auth/logout")
def logout(request: Request) -> Response:
    try:
        delete_session(request.cookies.get(SESSION_COOKIE))
    except Error:
        # Clear the browser cookie even if the database is temporarily unavailable.
        pass
    response = Response(content='{"authenticated":false}', media_type="application/json")
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=_cookie_secure(), samesite="lax")
    request.session.clear()
    return response


oauth = OAuth()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID or "not-configured",
    client_secret=GOOGLE_CLIENT_SECRET or "not-configured",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@router.get("/auth/google")
async def google_login(request: Request):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return RedirectResponse("/login?error=google_not_configured", status_code=303)
    requested_next = _safe_next_path(request.query_params.get("next"))
    request.session["auth_next"] = requested_next
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip() or str(request.url_for("google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = await oauth.google.userinfo(token=token)
        sub = str(userinfo.get("sub") or "").strip()
        email = _normalise_email(str(userinfo.get("email") or ""))
        if not sub or userinfo.get("email_verified") not in (True, "true", "True"):
            return RedirectResponse("/login?error=google_email_unverified", status_code=303)
        ensure_auth_schema()
        connection = get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT user_id, email, google_sub FROM users WHERE google_sub = %s LIMIT 1", (sub,))
            user = cursor.fetchone()
            if not user:
                cursor.execute("SELECT user_id, email, google_sub FROM users WHERE email = %s LIMIT 1", (email,))
                user = cursor.fetchone()
                if user:
                    existing_sub = user.get("google_sub")
                    if existing_sub and existing_sub != sub:
                        raise HTTPException(status_code=409, detail="This email is linked to another Google account.")
                    cursor.execute("UPDATE users SET google_sub = %s WHERE user_id = %s", (sub, user["user_id"]))
                    user_id = int(user["user_id"])
                else:
                    name = str(userinfo.get("name") or email.split("@", 1)[0])[:120]
                    random_hash = password_hash.hash(secrets.token_urlsafe(48))
                    cursor.execute(
                        "INSERT INTO users (name, email, password_hash, role, google_sub) VALUES (%s, %s, %s, %s, %s)",
                        (name, email, random_hash, "NAIVE_USER", sub),
                    )
                    user_id = int(cursor.lastrowid)
            else:
                user_id = int(user["user_id"])
            connection.commit()
        finally:
            connection.close()
        next_path = _safe_next_path(request.session.pop("auth_next", "/"))
        return _open_session_response(user_id, next_path)
    except HTTPException:
        raise
    except Exception:
        # Do not expose provider tokens, authorization codes, or internal details in redirects.
        return RedirectResponse("/login?error=google_signin_failed", status_code=303)
