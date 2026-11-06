# Bring your own agent

Mystery Shopper can test any agent framework (or your own backend) through the
`byo_http` adapter. Stand up an HTTP server that implements one route:

## `POST /reply`

**Request body:**
```json
{
  "messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "env": {
    "base_url": "http://127.0.0.1:8080/v1",
    "api_key": "<the run's virtual key>",
    "model": "shopmodel",
    "mcp_url": "http://127.0.0.1:8080/mcp",
    "mcp_headers": {"Authorization": "Bearer <the run's virtual key>"}
  }
}
```

- `messages` is the full conversation so far, OpenAI-style (`role` is `"user"` for
  the customer and `"assistant"` for prior agent replies).
- `env` carries everything your agent needs to reach Bifrost: the model base URL
  and API key for `/v1/chat/completions`, and the MCP URL and headers for tools.
  Your agent must use these, not its own hardcoded credentials or endpoints —
  that's what keeps every run's trace scoped to its own virtual key.

**Response body:**
```json
{"reply": "Your reply text here."}
```

That's the entire contract. Point `ms run --agents byo_http --byo-url <your-url>`
at your server and it runs in the same matrix, scored the same way, as every
built-in adapter.
