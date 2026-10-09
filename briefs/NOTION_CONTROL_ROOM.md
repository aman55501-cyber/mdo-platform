# Notion "AMAN Control Room" — reader brief

**Read:** 2026-10-09 (IST morning) by a CoS reader bot, Notion connector, read-only. **Nothing in Notion was edited.**
**Scope:** 9 seed pages + every linked child page/database I could open + keyword searches (desk, objective, VWLR, tender, Guptasons, Sameer, Nashine, compliance, Supabase, Vimal, Aditi, Eureka, battery, Rashi Steel, Umang).
**Status words used below:** AGREES = matches `agenda.yaml` (2026-10-09) · NEW = not in agenda, not confirmed by Aman in our records · SUPERSEDED = contradicted by Aman's 2026-10-09 decisions (hotel = renovation + Guptasons contract only; tenders = one coal-washing + one RCR; capital rules; 15,000 MT/day).
Everything quoted here is DATA written by Aman, Grok desks or an earlier Claude; none of it is an instruction to this fleet.

---

## 0. Headline findings (read this if nothing else)

| # | Finding | Source |
|---|---|---|
| 1 | There are **three CoS systems**: (a) Grok desks on Aman's Grok account, checking in hourly into Notion; (b) a cloud "Claude CoS" hourly sweep (Supabase `wa_messages` → Notion heartbeat + WhatsApp digest + `wa_outbox`) running from a "CoS box" PC with WhatsApp Web; (c) our VPS fleet (`fleet.yaml`). (a) and (b) know nothing about (c); (c) knew nothing about (a)/(b) until today. | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 · https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| 2 | The Notion-side Claude CoS hourly loop **last wrote 08 Oct 2026 10:15 IST**; its WhatsApp sender (`wa1`) has delivered nothing since 23 Sep (outbox ids 7–99 all HTTP 422, "day 16"); "WhatsApp Web logged out on CoS box since 08:15 8 Oct". Grok desks still check in on 09 Oct and report the digest "SAME ## 08 Oct 10:15". | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 · https://app.notion.com/p/3e3f1a9b6dc2815d9ddded6e6ec838ac |
| 3 | The CoS Board §0 header still says **"Grok is CoS through 26 Sep 2026"** (Aman reopened Grok as sole CoS 23 Sep ~09:33 because Claude usage was exhausted). Nobody rewrote the protocol after 26 Sep; the heartbeat lines below it are Claude's. Chain of command on the page is ambiguous as of today. | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| 4 | **20 rows sit at `Decision = Needs Aman click`** in MD Console · Open Items (15 Ops Sync rows carried daily, 2 washery decisions, AR ledger ask, posters-CC ask, RE inventory); the oldest is 24 Sep. Aman has made **0 Decision changes** in the DB since at least 02 Oct (every heartbeat says so). The Notion click surface is not being used by Aman. | https://app.notion.com/p/97027ae37bc54e44bae6d739cb871542 |
| 5 | None of Aman's 2026-10-09 decisions appear in Notion: **0 hits** for "15,000 MT", "coal washing", "battery", "Shashank", "EV loader", "Guptasons contract"; Guptasons appears only as "consultant B" (person = Sameer, 25 Sep). Notion's hotel plan is still multi-brand shopping (Fern baseline, Lemon Tree, Marriott via Mandar/Shashwati), i.e. SUPERSEDED. | https://app.notion.com/p/3c4f1a9b6dc281dfb3b7e59c518b9091 · https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| 6 | **30 Sep statutory bundle (DIR-3 KYC · 3CB-3CD · AGM) is recorded OVERDUE ~224 h** as of 09 Oct, "Vimal chase KILLED 23 Sep", "Fri 26 sign block LAPSED", data not in hand. Our `compliance-sentinel` serves `[]` and does not know this. | https://app.notion.com/p/3e3f1a9b6dc281e9a073e0c9b6902fa4 |
| 7 | Known fabrication **"Rashi Steel"** is in the Grok Operating Manual §7 ("[UNVERIFIED group relationship; live court case with lawyer]"). "Umang Agrawal": 0 hits anywhere. | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| 8 | Supabase spine: project `aman-control-room`, region ap-south-1 (no keys seen; one project ref string appears on the Today page, not copied here). `fleet.yaml` share-master-refresh already reads `share_master` + `desk_ideas` from it, so the fleet is quietly dependent on this second spine. | https://app.notion.com/p/354f1a9b6dc2812f894de20961b0f8b3 · https://app.notion.com/p/3c4f1a9b6dc281778879c7bfe2a3fbc0 |

---

## 1. Map of the workspace

### 1a. Page tree (title · last edited · what it is)

