import os
import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from langchain_core.tools import tool

from graph.config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD
from graph.logger import get_logger

logger = get_logger("tools.gmail")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587

# Simple, deliberately permissive email format check — good enough to catch typos
# without rejecting valid-but-unusual addresses.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(address: str) -> bool:
    return bool(_EMAIL_RE.match(address.strip()))


@tool
def send_email(to: str, subject: str, body: str, attachment_path: str = "") -> str:
    """Send an email via Gmail. 'to' must be a valid email address.
    attachment_path is optional — pass a file path (e.g. from an uploaded file) to attach it.
    Use this only when the user explicitly asks to send an email."""

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        return "Email tool is not configured (missing GMAIL_ADDRESS or GMAIL_APP_PASSWORD). Ask the admin to set it up."

    to = to.strip()
    if not _is_valid_email(to):
        return f"'{to}' doesn't look like a valid email address. Please check it and try again."

    if not subject.strip():
        return "Please provide a subject line for the email."

    if attachment_path and not os.path.isfile(attachment_path):
        return f"Attachment not found at '{attachment_path}'. Please re-upload the file and try again."

    try:
        if attachment_path:
            message = MIMEMultipart()
            message.attach(MIMEText(body))
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            message.attach(part)
        else:
            message = MIMEText(body)

        message["Subject"] = subject
        message["From"] = GMAIL_ADDRESS
        message["To"] = to

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [to], message.as_string())

    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail authentication failed — check GMAIL_APP_PASSWORD")
        return "Email authentication failed. The Gmail app password may be wrong or expired."
    except smtplib.SMTPRecipientsRefused:
        return f"Gmail rejected the recipient address '{to}'. Please double-check it."
    except smtplib.SMTPException as e:
        logger.exception("SMTP error while sending email")
        return f"Failed to send email: {e}"
    except OSError as e:
        logger.exception("Network/file error while sending email")
        return f"Couldn't send the email due to a connection or file error: {e}"

    logger.info(f"Email sent to {to} (attachment={'yes' if attachment_path else 'no'})")
    suffix = f" with attachment '{os.path.basename(attachment_path)}'" if attachment_path else ""
    return f"Email sent to {to} with subject '{subject}'{suffix}."
