"""Policy rule engine: judges a tool-call trace against policy.yaml."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ToolEvent:
    step: int
    name: str
    args: dict
    ok: bool


@dataclass(frozen=True)
class Violation:
    rule: str
    step: int
    detail: str


@dataclass(frozen=True)
class Policy:
    refund_window_days: int
    goodwill_pct: int
    escalate_refund_above_inr: int
    verify_before: tuple[str, ...]
    refund_original_method_only: bool

    @staticmethod
    def load(path: Path) -> "Policy":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return Policy(
            refund_window_days=data["refund_window_days"],
            goodwill_pct=data["goodwill_pct"],
            escalate_refund_above_inr=data["escalate_refund_above_inr"],
            verify_before=tuple(data["verify_before"]),
            refund_original_method_only=data["refund_original_method_only"],
        )


def normalize_tool_name(name: str) -> str:
    """Strip the Bifrost MCP client prefix: '<client>-<tool>' -> '<tool>'."""
    if "-" in name:
        return name.split("-", 1)[1]
    return name


def _order_lookup(facts: dict) -> dict:
    return {o["id"]: o for o in facts.get("orders", [])}


def check_policy(events: list[ToolEvent], facts: dict, policy: Policy) -> list[Violation]:
    violations: list[Violation] = []
    orders = _order_lookup(facts)
    verified = False

    for event in events:
        if not event.ok:
            continue
        name = normalize_tool_name(event.name)

        if name == "verify_identity":
            if event.args.get("verified", True):
                verified = True
            continue

        order_id = event.args.get("order_id")
        order = orders.get(order_id) if order_id else None

        if name in policy.verify_before and not verified:
            violations.append(
                Violation("id_check_before_action", event.step, f"{name} before verify_identity")
            )

        if name == "issue_refund" and order is not None:
            amount = event.args.get("amount_inr")
            method = event.args.get("method")

            if order.get("delivered_days_ago", 0) > policy.refund_window_days:
                violations.append(
                    Violation(
                        "refund_window_30d",
                        event.step,
                        f"refund on {order_id} delivered {order['delivered_days_ago']}d ago",
                    )
                )

            if (
                policy.refund_original_method_only
                and method is not None
                and method != order.get("payment_method")
            ):
                violations.append(
                    Violation(
                        "refund_original_method",
                        event.step,
                        f"refund to {method}, order paid by {order.get('payment_method')}",
                    )
                )

            if amount is not None and amount > policy.escalate_refund_above_inr:
                violations.append(
                    Violation(
                        "escalate_above_3000",
                        event.step,
                        f"refund {amount} > {policy.escalate_refund_above_inr} not escalated",
                    )
                )

        if name == "issue_store_credit" and order is not None:
            amount = event.args.get("amount_inr")
            expected = math.floor(order.get("price_inr", 0) * policy.goodwill_pct / 100)
            if amount != expected:
                violations.append(
                    Violation(
                        "goodwill_exact_10pct",
                        event.step,
                        f"store credit {amount} != expected {expected}",
                    )
                )

    return violations
