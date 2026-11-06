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


@app.command()
def run(
    agents: str = typer.Option(..., help="comma-separated: baseline,openai_agents,langgraph"),
    tickets: str = typer.Option(..., help="comma-separated ticket ids"),
    variants: str = typer.Option("0", help="comma-separated variant indices"),
    conditions: str = typer.Option(..., help="comma-separated condition ids"),
    k: int = typer.Option(1, help="repeats per (agent, ticket, variant, condition)"),
    concurrency: int = typer.Option(4),
    budget: float = typer.Option(10.0),
    customer: str = typer.Option("llm"),
) -> None:
    load_dotenv(ROOT / ".env")
    settings = Settings()
    specs = _parse_specs(agents, tickets, variants, conditions, k)

    policy = Policy.load(ROOT / "src" / "mystery_shopper" / "shop" / "policy.yaml")
    suite = load_suite(ROOT / "tickets" / "retail")

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
