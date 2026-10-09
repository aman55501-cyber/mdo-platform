# Aman's pending list — the clicks that unlock the fleet

Rule (Aman, chat 2026-10-09): the CoS shows this list in every status message, carries every item
over, and removes an item only when Aman says so. Never trimmed by housekeeping.

| # | Item | Why it matters | Since |
|---|---|---|---|
| A2 | DNS: `dig +short amanagrawal.cloud` must equal `curl -s4 ifconfig.me`; else add A records for `amanagrawal.cloud` and `www` | dashboard on your own domain | 2026-10-09 |
| A3 | `.env`: `ALT_DOMAINS=amanagrawal.cloud www.amanagrawal.cloud` and `NEXT_PUBLIC_API_URL=https://amanagrawal.cloud`, then `docker compose up -d caddy && FORCE_FRONTEND=1 bash deploy_vps.sh && docker compose up -d whatsapp2` | Caddy serves the new name, app calls it | 2026-10-09 |
| A4 | Scan both WhatsApp QRs on `/ops-feed` (phone 1 = account 1, phone 2 = account 2) | the fleet's only mouth and ears; nothing reaches you until then | 2026-10-08 |
| A5 | `.env` keys: GROK_API_KEY, VAULT_BACKUP_PASSPHRASE, VAULT_TOKEN, TENDER_INBOUND_TOKEN, GROK_CONTEXT_TOKEN (generated if blank), HDFC_API_KEY/SECRET; then `docker compose up -d backend whatsapp whatsapp2` | x-watch, Singhvi, weekly bundle, doors | 2026-10-08 |
| A6 | claude.ai environment secrets: MDO_SELF_URL=https://amanagrawal.cloud, MDO_AUTH_TOKEN (rotated), VAULT_TOKEN, TENDER_INBOUND_TOKEN; allowed domains amanagrawal.cloud + srv1641037.hstgr.cloud | cloud Routines can reach the VPS | 2026-10-08 |
| A7 | Routines page, attach: Gmail + repo → "Grok inbox relay"; Google Drive + repo → "Backup off-site"; repo → "Chief of Staff daily", "Weekly memory sync", "Weekly finance update (cloud, vault)", "Credit guard" | without sources the Routines run blind | 2026-10-08 |
| A8 | Gmail draft "Grok tasks v2": paste the two blocks into Grok's scheduler with the GROK_CONTEXT_TOKEN; log in to Tender247 once in Grok's browser | Singhvi + Tender247 feed | 2026-10-09 |
| A9 | Say **haiku** (or not) for the credit guard and Grok relay Routine model | cost per run ÷ 20 | 2026-10-09 |
| A11 | Decide on the three CoS systems: keep this fleet as the one CoS, Notion as the board it writes to, retire the PC "CoS box" loop and Grok desks' CoS role (briefs/NOTION_CONTROL_ROOM.md §6) | two systems in parallel waste credits and contradict each other | 2026-10-09 |
| A12 | Answer the 10 questions in briefs/COMPLIANCE_CALENDAR_REVIEW.md; mark which filings are yours vs Vimal's | compliance-sentinel objective | 2026-10-09 |
| A13 | Bot targets table: reply row number + ok/edit; the five people whose reply time matters; idle threshold hours (default 2); keep or kill the old `classifier` bot | pulse and ops-hourly tuning | 2026-10-09 |
| A14 | Vision session, 30 min, VISION_INTAKE.md blocks 2–4 | top-line objectives the bots run toward | 2026-10-08 |
| A15 | Vault import from the laptop (`_memory` folder + Family_Finance_Master.xlsx) via scp + vault_import.sh; then Shares CFO reconnect | memory and finance bots have nothing to read | 2026-10-08 |
| A16 | Send the Shashank Nashine WhatsApp (final urgent draft, chat 2026-10-09) for the hotel floor layouts PDF + CAD today | hotel objective, time-sensitive | 2026-10-09 |
| A17 | Run `bash vps_harden.sh` once on the VPS; reboot after | firewall, fail2ban, security updates | 2026-10-09 |
| A18 | Review and drop the old VPS stash: `git stash show -p stash@{0}` | leftover local Dockerfile edit | 2026-10-08 |
| A19 | Send the Ayush (Sultania) quote request for curcumin 95% + boswellia 65%, 500 kg FOB (draft in chat 2026-10-09) | botanicals G0 lane; contact was HELD, Aman's send = approval | 2026-10-09 |
| A20 | Las Vegas trip 10–12 Nov: confirm travellers/origin/class/hotel band, check US visas, then book flight + hotel (briefs/TRIP_LAS_VEGAS_2026-11.md) | money moves = your click | 2026-10-09 |

Removed items (only on Aman's word): A1 key rotation, A10 Vimal filings check — Aman, chat 2026-10-09 ("forget A1 A10").
