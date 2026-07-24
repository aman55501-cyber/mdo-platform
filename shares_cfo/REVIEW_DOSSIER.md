# Market Console — Review Dossier (for Fable)

**Purpose.** A complete review package for the *Shares CFO / Market Console* — an always-on
personal trading terminal for Indian markets (HDFC Securities + Angel One), deployed to a
Hostinger VPS via Docker + Caddy + autoheal. This document gives you the map and the known
weak spots; the **actual code is in this repo** — read it directly.

- **Repo / branch to review:** `aman55501-cyber/mdo-platform`, branch `claude/shares-cfo-hdfc-setup-wrlqaj`
- **Package:** `shares_cfo/` (~12,100 lines Python + one inline HTML/JS app)
- **Entry point:** `shares_cfo/server.py` (FastAPI, single-process). UI is `shares_cfo/terminal.py` (a self-contained HTML string served at `/`).

Review for: correctness, data integrity, real-time behaviour, execution safety, performance,
maintainability, and the two feature areas called out explicitly below — **Open Interest** and
**Screener data**. Rank findings; propose concrete changes.

---

## 1. Standing constraints (do not propose anything that breaks these)

1. **Every module reports every run** — there is a heartbeat/health feed (`health.py`, `/health.json`, `/status`). Nothing should silently no-op.
2. **Money / orders / signatures wait for an explicit click** — execution is propose→confirm behind a master switch and hard caps. Never auto-fire.
3. **Secrets live in `.env` only** — never logged, printed, or embedded.
4. **Dashboards point at ground-truth files, never copy/invent** — authoritative P&L/cost basis belongs to the CA + ground-truth exports; the app shows live *market* signals, not a rebuilt ledger.
5. **No scraping** (esp. Screener.in — premium CSV export only).
6. Any new data field must be normalised (`normalise.py`) before it is compared to a threshold.

---

## 2. Architecture at a glance

```
Phone / laptop (PWA)  ──HTTPS──▶  Caddy :443  ──▶  FastAPI (uvicorn) :8000
                                                     │
   terminal.py (HTML/JS SPA) ◀── served at "/"       │
                                                     ├─ brokers/  (HDFC async + Angel async + Angel scrip/order)
                                                     ├─ analysis/ (prices, technicals, fundamentals, oi, options, income, scoring…)
                                                     ├─ execution/(guardrails → engine → broker send)
                                                     ├─ stores:   token_store, account_store, balances, tips, persist
                                                     └─ angel_ws.py (SmartWebSocketV2 live ticks)
```

**Core data flow (the consolidated book):** `_consolidated()` in `server.py` fans out to every
account via `_fetch_account()` → `make_adapter()` (HDFC or Angel) → holdings/positions/funds,
merges, caches (stale-while-revalidate ~15s), **persists last-good to disk**, and **freezes after
15:30 IST**. A **quality guard** prevents a degraded fetch (e.g. a broker logged out after a
reboot) from replacing a better book. Positions get live enrichment (LTP/OI) in `_live_positions()`.

---

## 3. Module map (what each file is responsible for)

**Server / UI**
- `server.py` (3,856 lines) — FastAPI app: all endpoints, the consolidated book, live positions, holdings-grouped, chart, ideas, income, reconcile, execution, orders/GTT, tips, balances, health. **This is a monolith — a prime refactor target (see §5).**
- `terminal.py` (1,075 lines) — the entire SPA as an inline HTML/JS string (no build step). Tabs: Portfolio (sector map), Positions, Ideas (Ideas/Calls/Income), Chart, News, Settings. Order ticket, order book, GTT, basket, reconcile panel, advisor-calls channels, account drill.
- `status_page.py` — `/status` proof-of-life page. `health.py` — heartbeat registry.

