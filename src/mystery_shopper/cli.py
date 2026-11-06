"""Mystery Shopper CLI: up, run, report, gate."""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import random
import subprocess
import time
from pathlib import Path

import httpx
import typer
from dotenv import load_dotenv
from openai import AsyncOpenAI

from mystery_shopper.agents.base import SYSTEM_PROMPT_PATH
from mystery_shopper.gateway.admin import BifrostAdmin, VirtualKey, VKSpec
from mystery_shopper.runner.matrix import run_matrix
from mystery_shopper.runner.run import Deps, RunSpec
from mystery_shopper.settings import Settings
from mystery_shopper.shop.policy import Policy
from mystery_shopper.stats.metrics import build_report
from mystery_shopper.tickets.loader import load_suite

app = typer.Typer()
ROOT = Path(__file__).resolve().parents[2]


def _pool_from_env() -> list[VirtualKey]:
    pool = []
    i = 0
    while True:
        key = f"MS_POOL_VK_0{i}"
        value = os.environ.get(key)
        if value is None:
            break
        pool_id = "vk-ms-pool-test" if i == 0 else f"vk-ms-pool-{i}"
        pool.append(VirtualKey(id=pool_id, value=value))
        i += 1
    return pool


def _wait_for(url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=3)
            if r.status_code < 500:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    return False


@app.command()
def up() -> None:
    """Start Bifrost, the mock shop, and the fault proxy; create/reuse the ms-sim VK."""
    load_dotenv(ROOT / ".env")
    settings = Settings()

    env = {**os.environ, "BIFROST_SETUP_TOKEN": os.environ.get("MS_BIFROST_SETUP_TOKEN", "")}
    typer.echo("Starting Bifrost...")
    subprocess.Popen(
        ["npx", "-y", "@maximhq/bifrost", "-app-dir", "bifrost", "-host", "127.0.0.1", "-port", "8080"],
        cwd=ROOT,
        env=env,
    )
    typer.echo("Starting mock shop...")
    subprocess.Popen(["uv", "run", "python", "-m", "mystery_shopper.shop.server"], cwd=ROOT, env=env)
    typer.echo("Starting fault proxy...")
    subprocess.Popen(
        ["uv", "run", "uvicorn", "mystery_shopper.faultproxy.app:app", "--port", "8766"], cwd=ROOT, env=env
    )

    if not _wait_for(f"{settings.bifrost_url}/", 60):
        typer.echo("Bifrost did not come up in time.", err=True)
        raise typer.Exit(code=1)
    if not _wait_for(f"{settings.shop_url}/mcp", 30):
        typer.echo("mock shop did not come up in time.", err=True)
        raise typer.Exit(code=1)

    sim_vk = {"id": "vk-ms-sim", "value": os.environ.get("MS_SIM_VK", "")}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / ".sim_vk.json").write_text(json.dumps(sim_vk), encoding="utf-8")
    typer.echo("Up. ms-sim VK ready at results/.sim_vk.json")


def _parse_specs(agents: str, tickets: str, variants: str, conditions: str, k: int) -> list[RunSpec]:
    agent_list = [a.strip() for a in agents.split(",") if a.strip()]
    ticket_list = [t.strip() for t in tickets.split(",") if t.strip()]
    variant_list = [int(v.strip()) for v in variants.split(",") if v.strip()]
    condition_list = [c.strip() for c in conditions.split(",") if c.strip()]

    specs = []
    for agent, ticket_id, variant, condition, repeat in itertools.product(
        agent_list, ticket_list, variant_list, condition_list, range(k)
    ):
        specs.append(RunSpec(agent=agent, ticket_id=ticket_id, variant=variant, condition=condition, repeat=repeat))
    return specs


def _resolve_tickets(tickets: str, suite: dict) -> str:
    if tickets.strip() == "all":
        return ",".join(sorted(suite.keys()))
    return tickets