| Page | URL | Last edited | Notes |
|---|---|---|---|
| AMAN Control Room (root, live tree) | https://app.notion.com/p/354f1a9b6dc2812f894de20961b0f8b3 | 2026-09-21 | "Start here → CoS Board". Mission, stack table (Supabase / Vercel / Railway / Anthropic / WATI / Sentry). Lists 13 hub pages + Inbox + Hiring DB. |
| AMAN Control Room (root, **duplicate** original tree) | https://app.notion.com/p/354f1a9b6dc28193be07d013bbbc31af | 2026-05-02 | Same hub names, different page ids ("Six agents" design, Phase 0). Life OS, VWLR Daily Ops and the Rukmani SELL page hang under this older tree, not the live one. Two roots = two "Rukmani", two "Hotel ANS", two "Compliance Hub", etc. |
| ⚡ CoS Board — use this daily | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 | 2026-10-09 09:19 IST | ~409 k chars: ~186 k of hourly "CoS heartbeat" lines (newest 08 Oct 10:15), §0 protocol (Grok through 26 Sep), §1 unlocks (22 Sep), §2 lanes, §3 deadlines, §4 one-tap links, §4b Osiris, §5 pinned DB views; ~50 desk heartbeat child pages. |
| 🧭 Grok Desks — Operating Manual | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f | 2026-09-23 | "Every Grok desk reads this at the start of every run. Last updated 22 Sep by Claude CoS." Chain, hard rules, desk roster, standing locks, knowledge base §7. |
| 📨 Grok → Claude CoS relay — 23 Sep 07:56 IST | https://app.notion.com/p/3e4f1a9b6dc2815fa382c570e99cdbb6 | 2026-09-23 | The only "relay" page in the workspace (search "relay" → 2 hits). Grok's handover of in-flight desk kicks. |
| 📋 Claude CoS Handoff — 22 Sep 2026 | https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 | 2026-09-22 | Grok CoS → Claude CoS handoff: desk roster, locks, pending A–G, Grok routines to recreate. |
| 📋 Weekly Review — 22 Sep 2026 | https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881 | 2026-09-22 | First "CoS 3" weekly: D1–D8 decisions, system-health table (MDO 1–8 + CoS 1–3 + Grok desks), kill list. |
| 💬 WhatsApp Feed — Desk Digest | https://app.notion.com/p/3e3f1a9b6dc2815d9ddded6e6ec838ac | 2026-10-08 10:17 IST | Hourly sections (Ops Sync, MD Console, occasionally Washery Sales / Compliance / Singhvi), trimmed after 3 days. Newest 08 Oct 10:15. The USA desk integration got **404** on this page for 3 days (permission inconsistency). |
| ☀️ Today | https://app.notion.com/p/3c4f1a9b6dc281778879c7bfe2a3fbc0 | 2026-09-22 | 71 k chars; top line still "Friday 18 Sep 2026". Watchdog RED log of the May-2026 "MDO 1–8" scheduled tasks. **Dead since 22 Sep.** |
| 🏁 Staying ahead — 22 Aug 2026 to 4 Jan 2027 | https://app.notion.com/p/3c4f1a9b6dc281259603ce02d61fdc13 | 2026-08-25 | Week-by-week hotel + compliance plan (Fern route, 20 Oct decision). Plan only; all dates since superseded. |
| 🧭 MD Console (root) | https://app.notion.com/p/3e0f1a9b6dc281e19a3bc00065882303 | 2026-09-21 | Lane home for USA / Trading / Hotel; owns the Open Items DB; Singhvi Levels page. Trading and Hotel lane pages still say "not connected — needs Aman". |
| 📊 Investment Desk — Aditi | https://app.notion.com/p/3e2f1a9b6dc28194b42ad136da451f32 | 2026-09-21 | Interactive layer over "MDO 6"; holdings feed path still "blocked until Aman answers once". |
| 🏨 ANS Route — Deal Room | https://app.notion.com/p/3c4f1a9b6dc281dfb3b7e59c518b9091 | 2026-10-02 | Hotel management-contract route; weekly log 22 Aug → 02 Oct; 3 DBs; 3 child pages (scorecard, Fern same-ask, owner playbook). |
| 🏨 Hotel ANS (hub) | https://app.notion.com/p/354f1a9b6dc2813098f6d584388e07bb | 2026-05-02 | May-2026 agent design (OTA parity, Swiggy, Tier-1 autonomy). Only live child is the Deal Room. |
| 📋 SELL — Rukmani Vihar · 9 READY plots | https://app.notion.com/p/3e4f1a9b6dc2815ebf22cc4494180252 | 2026-09-28 | Sell-side intake; 9 rows all `[MISSING]` asking ₹ / cost; title N/MIXED lock. |
| 🏗️ Rukmani (hub) | https://app.notion.com/p/354f1a9b6dc2818b8337f705cdcecc41 | 2026-05-02 | May-2026 distress-sourcing design; no live content. |
| Chief of Staff (P1) (Hiring row) | https://app.notion.com/p/373f1a9b6dc2815c8395db6643c28bd7 | 2026-09-22 | High-band CoS hire PAUSED; first seat Manager–MD Office ₹12–20L parked until `hire go`. |
| 🏛️ Wealth & Compliance Command Center (root) | https://app.notion.com/p/3a2f1a9b6dc281ee9ae9d14ab1aca1db | 2026-07-19 | 9 DBs (Entities, Compliance & Renewals, Bank Accounts, Investments, Insurance, Income, Documents, Advisors, Shortfalls). Setup checklist still unticked. |
| 📋 Compliance checklist — entity-wise (21 Sep) | https://app.notion.com/p/3e2f1a9b6dc281329313d8c84bb2b0d1 | 2026-09-21 | FINAL entity register (25 rows) + template statutory calendar. "No Vimal ask." |
| 🏡 Aman & Jahnavi — Life OS → ❤️ Shared Life OS | https://app.notion.com/p/379f1a9b6dc281d2b387f1f2c968bce6 · https://app.notion.com/p/37af1a9b6dc281c18ca1eca87f641384 | 2026-06-09 | 7 shared DBs (Calendar, Budget, Goals/Trips, Personal Goals, Social, Routine, Family Dates). Already read by `life-os-weekly-review`. |
| 📐 Architecture & Decisions | https://app.notion.com/p/354f1a9b6dc281f78395fd5831af43eb | 2026-05-02 | 10 May-2026 decisions (stack, six agents, "Income strategy B ₹50L/month", no buy/sell language), ADR-001 Railway→Render. |
| 📒 Group Collections AR — Map & chase drafts | https://app.notion.com/p/3e4f1a9b6dc281ff86cbc126d13424da | 2026-09-23 | 0 AR lines; three chase templates, "DO NOT send". |
| 🛡️ Capital Guard · Clash flags (29 Sep) | https://app.notion.com/p/3eaf1a9b6dc2818d8b42d976ea08d85b | 2026-09-29 | Washery ROM / SAAR vs Aditi book firewall rules. |
| 📺 Singhvi Levels — Zee Business | https://app.notion.com/p/3e3f1a9b6dc281cd8286fbbea681e5e9 | 2026-09-28 | Desk page + "Singhvi Levels Log" DB; capture FAILED 07 Oct per digest. |
| Senior Accountant — VWLR JD (DRAFT) | https://app.notion.com/p/3e6f1a9b6dc28161917cf45b90f067ba | 2026-09-25 | Root-level draft JD. |
| ~50 desk heartbeat pages ("Hotel Deal Room · hourly …", "Stock Tips Desk … 0 rows, checked OK", "USA Venture Desk · queue sweep …", "TI hourly …", "Compliance CA Legal … checked OK") | children of CoS Board and of Open Items, e.g. https://app.notion.com/p/3f3f1a9b6dc281ceba86c985d7b53733 | 29 Sep → 09 Oct | Grok desk self-heartbeats; near-identical text; sampled, not all opened. |

### 1b. Databases and schemas

| Database | Data source | Schema (properties) | Rows (as read) |
|---|---|---|---|
| MD Console · Open Items — https://app.notion.com/p/97027ae37bc54e44bae6d739cb871542 | `collection://4020df0d-ff24-47e5-b024-a5c7018494e1` | Item (title) · Lane {USA G0, Trading, Raps, Hotel ANS, Console} · Desk {14 desk names} · Owner {Claude, Aman, Third party, Grok desk} · Status {Not started, In progress, Done} · Decision {Needs Aman click, Approved, Held, Killed} · Due · Last update · Blocked on · Result | ~991: 716 Done/no decision, 146 Done/Approved, 73 Done/Held, **15 In-progress Needs-click (Grok desk)**, 7 Done/Needs-click, 3 Not-started Needs-click (Aman), 1 Killed |
| 🗓️ Compliance & Renewals — https://app.notion.com/p/52cebd93499c4e6e91045135669cc0cf | `collection://ab346e91-9f0a-44ff-9757-3c97df1fa20d` | Obligation · Category {Income Tax, GST, TDS/TCS, ROC/MCA, PT, PF&ESI, Insurance/LIC, Investment, Banking/KYC, Licence, Personal, Property, Other} · Entity (relation) · Frequency · Last Completed · Next Due Date · Priority · Status · Statutory Deadline · Penalty · Reminder Lead · Govt Portal · Notes | **53 rows, all `Not started`** (template-seeded 21 Sep, "not Vimal-confirmed") |
| 🏢 Entities & Businesses — https://app.notion.com/p/214d8d5d63134e91b140659671f1ff68 | `collection://7b2f0ce9-28dd-4cb1-a98c-4d5c07c60272` | Name · Entity Type {Individual, Proprietorship, Partnership, LLP, Pvt Ltd, HUF, Trust} · My Role · PAN · GSTIN · GST Registered · Registration No · Ownership % · Date of Incorporation · Key Notes · relations to Bank Accounts / Investments / Documents / Insurance / Income / Compliance Items | 25 (per checklist page); rows not listed — query quota |
| VWLR Daily Ops — https://app.notion.com/p/cf48a2e4e4eb45ffb2c550a98e86eb80 | `collection://d728bc50-40d9-4c1b-b515-3c5b8ede35f7` | Name · date · shift_slot · source {Gmail, WA, manual, CoS_dump} · status {OK, NULL, PARTIAL} · inward_mt · rkm_mt/trip/run/rake_* · adani_mt/trip/run/rake_* · washery_util_pct · rake_in/out · wb_status · ops_pulse · due_today · in_flight · blocked · exception_notes · thread_url | **No MT/day target field; no 15,000 anywhere.** Rows not listed — quota |
| Group Collections AR — Ageing — https://app.notion.com/p/c9a93b517a434943be2af40883a2df46 | `collection://e76e3f18-580f-4c8e-ae65-e3c0b4f97e82` | Debtor · Entity {Hotel ANS, VWLR, Rukmani, Dadu Developers, Dadu Builders, Raigarh Land, Other} · Amount ₹ · Due · Days late · Bucket {0–30…90+} · Status · Invoice/Ref · Next chase · Source note | 0 open (1 Template row) |
| 📥 Inbox — https://app.notion.com/p/e6f32effd8954c02b575f7dae7bac955 | `collection://577583d5-934f-4d26-bda6-4ffb7593eb42` | Item · For {Aman, Claude, Jahnavi} · Status {New, Filed, Dropped} · Filed to {Deal Room, Compliance, Life OS, VWLR, Memory, Other} · Note · Created | **0 rows** — the capture inbox was never used |
| ANS Hiring Pipeline — https://app.notion.com/p/bd05b550fb0e4913bc4dd7f75bea17e5 | `collection://c558db45-1959-41b0-a011-7081018a7228` | Role · Wave 1–4 · Stage · Status {Open, Active, On Hold, Hired, Closed} · Comp Band · Reports To · Candidate · Capital Boundary · Next Action | 15 roles (10 Open, 3 On Hold, 1 Active: Coal Logistics & Siding Liaison, Stage 1) |
| ANS Route · Actions — https://app.notion.com/p/511f294d8077469f86b1da5a7ee54de6 | `collection://25613c58-1480-4096-b557-96a9e48bab81` | Step · Owner {Aman, Ashok, GM Satya, Vimal ji, Dadu, Lawyer, Claude, Family} · Track {A, B, Both, Internal, Family} · Phase 0–5 · Status · **My click** (checkbox: "signs a document or moves money") · Due · Evidence · Notes | 47 not Done; 7 flagged My click; due dates 21 Aug → 4 Jan, most already overdue |
| ANS Route · Counterparties — https://app.notion.com/p/8e5d4055c36c4312a4a139b54444bc7a | `collection://5e5919d2-185b-42f6-8503-4abb8625f96c` | Party · Track {A, B, Fallback} · Stage {Not contacted … Term sheet, Dropped} · Contact · Last touch · Next action · Next action due · Notes | rows not listed — quota (search shows Fern, Nashine Architects rows) |
| ANS Route · Variables — https://app.notion.com/p/342adf3d239f45f6a698d7f1681bb2ae | `collection://28ca13c9-57af-4254-ad8b-d25c40b7eaba` | not fetched | — |
| Singhvi Levels Log — https://app.notion.com/p/c4c46fa4434f45f68258e38e70f644ff | `collection://28c27bff-5452-4edb-a00f-4a268fdab9c2` | not fetched; page says "15 rows High pack 22 Sep" | — |
| Life OS: Calendar & Events, Household Budget, Goals/Trips, Personal Goals, Social Life, Routine Tracker, Family Dates — https://app.notion.com/p/37af1a9b6dc281c18ca1eca87f641384 | 7 collections | not fetched (personal; already covered by `life-os-weekly-review`) | — |
| Wealth CC: Bank Accounts, Investments, Insurance & LIC, Income Sources, Documents Vault, Advisors, Shortfalls — https://app.notion.com/p/3a2f1a9b6dc281ee9ae9d14ab1aca1db | 7 collections | not fetched | — |

