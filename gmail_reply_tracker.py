import json
import os
import re
import secrets
from datetime import datetime, timedelta
from email.utils import parseaddr
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from mysql.connector import Error
from pydantic import BaseModel
from typing import Literal

from auth import authenticated_user_id
from database import get_connection


router = APIRouter()

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_SCOPE]


def _redirect_uri():
    return os.getenv(
        "GMAIL_REPLY_REDIRECT_URI",
        "http://127.0.0.1:8000/auth/gmail/callback",
    ).strip()


def _client_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured."
        )

    redirect_uri = _redirect_uri()

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def _fernet():
    key = os.getenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "").strip()

    if not key:
        raise RuntimeError(
            "EMAIL_SETTINGS_ENCRYPTION_KEY is missing from .env."
        )

    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "EMAIL_SETTINGS_ENCRYPTION_KEY is not a valid Fernet key."
        ) from error


def _save_connection(user_id, gmail_email, credentials):
    encrypted_token = _fernet().encrypt(
        credentials.to_json().encode("utf-8")
    ).decode("utf-8")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO gmail_inbox_connections
                (user_id, gmail_email, token_encrypted)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                gmail_email = VALUES(gmail_email),
                token_encrypted = VALUES(token_encrypted),
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, gmail_email, encrypted_token),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _get_connection_row(user_id):
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT user_id, gmail_email, token_encrypted, last_checked_at
            FROM gmail_inbox_connections
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

        return cursor.fetchone()

    finally:
        connection.close()


def _get_gmail_service(user_id):
    row = _get_connection_row(user_id)

    if not row:
        raise HTTPException(
            status_code=409,
            detail="Connect your Gmail inbox before checking replies.",
        )

    try:
        raw_token = _fernet().decrypt(
            row["token_encrypted"].encode("utf-8")
        )

        token_data = json.loads(raw_token.decode("utf-8"))

        credentials = Credentials.from_authorized_user_info(
            token_data,
            GMAIL_SCOPES,
        )

    except (InvalidToken, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Saved Gmail credentials could not be decrypted. "
                "Check the encryption key in .env."
            ),
        ) from error

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleRequest())
        except GoogleAuthError as error:
            raise HTTPException(
                status_code=401,
                detail="Gmail authorization expired. Reconnect your inbox.",
            ) from error

        _save_connection(
            user_id,
            row["gmail_email"],
            credentials,
        )

    if not credentials.valid:
        raise HTTPException(
            status_code=401,
            detail="Reconnect Gmail before checking replies.",
        )

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    return service, row


def _subject_key(subject):
    value = (subject or "").strip().lower()

    # Normalize common reply/forward prefixes.
    while True:
        cleaned = re.sub(r"^(re|fw|fwd)\s*:\s*", "", value).strip()

        if cleaned == value:
            break

        value = cleaned

    return re.sub(r"\s+", " ", value)


def _header_map(message):
    headers = (
        message.get("payload", {}).get("headers", [])
    )

    return {
        str(header.get("name", "")).lower():
        str(header.get("value", ""))
        for header in headers
    }


def _sent_timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    if value.tzinfo is None:
        local_zone = ZoneInfo(
            os.getenv("APP_TIMEZONE", "Asia/Kolkata")
        )
        value = value.replace(tzinfo=local_zone)

    return value.timestamp()


def _search_after_date(sent_at):
    if isinstance(sent_at, str):
        sent_at = datetime.fromisoformat(
            sent_at.replace("Z", "+00:00")
        )

    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(
            tzinfo=ZoneInfo(
                os.getenv("APP_TIMEZONE", "Asia/Kolkata")
            )
        )

    # Gmail's search date is date-based. Search two days earlier,
    # then check the exact message timestamp in Python.
    search_date = sent_at.date() - timedelta(days=2)

    return search_date.strftime("%Y/%m/%d")


