import re
from pathlib import Path

import asyncio
import httpx
import openai
import pytest
import respx

from mystery_shopper.gateway.admin import Trace, VirtualKey, VKSpec
from mystery_shopper.runner.run import Deps, RunSpec, run_one
from mystery_shopper.settings import Settings
from mystery_shopper.shop.policy import Policy
from mystery_shopper.tickets.models import Adversarial, Expected, Persona, Ticket

SHOP_URL = "http://shop.test"
PROXY_URL = "http://proxy.test"
POLICY_PATH = Path(__file__).resolve().parents[2] / "src" / "mystery_shopper" / "shop" / "policy.yaml"


def _make_ticket(must_say=None) -> Ticket:
    return Ticket(
        id="refund-in-window",
        title="t",
        persona=Persona(name="Ravi", style="polite", language_mix="english", opener="Hi, order {order_id}"),
        hidden_goal="refund",
        facts={
            "customer": {"name": "Ravi", "email_local": "ravi", "phone_last4": "1234"},
            "orders": [
                {
                    "id": "A1043",
                    "item": "x",
                    "price_inr": 999,
                    "status": "delivered",
                    "delivered_days_ago": 5,
                    "payment_method": "upi",
                    "notes": "",
                }
            ],
            "shipments": [],
        },
        expected=Expected(db={}, must_say=must_say or []),
        expected_adversarial=None,
        policy_rules=[],
        adversarial=Adversarial(kind="urgency", lines=[], order_note=None),
        script=["hello", "thanks bye"],
        variants=[{}],
        live_fact=None,
    )


class FakeAdmin:
    def __init__(self):
        self.created: list[VKSpec] = []
        self.deleted: list[str] = []

    async def create_vk(self, spec: VKSpec) -> VirtualKey:
        self.created.append(spec)
        return VirtualKey(id="vk-test", value="sk-test-value")

    async def delete_vk(self, vk_id: str) -> None:
        self.deleted.append(vk_id)

    async def wait_for_logs(self, vk_id: str, min_llm: int, **kwargs) -> Trace:
        return Trace(llm=[], mcp=[], relay=[], complete=True)


class _SleepAdapter:
    def __init__(self, env):
        self.env = env

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def reply(self, transcript):
        import asyncio

        await asyncio.sleep(5)
        return "slow reply"


class _EchoAdapter:
    def __init__(self, env):
        self.env = env

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def reply(self, transcript):
        return "ok, sure"


class _StatusErrorAdapter:
    def __init__(self, env, status_code):
        self.env = env
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def reply(self, transcript):
        request = httpx.Request("POST", "http://x.test/v1/chat/completions")
        response = httpx.Response(self.status_code, request=request)
        raise openai.APIStatusError("boom", response=response, body=None)


def _status_error_factory(status_code):
    def factory(name, env):
        return _StatusErrorAdapter(env, status_code)

    return factory


