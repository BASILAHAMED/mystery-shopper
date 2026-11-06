"""Deterministic OpenAI-compatible fault proxy, registered as a Bifrost custom provider."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mystery_shopper.tokens import token_in


@dataclass(frozen=True)
class ProxySchedule:
    mode: Literal["fail_all", "fail_first_n", "rate_limit", "latency"]
    n: int = 0
    status: int = 503
    latency_ms: int = 0


def create_app(
    upstream_base: str = "https://api.groq.com/openai/v1",
    upstream_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> FastAPI:
    upstream_key = upstream_key or os.environ.get("GROQ_API_KEY", "")
    app = FastAPI()
    app.state.client = client or httpx.AsyncClient()
    schedules: dict[str, ProxySchedule] = {}
    stats: dict[str, dict[str, int]] = {}

    async def _handle(request: Request):
        body = await request.json()
        if body.get("stream"):
            return JSONResponse({"error": {"message": "streaming not supported"}}, status_code=400)

        token = token_in(json.dumps(body.get("messages", [])))
        schedule = schedules.get(token) if token else None

        if token is not None:
            s = stats.setdefault(token, {"calls": 0, "faulted": 0})
            s["calls"] += 1

        if schedule is not None:
            call_index = stats[token]["calls"]

            if schedule.mode == "fail_all":
                stats[token]["faulted"] += 1
                return JSONResponse(
                    {"error": {"message": "injected outage", "type": "server_error"}},
                    status_code=schedule.status,
                )

            if schedule.mode == "fail_first_n" and call_index <= schedule.n:
                stats[token]["faulted"] += 1
                return JSONResponse(
                    {"error": {"message": "injected outage", "type": "server_error"}},
                    status_code=schedule.status,
                )

            if schedule.mode == "rate_limit":
                stats[token]["faulted"] += 1
                return JSONResponse(
                    {"error": {"message": "rate limited", "type": "rate_limit_error"}},
                    status_code=429,
                    headers={"Retry-After": "1"},
                )

            if schedule.mode == "latency":
                import asyncio

                await asyncio.sleep(schedule.latency_ms / 1000)

        http_client: httpx.AsyncClient = app.state.client
        upstream_resp = await http_client.post(
            f"{upstream_base}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {upstream_key}"},
        )
        return JSONResponse(upstream_resp.json(), status_code=upstream_resp.status_code)

    @app.post("/v1/chat/completions")
    async def chat_completions_v1(request: Request):
        return await _handle(request)

    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        return await _handle(request)

    @app.post("/control/schedules")
    async def control_set_schedule(request: Request):
        body = await request.json()
        schedules[body["token"]] = ProxySchedule(**body["schedule"])
        return JSONResponse({"ok": True})

    @app.delete("/control/schedules/{token}")
    async def control_delete_schedule(token: str):
        schedules.pop(token, None)
        return JSONResponse({"ok": True})

    @app.get("/control/stats/{token}")
    async def control_stats(token: str):
        return JSONResponse(stats.get(token, {"calls": 0, "faulted": 0}))

    return app


app = create_app()
