"""Gmail tools — read inbox, draft, and send emails."""

from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from typing import Any

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.gmail")


def _get_gmail_service(token_path: Any, client_id: str, client_secret: str) -> Any:
    """Build a Gmail API service from cached credentials."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.send",
        ],
    )
    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict[str, Any]) -> str:
    """Extract plain text body from a Gmail message payload."""
    body = payload.get("body", {})
    data = body.get("data", "")
    if data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # Check parts
    parts = payload.get("parts", [])
    for part in parts:
        if part.get("mimeType") == "text/plain":
            part_data = part.get("body", {}).get("data", "")
            if part_data:
                return base64.urlsafe_b64decode(part_data).decode("utf-8", errors="replace")
    return "(no text content)"


def build_gmail_tools(
    token_path: Any, client_id: str, client_secret: str
) -> list[Tool]:
    """Return Gmail tools bound to the given OAuth credentials."""

    async def _read_inbox(args: dict[str, Any]) -> str:
        try:
            service = _get_gmail_service(token_path, client_id, client_secret)
            max_results = args.get("max_results", 5)

            results = (
                service.users()
                .messages()
                .list(userId="me", maxResults=max_results, labelIds=["INBOX"])
                .execute()
            )
            messages = results.get("messages", [])

            if not messages:
                return "Inbox is empty."

            lines = []
            for msg_ref in messages:
                msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["Subject", "From"])
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(no subject)")
                sender = headers.get("From", "(unknown sender)")
                snippet = msg.get("snippet", "")[:100]
                lines.append(f"- From: {sender}\n  Subject: {subject}\n  Preview: {snippet}")

            return "Recent emails:\n" + "\n".join(lines)
        except Exception as e:
            logger.exception("gmail read_inbox failed")
            return f"Error reading inbox: {e}"

    async def _read_email(args: dict[str, Any]) -> str:
        try:
            service = _get_gmail_service(token_path, client_id, client_secret)
            message_id = args.get("message_id", "")
            if not message_id:
                return "Error: message_id is required."

            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "(no subject)")
            sender = headers.get("From", "(unknown sender)")
            body = _decode_body(msg.get("payload", {}))

            return f"From: {sender}\nSubject: {subject}\n\n{body}"
        except Exception as e:
            logger.exception("gmail read_email failed")
            return f"Error reading email: {e}"

    async def _draft_email(args: dict[str, Any]) -> str:
        """Create a draft email (does not send)."""
        try:
            service = _get_gmail_service(token_path, client_id, client_secret)
            to = args.get("to", "")
            subject = args.get("subject", "")
            body = args.get("body", "")

            if not to or not subject or not body:
                return "Error: to, subject, and body are required."

            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            draft = (
                service.users()
                .drafts()
                .create(userId="me", body={"message": {"raw": raw}})
                .execute()
            )
            return f"Draft created (id: {draft.get('id')}). Review before sending."
        except Exception as e:
            logger.exception("gmail draft_email failed")
            return f"Error creating draft: {e}"

    async def _send_email(args: dict[str, Any]) -> str:
        """Send an email directly. Requires confirmation."""
        try:
            service = _get_gmail_service(token_path, client_id, client_secret)
            to = args.get("to", "")
            subject = args.get("subject", "")
            body = args.get("body", "")

            if not to or not subject or not body:
                return "Error: to, subject, and body are required."

            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return f"Email sent to {to} (id: {sent.get('id')})."
        except Exception as e:
            logger.exception("gmail send_email failed")
            return f"Error sending email: {e}"

    return [
        Tool(
            name="read_inbox",
            description="Read recent emails from the inbox. Returns sender, subject, and preview.",
            parameters={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of emails to fetch (default 5)",
                    },
                },
                "required": [],
            },
            handler=_read_inbox,
            requires_confirm=False,
        ),
        Tool(
            name="read_email",
            description="Read the full content of a specific email by its message ID.",
            parameters={
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The Gmail message ID",
                    },
                },
                "required": ["message_id"],
            },
            handler=_read_email,
            requires_confirm=False,
        ),
        Tool(
            name="draft_email",
            description="Create a Gmail draft without sending. Use this to let the user review before sending.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
            handler=_draft_email,
            requires_confirm=False,
        ),
        Tool(
            name="send_email",
            description="Send an email directly via Gmail. Requires user confirmation before sending.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body text"},
                },
                "required": ["to", "subject", "body"],
            },
            handler=_send_email,
            requires_confirm=True,
        ),
    ]