class _GroupedStatusErrorAdapter:
    """Mimics frameworks (e.g. LangGraph) that wrap errors in a TaskGroup."""

    def __init__(self, env, status_code):
        self.env = env
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def reply(self, transcript):
        async def _inner():
            request = httpx.Request("POST", "http://x.test/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request)
            raise openai.APIStatusError("boom", response=response, body=None)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(_inner())
        return "unreachable"


def _grouped_status_error_factory(status_code):
    def factory(name, env):
        return _GroupedStatusErrorAdapter(env, status_code)

    return factory


class _RaisingSimClient:
    class _Chat:
        class _Completions:
            async def create(self, **kwargs):
                raise RuntimeError("judge boom")

        completions = _Completions()

    chat = _Chat()


def _make_deps(suite, sim_client=None, **overrides) -> Deps:
    kwargs = dict(
        bifrost_url="http://bifrost.test",
        reply_timeout_s=90,
        run_timeout_s=1,
        max_customer_turns=5,
        max_tool_steps=10,
        fallback_mode="vk_weights",
        run_vk_budget_usd=0.05,
    )
    kwargs.update(overrides)
    settings = Settings(**kwargs)
    policy = Policy.load(POLICY_PATH)
    return Deps(
        admin=FakeAdmin(),
        shop_url=SHOP_URL,
        proxy_url=PROXY_URL,
        sim_client=sim_client,
        sim_model="m",
        suite=suite,
        policy=policy,
        settings=settings,
    )


def _mock_shop_routes():
    respx.post(f"{SHOP_URL}/control/runs").mock(return_value=httpx.Response(201, json={}))
    get_route = respx.route(method="GET", url__regex=re.escape(SHOP_URL) + r"/control/runs/.*").mock(
        return_value=httpx.Response(200, json={"state": {}, "events": []})
    )
    delete_route = respx.route(
        method="DELETE", url__regex=re.escape(SHOP_URL) + r"/control/runs/.*"
    ).mock(return_value=httpx.Response(204))
    return get_route, delete_route


def _mock_proxy_routes():
    respx.post(f"{PROXY_URL}/control/schedules").mock(return_value=httpx.Response(200, json={}))
    respx.route(
        method="DELETE", url__regex=re.escape(PROXY_URL) + r"/control/schedules/.*"
    ).mock(return_value=httpx.Response(200, json={}))


@respx.mock
@pytest.mark.asyncio
async def test_run_times_out_cleanly():
    get_route, delete_route = _mock_shop_routes()

    suite = {"refund-in-window": _make_ticket()}
    deps = _make_deps(suite, run_timeout_s=1)
    deps.adapter_factory = lambda name, env: _SleepAdapter(env)
    spec = RunSpec(agent="baseline", ticket_id="refund-in-window", variant=0, condition="C0_clean", repeat=0)

    record = await run_one(spec, deps, customer="scripted")

    assert record.outcome == "timeout"
    assert deps.admin.deleted == ["vk-test"]
    assert delete_route.called


@respx.mock
@pytest.mark.asyncio
async def test_upstream_rate_limit_is_infra_error():
    _mock_shop_routes()
    _mock_proxy_routes()

    suite = {"refund-in-window": _make_ticket()}
    deps = _make_deps(suite)
    deps.adapter_factory = _status_error_factory(429)

    spec_c0 = RunSpec(agent="baseline", ticket_id="refund-in-window", variant=0, condition="C0_clean", repeat=0)
    record_c0 = await run_one(spec_c0, deps, customer="scripted")
    assert record_c0.outcome == "infra_error"

    spec_c2 = RunSpec(
        agent="baseline", ticket_id="refund-in-window", variant=0, condition="C2_model_outage", repeat=1
    )
    record_c2 = await run_one(spec_c2, deps, customer="scripted")
    assert record_c2.outcome == "fail"


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_wrapped_in_exception_group_is_still_infra_error():
    """Regression: LangGraph/LangChain wrap 429s in a TaskGroup ExceptionGroup."""
    _mock_shop_routes()
    _mock_proxy_routes()

    suite = {"refund-in-window": _make_ticket()}
    deps = _make_deps(suite)
    deps.adapter_factory = _grouped_status_error_factory(429)

    spec = RunSpec(agent="langgraph", ticket_id="refund-in-window", variant=0, condition="C0_clean", repeat=0)
    record = await run_one(spec, deps, customer="scripted")
    assert record.outcome == "infra_error"


@respx.mock
@pytest.mark.asyncio
async def test_cleanup_always_runs():
    get_route, delete_route = _mock_shop_routes()

    suite = {"refund-in-window": _make_ticket(must_say=["thanks"])}
    deps = _make_deps(suite, sim_client=_RaisingSimClient())
    deps.adapter_factory = lambda name, env: _EchoAdapter(env)
    spec = RunSpec(agent="baseline", ticket_id="refund-in-window", variant=0, condition="C0_clean", repeat=0)

    with pytest.raises(RuntimeError, match="judge boom"):
        await run_one(spec, deps, customer="scripted")

    assert deps.admin.deleted == ["vk-test"]
    assert delete_route.called


class _RateLimitedSimClient:
    class _Chat:
        class _Completions:
            async def create(self, **kwargs):
                request = httpx.Request("POST", "http://x.test/v1/chat/completions")
                response = httpx.Response(429, request=request)
                raise openai.RateLimitError("rate limited", response=response, body=None)

        completions = _Completions()

    chat = _Chat()


@respx.mock
@pytest.mark.asyncio
async def test_judge_rate_limit_is_infra_error_not_a_crash():
    """Regression: a 429 from the judge/simulator LLM (not the agent) used to
    propagate out of run_one uncaught, since only the conversation's own
    try/except handled APIStatusError."""
    get_route, delete_route = _mock_shop_routes()

    suite = {"refund-in-window": _make_ticket(must_say=["thanks"])}
    deps = _make_deps(suite, sim_client=_RateLimitedSimClient())
    deps.adapter_factory = lambda name, env: _EchoAdapter(env)
    spec = RunSpec(agent="baseline", ticket_id="refund-in-window", variant=0, condition="C0_clean", repeat=0)

    record = await run_one(spec, deps, customer="scripted")

    assert record.outcome == "infra_error"
    assert deps.admin.deleted == ["vk-test"]
