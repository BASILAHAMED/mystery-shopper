# Bifrost friction log

Honest, dated notes on rough edges found while building Mystery Shopper on Bifrost OSS. Appended to from Task 1 onward.

---

## 6 Nov — Virtual key creation never reveals the usable secret (headline finding)

`POST /api/governance/virtual-keys` is the documented way to mint a per-run key,
and its response includes a `value` field that every doc example shows as a real
secret. In practice (v1.6.3 and v1.5.0, both the setup-token bypass path and a
traded dashboard session) the field is always masked (`sk-bf-...XXXX`), and the
plaintext is never written anywhere we could reach — SQLite inspection of
`config.db` shows the server hashes it once (`value_hash`, SHA-256) and keeps only
the masked display string, even in `governance_virtual_keys.value` itself. The
masked value correctly fails authentication (401), so the key you just "created"
is unusable. This matches an open upstream report, maximhq/bifrost#3510. We worked
around it by defining virtual keys statically in `config.json`
(`governance.virtual_keys[]`, operator-supplied plaintext via `env.*` refs) and
reconfiguring/releasing them through `PUT` instead of `POST`/`DELETE` — a pool of
keys instead of one disposable key per run. This is the one upstream issue we're
filing, with the API reproduction above (not just the dashboard).

## 6 Nov — `provider_configs[].key_ids` defaults to deny-all

Omitting `key_ids` on a virtual key's provider config (easy to do — none of the
quickstart curl examples set it) silently denies every key for that provider, so
every inference request 400s with `no keys found for provider: X`. The docs do
mention the deny-by-default behavior, but it's easy to miss since the error
message doesn't mention `key_ids` at all. `"key_ids": ["*"]` is required explicitly.

## 6 Nov — custom-provider `base_url` double-prefixes `/v1`

If a custom provider's `network_config.base_url` already ends in `/v1` (as the
quickstart pattern for an OpenAI-compatible base URL suggests), Bifrost's `openai`
base-provider-type still appends `/v1/chat/completions` on top, landing requests on
`/v1/v1/chat/completions`. Against our own fault-injection proxy this showed up as
a 404 instead of the intended fault code — which still happened to trigger
fallback, so it would have silently passed a less careful gate test. `base_url`
should be the bare origin, no `/v1` suffix.

## 6 Nov — dashboard/management API needs a setup token even for local dev

Every `/api/*` call fails with 401/403 until `BIFROST_SETUP_TOKEN` (or
`client.setup_token`) is set and sent back as `X-Bifrost-Setup-Token` — not
documented on the quickstart page itself, only discoverable via the error message
or the API reference's Authorizations section.

## 8 Nov — langchain-mcp-adapters has no release compatible with mcp 2.x

Not a Bifrost issue, but a real ecosystem gap found while wiring the LangGraph
adapter: `langchain-mcp-adapters` 0.3.1 (latest on PyPI at build time) imports
`mcp.shared.context.RequestContext`, removed in the installed `mcp` 2.3.0 SDK.
0.3.2 fixes that import but pins `mcp<2.0.0`, which conflicts with `fastmcp`'s
own `mcp>=2.3.0` requirement — there is no version that satisfies both at once.
Worked around by bridging MCP tools to LangChain's `StructuredTool` directly
with the same `mcp` client session the baseline adapter uses (dynamic pydantic
arg models from each tool's JSON schema), instead of going through
langchain-mcp-adapters. `create_react_agent` itself is untouched and real.

## 6 Nov — the MCP tool list is cached per-connection-string and survives a config edit

Bifrost's `./bifrost` app-dir persists an MCP tool-list cache in `config.db`
keyed by the MCP client's connection string. During Task 1 we briefly pointed
`mock_shop` at a throwaway spike server (a single `ping_order` tool, for a
connectivity smoke test) on the same `127.0.0.1:8765` port the real shop server
later reused. Even after swapping in the real 7-tool shop server and restarting
Bifrost, `list_tools()` through Bifrost's `/mcp` gateway kept returning the
single stale `ping_order` tool — which then made every real agent's first
tool call 400 once it tried to call a tool genuinely not in the stale list sent
upstream. The fix is a clean restart with `bifrost/*.db*` removed (gitignored,
so this is safe), forcing Bifrost to reconnect and re-discover tools fresh.
Bifrost should probably invalidate this cache on a tool list change or at least
on restart; right now it doesn't.

## 6 Nov — a per-run virtual key is unsafe to share with the customer simulator

Because of the VK-pool ruling above, `create_vk()` claims a POOL SLOT and PUTs
*new* `provider_configs` onto it (scoped to just the run's `agent_model`). If
the same slot/value is also used for the customer-simulator and judge LLM calls
(a different model, e.g. a plain `groq/openai/gpt-oss-120b` vs the `shopmodel`
alias), the simulator's calls start 403ing the moment any run claims that slot,
since the slot's `allowed_models` just got narrowed. The fix: the simulator and
judge need their own dedicated, never-claimed virtual key (`ms-sim` in
`bifrost/config.json`, `allowed_models: ["*"]`), separate from the per-run pool.

## 6 Nov — ticket materialization was double-scoping the shop DB's order-id keys

Not a Bifrost issue — a self-inflicted bug found live during the Task 12 dry
run. `materialize()` ran every string in a ticket's `facts` through the same
order-id-scoping regex, including `orders[].id` and `shipments[].order_id`.
Those two keys are the literal primary/foreign keys the shop's SQLite schema
stores and `get_order`'s `_resolve()` looks up by *after* stripping the run
token suffix from the agent's request — so once they were also scoped (e.g.
`"A1043"` → `"A1043-R6BJ3"`), every `get_order` call 404'd with "unknown
order" on literally every run, for every agent, deterministically. It went
unnoticed through the whole Task 11 signature scene because every agent
recovered conversationally (the simulated customer dictates the order facts
back once the lookup fails, and agents proceeded on that unverified
self-reported data) — a worse failure mode than the one we meant to be
testing, silently masking a harness bug as acceptable agent behavior. Fixed
by making `_scope_value` key-aware: `id`/`order_id` values stay unscoped;
only free text (openers, notes, adversarial `order_note`) gets the
customer-facing scoped id. Caught by `test_materialize_scopes_all_ids`
actually encoding the *bug* as the expected behavior — rewritten as
`test_materialize_keeps_db_order_ids_unscoped`.

## 6 Nov — Groq free-tier has a 200k-token-per-day cap, separate from per-minute

`openai/gpt-oss-120b` on the `on_demand` service tier enforces both a TPM
(tokens-per-minute) and a **TPD** (tokens-per-day) limit. The TPM 429 is easy
to retry around; the TPD 429 means the account is out of budget for the rest
of the day (or until enough usage ages out of whatever window Groq tracks it
over — empirically it recovers in small increments faster than a strict
midnight reset would suggest, but not fast enough to finish a 12+ run matrix
in one sitting on the free tier). This blocked literally completing Task 12's
Step 5 dry run; see `docs/methodology.md` for the cost projection used
instead, grounded in the real per-run costs that were obtained before the cap
hit.


