"""Wikipedia tools — search and read articles."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from jarvis import __version__
from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.wikipedia")

_REST_API = "https://en.wikipedia.org/api/rest_v1"
_MW_API = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": f"JarvisVoiceAssistant/{__version__} (github.com/awdtyo)"}


def build_wikipedia_tools() -> list[Tool]:
    """Return Wikipedia tools."""

    async def _wiki_search(args: dict[str, Any]) -> str:
        args = args or {}
        query = args.get("query", "").strip()
        if not query:
            return "Error: query is required."
        max_results = args.get("max_results", 5)
        try:
            async with httpx.AsyncClient(headers=_HEADERS) as client:
                resp = await client.get(
                    _MW_API,
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": max_results,
                        "format": "json",
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()

            results = data.get("query", {}).get("search", [])
            if not results:
                return f"No Wikipedia results for: {query}"

            lines = []
            for i, item in enumerate(results, 1):
                title = item["title"]
                snippet = item.get("snippet", "")
                snippet = re.sub(r"<[^>]+>", "", snippet)
                page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                lines.append(f"{i}. {title}\n   {snippet}\n   {page_url}")

            return f"Wikipedia results for '{query}':\n\n" + "\n".join(lines)
        except Exception as e:
            logger.exception("wiki_search failed")
            return f"Wikipedia search error: {e}"

    async def _wiki_read(args: dict[str, Any]) -> str:
        args = args or {}
        title = args.get("title", "").strip()
        if not title:
            return "Error: title is required."
        sentences = args.get("sentences", 5)
        try:
            async with httpx.AsyncClient(headers=_HEADERS) as client:
                resp = await client.get(
                    f"{_REST_API}/page/summary/{title}",
                    timeout=10,
                )
                if resp.status_code == 404:
                    # Try search to find the right title
                    search_resp = await client.get(
                        _MW_API,
                        params={
                            "action": "query",
                            "list": "search",
                            "srsearch": title,
                            "srlimit": 1,
                            "format": "json",
                        },
                        timeout=10,
                    )
                    search_resp.raise_for_status()
                    search_data = search_resp.json()
                    search_results = search_data.get("query", {}).get("search", [])
                    if search_results:
                        title = search_results[0]["title"]
                        resp = await client.get(
                            f"{_REST_API}/page/summary/{title}",
                            timeout=10,
                        )
                    else:
                        return f"Wikipedia article not found: {title}"

                resp.raise_for_status()
                data = resp.json()

            extract = data.get("extract", "")
            page_title = data.get("title", title)
            description = data.get("description", "")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

            parts = [f"## {page_title}"]
            if description:
                parts.append(f"*{description}*")
            if extract:
                # Truncate to roughly `sentences` sentences
                sents = extract.split(". ")
                if len(sents) > sentences:
                    extract = ". ".join(sents[:sentences]) + "."
                parts.append(extract)
            if page_url:
                parts.append(f"\nRead more: {page_url}")

            return "\n".join(parts)
        except Exception as e:
            logger.exception("wiki_read failed")
            return f"Wikipedia read error: {e}"

    return [
        Tool(
            name="wiki_search",
            description="Search Wikipedia for articles. Use this to find encyclopedic information about topics, people, places, concepts, etc.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                    },
                },
                "required": ["query"],
            },
            handler=_wiki_search,
            requires_confirm=False,
        ),
        Tool(
            name="wiki_read",
            description="Read a Wikipedia article summary. Use this after wiki_search to get detailed information about a specific topic.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Wikipedia article title (e.g. 'Artificial intelligence')",
                    },
                    "sentences": {
                        "type": "integer",
                        "description": "Number of sentences to return (default 5)",
                    },
                },
                "required": ["title"],
            },
            handler=_wiki_read,
            requires_confirm=False,
        ),
    ]