**Brokers**
- `brokers/hdfc.py` (async read: holdings/positions/funds/ltp + order book), `brokers/hdfc_order.py` (order **write** — NOT probe-verified), `brokers/hdfc_endpoints.py` (paths + candidate order-book paths).
- `brokers/angel.py` (async read adapter), `brokers/angel_scrip.py` (819 lines — scrip master, option/future token resolution, order lifecycle, GTT, quotes/depth, RMS, batch margin, equity LTPs).
- `angel_ws.py` — SmartWebSocketV2 binary tick stream (LTP/volume/close/OI parse).

**Analysis**
- `analysis/prices.py` (OHLCV provider chain: EODHD → Angel candles → yfinance), `technicals.py`, `patterns.py`, `levels.py`, `backtest.py`, `scoring.py`, `fundamentals.py` (Screener export reader), `oi.py`, `options.py`, `income.py` (covered calls / cash-secured puts), `market.py`, `eodhd.py`, `alerts.py`.

**Execution (guarded)**
- `execution/models.py` (OrderRequest + segment awareness), `guardrails.py` (equity + F&O caps), `engine.py` (propose/confirm/place_now + audit).

**Stores / misc**
- `token_store.py`, `account_store.py`, `balances.py`, `tips.py` (advisor calls), `mprofit.py` + `reconcile_live.py` (reconciliation), `deep.py` (per-underlying fundamental+technical+news+macro), `llm.py` (Anthropic narrative), `themes.py`, `config.py`, `normalise.py`, `proactive.py` (background alert agent), `persist.py`.

---

## 4. Open Interest — current state & what's lacking (REVIEW FOCUS)

**What exists:**
- `angel_ws.py` parses OI from the SnapQuote binary (`bytes[131:139]`) into a live tick cache.
- `angel_scrip.option_full()` returns `{ltp, oi, volume, change_pct}` per NFO token (FULL quote).
- `_live_positions()` (server.py) attaches OI to each F&O leg and computes:
  - `_oi_trend()` — OI change vs a *session base*,
  - `_buildup()` — price×OI read (long/short buildup, covering, unwinding),
  - `_leg_bias()` / `_leg_risk()` — directional + risk flags.
- `analysis/oi.py` exists (review it — how much is wired vs latent?).

**Gaps to review / likely improvements:**
- **No day-over-day OI change** — only intra-session base delta. Real OI signals compare to *previous day's* OI. Is there a stored prior-day OI snapshot? (There isn't — should there be?)
- **No PCR (put-call ratio)** and **no OI-across-strikes** view (OI concentration, max-pain, support/resistance from option OI). The option chain is fetched (`_load_options`) but OI isn't aggregated across the chain.
- **Session base is in-memory** — resets on restart; OI trend is wrong for a while after a reboot. Should the base persist (aligns with the book-freeze pattern)?
- **Equity futures OI** shown, but no rollover analytics (OI shift near/far month).
- Is `_buildup` classification validated against a known truth table? Verify the price/OI sign logic.

---

## 5. Screener data — current state & what's lacking (REVIEW FOCUS)

**What exists:**
- `analysis/fundamentals.py` reads a Screener.in premium **Excel/CSV export** (drop-zone upload in Settings). `COLMAP` currently captures: name, market_cap, P/E, ROE, ROCE, **industry_pe** (a number), D/E.
- Powers: high-conviction **Ideas** (`_high_conviction`), **deep analysis** fundamentals, and **market-cap buckets** for holdings-grouped.

**Gaps to review / likely improvements:**
- **No industry/sector NAME captured** — only `industry_pe` (a ratio). This blocks the requested **sub-sector drill** (split the "OTHER" sector tile into Auto Ancillary, Trading, etc.). Adding an `industry` column to `COLMAP` + a `symbol→industry` map would unlock a second drill level. **High-value, low-effort — please confirm the approach.**
- **Thin fundamental set** — no sales/profit growth, promoter holding, pledge %, PEG, interest coverage, cash flow. Ideas scoring (`scoring.py`) is limited by what's read.
- **Coverage gap** — Ideas only exist if a Screener export is uploaded; there's no fallback universe. Is that acceptable, or should there be a bundled default watchlist?
- **Staleness** — no freshness/expiry on the uploaded export; a months-old file silently powers "ideas."

