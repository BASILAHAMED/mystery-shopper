"""Baseline agent adapter: a plain tool-call loop, no framework. ~<=120 lines."""
from __future__ import annotations

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import AsyncOpenAI

from mystery_shopper.agents.base import RunEnv, map_role


def _mcp_tool_to_openai_schema(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


class BaselineAdapter:
    name = "baseline"

    def __init__(self, env: RunEnv):
        self.env = env
        self.client = AsyncOpenAI(base_url=env.base_url, api_key=env.api_key, max_retries=2)
        self._http_client = None
        self._mcp_cm = None
        self._session: ClientSession | None = None
        self._tool_schemas: list[dict] = []

    async def __aenter__(self) -> "BaselineAdapter":
        import httpx

        self._http_client = httpx.AsyncClient(headers=self.env.mcp_headers, timeout=60)
        self._mcp_cm = streamable_http_client(self.env.mcp_url, http_client=self._http_client)
        read, write = await self._mcp_cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        tools = await self._session.list_tools()
        self._tool_schemas = [_mcp_tool_to_openai_schema(t) for t in tools.tools]
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc)
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(*exc)
        if self._http_client is not None:
            await self._http_client.aclose()

    async def reply(self, transcript: list[dict]) -> str:
        messages: list[dict] = [{"role": "system", "content": self.env.system_prompt}]
        for item in transcript:
            messages.append({"role": map_role(item["role"]), "content": item["text"]})

        for _ in range(self.env.max_tool_steps):
            response = await self.client.chat.completions.create(
                model=self.env.model,
                messages=messages,
                tools=self._tool_schemas or None,
                temperature=0,
            )
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None)

            if not tool_calls:
                return message.content or ""

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc in tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                result = await self._session.call_tool(tc.function.name, args)
                text = result.content[0].text if result.content else ""
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})

        return ""
