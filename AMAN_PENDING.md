# Aman's pending list — the clicks that unlock the fleet

Rule (Aman, chat 2026-10-09): the CoS shows this list in every status message, carries every item
over, and removes an item only when Aman says so. Never trimmed by housekeeping.

| # | Item | Why it matters | Since |
|---|---|---|---|
| A6 | claude.ai environment SECRETS (laptop, Settings → Environments → Default Cloud Environment → Edit): MDO_SELF_URL, MDO_AUTH_TOKEN, VAULT_TOKEN, TENDER_INBOUND_TOKEN, GROK_CONTEXT_TOKEN, VAULT_BACKUP_PASSPHRASE. Domains DONE via Cowork 2026-10-09. | cloud Routines can reach the VPS | 2026-10-08 |
| A7 | Routines: DONE via Cowork 2026-10-09 except "Weekly memory sync" (exists, trig_01E3cCjuc9x35eYPvwtoWbQA, further down the list) → attach repo. Also decide: pause the 11 legacy Routines (CoS 1/2/3 hourly loop, Md morning brief, networth, investment book, F&O report, post-close wrap, hotel CV watch, Vedanta tender scan, Share Master refresh, Singhvi capture) — duplicates of the VPS fleet, 7 of them failing daily, the hourly sweep burns credits 14×/day | without sources the Routines run blind | 2026-10-08 |
| A8 | Gmail draft "Grok tasks v2": paste the two blocks into Grok's scheduler with the GROK_CONTEXT_TOKEN; log in to Tender247 once in Grok's browser | Singhvi + Tender247 feed | 2026-10-09 |
| A9 | PAUSED 2026-10-09: all cloud Routines disabled on Aman's word. When un-pausing, say **haiku** or **keep** for the model of the cheap Routines | cost per run ÷ 20 | 2026-10-09 |
| A11 | Decide on the three CoS systems: keep this fleet as the one CoS, Notion as the board it writes to, retire the PC "CoS box" loop and Grok desks' CoS role (briefs/NOTION_CONTROL_ROOM.md §6) | two systems in parallel waste credits and contradict each other | 2026-10-09 |
| A12 | WITHDRAWN by Aman 2026-10-09 ("compliance deadline questions unnecessary; statutory dates, remind me a week before"). Replaced by the compliance-reminder bot (built 2026-10-09: statutory calendar data/compliance_calendar_in.json, daily 08:00 IST 7-day WhatsApp message, Mon 08:05 "this week" line, zero LLM; live after the cron render in A25). Later: entity list with kinds after A15 → POST /api/compliance/entities | compliance objective | 2026-10-09 |
| A13 | Bot targets table: reply row number + ok/edit; the five people whose reply time matters. ANSWERED 2026-10-09: idle threshold = 1 hour; watched chats = Bantu Mausaji, Vedanta Daily Report, Washery Civil Update, Ans Management, VWLR Indent Planning, Core Group (priorities later); classifier KILLED (dead entry removed, commit 71e495d) | pulse and ops-hourly tuning | 2026-10-09 |
| A14 | Vision session, 30 min, VISION_INTAKE.md blocks 2–4 | top-line objectives the bots run toward | 2026-10-08 |
| A15 | Vault import from the laptop (`_memory` folder + Family_Finance_Master.xlsx) via scp + vault_import.sh; then Shares CFO reconnect | memory and finance bots have nothing to read | 2026-10-08 |
| A23 | Angel One holdings export (CSV) for the Share Master Portfolio tab; HDFC ×4 received 2026-10-09 | Portfolio tab incomplete without it | 2026-10-09 |
| A24 | NIFTY 29-Dec-26 25000 CE alert below 30 — ANSWERED 2026-10-09, built (commit 71e495d), live after the deploy step | the one F&O position with money left | 2026-10-09 |
| A25 | Deploy day: Step 1 `bash deploy_vps.sh` (renders cron) · Step 2 positions paste · Step 3 five uploads on the Share Master card · Step 4 confirm the sweep bot's chat list | activates Share Master, sweep, NIFTY alert | 2026-10-09 |
| A20 | Las Vegas trip 10–12 Nov: confirm travellers/origin/class/hotel band, check US visas, then book flight + hotel (briefs/TRIP_LAS_VEGAS_2026-11.md) | money moves = your click | 2026-10-09 |

A22 Mausaji chat name — answered "Bantu Mausaji", Aman 2026-10-09; wired as default.

A21 levels import — evidence 2026-10-09: VPS printed `levels import: 128 rows -> 200`.

Removed items (only on Aman's word): A1 key rotation, A10 Vimal filings check — Aman, chat 2026-10-09 ("forget A1 A10"). A16 Shashank layouts message, A19 Ayush quote request — sent, Aman 2026-10-09. A4 both WhatsApp QRs scanned — Aman 2026-10-09. A2 A3 A5 A17 A18 — evidence 2026-10-09 08:34 UTC: deploy clean on f295e87, alert test sent:true to Aman's phone, amanagrawal.cloud resolves to the VPS IP, aman_setup.sh completed (keys, harden, stash).
