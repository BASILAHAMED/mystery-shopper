"""Statistics: pass^k, bootstrap CIs, paired significance, degradation, the report."""
from __future__ import annotations

import random
from collections import defaultdict
from math import comb
from typing import Iterable


def _group(records: Iterable) -> dict[tuple, list[bool]]:
    groups: dict[tuple, list[bool]] = defaultdict(list)
    for r in records:
        if r.outcome == "infra_error":
            continue
        key = (r.spec.agent, r.spec.ticket_id, r.spec.variant, r.spec.condition)
        groups[key].append(r.outcome == "success")
    return groups


def pass_hat_k(records: Iterable, k: int) -> float:
    values: list[float] = []
    for outcomes in _group(records).values():
        n = len(outcomes)
        if n < k:
            continue
        c = sum(outcomes)
        values.append(comb(c, k) / comb(n, k))
    return sum(values) / len(values) if values else 0.0


def pass_at_1(records: Iterable) -> float:
    return pass_hat_k(records, k=1)


def bootstrap_ci(
    values: list[float], iters: int = 10000, seed: int = 1234, alpha: float = 0.05
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iters):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * iters)
    hi_idx = min(int((1 - alpha / 2) * iters), iters - 1)
    return (means[lo_idx], means[hi_idx])


def paired_diff(
    a: dict[str, float], b: dict[str, float], iters: int = 10000, seed: int = 1234
) -> tuple[float, tuple[float, float], bool]:
    keys = sorted(set(a) & set(b))
    diffs = [a[k] - b[k] for k in keys]
    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    lo, hi = bootstrap_ci(diffs, iters=iters, seed=seed)
    significant = not (lo <= 0 <= hi)
    return mean_diff, (lo, hi), significant


def degradation(records: Iterable, agent: str, condition: str) -> float:
    records = list(records)
    c0 = [r for r in records if r.spec.agent == agent and r.spec.condition == "C0_clean"]
    cond = [r for r in records if r.spec.agent == agent and r.spec.condition == condition]
    return pass_at_1(c0) - pass_at_1(cond)


def build_report(records: Iterable, k: int) -> dict:
    import datetime

    records = list(records)
    agents = sorted({r.spec.agent for r in records})
    conditions = sorted({r.spec.condition for r in records})

    leaderboard = []
    matrix: dict[str, dict[str, float]] = {}
    degradation_table: dict[str, dict[str, float]] = {}

    for agent in agents:
        agent_records = [r for r in records if r.spec.agent == agent]
        non_infra = [r for r in agent_records if r.outcome != "infra_error"]
        p1 = pass_at_1(agent_records)
        pk = pass_hat_k(agent_records, k)
        ci_low, ci_high = bootstrap_ci(
            [1.0 if r.outcome == "success" else 0.0 for r in non_infra]
        )

        successes = [r for r in non_infra if r.outcome == "success"]
        total_cost = sum(r.cost_usd for r in agent_records)
        cost_per_resolved = total_cost / len(successes) if successes else None

        violations_total = sum(
            len(r.score.violations) for r in non_infra if r.score is not None
        )
        violation_rate = violations_total / len(non_infra) if non_infra else 0.0

        freshness_values = [
            r.freshness for r in agent_records if r.freshness is not None
        ]
        freshness_mean = (
            sum(freshness_values) / len(freshness_values) if freshness_values else None
        )

        leaderboard.append(
            {
                "agent": agent,
                "pass1": p1,
                "pass_k": pk,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "cost_per_resolved_usd": cost_per_resolved,
                "violation_rate": violation_rate,
                "freshness_mean": freshness_mean,
                "runs": len(agent_records),
            }
        )

        matrix[agent] = {
            cond: pass_at_1([r for r in agent_records if r.spec.condition == cond])
            for cond in conditions
        }
        degradation_table[agent] = {
            cond: degradation(records, agent, cond) for cond in conditions if cond != "C0_clean"
        }

    # NOTE: RunRecord/RunSpec don't carry which customer type (llm vs scripted)
    # produced a run, so this can't be computed from a single record set yet.
    # ms run writes llm- and scripted-customer runs to separate --tickets runs;
    # a real simulator_effect needs both passed in separately. Placeholder 0.0
    # until that plumbing exists; see docs/methodology.md.
    simulator_effect = {agent: 0.0 for agent in agents}

    totals = {
        "runs": len(records),
        "cost_usd": sum(r.cost_usd for r in records),
        "tokens": sum(r.tokens_in + r.tokens_out for r in records),
    }

    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "k": k,
        "agents": agents,
        "leaderboard": leaderboard,
        "matrix": matrix,
        "degradation": degradation_table,
        "simulator_effect": simulator_effect,
        "totals": totals,
    }
