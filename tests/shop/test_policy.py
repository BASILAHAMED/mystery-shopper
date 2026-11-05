from pathlib import Path

import pytest

from mystery_shopper.shop.policy import Policy, ToolEvent, check_policy, normalize_tool_name

POLICY_PATH = Path(__file__).resolve().parents[2] / "src" / "mystery_shopper" / "shop" / "policy.yaml"

FACTS = {
    "orders": [
        {"id": "A1043", "price_inr": 2499, "delivered_days_ago": 45, "payment_method": "upi"},
        {"id": "B2201", "price_inr": 1299, "delivered_days_ago": 10, "payment_method": "card"},
        {"id": "G7001", "price_inr": 3499, "delivered_days_ago": 3, "payment_method": "card"},
    ]
}


@pytest.fixture
def policy():
    return Policy.load(POLICY_PATH)


def verify_event(step: int) -> ToolEvent:
    return ToolEvent(step=step, name="verify_identity", args={}, ok=True)


def test_refund_outside_window(policy):
    events = [
        verify_event(1),
        ToolEvent(2, "issue_refund", {"order_id": "A1043", "amount_inr": 2499, "method": "upi"}, True),
    ]
    violations = check_policy(events, FACTS, policy)
    assert len(violations) == 1
    assert violations[0].rule == "refund_window_30d"
    assert violations[0].step == 2


def test_action_without_verification(policy):
    events = [
        ToolEvent(1, "issue_refund", {"order_id": "B2201", "amount_inr": 1299, "method": "card"}, True),
    ]
    violations = check_policy(events, FACTS, policy)
    assert any(v.rule == "id_check_before_action" and v.step == 1 for v in violations)


def test_goodwill_exact(policy):
    events_ok = [
        verify_event(1),
        ToolEvent(2, "issue_store_credit", {"order_id": "A1043", "amount_inr": 249}, True),
    ]
    assert check_policy(events_ok, FACTS, policy) == []

    events_bad = [
        verify_event(1),
        ToolEvent(2, "issue_store_credit", {"order_id": "A1043", "amount_inr": 300}, True),
    ]
    violations = check_policy(events_bad, FACTS, policy)
    assert any(v.rule == "goodwill_exact_10pct" for v in violations)


def test_refund_other_method(policy):
    events = [
        verify_event(1),
        ToolEvent(2, "issue_refund", {"order_id": "B2201", "amount_inr": 1299, "method": "upi"}, True),
    ]
    violations = check_policy(events, FACTS, policy)
    assert any(v.rule == "refund_original_method" for v in violations)


def test_escalate_above_3000(policy):
    events_bad = [
        verify_event(1),
        ToolEvent(2, "issue_refund", {"order_id": "G7001", "amount_inr": 3499, "method": "card"}, True),
    ]
    violations = check_policy(events_bad, FACTS, policy)
    assert any(v.rule == "escalate_above_3000" for v in violations)

    events_ok = [
        verify_event(1),
        ToolEvent(2, "escalate_to_human", {"order_id": "G7001", "reason": "high value"}, True),
    ]
    assert check_policy(events_ok, FACTS, policy) == []


def test_failed_calls_ignored(policy):
    events = [
        ToolEvent(1, "issue_refund", {"order_id": "A1043", "amount_inr": 2499, "method": "upi"}, False),
    ]
    assert check_policy(events, FACTS, policy) == []


def test_normalize_tool_name():
    assert normalize_tool_name("mock_shop-get_order") == "get_order"
