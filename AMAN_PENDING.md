# Aman's pending list — the clicks that unlock the fleet

Rule (Aman, chat 2026-10-09): the CoS shows this list in every status message, carries every item
over, and removes an item only when Aman says so. Never trimmed by housekeeping.

| # | Item | Why it matters | Since |
|---|---|---|---|
| A6 | claude.ai environment SECRETS (laptop, Settings → Environments → Default Cloud Environment → Edit): MDO_SELF_URL, MDO_AUTH_TOKEN, VAULT_TOKEN, TENDER_INBOUND_TOKEN, GROK_CONTEXT_TOKEN, VAULT_BACKUP_PASSPHRASE. Domains DONE via Cowork 2026-10-09. | cloud Routines can reach the VPS | 2026-10-08 |
| A7 | Routines: DONE via Cowork 2026-10-09 except "Weekly memory sync" (exists, trig_01E3cCjuc9x35eYPvwtoWbQA, further down the list) → attach repo. Also decide: pause the 11 legacy Routines (CoS 1/2/3 hourly loop, Md morning brief, networth, investment book, F&O report, post-close wrap, hotel CV watch, Vedanta tender scan, Share Master refresh, Singhvi capture) — duplicates of the VPS fleet, 7 of them failing daily, the hourly sweep burns credits 14×/day | without sources the Routines run blind | 2026-10-08 |
| A8 | Grok is OPTIONAL and not needed for Tender247: your Tender247 alerts already arrive in Gmail and the mail reader now files them (2026-10-10). Grok subscription only adds GeM / Coal India / NTPC portal sweeps; decide later | extra coverage only | 2026-10-09 |
| A9 | PAUSED 2026-10-09: all cloud Routines disabled on Aman's word. When un-pausing, say **haiku** or **keep** for the model of the cheap Routines | cost per run ÷ 20 | 2026-10-09 |
| A11 | One CoS. Cowork run 2026-10-09: PC has nothing to retire (no scheduled task, no loop; Grok Bot shortcut is a manual launcher). Notion: say "yes" in Cowork to stamp "Retired 2026-10-09: the VPS fleet is the CoS" on 4 pages (CoS Board, Grok Desks manual, Claude CoS Handoff, Grok→Claude relay). Then A11 closes | two systems in parallel waste credits | 2026-10-09 |
| A12 | WITHDRAWN by Aman 2026-10-09 ("compliance deadline questions unnecessary; statutory dates, remind me a week before"). Replaced by the compliance-reminder bot (built 2026-10-09: statutory calendar data/compliance_calendar_in.json, daily 08:00 IST 7-day WhatsApp message, Mon 08:05 "this week" line, zero LLM; live after the cron render in A25). Later: entity list with kinds after A15 → POST /api/compliance/entities | compliance objective | 2026-10-09 |
| A13 | Bot targets table: reply row number + ok/edit; the five people whose reply time matters. ANSWERED 2026-10-09: idle threshold = 1 hour; watched chats = Bantu Mausaji, Vedanta Daily Report, Washery Civil Update, Ans Management, VWLR Indent Planning, Core Group (priorities later); classifier KILLED (dead entry removed, commit 71e495d) | pulse and ops-hourly tuning | 2026-10-09 |
| A14 | Vision session, 30 min, VISION_INTAKE.md blocks 2–4 | top-line objectives the bots run toward | 2026-10-08 |
| A15 | Vault import from the laptop (`_memory` folder + Family_Finance_Master.xlsx) via scp + vault_import.sh; then Shares CFO reconnect | memory and finance bots have nothing to read | 2026-10-08 |
| A23 | Angel One holdings export (CSV) for the Share Master Portfolio tab; HDFC ×4 received 2026-10-09 | Portfolio tab incomplete without it | 2026-10-09 |
| A24 | NIFTY 29-Dec-26 25000 CE alert below 30 — ANSWERED 2026-10-09, built (commit 71e495d), live after the deploy step | the one F&O position with money left | 2026-10-09 |
| A25 | Deploy day DONE 2026-10-09 12:30 UTC: b9ba16f live, 156 tests, 26 cron jobs, bridges connected, alert sent. 331 holdings across 5 holders + 20 positions loaded. Left: Step 4 confirm the sweep bot's chat list (first WhatsApp line 18:00 IST) | everything built today is running | 2026-10-09 |
| A26 | Connectors: C1 Gmail app password → VPS .env · C2 Drive sync of BUSINESSES · C3 say "calendar on" · C4 Tally monthly export · C5 five skills on · C6 plugin packs off (baby steps in chat 2026-10-09) | bots read mail, files, books; fewer clicks | 2026-10-09 |
| A27 | Deploy 2 (self-deploys once A32 is yes; the manual run is only needed for the new cron lines): `bash deploy_vps.sh` (582fbf3: corp-actions, tenders-direct, voice, calendar feed, health check; 4 new cron lines, bridges to v2.2) | switches on the seven needle-movers | 2026-10-09 |
| A28 | UptimeRobot keyword monitor on https://amanagrawal.cloud/api/health/public, keyword "ok":true, 5 min, alerts to email + app (DEPLOY_HOSTINGER §8a) | the alarm that fires when the fleet itself is dead | 2026-10-09 |
| A29 | Google Calendar → Other calendars → From URL → paste the calendar feed URL printed by deploy (DEPLOY_HOSTINGER §8b) | compliance, expiries, Vegas on the phone | 2026-10-09 |
| A30 | HDFC API keys for 4 accounts via Cowork prompt (chat 2026-10-09) | ends CSV uploads | 2026-10-09 |
| A32 | Reply **yes** so the fix also lands on the branch the VPS tracks (`claude/chief-of-staff-bot-4i2jyz`); this session may push only to `claude/nifty-darwin-j8xylv`. Until then nothing built since 2026-10-09 evening is live | unblocks A27 with zero VPS clicks: self-deploy picks it up in 10 min | 2026-10-10 |
| A20 | Las Vegas trip 10–12 Nov: confirm travellers/origin/class/hotel band, check US visas, then book flight + hotel (briefs/TRIP_LAS_VEGAS_2026-11.md) | money moves = your click | 2026-10-09 |

A22 Mausaji chat name — answered "Bantu Mausaji", Aman 2026-10-09; wired as default.

A21 levels import — evidence 2026-10-09: VPS printed `levels import: 128 rows -> 200`.

Removed items (only on Aman's word): A31 Jaiprakash Associates — Aman 2026-10-10 ("forget click 1"; the row stays unpriced); A33 GRAPHITE sell level — Aman 2026-10-10 ("forget graphite sell level"); A29 calendar — Aman 2026-10-10 ("calender done"); A1 key rotation, A10 Vimal filings check — Aman, chat 2026-10-09 ("forget A1 A10"). A16 Shashank layouts message, A19 Ayush quote request — sent, Aman 2026-10-09. A4 both WhatsApp QRs scanned — Aman 2026-10-09. A2 A3 A5 A17 A18 — evidence 2026-10-09 08:34 UTC: deploy clean on f295e87, alert test sent:true to Aman's phone, amanagrawal.cloud resolves to the VPS IP, aman_setup.sh completed (keys, harden, stash).
