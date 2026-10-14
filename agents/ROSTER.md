# Virtual professionals: roster

Principle: each one is a QC/analysis layer over a human. It reads what the groups and folders already produce, checks it, and reports
every run (including "0 new"). It never files, pays, signs or messages anyone but Aman. Humans own sign-off.

Group names below are the ones named in `mdo_server.py` (CHECKS_SEED). The real group list is UNVERIFIED until
`scripts/wa_analyze.py` runs against the live database (see WORKLIST P11).

| # | Professional | Build now? | Reads | Produces | Human who signs off |
|---|---|---|---|---|---|
| 1 | Civil QC engineer | YES | "Ans Hotel civil", "Vedanta washery- Civil Works", "ROAD BRIDGE WORK VEDANTA KUNKUNI" + Drive SITE_QC/ | deviations vs drawing/BOQ/IS codes, bill-vs-verified check | Structural engineer (structural items); Aman for payment |
| 2 | Accounts analyst (assists the hired controller) | YES | Vimal/bank statements in Drive, payment/bill photos from groups, BANK_STATEMENT_REQUEST, MISSING_DOCS_CHECKLIST | reconciliation drafts, GST/TDS calendar, inter-company tracker, payment batches prepared for Aman | CA Vimal / the Controller; Aman releases money |
| 3 | Dispatch & rake controller | YES | "Vedanta Daily Report", "VWLR RAKE PLACEMENT", "VWLR - RKM GROUP", "LOADER REPORT VWLR" | placed vs dispatched, trend vs 7-day average, demurrage risk (checks `dispatch_rakes`, `dispatch_trend`) | Site head |
| 4 | Compliance clerk | YES | compliance_filings, CA replies, notices | due-date board that is real, overdue list | CA Vimal files; Aman clicks regulator actions |
| 5 | Tender analyst | LATER | public portals + BUSINESSES/vedanta_automation/config.py (eligibility) | eligible-tender shortlist with closing dates | Aman |
| 6 | Hotel ops analyst | LATER | "Daily Sales Report" (auto-parsed to hotel_daily) | occupancy/RevPAR trend, contract-negotiation numbers for Guptasons | GM Hotel ANS |
| 7 | Equipment maintenance | LATER | "VWLR Machine Update" | breakdown log, repeat-failure list | Site head |

Pushback: build 1-4 only. Seven agents is seven things to babysit; 5-7 add reports before there is anyone to act on them.

Each is a Cowork project with: a standing instruction file (see `agents/civil-qc/INSTRUCTIONS.md` as the template), an intake folder, and a
scheduled daily run using `agents/AUTONOMY_ROUTINE_PROMPT.md`. Humans still needed (a virtual professional cannot be the signatory):
structural engineer, the CA/Controller, the site head.
