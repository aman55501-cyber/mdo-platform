# MDO Intelligence File — ANS Group / Aman Agrawal
*Extracted from all chat, code, and document sessions. Last updated: 2026-04-24.*

---

## 1. IDENTITY & PRINCIPALS

| Field | Detail |
|-------|--------|
| Owner | Aman Agrawal, 31 |
| Group | ANS Group, Kharsia, Raigarh, Chhattisgarh |
| CA | Vimal Agrawal — 9755220259 |
| Family | Father: Narendra Agrawal (ANS founders); Sister: Aditi Agrawal |
| Telegram Chat ID | Set in `TELEGRAM_CHAT_ID` env var |

---

## 2. BUSINESS ENTITIES (26 total)

### Active / Core
| Entity | Type | Activity |
|--------|------|----------|
| **VWLR** (exact legal name unknown — see PAN) | Coal Washery | Main ops, Kharsia Raigarh CG |
| **Aditi Investments** | Investment / Trading | Liquid portfolio ₹16–20 Cr, NSE Cash+F&O |
| **Hotel ANS** | Hospitality | Raigarh area |
| **Ozone Steel & Power** | Steel | §454 risk — NO ITR PDF filed (CRITICAL) |
| **Rashi Steel** | Steel | §454(8) CJM Bilaspur Court Case 3616/2026 (CRITICAL) |
| ANS Infra | Construction | — |
| ANS Trading | Trading entity | — |

### Compliance Risk Entities
| Entity | Issue | Severity |
|--------|-------|----------|
| Ozone Steel & Power | §454(8) — ITR not filed as PDF. Risk of strike-off | 🔴 CRITICAL |
| Rashi Steel | §454(8) CJM case no. 3616/2026 Bilaspur court | 🔴 CRITICAL |

### Full 26-entity list: stored in ANS_Group_Data_Capture files on Desktop/MASTER

---

## 3. VWLR — COAL WASHERY (Vedanta Sales Intelligence)

