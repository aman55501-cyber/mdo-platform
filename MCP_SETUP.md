# CFO MCP Server — Setup

The **CFO MCP server** (`cfo_mcp_server.py`) connects Claude (Desktop, Code,
Cursor, or any MCP client) to your live ANS MDO platform. Once configured, you
can ask Claude things like *"what's on my briefing today?"*, *"list overdue
compliance filings"*, *"calculate a VWLR bid for SECL, 8000 MT from Bilaspur at
₹2,300"*, or *"log a call with Adani Power"* — and it reads/writes straight
through the deployed backend.

It's a thin, stateless bridge: every tool call is proxied to your MDO backend
(`mdo_server.py`) at `CFO_MCP_BASE_URL`. It stores nothing itself.

---

## 1. Install (on the laptop, in a copy of the repo)

```bash
pip install -r requirements_mcp.txt
export CFO_API_TOKEN=…            # your app token (only if the backend requires one — see §4)
export CFO_MCP_BASE_URL=https://srv1641037.hstgr.cloud
```

Quick sanity check that it starts and the deps resolved:

```bash
python cfo_mcp_server.py   # starts on stdio; Ctrl-C to stop
```

(An MCP stdio server waits silently for a client — no output is normal.)

---

## 2. Wire it into your MCP client

### Claude Code (CLI)

```bash
claude mcp add cfo \
  --env CFO_MCP_BASE_URL=https://srv1641037.hstgr.cloud \
  --env CFO_API_TOKEN=your-app-token \
  -- python /ABSOLUTE/PATH/TO/mdo-platform/cfo_mcp_server.py
```

### Claude Desktop / Cursor (JSON config)

Copy the `cfo` block from [`mcp_config.example.json`](./mcp_config.example.json)
into your client's config, using an **absolute** path to `cfo_mcp_server.py`:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cfo": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/mdo-platform/cfo_mcp_server.py"],
      "env": {
        "CFO_MCP_BASE_URL": "https://srv1641037.hstgr.cloud",
        "CFO_API_TOKEN": "your-app-token-here"
      }
    }
  }
}
```

Restart the client. The tools appear under the **cfo** server.

> Tip: if `python` isn't on your client's PATH, use an absolute interpreter path
> (e.g. the one from `which python`), ideally a virtualenv where you ran the
> `pip install` above.

---

## 3. What you get (tools)

**Read**
`cfo_status` · `cfo_daily_briefing` · `cfo_list_intel` · `cfo_list_tasks` ·
`cfo_list_compliance` · `cfo_list_entities` · `cfo_aditi_pools` ·
`cfo_list_leads` · `cfo_list_followups` · `cfo_tender_pipeline` ·
`cfo_calc_bid` · `cfo_hotel_daily` · `cfo_market_watchlist` ·
`cfo_market_indices` · `cfo_market_quote` · `cfo_portfolio_news` ·
`cfo_intelligence_alerts` · `cfo_ask_grok`

**Write / act**
`cfo_add_intel` · `cfo_resolve_intel` · `cfo_add_task` · `cfo_update_task` ·
`cfo_update_compliance` · `cfo_add_lead` · `cfo_log_interaction` ·
`cfo_add_tender` · `cfo_run_intelligence_scan` · `cfo_generate_briefing`

**Escape hatch**
`cfo_api_request` — call any other `/api/...` route directly (trading signals,
Singhvi, WhatsApp, HDFC, etc.). See the routes in `mdo_server.py`.

---

## 4. About `CFO_API_TOKEN` (optional auth)

By default the MDO backend has **no** authentication — the API is open. In that
case `CFO_API_TOKEN` is not required (leave it unset on both sides).

To lock the API down, set the **same** `CFO_API_TOKEN` value in **two** places:

1. **On the backend** (e.g. the Railway service running `mdo_server.py`). When
   this env var is present, the server rejects any `/api/*` request without a
   matching `Authorization: Bearer <token>` (or `X-API-Token`) header. Returns
   `401` otherwise. `/api/health` and `/api/status` stay open for uptime checks.
2. **On this MCP server** (the `env` block above). It sends the token on every
   request automatically.

> ⚠️ If you enable the token on the backend, the MDO web dashboard
> (`mdo-app`) must also send it, or its API calls will start returning `401`.
> Enable it only once every client that talks to the backend supplies the
> token. Pick a long random string, e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`.

---

## 5. Configuration reference

| Variable            | Required | Default                          | Purpose                                       |
| ------------------- | -------- | -------------------------------- | --------------------------------------------- |
| `CFO_MCP_BASE_URL`  | no       | `https://srv1641037.hstgr.cloud` | Backend base URL the MCP server proxies to.   |
| `CFO_API_TOKEN`     | no       | *(unset)*                        | Bearer token; only needed if backend enforces it. |
| `CFO_MCP_TIMEOUT`   | no       | `30`                             | Per-request timeout, seconds.                 |

---

## 6. Troubleshooting

- **`Error: Cannot reach the MDO backend …`** — check `CFO_MCP_BASE_URL` and
  that the service is up (`curl $CFO_MCP_BASE_URL/api/health`).
- **`Error: Unauthorized (401) …`** — the backend has a token set; put the same
  value in `CFO_API_TOKEN` on the MCP side.
- **Tools don't appear** — confirm the path in the config is absolute and the
  client was fully restarted; check the client's MCP logs.
- **`ModuleNotFoundError: mcp`** — run `pip install -r requirements_mcp.txt`
  into the interpreter your client actually launches.
