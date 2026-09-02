import os
import re
import base64

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st
from langchain_core.tools import tool

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from graph.logger import get_logger

logger = get_logger("tools.gmail")

# Gmail API scope
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"

# Simple email validation
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(address: str) -> bool:
    return bool(_EMAIL_RE.match(address.strip()))


def _get_gmail_credentials():
    """
    Get the currently connected user's Gmail OAuth credentials
    from the Streamlit session.
    """

    credentials = st.session_state.get("gmail_credentials")

    if credentials is None:
        return None

    return credentials


def _get_gmail_service():
    """
    Create a Gmail API service using the currently
    authenticated user's OAuth credentials.
    """

    credentials = _get_gmail_credentials()

    if credentials is None:
        return None

    try:
        service = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

        return service

    except Exception:
        logger.exception("Failed to create Gmail API service")
        return None


def _create_email_message(
    to: str,
    subject: str,
    body: str,
    attachment_path: str = "",
):
    """
    Create a MIME email message and encode it for Gmail API.
    """

    if attachment_path:
        message = MIMEMultipart()

        message.attach(MIMEText(body, "plain", "utf-8"))

        with open(attachment_path, "rb") as f:
            attachment = MIMEApplication(
                f.read(),
                Name=os.path.basename(attachment_path),
            )

        attachment["Content-Disposition"] = (
            f'attachment; filename="{os.path.basename(attachment_path)}"'
        )

        message.attach(attachment)

    else:
        message = MIMEText(
            body,
            "plain",
            "utf-8",
        )

    message["To"] = to
    message["Subject"] = subject

    # Gmail API will automatically use the authenticated
    # user's Gmail account as the sender.
    #
    # We intentionally do NOT set:
    # message["From"] = GMAIL_ADDRESS

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    return {
        "raw": raw_message
    }


@tool
def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: str = "",
) -> str:
    """
    Send an email using the Gmail account currently connected
    by the user through Google OAuth.

    'to' must be a valid email address.

    'subject' is the email subject.

    'body' is the email body.

    'attachment_path' is optional and can contain the path
    to an uploaded file.

    Use this tool only when the user explicitly asks
    to send an email.
    """

    # ---------------------------------------------------------
    # 1. Check whether the user connected Gmail
    # ---------------------------------------------------------

    credentials = _get_gmail_credentials()

    if credentials is None:
        return (
            "Your Gmail account is not connected yet. "
            "Please click 'Connect Gmail' and authorize your "
            "Google account before sending an email."
        )

    # ---------------------------------------------------------
    # 2. Check credential validity
    # ---------------------------------------------------------

    if not credentials.valid:

        if credentials.expired and credentials.refresh_token:
            try:
                from google.auth.transport.requests import Request

                credentials.refresh(Request())

                # Update the session with refreshed credentials
                st.session_state["gmail_credentials"] = credentials

            except Exception:
                logger.exception(
                    "Failed to refresh Gmail OAuth credentials"
                )

                return (
                    "Your Gmail authorization has expired and "
                    "could not be refreshed. Please reconnect "
                    "your Gmail account."
                )

        else:
            return (
                "Your Gmail authorization is no longer valid. "
                "Please reconnect your Gmail account."
            )

    # ---------------------------------------------------------
    # 3. Validate recipient
    # ---------------------------------------------------------

    to = to.strip()

    if not _is_valid_email(to):
        return (
            f"'{to}' doesn't look like a valid email address. "
            "Please check the recipient address."
        )

    # ---------------------------------------------------------
    # 4. Validate subject
    # ---------------------------------------------------------

    if not subject or not subject.strip():
        return "Please provide a subject line for the email."

    # ---------------------------------------------------------
    # 5. Validate attachment
    # ---------------------------------------------------------

    if attachment_path:

        if not os.path.isfile(attachment_path):
            return (
                f"Attachment not found at '{attachment_path}'. "
                "Please re-upload the file and try again."
            )

    # ---------------------------------------------------------
    # 6. Create Gmail API service
    # ---------------------------------------------------------

    service = _get_gmail_service()

    if service is None:
        return (
            "Unable to connect to Gmail. "
            "Please reconnect your Gmail account."
        )

    # ---------------------------------------------------------
    # 7. Create MIME email
    # ---------------------------------------------------------

    try:

        message = _create_email_message(
            to=to,
            subject=subject,
            body=body,
            attachment_path=attachment_path,
        )

    except OSError as e:

        logger.exception(
            "Failed to read email attachment"
        )

        return (
            f"Could not read the attachment: {e}"
        )

    except Exception as e:

        logger.exception(
            "Failed to create email message"
        )

        return (
            f"Could not create the email: {e}"
        )

    # ---------------------------------------------------------
    # 8. Send through Gmail API
    # ---------------------------------------------------------

    try:

        sent_message = (
            service.users()
            .messages()
            .send(
                userId="me",
                body=message,
            )
            .execute()
        )

        message_id = sent_message.get("id", "")

        logger.info(
            f"Gmail email sent successfully to {to}. "
            f"Message ID: {message_id}"
        )

        suffix = ""

        if attachment_path:
            suffix = (
                f" with attachment "
                f"'{os.path.basename(attachment_path)}'"
            )

        return (
            f"Email sent successfully to {to} "
            f"with subject '{subject}'{suffix}."
        )

    except HttpError as e:

        logger.exception(
            "Gmail API error while sending email"
        )

        status_code = getattr(
            e.resp,
            "status",
            None,
        )

        if status_code == 401:
            return (
                "Gmail authorization failed. "
                "Please reconnect your Gmail account."
            )

        if status_code == 403:
            return (
                "Google denied permission to send this email. "
                "Please reconnect Gmail and make sure you "
                "approved the Gmail send permission."
            )

        if status_code == 400:
            return (
                "Gmail rejected the email request. "
                "Please check the recipient, subject, and message."
            )

        return (
            f"Gmail API error while sending the email: {e}"
        )

    except Exception as e:

        logger.exception(
            "Unexpected error while sending Gmail email"
        )

        return (
            f"Failed to send the email: {e}"
        )
