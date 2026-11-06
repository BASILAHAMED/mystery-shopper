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


def _run_dict(run_id, ticket_id, condition, outcome, violations=0, repeat=0):
    return {
        "run_id": run_id,
        "token": "T1",
        "spec": {
            "agent": "baseline",
            "ticket_id": ticket_id,
            "variant": 0,
            "condition": condition,
            "repeat": repeat,
        },
        "outcome": outcome,
        "score": {
            "success": outcome == "success",
            "db_diff": [],
            "violations": [{"rule": "r", "step": i, "detail": "d"} for i in range(violations)],
            "must_say_missing": [],
            "tone": None,
        }
        if outcome != "infra_error"
        else None,
        "transcript": [],
        "trace": {"llm": [], "mcp": [], "relay": [], "complete": True},
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "latency_s": 0.0,
        "fallback_hops": 0,
        "freshness": None,
        "explanation": None,
    }


def test_snapshot_selects_bounded_run_set(tmp_path):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    ui_dir = tmp_path / "ui"

    runs = []
    # "a-ticket" is alphabetically first; all its C1_adversarial runs must be included.
    for i in range(3):
        runs.append(
            _run_dict(f"agent__a-ticket__v0__C1_adversarial__r{i}", "a-ticket", "C1_adversarial", "success", repeat=i)
        )
    runs.append(_run_dict("agent__a-ticket__v0__C0_clean__r0", "a-ticket", "C0_clean", "success"))
    # b-ticket runs should not be pulled in via the C1 rule.
    runs.append(_run_dict("agent__b-ticket__v0__C1_adversarial__r0", "b-ticket", "C1_adversarial", "fail", violations=1))

    # 25 failed runs with varying violation counts; only the top 20 by violation count should survive.
    for i in range(25):
        runs.append(
            _run_dict(f"agent__b-ticket__v0__C3_broken_tool__r{i}", "b-ticket", "C3_broken_tool", "fail", violations=i, repeat=i)
        )

    for r in runs:
        (runs_dir / f"{r['run_id']}.json").write_text(json.dumps(r), encoding="utf-8")

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"leaderboard": [], "agents": []}), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "snapshot",
            "--report",
            str(report_path),
            "--runs-dir",
            str(runs_dir),
            "--ui-dir",
            str(ui_dir),
        ],
    )
    assert result.exit_code == 0, result.output

    index = json.loads((ui_dir / "public" / "data" / "runs" / "index.json").read_text(encoding="utf-8"))

    # All 3 C1_adversarial runs of the first ticket (a-ticket) are included.
    for i in range(3):
        assert f"agent__a-ticket__v0__C1_adversarial__r{i}" in index
    assert "agent__a-ticket__v0__C0_clean__r0" not in index
    assert "agent__b-ticket__v0__C1_adversarial__r0" not in index

    # The 20 failed runs with the most violations (r24..r5) are included.
    for i in range(5, 25):
        assert f"agent__b-ticket__v0__C3_broken_tool__r{i}" in index
    for i in range(0, 5):
        assert f"agent__b-ticket__v0__C3_broken_tool__r{i}" not in index

    copied = sorted(p.stem for p in (ui_dir / "public" / "data" / "runs").glob("*.json") if p.stem != "index")
    assert copied == sorted(index)
    assert len(copied) <= 300

    report_copy = json.loads((ui_dir / "public" / "data" / "report.json").read_text(encoding="utf-8"))
    assert report_copy == json.loads(report_path.read_text(encoding="utf-8"))