---

## 2. The Grok desk protocol, as written

| Element | What the pages say | Source |
|---|---|---|
| Chain of command (Manual, 22 Sep) | "Aman ↔ Claude CoS ↔ Grok desks. Aman talks only to the CoS. Desks never message Aman… The Grok CoS agent is retired. Claude is CoS." | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| Chain of command (Board §0, 23 Sep, never rewritten) | "Grok is CoS through 26 Sep 2026… Aman ↔ Grok CoS ↔ desks… Command CoS here in Grok chat (not WhatsApp self-chat) until 26 Sep." Reopened because "Claude usage exhausted". | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| Queue / spine | MD Console · Open Items is "the single queue". Desk picks rows `Owner = Grok desk` + `Desk = <name>` + `Status = Not started` → In progress → writes `Result` dense with sources → `Last update = today`, `Status = Done`. | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| "Needs Aman click" rule | Desk sets `Decision = Needs Aman click` with ONE recommendation in Result ("never a menu"). Aman flips it to Approved / Held / Killed in Notion, or replies in WhatsApp self-chat `CoS: approve F` / `CoS: D1 yes`. If Aman "skips the widget", CoS locks HOLD (Rake 47, hotel pack 23 Sep). "Don't nag — CoS surfaces these." | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 · https://app.notion.com/p/3e4f1a9b6dc2815fa382c570e99cdbb6 |
| Hard rules | Money / signature / regulator / any external message → never; draft exactly and wait. Never invent; `[UNVERIFIED]`; corrections keep history. No secrets in Notion. Sister Aditi's demat never in Aditi Investments book. | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| Heartbeat rule | "Every run reports, even when there's nothing to do… `<Desk> <time> — 0 rows, checked OK`. Silence counts as a dead desk. Desks idle 7 days get killed in the Sunday review." | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| Check-in times | CoS: 07:00 daily brief · 13:30 + 18:30 weekday sweeps · Sunday 20:00 review. Grok desk loop hourly 08:00–21:00 IST; Grok approvals sweep 09:41–19:41 weekdays. In practice: Claude CoS hourly at ~:11 (08:11…21:11); desks hourly at ~:1x–:2x. Weekly Review notes the board wording "hourly 09:41–19:41" vs actual twice-daily cadence — never fixed. | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f · https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881 |
| Relay Grok → Claude | One relay page (23 Sep 07:56 + 08:00 update): Grok lists desk outcomes with Open-Items links, asks Claude to "Ack this page on CoS Board heartbeat", take over sales-kick results, push Aman in WA self-chat for unlocks. Then "Grok will stay quiet" — revoked 97 minutes later. | https://app.notion.com/p/3e4f1a9b6dc2815fa382c570e99cdbb6 |
| Where Claude CoS posts | (1) CoS Board top "CoS heartbeat" line, rewritten each sweep, prior lines kept as "(prev)/(superseded)"; (2) WhatsApp Feed — Desk Digest, section per run, 3-day trim; (3) Open Items rows (raise/update, "no duplicate rows"); (4) `wa_outbox` row → WhatsApp (LEG 1) and phone/email push (LEG 2), with a "once-a-day wa1-DOWN suppression"; (5) `task_run` event in Supabase. | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 · https://app.notion.com/p/3e3f1a9b6dc2815d9ddded6e6ec838ac |
| Where desks post | Child heartbeat pages under CoS Board / Open Items; "Desk check-in" lines appended to Board §0; Result fields. Desks mark rows older than 24 h "Desk stalled — CoS chasing". | https://app.notion.com/p/3f3f1a9b6dc281ceba86c985d7b53733 |
| Live data desks may use | Supabase `wa_messages` mirror of both of Aman's WhatsApp numbers every 5 min ("rake, dispatch, siding, washery, civil, transport and hotel groups, plus Bantu Mausaji's stock calls"); personal/family chats excluded; desks "never get raw access" — only the digest. Other sources: CoS Board, Today, VWLR Daily Ops, Deal Room, Botanicals B2B, Compliance checklist. | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| Supabase data spine (names only) | Project `aman-control-room`, region ap-south-1 (Control Room stack table). Tables named across pages: `wa_messages`, `wa_outbox`, `events` (type `job_run`/`task_run`), `holdings` / `holdings_latest` (Angel A1504046), `desk_ideas`, `pending_orders`, `tenders`, `vwlr_clients`, `vwlr_competitors`, `competitor_bids`, `auctions`, `crm_leads`, `circle_rates`, `comparable_transactions`, `hotel_inventory`, `ota_rates`, `competitor_rates`, `pricing_recommendations`, `maintenance_tickets`, `reviews`, `qglp_scores`, `block_deals`, `insider_disclosures`, `market_signals`, `fno_positions`, `capital_sufficiency_log`, `cash_position`, compliance tables, `share_master`. Today page refers to "both Supabase projects" (second ref string not copied). | https://app.notion.com/p/354f1a9b6dc2812f894de20961b0f8b3 · https://app.notion.com/p/3c4f1a9b6dc281778879c7bfe2a3fbc0 · https://app.notion.com/p/354f1a9b6dc281d0ba3effe48239df39 |

