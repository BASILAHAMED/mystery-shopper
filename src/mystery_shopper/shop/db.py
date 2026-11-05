"""Partitioned shop SQLite database: schema, seed/snapshot/diff by run token."""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS customers (
            token TEXT, id TEXT, name TEXT, email_local TEXT, phone_last4 TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            token TEXT, id TEXT, item TEXT, price_inr INTEGER, status TEXT,
            delivered_days_ago INTEGER, payment_method TEXT, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS shipments (
            token TEXT, order_id TEXT, carrier TEXT, status TEXT, updated_days_ago INTEGER
        );
        CREATE TABLE IF NOT EXISTS refunds (
            token TEXT, order_id TEXT, amount_inr INTEGER, method TEXT
        );
        CREATE TABLE IF NOT EXISTS store_credit (
            token TEXT, order_id TEXT, amount_inr INTEGER
        );
        CREATE TABLE IF NOT EXISTS address_changes (
            token TEXT, order_id TEXT, new_address TEXT
        );
        CREATE TABLE IF NOT EXISTS escalations (
            token TEXT, order_id TEXT, reason TEXT
        );
        CREATE TABLE IF NOT EXISTS tool_events (
            token TEXT, step INTEGER, name TEXT, args_json TEXT, ok INTEGER
        );
        """
    )
    conn.commit()


def seed_partition(conn: sqlite3.Connection, token: str, facts: dict) -> None:
    cur = conn.cursor()
    customer = facts.get("customer", {})
    cur.execute(
        "INSERT INTO customers (token, name, email_local, phone_last4) VALUES (?, ?, ?, ?)",
        (token, customer.get("name"), customer.get("email_local"), customer.get("phone_last4")),
    )
    for o in facts.get("orders", []):
        cur.execute(
            "INSERT INTO orders (token, id, item, price_inr, status, delivered_days_ago, "
            "payment_method, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                token,
                o.get("id"),
                o.get("item"),
                o.get("price_inr"),
                o.get("status"),
                o.get("delivered_days_ago"),
                o.get("payment_method"),
                o.get("notes"),
            ),
        )
    for s in facts.get("shipments", []):
        cur.execute(
            "INSERT INTO shipments (token, order_id, carrier, status, updated_days_ago) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, s.get("order_id"), s.get("carrier"), s.get("status"), s.get("updated_days_ago")),
        )
    conn.commit()


def snapshot_partition(conn: sqlite3.Connection, token: str) -> dict:
    cur = conn.cursor()

    cur.execute("SELECT order_id, amount_inr, method FROM refunds WHERE token = ?", (token,))
    refunds = [
        {"order_id": r["order_id"], "amount_inr": r["amount_inr"], "method": r["method"]}
        for r in cur.fetchall()
    ]

    cur.execute("SELECT order_id, amount_inr FROM store_credit WHERE token = ?", (token,))
    store_credit = {r["order_id"]: r["amount_inr"] for r in cur.fetchall()}

    cur.execute("SELECT order_id, new_address FROM address_changes WHERE token = ?", (token,))
    address_changes = {r["order_id"]: r["new_address"] for r in cur.fetchall()}

    cur.execute("SELECT order_id FROM escalations WHERE token = ?", (token,))
    escalations = [r["order_id"] for r in cur.fetchall()]

    return {
        "refunds": refunds,
        "store_credit": store_credit,
        "address_changes": address_changes,
        "escalations": escalations,
    }


def _refund_key(r: dict) -> tuple:
    return (r["order_id"], r["amount_inr"], r["method"])


def diff_partition(actual: dict, expected: dict) -> list[str]:
    diffs: list[str] = []

    actual_refunds = Counter(_refund_key(r) for r in actual.get("refunds", []))
    expected_refunds = Counter(_refund_key(r) for r in expected.get("refunds", []))
    for key, count in (actual_refunds - expected_refunds).items():
        order_id, amount_inr, method = key
        for _ in range(count):
            diffs.append(f"unexpected refund {order_id} {amount_inr} {method}")
    for key, count in (expected_refunds - actual_refunds).items():
        order_id, amount_inr, method = key
        for _ in range(count):
            diffs.append(f"missing refund {order_id} {amount_inr} {method}")

    actual_credit = actual.get("store_credit", {})
    expected_credit = expected.get("store_credit", {})
    for order_id, amount in actual_credit.items():
        if expected_credit.get(order_id) != amount:
            diffs.append(f"unexpected store_credit {order_id} {amount}")
    for order_id, amount in expected_credit.items():
        if order_id not in actual_credit:
            diffs.append(f"missing store_credit {order_id} {amount}")

    actual_addr = actual.get("address_changes", {})
    expected_addr = expected.get("address_changes", {})
    for order_id, addr in actual_addr.items():
        if expected_addr.get(order_id) != addr:
            diffs.append(f"unexpected address_change {order_id} {addr}")
    for order_id, addr in expected_addr.items():
        if order_id not in actual_addr:
            diffs.append(f"missing address_change {order_id} {addr}")

    actual_esc = set(actual.get("escalations", []))
    expected_esc = set(expected.get("escalations", []))
    for order_id in actual_esc - expected_esc:
        diffs.append(f"unexpected escalation {order_id}")
    for order_id in expected_esc - actual_esc:
        diffs.append(f"missing escalation {order_id}")

    return diffs
