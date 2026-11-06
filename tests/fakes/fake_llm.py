"""Fake OpenAI-compatible chat server for agent-adapter contract tests.

Deterministic: if the last turn is a user message naming an order id, emit a
`get_order` tool call for it. If the last turn is a tool result, reply with
plain text confirming delivery.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_ORDER_RE = re.compile(r"\b([A-H]\d{4}-R[A-Z0-9]{4})\b")


def _chat_completion(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    message: dict = {"role": "assistant", "content": content}
    finish_reason = "stop"
    if tool_calls:
        message["tool_calls"] = tool_calls
        message["content"] = None
        finish_reason = "tool_calls"
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "shopmodel",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def make_fake_llm_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        last = messages[-1] if messages else {}

        if last.get("role") == "tool":
            order_id = None
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
                    order_id = args.get("order_id")
                    break
            return JSONResponse(_chat_completion(content=f"Your order {order_id} was delivered."))

        text = " ".join(str(m.get("content") or "") for m in messages)
        match = _ORDER_RE.search(text)
        if match:
            order_id = match.group(1)
            tool_call = {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_order", "arguments": json.dumps({"order_id": order_id})},
            }
            return JSONResponse(_chat_completion(tool_calls=[tool_call]))

        return JSONResponse(_chat_completion(content="How can I help?"))

    return app
