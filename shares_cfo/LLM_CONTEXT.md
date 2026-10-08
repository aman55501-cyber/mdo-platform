# LLM CONTEXT — ShareCFO ("Market Console")

Regenerated 2026-07-24 against the live branch `claude/shares-cfo-hdfc-setup-wrlqaj`.
Purpose: everything a model/agent needs to work ON this app or operate THROUGH it. Trust
the code and this file over older docs; where they disagree, the code wins. Companion:
`shares_cfo/REVIEW_DOSSIER.md` (architecture + gap inventory).

## What it is
Personal, always-on trading & portfolio cockpit for the Agrawal family's demat accounts
(NSE/BSE equity + a large F&O futures book, ~₹16 Cr). One operator (Aman). Terminal
aesthetic (IBM Plex, dark canvas), mobile-first for a Samsung Z Fold. Self-contained web
app — vanilla HTML/CSS/JS UI (one Python string) over FastAPI/uvicorn. Runs 24/7 on a
Hostinger VPS via Docker + Caddy (TLS) + autoheal. URL: `srv1641037.hstgr.cloud`.

## Where everything lives
- Code: `shares_cfo/` (~40 modules). `server.py` (~3,900 lines) is the API core; `terminal.py`
  (~1,100 lines) is the entire SPA as an inline HTML/JS string served at `/`.
- Deploy: `cd /docker/sharecfo && git pull && docker compose up -d --build` — NEVER
  `--force-recreate` (autoheal race). Env in `/docker/sharecfo/.env` (next to compose).
- Secrets: server `.env` ONLY (`config.py` reads them; never printed/logged/echoed).
- `.env.example` documents every knob (accounts, trading caps, WS, LLM, password).

