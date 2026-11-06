import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from mystery_shopper.faultproxy.app import create_app


def _client(upstream_base="https://api.groq.com/openai/v1"):
    app = create_app(upstream_base=upstream_base, upstream_key="test-upstream-key")
    return TestClient(app)


def _body(token: str | None = None) -> dict:
    order = f"A1043-{token}" if token else "A1043"
    return {"model": "shopmodel", "messages": [{"role": "user", "content": f"order {order}"}]}


@respx.mock
def test_passthrough_without_schedule():
    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    resp = _client().post("/v1/chat/completions", json=_body())
    assert resp.status_code == 200
    assert route.call_count == 1


@respx.mock
def test_fail_first_n_then_forward():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    client = _client()
    client.post("/control/schedules", json={"token": "R7K2A", "schedule": {"mode": "fail_first_n", "n": 2}})

    statuses = []
    for _ in range(3):
        resp = client.post("/v1/chat/completions", json=_body("R7K2A"))
        statuses.append(resp.status_code)

    assert statuses == [503, 503, 200]
    stats = client.get("/control/stats/R7K2A").json()
    assert stats == {"calls": 3, "faulted": 2}


@respx.mock
def test_rate_limit_sets_retry_after():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    client = _client()
    client.post("/control/schedules", json={"token": "R9Z9Z", "schedule": {"mode": "rate_limit"}})
    resp = client.post("/v1/chat/completions", json=_body("R9Z9Z"))
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "1"


@respx.mock
def test_token_detected_from_messages():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"id": "ok"})
    )
    client = _client()
    client.post("/control/schedules", json={"token": "R7K2A", "schedule": {"mode": "fail_all", "status": 503}})

    resp_match = client.post("/v1/chat/completions", json=_body("R7K2A"))
    assert resp_match.status_code == 503

    resp_other = client.post("/v1/chat/completions", json=_body("R0000"))
    assert resp_other.status_code == 200