def _get_sent_records(user_id):
    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                oe.email_id,
                oe.event_id,
                oe.company_id,
                oe.recipient_email,
                oe.subject,
                oe.sent_at,
                oe.reply_status
            FROM outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            WHERE e.user_id = %s
              AND oe.status = 'SENT'
              AND oe.sent_at IS NOT NULL
            ORDER BY oe.sent_at DESC
            LIMIT 100
            """,
            (user_id,),
        )

        return cursor.fetchall()

    finally:
        connection.close()


def _mark_awaiting(email_id):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Never downgrade a record for which a reply is already saved.
        cursor.execute(
            """
            UPDATE outreach_emails
            SET reply_status = 'AWAITING'
            WHERE email_id = %s
              AND COALESCE(reply_status, '') <> 'REPLIED'
            """,
            (email_id,),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _save_reply(
    email_id,
    message_id,
    reply_from,
    reply_subject,
    snippet,
    received_at,
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE outreach_emails
            SET reply_status = 'REPLIED',
                reply_received_at = %s,
                reply_from_email = %s,
                reply_subject = %s,
                reply_snippet = %s,
                reply_gmail_message_id = %s
            WHERE email_id = %s
            """,
            (
                received_at,
                reply_from,
                (reply_subject or "")[:500],
                (snippet or "")[:4000],
                message_id,
                email_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def _find_reply(
    service,
    record,
    connected_email,
    seen_message_ids,
):
    recipient = str(
        record.get("recipient_email") or ""
    ).strip().lower()

    original_subject = _subject_key(
        record.get("subject") or ""
    )

    sent_at = record.get("sent_at")

    if not recipient or not original_subject or not sent_at:
        return None

    query = (
        f"in:anywhere from:{recipient} "
        f"after:{_search_after_date(sent_at)}"
    )

    try:
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=30,
            )
            .execute()
        )

        messages = result.get("messages", [])

        for item in messages:
            gmail_message_id = item.get("id")

            if (
                not gmail_message_id
                or gmail_message_id in seen_message_ids
            ):
                continue

            message = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=gmail_message_id,
                    format="metadata",
                    metadataHeaders=[
                        "From",
                        "Subject",
                        "Date",
                        "Message-ID",
                        "In-Reply-To",
                        "References",
                    ],
                )
                .execute()
            )

            headers = _header_map(message)

            reply_from = parseaddr(
                headers.get("from", "")
            )[1].strip().lower()

            reply_subject = headers.get("subject", "")
            received_timestamp = (
                int(message.get("internalDate", 0)) / 1000
            )

            if not reply_from:
                continue

            if reply_from == connected_email.lower():
                continue

            if reply_from != recipient:
                continue

            if _subject_key(reply_subject) != original_subject:
                continue

            if received_timestamp <= _sent_timestamp(sent_at):
                continue

            # Prevent a single incoming email from being assigned
            # to several old outreach records in the same check.
            seen_message_ids.add(gmail_message_id)

            return {
                "message_id": gmail_message_id,
                "from_email": reply_from,
                "subject": reply_subject,
                "snippet": message.get("snippet", ""),
                "received_at": datetime.fromtimestamp(
                    received_timestamp
                ),
            }

    except HttpError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Gmail could not be searched. Check Gmail API "
                "access and reconnect the inbox if necessary."
            ),
        ) from error

    return None


@router.get("/auth/gmail/connect")
def connect_gmail(
    request: Request,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        state = secrets.token_urlsafe(32)

        request.session["gmail_reply_oauth_state"] = state

        flow = Flow.from_client_config(
            _client_config(),
            scopes=GMAIL_SCOPES,
            redirect_uri=_redirect_uri(),
        )

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )

        return RedirectResponse(
            authorization_url,
            status_code=302,
        )

    except RuntimeError as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error