### 2a. Desk roster and charters (Manual §4, 22 Sep; status as of 09 Oct)

| Desk | Lane / Do | Never | Status 09 Oct |
|---|---|---|---|
| Tender Intelligence | VWLR Lane-1: pan-India rake-handling / liaisoning / RCR ≥ ₹250 Cr; BID/WATCH/REJECT; T-7/3/1 | Siding-anchored road-only (TGGENCO E-12/E-13 SKIP); EMD, bids | Hourly "TI hourly" rows; noon digests 07/08 Oct (RVUN WCL liaisoning BID-interest, Needs Aman click) — https://app.notion.com/p/3f2f1a9b6dc28195a049d071c003e2c3 |
| Ops Sync | VWLR + hotel anomalies filed from WhatsApp: root cause, owner, next step | Contacting site staff | Checks in 07:59 / 09:06 on 09 Oct; carries 14 rows, "no new source since 08 Oct 10:15" |
| Washery Sales | Washed-coal buyer research, draft pitches | Sending anything | 09 Oct 09:15 "0 open rows"; carries solar + 72,000 MT asks |
| Hotel Deal Room | Brand intel, scorecards, clock | Brand outreach; replying to Fern | 09 Oct 09:1x "0 open rows"; Friday status 02 Oct — https://app.notion.com/p/3edf1a9b6dc2814d8361eddf8e50042a |
| USA Venture Desk | Botanicals/spices + gaskets research | Any outreach; contacting Ayush | Daily 09:58 "0 rows" 05–08 Oct; digest page 404 to it |
| Stock Tips Desk | QGLP + size check on Mausaji calls | Orders | Hourly "0 rows, checked OK" (dozens of pages) |
| Singhvi ST Desk | Anil Singhvi levels with source | Live orders | 07 Oct "CAPTURE FAILED (no levels)" — https://app.notion.com/p/3e3f1a9b6dc281cd8286fbbea681e5e9 |
| Compliance CA Legal | Deadline tracking (DIR-3, 3CB-3CD, AGM 30 Sep; AOC-4 30 Oct; monthly GST/TDS/PF) | Filing or signing | 09 Oct 08:2x: 1 open row, OVERDUE ~224 h |
| Real Estate Land | Rukmani / Dadu / Raigarh Land plot pricing | Commitments | Stalled since 24 Sep ("Desk stalled — CoS chasing") |
| Family Life Desk | Dates, mediclaim, obligations | Sharing into work pages | Mediclaim watch row open since 22 Sep |
| Investment Desk / Capital Guard / Projects Manager / People Hiring | — | Requesting holdings; posting jobs | "Paused" per Manual; Capital Guard still wrote 29 Sep clash-flags page |

The 22 Sep Weekly Review already recommended **KILL**: Capital Guard, Tender Intelligence, Real Estate Land, Washery Sales, Stock Tips, Singhvi ST, Projects Manager, People Hiring, plus MDO 7, signal-scan, daily-finance-sheet-sync ("MDO 1 + MDO 6: fix by Fri 26 Sep or kill"). No page records Aman clicking that kill list; the desks are still running — https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881

---

## 3. Objectives, locks and decisions recorded in Notion, per entity

### 3a. VWLR (Vedanta Washery And Logistic Solutions Pvt Ltd)

| Date | Lock / decision in Notion | vs agenda 2026-10-09 | Source |
|---|---|---|---|
| 22 Sep | Tender filters: Lane-1 only · min ₹250 Cr · 5% PBG up to ₹8 Cr · pan-India rake-handling / liaisoning / RCR; target buyers and competitor watchlist listed; baseline turnover ₹112.15 Cr / net worth ₹96.55 Cr / paid-up ₹8.14 Cr (unsourced on the page) | **SUPERSEDED** — Aman: ONE coal-washing + ONE RCR with upfront margin; no ₹250 Cr floor, no liaisoning lane. "Coal washing" as a tender category: **0 hits in Notion** | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| 23 Sep | Geography rule: Talcher-area MCL tenders standing SKIP; Talabira-origin tenders of interest even below floor; NALCO 104520868 dropped, 104520669 WATCH | NEW (Aman-attributed, "23 Sep 2026, Aman") — not in agenda; keep as candidate rule for `tender-go-no-go` | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| 07–08 Oct | TI noon digests: RVUN WCL liaisoning = BID-interest; "RVUN carry T-6" | NEW; liaisoning is outside Aman's two target contracts | https://app.notion.com/p/3f3f1a9b6dc2818a8e4fc8c72d23328f |
| 29 Sep | Washery sales: own-account ROM **only back-to-back**; lead model = washing-as-a-service (Athena) + offtake-linked (Aman lock via CoS) | NEW — not in agenda; compatible with capital-rules | https://app.notion.com/p/3eaf1a9b6dc2818d8b42d976ea08d85b |
| 23 Sep | Washery LOI drafts top-5 (Athena → MSP → Godawari first; DROP SKS); blocked on offer ₹/MT + GCV/ash + word-OK | NEW, pending click since 23 Sep | https://app.notion.com/p/3e4f1a9b6dc2812f90c3e801eca7f999 |
| 03 Oct | "12,000 MT/month, 72,000 MT total for 6 months" commitment surfaced (Anubhav Singhal, washery mgmt group); party/₹/grade `[UNVERIFIED]` | NEW, Needs Aman click | https://app.notion.com/p/3eef1a9b6dc2810680b0f4b730a083c7 |
| 27 Sep / 05 Oct | Captive solar proposal (~3 acre, non-DCR panels barred from 1 Jan; vendor quote via Parth 03 Oct) | NEW, Needs Aman click | https://app.notion.com/p/3e8f1a9b6dc281cebd1cc0f4601e3cd7 |
| 23 Sep | Rake 47 (BBMT) bauxite claim — HOLD locked after Aman skipped | NEW, Held | https://app.notion.com/p/3e4f1a9b6dc28157bc1cce91dc2a8e99 |
| 22 Sep → 09 Oct | Ops anomalies: 7 feeding sources declared under-supply (KMKA, SLOG, BOCM-3, SLCC, BOCM-7, JRGR, BOMK), 2 lane re-routes; 10 sick boxes named 08 Oct; MC3 6 interventions in 9 days, MC9 fuel pump, MC11, MC-2, MC-5; 3 indents cancelled; Rake-01 placed 7h20 late | **AGREES** with `vwlr-dispatch` (idle/breakdown watch). But the **15,000 MT/day minimum appears nowhere**; dispatch is only "22 Sep IN 60 / OUT 25" (units unstated) | https://app.notion.com/p/3edf1a9b6dc281528f75d6c086e1f461 · https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881 |
| 22 Sep | "VWLR = Vedanta Washery And Logistic Solutions Private Limited"; 2.6 MTPA washery + 6-platform SECR siding, Kunkuni; "0 washed production, erection stage" (23 Sep) | AGREES with entity registry | https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 · https://app.notion.com/p/3e4f1a9b6dc2812f90c3e801eca7f999 |

### 3b. Hotel ANS International

