"""Shared agent environment, adapter protocol, and factory."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass
class RunEnv:
    base_url: str
    api_key: str
    model: str
    mcp_url: str
    mcp_headers: dict[str, str]
    system_prompt: str
    reply_timeout_s: int = 90
    max_tool_steps: int = 10


class AgentAdapter(Protocol):
    name: str

    async def __aenter__(self) -> "AgentAdapter": ...

    async def __aexit__(self, *exc) -> None: ...

    async def reply(self, transcript: list[dict]) -> str: ...


def map_role(role: str) -> str:
    return "assistant" if role == "agent" else "user"


def make_adapter(
    name: Literal["openai_agents", "langgraph", "baseline", "byo_http"],
    env: RunEnv,
    byo_url: str | None = None,
) -> AgentAdapter:
    if name == "openai_agents":
        from mystery_shopper.agents.openai_agents import OpenAIAgentsAdapter

        return OpenAIAgentsAdapter(env)
    if name == "langgraph":
        from mystery_shopper.agents.langgraph_react import LangGraphAdapter

        return LangGraphAdapter(env)
    if name == "baseline":
        from mystery_shopper.agents.baseline import BaselineAdapter

        return BaselineAdapter(env)
    if name == "byo_http":
        from mystery_shopper.agents.byo_http import ByoHttpAdapter

        if byo_url is None:
            raise ValueError("byo_url is required for the byo_http adapter")
        return ByoHttpAdapter(env, byo_url)
    raise ValueError(f"unknown adapter: {name}")


SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.md"
