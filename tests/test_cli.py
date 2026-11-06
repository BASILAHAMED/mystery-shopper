import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from mystery_shopper.cli import app

runner = CliRunner()


def test_gate_exit_code(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "leaderboard": [
                    {"agent": "baseline", "pass1": 0.7, "pass_k": 0.7, "runs": 10},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "gate",
            "--agent",
            "baseline",
            "--metric",
            "pass_k",
            "--min",
            "0.8",
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 1


def test_gate_exit_code_pass(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "leaderboard": [
                    {"agent": "baseline", "pass1": 0.9, "pass_k": 0.9, "runs": 10},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "gate",
            "--agent",
            "baseline",
            "--metric",
            "pass_k",
            "--min",
            "0.8",
            "--report",
            str(report_path),
        ],
    )

    assert result.exit_code == 0


def test_explain_fills_explanation_for_failed_runs_only(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    fail_record = {
        "run_id": "r1",
        "token": "T1",
        "spec": {"agent": "baseline", "ticket_id": "t", "variant": 0, "condition": "C0_clean", "repeat": 0},
        "outcome": "fail",
        "score": {
            "success": False,
            "db_diff": ["x"],
            "violations": [{"rule": "r", "step": 1, "detail": "d"}],
            "must_say_missing": [],
            "tone": None,
        },
        "transcript": [{"role": "agent", "text": "hi"}],
        "trace": {"llm": [], "mcp": [{"step": 1, "name": "issue_refund", "args": {}}], "relay": [], "complete": True},
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "latency_s": 0.0,
        "fallback_hops": 0,
    }
    success_record = {**fail_record, "run_id": "r2", "outcome": "success", "score": None}

    (runs_dir / "r1.json").write_text(json.dumps(fail_record), encoding="utf-8")
    (runs_dir / "r2.json").write_text(json.dumps(success_record), encoding="utf-8")

    fake_explain = AsyncMock(return_value="Step 1: issued a refund outside policy.")
    with patch("mystery_shopper.scoring.analyst.explain_failure", fake_explain):
        result = runner.invoke(app, ["explain", "--runs-dir", str(runs_dir)])

    assert result.exit_code == 0, result.output
    assert fake_explain.await_count == 1

    updated = json.loads((runs_dir / "r1.json").read_text(encoding="utf-8"))
    assert updated["explanation"].startswith("Step 1:")
    untouched = json.loads((runs_dir / "r2.json").read_text(encoding="utf-8"))
    assert untouched.get("explanation") is None


def test_resolve_tickets_expands_all():
    from mystery_shopper.cli import _resolve_tickets

    suite = {"b-ticket": object(), "a-ticket": object()}
    assert _resolve_tickets("all", suite) == "a-ticket,b-ticket"
    assert _resolve_tickets("a-ticket,b-ticket", suite) == "a-ticket,b-ticket"
