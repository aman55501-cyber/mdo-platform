# Tender247 Missed Opportunities — what the 320 tell us (2026-10-12)
Source: Tender247_Missed_Opportunities.xlsx (export of 11 Oct 2026; filter 1 Jan 2024 - 31 Oct 2026; 324 tenders, 4 civil removed, 320 left, Cowork prepared the sheets). Caveats in the file itself: bidder lists partial where Tender247 shows "view all (N)"; EMD, publish date and duration are not in the export; mine and plant are parsed from titles. Close dates run 1 Jan 2025 - 6 Oct 2026.

## The finding that matters
**None of the 320 could have been caught by an alert, because no alert was set** ("Alerts: None set" in the file's Summary). Three faults in a row:
1. No keyword or competitor alert in the Tender247 portal.
2. The alert e-mails that do arrive list only 5 tenders and say "view all (N)" (known since 10 Oct).
3. Tenders that reach our pipeline are stored as "evaluating", and the old deadline reminder only looked at "active" - so no reminder could ever fire.
All three are now fixed or have a fix below. Nothing in the file can be bid on today: every tender closed by 6 Oct 2026 (230 awarded, 81 at financial-bid stage, 9 technical).

## What was missed
| Group | Count | Median award | Cheap to enter (<= Rs 10 cr) | Who wins |
|---|---|---|---|---|
| Coal transport by road | 116 | Rs 18.7 cr | 33 of 85 awarded | Variant Commercial, Nakul Tiwari |
| **RCR / siding transport** | 71 | **Rs 8.0 cr** | **28 of 46** | Swami Fuels, Chandan Kumar Singh |
| Coal supply | 39 | Rs 210 cr | 1 of 21 | Mohit Minerals (5 wins), Smartgen |
| **Loading / handling / crushing** | 34 | **Rs 5.4 cr** | **17 of 27** | Govinda Enterprises, United Coal Carriers |
| Mining services (OB, extraction) | 31 | Rs 379 cr | 2 of 27 | KVRR, JARPL-AT |
| Other / biomass / washery | 29 | small | - | - |
Reading: your realistic first-year targets are **RCR / siding transport and loading / handling / crushing** (median award Rs 5-8 crore, 45 of 73 awarded ones at or under Rs 10 crore). **Coal supply (median Rs 210 crore) and mining services (Rs 379 crore) belong to a handful of big players**; watch them for intelligence, do not chase until the washery has a record.
- Buyers: NTPC 73 (23%), SECL 49, WCL 41, CCL 36, then MCL 13, NCL 11. Four buyers are 62% of everything. Core families alone: NTPC 43 of 115.
- Places: Jharkhand 63, Chhattisgarh 60, Maharashtra 46, Madhya Pradesh 45, Orissa 35. SECL's 49 are mostly Korba, Surguja, Anuppur, Korea (3 in Raigarh).
- Rivals: a tracked competitor bid on 188 of the 320 (59%). The median tender had 9 bidders - these are not quiet tenders. Most frequent bidders: Godavari Commodities (60), G K Associates (40, 5 wins, Rs 375 cr), Mohit Minerals (24 bids, 5 wins, Rs 794 cr), Anoop Road Carriers (19, 0 wins).
- Wins are concentrated: Caliber Mining (2 wins, Rs 2,948 cr), Mohit Minerals, Indermani (Rs 513 cr), G K Associates.

## What is now in place (live after the next deploy)
- **tender-radar bot** (08:00 and 14:00 IST daily, WhatsApp, every run reports): tier A = coal supply, RCR / siding, washery, loading / handling / crushing: reminder at 7, 3, 1 and 0 days; tier B = mining services, road transport: 3 days and 0; civil, construction, biomass and repair are never reminded; a tender that closed with no decision is named once. Preferred states and 42 rival names are flagged.
- Commands on WhatsApp: **tenders** (what is open), **bid 42**, **skip 42**. Filing a bid stays your click on the portal.
- The five tenders already in the pipeline (closing 13, 15, 20, 27 and 30 Oct) get their first reminders in today's run.

## What still needs the portal (Cowork prompt: briefs/COWORK_TENDER247_ALERTS.md)
Tender247 only emails what you set in its Alerts. The file's Alert plan (5 keyword groups, 1 exclusion, 42 competitor names) is "pending approval" - say "approve alerts" and run the prompt. Alerts attach to live tenders only.
Risk of too many alerts: noise. The exclusion list and the tiers are there to keep the daily mail short; review the first week.
