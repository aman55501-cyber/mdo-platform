# MDO Platform — walkthrough for Aman

**Built from the code, not from memory.** Branch `claude/chief-of-staff-bot-4i2jyz`, read 2026-10-09. Base read at commit `0d21c48`; while this brief was being written the branch moved to `e6d3182` ("align fleet with Aman's 2026-10-09 decisions: objectives, charters, Singhvi bot, 30-day receivables"), which changed `agenda.yaml` (five objectives now `confirmed: true`, stated by Aman in chat), `fleet.yaml`, `mdo_agent.py`, `mdo_wa_intel.py` and `DEPLOY_HOSTINGER.md`. §5, §7 and §9 reflect `e6d3182` and mark those changes "2026-10-09". Every line below names the file it came from. Where a page or endpoint exists but returns nothing real, it says **stub**. Nothing here is a plan — only what the repository contains today.

How to read it: §1 is the map. §2 is every screen. §3 is every API route. §4 is every database table. §5 is every bot. §6–§8 are the plumbing (WhatsApp, VPS cron, cloud Routines). §9 is the honest list of what is not built.

---

## 1. Topology (docker-compose.yml, Caddyfile)

| Service | Image / build | Port | Role | Source |
|---|---|---|---|---|
| `caddy` | caddy:2 | 80/443 | One hostname (`DOMAIN`, optional `ALT_DOMAINS`), routed by path: `/api/*` and `/mcp/*` → backend, `/hdfc/*` → Shares CFO, `/*` → frontend | Caddyfile |
| `frontend` | ./mdo-app (Next.js) | 3000 | The app ("AMAN · Decision Office") | mdo-app/ |
| `backend` | Dockerfile (FastAPI, `mdo_server.py`) | 8501 | Every `/api/*` route, SQLite at `/data/vega_data.db`, MCP server at `/mcp/<MDO_MCP_SECRET>/mcp` | mdo_server.py |
| `sharescfo` | Dockerfile.sharescfo | 127.0.0.1:8000 only | Broker sessions (HDFC ×3 + Angel); backend reads it through `_cfo_get` for `/api/capital/*` | shares_cfo/ |
| `whatsapp`, `whatsapp2` | ./whatsapp_bridge (Baileys) | internal 3001 | Phone 1 (ops) and Phone 2 (hotel groups); forward every chat to `/api/whatsapp/message` | whatsapp_bridge/index.js |
| `vpn-hotel`, `vpn-vedanta` | ./vpn | internal 8888 proxy | OpenVPN sidecars to the two site LANs; read-only, no site hostnames discovered yet | mdo_sites.py |
| `autoheal` | willfarrell/autoheal | — | Restarts unhealthy containers | docker-compose.yml |
| Volumes | `mdo-data` (/data: DB, vault, backups, archive), `wa-auth`, `wa-auth2`, caddy, sharescfo state | | | DEPLOY_HOSTINGER.md §10 |

Access control (mdo_server.py `_require_key`): when `MDO_AUTH_TOKEN` is set, every `/api/*` call must carry `X-MDO-Key` (or `?key=` / Bearer). The app asks once per device (AuthGate.tsx, stored in localStorage). Exempt: `/mcp/*` (own secret), `/api/hdfc/callback`, `/api/cos/meta-webhook`, `/api/cos/tender-inbound`, `/api/vault/*` (own `X-Vault-Token`). **When `MDO_AUTH_TOKEN` is empty, the whole API is open** (deploy_vps.sh warns about this).

---

## 2. Frontend — every page (mdo-app/app/*/page.tsx)

### 2.1 Navigation order (components/layout/Sidebar.tsx)

| Section | Order | Label | Route |
|---|---|---|---|
| Command | 1 | Dashboard | `/` |
| | 2 | Decision Feed | `/feed` |
| | 3 | Fleet & Memory | `/fleet` |
| | 4 | Business Intel | `/wa-intel` |
| | 5 | Life LLM Map | `/lifemap` |
| | 6 | Daily Briefing | `/briefing` |
| | 7 | Agent Reports | `/reports` |
| | 8 | Live Feeds | `/feeds` |
| | 9 | Intel Centre | `/intel` |
| Sales | 10 | VWLR — Washery | `/vwlr` |
| Operations | 11 | Task Board | `/ops` |
| | 12 | VWLR Ops Feed | `/ops-feed` |
| | 13 | Entities (26) | `/entities` |
| | 14 | Compliance | `/compliance` |
| | 15 | Hotel ANS | `/hotel` |
| Capital | 16 | Morning Setup | `/morning` |
| | 17 | Aditi Investments | `/aditi` |
| Intelligence | 18 | Portfolio News | `/news` |
| | 19 | MDO Brain | `/grok` |
| (not in sidebar) | — | Trading | `/trading` |
| (not in sidebar) | — | Feed item | `/feed/[id]` (push-notification landing page) |

Also in the sidebar: "Next steps" mini-list (RemainingSteps.tsx → `GET /api/ops/tasks?category=roadmap`, tick = `PUT /api/ops/tasks/{id}`), 8 portal links (NSE, HDFC SKY, Tender247, GeM, IBBI, NCLT, MCA, GST), IST clock, LIVE/OFFLINE dot (SSE `/api/stream`). Every page is wrapped by `AuthGate` (lock screen) and `BrainDock` (floating chat → `POST /api/brain/ask`). React Query refetches every page every 20 s (layout.tsx).

### 2.2 Page by page

