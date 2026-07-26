"""Instagram Graph API tools — read comments/DMs and send replies."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.instagram")

_BASE_URL = "https://graph.facebook.com/v19.0"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_instagram_tools(
    access_token: str, ig_user_id: str
) -> list[Tool]:
    """Return Instagram Graph API tools."""

    async def _read_comments(args: dict[str, Any]) -> str:
        """Read recent comments on media posts."""
        if not access_token or not ig_user_id:
            return "Error: Instagram credentials not configured."
        try:
            async with httpx.AsyncClient() as client:
                # First get recent media
                media_resp = await client.get(
                    f"{_BASE_URL}/{ig_user_id}/media",
                    headers=_headers(access_token),
                    params={"fields": "id,caption,comments{from,text,timestamp}", "limit": 5},
                    timeout=10,
                )
                media_resp.raise_for_status()
                media_data = media_resp.json()

            posts = media_data.get("data", [])
            if not posts:
                return "No recent Instagram posts found."

            lines = []
            for post in posts[:5]:
                caption = (post.get("caption") or "")[:60]
                comments = post.get("comments", {}).get("data", [])
                for comment in comments[:3]:
                    user = comment.get("from", {}).get("username", "unknown")
                    text = comment.get("text", "")
                    lines.append(f"- On '{caption}...': @{user}: {text}")

            if not lines:
                return "No recent comments on your posts."

            return "Recent Instagram comments:\n" + "\n".join(lines)
        except httpx.HTTPStatusError as e:
            logger.exception("instagram read_comments HTTP error")
            return f"Instagram API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("instagram read_comments failed")
            return f"Error reading Instagram comments: {e}"

    async def _reply_to_comment(args: dict[str, Any]) -> str:
        """Reply to a comment. Requires user confirmation."""
        if not access_token or not ig_user_id:
            return "Error: Instagram credentials not configured."
        comment_id = args.get("comment_id", "")
        text = args.get("text", "")
        if not comment_id or not text:
            return "Error: comment_id and text are required."
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{_BASE_URL}/{comment_id}/replies",
                    headers=_headers(access_token),
                    json={"message": text},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            reply_id = data.get("id", "unknown")
            return f"Reply posted (id: {reply_id})."
        except httpx.HTTPStatusError as e:
            logger.exception("instagram reply HTTP error")
            return f"Instagram API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("instagram reply failed")
            return f"Error replying on Instagram: {e}"

    async def _create_post(args: dict[str, Any]) -> str:
        """Create a new Instagram post. Requires user confirmation."""
        if not access_token or not ig_user_id:
            return "Error: Instagram credentials not configured."
        caption = args.get("caption", "")
        image_url = args.get("image_url", "")
        if not caption:
            return "Error: caption is required."
        # For Phase 1, we support text+image_url posts only
        try:
            async with httpx.AsyncClient() as client:
                if image_url:
                    # Create container with image
                    resp = await client.post(
                        f"{_BASE_URL}/{ig_user_id}/media",
                        headers=_headers(access_token),
                        json={
                            "image_url": image_url,
                            "caption": caption,
                        },
                        timeout=10,
                    )
                    resp.raise_for_status()
                    container_id = resp.json().get("id", "")

                    # Publish
                    pub_resp = await client.post(
                        f"{_BASE_URL}/{ig_user_id}/media_publish",
                        headers=_headers(access_token),
                        json={"creation_id": container_id},
                        timeout=10,
                    )
                    pub_resp.raise_for_status()
                    post_id = pub_resp.json().get("id", "unknown")
                    return f"Instagram post published (id: {post_id})."
                else:
                    # Text-only not supported by IG API — need image
                    return "Error: Instagram posts require an image_url. Use draft_instagram_post to review first."
        except httpx.HTTPStatusError as e:
            logger.exception("instagram create_post HTTP error")
            return f"Instagram API error: {e.response.status_code} {e.response.text[:200]}"
        except Exception as e:
            logger.exception("instagram create_post failed")
            return f"Error creating Instagram post: {e}"

    async def _draft_post(args: dict[str, Any]) -> str:
        """Draft a post for review without publishing."""
        caption = args.get("caption", "")
        image_url = args.get("image_url", "")
        if not caption:
            return "Error: caption is required."
        parts = [f"Caption: {caption}"]
        if image_url:
            parts.append(f"Image: {image_url}")
        return "Draft Instagram post:\n" + "\n".join(parts)

    return [
        Tool(
            name="read_instagram_comments",
            description="Read recent comments on Instagram posts.",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=_read_comments,
            requires_confirm=False,
        ),
        Tool(
            name="reply_to_instagram_comment",
            description="Reply to an Instagram comment. Requires user confirmation before posting.",
            parameters={
                "type": "object",
                "properties": {
                    "comment_id": {
                        "type": "string",
                        "description": "The Instagram comment ID to reply to",
                    },
                    "text": {
                        "type": "string",
                        "description": "Reply text",
                    },
                },
                "required": ["comment_id", "text"],
            },
            handler=_reply_to_comment,
            requires_confirm=True,
        ),
        Tool(
            name="create_instagram_post",
            description="Publish an Instagram post with caption and optional image. Requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "caption": {
                        "type": "string",
                        "description": "Post caption text",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of the image to post (required for IG posts)",
                    },
                },
                "required": ["caption"],
            },
            handler=_create_post,
            requires_confirm=True,
        ),
        Tool(
            name="draft_instagram_post",
            description="Draft an Instagram post for review without publishing.",
            parameters={
                "type": "object",
                "properties": {
                    "caption": {
                        "type": "string",
                        "description": "Post caption text",
                    },
                    "image_url": {
                        "type": "string",
                        "description": "URL of the image to post",
                    },
                },
                "required": ["caption"],
            },
            handler=_draft_post,
            requires_confirm=False,
        ),
    ]
