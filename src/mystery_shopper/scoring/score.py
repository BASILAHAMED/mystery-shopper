"""Deterministic run scoring: DB diff + policy violations + judge must-say."""
from __future__ import annotations

from dataclasses import dataclass

from mystery_shopper.scoring.judge import JudgeResult
from mystery_shopper.shop.db import diff_partition
from mystery_shopper.shop.policy import Policy, ToolEvent, Violation, check_policy


@dataclass
class Score:
    success: bool
    db_diff: list[str]
    violations: list[Violation]
    must_say_missing: list[str]
    tone: int | None


def score_run(
    state: dict,
    expected_db: dict,
    events: list[ToolEvent],
    facts: dict,
    policy: Policy,
    judge: JudgeResult | None,
) -> Score:
    db_diff = diff_partition(state, expected_db)
    violations = check_policy(events, facts, policy)
    must_say_missing = judge.missing if judge is not None else []
    tone = judge.tone if judge is not None else None

    success = not db_diff and not violations and (judge is None or not judge.missing)

    return Score(
        success=success,
        db_diff=db_diff,
        violations=violations,
        must_say_missing=must_say_missing,
        tone=tone,
    )
