"""LinkedIn API tools — read profile, create posts, draft DMs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.linkedin")

_BASE_URL = "https://api.linkedin.com/v2"


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


def build_linkedin_tools(access_token: str) -> list[Tool]:
    """Return LinkedIn API tools."""

    async def _read_profile(args: dict[str, Any]) -> str:
        """Read the authenticated user's LinkedIn profile."""
        if not access_token:
            return "Error: LinkedIn access token not configured."
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_BASE_URL}/userinfo",
                    headers=_headers(access_token),
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            name = data.get("name", "Unknown")
            headline = data.get("headline", "")
            location = data.get("location", "")
            parts = [f"Name: {name}"]
            if headline:
                parts.append(f"Headline: {headline}")
            if location:
                parts.append(f"Location: {location}")
            return "\n".join(parts)
        except httpx.HTTPStatusError as e:
            logger.exception("linkedin read_profile HTTP error")
            return f"LinkedIn API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("linkedin read_profile failed")
            return f"Error reading LinkedIn profile: {e}"

    async def _create_post(args: dict[str, Any]) -> str:
        """Create a LinkedIn post. Requires user confirmation."""
        if not access_token:
            return "Error: LinkedIn access token not configured."
        text = args.get("text", "")
        if not text:
            return "Error: text is required."
        try:
            # Get the user's URN first
            async with httpx.AsyncClient() as client:
                me_resp = await client.get(
                    f"{_BASE_URL}/userinfo",
                    headers=_headers(access_token),
                    timeout=10,
                )
                me_resp.raise_for_status()
                user_id = me_resp.json().get("sub", "")
                if not user_id:
                    return "Error: could not determine LinkedIn user ID."

                post_body = {
                    "author": f"urn:li:person:{user_id}",
                    "lifecycleState": "PUBLISHED",
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {"text": text},
                            "shareMediaCategory": "NONE",
                        }
                    },
                    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                }

                resp = await client.post(
                    f"{_BASE_URL}/ugcPosts",
                    headers=_headers(access_token),
                    json=post_body,
                    timeout=10,
                )
                resp.raise_for_status()
                post_id = resp.headers.get("x-restli-id", "unknown")
                return f"LinkedIn post created (id: {post_id})."
        except httpx.HTTPStatusError as e:
            logger.exception("linkedin create_post HTTP error")
            return f"LinkedIn API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("linkedin create_post failed")
            return f"Error creating LinkedIn post: {e}"

    async def _draft_post(args: dict[str, Any]) -> str:
        """Draft a LinkedIn post for review (no API call)."""
        text = args.get("text", "")
        if not text:
            return "Error: text is required."
        return f"LinkedIn post draft:\n\n{text}"

    async def _draft_dm(args: dict[str, Any]) -> str:
        """Draft a LinkedIn DM (LinkedIn does not expose personal messaging API — returns limitation notice)."""
        to_name = args.get("to_name", "someone")
        text = args.get("text", "")
        if not text:
            return "Error: text is required."
        return (
            f"LinkedIn DMs are not available via the API for personal accounts. "
            f"Here is the draft you can send manually to {to_name}:\n\n{text}"
        )

    return [
        Tool(
            name="read_linkedin_profile",
            description="Read the user's LinkedIn profile (name, headline, location).",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_read_profile,
            requires_confirm=False,
        ),
        Tool(
            name="create_linkedin_post",
            description="Publish a LinkedIn post. Requires user confirmation before posting.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Post text content",
                    },
                },
                "required": ["text"],
            },
            handler=_create_post,
            requires_confirm=True,
        ),
        Tool(
            name="draft_linkedin_post",
            description="Draft a LinkedIn post for review without publishing.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Post text content",
                    },
                },
                "required": ["text"],
            },
            handler=_draft_post,
            requires_confirm=False,
        ),
        Tool(
            name="draft_linkedin_dm",
            description="Draft a LinkedIn DM. Note: LinkedIn does not expose personal messaging via API, so this only shows the draft for manual sending.",
            parameters={
                "type": "object",
                "properties": {
                    "to_name": {
                        "type": "string",
                        "description": "Recipient name",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text",
                    },
                },
                "required": ["to_name", "text"],
            },
            handler=_draft_dm,
            requires_confirm=False,
        ),
    ]
