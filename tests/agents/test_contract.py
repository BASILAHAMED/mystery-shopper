import httpx
import pytest
import pytest_asyncio
import uvicorn

from mystery_shopper.agents.base import RunEnv, make_adapter
from mystery_shopper.shop.server import build_server
from tests.fakes.fake_llm import make_fake_llm_app

FAKE_LLM_PORT = 18080
SHOP_PORT = 18765
TOKEN = "R7K2A"

FACTS = {
    "customer": {"name": "Ravi", "email_local": "ravi", "phone_last4": "1234"},
    "orders": [
        {
            "id": "A1043",
            "item": "earbuds",
            "price_inr": 2499,
            "status": "delivered",
            "delivered_days_ago": 10,
            "payment_method": "upi",
            "notes": "",
        }
    ],
    "shipments": [],
}

SYSTEM_PROMPT = "You are a test support agent. Use tools to look up orders."


@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="module")
async def services(tmp_path_factory):
    import asyncio

    fake_llm_app = make_fake_llm_app()
    fake_llm_config = uvicorn.Config(fake_llm_app, host="127.0.0.1", port=FAKE_LLM_PORT, log_level="warning")
    fake_llm_server = uvicorn.Server(fake_llm_config)
    fake_llm_task = asyncio.create_task(fake_llm_server.serve())

    db_path = tmp_path_factory.mktemp("shop") / "shop.sqlite"
    shop_server = build_server(db_path)
    shop_app = shop_server.http_app()
    shop_config = uvicorn.Config(shop_app, host="127.0.0.1", port=SHOP_PORT, log_level="warning")
    shop_uv_server = uvicorn.Server(shop_config)
    shop_task = asyncio.create_task(shop_uv_server.serve())

    for _ in range(100):
        await asyncio.sleep(0.05)
        try:
            async with httpx.AsyncClient() as c:
                r1 = await c.get(f"http://127.0.0.1:{FAKE_LLM_PORT}/docs")
                r2 = await c.get(f"http://127.0.0.1:{SHOP_PORT}/mcp", timeout=2)
            if r1.status_code < 500:
                break
        except httpx.TransportError:
            continue

    async with httpx.AsyncClient() as c:
        await c.post(
            f"http://127.0.0.1:{SHOP_PORT}/control/runs",
            json={"token": TOKEN, "facts": FACTS, "tool_faults": []},
        )

    yield

    fake_llm_server.should_exit = True
    shop_uv_server.should_exit = True
    await asyncio.sleep(0.2)


def _env() -> RunEnv:
    return RunEnv(
        base_url=f"http://127.0.0.1:{FAKE_LLM_PORT}/v1",
        api_key="unused",
        model="shopmodel",
        mcp_url=f"http://127.0.0.1:{SHOP_PORT}/mcp",
        mcp_headers={},
        system_prompt=SYSTEM_PROMPT,
    )


async def _run_lookup(agent_name: str) -> str:
    env = _env()
    adapter = make_adapter(agent_name, env)
    async with adapter:
        reply = await adapter.reply([{"role": "customer", "text": f"Where is order A1043-{TOKEN}?"}])
    return reply


@pytest.mark.asyncio(loop_scope="module")
async def test_baseline_does_lookup_and_replies():
    reply = await _run_lookup("baseline")
    assert "delivered" in reply.lower()

    async with httpx.AsyncClient() as c:
        resp = await c.get(f"http://127.0.0.1:{SHOP_PORT}/control/runs/{TOKEN}")
    events = resp.json()["events"]
    get_order_events = [e for e in events if e["name"] == "get_order"]
    assert len(get_order_events) == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_openai_agents_does_lookup_and_replies():
    reply = await _run_lookup("openai_agents")
    assert "delivered" in reply.lower()


@pytest.mark.asyncio(loop_scope="module")
async def test_langgraph_does_lookup_and_replies():
    reply = await _run_lookup("langgraph")
    assert "delivered" in reply.lower()


@pytest.mark.asyncio(loop_scope="module")
async def test_byo_http_contract():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    byo_app = FastAPI()
    captured = {}

    @byo_app.post("/reply")
    async def reply_route(request: Request):
        body = await request.json()
        captured["body"] = body
        return JSONResponse({"reply": "hi"})

    byo_config = uvicorn.Config(byo_app, host="127.0.0.1", port=18090, log_level="warning")
    byo_server = uvicorn.Server(byo_config)
    import asyncio

    task = asyncio.create_task(byo_server.serve())
    await asyncio.sleep(0.3)

    try:
        env = _env()
        adapter = make_adapter("byo_http", env, byo_url="http://127.0.0.1:18090")
        async with adapter:
            reply = await adapter.reply([{"role": "customer", "text": "hello"}])
        assert reply == "hi"
        assert captured["body"]["messages"][0]["role"] == "user"
    finally:
        byo_server.should_exit = True
        await asyncio.sleep(0.2)
