"""Per-user SMTP account storage with Fernet encryption for credentials."""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

from database import get_connection

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class EmailSettingsError(Exception):
    """Raised when user email configuration cannot be saved or loaded."""


def _fernet() -> Fernet:
    key = os.getenv("EMAIL_SETTINGS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise EmailSettingsError(
            "EMAIL_SETTINGS_ENCRYPTION_KEY is missing from the .env file."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as error:
        raise EmailSettingsError(
            "EMAIL_SETTINGS_ENCRYPTION_KEY is invalid. Generate a Fernet key and set it in .env."
        ) from error


def get_user_email_settings(user_id: int, decrypt_password: bool = False):
    """Return one user's SMTP settings. Never return the encrypted value to callers."""
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, smtp_host, smtp_port, smtp_security,
                   smtp_username, smtp_password_encrypted,
                   from_email, from_name, updated_at
            FROM user_email_settings
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cursor.fetchone()
    finally:
        connection.close()

    if not row:
        return None

    encrypted_password = row.pop("smtp_password_encrypted", None)
    row["smtp_port"] = int(row["smtp_port"])
    row["has_password"] = bool(encrypted_password)

    if decrypt_password:
        if not encrypted_password:
            raise EmailSettingsError("No SMTP password is saved for this user.")
        try:
            row["smtp_password"] = _fernet().decrypt(
                encrypted_password.encode("utf-8")
            ).decode("utf-8")
        except InvalidToken as error:
            raise EmailSettingsError(
                "Could not decrypt this user's SMTP password. Check that EMAIL_SETTINGS_ENCRYPTION_KEY has not changed."
            ) from error

    return row


def save_user_email_settings(user_id: int, settings: dict) -> None:
    """Save SMTP settings for one user. A blank password preserves an existing password."""
    host = str(settings.get("smtp_host") or "").strip()
    username = str(settings.get("smtp_username") or "").strip()
    from_email = str(settings.get("from_email") or "").strip()
    from_name = str(settings.get("from_name") or "").strip() or "SponsyBot User"
    security = str(settings.get("smtp_security") or "STARTTLS").strip().upper()
    password = str(settings.get("smtp_password") or "").strip()

    try:
        port = int(settings.get("smtp_port", 587))
    except (TypeError, ValueError) as error:
        raise EmailSettingsError("SMTP port must be a number.") from error

    if not host or not username or not from_email:
        raise EmailSettingsError(
            "SMTP host, SMTP username, and sender email are required."
        )
    if not (1 <= port <= 65535):
        raise EmailSettingsError("SMTP port must be between 1 and 65535.")
    if security not in {"STARTTLS", "SSL"}:
        raise EmailSettingsError("Security must be STARTTLS or SSL.")
    if "@" not in from_email or from_email.startswith("@") or from_email.endswith("@"):
        raise EmailSettingsError("Enter a valid sender email address.")

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT smtp_password_encrypted FROM user_email_settings WHERE user_id = %s LIMIT 1",
            (user_id,),
        )
        existing = cursor.fetchone()
        encrypted_password = existing[0] if existing else None

        if password:
            encrypted_password = _fernet().encrypt(password.encode("utf-8")).decode("utf-8")
        elif not encrypted_password:
            raise EmailSettingsError(
                "Enter your SMTP password or app password the first time you save an account."
            )

        cursor.execute(
            """
            INSERT INTO user_email_settings
                (user_id, smtp_host, smtp_port, smtp_security, smtp_username,
                 smtp_password_encrypted, from_email, from_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                smtp_host = VALUES(smtp_host),
                smtp_port = VALUES(smtp_port),
                smtp_security = VALUES(smtp_security),
                smtp_username = VALUES(smtp_username),
                smtp_password_encrypted = VALUES(smtp_password_encrypted),
                from_email = VALUES(from_email),
                from_name = VALUES(from_name),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id, host, port, security, username,
                encrypted_password, from_email, from_name,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
