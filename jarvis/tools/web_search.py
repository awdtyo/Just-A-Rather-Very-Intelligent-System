"""Web search tool using DuckDuckGo — no API key required."""

from __future__ import annotations

import logging
from typing import Any

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.web_search")


def build_web_search_tools() -> list[Tool]:
    """Return web search tools (DuckDuckGo, no API key needed)."""

    async def _web_search(args: dict[str, Any]) -> str:
        args = args or {}
        query = args.get("query", "").strip()
        if not query:
            return "Error: query is required."
        max_results = args.get("max_results", 5)
        try:
            from ddgs import DDGS

            results = DDGS().text(query, max_results=max_results)
            if not results:
                return f"No search results found for: {query}"

            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                lines.append(f"{i}. {title}\n   {body}\n   {href}")

            return f"Search results for '{query}':\n\n" + "\n\n".join(lines)
        except Exception as e:
            logger.exception("web_search failed")
            return f"Search error: {e}"

    async def _web_news(args: dict[str, Any]) -> str:
        args = args or {}
        query = args.get("query", "").strip()
        if not query:
            return "Error: query is required."
        max_results = args.get("max_results", 5)
        try:
            from ddgs import DDGS

            results = DDGS().news(query, max_results=max_results)
            if not results:
                return f"No news found for: {query}"

            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                source = r.get("source", "")
                url = r.get("url", "")
                date = r.get("date", "")
                lines.append(f"{i}. [{source}] {title}\n   {body}\n   {url}\n   {date}")

            return f"News for '{query}':\n\n" + "\n\n".join(lines)
        except Exception as e:
            logger.exception("web_news failed")
            return f"News search error: {e}"

    return [
        Tool(
            name="web_search",
            description="Search the internet for information. Use this for current events, facts, people, places, or anything you don't know or aren't sure about.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
            handler=_web_search,
            requires_confirm=False,
        ),
        Tool(
            name="web_news",
            description="Search for recent news articles. Use this for current events, breaking news, or recent developments.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "News search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
            handler=_web_news,
            requires_confirm=False,
        ),
    ]
