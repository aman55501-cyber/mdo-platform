# Life LLM — Status Ledger

**As of:** 17 Aug 2026 · **Last feature commit before this work:** 31 Jul 2026 (`d6b584b`)
**Gap:** 17 days with no feature commits — the time away from the laptop.

> **Verification note.** Everything marked ✅ below is verified by reading the code in
> this repo. What I could **not** verify from this sandbox is whether the VPS itself
> stayed up while you were away — outbound network here is restricted and
> `https://amanagrawal.cloud` was unreachable through the proxy, which proves nothing
> either way. **First thing to do:** open the app on your phone, and run
> `tail -100 /var/log/mdo-agent.log` on the VPS. If the log shows entries through
> August, the reflexes kept running without you — which is the entire point of the
> design. If it stops on 31 July, something needs restarting.

---

## 1. Where it actually stands

Twelve weeks in, the system has a working nervous system and almost no playbooks.
Signals arrive, get classified and reach the phone. What it cannot yet do is *decide*
in your place — because 34 of ~35 skills are unwritten — and it cannot see anything
you personally own or owe.

| Layer | State |
|---|---|
| Ingestion (senses) | **Strong** — WhatsApp ×2, vision, market, news, broker |
| Memory | **Strong** — SQLite, persistent volume, survives redeploys |
| Reflexes (checks) | **Working** — hourly + daily on cron, 10 active / 6 blocked |
| Judgement (Brain) | **Working** — tools over the whole backend, MCP to the phone |
| Playbooks (skills) | **Weak** — 1 of ~35 written |
| Personal coverage | **Absent** — see §4 |
| Site systems | **Built, switched off** — VPN code committed, tunnel never raised |

---

## 2. Done — verified in the repo

**Infrastructure**
- ✅ Hostinger VPS, Docker Compose, off Railway. SQLite on a named volume, survives rebuilds.
- ✅ Six compose services: `backend`, `frontend`, `whatsapp`, `whatsapp2`, `vpn-hotel`, `vpn-vedanta`.
- ✅ Token-gated API (`X-MDO-Key`) with a lock screen; autofill and keyboard mangling fixed.
- ✅ Domain `amanagrawal.cloud` fronted by the existing Caddy.

**Senses**
- ✅ WhatsApp bridge rewritten on Baileys — no Chromium. Two accounts (both phones).
- ✅ Watches **all** groups by default; punctuation-insensitive matching; full history backfill; self-heals after a device unlink by regenerating the QR.
- ✅ Hotel "Daily Sales Report" group parsed automatically into `hotel_daily` — occupancy and RevPAR without manual entry.
- ✅ **Vision pipeline** — reads photographed weighbridge slips, tallies and registers. This is the one that matters most: the site communicates in photographs.
- ✅ Yahoo RSS for 15 watchlist names; Grok live search.

