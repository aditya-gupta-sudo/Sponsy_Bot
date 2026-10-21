"""Send mail using an explicit per-user SMTP configuration."""

import smtplib
import ssl
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr


class EmailSendError(Exception):
    """Raised when an SMTP connection or send fails."""


def _validate_config(smtp_config: dict) -> tuple[str, int, str, str, str, str, str]:
    if not isinstance(smtp_config, dict):
        raise EmailSendError("A saved email account must be configured before sending.")

    host = str(smtp_config.get("smtp_host") or "").strip()
    username = str(smtp_config.get("smtp_username") or "").strip()
    password = str(smtp_config.get("smtp_password") or "")
    from_email = str(smtp_config.get("from_email") or "").strip()
    from_name = str(smtp_config.get("from_name") or "SponsyBot User").strip()
    security = str(smtp_config.get("smtp_security") or "STARTTLS").strip().upper()

    try:
        port = int(smtp_config.get("smtp_port", 587))
    except (TypeError, ValueError) as error:
        raise EmailSendError("SMTP port must be a number.") from error

    if not all((host, username, password, from_email)):
        raise EmailSendError(
            "This user has not configured a complete SMTP account. Open Email Settings."
        )
    if not 1 <= port <= 65535:
        raise EmailSendError("SMTP port must be between 1 and 65535.")
    if security not in {"STARTTLS", "SSL"}:
        raise EmailSendError("SMTP security must be STARTTLS or SSL.")

    return host, port, username, password, from_email, from_name, security


@contextmanager
def _authenticated_server(smtp_config: dict):
    host, port, username, password, _, _, security = _validate_config(smtp_config)
    context = ssl.create_default_context()

    if security == "SSL":
        server_context = smtplib.SMTP_SSL(
            host, port, timeout=30, context=context
        )
    else:
        server_context = smtplib.SMTP(host, port, timeout=30)

    with server_context as server:
        server.ehlo()
        if security == "STARTTLS":
            server.starttls(context=context)
            server.ehlo()
        server.login(username, password)
        yield server


def test_smtp_connection(smtp_config: dict) -> None:
    """Connect and authenticate; does not send a test email."""
    try:
        with _authenticated_server(smtp_config):
            pass
    except (smtplib.SMTPException, OSError, ValueError) as error:
        raise EmailSendError(
            "SMTP connection failed. Check the host, port, security mode, username, and app password."
        ) from error


def send_email(
    recipient_email: str,
    recipient_name: str | None,
    subject: str,
    body: str,
    smtp_config: dict,
) -> None:
    """Send an email through the current user's SMTP account."""
    _, _, _, _, from_email, from_name, _ = _validate_config(smtp_config)

    message = EmailMessage()
    message["From"] = formataddr((from_name, from_email))
    if recipient_name:
        message["To"] = formataddr((recipient_name, recipient_email))
    else:
        message["To"] = recipient_email
    message["Subject"] = subject
    message["Reply-To"] = from_email
    message.set_content(body)

    try:
        with _authenticated_server(smtp_config) as server:
            server.send_message(message)
    except (smtplib.SMTPException, OSError, ValueError) as error:
        # Do not log credentials or full email contents.
        raise EmailSendError(
            "The user's SMTP server failed to send the email. Check Email Settings and the provider's SMTP requirements."
        ) from error
