"""OpenAI Agents SDK adapter."""
from __future__ import annotations

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStreamableHttp
from openai import AsyncOpenAI

from mystery_shopper.agents.base import RunEnv, map_role

set_tracing_disabled(True)


class OpenAIAgentsAdapter:
    name = "openai_agents"

    def __init__(self, env: RunEnv):
        self.env = env
        self._mcp_server: MCPServerStreamableHttp | None = None
        self._agent: Agent | None = None

    async def __aenter__(self) -> "OpenAIAgentsAdapter":
        self._mcp_server = MCPServerStreamableHttp(
            params={"url": self.env.mcp_url, "headers": self.env.mcp_headers},
            cache_tools_list=True,
        )
        await self._mcp_server.__aenter__()

        model = OpenAIChatCompletionsModel(
            model=self.env.model,
            openai_client=AsyncOpenAI(base_url=self.env.base_url, api_key=self.env.api_key, max_retries=2),
        )
        self._agent = Agent(
            name="shop_support_agent",
            instructions=self.env.system_prompt,
            model=model,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[self._mcp_server],
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._mcp_server is not None:
            await self._mcp_server.__aexit__(*exc)

    async def reply(self, transcript: list[dict]) -> str:
        items = [{"role": map_role(item["role"]), "content": item["text"]} for item in transcript]
        result = await Runner.run(self._agent, input=items, max_turns=self.env.max_tool_steps)
        return result.final_output