**Capital**
- ✅ **sharecfo bridge live** — `/api/capital/summary` reads all four broker accounts (Aman, Sudha, Ashok on HDFC; Aditi on Angel) through sharecfo's existing authenticated sessions. No second broker auth path was built. Staleness is always reported, never hidden.
- ✅ Threshold flags computed server-side: day move, unrealised P&L, F&O expiry pressure, per-position drawdown, sector concentration.
- ✅ Aditi broker mapping corrected (AngelOne #A1504046 is the firm's; HDFC #4016900 is personal).

**Reflexes and judgement**
- ✅ **Agents moved onto the VPS** (`mdo_agent.py`) after cloud-scheduled sessions kept firing and delivering nothing silently. Hourly + daily on host cron.
- ✅ **Checks registry** — a standing cadence list with per-check sources, thresholds, owners, run windows. `blocked` means the data source does not exist and the agent reports the gap rather than guessing.
- ✅ Hourly agent defaults to silence; only threshold breaches file a report. Daily always files.
- ✅ Agent output budget and boot-race bugs fixed (empty model output, cron firing before the backend was up).
- ✅ **MDO Brain** — Claude with 18 live tools over the backend, plus an MCP mount at `/mcp/<secret>/mcp` so the Claude phone app talks to your own system as a connector.
- ✅ 🔴 alerts push to WhatsApp; Agent Reports page in the app.
- ✅ Auto-generated briefing on the homepage.

**Knowledge**
- ✅ `/lifemap` — the live architecture map, editable from the UI.
- ✅ CA Vimal compliance reconciliation briefing + draft email written.
- ✅ VPN site-access plan — a genuinely rigorous document: requirements, assumption ledger, per-phase acceptance checks.
- ✅ Tier 1 skill **escalation-routing** — the COO-handoff playbook, the one that makes a COO possible.

**Added today (this branch)**
- ✅ Personal-risk and net-worth checks registered as `blocked` (5 new), so the gap is reported monthly instead of being invisible.
- ✅ Seeds now **top up on every boot** instead of only when the table is empty. This was a real bug: the tables were seeded months ago, so any new check or map node added since then would never have appeared on the live VPS.
- ✅ `sharecfo` and the VPN sidecars now appear on the life map — both were live or built and neither was on it.
- ✅ Monthly/quarterly cron lines added to the deploy doc (those cadences had no way to fire).
- ✅ **Live net-worth tracker** — `/networth` page + `networth_snapshots` table + an
  in-process poller through market hours (09:00–15:45 IST Mon–Fri). Stores a point only
  when sharecfo's own `as_of` advances, and reports the **measured** refresh cadence so
  the feasible interval is a number rather than a guess. Verified: `tsc` clean, Next
  build passes, backend boots, all three endpoints answer and degrade honestly when
  sharecfo is absent.

---

## 3. Pending — carrying over from before you left

Ordered by what it costs you to keep not doing.

### 🔴 Blocked on you personally — nobody else can clear these

> **Descoped 17 Aug 2026 on Aman's instruction:** Ozone Steel §454(8) and Rashi Steel
> (CJM Bilaspur 3616/2026). Both are out of the ledger and out of the CA email. Not
> resolved — deliberately not being worked on. Re-add them here if that changes.

| # | Item | Why it is stuck | The one action |
|---|---|---|---|
| 1 | **ITR for FY2025-26 — deadline passed** | 31 July fell while you were away. Aman (individual, with F&O/crypto capital gains), Aditi Investments, ANS Group HUF. | Confirm with the CA whether each was filed. If not, late fee and interest are accruing now. |
| 2 | **Compliance dates are stale** | Seeded April 2026; the daily check flags its own unreliability | Reconcile all 26 entities with the CA — email drafted at `docs/CA_VIMAL_BRIEFING.md` |
| 3 | **Hotel ANS AOC-4 + MGT-7** | Filing currency still "unknown" since April | One question to the CA — already in the drafted email |
| 4 | **Entity register unverified** | ~12 of 26 entity names cannot be sourced from any document | Rebuild the register from the CA's records rather than guessing |
| 5 | **VPN Phase 1 — rotate both certificates** | Both client private keys were transmitted in chat/Drive. Everything else is blocked behind this. | Revoke and reissue in the Omada controllers; delete the Drive copy |
| 6 | **HDFC OAuth OTP test** | Auth wired since April, never run once. See the correction below — auth is only half the gap. | 10 minutes, once, on a weekday morning |
| 7 | **Staah token** | Never fetched from the dashboard | Copy from Staah → `.env` |

### 🟡 Built but never switched on

| Item | State |
|---|---|
| **VPN tunnels (Phases 2–6)** | Compose services, Dockerfile and entrypoint committed 31 Jul. The tunnel has never been raised, the hotel LAN never scanned, `SITE_INVENTORY_HOTEL.md` does not exist. Blocked behind Phase 1. |
| **Singhvi extractor** | Built in April, never live-tested. The VPS has the RAM the free tier lacked — the original blocker is gone and the test still has not happened. |
| **Monthly/quarterly checks** | Cadences accepted by the runner; cron lines added today but not yet installed on the VPS. |

### 🔴 Correction — there is no trade execution to switch on

I described this on 11 Aug as "auth wired, untested". That was too generous, and I only
found the truth when asked to connect it. **No order-placement code exists anywhere in
the repo.**

- `/api/singhvi/execute` moves approved calls from `singhvi_calls` into
  `trading_signals` with `status='pending'`. It never contacts HDFC.
- `/api/trading/signals/{id}/execute` is *bookkeeping*: its own docstring says
  "Called by Capital engine when order is placed" — it records an `executed_price` and
  `order_id` that something else was supposed to have obtained.
- Nothing in the codebase calls an HDFC orders endpoint. `MDO_VISION.md` §12's
  "9:15 AM: Hit **Execute** — orders placed at market open" describes an intention.

So the gap is not one OTP test. It is: (a) get OAuth to succeed once, which is the only
way to learn the real API shapes — note `_hdfc_try_exchange` already tries **four**
different token-exchange payload shapes, which is what code written against unconfirmed
docs looks like; (b) write order placement against the shape that actually worked;
(c) put a dry-run and a confirmation gate in front of it.

**Deliberately not written blind.** An untested order path against a guessed API, moving
real money, is the exact thing the house rule *"money / signature / regulator = Aman's
click"* exists to prevent. Step (a) needs Aman's OTP and cannot be done for him.

### 🟡 Structurally incomplete

| Item | Gap |
|---|---|
| **Skills** | 1 of 10 Tier 1 written. Tiers 2–5 empty. This is what blocks the COO hire and therefore the operator→architect transition — the stated three-year goal. |
| **Bank feeds** | `bank_balances` blocked since inception. Blocks liabilities too. Emailed statements via Gmail MCP is the cheapest channel. |
| **Pools C and D** | Sized "TBD" since April. Net worth cannot be stated without them. |
| **§3 of MDO_VISION** | Banker, advocate, site head, GM Hotel, COO — all still `[EDIT]`. The escalation-routing skill routes to roles that have no names. |
| **Escalation thresholds** | The skill ships with ⚠️ markers where your numbers should be. It is not binding until you fill them. |
| **Monday Master Brief** | Surface marked "building" since April. |
| **NSE block deals / FII-DII** | Parked, no source. |

---

## 4. The blind side — what "Life LLM" did not cover

You asked for business, personal, investments, **car insurance, LIC, and other assets
and liabilities**. Before today the codebase contained zero references to insurance,
LIC, premiums, loans or liabilities — I searched. The system knows your F&O expiry to
the day and does not know whether your car is insured.

Concretely missing:

| Domain | Status |
|---|---|
| Vehicle insurance, PUC, fitness, permits (personal cars **and** the VWLR tippers/loaders) | no register |
| LIC and life cover — premiums due, sum assured vs. actual dependants' need | no register |
| Health insurance — family floater, cover adequacy | no register |
| Fire/marine/plant cover on the washery and hotel | no register |
| Loans, EMIs, OD/CC limits, **personal guarantees** | no register |
| Property, unlisted equity, receivables | no register |
| True net worth (assets − liabilities across 26 entities) | uncomputable |

Two of these are asymmetric risks rather than admin: **a lapsed LIC policy is
unrecoverable value**, and **a personal guarantee with no matching asset cover** is the
single largest undocumented exposure in a group of 26 entities.

**What I did about it today:** created the registers at
[domains/personal-assets-liabilities.md](domains/personal-assets-liabilities.md) and
registered five blocked checks (`insurance_cover`, `lic_policies`, `vehicle_fleet`,
`liabilities_emi`, `networth_rollup`). They will report the gap every month until the
registers are filled. Filling them is an evening with a folder of papers and your
phone camera — the vision pipeline already reads documents.

---

## 5. If you do only three things this week

1. **Get the compliance reconciliation moving.** Items 1–4 above are the only ones on
   this page with a counterparty and a clock — and item 1's deadline has already
   passed. Route: Jahnavi reviews, then it goes to CA Vimal.
2. **Photograph every policy, RC and sanction letter into a Drive folder.** That single
   act unblocks four of the six blocked checks, and the vision pipeline already exists
   to read them.
3. **Write two more Tier 1 skills.** `weekly-operating-review` and `tender-go-no-go`.
   Nothing else moves operator→architect, and the agents get sharper the moment the
   playbooks exist because they load them as prompts.

Everything else — VPN tunnels, Singhvi, Staah — is optimisation. These three are the
system's actual bottlenecks.
