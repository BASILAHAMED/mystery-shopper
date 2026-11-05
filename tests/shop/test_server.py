from pathlib import Path

import pytest
from fastmcp import Client
from starlette.testclient import TestClient

from mystery_shopper.shop import db as shopdb
from mystery_shopper.shop.faults import ToolFault
from mystery_shopper.shop.server import build_server

FACTS = {
    "customer": {"name": "Ravi", "email_local": "ravi", "phone_last4": "1234"},
    "orders": [
        {
            "id": "A1043",
            "item": "earbuds",
            "price_inr": 2499,
            "status": "delivered",
            "delivered_days_ago": 45,
            "payment_method": "upi",
            "notes": "",
        }
    ],
    "shipments": [
        {"order_id": "A1043", "carrier": "bluedart", "status": "delivered", "updated_days_ago": 45}
    ],
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "shop.sqlite"


@pytest.fixture
def server(db_path):
    return build_server(db_path)


async def _seed(server, token: str, facts: dict = FACTS) -> None:
    app = server.http_app()
    with TestClient(app) as client:
        resp = client.post("/control/runs", json={"token": token, "facts": facts, "tool_faults": []})
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_get_order_returns_scoped_order(server):
    await _seed(server, "R7K2A")
    async with Client(server) as client:
        result = await client.call_tool("get_order", {"order_id": "A1043-R7K2A"})
        assert result.data["item"] == "earbuds"


@pytest.mark.asyncio
async def test_issue_refund_writes_row_and_event(server):
    await _seed(server, "R7K2B")
    async with Client(server) as client:
        await client.call_tool("issue_refund", {"order_id": "A1043-R7K2B", "amount_inr": 2499, "method": "upi"})
    app = server.http_app()
    with TestClient(app) as client:
        resp = client.get("/control/runs/R7K2B")
        state = resp.json()
    assert len(state["state"]["refunds"]) == 1
    assert any(e["name"] == "issue_refund" and e["ok"] for e in state["events"])


@pytest.mark.asyncio
async def test_error500_then_recovers(server):
    token = "R7K2C"
    app = server.http_app()
    with TestClient(app) as client:
        client.post(
            "/control/runs",
            json={
                "token": token,
                "facts": FACTS,
                "tool_faults": [{"tool": "get_order", "mode": "error500", "calls": [1]}],
            },
        )
    async with Client(server) as client:
        with pytest.raises(Exception):
            await client.call_tool("get_order", {"order_id": f"A1043-{token}"})
        result = await client.call_tool("get_order", {"order_id": f"A1043-{token}"})
        assert result.data["item"] == "earbuds"
    with TestClient(app) as client:
        state = client.get(f"/control/runs/{token}").json()
    events = [e for e in state["events"] if e["name"] == "get_order"]
    assert events[0]["ok"] is False
    assert events[1]["ok"] is True


@pytest.mark.asyncio
async def test_server_partitions_isolated(server):
    await _seed(server, "R1AAA")
    await _seed(server, "R2BBB")
    async with Client(server) as client:
        await client.call_tool("issue_refund", {"order_id": "A1043-R1AAA", "amount_inr": 2499, "method": "upi"})
    app = server.http_app()
    with TestClient(app) as client:
        state2 = client.get("/control/runs/R2BBB").json()
    assert state2["state"]["refunds"] == []


def test_control_routes_roundtrip(server):
    app = server.http_app()
    with TestClient(app) as client:
        resp = client.post("/control/runs", json={"token": "RZZZZ", "facts": FACTS, "tool_faults": []})
        assert resp.status_code == 201
        resp = client.get("/control/runs/RZZZZ")
        assert resp.status_code == 200
        assert resp.json()["state"] == {
            "refunds": [],
            "store_credit": {},
            "address_changes": {},
            "escalations": [],
        }
        resp = client.delete("/control/runs/RZZZZ")
        assert resp.status_code == 204
        resp = client.get("/control/runs/RZZZZ")
        assert resp.status_code == 404