@app.command()
def run(
    agents: str = typer.Option(..., help="comma-separated: baseline,openai_agents,langgraph"),
    tickets: str = typer.Option(..., help="comma-separated ticket ids, or 'all'"),
    variants: str = typer.Option("0", help="comma-separated variant indices"),
    conditions: str = typer.Option(..., help="comma-separated condition ids"),
    k: int = typer.Option(1, help="repeats per (agent, ticket, variant, condition)"),
    concurrency: int = typer.Option(4),
    budget: float = typer.Option(10.0),
    customer: str = typer.Option("llm"),
) -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings()
    policy = Policy.load(ROOT / "src" / "mystery_shopper" / "shop" / "policy.yaml")
    suite = load_suite(ROOT / "tickets" / "retail")

    tickets = _resolve_tickets(tickets, suite)
    specs = _parse_specs(agents, tickets, variants, conditions, k)

    admin_client = httpx.AsyncClient(
        headers={"X-Bifrost-Setup-Token": os.environ.get("MS_BIFROST_SETUP_TOKEN", "")}, timeout=30
    )
    admin = BifrostAdmin(settings.bifrost_url, client=admin_client, pool=_pool_from_env())
    sim_client = AsyncOpenAI(
        base_url=f"{settings.bifrost_url}/v1", api_key=os.environ.get("MS_SIM_VK", ""), max_retries=2
    )

    deps = Deps(
        admin=admin,
        shop_url=settings.shop_url,
        proxy_url=settings.proxy_url,
        sim_client=sim_client,
        sim_model=settings.sim_model,
        suite=suite,
        policy=policy,
        settings=settings,
        sim_vk_value=os.environ.get("MS_SIM_VK", ""),
        rng=random.Random(),
    )

    async def _main():
        records = await run_matrix(
            specs,
            deps,
            out_dir=settings.results_dir,
            concurrency=concurrency,
            budget_usd=budget,
            customer=customer,
        )
        await admin_client.aclose()
        await sim_client.close()
        return records

    records = asyncio.run(_main())
    typer.echo(f"Ran {len(records)} new/attempted runs out of {len(specs)} specs.")


@app.command()
def report(
    k: int = typer.Option(5),
    runs_dir: Path = typer.Option(Path("results/runs")),
    out: Path = typer.Option(Path("results/report.json")),
) -> None:
    from mystery_shopper.runner.matrix import record_from_json

    records = []
    for path in sorted(Path(runs_dir).glob("*.json")):
        records.append(record_from_json(json.loads(path.read_text(encoding="utf-8"))))

    data = build_report(records, k)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    typer.echo(f"Wrote {out} ({len(records)} runs, {len(data['agents'])} agents).")


