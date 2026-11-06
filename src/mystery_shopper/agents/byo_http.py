"""Bring-your-own-agent HTTP adapter: see docs/byo-agent.md for the contract."""
from __future__ import annotations

import httpx

from mystery_shopper.agents.base import RunEnv, map_role


class ByoHttpAdapter:
    name = "byo_http"

    def __init__(self, env: RunEnv, byo_url: str):
        self.env = env
        self.byo_url = byo_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ByoHttpAdapter":
        self._client = httpx.AsyncClient(timeout=self.env.reply_timeout_s)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def reply(self, transcript: list[dict]) -> str:
        messages = [{"role": map_role(item["role"]), "content": item["text"]} for item in transcript]
        body = {
            "messages": messages,
            "env": {
                "base_url": self.env.base_url,
                "api_key": self.env.api_key,
                "model": self.env.model,
                "mcp_url": self.env.mcp_url,
                "mcp_headers": self.env.mcp_headers,
            },
        }
        resp = await self._client.post(f"{self.byo_url}/reply", json=body)
        resp.raise_for_status()
        return resp.json()["reply"]
