"""Run orchestration: spec -> materialized ticket -> VK -> conversation -> score.

This is the integration point for everything built in Tasks 2-10.
"""
from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
import openai

from mystery_shopper.agents.base import RunEnv, make_adapter
from mystery_shopper.agents.base import SYSTEM_PROMPT_PATH
from mystery_shopper.gateway.admin import BifrostAdmin, Trace, VKSpec
from mystery_shopper.runner.conditions import CONDITIONS, provider_configs_for
from mystery_shopper.scoring.judge import JudgeResult, judge_must_say
from mystery_shopper.scoring.score import Score, score_run
from mystery_shopper.shop.policy import Policy, ToolEvent
from mystery_shopper.sim.customer import LLMCustomer, ScriptedCustomer
from mystery_shopper.tickets.loader import expand_variants, expected_for, materialize
from mystery_shopper.tickets.models import Ticket
from mystery_shopper.tokens import new_token

SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

_OUTAGE_CONDITIONS = {"C2_model_outage", "C2x_outage_no_fallback"}


@dataclass(frozen=True)
class RunSpec:
    agent: str
    ticket_id: str
    variant: int
    condition: str
    repeat: int


def run_id(spec: RunSpec) -> str:
    return f"{spec.agent}__{spec.ticket_id}__v{spec.variant}__{spec.condition}__r{spec.repeat}"


@dataclass
class RunRecord:
    run_id: str
    token: str
    spec: RunSpec
    outcome: Literal["success", "fail", "timeout", "infra_error"]
    score: Score | None
    transcript: list[dict]
    trace: Trace
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_s: float
    fallback_hops: int
    freshness: float | None = None
    explanation: str | None = None

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class Deps:
    admin: BifrostAdmin
    shop_url: str
    proxy_url: str
    sim_client: object
    sim_model: str
    suite: dict[str, Ticket]
    policy: Policy
    settings: object
    adapter_factory: object = make_adapter
    rng: object = field(default_factory=lambda: __import__("random").Random())


def _template_index(suite: dict[str, Ticket], ticket_id: str) -> int:
    return sorted(suite.keys()).index(ticket_id) + 1


async def run_one(spec: RunSpec, deps: Deps, customer: Literal["llm", "scripted"] = "llm") -> RunRecord:
    token = new_token(deps.rng)
    condition = CONDITIONS[spec.condition]
    ticket = deps.suite[spec.ticket_id]
    template_index = _template_index(deps.suite, spec.ticket_id)
    instance = expand_variants(ticket, template_index)[spec.variant]
    m = materialize(instance, token)

    provider_configs = provider_configs_for(condition, deps.settings.fallback_mode)
    vk_spec = VKSpec(
        name=f"ms-{spec.condition}-{token}",
        provider_configs=provider_configs,
        relay=instance.live_fact is not None,
        budget_usd=deps.settings.run_vk_budget_usd,
    )
    vk = await deps.admin.create_vk(vk_spec)

    rid = run_id(spec)
    outcome: Literal["success", "fail", "timeout", "infra_error"] = "success"
    transcript: list[dict] = []
    tokens_in = tokens_out = 0
    cost_usd = 0.0
    fallback_hops = 0
    score: Score | None = None
    trace = Trace([], [], [], False)
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=30) as http:
            shop_facts = dict(m.facts)
            if condition.adversarial and m.adversarial_note and shop_facts.get("orders"):
                shop_facts["orders"] = [dict(o) for o in shop_facts["orders"]]
                shop_facts["orders"][0]["notes"] = m.adversarial_note

            await http.post(
                f"{deps.shop_url}/control/runs",
                json={
                    "token": token,
                    "facts": shop_facts,
                    "tool_faults": [
                        {
                            "tool": f.tool,
                            "mode": f.mode,
                            "calls": list(f.calls) if f.calls != "all" else "all",
                        }
                        for f in condition.tool_faults
                    ],
                },
            )

            if condition.proxy_schedule is not None:
                await http.post(
                    f"{deps.proxy_url}/control/schedules",
                    json={"token": token, "schedule": dataclasses.asdict(condition.proxy_schedule)},
                )

            env = RunEnv(
                base_url=f"{deps.settings.bifrost_url}/v1",
                api_key=vk.value,
                model=deps.settings.agent_model,
                mcp_url=f"{deps.settings.bifrost_url}/mcp",
                mcp_headers={"Authorization": f"Bearer {vk.value}"},
                system_prompt=SYSTEM_PROMPT,
                reply_timeout_s=deps.settings.reply_timeout_s,
                max_tool_steps=deps.settings.max_tool_steps,
            )

            if customer == "scripted":
                sim = ScriptedCustomer(instance.script)
            else:
                sim = LLMCustomer(
                    m,
                    adversarial=condition.adversarial,
                    client=deps.sim_client,
                    model=deps.sim_model,
                    max_turns=deps.settings.max_customer_turns,
                )

            adapter = deps.adapter_factory(spec.agent, env)

            async def _conversation() -> None:
                async with adapter:
                    for _ in range(deps.settings.max_customer_turns):
                        turn = await sim.next_message(transcript)
                        transcript.append({"role": "customer", "text": turn.text})
                        if turn.done:
                            break
                        reply = await asyncio.wait_for(
                            adapter.reply(transcript), timeout=deps.settings.reply_timeout_s
                        )
                        transcript.append({"role": "agent", "text": reply})

            try:
                await asyncio.wait_for(_conversation(), timeout=deps.settings.run_timeout_s)
            except asyncio.TimeoutError:
                outcome = "timeout"
            except openai.APIStatusError as e:
                if e.status_code == 429 or e.status_code >= 500:
                    outcome = "fail" if spec.condition in _OUTAGE_CONDITIONS else "infra_error"
                else:
                    raise

            resp = await http.get(f"{deps.shop_url}/control/runs/{token}")
            data = resp.json()
            state = data["state"]
            events = [ToolEvent(e["step"], e["name"], e["args"], e["ok"]) for e in data["events"]]

            trace = await deps.admin.wait_for_logs(vk.id, min_llm=1)

            expected = expected_for(m, adversarial=condition.adversarial)
            judge_result: JudgeResult | None = None
            if expected.must_say:
                judge_result = await judge_must_say(
                    transcript, expected.must_say, deps.sim_client, deps.sim_model
                )
            score = score_run(state, expected.db, events, m.facts, deps.policy, judge_result)
            if outcome == "success" and not score.success:
                outcome = "fail"

            tokens_in = sum(r.get("prompt_tokens", 0) for r in trace.llm)
            tokens_out = sum(r.get("completion_tokens", 0) for r in trace.llm)
            cost_usd = sum(r.get("cost", 0) for r in trace.llm)
            if spec.condition == "C2_model_outage":
                fallback_hops = sum(1 for r in trace.llm if r.get("provider") == "groq")

    finally:
        async with httpx.AsyncClient(timeout=30) as cleanup:
            try:
                await cleanup.delete(f"{deps.shop_url}/control/runs/{token}")
            except Exception:
                pass
            if condition.proxy_schedule is not None:
                try:
                    await cleanup.delete(f"{deps.proxy_url}/control/schedules/{token}")
                except Exception:
                    pass
        await deps.admin.delete_vk(vk.id)

    latency_s = time.monotonic() - start

    return RunRecord(
        run_id=rid,
        token=token,
        spec=spec,
        outcome=outcome,
        score=score,
        transcript=transcript,
        trace=trace,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_s=latency_s,
        fallback_hops=fallback_hops,
    )
