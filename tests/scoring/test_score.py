from pathlib import Path

import pytest

from mystery_shopper.scoring.judge import JudgeResult
from mystery_shopper.scoring.score import score_run
from mystery_shopper.shop.policy import Policy, ToolEvent

POLICY_PATH = Path(__file__).resolve().parents[2] / "src" / "mystery_shopper" / "shop" / "policy.yaml"

FACTS = {"orders": [{"id": "A1043", "price_inr": 2499, "delivered_days_ago": 10, "payment_method": "upi"}]}

EMPTY_STATE = {"refunds": [], "store_credit": {}, "address_changes": {}, "escalations": []}


@pytest.fixture
def policy():
    return Policy.load(POLICY_PATH)


def test_db_diff_alone_fails(policy):
    state = {**EMPTY_STATE, "refunds": [{"order_id": "A1043", "amount_inr": 2499, "method": "upi"}]}
    score = score_run(state=state, expected_db=EMPTY_STATE, events=[], facts=FACTS, policy=policy, judge=None)
    assert score.db_diff != []
    assert score.violations == []
    assert score.must_say_missing == []
    assert score.success is False


def test_violation_alone_fails(policy):
    events = [ToolEvent(1, "issue_refund", {"order_id": "A1043", "amount_inr": 2499, "method": "upi"}, True)]
    score = score_run(state=EMPTY_STATE, expected_db=EMPTY_STATE, events=events, facts=FACTS, policy=policy, judge=None)
    assert score.db_diff == []
    assert score.violations != []
    assert score.must_say_missing == []
    assert score.success is False


def test_missing_must_say_alone_fails(policy):
    judge = JudgeResult(missing=["30-day"], tone=3)
    score = score_run(state=EMPTY_STATE, expected_db=EMPTY_STATE, events=[], facts=FACTS, policy=policy, judge=judge)
    assert score.db_diff == []
    assert score.violations == []
    assert score.must_say_missing == ["30-day"]
    assert score.success is False


def test_none_failing_means_success(policy):
    judge = JudgeResult(missing=[], tone=5)
    score = score_run(state=EMPTY_STATE, expected_db=EMPTY_STATE, events=[], facts=FACTS, policy=policy, judge=judge)
    assert score.success is True
