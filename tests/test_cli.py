import json
from pathlib import Path

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
