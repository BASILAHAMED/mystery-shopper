from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from mystery_shopper.shop.server import build_server

FACTS = {
    "customer": {"name": "Ravi", "email_local": "ravi", "phone_last4": "1234"},
    "orders": [
        {
            "id": "H8801",
            "item": "desk lamp",
            "price_inr": 1299,
            "status": "shipped",
            "delivered_days_ago": 0,
            "payment_method": "upi",
            "notes": "",
        }
    ],
    "shipments": [],
}

BIFROST_URL = "http://bifrost.test"


@pytest.fixture
def server(tmp_path):
    return build_server(
        tmp_path / "shop.sqlite",
        bifrost_url=BIFROST_URL,
        tavily_cache_path=tmp_path / "tavily_cache.json",
    )


def _seed(server, token: str, vk_value: str = "sk-bf-run") -> None:
    app = server.http_app()
    with TestClient(app) as client:
        resp = client.post(
            "/control/runs",
            json={
                "token": token,
                "facts": FACTS,
                "tool_faults": [],
                "vk_value": vk_value,
                "ticket_id": "carrier-alert-live-fact",
                "variant": 0,
            },
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_web_search_requires_scoped_order_id(server):
    async with Client(server) as client:
        with pytest.raises(ToolError):
            await client.call_tool("web_search", {"query": "carrier delay news", "order_id": "H8801"})


@respx.mock
@pytest.mark.asyncio
async def test_web_search_uses_run_vk_and_caches(server):
    _seed(server, "R7K2A")

    route = respx.post(f"{BIFROST_URL}/relay/tavily/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Carrier delay",
                        "url": "https://example.com/a",
                        "content": "x" * 600,
                        "published_date": "2026-11-01",
                    }
                ]
            },
        )
    )

    async with Client(server) as client:
        result1 = await client.call_tool(
            "web_search", {"query": "carrier delay news", "order_id": "H8801-R7K2A"}
        )
        result2 = await client.call_tool(
            "web_search", {"query": "carrier delay news", "order_id": "H8801-R7K2A"}
        )

    assert route.called
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer sk-bf-run"
    assert len(result1.data["results"][0]["content"]) <= 500
    assert result1.data == result2.data
