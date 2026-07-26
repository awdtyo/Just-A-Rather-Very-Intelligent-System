"""WhatsApp Cloud API tools — read inbox and send messages."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.whatsapp")

_BASE_URL = "https://graph.facebook.com/v19.0"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_whatsapp_tools(
    access_token: str, phone_number_id: str
) -> list[Tool]:
    """Return WhatsApp Cloud API tools."""

    async def _read_inbox(args: dict[str, Any]) -> str:
        """Read recent inbound messages (requires webhook config for full history)."""
        if not access_token or not phone_number_id:
            return "Error: WhatsApp credentials not configured."
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_BASE_URL}/{phone_number_id}/messages",
                    headers=_headers(access_token),
                    params={"limit": args.get("limit", 10)},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            messages = data.get("data", [])
            if not messages:
                return "No recent WhatsApp messages."

            lines = []
            for msg in messages[:10]:
                sender = msg.get("from", "unknown")
                msg_type = msg.get("type", "text")
                text = ""
                if msg_type == "text":
                    text = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    text = "[image]"
                elif msg_type == "audio":
                    text = "[audio]"
                elif msg_type == "video":
                    text = "[video]"
                elif msg_type == "document":
                    text = "[document]"
                else:
                    text = f"[{msg_type}]"
                ts = msg.get("timestamp", "")
                lines.append(f"- From {sender} at {ts}: {text}")

            return "Recent WhatsApp messages:\n" + "\n".join(lines)
        except httpx.HTTPStatusError as e:
            logger.exception("whatsapp read_inbox HTTP error")
            return f"WhatsApp API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("whatsapp read_inbox failed")
            return f"Error reading WhatsApp: {e}"

    async def _send_message(args: dict[str, Any]) -> str:
        """Send a text message. Requires user confirmation."""
        if not access_token or not phone_number_id:
            return "Error: WhatsApp credentials not configured."
        to = args.get("to", "")
        text = args.get("text", "")
        if not to or not text:
            return "Error: to and text are required."
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{_BASE_URL}/{phone_number_id}/messages",
                    headers=_headers(access_token),
                    json={
                        "messaging_product": "whatsapp",
                        "to": to,
                        "type": "text",
                        "text": {"body": text},
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            msg_id = data.get("messages", [{}])[0].get("id", "unknown")
            return f"WhatsApp message sent to {to} (id: {msg_id})."
        except httpx.HTTPStatusError as e:
            logger.exception("whatsapp send_message HTTP error")
            return f"WhatsApp API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("whatsapp send_message failed")
            return f"Error sending WhatsApp: {e}"

    async def _draft_reply(args: dict[str, Any]) -> str:
        """Draft a reply (stores text for review, does not send)."""
        to = args.get("to", "")
        text = args.get("text", "")
        if not to or not text:
            return "Error: to and text are required."
        # Draft is just returned as-is for the LLM to read back
        return f"Draft WhatsApp reply to {to}: \"{text}\""

    return [
        Tool(
            name="read_whatsapp_inbox",
            description="Read recent inbound WhatsApp messages.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of messages to fetch (default 10)",
                    },
                },
                "required": [],
            },
            handler=_read_inbox,
            requires_confirm=False,
        ),
        Tool(
            name="send_whatsapp_message",
            description="Send a WhatsApp message to a phone number. Requires user confirmation before sending.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient phone number in international format (e.g. +1234567890)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text to send",
                    },
                },
                "required": ["to", "text"],
            },
            handler=_send_message,
            requires_confirm=True,
        ),
        Tool(
            name="draft_whatsapp_reply",
            description="Draft a reply to a WhatsApp contact without sending. Use this to let the user review before sending.",
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient phone number",
                    },
                    "text": {
                        "type": "string",
                        "description": "Draft reply text",
                    },
                },
                "required": ["to", "text"],
            },
            handler=_draft_reply,
            requires_confirm=False,
        ),
    ]
