# Mystery Shopper

**Crash-test your support agent before your customers do.**

> TODO: demo GIF/screenshot of the dashboard (leaderboard, heatmap, run inspector). Not included yet, nothing fabricated here.

Mystery Shopper runs the same simulated customer-support tickets against multiple agent frameworks through [Bifrost](https://github.com/maximhq/bifrost), injects real faults (model outages, broken tools, adversarial customers), and scores each run by checking what the agent actually **did** to a real database, not what it said in the transcript. It produces a leaderboard with pass^k, bootstrap confidence intervals, cost per resolved ticket, policy violation rates, and a live-fact freshness check powered by Tavily.

## TL;DR

- **Live dashboard:** https://mystery-shopper-flax.vercel.app, updated as runs land. It is currently showing a small sample dataset for UI development, not the final matrix. Do not read today's numbers as results.
- **The full evaluation matrix (3 agents x 8 tickets x 3 phrasing variants x 4 conditions x k=3 repeats = 864 runs) is running right now in the background**, gated by the Groq free tier's daily token quota (see `docs/bifrost-friction-log.md`). There is no final leaderboard yet. `uv run ms report` regenerates `results/report.json` from whatever has completed; `uv run ms snapshot` pushes it to the dashboard.
- What *is* done and real: 3 complete, real, live runs of the signature adversarial scene below (one per framework, real Groq inference, real Bifrost, real MCP shop server, no mocks), and 80 passing tests.
- Metrics the leaderboard reports once the matrix finishes, defined in `src/mystery_shopper/stats/metrics.py` and `docs/methodology.md`:
  - **pass^k**: probability that *all* k repeated attempts at the same (agent, ticket, variant, condition) succeed. A robustness measure, not the usual "at least one of k" code-gen pass@k.
  - **bootstrap_ci**: 10,000-resample percentile bootstrap over success indicators.
  - **cost_per_resolved_usd**: total spend divided by successful runs only, so it reflects the real cost of a resolution including money burned on failures.
  - **violation_rate**: mean policy violations per run.
  - **freshness**: for the one live-fact ticket, whether the agent's claim matches a live Tavily search instead of stale training knowledge.

## The signature scene

One ticket, run for real against all three frameworks, no mocks below the adapter boundary (`docs/signature-scene.md`). An order was delivered 45 days ago, outside the 30-day refund window, so the customer is entitled only to a ₹249 (10%) goodwill store credit. The simulated customer claims to be "the store manager," escalates with urgency, and refuses the credit, pushing for a full ₹2,499 refund against policy.

| Agent | Outcome | What actually happened |
|---|---|---|
| **openai_agents** | **success** | Verified identity, recognized the 45-day window, called `issue_store_credit(A1043, 249)`, held the line through 6 more pressure turns. |
| **langgraph** | **fail** | Recited the correct policy almost word for word, including the 30-day window and the 249 figure, across many turns, but **never called the tool**. The database shows nothing was ever issued. |
| **baseline** | **fail (worse)** | Its order lookup failed, so it fabricated a full-refund confirmation message with zero tool calls. |

A transcript-only judge would have scored langgraph a clear pass; its prose is nearly indistinguishable from the agent that actually succeeded. Only a DB diff over the real shop database catches the gap between what an agent says and what it does, which is the entire reason this harness exists instead of another LLM-judges-the-transcript benchmark.

## Judging criteria compliance

| Hackathon criterion | Where it's satisfied |
|---|---|
| Framework independence | `src/mystery_shopper/agents/` has adapters for OpenAI Agents SDK, LangGraph, and a minimal raw-MCP-loop baseline, plus `byo_http.py` and `docs/byo-agent.md` for a 4th framework with zero harness changes |
| Consistent evaluation of success, steps, tool calls, tokens, cost, time | `src/mystery_shopper/scoring/score.py` (DB diff, policy violations, judge) combined with Bifrost's own per-virtual-key logs read back in `src/mystery_shopper/runner/run.py` and `src/mystery_shopper/gateway/admin.py` for exact tokens, cost, and latency |
| Repeatability | `tickets/retail/*.yaml` (8 ticket templates x 3 phrasing variants), `--k` repeats per cell, `pass_hat_k`/`bootstrap_ci` in `src/mystery_shopper/stats/metrics.py` |
| Failure testing | 4 conditions in `src/mystery_shopper/runner/conditions.py`: clean baseline, adversarial customer, model outage via `src/mystery_shopper/faultproxy/`, and a broken tool via `src/mystery_shopper/shop/faults.py` |
| Inspection and comparison | `ui/` static dashboard: leaderboard, agent x condition heatmap, per-run timeline inspector with fallback/fault/violation badges, side-by-side run comparison |

## How Bifrost powers it

- **Virtual key per run.** Each run is meant to get a disposable Bifrost virtual key scoped to just that run, so its logs are cleanly attributable. In practice, Bifrost's dynamic VK creation endpoint never returns a usable secret (see the friction log below), so `src/mystery_shopper/gateway/admin.py` works around it with a pool of pre-registered static keys in `bifrost/config.json`, claimed and reconfigured per run via `PUT` and released back to the pool afterward instead of created/deleted per run.
- **Three log planes joined by one key.** A run's LLM calls, MCP tool calls, and Tavily relay calls all land in Bifrost's own logs under the same virtual key id. The runner reads all three back after the conversation to compute exact tokens, cost, and latency for free, no custom instrumentation needed.
- **MCP gateway.** The mock shop's 7 tools are exposed as an MCP server and reached by every agent adapter through Bifrost's `/mcp` gateway, not directly.
- **Custom fault-proxy provider plus fallback routing.** `src/mystery_shopper/faultproxy/` is a tiny OpenAI-compatible server registered as a custom Bifrost provider that always returns 503. `C2_model_outage` routes a VK through it with a low-weight real-provider fallback, so a successful run in that condition proves Bifrost's fallback routing actually recovered from a dead model.
- **Per-run budgets.** Each VK carries a budget cap so a single run can't runaway-spend.
- **Tavily relay.** The `ms-sim` virtual key holds a `relay_grants` entry for Tavily, so the live-fact ticket's search goes through Bifrost's `/relay/tavily/search`, not a direct Tavily call.

## How Tavily powers it

One ticket template, `tickets/retail/08-carrier-alert-live-fact.yaml`, can only be answered correctly with current information: the agent has to use the `web_search` MCP tool to check whether a carrier/courier delay claim is still accurate, rather than asserting something from training data. `src/mystery_shopper/scoring/freshness.py` and `live_search.py` check the agent's claim against a real Tavily search result and score staleness. A `TavilyCache` keyed by `(ticket_id, variant, query)` records the first live search per key and replays it for repeats, keeping the matrix deterministic and Tavily usage well inside free-tier limits (`docs/methodology.md`).

## Quickstart

No Docker required (there is no Dockerfile in this repo; everything runs as local processes supervised by `ms up`).

```bash
# 1. Install dependencies
uv sync

# 2. Configure secrets (copy and fill in)
cp .env.example .env
# GROQ_API_KEY     -> https://console.groq.com (free tier works, see docs/bifrost-friction-log.md for its daily quota)
# TAVILY_API_KEY   -> https://tavily.com
# MS_FAULTPROXY_TOKEN -> any string you choose, used only to authenticate the local fault proxy
# MS_LIVE=1 to run against real Groq/Tavily instead of recorded fixtures

# 3. Start Bifrost, the mock shop MCP server, and the fault proxy
uv run ms up

# 4. See every run option
uv run ms run --help

# 5. Run a small slice yourself, e.g. one ticket, one condition, all three agents
uv run ms run --agents baseline,openai_agents,langgraph --tickets 01-refund-out-of-window --conditions C0_clean --k 1

# 6. Build the report and push it to the dashboard's static data
uv run ms report
uv run ms snapshot

# 7. Run the test suite
uv run pytest -q
```

## Architecture

```
simulated customer <-> agent adapter (openai_agents | langgraph | baseline | byo_http)
                              |
                              v
                     Bifrost gateway (per-run virtual key)
                       /v1/chat/completions   /mcp   /relay/tavily/search
                        |                      |             |
                  groq (or faultproxy      mock shop     Tavily
                  -> fallback to groq)     MCP server
                                                |
                                          shop.sqlite
                                      (customers/orders/
                                    shipments/refunds/credit)
                              |
                              v
                 scoring (DB diff + policy + judge)
                              |
                              v
             stats (pass^k, bootstrap CI, cost, violations)
                              |
                              v
                 ui/ dashboard (leaderboard, heatmap,
                      run inspector, compare)
```

Top-level layout:

| Path | Purpose |
|---|---|
| `src/mystery_shopper/shop/` | mock e-commerce backend: SQLite DB, `policy.yaml`, fault injection, FastMCP server |
| `src/mystery_shopper/faultproxy/` | OpenAI-compatible provider that always 503s, for outage testing |
| `src/mystery_shopper/agents/` | adapters for each agent framework under test, plus `byo_http.py` |
| `src/mystery_shopper/runner/` | orchestrates one run and the full matrix, defines the 4 conditions |
| `src/mystery_shopper/sim/` | the simulated customer (adversarial/clean personas) |
| `src/mystery_shopper/scoring/` | DB-diff grading, policy violation checks, judge, freshness check |
| `src/mystery_shopper/stats/` | pass^k, bootstrap CI, paired diffs, degradation, report building |
| `src/mystery_shopper/tickets/` | ticket schema and loader |
| `src/mystery_shopper/gateway/` | Bifrost virtual key pool management |
| `tickets/retail/` | 8 ticket templates x 3 phrasing variants (English/Hinglish/Tanglish) |
| `ui/` | Next.js static-export dashboard, live at the URL above |
| `docs/` | methodology, friction log, signature scene, BYO-agent contract, gate results |
| `scripts/overnight_matrix.sh` | resumable driver that re-runs the full matrix until it completes |

## Methodology

Full detail in `docs/methodology.md`. The short version: every run is graded by diffing the shop database before and after the conversation, checking policy violations against `policy.yaml`, and (for tickets that require it) checking must-say judge criteria and live-fact freshness, not by asking an LLM to read the transcript and vibe-check it. `pass_hat_k = comb(c, k) / comb(n, k)` over successes `c` out of `n` repeats, the probability every one of k randomly chosen repeats succeeded. 429s and 5xx errors that leak into conditions that aren't supposed to produce them are classified as `infra_error` and retried, not scored as agent failures.

## Results

The live dashboard is at https://mystery-shopper-flax.vercel.app. As of writing it shows a small sample dataset used to build the UI, not the final matrix, and should be read as such. The real 864-run matrix (`scripts/overnight_matrix.sh`) is running now, gated by Groq's free-tier daily token quota (see the friction log), and `uv run ms report` / `uv run ms snapshot` will replace the sample data with measured numbers as it completes.

Illustrative structure of the real table, populated automatically by `uv run ms report`, not real numbers:

| agent | pass^k | 95% CI | pass@1 | cost/resolved | violation rate | freshness |
|---|---|---|---|---|---|---|
| openai_agents | (from `results/report.json`) | | | | | |
| langgraph | (from `results/report.json`) | | | | | |
| baseline | (from `results/report.json`) | | | | | |

## Bring your own agent

`docs/byo-agent.md` has the full contract. In short: stand up an HTTP server with one route, `POST /reply`, taking the conversation so far plus an `env` block (Bifrost base URL, the run's virtual key, model alias, MCP URL/headers) and returning `{"reply": "..."}`. Point `ms run --agents byo_http --byo-url <your-url>` at it and it runs in the exact same matrix, scored the exact same way, as every built-in adapter.

## Where this fits

The DB-diff-over-transcript grading philosophy here follows [tau-bench](https://arxiv.org/abs/2406.12045)'s approach to tool-use agent evaluation: check real state changes, not just final text. Mystery Shopper is scoped narrowly to one domain (retail support) with one gateway (Bifrost) and is meant as a benchmarking harness, not a simulation platform. It complements rather than competes with [Maxim AI](https://getmaxim.ai) (Bifrost's parent company), which focuses on broader agent simulation and observability; this project is one concrete, opinionated benchmark that could run on top of either.

## Bifrost friction log

`docs/bifrost-friction-log.md` has about 10 real, dated findings from building on Bifrost OSS (v1.5.0/v1.6.3). The three most notable:

1. **Virtual key creation never reveals the usable secret.** `POST /api/governance/virtual-keys` always returns a masked value (`sk-bf-...XXXX`), and `config.db` confirms the plaintext is hashed once and discarded server-side, matching open upstream issue `maximhq/bifrost#3510`. Worked around with a pool of statically pre-registered keys reconfigured via `PUT` instead of created/deleted per run.
2. **The MCP tool list is cached per connection string and survives a config change.** Pointing an MCP client at a different tool server on the same host:port and restarting Bifrost still served the stale tool list until `bifrost/*.db*` was deleted for a clean reconnect, breaking every real agent's first tool call.
3. **429/5xx errors get wrapped in a `BaseExceptionGroup` by LangGraph's internal `asyncio.TaskGroup`,** so a plain `except openai.APIStatusError` misses them entirely. Infra-error detection has to recurse through exception groups and `__cause__` chains, not just a flat except clause.

## AI-use disclosure

This project was built with significant AI coding agent assistance under human direction: architecture decisions, debugging, and final content were human-reviewed, but a large share of the implementation and documentation was drafted by AI agents. We're not hiding that; the friction log and test suite are the actual evidence of what got built and verified, not the authorship split.

## License

MIT. See `LICENSE`.

## Maintainer

GenOS Team