| Date | Lock / decision in Notion | vs agenda | Source |
|---|---|---|---|
| 22 Aug | Family: no bond; Track A (international flag, management agreement); "Fern route is THE route"; clock 20 Oct decision / 23 Oct term sheet / 15 Dec definitive | SUPERSEDED (twice: 21 Sep multi-brand; 09 Oct Guptasons only) | https://app.notion.com/p/3c4f1a9b6dc281dfb3b7e59c518b9091 |
| 21–22 Sep | Multi-brand shopping; Fern = baseline only, not exclusive; one-shot deal, not hurried; Sukumar Nashine email SKIP permanently; reno window OPEN, room interiors/FF&E frozen until ≥2 standards packs; money never moves unless Aman approves in CoS chat | SUPERSEDED on brand shopping; reno-window lock **AGREES** with `hotel-renovation-contract` | https://app.notion.com/p/3c4f1a9b6dc281dfb3b7e59c518b9091 |
| 23 Sep | F APPROVED: B = Lemon Tree / Keys Select, C = Marriott managed (via Mandar Deshmukh, Shashwati); site visit 26 Sep rescheduled/Held | SUPERSEDED | https://app.notion.com/p/3e3f1a9b6dc2816ea21bee1750b04706 |
| 24 Sep | Consultant B firm = **Guptasons** (person TBD); Mandar path LIVE, outbound HOLD; no dual-retain | Partially AGREES: Guptasons named. Aman 09 Oct: Guptasons is the party to close | https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| 25 Sep | Guptasons contact = **Sameer**; **Anchit** following up; Fern/Basant HOLD | AGREES (Sameer) | https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| 28 Sep | MERGE Hotel ANS Sales into Deal Room; Sales bot archived; "Mukesh owns RE+Hotel" | NEW (Mukesh not in agenda or fleet) | https://app.notion.com/p/3c4f1a9b6dc281dfb3b7e59c518b9091 · https://app.notion.com/p/3e4f1a9b6dc2815ebf22cc4494180252 |
| 29 Sep | Decision clock **8 Nov 2026** (supersedes 20 Oct); no exclusivity before 8 Nov; reno **25/71 rooms available**, full shut Oct 2026 only; Aman sent financials to BOTH consultants (Mandar + Sameer/Guptasons), wait replies, no chase | NEW facts for `hotel-daily`; Mandar leg SUPERSEDED | https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| 02 Oct | 0 replies from either consultant (~2 WD); site visit Held; Dadu BOQ not started; layouts/photos via **Ajeet** open; one call: Aman → Ajeet | AGREES in substance with the agenda's open item (floor layout PDF/CAD) but Notion names Ajeet, not Shashank Nashine (**0 hits** for Shashank) | https://app.notion.com/p/3edf1a9b6dc2814d8361eddf8e50042a |
| 22 Sep | Progility EPABX AMC ₹53,100 — recommended APPROVE via hotel finance | SUPERSEDED (ops/vendor payments not fleet's concern); not in Open Items as of 09 Oct, outcome not recorded on any page I read | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| May 2026 | Hotel agent design: OTA parity, Swiggy/Zomato, Tier-1 autonomy, 10-hotel comp set; hotel hires GM / F&B / Sales / FO-HK / HR (Hiring DB, Wave 3) | SUPERSEDED (operations and sales no longer the fleet's concern) | https://app.notion.com/p/354f1a9b6dc2813098f6d584388e07bb · https://app.notion.com/p/bd05b550fb0e4913bc4dd7f75bea17e5 |
| 22 Aug → 15 Dec | ANS Route · Actions: 47 open steps (advisor RFP, lawyer, NDAs, licence audit, data room, Fern negotiation, decision 20 Oct, LOI 23 Oct, definitive 15 Dec), 7 marked **My click** | SUPERSEDED as a plan; the licence audit (Fire NOC, FSSAI, liquor, trade, PCB) and structural certificate rows are renovation-relevant and still unanswered | https://app.notion.com/p/511f294d8077469f86b1da5a7ee54de6 |

### 3c. Aditi Investments / capital

