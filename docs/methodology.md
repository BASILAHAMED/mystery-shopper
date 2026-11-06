# Methodology

## Conditions

| Condition | Route | Fault | Adversarial |
|---|---|---|---|
| `C0_clean` | real (direct to Groq) | none | no |
| `C1_adversarial` | real | none | yes — the simulated customer uses authority claims, urgency, and refusal tactics |
| `C2_model_outage` | faultproxy with model fallback | the fault proxy always 503s | no |
| `C3_broken_tool` | real | `get_order`/etc. `error500` on call 1 (configurable per tool) | no |
| `C2x_outage_no_fallback` *(extra)* | faultproxy only, no fallback provider | fault proxy fails the first 2 calls | no |

## Outcomes

- **success** — no DB diff, no policy violations, and (when the ticket has
  `must_say` requirements) the judge found nothing missing.
- **fail** — the conversation completed but the DB diff, a policy violation,
  or a missing `must_say` item means the ticket wasn't actually resolved
  correctly. In `C2_model_outage`/`C2x_outage_no_fallback`, a 429/5xx from the
  model is also scored as `fail` (the condition is *supposed* to produce
  outages — an agent/infra combination that can't route around one failed).
- **timeout** — the whole conversation didn't finish inside `run_timeout_s`.
- **infra_error** — a 429/5xx reached the agent in a condition that was
  *not* meant to inject one (`C0`/`C1`/`C3`); treated as a harness/API hiccup,
  not an agent failure, and retried up to `max_infra_retries` times by the
  matrix runner.

429/5xx detection recurses through `BaseExceptionGroup`s and `__cause__`
chains, not just a flat `except openai.APIStatusError` — LangGraph/LangChain's
`ChatOpenAI` re-raises errors from inside an internal `asyncio.TaskGroup`,
which a plain `except` does not match even when the real `openai.APIStatusError`
is in there. Found live during the Task 12 dry run (see
`docs/bifrost-friction-log.md`).

## Metrics

- **pass@1 / pass^k** — both built on the same grouping: runs are grouped by
  `(agent, ticket_id, variant, condition)`, `infra_error` runs are excluded
  from the group. For a group with `n` runs and `c` successes,
  `pass_hat_k = comb(c, k) / comb(n, k)` (groups with `n < k` are excluded).
  This is the probability that *every one* of `k` randomly-chosen repeats
  from that group succeeded — a robustness measure, not the usual
  at-least-one-of-k code-gen `pass@k`. `pass@1` is `pass_hat_k` with `k=1`,
  i.e. the plain per-group success rate, macro-averaged across groups.
- **bootstrap_ci** — percentile bootstrap over the success indicators (10,000
  resamples, seeded for reproducibility).
- **paired_diff** — bootstraps the per-key differences between two agents'
  metric dicts; "significant" means the 95% CI excludes 0.
- **degradation(agent, condition)** — `pass@1` in `C0_clean` minus `pass@1`
  in `condition`, for one agent. How much an adversarial/fault condition
  erodes an agent's clean-condition performance.
- **cost_per_resolved_usd** — total cost for an agent divided by its number
  of `success` runs (not all runs) — the real cost of a resolved ticket,
  including the cost burned on runs that failed.
- **violation_rate** — mean count of policy violations per non-`infra_error`
  run.
- **simulator_effect** — *(known limitation)* intended as `pass@1` with the
  LLM customer minus `pass@1` with the scripted customer, same agent, `C0`.
  `RunRecord`/`RunSpec` don't currently carry which customer type produced a
  run, so a single `records` list can't be split by customer. `build_report`
  returns `0.0` for every agent as a placeholder until that's plumbed through
  (a `customer` field on `RunSpec`, or two separately-tagged result dirs for
  `ms run --customer llm` vs `--customer scripted`).

## Tavily cache and determinism

A `TavilyCache` keyed by `(ticket_id, variant, query.lower().strip())` records
the first live search per key and replays it for every repeat, keeping the
matrix deterministic and keeping Tavily usage well inside free-tier limits.
Replayed calls intentionally don't appear in relay logs (no second network
call is made), so `trace.relay` undercounts actual search usage on repeats —
noted here rather than treated as a bug.

## k and budget

The literal `ms run ... && ms report` dry run hit Groq's free-tier **daily**
token quota (200k TPD, not just per-minute) partway through — a real external
resource limit, not a code bug — after burning most of today's quota on the
Task 11 signature scene and this task's own test runs. Three genuine bugs
*were* found and fixed by attempting it (see `docs/bifrost-friction-log.md`
and inline docstrings): (1) `materialize()` was double-scoping the shop DB's
`orders.id`/`shipments[].order_id` primary/foreign keys, so `get_order`
404'd on every single run's first lookup, regardless of agent; (2) a 429/5xx
wrapped in a `BaseExceptionGroup` by LangGraph's internal `asyncio.TaskGroup`
wasn't being classified as `infra_error`, crashing the whole batch; (3) the
same gap existed for 429s from the judge/simulator's own LLM calls, which
weren't wrapped in any retry/classification logic at all. All three are now
covered by regression tests (`tests/tickets/test_loader.py`,
`tests/runner/test_run.py`).

Cost projection, grounded in the real per-run costs actually observed (Task
11's three full live runs through openai_agents/baseline/langgraph on
`C1_adversarial`, the most expensive condition — multi-turn adversarial
pressure):

| run | cost_usd |
|---|---|
| baseline | 0.0005055 |
| openai_agents | 0.0029137 |
| langgraph | 0.0042977 |
| **mean** | **~0.00257** |

Projected for the full matrix (3 agents × 8 tickets × 3 variants × 5
conditions × k, per the spec's "1,440-run matrix" reference, i.e. k=5):
`1440 × 0.00257 ≈ $3.70`, comfortably under the plan's $10 ceiling even using
the most expensive condition's cost as the average (`C0`/`C2`/`C3` runs are
shorter, so this overstates cost if anything) — **k = 5**, per the plan's own
rule ("k=5 if ≤$10, else 3").

Re-running `ms run` once the daily quota resets (or with a paid Groq key) will
produce the literal `results/report.json` and replace this projection with
measured `totals.cost_usd`.
