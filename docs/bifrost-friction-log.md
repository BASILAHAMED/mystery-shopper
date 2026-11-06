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


