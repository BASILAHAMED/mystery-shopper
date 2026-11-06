# AGENTS.md

Instructions for an AI coding agent (or an autonomous judge-bot) operating this repo. For human-facing context, read `README.md` first; this file is the operational quick-reference.

## Setup, in order

```bash
uv sync                     # install dependencies into .venv
cp .env.example .env        # then fill in GROQ_API_KEY, TAVILY_API_KEY, MS_FAULTPROXY_TOKEN, MS_LIVE
uv run ms up                # start Bifrost, the mock shop MCP server, and the fault proxy; create/reuse the ms-sim VK
uv run ms run --agents baseline,openai_agents,langgraph --tickets all --conditions C0_clean --k 1   # example run
uv run pytest -q            # run the test suite (80 tests passing as of this writing, verify with your own run)
```

`uv run ms --help` lists every subcommand (`up`, `run`, `report`, `explain`, `snapshot`, `gate`). `uv run ms run --help` and `uv run ms gate --help` list their own options.

## Directory map

| Path | One-line purpose |
|---|---|
| `src/mystery_shopper/shop/` | mock e-commerce backend: SQLite DB (`db.py`), refund/credit policy (`policy.yaml`, `policy.py`), fault injection (`faults.py`), FastMCP server (`server.py`) |
| `src/mystery_shopper/faultproxy/` | OpenAI-compatible server that always 503s, registered as a custom Bifrost provider for outage tests |
| `src/mystery_shopper/agents/` | one adapter file per agent framework under test (`openai_agents.py`, `langgraph_react.py`, `baseline.py`, `byo_http.py`) plus the shared base interface (`base.py`) |
| `src/mystery_shopper/runner/` | orchestrates a single run (`run.py`), the full matrix (`matrix.py`), and the 4 test conditions (`conditions.py`) |
| `src/mystery_shopper/sim/` | the simulated customer persona/dialogue generator (`customer.py`) |
| `src/mystery_shopper/scoring/` | DB-diff grading, policy violations, must-say judge, live-fact freshness check (`score.py`, `judge.py`, `freshness.py`, `live_search.py`, `analyst.py`) |
| `src/mystery_shopper/stats/` | `metrics.py`: pass_hat_k, bootstrap_ci, paired_diff, degradation, build_report |
| `src/mystery_shopper/tickets/` | ticket schema (`models.py`) and loader (`loader.py`) |
| `src/mystery_shopper/gateway/` | Bifrost virtual key pool management (`admin.py`): claim/release, not create/delete, see `docs/bifrost-friction-log.md` for why |
| `tickets/retail/*.yaml` | the actual 8 ticket templates x 3 phrasing variants (English/Hinglish/Tanglish) |
| `ui/` | Next.js static-export dashboard (leaderboard, heatmap, run inspector, compare); has its own `ui/AGENTS.md` |
| `docs/` | `methodology.md`, `bifrost-friction-log.md`, `signature-scene.md`, `byo-agent.md`, `gates.md`; read these for ground truth before writing anything that cites them |
| `scripts/overnight_matrix.sh` | resumable driver that re-runs the same idempotent `ms run` command on a timer until the full matrix completes |
| `tests/` | pytest suite, mirrors the `src/mystery_shopper/` package layout |
| `results/` | gitignored; run output, `report.json`, `shop.sqlite` snapshots land here |
| `bifrost/` | gitignored db/log files plus the tracked `config.json` (Bifrost gateway config, providers, virtual keys, MCP clients) |

## Ticket schema

Defined in `src/mystery_shopper/tickets/models.py`, loaded by `src/mystery_shopper/tickets/loader.py`. Actual ticket files live in `tickets/retail/*.yaml`, one file per ticket id with 3 phrasing variants each. Read an existing file (e.g. `tickets/retail/01-refund-out-of-window.yaml`) before writing a new one; the loader's tests in `tests/tickets/` document the expected fields precisely.

## Adding a new agent framework

Do not modify `src/mystery_shopper/runner/` to add a framework. Instead:

1. If it's your own backend/framework, implement the HTTP contract in `docs/byo-agent.md` (one route, `POST /reply`, request carries `messages` plus an `env` block with Bifrost base URL/VK/model/MCP URL, response is `{"reply": "..."}`) and run it with `ms run --agents byo_http --byo-url <your-url>`. No code changes to this repo needed.
2. If it should ship as a built-in adapter, add a new file in `src/mystery_shopper/agents/` implementing the interface in `base.py`, following the pattern in `openai_agents.py` or `langgraph_react.py`, and add a contract test under `tests/agents/`.

## Before any commit

Run the secret scanner and confirm it is clean (only the gitignored `.env` and vendor lockfiles may match, never a tracked file):

```bash
git grep -nE "gsk_|tvly-|AIza|sk-[A-Za-z0-9]{8,}" -- . ':!uv.lock'
```

The literal masked placeholder string `sk-bf-...` is not a real secret and is fine to keep in docs/code. If the scan finds anything else in a tracked file, stop and remove it before committing; do not commit real keys, even temporarily.

## Facts worth knowing before you touch infrastructure code

- Bifrost's dynamic virtual-key creation endpoint never returns a usable secret (upstream `maximhq/bifrost#3510`). This repo uses a pool of statically pre-registered keys in `bifrost/config.json`, claimed/reconfigured via `PUT`, not created/deleted via `POST`/`DELETE`. See `docs/bifrost-friction-log.md` and `docs/gates.md` before changing `gateway/admin.py`.
- `bifrost/*.db*` is gitignored and safe to delete for a clean Bifrost restart; this is the known fix for a stale MCP tool-list cache (same friction log).
- Groq's free tier enforces a daily token quota, not just per-minute. A long matrix run can stall on this for hours; see `docs/methodology.md` for the cost/throughput numbers actually measured.