### Identity
- Location: Kharsia, Raigarh District, Chhattisgarh
- Product: Washed coal / coal fines (to power plants, steel mills, cement)
- Main buyers: SECL (South Eastern Coalfields), MCL (Mahanadi Coalfields), NTPC, JSPL, SAIL
- DB: `C:\Users\Owner\Desktop\MASTER\misc\vedanta\vedanta_crm.db`
- CRM code: `C:\Users\Owner\Desktop\MASTER\misc\vedanta\`

### Seed Leads (11 hot prospects)
| Company | Volume | Distance (km) | Priority |
|---------|--------|---------------|----------|
| NTPC Sipat | 50,000 MT/mo | 85 | High |
| JSPL Raigarh | 30,000 MT/mo | 12 | High |
| SAIL Bhilai | 45,000 MT/mo | 140 | High |
| Monnet Ispat | 20,000 MT/mo | 35 | High |
| Chettinad Cement | 15,000 MT/mo | 95 | Medium |
| OCL India | 12,000 MT/mo | 110 | Medium |
| Godawari Power | 25,000 MT/mo | 45 | High |
| Shakti Pumps | 8,000 MT/mo | 180 | Low |
| KSK Energy | 18,000 MT/mo | 65 | Medium |
| SECL | 100,000 MT/mo | 20 | High |
| ACC Cement | 10,000 MT/mo | 125 | Low |

### FOIS Rail Routes (for bid optimization)
| Route | Rate (₹/MT) |
|-------|-------------|
| VWLR → Sipat | ~850 |
| VWLR → Raigarh | ~120 |
| VWLR → Bhilai | ~1,200 |
| VWLR → Nagpur | ~1,400 |

### Bid Optimizer Formula
```
Landed Cost = Washery Gate Price + FOIS Freight + Port/Unloading
Win Probability = f(competitor price, buyer's last 3 tender rates, FOIS route cost)
Target Margin = 12–18% on landed cost
```

### Competitors (33 profiled in DB)
Categories:
- **Tier 1 (Very High threat)**: Large washeries within 100km with SECL/MCL tie-ups
- **Tier 2 (High threat)**: Mid-size washeries 100–200km radius
- **Tier 3 (Medium)**: Small operators, niche routes

Key pricing intel in DB: `competitors` table, `pricing` column

---

## 4. TENDER PORTALS (26 buyer codes)

| Portal | URL | Buyer |
|--------|-----|-------|
| SECL eProcurement | https://secl.cmpdi.co.in | South Eastern Coalfields |
| MCL eProcurement | https://mcl.gov.in | Mahanadi Coalfields |
| NTPC eTender | https://etender.ntpc.co.in | NTPC |
| GeM Portal | https://gem.gov.in | Govt entities |
| CPPP | https://eprocure.gov.in | Central Govt |
| JSPL | https://jspl.com/tenders | Jindal Steel |
| SAIL | https://sailonline.in | Steel Authority |
| NLC India | https://nlcindia.in | NLC |
| Hindalco | https://hindalco.com | Aditya Birla Metals |
| Tata Power | https://tatapower.com | Tata Power |
| *(full 26 in vedanta_crm.db `tender_portals` or `tender_activities` tables)* | | |

---

## 5. ADITI INVESTMENTS — TRADING

| Parameter | Value |
|-----------|-------|
| AUM (liquid) | ₹16–20 Cr (Pool B — liquid) |
| Broker | HDFC Securities InvestRight |
| Strategy | EMA 9/21 + RSI14 + VWAP + Singhvi sentiment |
| Risk/trade | 2% of capital |
| Max positions | 5 |
| Daily loss limit | 5% |
| Target/trade | 3% |
| Stop loss | 1.5% |
| Watchlist | RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK |
| Signals | Anil Singhvi (@AnilSinghvi_ on X) + Grok live sentiment |
| Auto-execute | Toggle via `/autosinghvi on/off` |

### HDFC API
- Base: `https://developer.hdfcsec.com`
- Auth: OAuth2 + OTP (session-based)
- Env vars: `HDFC_API_KEY`, `HDFC_API_SECRET`

---

## 6. GROK / xAI

| Parameter | Value |
|-----------|-------|
| API Key | `GROK_API_KEY` env var |
| Endpoint | `https://api.x.ai/v1/responses` (Agent Tools) |
| Endpoint (plain) | `https://api.x.ai/v1/chat/completions` |
| Models | grok-4 (all tiers — only grok-4 supports server-side tools) |
| Live search tools | `x_search`, `web_search` |
| Note | `search_parameters` DEPRECATED (410 Gone since Jan 12 2026) |

---

## 7. ANS WEALTH OS — 4 POOLS

| Pool | Name | Size | Description |
|------|------|------|-------------|
| A | Operating Business Cash | Operational | Day-to-day business (VWLR, Hotel, etc.) |
| B | Liquid — Aditi | ₹16–20 Cr | NSE trading via VEGA |
| C | Strategic Illiquid | TBD | Real estate, unlisted equity |
| D | Freedom Capital | TBD | Long-term wealth, no-touch |

---

## 8. MDO ARCHITECTURE (5 Layers)

| Layer | Status | Description |
|-------|--------|-------------|
| L1 | ✅ LIVE (108 .md files) | Knowledge base, all decisions |
| L2 | ❌ Not built | Google Sheets — live data capture |
| L3 | ❌ Not built | Make.com automation — triggers |
| L4 | ❌ Not built | Telegram bot — mobile control |
| L5 | 🔄 Building | Railway.app — VEGA + Vedanta bridge |

### MDO Google Sheet (12 tabs)
1. Dashboard (KPIs)
2. VWLR Tenders
3. VWLR Leads (CRM)
4. VWLR Pricing
5. VWLR Competitors
6. Aditi Trading Log
7. Compliance Tracker
8. Compliance Calendar
9. Hotel ANS Ops
10. Group Financials
11. Weekly Brief
12. Contacts

---

## 9. TELEGRAM BOT

- Token: `TELEGRAM_BOT_TOKEN` env var
- Chat ID: `TELEGRAM_CHAT_ID` env var
- Commands registered: 20 (via `set_my_commands`)
- Bot uses `python-telegram-bot` v20+ (async)
- Conflict fix: only one bot instance allowed — `taskkill //F //IM python.exe` to kill

---

## 10. DEPLOYMENT

| Parameter | Value |
|-----------|-------|
| Platform | Railway.app |
| DB mount | `/data/vega_data.db` (persistent volume) |
| Config | `Dockerfile` + `railway.toml` at project root |
| Entry | `python -m vega` |
| Local entry | `cd misc/vega && python -m vega` |

---

## 11. CRITICAL COMPLIANCE FLAGS

### Ozone Steel & Power — §454(8) Risk
- **Issue**: Company has NOT filed ITR as PDF (mandatory for active companies)
- **Risk**: Strike-off by ROC under §454(8)
- **Action needed**: File ITR PDF immediately via CA Vimal Agrawal (9755220259)
- **Status**: UNRESOLVED as of intel extraction

### Rashi Steel — Court Case
- **Case**: §454(8) CJM Bilaspur, Case No. 3616/2026
- **Court**: Chief Judicial Magistrate, Bilaspur, CG
- **Action needed**: Legal counsel + CA Vimal Agrawal response
- **Status**: ACTIVE CASE

---

## 12. KEY FILE PATHS

| File | Purpose |
|------|---------|
| `misc/vega/vega/engine.py` | Main orchestrator |
| `misc/vega/vega/config.py` | Config (pydantic-settings) |
| `misc/vega/vega/telegram_bot/handlers.py` | All Telegram commands |
| `misc/vega/vega/telegram_bot/bot.py` | Bot registration |
| `misc/vega/vega/sentiment/client.py` | Grok API client |
| `misc/vega/vega/sentiment/singhvi.py` | Singhvi monitor |
| `misc/vega/vega/sentiment/portfolio_watch.py` | Portfolio watch agent |
| `misc/vega/mdo_config.json` | MDO mind map (live editable) |
| `misc/vega/vega/vedanta/bridge.py` | Vedanta CRM bridge |
| `misc/vega/vega/vedanta/tender_watch.py` | Real-time tender monitor |
| `misc/vedanta/vedanta_crm.db` | Vedanta CRM SQLite database |
| `misc/vedanta/crm/models.py` | CRM SQLAlchemy models |
| `misc/vedanta/run.py` | Vedanta CLI entry |

---

## 13. UNFINISHED WORK (as of 2026-04-24)

- [ ] HDFC `/testbroker` live test (auth + funds fetch)
- [ ] Railway.app deployment and go-live
- [ ] Vedanta bridge layer → VWLR Telegram commands
- [ ] Real-time tender/auction/compliance Grok monitor
- [ ] Hotel ANS ops module (placeholder in MDO)
- [ ] L2 Google Sheets integration
- [ ] L3 Make.com automation
- [ ] Ozone Steel §454 ITR filing
- [ ] Rashi Steel court case 3616/2026 response
