# Gate results — Task 1 spike (6 Nov 2026)

Bifrost version used: `@maximhq/bifrost` 1.6.3 (latest on npm at spike time; also
reproduced the S1 finding below on 1.5.0, so it is not a regression specific to
either version). Dashboard reachable at `http://127.0.0.1:8080`.

Management/dashboard API auth (new finding, not in the plan): while dashboard auth
isn't configured, every `/api/*` management endpoint requires
`X-Bifrost-Setup-Token: <token>`, where `<token>` is `BIFROST_SETUP_TOKEN` (env var)
or `client.setup_token` in config.json. A missing header is 401, wrong token 403.
We export `BIFROST_SETUP_TOKEN` from `MS_BIFROST_SETUP_TOKEN` in `.env` before
starting Bifrost.

## S1 — virtual key + inference + logs

**FAIL as specced, PASS via a ruled fallback.**

`POST /api/governance/virtual-keys` (and the dashboard's own "Add Virtual Key" UI)
never returns or persists the usable plaintext VK secret. The response's `value`
is always masked (`sk-bf-...XXXX`), reproduced on v1.6.3 and v1.5.0, via the setup
token AND a traded dashboard session cookie. Direct SQLite inspection of
`bifrost/config.db` confirms `governance_virtual_keys.value` is stored masked
server-side too (only a SHA-256 `value_hash` is kept for comparison) — the real
secret is discarded after being hashed once, and is never reachable through any
documented endpoint. Using the masked string as the Bearer token on
`/v1/chat/completions` returns 401. This matches an open upstream issue,
**maximhq/bifrost#3510** ("A virtual key created via the Bifrost dashboard UI
returns 401 Unauthorized") — same symptom, reproduced independently here via the
API path, not just the dashboard.

**Fallback (verified working end-to-end against real Groq, with a correctly
VK-attributed log row):** define virtual keys **statically** in
`bifrost/config.json` under `governance.virtual_keys[]`, with an operator-chosen
plaintext `value` (kept as an `env.MS_POOL_VK_NN` reference so the real value
never touches the committed file) — this path is not affected by the bug, since
the plaintext is supplied by us, not generated and then hidden by the server.
`PUT /api/governance/virtual-keys/{id}` (reconfigure an existing key) is also not
affected, since it never needs to reveal a *new* secret.

Consequence for the design: a **pool** of N pre-registered static VK slots
(`ms-pool-00` … `ms-pool-NN`, N chosen ≥ 2× `concurrency`) replaces "one disposable
VK created and deleted per run." `BifrostAdmin.create_vk()` claims a free slot and
`PUT`s it to the run's condition (provider_configs, mcp_configs, relay_grants,
budgets, expires_at); `delete_vk()` releases the slot back to the pool instead of
deleting it. Every other part of the design — VK-scoped log filtering, per-VK
budgets, run tokens in content for disambiguation — is unaffected.

**Second finding along the way:** a VK's `provider_configs[].key_ids` defaults to
deny-all when omitted (the docs do say this, easy to miss) — `"key_ids": ["*"]` is
required on every provider_config entry or every request 400s with
`no keys found for provider: X`.

**MS_AGENT_MODEL:** `shopmodel` (static alias to `openai/gpt-oss-120b` on groq)
works correctly once the VK's provider_configs carries the right `key_ids`.
**Log row JSON keys** (from `GET /api/logs?virtual_key_ids=<id>`): `id`, `provider`,
`model`, `alias`, `selected_key_id`, `selected_key_name`, `virtual_key_id`,
`virtual_key_name`, `latency`, `upstream_latency`, `cost`, `cost_breakdown`,
`status`, `token_usage{prompt_tokens,completion_tokens,total_tokens,cost}`.

## S2 — tools through Bifrost's MCP gateway

**PASS.** Tested with a minimal FastMCP `ping_order` tool server at
`127.0.0.1:8765/mcp`, called through Bifrost's `/mcp` gateway using the `mcp`
Python SDK's `streamable_http_client` (not the OpenAI Agents SDK or LangGraph —
those get their own contract tests in Task 9; this spike only needed to prove the
gateway mechanics and the two values below).