---

## 6. Everything else that may be lacking or fragile (rank these)

**Execution / brokers**
- **HDFC order write is NOT verified** (`hdfc_order.py` — place/cancel/modify are best-guess paths, preview-first). Only Angel order lifecycle is live. Cancel/modify route to Angel; HDFC returns 501.
- **HDFC order-book path is unconfirmed** — `get_order_book()` tries a *candidate list* (`ORDERBOOK_CANDIDATES`); it works in prod but the winning path should be pinned via `HDFC_ORDERBOOK_PATH`.
- **No OCO GTT** (stop+target bracket on a held position) — GTT is single-trigger; advisor-call "Arm GTT" rests only the entry.
- **No equity 5-level depth** — depth is wired for NFO tokens only.

**Data integrity**
- **HDFC F&O `average_price` is wrong at source** — HDFC returns *per-unit unrealised P&L* in that field. `_live_positions()` currently **reconstructs** cost basis heuristically (`real_avg = ltp − field`) for futures, marked `≈`. This is a heuristic, not ground truth — the correct fix is to read the real field (needs the raw HDFC position JSON) or point at a ground-truth export. **Review the heuristic's safety and propose the clean fix.**
- Reconciliation (`reconcile_live.py`) matches order-audit vs broker book, flags naked positions (now GTT-aware) and suspect cost basis. Review the matchers for false-positive/negative risk (symbol matching is token-first, name-fallback).

**Real-time / performance**
- **`server.py` is a 3,856-line monolith** — endpoints, business logic, caching, and rendering-adjacent code all in one file. Propose a module split (routers, services, cache layer).
- **`terminal.py` is a 1,075-line inline HTML/JS blob** — no build, no components, no tests. Is a light componentization or a real front-end build worth it, or does the single-file simplicity win for a solo operator?
- WebSocket (`angel_ws.py`) reconnect/heartbeat robustness; the polling fallback path; the warm-tick cache TTLs.

**Alerts / proactivity**
- `proactive.py` runs F&O move / conflict / health / order-status alerts. **Advisor calls (`tips.py`) have NO alerts** — no push when a call hits its buy zone / stop / accumulation rung. Likely high-value.

**Testing / safety**
- `tests/` exists — assess coverage, especially guardrails, reconciliation matchers, and the freeze/quality-guard logic. The guardrail path and the avg-reconstruction are the highest-risk untested-ish areas.

**UX (in progress)**
- "Everything is a click" pass is partial (sector tiles, holdings, positions, ideas, calls, account drill done; index tiles, numbers→breakdown, order-book/reconcile symbols pending).
- A **desktop cockpit layout** (wide 3–4 column) is proposed but not built.

---

## 7. Questions for you (Fable)

1. **OI:** what's the highest-signal addition — day-over-day OI change (needs a persisted prior-day snapshot), PCR + OI-across-strikes (max pain), or validating the existing buildup logic first?
2. **Screener:** confirm adding `industry` to `COLMAP` + a symbol→industry map is the right way to power the sub-sector drill; and which extra fundamentals most improve `scoring.py` for Indian equities.
3. **Data integrity:** is the `≈` avg reconstruction acceptable as a *labelled trading estimate*, or should the app refuse to show cost basis until a ground-truth export supplies it?
4. **Structure:** is splitting `server.py`/`terminal.py` worth the churn for a single-operator tool, or does the monolith's simplicity win? If split, propose the seams.
5. **Anything we're not seeing** — correctness bugs, race conditions in the cache/WS, or safety gaps in the guarded execution path.

Rank every finding by impact × effort. Concrete diffs welcome.