@router.get("/auth/gmail/callback")
def gmail_callback(
    request: Request,
    user_id: int = Depends(authenticated_user_id),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    expected_state = request.session.pop(
        "gmail_reply_oauth_state",
        None,
    )

    if not expected_state or not state or state != expected_state:
        raise HTTPException(
            status_code=400,
            detail="Gmail OAuth state validation failed. Try connecting again.",
        )

    if error:
        return RedirectResponse(
            "/outreach?" + urlencode({"gmail_error": error}),
            status_code=303,
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Google did not return an authorization code.",
        )

    try:
        flow = Flow.from_client_config(
            _client_config(),
            scopes=GMAIL_SCOPES,
            state=state,
            redirect_uri=_redirect_uri(),
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        profile = (
            service.users()
            .getProfile(userId="me")
            .execute()
        )

        gmail_email = str(
            profile.get("emailAddress") or ""
        ).strip().lower()

        if not gmail_email:
            raise RuntimeError(
                "Gmail did not return the connected mailbox address."
            )

        _save_connection(
            user_id,
            gmail_email,
            credentials,
        )

        return RedirectResponse(
            "/outreach?" + urlencode({"gmail_connected": "1"}),
            status_code=303,
        )

    except (RuntimeError, ValueError, GoogleAuthError, HttpError) as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "Gmail connection failed. Verify the OAuth redirect URI, "
                "Gmail API, consent screen and server logs."
            ),
        ) from error


@router.get("/api/gmail-inbox/status")
def gmail_inbox_status(
    user_id: int = Depends(authenticated_user_id),
):
    row = _get_connection_row(user_id)

    return {
        "connected": bool(row),
        "gmail_email": row["gmail_email"] if row else None,
        "last_checked_at": (
            row["last_checked_at"].isoformat()
            if row and row.get("last_checked_at")
            else None
        ),
    }


@router.post("/api/outreach/check-replies")
def check_outreach_replies(
    user_id: int = Depends(authenticated_user_id),
):
    service, inbox = _get_gmail_service(user_id)
    records = _get_sent_records(user_id)

    seen_message_ids = set()
    checked = 0
    replies_found = 0

    for record in records:
        checked += 1

        reply = _find_reply(
            service,
            record,
            inbox["gmail_email"],
            seen_message_ids,
        )

        if reply:
            _save_reply(
                email_id=record["email_id"],
                message_id=reply["message_id"],
                reply_from=reply["from_email"],
                reply_subject=reply["subject"],
                snippet=reply["snippet"],
                received_at=reply["received_at"],
            )

            replies_found += 1

        else:
            _mark_awaiting(record["email_id"])

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE gmail_inbox_connections
            SET last_checked_at = NOW()
            WHERE user_id = %s
            """,
            (user_id,),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return {
        "message": (
            f"Checked {checked} sent record(s). "
            f"Detected {replies_found} matching reply/replies."
        ),
        "gmail_email": inbox["gmail_email"],
        "checked": checked,
        "replies_found": replies_found,
    }


class ReplyDecisionRequest(BaseModel):
    decision: Literal[
        "UNCLASSIFIED",
        "INTERESTED",
        "DECLINED",
        "NEEDS_DETAILS",
        "FOLLOW_UP",
        "CLOSED",
    ]


@router.patch("/api/outreach/{email_id}/reply-decision")
def classify_outreach_reply(
    email_id: int,
    payload: ReplyDecisionRequest,
    user_id: int = Depends(authenticated_user_id),
):
    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE outreach_emails AS oe
            JOIN events AS e
                ON e.event_id = oe.event_id
            SET oe.reply_decision = %s
            WHERE oe.email_id = %s
              AND e.user_id = %s
              AND oe.reply_status = 'REPLIED'
            """,
            (
                payload.decision,
                email_id,
                user_id,
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()

            raise HTTPException(
                status_code=404,
                detail=(
                    "A replied outreach record for this user was not found."
                ),
            )

        connection.commit()

        return {
            "message": "Reply outcome saved.",
            "email_id": email_id,
            "reply_decision": payload.decision,
        }

    except HTTPException:
        raise

    except Error as error:
        connection.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not save the reply outcome.",
        ) from error

    finally:
        connection.close()