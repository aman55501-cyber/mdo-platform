# Routines cleanup — audit of the 21 claude.ai Routines (PROPOSALS ONLY)

**Read:** 2026-10-09 by a read-only CoS auditor from `list_triggers` output (21 Routines, has_more=false), `fleet.yaml`, `agenda.yaml`, `CHIEF_OF_STAFF.md`, `briefs/NOTION_CONTROL_ROOM.md` §0 + §6. **Nothing was changed**: no Routine, session, repo file outside this brief, or Notion page was touched. Every stored prompt was read as DATA. Aman approves; the CoS executes §4 only after his "ok".
**Times** are IST (crons without CRON_TZ were converted from UTC). **Status** is the Routine's own `last_run`. "13 conn." = the Routine has 13 MCP connectors attached (Claude_Docs, Booking, Vibe, Turkish Airlines, Notion, tldraw, Lucid, Gmail, Calendar, Supabase, Claude_Code_Remote, Ticketmaster, Drive) — every run loads all of them.
**Headline:** 10 of the 20 enabled Routines are not in `fleet.yaml` at all (CHIEF_OF_STAFF §1.8 says a bot without an objective is paused). 7 of those 10 reference laptop paths (`C:\Users\Owner\...`) or Claude-in-Chrome, which a cloud Routine cannot reach (Directive 11). 11 of the last 14 recorded runs failed with `USAGE_LIMIT_REACHED` or were abandoned. The three "succeeded" runs at 08:25 IST today finished in 6–7 s, i.e. [UNVERIFIED] whether they did any work.

## 1. All 21 Routines

