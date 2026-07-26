"""Smoke test: Wikipedia + System tools."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis.tools.wikipedia import build_wikipedia_tools
from jarvis.tools.system import build_system_tools


async def main():
    print("=== Wikipedia Tools ===")
    wiki_tools = build_wikipedia_tools()
    for t in wiki_tools:
        print(f"  - {t.name}: {t.description[:60]}...")

    search_tool = [t for t in wiki_tools if t.name == "wiki_search"][0]
    read_tool = [t for t in wiki_tools if t.name == "wiki_read"][0]

    print("\n--- wiki_search: quantum computing ---")
    result = await search_tool.handler({"query": "quantum computing", "max_results": 3})
    print(result[:500])

    print("\n--- wiki_read: Albert Einstein ---")
    result = await read_tool.handler({"title": "Albert Einstein", "sentences": 3})
    print(result[:500])

    print("\n=== System Tools ===")
    sys_tools = build_system_tools()
    for t in sys_tools:
        print(f"  - {t.name}: {t.description[:60]}...")

    for t in sys_tools:
        print(f"\n--- {t.name} ---")
        result = await t.handler({})
        print(result[:400])

    print("\n--- list_files: ~/Desktop ---")
    list_tool = [t for t in sys_tools if t.name == "list_files"][0]
    result = await list_tool.handler({"path": "~/Desktop"})
    print(result[:500])

    print("\n--- find_files: *.py in cwd ---")
    find_tool = [t for t in sys_tools if t.name == "find_files"][0]
    result = await find_tool.handler({"pattern": "*.py", "directory": "."})
    print(result[:500])

    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