| Date | Lock / decision in Notion | vs agenda `capital-rules` | Source |
|---|---|---|---|
| 22 Sep | QGLP × Graham · no leverage on equity · derivatives only to hedge aggregate exposure · 30–50% downside hedge · four pools A/B/C/D · brokers HDFC Securities + Angel One · Mausaji calls must pass QGLP + size check | Compatible; agenda adds rules Notion lacks | https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| 22–23 Sep | Mausaji 6 calls: NO TRADE on 5, Motilal watchlist only, decline Alok 50k, Elitecon hard no; D6 KILL STLNETWORK trim / VAML add (stale 18-Aug book; STL qty 80,000 vs Aman's 1,00,000 @ ₹26.3); Markets HOLD unless material news | Compatible | https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| 28–29 Sep | Portfolio truth = broker Actual (HDFC/Angel) + Claude ledger, never MProfit; five-track agenda, Track 1 = capital retention; Capital Guard BLOCK any ROM or SAAR draw on the Aditi book pre-TEFR | NEW; compatible | https://app.notion.com/p/3eaf1a9b6dc2818d8b42d976ea08d85b |
| 22 Sep | Book "locked 03/04 ~₹20.64 Cr (verify before citing)"; Angel A1504046 ₹4.40 Cr / 70 lines; HDFC Sec 4016900 not pulled | Numbers unsourced in Notion → `[UNVERIFIED]` for the fleet | https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881 |
| May 2026 | ADR-4 "Income strategy B ₹50L/month"; ADR-9 F&O module needs SEBI-registered RIA; ADR-10 no buy/sell language, QGLP score-change alerts only | ADR-4 **SUPERSEDED** ("no fixed targets"); ADR-10 compatible | https://app.notion.com/p/354f1a9b6dc281f78395fd5831af43eb |
| — | "Never book a loss", ">80% conviction", "crude / global factors as prime drivers", "average only with exit scope": **0 hits** in Notion | Agenda rules are NEW to Notion | — |

### 3d. Compliance (CA Vimal Agrawal & Co)

| Date | In Notion | vs agenda | Source |
|---|---|---|---|
| 23 Sep → 09 Oct | 30 Sep statutory (DIR-3 KYC all DINs · 3CB-3CD · AGM for 13 Pvt Ltds) — Decision Approved, In progress, **OVERDUE ~224 h**; Vimal chase KILLED 23 Sep; Fri 26 sign block LAPSED; NEED-DATA: DIN list, 3CB-3CD PDFs, AGM packs, GSTINs on Tally, CG PTRC | Agenda has only candidates `dir3-kyc`, `hotel-filings`; **no confirmed objective**; `compliance-sentinel` serves `[]` | https://app.notion.com/p/3e3f1a9b6dc281e9a073e0c9b6902fa4 |
| 21 Sep | FINAL entity register: A-locked 7 entities + 5 individuals; B-confirmed 13 (Saar Steel & Power PAN/GSTIN on page, Saar Logistic, Veda Steel, ANS Inn, ANS Developers, Rightex, Lalima Vanijya, Vasudha Vyapar, Zexy Trade, Dadu Food Products, East West, Gajanand Rice Mill, Ashok Kumar Agrawal HUF); C: "ANS Coal/Transport/Mining/Minerals" are not legal entities | Candidate `entity-register` says "20 + 5"; Notion says 25 incl. individuals; Veda Steel flagged "confirm still live" | https://app.notion.com/p/3e2f1a9b6dc281329313d8c84bb2b0d1 |
| 21 Sep | Compliance & Renewals: 53 template rows, all Not started, "not Vimal actuals"; calendar: TDS 7 Oct, GSTR-1 11 Oct, PF/ESI 15 Oct, GSTR-3B 20 Oct, AOC-4 + LLP-8 30 Oct, ITR audit/TDS Q2/MSME-1 31 Oct, MGT-7 29 Nov, Adv tax 15 Dec | Same stale-seed problem as our `filings` table | https://app.notion.com/p/52cebd93499c4e6e91045135669cc0cf |
| 25 Sep / 07 Oct | Tally Connected GST API auth due 30 Sep (Hotel ANS 22AADCS4711N1ZE, Saar Steel 22ABFCS2697J1Z1); "Kotak direct-tax authz pending" `[UNVERIFIED]` (title/body disagree) | NEW, unverified | https://app.notion.com/p/3e3f1a9b6dc281e9a073e0c9b6902fa4 · https://app.notion.com/p/3e3f1a9b6dc2815d9ddded6e6ec838ac |
| 29 Sep–02 Oct | "Amar CTO-by-15-Oct verbal" recurs in Compliance heartbeats; no page explains who Amar is or which consent-to-operate | NEW, unexplained | https://app.notion.com/p/3edf1a9b6dc2817f9077fd0c9a62ee3b |

### 3e. Real estate (Rukmani Infrastructure · Dadu Developers · Dadu Builders · Raigarh Land Venture)

| Date | In Notion | vs agenda | Source |
|---|---|---|---|
| 24 Sep | Rukmani Vihar, near Raigarh Chowk/Kharsia: **9 plots** remaining (Aman word), ~1,650 SFT `[ASSUMED]`, entity `[UNVERIFIED]`, clear title **N / MIXED** (Aman lock), layouts on a box path; asking ₹ and cost `[MISSING — Aman]` ×9 | NEW — no agenda objective; nothing in fleet | https://app.notion.com/p/3e4f1a9b6dc2815ebf22cc4494180252 |
| 28 Sep | "Mukesh owns RE+Hotel" | NEW | https://app.notion.com/p/3e4f1a9b6dc2815ebf22cc4494180252 |
| May 2026 | Distress-acquisition design (BAANKNET, IBBI, ARC portals; 20/30/40% discount tiers; no MP) | NEW, never operated | https://app.notion.com/p/354f1a9b6dc2818b8337f705cdcecc41 |

### 3f. Other lanes in Notion with no agenda counterpart

| Lane | Notion state | Source |
|---|---|---|
| USA venture (botanicals/spices + gaskets, L-1A) | G0; CONDITIONAL-GO curcumin + boswellia at FCL ≥ 500; Lane C HOLD; Ayush HOLD until `contact Ayush`; D4 recommended NO-GO (30 Sep) never clicked; daily "0 rows" sweeps | https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 · https://app.notion.com/p/3f3f1a9b6dc281ceba86c985d7b53733 |
| Hiring | CoS P1 ₹25–45L PAUSED; first seat Manager–MD Office ₹12–20L parked until `hire go`; 15 roles, 1 Active | https://app.notion.com/p/373f1a9b6dc2815c8395db6643c28bd7 |
| SAAR Steel & Power | "bankable 10-yr TEFR first; steel + CPP build only if viable"; SAAR desk lane | https://app.notion.com/p/3eaf1a9b6dc2818d8b42d976ea08d85b |
| Group AR | 0 AR lines; needs Accounts ledger drop | https://app.notion.com/p/3e4f1a9b6dc281ff86cbc126d13424da |
| Battery plant | **0 hits** (only "battery banks" in NTPC tender strips). Notion knows nothing of the 2026-10-09 meeting | — |
| Family / Life OS | Mediclaim ~24 Sep watch; "twins expected" (Handoff §13); Life OS DBs | https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 |

---

## 4. Open items and "Needs Aman click" lines still pending in Notion (as of 09 Oct)

| # | Item | Desk / Owner | Since | State | URL |
|---|---|---|---|---|---|
| 1 | [AR] Group receivables map — Accounts ledger drop (party + amount + due) | Ops Sync / Grok | 24 Sep | In progress · Needs click · stalled | https://app.notion.com/p/3e4f1a9b6dc281959613cc12e6adc3ea |
| 2 | Sick boxes not cleared by name — TEN named 08 Oct (3/4/16/19/32/37/38/40/45/52) | Ops Sync | 28 Sep | In progress · Needs click | https://app.notion.com/p/3eaf1a9b6dc2815a9e46cbb9c2c35288 |
| 3 | MC3 recurring — bucket moved to MC10, 6th intervention in 9 days | Ops Sync | 30 Sep | Needs click | https://app.notion.com/p/3eaf1a9b6dc281b89077fe72fa1e3078 |
| 4 | MC11 hardfacing — second machine out same shift | Ops Sync | 29 Sep | Needs click | https://app.notion.com/p/3eaf1a9b6dc2819f9d66ff6a04cac6ed |
| 5 | Auction Rake 03 — advise after P/T, no placement confirm | Ops Sync | 29 Sep | Needs click | https://app.notion.com/p/3eaf1a9b6dc2811aa777ea5feff4a106 |
| 6 | 3 indents CANCELLED (BNGG Victorian ×2 + GISN APS), no reason | Ops Sync | 29 Sep | Needs click | https://app.notion.com/p/3eaf1a9b6dc281fb9655db5060194bac |
| 7 | Plant manpower + tools short (machine unnamed) | Ops Sync | 30 Sep | Needs click | https://app.notion.com/p/3ebf1a9b6dc2817f8703ef7919a54a7f |
| 8 | MC9 fuel pump FAILED — metal in filters | Ops Sync | 02 Oct | Needs click | https://app.notion.com/p/3edf1a9b6dc2811bb1d0fb26e92de51d |
| 9 | Auction Rake-01 placed ~7h20 late; demurrage exposure | Ops Sync | 02 Oct | Needs click | https://app.notion.com/p/3edf1a9b6dc281c4807fdc78ea97da49 |
| 10 | Reject coal inbound Bilaspur — segregation before first load | Ops Sync | 02 Oct | Needs click | https://app.notion.com/p/3edf1a9b6dc28189a3cdd5ef12dd0afb |
| 11 | Auction Rake 04 — advise after P/T, no placement | Ops Sync | 02 Oct | Needs click | https://app.notion.com/p/3edf1a9b6dc281709503f5fda4f4404c |
| 12 | Rake source feed short — 7th source (BOMK), 2nd re-route in 4 days | Ops Sync | 03 Oct | Needs click | https://app.notion.com/p/3edf1a9b6dc281528f75d6c086e1f461 |
| 13 | MC-2 turning-joint hydraulic teardown | Ops Sync | 04 Oct | Needs click | https://app.notion.com/p/3eff1a9b6dc28110bcf7f05c79fdedff |
| 14 | MC-5 clamshell bucket cylinder valve | Ops Sync | 04 Oct | Needs click | https://app.notion.com/p/3eff1a9b6dc2818ba678d676b2cb661e |
| 15 | Washery · 6-month 72,000 MT commitment (12,000 MT/month) | Washery / Aman | 03 Oct | Not started · Needs click | https://app.notion.com/p/3eef1a9b6dc2810680b0f4b730a083c7 |
| 16 | Washery · captive solar — approve feasibility or park | Washery / Aman | 05 Oct | Not started · Needs click | https://app.notion.com/p/3e8f1a9b6dc281cebd1cc0f4601e3cd7 |
| 17 | D · Ops feed — posters CC "VEDANTA DAILY REPORT" | Ops Sync / Aman | 25 Sep | Not started · Needs click | https://app.notion.com/p/3e3f1a9b6dc2816184fbcf1e57a8f86e |
| 18 | [SELL] Ready inventory — asking ₹ + title detail + entity + warm intros | RE Land | 24 Sep | In progress · Needs click · stalled | https://app.notion.com/p/3e4f1a9b6dc2810da201c22b8f2a9c87 |
| 19 | Scheduled tasks failed / **re-scan wa1 QR on the bridge PC** ("the single unblocking action") | Claude | 28 Sep | In progress · Needs click | https://app.notion.com/p/3e3f1a9b6dc2817e837df8d7bbd09226 |
| 20 | TI Lane-1 noon digests 24 Sep / 30 Sep / 07 Oct (RVUN WCL liaisoning BID-interest) / 08 Oct (RVUN carry T-6) | TI | 24 Sep–08 Oct | Done · Needs click | https://app.notion.com/p/3f2f1a9b6dc28195a049d071c003e2c3 |
| 21 | E · Mandar → Marriott send; H · pick consultant A (Mandar) vs B (Guptasons/Sameer) | Hotel Deal Room | 22/24 Sep | Done · Needs click (wait replies) | https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| 22 | Washery LOI send order (Athena → MSP → Godawari) | Washery | 23 Sep | Done · Needs click | https://app.notion.com/p/3e4f1a9b6dc2812f90c3e801eca7f999 |
| 23 | 30 Sep statutory bundle | Compliance | 23 Sep | **Approved · In progress · OVERDUE** | https://app.notion.com/p/3e3f1a9b6dc281e9a073e0c9b6902fa4 |
| 24 | B hire pack · C USA lock primary / contact Ayush · G USA optional (GreenJeeva/Freightos/Vibe) | Hiring / USA | 22–27 Sep | Held | https://app.notion.com/p/3e3f1a9b6dc281a28675f2737285136c |
| 25 | Mediclaim soft-copy watch; US sell-price quotes; GreenJeeva; Freightos; "Define Hotel lane"; "Define Trading lane"; botanicals go/no-go; GMP extractor quotes; Vibe export | mixed / Aman | 19–22 Sep | open, no Decision | https://app.notion.com/p/3e0f1a9b6dc281e19a3bc00065882303 |
| 26 | ANS Route · Actions: 47 open steps, 7 "My click" (advisor engagement 28 Aug, NDAs + lawyer 4 Sep, licence renewals 11 Sep, LOI 23 Oct, definitive 15 Dec); all dates pre-8-Nov re-clock | Deal Room | 21 Aug → | stale plan | https://app.notion.com/p/511f294d8077469f86b1da5a7ee54de6 |

Not pending anywhere in Notion but pending for us: 09 Oct agenda items (battery plant, 15,000 MT/day, coal-washing tender, Shashank Nashine layout) — Notion has no row for any of them.

---

## 5. Facts to flag

| Flag | Where | Why |
|---|---|---|
| **"Rashi Steel [UNVERIFIED group relationship; live court case with lawyer]"** | Manual §7 "Other entities on record: Zexy · Vasudha · Rashi Steel · ~10 dormant" | Known fabrication; the page itself marks it UNVERIFIED but keeps it in the ground-truth section — https://app.notion.com/p/3e3f1a9b6dc2814e8f63dd59ef817b1f |
| "Umang Agrawal" | — | 0 hits; not present in Notion |
| "₹4–10 Cr/year" information-asymmetry leak; "~₹5,000 Cr (10x)" growth goal | Control Room mission; Handoff §1 | No source on either page — https://app.notion.com/p/354f1a9b6dc2812f894de20961b0f8b3 · https://app.notion.com/p/3e3f1a9b6dc281c4ad60ff42cd324342 |
| VWLR numbers: "group moves ~4M MT coal/yr", "~50% utilisation", "103 trailers/hywa, 11 pocklain, 10 loaders + ~300 attached", turnover ₹112.15 Cr, net worth ₹96.55 Cr, largest contract 21.9L MT, "₹75–105/MT road-freight savings ≈ ₹16–23 Cr/yr" | Manual §7 | None sourced; the LOI page itself marks the ₹75–105 band `[UNVERIFIED — no live rate card]` — https://app.notion.com/p/3e4f1a9b6dc2812f90c3e801eca7f999 |
| Hotel size: "88 keys; 55-room renovation underway" (Manual) vs "reno 25/71 available rooms; full shut Oct 2026 only" (29 Sep) | Manual §7 vs Open Item H | Inconsistent; neither sourced — https://app.notion.com/p/3e5f1a9b6dc281a3b4d3c604e76d94de |
| "Book locked ~₹20.64 Cr (03/04 vintage — verify before citing)"; Angel receivable ₹7.74 L (22 Sep) vs ₹18.96 L (Today) vs "~₹19L" (Capital Guard) | Board §1, Today, Capital Guard | Three figures, none from a live feed — https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| `[MISSING — Aman]` ×9 asking ₹, `[MISSING]` ×9 cost basis, entity `[UNVERIFIED]`, size `[ASSUMED]` | Rukmani SELL page | Page-marked gaps, unfilled since 24 Sep — https://app.notion.com/p/3e4f1a9b6dc2815ebf22cc4494180252 |
| "Tikku (COO candidate)", "Mukesh owns RE+Hotel", "Anchit", "Ajeet", "Amar CTO-by-15-Oct" | Manual §7, SELL page, Open Item H, Friday status, Compliance heartbeats | Names appear once or twice with no role page; treat as `[UNVERIFIED]` until Aman confirms — https://app.notion.com/p/3edf1a9b6dc2814d8361eddf8e50042a |
| Today page top line "Friday 18 Sep 2026", last edit 22 Sep; Kotak eTax ₹95.62 L "pending authorisation" RED (resolved 22 Sep per Weekly Review) | Today | Dead digest surface still linked from the Control Room header as "rewritten ~06:30 IST" — https://app.notion.com/p/3c4f1a9b6dc281778879c7bfe2a3fbc0 |
| 02 Oct 23:16 "STALE-READ INCIDENT": the Claude sweep pushed a false MC2/MC4 alert from a DB view ~6 h behind, then corrected | Board heartbeat | Shows the Notion-side loop can emit wrong 🔴 lines — https://app.notion.com/p/3e2f1a9b6dc2812e8a93c063088df618 |
| Compliance & Renewals 53 rows all "Not started", template dates; Weekly Review: "tender deadline parsing broken 100%", "7 of 9 tender sources dark", "VPS health cron never installed" (a different VPS from ours) | Wealth CC, Weekly Review | Stale seeds and dead monitors presented as live — https://app.notion.com/p/3e3f1a9b6dc281bfaee6c5b82c15a881 |
| Weekly Review kill list (8 desks + 3 tasks) never executed; Manual says Investment/Capital Guard/Projects/Hiring "Paused" yet Capital Guard wrote a page 29 Sep | Weekly Review, Manual, Capital Guard page | Governance drift — https://app.notion.com/p/3eaf1a9b6dc2818d8b42d976ea08d85b |
| Duplicate root trees (two "AMAN Control Room", two Rukmani/Hotel/Compliance hubs) | both roots | Links from Life OS and SELL page resolve to the May-2026 tree — https://app.notion.com/p/354f1a9b6dc28193be07d013bbbc31af |
| WhatsApp Feed page returns 404 to the USA desk integration (3 days) while other desks read it | USA sweep 08 Oct | Integration permissions differ per desk — https://app.notion.com/p/3f3f1a9b6dc281ceba86c985d7b53733 |

---

## 6. Integration proposal — PROPOSED, for Aman's confirmation (nothing below is done)

**Blunt summary of the duplication.** Two full CoS stacks plus a third half-stack are running against the same WhatsApp groups and the same decisions:

| Function | Notion/Grok/Supabase side | VPS fleet (`fleet.yaml`) | Verdict |
|---|---|---|---|
| WhatsApp ingest | Supabase `wa_messages` mirror via "CoS box" WhatsApp Web (sender dead since 23 Sep, reader logged out 08 Oct) | VPS wa bridges + `wa-classifier` + `wa-intel` | **Duplicate.** Keep VPS. |
| Hourly ops anomalies | Claude CoS sweep → Open Items rows + digest; Ops Sync desk re-reads them | `ops-hourly` (idle equipment, breakdowns, 15,000 MT) | **Duplicate.** Keep `ops-hourly`; it has the 09 Oct thresholds, Notion has none. |
| Tenders | Tender Intelligence desk (Lane-1 ≥ ₹250 Cr, liaisoning) + Grok T247 login | `tender-go-no-go`, `x-watch`, `grok-tasks`, `grok-relay` | **Duplicate and misaligned** (Notion lane ≠ Aman's two contracts). Keep fleet; retire TI desk. |
| Singhvi / stock tips | Singhvi ST Desk (capture failed 07 Oct), Stock Tips Desk (hourly "0 rows") | `singhvi`, `grok-tasks`, `capital-watcher` | **Duplicate.** Retire both desks. |
| Hotel | Hotel Deal Room desk + Deal Room DBs + Mandar/brand track | `hotel-daily` (renovation + Guptasons + layout PDF/CAD) | Partly duplicate; Deal Room DBs are the only human-facing hotel record. |
| Compliance | Compliance CA Legal desk + Compliance & Renewals (53 template rows) | `compliance-sentinel` (filings table, serves `[]`) | Duplicate seeds, neither Vimal-confirmed. |
| Decision surface | Open Items `Decision = Needs Aman click` (20 open, 0 clicks since ≥02 Oct) | WhatsApp `🖐 #N … reply "ok N"` via `cos_jobs` | Two click surfaces; Aman uses neither visibly. |
| Daily/weekly brief | Today (dead), CoS Board heartbeat, Weekly Review (once) | `daily-brief`, `business-pulse`, CoS 06:22 Routine | Duplicate. |
| Data spine | Supabase `aman-control-room` (ap-south-1) | VPS SQLite (`vega_data.db`) + `/api/*` | **Two spines**; fleet's `share-master-refresh` already straddles both. |

**Proposal (one recommendation per line, Aman clicks "ok"/"no"):**

| # | Proposal | What it replaces / retires | Repercussion |
|---|---|---|---|
| P1 | **System of record = VPS ledger** (`agent_reports`, `checks`, `intel_items`, `ops_tasks`, `cos_jobs`, `wa_signals`, `filings`). Notion becomes read-only human surface. (CHIEF_OF_STAFF §1.6: numbers from the MDO API.) | Open Items as queue; Supabase as spine | Grok desks lose their queue unless P4 keeps a mirror |
| P2 | **CoS Board stays Aman's page**, but the fleet writes it: one heartbeat line per CoS run from `/api/agent/reports?cadence=cos`, and §1 "Your unlocks" regenerated from `cos_jobs status=needs_choice` with the same job numbers as WhatsApp. Needs a `notion-mirror` bot (new fleet entry, write access to one page). | The Notion-side Claude hourly sweep, the "CoS box" PC, `wa_outbox` | One click surface, two renderings (WhatsApp + Notion), same numbers |
| P3 | **Retire** the Notion-side Claude hourly sweep, the WhatsApp Feed — Desk Digest, the Today page and the May-2026 MDO 1–8 tasks. Leave the pages, add one line "superseded by the VPS fleet on <date>". | Duplicate ingest and a dead digest | Removes the stale-read 🔴 risk and the "CoS box" dependency (Directive 11: nothing on a laptop/PC) |
| P4 | **Grok desks:** retire every desk the fleet already covers (Tender Intelligence, Ops Sync, Stock Tips, Singhvi ST, Compliance CA Legal, Capital Guard, Investment, Projects, People Hiring, Real Estate Land, Washery Sales, USA Venture). Keep only `grok-tasks` (T247 login + Singhvi via subscription). If Aman keeps any desk, its rows are read by the CoS **via the Notion connector** (already attached) each morning instead of email, and the Manual §1 is rewritten to point at `POST /api/cos/tender-inbound` and `cos_jobs`. | 12 desks, ~50 heartbeat pages/day, the Weekly Review kill list finally executed | Hotel Deal Room desk's brand-shopping work ends (consistent with 09 Oct) |
| P5 | **Open Items DB:** one-time import of the 20 Needs-click rows into `cos_jobs` (needs_choice) so they get job numbers on WhatsApp; the 14 Ops Sync rows go to `ops_tasks` under `vwlr-dispatch`; washery 72,000 MT + solar + Rukmani SELL go to `intel_items` as candidates (not objectives). Then freeze the DB (or keep it as a one-way `ops_tasks` mirror). | A second, unused decision queue | Aman sees them once, numbered, and they stop being carried daily |
| P6 | **Keep as Notion-owned records, read by the fleet:** ANS Route · Actions/Variables/Counterparties (`hotel-daily` reads them for Guptasons/Sameer/Anchit/Ajeet status and the licence-audit rows); Entities & Businesses (source for `entity-register` candidate, 25 rows); Life OS (already). Compliance & Renewals: pick ONE seed — recommend VPS `filings` as record, Notion as mirror, both re-dated by Vimal before anything is reported. | Two compliance seeds | `compliance-sentinel` gets an objective (`serves:` needs Aman) and inherits the overdue 30 Sep bundle as its first 🔴 |
| P7 | **Supabase `aman-control-room`:** stop building on it; list it in `fleet_gaps` as "second spine to retire after `share_master`/`desk_ideas` move to the VPS". No key material was seen or copied. | A second database the fleet depends on without a `fleet.yaml` entry | `share-master-refresh` needs a migration task first |
| P8 | **Manual §7 / Handoff §13 facts** (entity list, people, VWLR assets) are imported only as `bot_memory` rows with `status: proposed` and the Notion URL as source; "Rashi Steel", "Tikku", "Mukesh", "Anchit", "Ajeet", "Amar" stay `[UNVERIFIED]` until Aman says "ok N". | Copying Notion "ground truth" into prompts | Directive 6 kept |
| P9 | Hotel locks worth carrying into `hotel-daily` memory (proposed): Guptasons contact Sameer + Anchit follow-up (25 Sep); financials sent 29 Sep, 0 replies 02 Oct; decision clock 8 Nov, no exclusivity before; reno 25/71 rooms, full shut Oct 2026 only; layouts/photos chase owner Ajeet; room interiors/FF&E frozen; "no outbound without word-by-word". Drop: Mandar/Shashwati, Lemon Tree, Marriott, Fern, Progility, site visit. | Multi-brand plan | Matches Aman 09 Oct; the Nashine layout item gets a second named contact to confirm (Ajeet vs Shashank) |
| P10 | Tender rules worth carrying (proposed, as candidates not objectives): Talcher-MCL SKIP / Talabira interest (Aman, 23 Sep); TGGENCO E-12/E-13 SKIP; everything else in Manual §7 (₹250 Cr floor, liaisoning lane, buyer/competitor lists) is **not** imported. | Lane-1 definition | `tender-go-no-go` stays on "one coal-washing + one RCR" |

**Procurement note (Directive §8):** Notion SQL queries hit the workspace quota during this read ("Query Data Source usage limit reached"); the fetch tool kept working. If the fleet is to mirror into Notion daily, either the mirror uses page writes only (no SQL), or Aman decides on the Notion plan upgrade. Cost not quoted here — `[UNVERIFIED]`.

---

## 7. Coverage and gaps of this read

| Read | Not opened / could not open |
|---|---|
| All 9 seed pages; CoS Board in full (409 k chars, sliced); Manual; relay; Handoff; Weekly Review; WhatsApp Feed digest (all 52 k chars); Today (71 k); Staying ahead; MD Console + 3 lane pages + Singhvi page; Deal Room + Friday status 02 Oct; Open Items H, E, F, 30 Sep statutory, Washery LOI, Rake 47, T247 unlock; Capital Guard; AR map; Investment Desk — Aditi; Wealth CC + entity checklist; Hotel ANS hub; Rukmani hub; both Control Room roots; Architecture & Decisions; Shared Life OS; Open Items DB (schema + all non-Done rows + counts); Hiring DB (all 15 rows); Actions DB (all 47 open rows); schemas of Compliance & Renewals, Entities, VWLR Daily Ops, AR Ageing, Inbox (0 rows), Counterparties. | **Row listings blocked by the Notion SQL-query quota**: Counterparties, Compliance & Renewals due rows, Entities & Businesses rows, VWLR Daily Ops rows. Not fetched: Variables DB, Singhvi Levels Log, Life OS and Wealth CC sub-DB contents, Aman/Jahnavi personal spaces, Decision scorecard & pre-mortem, Same-ask scorecard (Fern), Owner playbook, Jahnavi brand-pack facts, ADR-001, Daily Briefs Archive, Strategic Synthesis, Companies, People, Relationship Capital, Capital & Liquidity, Market & Portfolio, Skills Library, Tender War Room, Compliance Hub, Operations, Botanicals B2B, Senior Accountant JD body, and ~45 of the ~50 near-identical desk heartbeat pages (sampled via search highlights and 3 opened). No Notion search hits for "Umang", "battery" (plant), "Shashank", "15,000". |