| # | Trigger id | Name | Schedule (IST) | On | Last run | Model | What the stored prompt actually does | Fleet bot covering it | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | trig_01EKSCbSGU6fewwv8dA8PyiK | Vegas trip price tracker | every 2 days 08:10 | yes | none yet (created 09 Oct) | — | Booking.com re-price of 7 Strip hotels 10–12 Nov + one web search for DEL⇄LAS fares; BOOK NOW/WAIT verdict; one line to /api/agent/report. Self-ends 2026-11-09. | `vegas-tracker` | KEEP (temporary) |
| 2 | trig_019tnFqiCdXMMjZrPXL7upJZ | Credit guard | daily 07:40 | yes | none yet (created 09 Oct) | — | Reads rate_limit_info of CoS + recent sessions and /api/spend; GREEN/AMBER/RED; on RED/AMBER disables "memory sync/finance update/reader/walkthrough" Routines via update_trigger, re-enables on GREEN; one line. | `credit-guard` | KEEP |
| 3 | trig_01H2u2CccEZ2X6EX1UxSySd4 | Grok inbox relay | 09:25 Mon–Sat | yes | FAILED usage-limit 09 Oct 09:26 | — | Gmail: unread [GROK-TENDER]/[GROK-SINGHVI] → POST tender-inbound and /api/singhvi/calls (pending only) + /api/grok/memory; marks mail read; heartbeat. | `grok-relay` | KEEP (failing on credits, not design) |
| 4 | trig_017XfzhW7zXZMrQdaygMMwGm | Backup off-site | Sun 07:46 | yes | none yet | — | GET /api/vault/backup/latest with VAULT_TOKEN, upload unchanged to Drive "MDO Backups", never decrypts; one line heartbeat. | `backup-offsite` (fleet says 08:00 and `fleet_gaps` says "not yet created" — both stale) | KEEP; fix fleet.yaml cadence/gap |
| 5 | trig_01JrusKh5mH1JTuVyAw91gHQ | Weekly finance update (cloud, vault) | Sun 08:30 | yes | none yet | — | GET Family_Finance_Master.xlsx from vault, Gmail 8-day search of bank/broker/dividend senders, openpyxl append WeeklyLog/MonthlyBalances/Holdings, PUT back; gaps listed; push. | `weekly-finance-update` (serves `[]`) | KEEP; Aman to name the objective it serves |
| 6 | trig_01VCqGPK8XSC82hp8eqDy2DN | Chief of Staff morning run | daily 06:22 | yes | FAILED usage-limit 09 Oct 06:22 | claude-fable-5-1 | Clones repo, reads constitution/agenda/fleet, mirrors Objectives sheet, ledger read, heartbeat audit → cos_jobs, Gmail tender sweep, advances confirmed objectives, roll-up via /api/agent/report, COS_LOG line. | `cos` | KEEP |
| 7 | trig_01Dubtj6wfDvKZkYjHJLe5uJ | Daily Share Master refresh | 09:25 Mon–Fri | yes | FAILED usage-limit 09 Oct 09:25 | claude-sonnet-5-5 | Supabase `aman-control-room` SQL (share_master, share_summary, desk_ideas) → rebuilds JSON in artifact 9QTARJGxwAD5ueRyR7RiXq, CAP>12%/L15/L30 flags; republish; push. 13 conn. | `share-master-refresh`; overlaps `capital-watcher` (same accounts, thresholds) | REWRITE now (Supabase+Artifact only, drop 11 connectors); MERGE INTO `capital-watcher` after gap G9 |
| 8 | trig_014pctpK3faTkHhJqco1Y6YJ | Weekly finance update (laptop — retired) | Sun 08:30 | **no** | none | — | Laptop twin of #5: edits `C:\Users\Owner\claude master\finance\...xlsx`, Chrome to download PDFs. Disabled 08 Oct, history kept. 13 conn. | `weekly-finance-update` (notes) | KEEP disabled (delete only on Aman's word) |
| 9 | trig_01E3cCjuc9x35eYPvwtoWbQA | Weekly memory sync | Sun 07:30 | yes | none yet | — | Lists/reads memory/*.md in vault, "reviews the week's Cowork and Claude Code sessions", writes corrected facts + _log.md via /api/vault/put; push. 13 conn. | `weekly-memory-sync` | REWRITE: step 2 reads past sessions every week — breaks Directive 15; drop it, vault + bot_memory proposals only, cheapest model, Claude_Code_Remote connector only |
| 10 | trig_01D25Vq4AcbfWVfjkwW8sm8k | Life OS weekly review | Sun 08:00 | yes | none yet | — | Notion read-only: 6 Life OS databases → warm "Weekly Review" digest for Aman & Jahnavi. 13 conn. | `life-os-weekly-review` | KEEP; trim to Notion connector only |
| 11 | trig_012HF78NLzKwVfd29ZYtnhCT | Fno daily report | 08:45 Mon–Fri | yes | FAILED usage-limit 09 Oct 08:45 | — | Calls a portfolio connector (HDFC Sky ×2 + Angel) health/portfolio/alerts; F&O P&L by expiry, expiry≤7d and LTP<30% flags, "LAP scorecard" vs interest hurdle; quarterly XIRR tripwire appended to `C:\...\_memory\topics\investing.md`. 13 conn. | `capital-watcher` (acct_positions, fo_update, hourly in market hours) | PAUSE (failing + laptop path; replace by `capital-watcher`) — gap G5 first recorded, not blocking |
| 12 | trig_01P4GPRqjkfR3udsha2wRh3m | Post close analyst wrap | 16:00 Mon–Fri | yes | FAILED usage-limit 08 Oct 16:08 | — | Drive KB docs + Chrome web gather: index close, FII/DII, coverage movers, coal/steel/power read-through "to VWLR and Rashi Steel & Power" (known fabrication, Notion brief §0.7); Gmail DRAFT to Aman. 13 conn. | `capital-watcher` (crude/global watch, window ends 15:35) + `x-watch` (market posts to 22:00) | PAUSE (failing; cites a fabricated entity; replace by `capital-watcher` + gap G6) |
| 13 | trig_01XKof3kBk3qjJbr1bZwMSoL | Investment book refresh | daily 18:45 | yes | SUCCEEDED 09 Oct 08:25 (7 s) | — | Claude-in-Chrome login to MProfit (autofill), captures 9 portfolios into `C:\...\BUSINESSES\investment-pnl\CAPITAL_ALLOCATION.xlsx`; ingests Downloads bank/MProfit/Binance files into recon workbooks. 13 conn. | none (laptop-bound); `weekly-finance-update` is the cloud finance record | PAUSE (laptop/Chrome only; a 7-second "success" from the cloud did no work [UNVERIFIED]) — gap G7 |
| 14 | trig_012pm9KgE69hpbGAgJjUTgQz | Daily networth tracker | daily 07:00 | yes | SUCCEEDED 09 Oct 08:25 (6 s) | — | Reads newest "Portfolio/MProfit" file in Drive, holds PPF/Bank/LAS constants, appends a row to `C:\Users\Owner\Downloads\ANS_Group_NetWorth_Tracker.xlsx`; 3-line report. 13 conn. | `weekly-finance-update` (NetWorth sheet in the vault workbook) | MERGE INTO `weekly-finance-update` (laptop workbook; duplicate) |
| 15 | trig_01QniskFFvExtnymrhXCEVUQ | Md morning brief | daily 06:30 | yes | SUCCEEDED 09 Oct 08:25 (6 s) | — | Reads `C:\...\_memory\CLAUDE.md`, checklist xlsx (deadline 22-Jul-2026), Supabase `vwlr-tender-map` rows, web market cues; heartbeat + needs-click + progress widget + "THE ONE THING". 13 conn. | `cos` 06:22 + `daily-brief` 06:57 + AMAN_PENDING.md (Directive 16) | PAUSE (duplicate; laptop paths) — gap G3 |
| 16 | trig_01Y6o2e7esSVWNR2BaqWbM8S | Hotel cv drive watch | daily 18:00 | yes | FAILED usage-limit 08 Oct 18:06 | — | Hotel ANS hiring analyst: new CVs in a Drive folder → role fit/verdict/locality, web-verifies employers, DOCX batch + "Candidate Master — LIVE" CSV for Jahnavi; state file under `C:\Users\Owner\AppData\...`. 13 conn. | none; hotel objective = renovation + Guptasons contract only (agenda 2026-10-09) | PAUSE (no confirmed objective, §1.8) — Aman decides if hotel hiring is live (B) |
| 17 | trig_014uK3FxZr7fgePJEx2vraaK | Vedanta tender daily scan | daily 08:00 | yes | FAILED usage-limit 09 Oct 08:25 | — | 15k-char prompt: Claude-in-Chrome over coalindiatenders/SECL, CG eProc, NTPC, CPPP(NALCO), GeM + Tender247 analytics; 3-gate match (coal-logistics scope · hard excludes · CG haul radius); upserts `tender_candidates` in Supabase `vwlr-tender-map` (feeds the Android tender-map app). 13 conn. | `tender-go-no-go` 08:00 + `x-watch` + `grok-tasks` (T247) + `grok-relay` | PAUSE (failing; browser-bound, cannot run in cloud; replace by `tender-go-no-go`) after gap G4 |
| 18 | trig_01VEXwqvcG2TxY3jUr5qtRH4 | CoS · Singhvi levels capture | 09:05 Mon–Fri | yes | FAILED usage-limit 09 Oct 09:05 | claude-opus-5 | zeebiz.com fetch of Singhvi's Nifty/BankNifty zones, stocks of the day, F&O ban, macro; INSERT into Supabase `wa_outbox` (bridge dead since 23 Sep per Notion brief) + Notion Desk Digest section. 13 conn. | `singhvi` (grok-4, 08:05) + `grok-tasks` 09:10 + `grok-relay` | PAUSE (triple duplicate; dead delivery channel) — gap G8 |
| 19 | trig_01NMEWQ7VLjwALw7c12a7rgA | CoS 3 · Weekly review | Sun 20:00 | yes | ABANDONED 04 Oct 20:05 | claude-opus-5 | Supabase wa_messages/events 7d, Notion Open Items/CoS Board/Deal Room/Botanicals, Gmail; writes Notion "Weekly Review" page, CoS Board §1, wa_outbox, events heartbeat; "kill any desk silent 7 days". 13 conn. | `business-pulse` Sun 07:00 + CoS Sunday hygiene (§9) | PAUSE (duplicate; abandoned) — gap G10 → janitor |
| 20 | trig_014bvzEvNdBQoXydxwEwYRDX | CoS 2 · Hourly sweep | hourly 08:00–21:00 daily | yes | SUCCEEDED 09 Oct 12:11 (2m48s) | claude-opus-5 | Every hour: wa_outbox/bridge health, executes "CoS …" self-chat commands, Open Items decisions, 75-min WhatsApp window, push rules, two-leg delivery (wa_outbox + PushNotification), Notion digest + heartbeat, events row. Source mirror logged out since 08 Oct 08:15 (Notion brief §0.2). 13 conn. | `ops-hourly` + `wa-classifier` + `wa-intel` + `cos_jobs` reply routing | PAUSE (duplicate; 98 opus runs/week against a dead feed) — gaps G1, G2 |
| 21 | trig_01HnWGTkT7uro7Q8sDZX68yy | CoS 1 · Morning brief | daily 07:00 | yes | FAILED usage-limit 09 Oct 07:08 | claude-opus-5 | 24h wa_messages digest, Mausaji calls through QGLP, commands, Notion Open Items, Gmail (Vimal, marriott/fern, "VEDANTA DAILY REPORT"); writes CoS Board §1, Desk Digest, wa_outbox brief, events. 13 conn. | `cos` 06:22 + `daily-brief` 06:57 | PAUSE (duplicate; failing) — gaps G3, G11 |

## 2. Credit burn (runs per week from the cron; count only, enabled Routines)

| Runs/wk | Trigger id · name | Note |
|---|---|---|
| **98** | trig_014bvzEvNdBQoXydxwEwYRDX CoS 2 · Hourly sweep | **#1 consumer.** 14 fires/day × 7, claude-opus-5, 5.6k prompt, 13 connectors, ~3 min each. Half of all fleet fires. |
| 7 | trig_014uK3FxZr7fgePJEx2vraaK Vedanta tender daily scan | **#2 consumer.** 15k prompt, 5 portals via browser, Supabase writes, 15-min runtime cap; browser never attaches in the cloud. |
| 7 | trig_01HnWGTkT7uro7Q8sDZX68yy CoS 1 · Morning brief | **#3 consumer.** claude-opus-5, 5 sources, 3 Notion writes + SQL, 13 connectors. (Hotel CV watch is a close 4th: 7.8k prompt, web verification, DOCX.) |
| 7 each | trig_01VCqGPK8XSC82hp8eqDy2DN CoS morning run · trig_019tnFqiCdXMMjZrPXL7upJZ Credit guard · trig_01XKof3kBk3qjJbr1bZwMSoL Investment book · trig_012pm9KgE69hpbGAgJjUTgQz Networth · trig_01QniskFFvExtnymrhXCEVUQ Md morning brief · trig_01Y6o2e7esSVWNR2BaqWbM8S Hotel CV watch | |
| 6 | trig_01H2u2CccEZ2X6EX1UxSySd4 Grok inbox relay | |
| 5 each | trig_01Dubtj6wfDvKZkYjHJLe5uJ Share Master · trig_012HF78NLzKwVfd29ZYtnhCT Fno daily · trig_01P4GPRqjkfR3udsha2wRh3m Post close · trig_01VEXwqvcG2TxY3jUr5qtRH4 Singhvi levels | Share Master and Grok relay both fire at 09:25 — two sessions at the same minute. |
| 3.5 | trig_01EKSCbSGU6fewwv8dA8PyiK Vegas tracker | ends 2026-11-09 |
| 1 each | trig_017XfzhW7zXZMrQdaygMMwGm Backup · trig_01JrusKh5mH1JTuVyAw91gHQ Finance (cloud) · trig_01E3cCjuc9x35eYPvwtoWbQA Memory sync · trig_01D25Vq4AcbfWVfjkwW8sm8k Life OS · trig_01NMEWQ7VLjwALw7c12a7rgA CoS 3 | Sunday 07:30–08:30 stack: 4 Routines + VPS business-pulse 07:00 |
| 0 | trig_014pctpK3faTkHhJqco1Y6YJ Finance (laptop) | disabled |
| **≈196 total** | | §4-A alone removes **152/wk (78%)**; what remains is ≈44/wk, 7 of them on the CoS model. |

## 3. Duplication map — three CoS systems

Systems: **(a)** Notion Grok desks (Aman's Grok account, hourly check-ins into Notion); **(b)** the cloud "CoS 1/2/3" loop + the pre-fleet Routines (#11–#18 above) on Supabase `aman-control-room` / `vwlr-tender-map` + the "CoS box" PC; **(c)** the VPS fleet (`fleet.yaml`). Default keep = (c), per Aman's direction (Notion brief §6 P1). "Legacy does that fleet does not" is written as a `fleet_gaps` entry so nothing of value is lost.

| Function | (a) Grok desks | (b) cloud loop / old Routines | (c) VPS fleet — KEEP | fleet_gaps entry (what the legacy copy does that (c) does not yet) |
|---|---|---|---|---|
| WhatsApp ingest | reads Notion digest | CoS 1/2 read Supabase `wa_messages` (CoS box, logged out 08 Oct) | wa bridges + `wa-classifier` + `wa-intel` | **G1** Free-text "CoS …" commands Aman types in his self-chat are executed and marked done by CoS 2; the fleet only routes `ok N`/`no N` replies (§4). Add a `command` intake to the bridge → cos_jobs. |
| Hourly ops anomalies | Ops Sync desk re-reads rows | CoS 2 push rules + two-leg delivery | `ops-hourly` (15,000 MT, idle equipment, breakdown) | **G2** (i) "anyone in a group asking for Aman by name" and "wrong material in boxes / claim risk" are not ops-hourly triggers; (ii) no fallback leg when the WhatsApp bridge is down — CoS 2 used PushNotification. Add both to `ops-hourly` / backend push. |
| Morning brief | CoS Board heartbeat; Today page (dead) | CoS 1 07:00; Md morning brief 06:30 | `cos` 06:22 + `daily-brief` 06:57 | **G3** (i) Gmail subject "VEDANTA DAILY REPORT" is a candidate dispatch-MT feed (closes the "no weighbridge/ERP feed" gap) — daily-brief reads WhatsApp only; (ii) a single closing "THE ONE THING" line in the roll-up. |
| Tenders | Tender Intelligence desk + Grok T247 login | Vedanta tender daily scan → `tender_candidates` → Android map app | `tender-go-no-go` + `x-watch` + `grok-tasks` + `grok-relay` | **G4** Port the 3-gate match logic (primary scope = coal logistics/RCR/handling/supply · hard excludes · CG + border-district haul radius) and the explicit portal list (coalindiatenders.nic.in, eproc.cgstate.gov.in, ntpctender.ntpc.co.in/Index/Search, eprocure.gov.in→NALCO, bidplus.gem.gov.in) into `skills/tender-go-no-go.md`; add a reject-trail (reject_reason) to `/api/vwlr/pipeline` so junk is not re-reviewed; decide what the Android tender-map app reads once Supabase goes (G12). Tender247 analytics (hearted-tender stage changes, competitor deltas) → `grok-tasks` task 3. |
| Capital / F&O | Capital Guard, Investment desks | Fno daily, Post-close wrap, Share Master, Investment book, Networth | `capital-watcher` + `share-master-refresh` + `weekly-finance-update` | **G5** LAP interest-hurdle scorecard (MTD realised F&O P&L vs loan interest; figures live only in the stored prompt, [UNVERIFIED]), expiry ≤7 d and LTP <30% of avg flags, quarterly XIRR tripwire → `capital-watcher` rules, Aman to confirm the numbers. **G6** No post-close line (index close, FII/DII, tomorrow's results/ex-dates): extend `capital-watcher` with one 16:00 run. **G7** MProfit per-portfolio values and bank-flow/capital-gains recon have no cloud source: candidate = MProfit export emailed/dropped into vault `finance/`. **G9** `share_master`/`desk_ideas` live in Supabase; move to VPS, then fold the Share Master page into capital-watcher's output. |
| Singhvi / stock tips | Singhvi ST desk (failed 07 Oct), Stock Tips desk | Singhvi levels capture; CoS 1/2 Mausaji QGLP | `singhvi` (grok-4) + `grok-tasks` + `grok-relay` | **G8** Index level zones (Nifty/BankNifty support/sell zones, PCR, F&O ban list, GIFT/crude/rupee) are context, not calls; add as a non-proposal context line to `singhvi`. Bantu Mausaji's calls + QGLP screen serve no confirmed objective → list as a candidate, not a gap. |
| Hotel | Hotel Deal Room desk (brand shopping, superseded) | Hotel CV drive watch | `hotel-daily` | none unless Aman confirms a hiring objective; Deal Room DBs stay the human record (Notion brief P6). |
| Compliance | Compliance CA Legal desk + Compliance & Renewals DB | CoS 1 Gmail watch on CA Vimal; CoS 3 14-day deadlines | `compliance-sentinel` (serves `[]`) | **G11** No Gmail watch for CA Vimal's mails in the fleet; the 30 Sep statutory bundle recorded overdue in Notion is unknown to the sentinel; `serves:` needs an objective from Aman. |
| Decision surface | Open Items "Needs Aman click" (20 rows, 0 clicks since ≥02 Oct) | CoS 1/2 write Open Items + wa_outbox | cos_jobs + WhatsApp 🖐 #N + AMAN_PENDING.md | covered by Notion brief P2/P5 (`notion-mirror` bot; one-time import of the 20 rows). |
| Weekly review | Weekly Review 22 Sep (once) | CoS 3 Sun 20:00 | `business-pulse` + CoS Sunday §9 | **G10** "Automation runs vs expected + kill anything silent 7 days" → the `janitor` bot (§5). |
| Memory | Manual §7 knowledge base | Weekly memory sync (reads sessions) | vault memory/ + `bot_memory` proposals | rewrite #9; Manual §7 facts enter as `bot_memory status: proposed` (P8). |
| Data spine | Notion DBs | Supabase `aman-control-room` + `vwlr-tender-map`; CoS box PC | VPS SQLite + `/api/*` | **G12** Two Supabase projects outside `fleet.yaml`; retirement steps in §4-S. |

## 4. Action list for the CoS — after Aman's "ok" (nothing below is done)

**A) Safe to pause now** (failing, laptop/browser-bound, or pure duplicates of a running fleet bot; nothing currently delivered is lost):
- disable trig_014bvzEvNdBQoXydxwEwYRDX (CoS 2 · Hourly sweep) — 98 opus runs/wk on a logged-out feed; `ops-hourly`/`wa-intel` cover it
- disable trig_01HnWGTkT7uro7Q8sDZX68yy (CoS 1 · Morning brief) — duplicate of `cos` + `daily-brief`; failing
- disable trig_01NMEWQ7VLjwALw7c12a7rgA (CoS 3 · Weekly review) — duplicate of `business-pulse`; abandoned 04 Oct
- disable trig_01VEXwqvcG2TxY3jUr5qtRH4 (CoS · Singhvi levels capture) — third Singhvi copy; writes to a dead wa_outbox
- disable trig_01QniskFFvExtnymrhXCEVUQ (Md morning brief) — laptop paths; duplicate
- disable trig_012pm9KgE69hpbGAgJjUTgQz (Daily networth tracker) — laptop workbook; merge into weekly-finance-update
- disable trig_01XKof3kBk3qjJbr1bZwMSoL (Investment book refresh) — Chrome/MProfit/laptop only
- disable trig_01P4GPRqjkfR3udsha2wRh3m (Post close analyst wrap) — failing; cites "Rashi Steel & Power"
- disable trig_012HF78NLzKwVfd29ZYtnhCT (Fno daily report) — failing; laptop memory path; `capital-watcher` covers
- then: copy each disabled prompt verbatim into `briefs/legacy_prompts/` (history kept, Directive 7), add G1–G8, G10 to `fleet_gaps`, add the 10 unregistered Routines to COS_LOG as "paused 2026-10-xx on Aman's ok".

**B) Pause after a gap is closed or Aman decides:**
- disable trig_014uK3FxZr7fgePJEx2vraaK (Vedanta tender daily scan) — after G4 (3-gate logic + portals in `skills/tender-go-no-go.md`, reject trail, Android-app source decided). It cannot run in the cloud today, so pausing earlier loses nothing but the prompt text, which step A archives.
- disable trig_01Y6o2e7esSVWNR2BaqWbM8S (Hotel cv drive watch) — after Aman answers once: is Hotel ANS hiring a live objective? "no" → pause; "yes" → add it to agenda.yaml + fleet.yaml and REWRITE without the `C:\` state file (Drive sheet as state).
- disable trig_01Dubtj6wfDvKZkYjHJLe5uJ (Daily Share Master refresh) — after G9 (share_master/desk_ideas on the VPS, page fed by `capital-watcher`). Until then: REWRITE to Supabase + Artifact connectors only.
- REWRITE (not pause) trig_01E3cCjuc9x35eYPvwtoWbQA (Weekly memory sync) — remove "review the week's sessions" (Directive 15), cheapest model, one connector.

**C) Keep:** trig_01VCqGPK8XSC82hp8eqDy2DN (Chief of Staff morning run) · trig_019tnFqiCdXMMjZrPXL7upJZ (Credit guard) · trig_01H2u2CccEZ2X6EX1UxSySd4 (Grok inbox relay) · trig_017XfzhW7zXZMrQdaygMMwGm (Backup off-site; fix fleet.yaml to 07:46 and drop the stale gap line) · trig_01JrusKh5mH1JTuVyAw91gHQ (Weekly finance update, cloud) · trig_01D25Vq4AcbfWVfjkwW8sm8k (Life OS weekly review; Notion connector only) · trig_01EKSCbSGU6fewwv8dA8PyiK (Vegas tracker, to 09 Nov) · trig_014pctpK3faTkHhJqco1Y6YJ (laptop finance — stays disabled).

**Notion pages to mark "superseded by the VPS fleet on <date>"** (one line added at the top; pages are never deleted; Notion brief P3/P4):
- CoS Board — use this daily (§0 header + heartbeat lines) https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618
- WhatsApp Feed — Desk Digest https://app.notion.com/p/3e3f1a9b6dc2815d9ddded6e6ec838ac
- Today https://app.notion.com/p/3c4f1a9b6dc281778879c7bfe2a3fbc0
- Grok Desks — Operating Manual https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f (and §1 rewritten to point at /api/cos/tender-inbound if any desk survives)
- Grok → Claude CoS relay https://app.notion.com/p/3e4f1a9b6dc2815fa382c570e99cdbb6 · Claude CoS Handoff https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 · Weekly Review 22 Sep https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881
- Singhvi Levels — Zee Business https://app.notion.com/p/3e3f1a9b6dc281cd8286fbbea681e5e9
- Staying ahead (Fern route plan) https://app.notion.com/p/3c4f1a9b6dc281259603ce02d61fdc13
- MD Console · Open Items https://app.notion.com/p/97027ae37bc54e44bae6d739cb871542 — only after the P5 one-time import of the 20 "Needs Aman click" rows into cos_jobs.
- Not superseded (fleet reads them): ANS Route — Deal Room + its 3 DBs, Entities & Businesses, Life OS, Compliance & Renewals (as mirror).

**S) Supabase spine retirement — proposals, each its own Aman click (pause is reversible; nothing is deleted):**
- S1 Inventory both projects read-only: `aman-control-room` (wa_messages, wa_outbox, events, share_master, share_summary, desk_ideas, holdings_latest) and `vwlr-tender-map` (tender_candidates, tenders, locations). Row counts + last write per table → one line each in the ledger. Project refs stay in the stored prompts, not in this repo.
- S2 Stop the writers: §4-A pauses CoS 1/2/3 + Singhvi levels; Aman switches off the "CoS box" PC bridge (Directive 11). Confirm zero writes for 7 days.
- S3 Export `share_master` + `desk_ideas` to the VPS (`/api/capital/*` or vault `finance/`), rewire `share-master-refresh` (G9).
- S4 Export `tender_candidates` → `/api/vwlr/pipeline` with reject_reason; Aman decides whether the Android tender-map app is kept (then it needs a VPS read endpoint) or retired.
- S5 Final full dump of both projects into the vault (`finance/archive/supabase-<date>/`), covered by the weekly encrypted bundle + backup-offsite.
- S6 `pause_project` on both (reversible) — Aman's click; delete never proposed. Add "Supabase spines paused <date>; restore = unpause" to COS_LOG and `fleet_gaps` G12.

## 5. Proposed `janitor` bot charter (for fleet.yaml, pending Aman's ok)

```yaml
- id: janitor
  name: Weekly janitor (Routines · dead bots · duplicate jobs · stale clicks · disk/spend)
  runs_on: cloud-routine
  cadence: weekly Sun 09:10 IST   # after housekeeping 03:00, business-pulse 07:00, backup 07:46, finance 08:30
  model: cheapest available (Aman decides; proposed claude-haiku-5-5)
  heartbeat: 'one line every run: "janitor: R routines (F failing, D dup, U unregistered) · B bots missed slot · J dup jobs · N Needs-Aman-click rows >7d · disk X% · spend ₹y of cap · P proposals"'
  serves: [all]
  enabled: false   # Aman flips it
  charter:
    purpose: Nothing runs twice, nothing runs dead, nothing waits on Aman unseen, nothing fills the disk or the wallet quietly.
    thinks: Read-only auditor. A Routine not in fleet.yaml, a Routine failing 3 runs running, two Routines or a Routine and a VPS bot doing the same job, a bot with serves [] or a missed slot, a Needs-Aman-click row older than 7 days, disk under 20% free or spend over 80% of cap — each is one proposal line. It never decides.
    works: 'Sun 09:10 IST. list_triggers (name, cron, enabled, last_run) vs fleet.yaml; /api/fleet missed flags; /api/cos/jobs?status=needs_choice age; Notion Open Items Decision=Needs Aman click via the Notion connector (read); /api/spend; housekeeping''s last disk line from /api/agent/reports. ≤12 tool calls. Writes one job per proposal (kind proposal) and the heartbeat via /api/agent/report.'
    limits: Never calls update_trigger, delete_trigger, fire_trigger, pause_project, or any write to Notion/Supabase/VPS cron. Cannot see Grok-subscription tasks (reads grok-relay heartbeats instead). Proposals expire unanswered after 30 days and are re-raised once.
    minimum_output: One line per run, even "janitor: 0 proposals · all clean". A silent Sunday is a 💀 for the CoS.
    rules:
    - Proposals only; Aman's "ok N" executes, via the CoS
    - Every proposal names the trigger id or bot id and the evidence (last_run, cron, duplicate partner)
    - Never reads transcripts or chats (Directive 15)
    - Cheapest model; never the CoS model
```

**Owner note:** `credit-guard` already holds the only write permission on Routines (disable on RED). The janitor proposes; credit-guard enforces budget; the CoS executes cleanups on Aman's word. Three roles, no overlap.
