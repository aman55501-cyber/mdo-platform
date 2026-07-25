# Life LLM Map — Architecture & Build Roadmap

**What this is:** a live, editable map of the whole "Life LLM" system — every layer
from Aman's life domains down to the surfaces where decisions arrive. It lives at
`/lifemap` in the MDO app, backed by `life_map_nodes` / `life_map_edges` in SQLite.

> None of this data is absolute. Edit nodes, add APIs/MCP servers/skills, and rewire
> connections directly from the UI as the system evolves. `POST /api/lifemap/reset`
> restores the seed.

---

## The 7 layers (left → right = data flow)

| # | Layer | What lives here | Examples |
|---|-------|-----------------|----------|
| 0 | **Principal** | The person the system serves | Aman — operator → architect |
| 1 | **Life & Business** | Domains under management | VWLR, Aditi, Hotel ANS, Compliance, Wealth OS, Family/Legacy, Health |
| 2 | **Data Sources** | Raw signals from the real world | Tender247, WhatsApp groups, Zee Business, HDFC, Yahoo RSS, MCA/GST, Staah |
| 3 | **APIs · MCP · Bridges** | How signals enter the system | FastAPI backend, Grok API, HDFC API, Claude, MCP servers, yt-dlp+Whisper |
| 4 | **LLM Core & Agents** | Engines that think — ideally 24/7 | Daily Briefing Engine, Singhvi Extractor, Business/Capital/Compliance agents |
| 5 | **Skill Library** | Codified playbooks (Tier 1–5) | tender-go-no-go, qglp-graham-screen, monday-master-brief |
| 6 | **Surfaces & Outputs** | Where decisions reach Aman | MDO app, Daily Briefing, Morning Setup, WhatsApp alerts, Monday Master Brief |

**Connecting the layers means:** every domain names its sources → every source has a
connector → every connector feeds an engine → engines run skills → skills publish to
surfaces. A node with no path to Layer 6 is dead weight; a domain with no sources is
flying blind. The map makes those gaps visible.

---

## Step-by-step build order

### Phase 1 — Foundation (done in this branch)
1. ✅ Map data model + CRUD API (`/api/lifemap*`)
2. ✅ `/lifemap` UI — layered columns, connection lines, click-to-edit, add nodes/edges
3. ✅ Seeded from MDO_VISION.md / MDO_INTEL.md

### Phase 2 — Close the connector gaps (highest leverage per hour)
1. **HDFC OAuth callback** → register the VPS/domain URL, run the OTP test (unblocks live execution)
2. **Staah token** → hotel occupancy becomes a live feed instead of manual entry
3. **MCP servers** → connect Gmail / Calendar / Drive / Notion to the agent runtime —
   zero scraping, instant coverage of the Legacy/personal domains
4. **WhatsApp**: decide Meta Business API vs Tasker-webhook (Chromium bridge stays parked)

### Phase 3 — 24/7 autonomous agents (no laptop required)
The key insight: **the agents must run in the cloud, on a schedule, and write their
results into the MDO database** — so findings are waiting in the app/briefing when you
wake up. Three ways to do it, cheapest first:

1. **Scheduled jobs on the Hostinger VPS (already paid for).** Add cron-style loops inside
   `mdo_server.py` (asyncio task or APScheduler) that call Grok/Claude APIs nightly:
   - Business Optimizer: scan tender pipeline + competitor wins → draft bid strategies
   - Capital Optimizer: portfolio drift vs pools, screen runs, Singhvi backtest update
   - Compliance Sentinel: filing calendar across 26 entities → escalate to CA
   Results insert into `intel_items` / `intelligence_alerts` → they surface in the
   existing Daily Briefing automatically.
2. **Claude Code cloud Routines.** Claude Code (web) can run scheduled sessions
   against this repo — an agent with full code + data context that can *change the
   system itself* (write new skills, fix scrapers, refine this map). Good for the
   creative/open-ended work; pair with a fresh-session cron (e.g. nightly).
3. **GitHub Actions cron.** Free tier, runs scripts on schedule, POSTs results to the
   VPS backend. Good fallback if the VPS is busy.

Recommended: start with (1) for deterministic scans + (2) weekly for creative
synthesis (Monday Master Brief).

### Phase 4 — Skills as real artifacts
Turn each Tier 1 skill into a markdown playbook in `skills/` (input → checklist →
output format). Agents load them as prompts; humans read them as SOPs. This is what
unlocks the COO hire.

### Phase 5 — Push surfaces
- WhatsApp / push alerts for 🔴 critical items (agent → phone, unprompted)
- Monday Master Brief page — weekly synthesis of all agent output

---

## Candidate additions (park here until promoted onto the map)
- **Screener.in / Tijori API** — fundamentals for the QGLP screen
- **NSE bhavcopy download** — free EOD data, no session cookies needed
- **Supabase** — swap SQLite when multi-device writes become a problem
- **Hostinger deployment**: see DEPLOY_HOSTINGER.md — VPS replaces Railway (persistent DB, Whisper RAM, Chromium)
- **Notion MCP** — decision log + SOP library synced both ways
- **Telegram bot revival** — cheapest push channel if Meta WA API drags