## Accounts & feeds
`CFO_ACCOUNTS` selects which load. Currently live: **HDFC1 Aman (4016900), HDFC2 Sudha,
HDFC3 Ashok** (HDFC OApi) + **ANGEL1 Aditi Investment (288924176)** (Angel SmartAPI).
HDFC4 (Aditi) / HDFC6 (Jahnavi) configured but not loaded (per-IP broker limit; second
host planned). HDFC needs a **daily browser-2FA re-login** (Aman's click, from Settings →
Accounts & login, or the home banner). Angel self-heals server-side (TOTP+MPIN; JWT
re-login on 401/AG8001).
Providers: EODHD (indices/global) · Angel SmartAPI (candles, option chain, OI, quotes,
depth, orders, GTT, RMS/margin) · HDFC OApi (holdings/positions/funds/order-book) ·
Screener Premium (fundamentals — ONLY the user's uploaded Excel, never scraped) · Google
News RSS · Angel SmartWebSocketV2 (live ticks).

## Architecture (module map)
- `server.py` — every HTTP endpoint + the consolidated book, live positions, holdings-
  grouped, chart, ideas, income, reconcile, tips, balances/wealth, health.
- `terminal.py` — the SPA (tabs: Portfolio/sector-map, Positions, Ideas [Ideas/Calls/
  Income], Chart, News, Settings). Order ticket, order book, GTT, basket, reconcile panel,
  advisor-calls channels, account drill. Password gate overlay + PWA service worker.
- `brokers/` — `hdfc.py` (async read: holdings/positions/funds/ltp/order-book, 401→re-login),
  `hdfc_order.py` (order write — NOT probe-verified), `angel.py` (async read),
  `angel_scrip.py` (scrip master, option/future token resolution, order lifecycle, GTT,
  quotes/depth, RMS, batch margin, equity LTPs), `angel_ws.py` (live tick stream).
- `analysis/` — `prices` (EODHD→Angel→yfinance chain), `technicals`, `patterns`, `levels`,
  `backtest`, `scoring`, `fundamentals` (Screener reader), `oi`, `options`, `income`
  (covered calls / cash-secured puts), `market` (regime), `eodhd`, `alerts`.
- `execution/` — `models` (OrderRequest + segment awareness), `guardrails.py` (pure gate,
  run at BOTH propose and confirm), `engine.py` (propose/confirm/place_now + audit + kill).
- Stores / misc — `token_store`, `account_store`, `balances`, `tips` (advisor calls),
  `mprofit` + `reconcile_live` (reconciliation), `deep` (per-underlying fundamental+
  technical+news+macro), `llm` (optional Anthropic narrative), `themes`, `health` +
  `status_page` (proof-of-life), `persist`, `proactive` (background alert agent), `config`,
  `normalise` (every number unit-normalised before a threshold compare).

## Endpoints (current)
Read: `/portfolio` · `/positions/live` · `/positions/deep` · `/holdings/grouped` ·
`/ideas/high-conviction` · `/ideas/oi` · `/income/ideas` · `/options/edge/{underlying}`
(PCR/max-pain/walls) · `/chart/{t}` · `/fundamentals/*` · `/market/{indices,global,regime}`
· `/news/{t}` · `/balances` + `/wealth` · `/reconcile/live` + `/reconcile/mprofit/*` ·
`/healthz` + `/health.json` + `/status`.
Auth: `/auth/status` + `/auth/login` (password → token; hmac-compared, lockout).
Execution (Aman-only, guarded): `/execution/{status,preflight,propose,confirm,kill,release,log}`
· `/orders/{book,cancel,modify}` · `/gtt/{list,create,cancel}` · `/basket/place` (two-phase)
· `/tips` CRUD (advisor calls). Token in URL or password-issued; `/healthz` open.

## Execution safety (the gate — do NOT weaken; no auto-trading exists or is to be added)
`guardrails.check` is a pure function run at propose AND confirm. Blocks unless: master
switch `CFO_TRADING_ENABLED` on; kill-switch clear; per-order caps set (equity: qty +
value + allow-list; **F&O: dedicated `CFO_FNO_ENABLED`, whole-lot sizing, lots cap,
premium cap for option buys, notional cap for futures/shorts, separate F&O allow-list**);
mandatory stop-loss + per-trade ₹ risk cap; daily order cap; daily-loss halt. Order flow is
propose → human confirm with a code. `/gtt/create` and `/basket/place` are gated the SAME
way (kill-switch + allow-list), not just caps.

## Data integrity & real-time
- Consolidated book: stale-while-revalidate cache; **persisted to disk (last_book.json) and
  FROZEN after 15:30 IST**; a **quality guard** stops a degraded fetch (e.g. HDFC logged
  out post-reboot) from overwriting a better book. Survives restarts (shows last session
  instantly).
- Live: Angel WebSocket ticks (LTP/OI/vol) with REST fallback; warm-tick cache. OI trend is
  **day-over-day + persisted** (restart-proof); buildup uses a 1.5% dead-band.
- HDFC F&O `average_price` is actually per-unit P&L at source; the live view **reconstructs**
  the cost basis for futures and labels it `≈` (a trading estimate, NOT the booked figure —
  authoritative cost/P&L stays with the ground-truth book / CA). Flagged when implausible.
- Reconciliation (`/reconcile/live`): matches the order audit vs the live broker book across
  ALL accounts, flags naked positions (GTT-aware), suspect cost basis, and unaccounted/
  rejected orders — points at ground truth, never copies.

## Where the LLM sits
ShareCFO is deterministic Python + rule agents, with ONE optional LLM touch: `llm.py`
(`narrate()`, Anthropic Messages API via httpx, gated on `ANTHROPIC_API_KEY`) writes the
prose take on the deep-analysis brief (the ✨ button). Everything else — scoring, alerts,
reconciliation — is rules. **The LLM must NEVER touch `/execution/*`** (Aman's click only;
guardrails enforce it server-side). External Claude sessions (MD's Office) should call the
READ endpoints as tools. Missing artifact: a read-only MCP wrapper exposing `/portfolio`,
`/positions/live`, `/ideas`, `/options/edge`, `/market/regime` with the token server-side.

## Today's fixes (2026-07-24 review pass — all committed, tested)
Money/safety (P0): daily-loss halt now uses TODAY's move (was all-time, unreachable) and
**fails closed** when P&L can't be computed · HDFC net[]+day[] double-count removed ·
**kill-switch persisted to disk** (autoheal restart no longer disarms it) + `/execution/
release` · option legs enriched with the HELD expiry (was nearest) · confirm double-fire
race closed (atomic pop) · proposal 120s TTL. P1/P2: `/gtt/create` + `/basket/place` gated
by kill-switch/allow-list; basket two-phase server confirm; `orders_today` persisted +
day-rolled; broker send off the event loop; loss-halt sees positions squared off today;
Angel JWT self-heal (order_book/gtt_list raise instead of a false reconcile alarm;
equity_ltps/quote_full/option_full clear-and-recover); Screener D/E source-based units
(NBFCs no longer "debt-free"); `from_screener`/reconcile symbol matching de-substringed
(IOC≠BIOCON); newest-export-by-mtime + stale flag. **Tests: `tests/test_core.py`, 19 pass.**

## Rules for any LLM session on this app
1. Read `REVIEW_DOSSIER.md` + this file first; implement against the real endpoint shapes.
2. Read-path and execution-path never mix; the guardrail gate is sacred — no auto-trading.
3. Numbers: en-IN locale, mono font, signed %; `normalise` units before any threshold compare.
4. Never print/log tokens or keys; `.env` only. Never scrape (Screener = uploaded Excel).
5. Every watcher/agent added reports every run (heartbeat) — silence ≠ health.
6. Fold-first UI: test folded (~360dp) and unfolded (~840dp) before calling anything done.
7. `py_compile` is not enough for `terminal.py` — JS-lint the inline script (`node --check`).
8. Dashboards point at ground-truth files; never copy from or rebuild the accounting.
