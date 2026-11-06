import httpx
import pytest
import respx

from mystery_shopper.gateway.admin import BifrostAdmin, Trace, VirtualKey, VKSpec


def _admin(pool):
    return BifrostAdmin(base_url="http://127.0.0.1:8080", client=httpx.AsyncClient(), pool=pool)


@pytest.mark.asyncio
@respx.mock
async def test_create_vk_puts_config_shaped_correctly():
    put_route = respx.put("http://127.0.0.1:8080/api/governance/virtual-keys/vk-pool-0").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    admin = _admin([VirtualKey("vk-pool-0", "sk-bf-known-0")])
    spec = VKSpec(name="ms-C0-R7K2A", provider_configs=[{"provider": "groq", "weight": 1.0}], relay=True, budget_usd=0.05)

    await admin.create_vk(spec)

    sent = respx.calls.last.request
    import json as _json

    payload = _json.loads(sent.content)
    assert payload["mcp_configs"][0]["mcp_client_name"] == "mock_shop"
    assert payload["relay_grants"] == [{"relay_name": "tavily"}]
    assert payload["budgets"][0]["max_limit"] == 0.05
    assert put_route.called


@pytest.mark.asyncio
@respx.mock
async def test_create_vk_returns_known_pool_value_not_parsed_from_response():
    respx.put("http://127.0.0.1:8080/api/governance/virtual-keys/vk-pool-0").mock(
        return_value=httpx.Response(200, json={"virtual_key": {"id": "vk-pool-0", "value": "sk-bf-...masked"}})
    )
    admin = _admin([VirtualKey("vk-pool-0", "sk-bf-known-0")])
    spec = VKSpec(name="ms-C0-R7K2A", provider_configs=[{"provider": "groq", "weight": 1.0}])

    vk = await admin.create_vk(spec)

    assert vk == VirtualKey("vk-pool-0", "sk-bf-known-0")


@pytest.mark.asyncio
@respx.mock
async def test_delete_vk_releases_slot_back_to_pool():
    respx.put("http://127.0.0.1:8080/api/governance/virtual-keys/vk-pool-0").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    admin = _admin([VirtualKey("vk-pool-0", "sk-bf-known-0")])
    spec = VKSpec(name="ms-C0-R7K2A", provider_configs=[])

    vk1 = await admin.create_vk(spec)
    await admin.delete_vk(vk1.id)
    vk2 = await admin.create_vk(spec)

    assert vk2 == vk1


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_logs_stable():
    call_count = {"n": 0}

    def _responder(request):
        call_count["n"] += 1
        rows = min(call_count["n"], 3)
        return httpx.Response(200, json={"logs": [{"id": i} for i in range(rows)]})

    respx.get("http://127.0.0.1:8080/api/logs").mock(side_effect=_responder)
    respx.get("http://127.0.0.1:8080/api/mcp-logs").mock(return_value=httpx.Response(200, json={"logs": []}))
    respx.get("http://127.0.0.1:8080/api/relay-logs").mock(return_value=httpx.Response(200, json={"logs": []}))

    admin = _admin([])
    trace = await admin.wait_for_logs("vk-pool-0", min_llm=3, timeout_s=5.0, interval_s=0.01)

    assert len(trace.llm) == 3
    assert trace.complete is True


@pytest.mark.asyncio
@respx.mock
async def test_wait_for_logs_marks_incomplete():
    respx.get("http://127.0.0.1:8080/api/logs").mock(return_value=httpx.Response(200, json={"logs": []}))
    respx.get("http://127.0.0.1:8080/api/mcp-logs").mock(return_value=httpx.Response(200, json={"logs": []}))
    respx.get("http://127.0.0.1:8080/api/relay-logs").mock(return_value=httpx.Response(200, json={"logs": []}))

    admin = _admin([])
    trace = await admin.wait_for_logs("vk-pool-0", min_llm=1, timeout_s=0.3, interval_s=0.1)

    assert trace.complete is False
