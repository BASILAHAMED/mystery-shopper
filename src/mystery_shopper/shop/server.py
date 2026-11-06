"""Mock shop MCP server: tools, control routes, and deterministic faults."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mystery_shopper.shop import db as shopdb
from mystery_shopper.shop.faults import ToolFault, ToolFaultSchedule
from mystery_shopper.tavily_cache import TavilyCache
from mystery_shopper.tokens import token_in


def build_server(
    db_path: Path,
    bifrost_url: str | None = None,
    tavily_cache_path: Path | None = None,
) -> FastMCP:
    conn = shopdb.connect(db_path)
    shopdb.init_schema(conn)

    if bifrost_url is None:
        from mystery_shopper.settings import Settings

        bifrost_url = Settings().bifrost_url
    bifrost_url = bifrost_url.rstrip("/")

    tavily_cache_path = tavily_cache_path or (Path(db_path).parent / "tavily_cache.json")
    tavily_cache = TavilyCache(tavily_cache_path)
    relay_client = httpx.AsyncClient(timeout=15)

    schedules: dict[str, ToolFaultSchedule] = {}
    call_counts: dict[tuple[str, str], int] = defaultdict(int)
    step_counts: dict[str, int] = defaultdict(int)
    run_meta: dict[str, dict] = {}

    mcp = FastMCP("mock_shop")

    def _record_event(token: str, name: str, args: dict, ok: bool) -> None:
        step_counts[token] += 1
        conn.execute(
            "INSERT INTO tool_events (token, step, name, args_json, ok) VALUES (?, ?, ?, ?, ?)",
            (token, step_counts[token], name, json.dumps(args), 1 if ok else 0),
        )
        conn.commit()

    def _resolve(tool_name: str, scoped_order_id: str) -> tuple[str, str]:
        token = token_in(scoped_order_id)
        if token is None:
            raise ToolError(f"unknown order {scoped_order_id}")
        call_counts[(token, tool_name)] += 1
        index = call_counts[(token, tool_name)]
        fault = schedules.get(token)
        mode = fault.decide(tool_name, index) if fault else None
        order_id = scoped_order_id.rsplit("-", 1)[0]
        return token, order_id, mode  # type: ignore[return-value]

    def _apply_fault(mode: str | None, result: dict) -> dict:
        if mode == "error500":
            raise ToolError("upstream error 500")
        if mode == "malformed":
            return {"__malformed__": '{"order_id": '}
        if mode == "partial":
            result = {k: v for k, v in result.items() if k not in ("status", "delivered_days_ago")}
        if mode == "stale":
            result = {**result, "status": "in_transit", "updated_days_ago": 9}
        return result

    @mcp.tool
    def verify_identity(email: str, phone_last4: str) -> dict:
        """Verify a customer's identity by email and the last 4 digits of their phone."""
        token = token_in(email)
        ok = False
        if token:
            row = conn.execute(
                "SELECT email_local, phone_last4 FROM customers WHERE token = ?", (token,)
            ).fetchone()
            if row:
                local = email.split("@", 1)[0].rsplit(".", 1)[0]
                ok = local == row["email_local"] and phone_last4 == row["phone_last4"]
            _record_event(token, "verify_identity", {"email": email, "verified": ok}, True)
        return {"verified": ok}

    @mcp.tool
    def get_order(order_id: str) -> dict:
        """Look up an order by its (token-scoped) id, including notes."""
        token, base_id, mode = _resolve("get_order", order_id)
        row = conn.execute(
            "SELECT item, price_inr, status, delivered_days_ago, payment_method, notes "
            "FROM orders WHERE token = ? AND id = ?",
            (token, base_id),
        ).fetchone()
        if row is None:
            _record_event(token, "get_order", {"order_id": order_id}, False)
            raise ToolError(f"unknown order {order_id}")
        try:
            result = _apply_fault(mode, dict(row))
        except ToolError:
            _record_event(token, "get_order", {"order_id": order_id}, False)
            raise
        _record_event(token, "get_order", {"order_id": order_id}, True)
        return result

    @mcp.tool
    def get_shipment(order_id: str) -> dict:
        """Look up a shipment by its (token-scoped) order id."""
        token, base_id, mode = _resolve("get_shipment", order_id)
        row = conn.execute(
            "SELECT carrier, status, updated_days_ago FROM shipments WHERE token = ? AND order_id = ?",
            (token, base_id),
        ).fetchone()
        if row is None:
            _record_event(token, "get_shipment", {"order_id": order_id}, False)
            raise ToolError(f"unknown shipment {order_id}")
        try:
            result = _apply_fault(mode, dict(row))
        except ToolError:
            _record_event(token, "get_shipment", {"order_id": order_id}, False)
            raise
        _record_event(token, "get_shipment", {"order_id": order_id}, True)
        return result

    @mcp.tool
    def issue_refund(order_id: str, amount_inr: int, method: str) -> dict:
        """Issue a refund for an order. The shop records whatever it's asked."""
        token, base_id, mode = _resolve("issue_refund", order_id)
        try:
            if mode == "error500":
                raise ToolError("upstream error 500")
            conn.execute(
                "INSERT INTO refunds (token, order_id, amount_inr, method) VALUES (?, ?, ?, ?)",
                (token, base_id, amount_inr, method),
            )
            conn.commit()
        except ToolError:
            _record_event(token, "issue_refund", {"order_id": order_id, "amount_inr": amount_inr, "method": method}, False)
            raise
        _record_event(token, "issue_refund", {"order_id": order_id, "amount_inr": amount_inr, "method": method}, True)
        return {"order_id": order_id, "amount_inr": amount_inr, "method": method}

    @mcp.tool
    def issue_store_credit(order_id: str, amount_inr: int) -> dict:
        """Issue store credit for an order."""
        token, base_id, mode = _resolve("issue_store_credit", order_id)
        try:
            if mode == "error500":
                raise ToolError("upstream error 500")
            conn.execute(
                "INSERT INTO store_credit (token, order_id, amount_inr) VALUES (?, ?, ?)",
                (token, base_id, amount_inr),
            )
            conn.commit()
        except ToolError:
            _record_event(token, "issue_store_credit", {"order_id": order_id, "amount_inr": amount_inr}, False)
            raise
        _record_event(token, "issue_store_credit", {"order_id": order_id, "amount_inr": amount_inr}, True)
        return {"order_id": order_id, "amount_inr": amount_inr}

    @mcp.tool
    def update_address(order_id: str, new_address: str) -> dict:
        """Update the delivery address for an order (only before shipment)."""
        token, base_id, mode = _resolve("update_address", order_id)
        try:
            if mode == "error500":
                raise ToolError("upstream error 500")
            conn.execute(
                "INSERT INTO address_changes (token, order_id, new_address) VALUES (?, ?, ?)",
                (token, base_id, new_address),
            )
            conn.commit()
        except ToolError:
            _record_event(token, "update_address", {"order_id": order_id, "new_address": new_address}, False)
            raise
        _record_event(token, "update_address", {"order_id": order_id, "new_address": new_address}, True)
        return {"order_id": order_id, "new_address": new_address}

    @mcp.tool
    def escalate_to_human(order_id: str, reason: str) -> dict:
        """Escalate an order to a human specialist."""
        token, base_id, mode = _resolve("escalate_to_human", order_id)
        try:
            if mode == "error500":
                raise ToolError("upstream error 500")
            conn.execute(
                "INSERT INTO escalations (token, order_id, reason) VALUES (?, ?, ?)",
                (token, base_id, reason),
            )
            conn.commit()
        except ToolError:
            _record_event(token, "escalate_to_human", {"order_id": order_id, "reason": reason}, False)
            raise
        _record_event(token, "escalate_to_human", {"order_id": order_id, "reason": reason}, True)
        return {"order_id": order_id, "reason": reason}

    @mcp.tool
    async def web_search(query: str, order_id: str) -> dict:
        """Search the web for context relevant to this order (audit: order id this search is for)."""
        token = token_in(order_id)
        if token is None:
            raise ToolError("unknown order")

        meta = run_meta.get(token, {})
        cache_key = (meta.get("ticket_id", ""), meta.get("variant", 0), query.lower().strip())
        cached = tavily_cache.get(cache_key)
        if cached is not None:
            _record_event(token, "web_search", {"query": query}, True)
            return cached

        resp = await relay_client.post(
            f"{bifrost_url}/relay/tavily/search",
            headers={"Authorization": f"Bearer {meta.get('vk_value', '')}"},
            json={"query": query, "topic": "news", "time_range": "week", "max_results": 3},
        )
        data = resp.json()
        results = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": (r.get("content") or "")[:500],
                "published_date": r.get("published_date"),
            }
            for r in data.get("results", [])
        ]
        out = {"results": results}
        tavily_cache.put(cache_key, out)
        _record_event(token, "web_search", {"query": query}, True)
        return out

    @mcp.custom_route("/control/runs", methods=["POST"])
    async def control_create_run(request: Request) -> Response:
        body = await request.json()
        token = body["token"]
        shopdb.seed_partition(conn, token, body.get("facts", {}))
        run_meta[token] = {
            "vk_value": body.get("vk_value", ""),
            "ticket_id": body.get("ticket_id", ""),
            "variant": body.get("variant", 0),
        }
        faults = [
            ToolFault(f["tool"], f["mode"], tuple(f["calls"]) if isinstance(f["calls"], list) else f["calls"])
            for f in body.get("tool_faults", [])
        ]
        schedules[token] = ToolFaultSchedule(faults)
        return JSONResponse({"token": token}, status_code=201)

    @mcp.custom_route("/control/runs/{token}", methods=["GET"])
    async def control_get_run(request: Request) -> Response:
        token = request.path_params["token"]
        row = conn.execute("SELECT 1 FROM customers WHERE token = ?", (token,)).fetchone()
        if row is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        state = shopdb.snapshot_partition(conn, token)
        events = conn.execute(
            "SELECT step, name, args_json, ok FROM tool_events WHERE token = ? ORDER BY step", (token,)
        ).fetchall()
        events_out = [
            {"step": e["step"], "name": e["name"], "args": json.loads(e["args_json"]), "ok": bool(e["ok"])}
            for e in events
        ]
        return JSONResponse({"state": state, "events": events_out})

    @mcp.custom_route("/control/runs/{token}", methods=["DELETE"])
    async def control_delete_run(request: Request) -> Response:
        token = request.path_params["token"]
        for table in (
            "customers",
            "orders",
            "shipments",
            "refunds",
            "store_credit",
            "address_changes",
            "escalations",
            "tool_events",
        ):
            conn.execute(f"DELETE FROM {table} WHERE token = ?", (token,))
        conn.commit()
        schedules.pop(token, None)
        run_meta.pop(token, None)
        return Response(status_code=204)

    return mcp


if __name__ == "__main__":
    from mystery_shopper.settings import Settings

    settings = Settings()
    server = build_server(settings.results_dir / "shop.sqlite")
    server.run(transport="http", host="127.0.0.1", port=8765, path="/mcp")
