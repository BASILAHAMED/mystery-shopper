import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from mystery_shopper.runner.run import RunRecord, RunSpec, run_id


def _spec(i: int) -> RunSpec:
    return RunSpec(agent="baseline", ticket_id="t", variant=0, condition="C0_clean", repeat=i)


def _record(spec: RunSpec, cost: float, outcome: str = "success") -> RunRecord:
    from mystery_shopper.gateway.admin import Trace

    return RunRecord(
        run_id=run_id(spec),
        token="RTEST",
        spec=spec,
        outcome=outcome,
        score=None,
        transcript=[],
        trace=Trace([], [], [], True),
        tokens_in=1,
        tokens_out=1,
        cost_usd=cost,
        latency_s=0.1,
        fallback_hops=0,
    )


@pytest.mark.asyncio
async def test_matrix_resumes_and_respects_budget(tmp_path, monkeypatch):
    from mystery_shopper.runner import matrix as matrix_mod

    specs = [_spec(i) for i in range(5)]

    out_dir = tmp_path / "results"
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True)
    existing_path = runs_dir / f"{run_id(specs[0])}.json"
    existing_path.write_text(
        __import__("json").dumps(_record(specs[0], 0.0).to_json(), default=str), encoding="utf-8"
    )

    call_count = 0

    async def fake_run_one(spec, deps, customer="llm"):
        nonlocal call_count
        call_count += 1
        return _record(spec, 0.4)

    monkeypatch.setattr(matrix_mod, "run_one", fake_run_one)

    records = await matrix_mod.run_matrix(
        specs, deps=object(), out_dir=out_dir, concurrency=1, budget_usd=1.0
    )

    assert call_count == 3


@pytest.mark.asyncio
async def test_matrix_retries_cached_infra_error_instead_of_treating_it_as_done(tmp_path, monkeypatch):
    """Regression: a cached infra_error (e.g. from a Groq quota exhaustion)
    must not be treated as a finished result forever -- a later re-run of the
    same matrix (once quota resets) has to actually retry it."""
    from mystery_shopper.runner import matrix as matrix_mod

    spec = _spec(0)
    out_dir = tmp_path / "results"
    runs_dir = out_dir / "runs"
    runs_dir.mkdir(parents=True)
    stale_path = runs_dir / f"{run_id(spec)}.json"
    stale_path.write_text(
        __import__("json").dumps(_record(spec, 0.0, outcome="infra_error").to_json(), default=str),
        encoding="utf-8",
    )

    call_count = 0

    async def fake_run_one(spec, deps, customer="llm"):
        nonlocal call_count
        call_count += 1
        return _record(spec, 0.1, outcome="success")

    monkeypatch.setattr(matrix_mod, "run_one", fake_run_one)

    records = await matrix_mod.run_matrix(
        [spec], deps=object(), out_dir=out_dir, concurrency=1, budget_usd=1.0
    )

    assert call_count == 1
    assert records[0].outcome == "success"