| Route | Shows | API calls | Actions / clicks | Status |
|---|---|---|---|---|
| `/` Dashboard (page.tsx, 970 lines) | 4 sections: Morning Briefing (today's generated text), Market indices bar (NIFTY 50, BANKNIFTY, USD/INR, NASDAQ, DOW), Coal Sector Pulse (Coal India, NTPC, Newcastle, NCI India, USD/INR with VWLR tooltips), Watchlist table (15 names, 52-week range bars) | `GET /api/briefing/today`, `POST /api/briefing/generate`, `GET /api/market/indices`, `GET /api/market/watchlist`, `GET /api/market/quote/{ticker}` | "Generate / Regenerate briefing" button; Ctrl-K hint | Live (Yahoo Finance data; briefing needs `ANTHROPIC_API_KEY` or `GROK_API_KEY`, else raw-data fallback) |
| `/feed` Decision Feed | Everything that needs Aman, critical first; each item shows evidence, proposed action in full text, and the site-tunnel status banner ("Site link down") | `GET /api/feed`, `GET /api/sites`, `POST /api/feed/{id}/approve`, `POST /api/feed/{id}/reject` | Approve / Reject per item; money-kind actions shown read-only with the refusal reason | Live |
| `/feed/[id]` | One item: what it is based on, proposed action, decision trail | `GET /api/feed/{id}`, `POST /api/feed/{id}/{approve\|reject}` | Approve / Reject | Live |
| `/fleet` Fleet & Memory | Spend this month vs cap + mode, "Needs you" open jobs, Storage, Bots table (cadence, model, last run, status, next due, dead list), Memory panel (where things live, objectives mirror, row counts, chats remembered, bot_memory) | `GET /api/fleet`, `GET /api/spend`, `GET /api/cos/memory`, `GET /api/cos/jobs?status=open` | Read-only | Live |
| `/wa-intel` Business Intel | 4 tabs: To classify (unclear chats with samples), Signals (filter by status/kind/entity), Register (assets/liabilities/… facts), Pulse (latest weekly pulse: sales gap, bottlenecks, reply efficiency, register changes, next steps) + stat strip | `GET /api/wa/stats`, `GET /api/wa/chats`, `POST /api/wa/chats/classify`, `GET /api/wa/signals`, `POST /api/wa/signals/{id}/status`, `GET/POST /api/wa/register`, `GET /api/wa/pulse/latest` | Mark chat business (+entity) / personal; signal done / dismissed / reopen; add register row | Live (empty until the bots have run) |
| `/lifemap` Life LLM Map | Column graph of layers principal → domains → sources → connectors → core → skills → surfaces, nodes coloured by live/building/planned/parked, SVG edges | `GET /api/lifemap`, `POST/PUT/DELETE /api/lifemap/nodes`, `POST/DELETE /api/lifemap/edges`, `POST /api/lifemap/reset` | Add node, edit label/detail/notes/status, link/unlink, delete, filter by status, "Reset to seed" | Live (seed is "reconstructed from MDO_VISION — NOT absolute data", mdo_server.py comment) |
| `/briefing` Daily Briefing | 🔴/🟡/🟢 alert list grouped by level, with what changed / why it matters / action | `GET /api/intelligence/briefing`, `POST /api/intelligence/scan`, `POST /api/intelligence/alerts/{id}/ack` | "Run scan" button (this is the **only** trigger for the rule-based scan — no cron calls it); Acknowledge per alert | Live |
| `/reports` Agent Reports | Last 40 bot reports filtered by cadence, expandable body + findings; checks registry | `GET /api/agent/reports?limit=40&cadence=`, `GET /api/checks` | Cadence filter, expand | Live |
| `/feeds` Live Feeds | Cards for Singhvi / Tender247 / GeM / NCLT-IBBI / Bank auction / HDFC; 9 quick links | `GET /api/feeds/all`, `POST /api/singhvi/refresh` | Source filter, Refresh | **Stub** — backend returns empty lists with note "Add GROK_API_KEY to .env for live feeds"; no fetcher exists even with the key |
| `/intel` Intel Centre | Intel items by status / urgency / category, expandable | `GET /api/intel?…`, `POST /api/intel/{id}/resolve`, `/acknowledge`, `/snooze` | Resolve, Acknowledge, Snooze (days); filters | Live |
| `/vwlr` VWLR — Washery Sales | Tabs: Coal Tenders (Tender247 quick-launch buttons RCR / loading-unloading / rake handling, tender pipeline), Leads (filter by priority, follow-up reminders), Bid Calculator (buyer, volume, route, gate price → breakdown, copy), Competitors (grid, "log a sighting", threat) | `GET /api/vwlr/tenders`, `/leads`, `/followups`, `/interactions`, `/competitors`, `/bid?…`; `POST /api/vwlr/tenders/add`, `POST /api/vwlr/interactions`, `POST /api/vwlr/leads` (via modal), `PUT /api/vwlr/competitors/{id}` | New tender, Add lead, Log call, calculate bid, copy breakdown, competitor notes/last-seen | Live (leads/tenders read the Vedanta CRM DB — a **stopgap seed of 11 leads + 4 pipeline rows** unless the real `vedanta_crm.db` is uploaded, seed_mdo_db.py) |
| `/ops` Task Board | Tasks by tab all / sales / compliance / operations / trading, due-today badge, show-done toggle | `GET /api/ops/tasks?…`, `POST /api/ops/tasks`, `PUT /api/ops/tasks/{id}` | Add task (title, description, entity, assignee, due, priority, category), Complete, Delete (status change) | Live |
| `/ops-feed` VWLR Ops Feed | WhatsApp groups list, messages per group, QR panels for Phone 1 (+91 7000512030) and Phone 2 (hotel groups) | `GET /api/whatsapp/groups`, `GET /api/whatsapp/messages?group=`, `GET /api/whatsapp/qr?account=1\|2` | Group filter, refresh, scan QR | Live |
| `/entities` Entities | Card grid with type filter (company / individual / HUF / firm) and search; drawer with CIN/GSTIN/PAN, directors, turnover, notes, that entity's filings, Quick Actions (MCA, GST, Income Tax, NCLT links) | `GET /api/entities?type=`, `GET /api/compliance/filings?entity=` | Open drawer; external links | Live, but the register is the **seed**: 25 rows, 12 flagged `unverified` (seed_mdo_db.py `UNVERIFIED`). Sidebar says "(26)" and the page says "ANS Group Entities"; MDO_VISION §2D says the real register is 20 entities + 5 individuals and the "26th" does not exist |
| `/compliance` Compliance | Filings grouped by entity, status filter (Overdue / Pending / Filed), due-today badge, CA contact card (CA Vimal Agrawal), portal links (MCA, GST, Income Tax, TRACES) | `GET /api/compliance/filings?entity=&status=`, `PUT /api/compliance/filings/{id}` | Mark filed / Mark pending | Live UI over **17 seeded rows dated April 2026** (see briefs/COMPLIANCE_CALENDAR_REVIEW.md) |
| `/hotel` Hotel ANS | Quick-access portals, Occupancy tracker (7-day chart, 30-room constant), today's numbers form (occupied, rate, F&B), OTA & distribution channel cards, Ops notes | `GET /api/hotel/daily?days=7`, `POST /api/hotel/daily`, `POST /api/ops/tasks` (note → task, category hotel) | Save numbers, Save note | Live; an amber banner "Backend not yet configured — data saved locally" appears when the API is unreachable. `TOTAL_ROOMS = 30` in the page vs "88 rooms" in the entity notes — the page constant is unverified |
| `/morning` Morning Setup | Singhvi calls for today (pending / approved / skipped counts), manual trade entry form, HDFC connection widget, "Execute at Market Open", How-to-use | `GET /api/singhvi/today`, `POST /api/singhvi/calls`, `POST /api/singhvi/calls/{id}/{approve\|reject}`, `DELETE /api/singhvi/calls/{id}`, `POST /api/singhvi/extract`, `POST /api/singhvi/execute`, `GET /api/hdfc/status`, `POST /api/hdfc/auth/init` | Extract (yt-dlp → Whisper → LLM, background), Add call, Approve / Reject / Delete, Execute all, Connect HDFC | Partly live. **"Execute" does not place a broker order**: it copies approved calls into `trading_signals` (mdo_server.py `singhvi_execute`). HDFC OAuth exists but the callback registration is an open candidate (agenda `hdfc-oauth`) |
| `/aditi` Aditi Investments | Tabs Portfolio (4 pools, allocation, Pool B positions/holdings), Trade Ideas (live signals with confirm/reject, risk meter), Market Intel (block deals, corporate actions, FII/DII), Global Triggers, News | `GET /api/aditi/pools`, `GET /api/positions`, `/holdings`, `/pnl`, `/funds`, `GET /api/trading/signals`, `POST /api/trading/signals/{id}/{confirm\|reject}` | Tab switch, Confirm / Reject signal | **Mixed.** Pools come from the DB (seeded). Positions / holdings / pnl / funds are backend **stubs returning zero/empty**. Market Intel, Global Triggers, Market Calendar and News tabs are **hard-coded arrays dated April 2026** in the page file (`BLOCK_DEALS`, `CORP_ACTIONS`, `FII_DII`, `GLOBAL_TRIGGERS`, `MARKET_CALENDAR`, `NEWS_ITEMS`) — not data |
| `/news` Portfolio News | Headlines per ticker, unread marker | `GET /api/news/portfolio?tickers=`, `POST /api/news/portfolio/refresh`, `POST /api/news/{id}/read` | Refresh (Yahoo Finance RSS), ticker filter, mark read | Live |
| `/grok` MDO Brain | Chat with the brain, suggested questions, status line | `GET /api/brain/status`, `POST /api/brain/ask` | Send question | Live (Anthropic API, `BRAIN_MODEL` default claude-fable-5-1, 41 tools over the backend; CHIEF_OF_STAFF.md is prepended to its system prompt) |
| `/trading` (hidden) | Realised / unrealised P&L, trades today, win rate, position P&L chart, funds, holdings | `GET /api/positions`, `/holdings`, `/pnl`, `/funds` | None | **Stub** — all four endpoints return zeros/empty |

---

## 3. Backend routes — grouped, with auth

Auth legend: **app key** = `X-MDO-Key` when `MDO_AUTH_TOKEN` is set · **vault** = `X-Vault-Token` (`VAULT_TOKEN`) · **tender** = `X-Tender-Token` (`TENDER_INBOUND_TOKEN`) · **meta** = Meta webhook signature / verify token · **public** = no key.

### 3.1 mdo_server.py (FastAPI app, 3,339 lines)

| Area | Method + path | Purpose | Auth |
|---|---|---|---|
| Status | GET `/api/status` | Market open/closed by IST clock, fixed 5-name watchlist, `broker_authenticated: False` | app key |
| Trading stubs | GET `/api/positions`, `/api/holdings`, `/api/funds`, `/api/pnl`, `/api/watchlist`, `/api/health` | **Stubs**: empty lists / zeros / `broker: False, grok: False` | app key |
| Stream | GET `/api/stream` | SSE keep-alive ping every 25 s (frontend LIVE dot) — no real events | app key (or `?key=`) |
| Intel | GET `/api/intel`, POST `/api/intel`, POST `/api/intel/{id}/resolve` · `/acknowledge` · `/snooze` | Intel items CRUD-lite | app key |
| Ops tasks | GET/POST `/api/ops/tasks`, PUT `/api/ops/tasks/{id}` | Task board + roadmap items | app key |
| Capital | GET `/api/capital/summary`, GET `/api/capital/accounts` | Reads Shares CFO (`/portfolio`, `/exposure`, `/positions/live`, `/accounts`) and computes the 🔴/🟡 flags; reports staleness | app key |
| Checks | GET/POST `/api/checks`, PUT `/api/checks/{id}` | The standing checks registry (12 seeded) | app key |
| Alerts | POST `/api/alerts/test` | Fires a test line to WhatsApp | app key |
| Decision Feed | GET `/api/feed`, GET `/api/feed/digest`, GET `/api/feed/{id}`, POST `/api/feed/publish`, POST `/api/feed/{id}/approve` · `/reject`, POST `/api/feed/notify-pending`, POST `/api/feed/check-sessions` | Publish with dedup + cooldown + severity routing; approve executes registered actions (`add_task`, `file_intel` internal; `whatsapp_message` outward; **money refused**); check-sessions publishes a 🔴 when a broker login is dead | app key |
| Sites | GET `/api/sites`, GET `/api/sites/{site}`, POST `/api/sites/check` | VPN tunnel status + configured read-only sources (none configured yet) | app key |
| Agent reports | POST `/api/agent/report`, GET `/api/agent/reports`, GET `/api/agent/reports/{id}` | Every bot files here; heartbeats record `cos_runs`; new 🔴 findings push one WhatsApp line each; error heartbeats push 💀 | app key |
| Entities | GET `/api/entities`, PUT `/api/entities/{id}` | Register | app key |
| Compliance | GET `/api/compliance/filings`, PUT `/api/compliance/filings/{id}` | Filing tracker (no POST — new filings can only come from the seed or SQL) | app key |
| Aditi | GET `/api/aditi/pools`, PUT `/api/aditi/pools/{code}` | 4 pools | app key |
| VWLR | GET `/api/vwlr/tenders` · `/leads` · `/followups` · `/bid` · `/interactions` · `/pipeline` · `/competitors`; POST `/api/vwlr/leads` · `/interactions` · `/tenders/add`; PUT `/api/vwlr/leads/{id}` · `/pipeline/{id}` · `/competitors/{id}` | Sales CRM over the Vedanta DB + pipeline/competitor tables | app key |
| Hotel | GET/POST `/api/hotel/daily` | 7-day occupancy history; manual entry | app key |
| Trading signals | GET/POST `/api/trading/signals`, POST `/api/trading/signals/{id}/confirm` · `/reject` · `/execute`, PUT `/api/trading/signals/{id}` | Signal ledger; `/execute` only records an order id someone else placed | app key |
| Feeds | GET `/api/feeds/all` · `/tenders` · `/gem` · `/npa`, GET `/api/singhvi`, POST `/api/singhvi/refresh`, POST `/api/grok/ask` | **Stubs** — empty lists with "Add GROK_API_KEY" note; `/grok/ask` returns a fixed string | app key |
| Market | GET `/api/market/quote/{symbol}` · `/watchlist` · `/indices` | Yahoo Finance | app key |
| Briefing | GET `/api/briefing/today`, GET `/api/briefing/today/raw`, POST `/api/briefing/generate` | Written briefing via Anthropic (claude-sonnet-5) or Grok (grok-3-mini), else raw-data fallback | app key |
| WhatsApp ingest | POST `/api/whatsapp/message`, POST `/api/whatsapp/status`, GET `/api/whatsapp/qr`, GET `/api/whatsapp/extractions` · `/messages` · `/groups` | Bridge inbound: personal gate, dedup, night-report → `hotel_daily`, group images → vision extraction (`VISION_MODEL` claude-sonnet-5, keyword-matched groups) | app key (bridge sends `MDO_AUTH_TOKEN`) |
| Singhvi | GET `/api/singhvi/today`, POST `/api/singhvi/calls`, POST `/api/singhvi/calls/{id}/approve` · `/reject`, DELETE `/api/singhvi/calls/{id}`, POST `/api/singhvi/extract`, GET `/api/singhvi/extract/status`, POST `/api/singhvi/execute` | Morning Setup queue; extract = yt-dlp → faster-whisper → LLM in a background thread | app key |
| HDFC | GET `/api/hdfc/status`, POST `/api/hdfc/auth/init`, POST `/api/hdfc/auth/callback`, GET `/api/hdfc/callback`, GET `/api/hdfc/funds` | InvestRight OAuth; callback hands over to Shares CFO (`CFO_PUBLIC_URL`) | app key except GET `/api/hdfc/callback` = **public** |
| News | GET `/api/news/portfolio`, POST `/api/news/portfolio/refresh`, POST `/api/news/{id}/read` | Yahoo RSS per ticker | app key |
| Intelligence | GET `/api/intelligence/alerts`, POST `/api/intelligence/alerts/{id}/ack`, POST `/api/intelligence/scan`, GET `/api/intelligence/briefing` | Rule-based scan: compliance due dates, tender dates, tasks, intel → `intelligence_alerts`. Triggered only by the Daily Briefing page button | app key |
| Life map | GET `/api/lifemap`, POST/PUT/DELETE `/api/lifemap/nodes[/{id}]`, POST/DELETE `/api/lifemap/edges[/{id}]`, POST `/api/lifemap/reset` | Graph CRUD | app key |
| Brain | POST `/api/brain/ask`, GET `/api/brain/status` | Chat with tools; MCP mount at `/mcp/<secret>/mcp` for the Claude app | app key; `/mcp/*` = own secret |

### 3.2 mdo_cos_api.py (mounted into the same app)

| Area | Method + path | Purpose | Auth |
|---|---|---|---|
| Spend | GET `/api/spend`, POST `/api/spend/record` | Month-to-date ₹ vs `SPEND_CAP_INR_MONTH`; mode normal / economy (≥90%, bots drop to Haiku) / paused (100%) | app key |
| Fleet | GET `/api/fleet`, POST `/api/fleet/run` | fleet.yaml + last run per bot + dead list | app key |
| Agenda | GET/PUT `/api/cos/agenda` | Mirror of agenda.yaml (CoS writes it) | app key |
| Jobs | GET/POST `/api/cos/jobs`, PUT `/api/cos/jobs/{id}` | Numbered jobs: info / needs_click / needs_choice / proposal / stuck | app key |
| Memory | GET/POST `/api/cos/memory` | Where things live + `bot_memory` rows (active / proposed / retired) | app key |
| Inbound | POST `/api/cos/inbound` | WhatsApp reply from Aman: `ok 14` / `no 14` / `14:2` resolve jobs, else free text → brain with chat memory | app key (bridge) |
| Meta | GET/POST `/api/cos/meta-webhook` | Meta Cloud API verify + inbound (alternative channel) | **meta** signature |
| Tender door | POST `/api/cos/tender-inbound` | Any outside agent may post tenders → `vwlr_tender_pipeline` (status evaluating), nothing else | **tender** token |
| Vault | GET `/api/vault/list` · `/get` · `/audit`, PUT `/api/vault/put`, GET `/api/vault/backup/list` · `/backup/latest` | `memory/` and `finance/` files on the VPS; atomic write keeps `.prev`; every call audited; backup door serves only `.enc` bundles | **vault** token |
| Send | POST `/api/cos/send` | Send a CoS line to WhatsApp (channel per `COS_CHANNEL`: alert self-message / baileys / meta) | app key |
| Constitution | GET `/api/cos/constitution` | Returns CHIEF_OF_STAFF.md | app key |

### 3.3 mdo_wa_intel.py (mounted)

| Method + path | Purpose | Auth |
|---|---|---|
| GET `/api/wa/chats`, POST `/api/wa/chats/classify`, POST `/api/wa/chats/asked`, POST `/api/wa/verdicts/apply` | Chat register (business / personal / unclear); a **personal verdict deletes that chat's messages, extractions and open signals**; `asked` links a needs_choice job; `apply` executes Aman's replies | app key |
| GET `/api/wa/messages` | Business-chat messages since a watermark (for wa-intel) | app key |
| GET/POST `/api/wa/signals`, POST `/api/wa/signals/{id}/status` | Signal ledger; on insert, 🔴 line pushed for decision_needed, complaint, payable due ≤3 days | app key |
| GET/POST `/api/wa/register` | Facts register (asset / liability / capital / debt / resource / commitment / vision) | app key |
| GET `/api/wa/pulse/input`, POST `/api/wa/pulse`, GET `/api/wa/pulse/latest` | Computed weekly numbers in; narrated pulse out | app key |
| GET `/api/wa/stats` | Counts for the Business Intel stat strip | app key |

### 3.4 mdo_feed.py and mdo_sites.py

No routes of their own. `mdo_feed.py` is the Decision Feed library (dedup keys, cooldowns 180/720/1440 min by severity, 7-day expiry, notify policy push/digest/silent, action kinds internal/outward/money with money refused unless `MDO_FEED_MONEY_ACTIONS=1`). `mdo_sites.py` is the VPN read layer (GET only; sources from `MDO_SITE_SOURCES` / `site_sources.json`; "no sources configured" otherwise; tunnel alerts published to the feed).

---

## 4. SQLite tables (`/data/vega_data.db`, plus the Vedanta CRM DB)

| Table | Records | Written by |
|---|---|---|
| `intel_items` | Findings with urgency / entity / due / status | seed; app + brain `add_intel_item`; every bot's 🔴/🟡 finding via `/api/agent/report`; feed action `file_intel` |
| `ops_tasks` | Tasks incl. `category=roadmap` build steps | seed; app; brain `add_task`; feed action `add_task`; hotel notes; RemainingSteps ticks |
| `compliance_filings` | One row per filing: entity, type, description, due, period, status, assigned_to (default "CA Vimal Agrawal"), filed_on | **seed only (seed_mdo_db.py `FILINGS`, 17 rows) + PUT from /compliance.** No bot writes it |
| `ans_entities` | Entity register (name, type, CIN/GSTIN/PAN, directors, turnover, status) | seed (25 rows, 12 `unverified`) + PUT from /entities |
| `aditi_pools` | Pools A–D target vs current | seed + PUT |
| `vwlr_interactions` | Call / meeting logs per lead | /vwlr "Log call" |
| `vwlr_tender_pipeline` | Tenders being evaluated | /vwlr "New tender"; tender-inbound door (any outside agent); PUT |
| `hotel_daily` | One row per date: rooms, occupied, rate, F&B, occupancy % | /hotel form; WhatsApp night-report parser (`_parse_night_report`) |
| `trading_signals` | Trade ideas with entry / target / SL / status | POST `/api/trading/signals` (external capital engine); `singhvi_execute`; confirm/reject from /aditi |
| `morning_briefing` | One generated briefing per date | `/api/briefing/generate` (dashboard button or auto on first view) |
| `singhvi_calls` | Calls for the day with status | /morning manual entry; Singhvi extract pipeline |
| `whatsapp_messages` | Every stored message (group + DM, both accounts, `from_me`) | bridges via `/api/whatsapp/message`; trimmed >90 d by housekeeping; deleted on a personal verdict |
| `checks` | The 12 standing checks (code, cadence, domain, sources, threshold, owner, window, status, blocker, last_run) | seed `CHECKS_SEED`; PUT; bots read it to know what to run |
| `agent_reports` | Every bot run's title / summary / body / findings | every bot, deploy heartbeat, housekeeping; archived >60 d |
| `media_extractions` | What a photo said (doc_type, summary, fields) | vision extraction inside `/api/whatsapp/message` |
| `hdfc_session` | Access token, expiry, margin, connected | HDFC OAuth callback |
| `vwlr_competitors` | 15 tracked competitors | seed; /vwlr competitor grid |
| `intelligence_alerts` | 🔴/🟡/🟢 alerts from the rule scan | `/api/intelligence/scan` (Daily Briefing button only) |
| `portfolio_news` | Headlines per ticker | `/api/news/portfolio/refresh` (Yahoo RSS) |
| `life_map_nodes`, `life_map_edges` | The Life LLM Map graph | seed; /lifemap |
| `cos_runs` | One row per bot heartbeat / report (bot, status, summary) | `/api/agent/report`, `/api/fleet/run`, tender-inbound |
| `spend_ledger` | Tokens + ₹ per LLM call | mdo_agent after each call; housekeeping chat compaction |
| `cos_jobs` | Numbered jobs needing Aman (kind, options, status, answer, payload) | CoS; wa-classifier (`needs_choice`); brain `create_job`; resolved by WhatsApp reply or PUT |
| `cos_agenda` | JSON mirror of agenda.yaml | CoS via PUT `/api/cos/agenda` |
| `cos_chat`, `cos_chat_summary` | Brain chat memory per chat id | brain (WhatsApp inbound + app chat); compacted to 20 turns by housekeeping |
| `vault_audit` | Every vault access (never trimmed) | `/api/vault/*` |
| `bot_memory` | Facts a bot learned (active / proposed / retired) | bots (e.g. wa-intel watermark); CoS proposals |
| `wa_chats` | One row per chat: classification, entity, confidence, decided_by | `/api/whatsapp/message` upsert; wa-classifier; Aman via /wa-intel |
| `biz_signals` | Lead / quote / order / receivable / payable / delay / … with evidence ids | wa-intel via POST `/api/wa/signals`; status from /wa-intel |
| `biz_register` | Asset / liability / capital / debt / resource / commitment / vision rows | /wa-intel register form (POST `/api/wa/register`) |
| `biz_pulse` | Weekly computed + narrated pulse | business-pulse via POST `/api/wa/pulse` |
| `feed_items`, `feed_audit` | Decision Feed items + append-only state log | mdo_agent (findings → feed), wa signals, site tunnel alerts, session check, business-pulse; decisions from the app |
| Vedanta DB: `leads`, `tender_tracking` | Sales CRM | real `vedanta_crm.db` if uploaded; else stopgap seed (11 leads, 4 pipeline rows) |

---

## 5. The fleet (fleet.yaml, working tree 2026-10-09)

Objectives in `agenda.yaml` (working tree, all `confirmed: true`, source "Aman, chat 2026-10-09"): `vwlr-dispatch` (≥15,000 MT/day, no idle equipment, EV loader-4 added), `tenders-washing-rcr` (win one coal-washing + one RCR contract, margin first), `hotel-renovation-contract` (renovation + Guptasons management contract only; floor-layout PDF/CAD owner Shashank Nashine), `capital-rules` (no targets, never book a loss, >80% conviction, crude watch), `battery-plant` (exploratory, no objective yet). None is on the Objectives sheet yet (fleet_gaps).

| Bot | Runs on | Cadence (cron, IST) | Model | Reads | Writes | Reports to | Enabled / serves |
|---|---|---|---|---|---|---|---|
| **cos** Chief of Staff | claude-code-routine (fresh cloud session) | daily 06:22 + on demand | claude-fable-5-1 | Objectives sheet, agenda.yaml, fleet.yaml, `/api/agent/reports`, `/api/checks`, `/api/intel`, `/api/ops/tasks`, `/api/capital/summary`, Gmail, Calendar | agenda mirror, jobs, intel, Gmail drafts (never sends), repo fixes, COS_LOG.md | `POST /api/agent/report cadence=cos` → WhatsApp roll-up | enabled |
| ops-hourly | vps-cron | hourly (:24) | claude-sonnet-5-5 | last ~120 group messages + photo extractions, open intel, reports, agenda, sites | report / feed items; now also: idle equipment while work waits, machine down >30 min = 🔴, day under 15,000 MT, manpower short | `/api/agent/report` | enabled; serves vwlr-dispatch, tenders-washing-rcr |
| daily-brief | vps-cron | 06:57 | claude-sonnet-5-5 | ~300 messages, filings, open tasks, pools, entities (hotel_daily check **dropped** 2026-10-09) | report, first line = yesterday's MT vs 15,000 + equipment availability | `/api/agent/report` | enabled; serves vwlr-dispatch |
| tender-go-no-go | vps-cron | 08:00 | claude-opus-5-5 | `/api/vwlr/pipeline`, feeds, agenda; skill `skills/tender-go-no-go.md` (**file absent** — skills/ holds only escalation-routing.md) | report: coal-washing / RCR tenders only, margin first; everything else one line | `/api/agent/report` | enabled; serves tenders-washing-rcr |
| compliance-sentinel | vps-cron | 07:30 | claude-opus-5-5 | `/api/compliance/filings`, `/api/ops/tasks?status=open`, intel, entities | report (🔴 ≤3 d / overdue, 🟡 4–14 d) | `/api/agent/report` | enabled; **serves [] — no confirmed objective behind it** (unchanged by the 2026-10-09 edit) |
| capital-watcher | vps-cron | hourly 09:05–15:35 Mon–Fri | claude-opus-5-5 | `/api/capital/summary` (Shares CFO), watchlist, portfolio news; crude watch | report; never suggests booking a loss; trade suggestions only >80% conviction | `/api/agent/report` | enabled; serves capital-rules |
| hotel-daily | vps-cron | **20:00** (was 22:30) | claude-sonnet-5-5 | hotel civil/renovation groups, open tasks, sites (check `projects_update`, not `hotel_daily`) | report: renovation progress, Guptasons contract milestones, floor-layout PDF/CAD status; **no occupancy/sales/OTA** | `/api/agent/report` | enabled; serves hotel-renovation-contract |
| wa-classifier | vps-cron | every 2 h (:10) | claude-haiku-4-5 | unclear chats (≥3 msgs; ≥1 for groups), ≤30 samples each; resolved `cos_jobs` | `/api/wa/chats/classify`, `/api/cos/jobs` (needs_choice when <0.85) | heartbeat line | enabled, serves [] |
| wa-intel | vps-cron | every 6 h (:20) | claude-sonnet-5-5 | business messages since watermark (`bot_memory`), ≤80/call, ≤2000/run; open receivables | `/api/wa/signals` (backend pushes 🔴 for decision_needed / complaint / payable ≤3 d); **new**: sweep files 🔴 per receivable open >`RECEIVABLE_OVERDUE_DAYS` (default 30) once each | heartbeat line | enabled, serves [] |
| business-pulse | vps-cron | Sun 07:00 + on demand | claude-opus-5-5 | open signals 90 d, reply metrics 14 d, register (`/api/wa/pulse/input`) | `biz_pulse`, one Decision Feed item, one roll-up line | heartbeat line | enabled, serves [] |
| classifier | library | — | claude-haiku-4-5 | — | — | — | **disabled** |
| housekeeping | vps-cron | daily 03:00 (`--daily`) + Sun 03:00 | none | DBs, reports, messages, chats, disk | snapshots (keep 14), archive >60 d reports / >90 d messages, VACUUM, chat compaction, weekly AES-256 bundle (keep 8; skipped without `VAULT_BACKUP_PASSPHRASE`) | `/api/agent/report` one line | enabled, serves all |
| backup-offsite | cloud-routine | Sun 08:00 | claude-fable-5-1 | `GET /api/vault/backup/latest` (vault token) | Google Drive › "MDO Backups" | push | enabled in yaml; **Routine not yet created** (fleet_gaps) |
| deploy | vps-cron | every 10 min (`deploy_vps.sh --auto`) | none | origin/branch | pull → pytest in throwaway container → `docker compose up -d --build` | heartbeat `/api/agent/report` (bot=deploy) | enabled, serves all |
| singhvi | vps-cron (**enabled 2026-10-09**, was disabled) | weekdays 08:05 | grok-4 (x_search + web_search) | X / zeebiz.com write-ups of Singhvi's calls (`run_singhvi` in mdo_agent.py) | `POST /api/singhvi/calls` status pending, only >80% conviction, URL per call; never approves, never writes trading_signals | heartbeat every weekday | enabled; serves capital-rules; needs `GROK_API_KEY` + the new cron line installed by re-running deploy_vps.sh |
| x-watch | vps-cron | hourly 07:00–22:00 | grok-4 (xAI x_search + web_search) | X + web; crude keywords every run (Brent, WTI, OPEC+, EIA/API, Hormuz, sanctions, INR/USD) | report with URL per finding, market-positive/negative tag; spend ledger at Grok list price | `/api/agent/report` | enabled; serves tenders-washing-rcr, capital-rules; **still no cron line in DEPLOY_HOSTINGER §8** (see §9) |
| share-master-refresh | claude-routine | 09:25 Mon–Fri | claude-sonnet-5-5 | Supabase share_master + desk_ideas | republishes the Share Master artifact | push | enabled |
| weekly-finance-update | claude-routine | Sun 08:30 | (blank) | Gmail statements; workbook from vault | workbook PUT back to vault (`.prev` kept) | push | enabled; needs Gmail connector + VAULT_TOKEN + MDO_SELF_URL |
| weekly-memory-sync | claude-routine | Sun 07:30 | (blank) | week's sessions; `memory/*.md` from vault | vault PUT + `memory/_log.md` | push | enabled; vault import pending |
| life-os-weekly-review | claude-routine | Sun 08:00 | (blank) | Notion Life OS | nothing (read-only digest) | push | enabled |

Every VPS bot runs as `docker compose exec -T backend python mdo_agent.py <bot-id>` (mdo_agent.py): reads the checks registry, respects run windows, drops to Haiku at ≥90% of cap, stops at 100%, files a heartbeat even when clean, publishes findings to the Decision Feed. By CHIEF_OF_STAFF.md §1.8 a bot with no live objective is to be paused: compliance-sentinel, wa-classifier, wa-intel and business-pulse still carry `serves: []` with `enabled: true`.

---

## 6. WhatsApp bridges (whatsapp_bridge/index.js, 504 lines)

| What | Detail |
|---|---|
| Library | Baileys (`@whiskeysockets/baileys` 6.7), no Chromium; Express on :3001. (`server.js` in the same folder is the **old whatsapp-web.js version**, not used by compose.) |
| Accounts | `WA_ACCOUNT=1` (ops phone +91 7000512030) and `2` (second phone, hotel groups); separate auth volumes `/data/wa_auth` |
| What it forwards | **Every chat** — groups and DMs, incoming and Aman's own (`from_me`) — to `POST /api/whatsapp/message` with `X-MDO-Key`. Drops status / broadcast / newsletter, reactions, edits, unresolved LIDs. `WA_WATCH_MODE=list` restricts to the 6 `WATCHED_GROUPS` (Vedanta Daily Report, VWLR Rake Placement, VWLR to APL Raigarh, VWLR-RKM Group, VWLR Shifting, Night Report); default is `all` |
| Images | Group images ≤8 MB downloaded and sent base64; backend runs vision (claude-sonnet-5) when the group name matches `VISION_GROUPS` keywords. DM images: caption or `[media]` only, no download |
| History | On first pairing ingests existing history so Ops Feed is not empty |
| Two-way CoS | With `COS_INBOUND=1` and `COS_ALLOWED_NUMBERS`, DMs from allowed numbers go to `POST /api/cos/inbound`; replies start with `CoS ·` and are never echoed back |
| Endpoints it serves | `GET /api/whatsapp/qr` (base64 PNG), `GET /api/whatsapp/status`, `POST /api/whatsapp/send` (backend → phone), `GET /health` |
| Status | Posts connected / logged-out to `/api/whatsapp/status`; logged-out = rescan QR (one of the three things only Aman can do per deploy summary) |

---

## 7. VPS: deploy, cron, self-update, backups (deploy_vps.sh, DEPLOY_HOSTINGER.md §8 / §10)

**`sudo bash deploy_vps.sh`** (idempotent): checks out the branch, gap-fills `.env` from `.env.example` (never overwrites), builds backend, runs `pytest tests/` in a throwaway container (red test = nothing changes), `docker compose up -d --build` backend + bridges, writes `/etc/cron.d/mdo-fleet` from the §8 block, removes old per-user cron lines, fires a test alert, prints the keys only Aman can fill. **`--auto`** every 10 min: `git fetch` + `ff-only pull` only when origin is ahead, same test gate, logs to `/var/log/mdo-deploy.log`, one at a time (flock), and posts a `deploy` heartbeat every run ("deployed <sha> — tests passed" / "up to date" / error → 💀).

The cron file (`/etc/cron.d/mdo-fleet`, host time UTC):

| UTC | IST | Job |
|---|---|---|
| `24 * * * *` | hourly | `mdo_agent.py ops-hourly` |
| `27 1 * * *` | 06:57 | `mdo_agent.py daily-brief` |
| `0 2 * * *` | 07:30 | `mdo_agent.py compliance-sentinel` |
| `30 2 * * *` | 08:00 | `mdo_agent.py tender-go-no-go` |
| `35 2 * * 1-5` | 08:05 Mon–Fri | `mdo_agent.py singhvi` (**added 2026-10-09, working tree**; installed only when `deploy_vps.sh` is re-run) |
| `35 3-10 * * 1-5` | 09:05–15:35 Mon–Fri | `mdo_agent.py capital-watcher` |
| `30 14 * * *` | 20:00 (was 22:30) | `mdo_agent.py hotel-daily` (renovation + Guptasons tracker, **working tree**) |
| `10 */2 * * *` | every 2 h | `mdo_agent.py wa-classifier` |
| `20 */6 * * *` | every 6 h | `mdo_agent.py wa-intel` |
| `30 1 * * 0` | Sun 07:00 | `mdo_agent.py business-pulse` |
| `30 21 * * *` | 03:00 daily | `mdo_housekeeping.py --daily` (snapshots) |
| `30 21 * * 6` | Sun 03:00 | `mdo_housekeeping.py` (purge + weekly bundle) |
| `0 22 * * 6` | Sun 03:30 | `savelog -n -c 8 /var/log/mdo-agent.log` |
| `*/10 * * * *` | every 10 min | `deploy_vps.sh --auto` (appended by the script) |

Backups (§10): `/data/backups/<name>-YYYYMMDD.db.gz` daily via SQLite online-backup API + `PRAGMA integrity_check`, keep 14; `/data/backups/weekly-YYYYMMDD.tar.enc` (vault + snapshots, `openssl aes-256-cbc -pbkdf2`, `VAULT_BACKUP_PASSPHRASE`), keep 8, served only through `GET /api/vault/backup/latest`; off-site copy to Drive by `backup-offsite`; restore = 5 documented commands. Housekeeping never touches agenda.yaml, COS_LOG.md, the Objectives sheet, open intel / tasks / jobs, checks, bot_memory. 🔴 at <15% disk free. CI (`.github/workflows/ci.yml`): pytest + py_compile on Python 3.11 and `node --check` on the bridge, every push.

---

## 8. claude.ai Routines named in fleet.yaml

| Routine | Fires | Needs | Does |
|---|---|---|---|
| Chief of Staff morning run | `CRON_TZ=Asia/Kolkata 22 6 * * *`, fresh session | `MDO_AUTH_TOKEN` + `MDO_SELF_URL` in the cloud env, domain allowed, Claude Docs + Gmail + Calendar connectors | §2 of CHIEF_OF_STAFF.md: read sheet → ledger → heartbeat audit → advance objectives → one message → COS_LOG.md line |
| backup-offsite (`runs_on: cloud-routine`) | Sun 08:00 | Google Drive connector, `VAULT_TOKEN`, `MDO_SELF_URL`, and a bundle to fetch | Fetch `weekly-*.tar.enc`, upload to Drive "MDO Backups", report name + bytes. **Not yet created** (fleet_gaps) |
| share-master-refresh | 09:25 Mon–Fri | Supabase | Republish Share Master artifact, one push |
| weekly-finance-update (cloud, vault) | Sun 08:30 | Gmail connector, `VAULT_TOKEN`, `MDO_SELF_URL` | Append statements / dividends / balances to the finance workbook in the vault. Laptop twin disabled, not deleted |
| weekly-memory-sync | Sun 07:30 | `VAULT_TOKEN` | Consolidate the week's facts into `memory/*.md` in the vault + `_log.md` |
| life-os-weekly-review | Sun 08:00 | Notion connector | Read-only digest for Aman & Jahnavi |

COS_LOG.md shows three logged runs (2026-10-08 11:40, 13:05; 2026-10-09 10:20), all with `objectives 0/0/0`, `findings 0`, `spend ₹0`, fleet `0/N` ("cron pending first cycle").

---

## 9. What is NOT built

### 9.1 fleet_gaps (fleet.yaml, verbatim intent)

| Gap | Effect today |
|---|---|
| `bank_balances` check has no feed | Reported as a gap in every daily brief; check status `blocked` |
| `tender_watch` has no Tender247 access | Public portals only; Tender247 is a manual login |
| CoS Routine cannot reach the VPS until `MDO_AUTH_TOKEN` + `MDO_SELF_URL` are set in the cloud environment and the domain is allowed | The daily 06:22 run cannot read the ledger |
| Vault import pending (two scp lines + `vault_import.sh`, DEPLOY_HOSTINGER §9) | The two Sunday Routines (memory, finance) have nothing to read |
| backup-offsite Routine not created; `VAULT_BACKUP_PASSPHRASE` unset on the VPS | No weekly bundle, no off-site copy |
| (added 2026-10-09) The five agenda objectives are not yet on the Objectives sheet | A sheet refresh must not drop them until Aman adds them himself |
| (added 2026-10-09) `singhvi` needs `GROK_API_KEY` and the new §8 cron line; its cadence "weekdays 08:05 IST" is not parsed by `mdo_cos.next_due` | CoS heartbeat audit treats it as never-late |
| (added 2026-10-09) VWLR MT/day has no weighbridge/ERP feed | Read from dispatch WhatsApp messages; a day without a message is a gap, not a zero |
| (added 2026-10-09) `hotel_daily` check no longer run by any bot | Night-report parser still fills the table; floor-layout PDF/CAD has no feed |
| (added 2026-10-09) `RECEIVABLE_OVERDUE_DAYS` not in `.env.example` | Default 30 applies |

### 9.2 Stubs and placeholders found in code

| Where | What |
|---|---|
| `mdo_server.py` `/api/positions`, `/holdings`, `/funds`, `/pnl`, `/watchlist`, `/health` | Return empty / zero; `/trading` page and the Aditi Portfolio tab's positions/holdings are therefore empty |
| `mdo_server.py` `/api/feeds/*`, `/api/singhvi`, `/api/singhvi/refresh`, `/api/grok/ask` | Marked `# Feeds (stub — needs Grok)`; return empty lists / a fixed string. `/feeds` page is a shell |
| `mdo_server.py` `/api/stream` | `# SSE stub (keeps frontend happy)` — pings only; the LIVE dot means "backend reachable", not "live data" |
| `mdo-app/app/aditi/page.tsx` | Block deals, corporate actions, FII/DII, global triggers, market calendar, news = hard-coded April 2026 arrays |
| `mdo-app/app/hotel/page.tsx` | `TOTAL_ROOMS = 30` constant; "Backend not yet configured" banner path |
| `seed_mdo_db.py` | 12 entity names flagged `UNVERIFIED — name not found in any source document`; Vedanta CRM stopgap seed; compliance dates April 2026 |
| `mdo_sites.py` | No site sources configured; hostnames inside the two LANs undiscovered (docs/PLAN_VPN_SITE_ACCESS.md Phase 3) |
| `fleet.yaml` `tender-go-no-go.skill: skills/tender-go-no-go.md` | File does not exist; `skills/` contains only `escalation-routing.md` (with ⚠️ blank thresholds — agenda candidate `escalation-thresholds`) |
| `fleet.yaml` `x-watch` | Enabled with a cron command, but DEPLOY_HOSTINGER §8 has no cron line for it, so it is never scheduled |
| `fleet.yaml` `classifier` | `enabled: false` (library helper, never scheduled) |
| `fleet.yaml` `singhvi` (working tree) | Now `enabled: true` via Grok search of written-up calls; the audio path (yt-dlp → Whisper) remains the `/morning` page "Extract" button only, "untested on this VPS" per MDO_VISION §18 |
| `whatsapp_bridge/server.js` | Legacy whatsapp-web.js bridge left in the folder, unused |
| `/api/intelligence/scan` | Runs only when the Daily Briefing page button is pressed — not on any schedule |
| `MDO_VISION.md` §3 | Banker, advocate (§454 matters), site head, hotel GM, COO rows all `[EDIT]` |
| Staah / HDFC OAuth / bank feed / entity register / DIR-3 KYC / Ozone §454 / hotel filings | Listed as **candidates** in agenda.yaml, `confirmed: false` — no bot may act on them |

### 9.3 Things the system deliberately does not do (by constitution, not by omission)

Send email, place or modify an order (`/execute` only records), move money (feed refuses `money` actions), file anything with a regulator, message third parties without a click, write to the Objectives sheet, decide an objective.