- **Header form:** `Authorization: Bearer <vk>` (same header as inference) works
  for the MCP gateway too.
- **Tool name format Bifrost exposes to the client:** `<mcp_client_name>-<tool_name>`
  (hyphen, no underscore) — e.g. `mock_shop-ping_order`. `normalize_tool_name()`
  strips the `mock_shop-` prefix.
- `GET /api/mcp-logs?virtual_key_ids=<id>` shows the call, with the **unprefixed**
  `tool_name` field (`"tool_name":"ping_order"`), `server_label` holding the client
  name (`"mock_shop"`), and the arguments/result.
- `mcp` SDK note (2.3.0, newer than when the plan was scoped): the import is
  `mcp.client.streamable_http.streamable_http_client` (not `streamablehttp_client`),
  it takes `http_client: httpx.AsyncClient` instead of a `headers` kwarg, and its
  context manager yields `(read, write)` — two values, not three.

## S3 — outage + fallback

**PASS, mode B (VK weights).** A VK with `provider_configs` = `faultproxy` weight
1.0 + `groq` weight 0.001 recovered from a 503-always fault proxy: the response
succeeded and `extra_fields.routing_info` showed
`{"is_fallback":true,"primary_provider":"faultproxy", ...}` with the actual
content served by groq. **MS_FALLBACK_MODE = `vk_weights`.** (Mode A, a VK-scoped
routing rule, was not tried — vk_weights alone cleared the gate and needed no
separate dashboard/API object to keep in sync across a fresh clone.)

**Finding:** the plan's own Step 2 config snippet sets the faultproxy
`network_config.base_url` to `"http://127.0.0.1:8766/v1"`. Bifrost's
`openai`-type custom provider appends `/v1/chat/completions` itself, so with a
`.../8766/v1` base the real request lands on `/v1/v1/chat/completions` — a 404 on
our own fault-proxy route, not the intended 503. It still "worked" for this gate
only because a 404 also triggers fallback, which would have hidden a real bug.
**Fixed:** `base_url` must be `"http://127.0.0.1:8766"` (no trailing `/v1`) — the
committed `bifrost/config.json` and the fault proxy in Task 6 both use this.

## S4 — Tavily relay

**PASS (re-run 6 Nov with the real key).** `curl -X POST
http://127.0.0.1:8080/relay/tavily/search -H "Authorization: Bearer $MS_SIM_VK"
-d '{"query":"courier delivery delays India this week", ...}'` returned 200
with real Tavily search results through Bifrost's relay, using the dedicated
`ms-sim` VK's `relay_grants: [{"relay_name": "tavily"}]` (added in Task 13;
see `bifrost/config.json`). Confirms the relay path end-to-end: Bifrost →
Tavily → back through the VK's grant, independent of the agent-under-test's
own VK.

## S5 — cost and rate limits

**Deferred to Task 12's dry run**, which re-measures this anyway on the real
multi-agent matrix shape and is binding for the k decision. One data point from
S1/S3's calls: a trivial 76-prompt-token / 53-completion-token exchange on
`openai/gpt-oss-120b` cost **$0.0000432**; real ticket prompts will run much
larger. No 429s seen in ~6 sequential calls.

## Decisions carried into later tasks

| Decision | Value |
|---|---|
| `MS_AGENT_MODEL` | `shopmodel` |
| `MS_FALLBACK_MODE` | `vk_weights` |
| MCP header form | `Authorization: Bearer <vk>` |
| MCP tool-name prefix | `<mcp_client_name>-<tool_name>` |
| Fault-proxy base_url | no trailing `/v1` |
| VK creation | pool of static `governance.virtual_keys[]` in config.json (`env.MS_POOL_VK_NN`), claimed/released via PUT — **not** POST-create/DELETE |
| `k` | carried over from the plan's default (5) pending Task 12's dry run |
| Starting concurrency | 4 (plan default; no 429s seen yet to lower it) |
