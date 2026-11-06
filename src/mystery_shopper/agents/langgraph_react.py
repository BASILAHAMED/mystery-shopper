"""LangGraph prebuilt ReAct agent adapter.

langchain-mcp-adapters (0.3.1, the latest on PyPI at build time) imports
`mcp.shared.context.RequestContext`, which doesn't exist in the installed
`mcp` 2.3.0 SDK (langchain-mcp-adapters 0.3.2 fixes the import but pins
`mcp<2.0.0`, which conflicts with fastmcp's `mcp>=2.3.0` requirement — there
is no released version compatible with both). See
docs/bifrost-friction-log.md. Worked around by bridging MCP tools to
LangChain's StructuredTool directly with the same `mcp` client session the
baseline adapter uses, instead of going through langchain-mcp-adapters.
create_react_agent is still the real, unmodified LangGraph prebuilt agent.
"""
from __future__ import annotations

import httpx
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import create_model

from mystery_shopper.agents.base import RunEnv, map_role

_TYPE_MAP = {"string": str, "integer": int, "number": float, "boolean": bool}


def _schema_to_pydantic(name: str, schema: dict):
    props = (schema or {}).get("properties", {})
    required = set((schema or {}).get("required", []))
    fields = {}
    for key, spec in props.items():
        py_type = _TYPE_MAP.get(spec.get("type"), str)
        fields[key] = (py_type, ... if key in required else None)
    return create_model(f"{name}_Args", **fields)


def _make_tool(session: ClientSession, mcp_tool) -> StructuredTool:
    args_model = _schema_to_pydantic(mcp_tool.name, mcp_tool.input_schema)

    async def _call(**kwargs):
        result = await session.call_tool(mcp_tool.name, kwargs)
        return result.content[0].text if result.content else ""

    return StructuredTool(
        name=mcp_tool.name,
        description=mcp_tool.description or "",
        args_schema=args_model,
        coroutine=_call,
        func=None,
    )


class LangGraphAdapter:
    name = "langgraph"

    def __init__(self, env: RunEnv):
        self.env = env
        self._http_client: httpx.AsyncClient | None = None
        self._mcp_cm = None
        self._session: ClientSession | None = None
        self._agent = None

    async def __aenter__(self) -> "LangGraphAdapter":
        self._http_client = httpx.AsyncClient(headers=self.env.mcp_headers, timeout=60)
        self._mcp_cm = streamable_http_client(self.env.mcp_url, http_client=self._http_client)
        read, write = await self._mcp_cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

        mcp_tools = await self._session.list_tools()
        tools = [_make_tool(self._session, t) for t in mcp_tools.tools]

        model = ChatOpenAI(
            model=self.env.model,
            base_url=self.env.base_url,
            api_key=self.env.api_key,
            temperature=0,
            max_retries=2,
        )
        self._agent = create_react_agent(model, tools, prompt=self.env.system_prompt)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc)
        if self._mcp_cm is not None:
            await self._mcp_cm.__aexit__(*exc)
        if self._http_client is not None:
            await self._http_client.aclose()

    async def reply(self, transcript: list[dict]) -> str:
        messages = [{"role": map_role(item["role"]), "content": item["text"]} for item in transcript]
        result = await self._agent.ainvoke(
            {"messages": messages}, {"recursion_limit": 2 * self.env.max_tool_steps + 1}
        )
        return result["messages"][-1].content