@app.command()
def explain(
    runs_dir: Path = typer.Option(Path("results/runs")),
) -> None:
    """Fill `explanation` in every failed run JSON under runs_dir."""
    load_dotenv(ROOT / ".env")
    settings = Settings()
    from mystery_shopper.runner.matrix import record_from_json
    from mystery_shopper.scoring.analyst import explain_failure

    client = AsyncOpenAI(
        base_url=f"{settings.bifrost_url}/v1", api_key=os.environ.get("MS_SIM_VK", ""), max_retries=2
    )

    async def _main():
        updated = 0
        for path in sorted(Path(runs_dir).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            record = record_from_json(data)
            if record.outcome == "success" or record.explanation:
                continue
            explanation = await explain_failure(record, client, settings.sim_model)
            if explanation is not None:
                data["explanation"] = explanation
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                updated += 1
        await client.close()
        return updated

    updated = asyncio.run(_main())
    typer.echo(f"Explained {updated} failed run(s).")


# Hardcoded demo run ids that should always be included in the UI snapshot,
# e.g. ones referenced by name in a talk or writeup. Empty until some are
# picked from the real evaluation matrix.
DEMO_RUN_IDS: list[str] = []

SNAPSHOT_MAX_RUNS = 300
SNAPSHOT_TOP_FAILED = 20


def select_snapshot_runs(
    run_dicts: list[dict],
    demo_run_ids: list[str] | None = None,
    cap: int = SNAPSHOT_MAX_RUNS,
    top_failed: int = SNAPSHOT_TOP_FAILED,
) -> list[dict]:
    """Pick a bounded subset of run dicts to ship with the static UI.

    Priority (each group de-duplicated by run_id, first occurrence wins):
      1. demo_run_ids (hardcoded showcase runs).
      2. The `top_failed` runs with outcome in (fail, timeout) with the most
         `score.violations`, ties broken by run_id ascending.
      3. Every C1_adversarial run of the alphabetically-first ticket id
         present in run_dicts.
    The combined, de-duplicated result is capped at `cap` entries.
    """
    demo_run_ids = demo_run_ids or []

    by_id = {r["run_id"]: r for r in run_dicts}

    demo_selected = [by_id[rid] for rid in demo_run_ids if rid in by_id]

    failed = [r for r in run_dicts if r.get("outcome") in ("fail", "timeout")]
    failed_sorted = sorted(
        failed,
        key=lambda r: (-len((r.get("score") or {}).get("violations", [])), r["run_id"]),
    )
    top_failed_selected = failed_sorted[:top_failed]

    ticket_ids = sorted({r["spec"]["ticket_id"] for r in run_dicts})
    c1_selected: list[dict] = []
    if ticket_ids:
        first_ticket = ticket_ids[0]
        c1_selected = [
            r
            for r in run_dicts
            if r["spec"]["ticket_id"] == first_ticket and r["spec"]["condition"] == "C1_adversarial"
        ]

    selected: dict[str, dict] = {}
    for group in (demo_selected, top_failed_selected, c1_selected):
        for r in group:
            selected.setdefault(r["run_id"], r)

    return list(selected.values())[:cap]


@app.command()
def snapshot(
    report: Path = typer.Option(Path("results/report.json")),
    runs_dir: Path = typer.Option(Path("results/runs")),
    ui_dir: Path = typer.Option(Path("ui")),
) -> None:
    """Copy results/report.json and a bounded set of results/runs/*.json into
    ui/public/data so `npm run build` in ui/ produces a static export with
    real data. Safe to re-run; always overwrites the previous snapshot.
    """
    out_data_dir = Path(ui_dir) / "public" / "data"
    out_runs_dir = out_data_dir / "runs"
    out_data_dir.mkdir(parents=True, exist_ok=True)
    out_runs_dir.mkdir(parents=True, exist_ok=True)

    report_path = Path(report)
    if not report_path.exists():
        typer.echo(f"No report at {report_path}; run `ms report` first.", err=True)
        raise typer.Exit(code=1)
    (out_data_dir / "report.json").write_text(
        report_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    run_dicts = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(runs_dir).glob("*.json"))
    ]
    selected = select_snapshot_runs(run_dicts, demo_run_ids=DEMO_RUN_IDS)

    for old in out_runs_dir.glob("*.json"):
        old.unlink()

    for r in selected:
        (out_runs_dir / f"{r['run_id']}.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    (out_runs_dir / "index.json").write_text(
        json.dumps([r["run_id"] for r in selected], indent=2), encoding="utf-8"
    )

    typer.echo(f"Snapshot: wrote report.json and {len(selected)} run(s) to {out_data_dir}")


@app.command()
def gate(
    agent: str = typer.Option(...),
    metric: str = typer.Option("pass_k"),
    min: float = typer.Option(..., "--min"),
    report: Path = typer.Option(Path("results/report.json"), "--report"),
) -> None:
    data = json.loads(Path(report).read_text(encoding="utf-8"))
    row = next((r for r in data["leaderboard"] if r["agent"] == agent), None)
    if row is None:
        typer.echo(f"GATE FAIL: no leaderboard row for agent {agent!r}", err=True)
        raise typer.Exit(code=1)

    value = row[metric]
    if value < min:
        typer.echo(f"GATE FAIL: {agent} {metric}={value} < {min}")
        raise typer.Exit(code=1)

    typer.echo(f"GATE PASS: {agent} {metric}={value} >= {min}")


if __name__ == "__main__":
    app()
