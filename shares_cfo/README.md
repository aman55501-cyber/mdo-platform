# Shares CFO — Stage A (read-only)

Your read-only reconciliation & analysis system. **Stage A** = get one HDFC account
(HDFC1 — Aditi Investments, client code 4016900) reading end-to-end: login → probe →
`/portfolio` shows your real holdings, F&O positions and cash.

> **Safety by design:** this package contains **no order-placement code**. It cannot
> place, modify, or cancel a trade. Execution, if ever built, will live in a
> separate, explicitly-gated module (Stage C) — never in this read path.

---

## What's here

| File | What it does |
|---|---|
| `config.py` | Loads per-account credentials from `.env` (never prints secrets) |
| `brokers/hdfc.py` | Read-only HDFC adapter — correct base URL, **mandatory User-Agent**, `request_token` login, 401→re-login |
| `brokers/hdfc_endpoints.py` | Endpoint paths (best-guess; **corrected by the probe on your PC**) |
| `sectors.py` + `data/sectors.json` | Symbol→sector map (seeded from your 15-stock watchlist). Unmapped tickers are flagged, never silently dropped |
| `normalise.py` | Every field passes here before any threshold compare (kills unit-mismatch false alerts) |
| `server.py` | `/portfolio`, `/health` — consolidated book, net worth, sector concentration, degraded-account flags |
| `../scripts/hdfc_login.py` | Daily browser-2FA login → writes access token to `.env` |
| `../scripts/probe_hdfc.py` | Finds which endpoints work + their JSON shape (GET-only, never trades) |

---

## Run it on your PC — one command at a time

All commands are run from the project root with your venv active
(`.venv\Scripts\activate.bat` on Windows).

**1. Fill in your `.env`** (copy from `.env.example`). Set `HDFC_HDFC1_API_KEY`,
`HDFC_HDFC1_API_SECRET`, and a random `CFO_API_TOKEN`. Leave `HDFC_HDFC1_ACCESS_TOKEN` blank.

**2. Log in (once per day):**
```
python scripts/hdfc_login.py HDFC1
```
*Expect:* your browser opens HDFC's login → do 2FA → accept T&C → you land on a page
whose address contains `?request_token=...`. Copy that whole address, paste it back.
You should see `[OK] Access token saved`. (The token is never printed.)

**3. Probe the endpoints (confirms the real paths):**
```
python scripts/probe_hdfc.py HDFC1
```
*Expect:* a list showing which paths returned `200` and their JSON keys, then
"Suggested edits". If a suggested path differs from what's in
`brokers/hdfc_endpoints.py`, update that one constant to match.

**4. Start the server (binds 0.0.0.0 so your phone can reach it later):**
```
python -m shares_cfo.server
```
*Expect:* `Uvicorn running on http://0.0.0.0:8000`.

**5. See your real book** (new terminal):
```
curl "localhost:8000/portfolio?token=YOUR_CFO_API_TOKEN"
```
*Expect:* JSON with your actual holdings, positions, cash, `net_worth`, and
`sector_concentration`. **That's the Stage A "done" line.**

---

## When the token expires (same-day)

Any read that returns 401 surfaces a plain message: *"Your HDFC session for HDFC1 has
expired … re-login by running: python scripts/hdfc_login.py HDFC1"*. The book degrades
gracefully — `/health` shows `degraded` and `/portfolio` flags the account incomplete,
the run still completes.

## Not yet (later stages)
- Live net-worth dashboard + the 5 app tabs (Stage A UI → B)
- EODHD price/volume feed + Screener fundamentals (Cell 2 / Phase 4)
- US equity (IndMoney) + crypto (SunCrypto/Binance) folded into net worth
- Execution (Stage C) — gated, guard-railed, opt-in
