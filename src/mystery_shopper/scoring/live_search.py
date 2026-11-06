"""Live-fact search for the freshness check: goes through Bifrost's Tavily
relay using the dedicated ms-sim VK (never the agent-under-test's own VK —
see docs/bifrost-friction-log.md on why a shared VK is unsafe), independent
of the shop's own `web_search` MCP tool that the agent itself calls.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import httpx


def relay_search_factory(bifrost_url: str, vk_value: str) -> Callable[[str], Awaitable[list[dict]]]:
    async def search(query: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{bifrost_url.rstrip('/')}/relay/tavily/search",
                headers={"Authorization": f"Bearer {vk_value}"},
                json={"query": query, "topic": "news", "time_range": "week", "max_results": 3},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])

    return search

