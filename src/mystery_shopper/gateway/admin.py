"""Bifrost admin client: VK pool lifecycle (see docs/gates.md S1 ruling) and log polling.

POST /api/governance/virtual-keys never reveals a usable plaintext secret in the
installed Bifrost line (confirmed upstream bug, see docs/bifrost-friction-log.md).
Virtual keys are instead pre-provisioned as a POOL of statically-valued entries in
bifrost/config.json (governance.virtual_keys[], env.* refs). create_vk() claims a
free slot and PUTs it into the run's shape; delete_vk() releases the slot back to
the pool instead of literally deleting it.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class VKSpec:
    name: str
    provider_configs: list[dict]
    mcp_tools: list[str] | None = None
    relay: bool = False
    budget_usd: float = 0.05
    ttl_s: int = 3600


@dataclass(frozen=True)
class VirtualKey:
    id: str
    value: str


@dataclass
class Trace:
    llm: list[dict]
    mcp: list[dict]
    relay: list[dict]
    complete: bool


class BifrostAdmin:
    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        pool: list[VirtualKey] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient()
        self._free: list[VirtualKey] = list(pool or [])
        self._in_use: dict[str, VirtualKey] = {}

    async def create_vk(self, spec: VKSpec) -> VirtualKey:
        if not self._free:
            raise RuntimeError("virtual key pool exhausted")
        vk = self._free.pop(0)
        self._in_use[vk.id] = vk

        body = {
            "name": spec.name,
            "provider_configs": spec.provider_configs,
            "mcp_configs": [{"mcp_client_name": "mock_shop", "tools_to_execute": spec.mcp_tools or ["*"]}],
            "relay_grants": [{"relay_name": "tavily"}] if spec.relay else [],
            "budgets": [{"max_limit": spec.budget_usd, "reset_duration": "1d"}],
            "is_active": True,
        }
        await self.client.put(f"{self.base_url}/api/governance/virtual-keys/{vk.id}", json=body)
        return vk

    async def delete_vk(self, vk_id: str) -> None:
        body = {"is_active": False, "provider_configs": [], "mcp_configs": [], "relay_grants": []}
        await self.client.put(f"{self.base_url}/api/governance/virtual-keys/{vk_id}", json=body)
        vk = self._in_use.pop(vk_id, None)
        if vk is not None:
            self._free.append(vk)

    async def logs(self, vk_id: str) -> Trace:
        params = {"virtual_key_ids": vk_id, "limit": 500}
        llm_resp = await self.client.get(f"{self.base_url}/api/logs", params=params)
        mcp_resp = await self.client.get(f"{self.base_url}/api/mcp-logs", params=params)
        relay_resp = await self.client.get(f"{self.base_url}/api/relay-logs", params=params)
        return Trace(
            llm=llm_resp.json().get("logs", []),
            mcp=mcp_resp.json().get("logs", []),
            relay=relay_resp.json().get("logs", []),
            complete=True,
        )

    async def wait_for_logs(
        self, vk_id: str, min_llm: int, timeout_s: float = 20.0, interval_s: float = 1.0
    ) -> Trace:
        start = time.monotonic()
        prev_counts: tuple[int, int, int] | None = None
        stable_polls = 0
        trace = Trace([], [], [], False)

        while time.monotonic() - start < timeout_s:
            trace = await self.logs(vk_id)
            counts = (len(trace.llm), len(trace.mcp), len(trace.relay))
            if len(trace.llm) >= min_llm:
                if counts == prev_counts:
                    stable_polls += 1
                    if stable_polls >= 2:
                        trace.complete = True
                        return trace
                else:
                    stable_polls = 1
                prev_counts = counts
            await asyncio.sleep(interval_s)

        trace.complete = False
        return trace
