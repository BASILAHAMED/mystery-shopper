"""Matrix runner: resumable, budget-capped, infra-retrying batch of run_one calls."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mystery_shopper.gateway.admin import Trace
from mystery_shopper.runner.run import Deps, RunRecord, RunSpec, run_id, run_one
from mystery_shopper.scoring.score import Score
from mystery_shopper.shop.policy import Violation


def _score_from_json(data: dict | None) -> Score | None:
    if data is None:
        return None
    return Score(
        success=data["success"],
        db_diff=data["db_diff"],
        violations=[Violation(**v) for v in data["violations"]],
        must_say_missing=data["must_say_missing"],
        tone=data.get("tone"),
    )


def record_from_json(data: dict) -> RunRecord:
    spec = RunSpec(**data["spec"])
    trace_data = data.get("trace") or {}
    trace = Trace(
        llm=trace_data.get("llm", []),
        mcp=trace_data.get("mcp", []),
        relay=trace_data.get("relay", []),
        complete=trace_data.get("complete", True),
    )
    return RunRecord(
        run_id=data["run_id"],
        token=data["token"],
        spec=spec,
        outcome=data["outcome"],
        score=_score_from_json(data.get("score")),
        transcript=data.get("transcript", []),
        trace=trace,
        tokens_in=data.get("tokens_in", 0),
        tokens_out=data.get("tokens_out", 0),
        cost_usd=data.get("cost_usd", 0.0),
        latency_s=data.get("latency_s", 0.0),
        fallback_hops=data.get("fallback_hops", 0),
        freshness=data.get("freshness"),
        explanation=data.get("explanation"),
    )


async def run_matrix(
    specs: list[RunSpec],
    deps: Deps,
    out_dir: Path,
    concurrency: int,
    budget_usd: float,
    max_infra_retries: int = 2,
    customer: str = "llm",
) -> list[RunRecord]:
    out_dir = Path(out_dir)
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(max(1, concurrency))
    lock = asyncio.Lock()
    state = {"cumulative_cost": 0.0, "budget_exhausted": False}

    async def _attempt(spec: RunSpec) -> RunRecord | None:
        path = runs_dir / f"{run_id(spec)}.json"
        if path.exists():
            return record_from_json(json.loads(path.read_text(encoding="utf-8")))

        async with sem:
            async with lock:
                if state["budget_exhausted"]:
                    return None

            record = None
            for _ in range(max_infra_retries + 1):
                record = await run_one(spec, deps, customer=customer)
                if record.outcome != "infra_error":
                    break

            path.write_text(
                json.dumps(record.to_json(), ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            async with lock:
                state["cumulative_cost"] += record.cost_usd
                if state["cumulative_cost"] >= budget_usd:
                    state["budget_exhausted"] = True

            return record

    results = await asyncio.gather(*(_attempt(s) for s in specs))
    return [r for r in results if r is not None]
