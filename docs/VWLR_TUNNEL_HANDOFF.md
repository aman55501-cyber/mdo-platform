# VWLR tender + FOIS — handoff to the tunnel-machine session

Written 2026-10-07 from the cloud sandbox (no VPN / VPS access). Everything under
"Done" was verified by direct query against Supabase project `vwlr-tender-map`
(`sysicrpylpnzpcuvpvjc`). Everything under "Needs the tunnel machine" was NOT touched.

## Done in the cloud (additive, reversible)

| Item | State |
|---|---|
| `public.fois_snapshots` | Created (migration `fois_snapshots_and_vwlr_score_columns`). RLS on, no policies, so service key only. Empty. |
| `tender_candidates.vwlr_score / vwlr_reason / vwlr_rules_version / vwlr_scored_at` | Added. The scanner's `relevance_score` / `reject_reason` are untouched. |
| `public.vwlr_score(text)` | Scorer v1.1 (migrations `vwlr_score_function_v1`, `..._v1_1_results`). Returns `(score, reason)`. |
| Backfill | All rows scored. Rejected rows kept. Rules version stamp: `v1.1-unverified-vs-config.py`. |
| Tender247 email feed | 13 digests (30 Sep to 6 Oct) parsed. 41 new rows inserted as `source_api='tender247_email'`, with the real printed closing dates. |

## The scorer is [UNVERIFIED]

It was built from `org_profile` plus the July project rules. It has NOT been diffed against
`vedanta_automation/config.py` / `tender_relevance.py`, which were not reachable here.
First job on the tunnel machine: diff them and reconcile. Do not treat v1.1 as the criteria of record.

Known gaps in v1.1 (found by reading the live shortlist, not yet fixed; awaiting owner approval):
procurement/supply, O&M and housekeeping, third-party sampling/analysis, in-plant bunker
cleaning, and "carriage of material" all score as relevant when they should be rejected.
Roughly 6 of 21 live candidates on 2026-10-07 were of this kind.

Fixed in v1.1: `RESULT:` / award notices are closed tenders and score 0 (kept as competitor data).
`corrigendum :` prefix means an amended OPEN tender and is scored with the prefix stripped.

## Findings that matter

1. **Deadline defect confirmed.** 2,733 of 3,102 non-null deadlines (88%) equal the scan date.
   "Closing within N days" from the scanner is fiction. Tender247 email rows carry the real date.
   The scanner's parser (VPS) is where it must be fixed.
2. **The scanner's own score is miscalibrated.** It gave road strengthening, speed breakers,
   fire fighting and structural inspection the same 75 as an RCR haulage tender.
3. **Digest coverage gap.** Each Tender247 digest shows at most 5 tenders in its markup; the rest
   are behind a "view all (N)" link. 16 advertised tenders in the last 7 days were not recoverable
   from email. The email feed is therefore a floor, not the full inflow.
4. `tender247_email` rows set `relevance_score = vwlr_score` because no scanner pass exists for them.

## Needs the tunnel machine (not started)

- Phase 0 recon of `/docker/vwlr` (image vs source drift, trigger mechanism, `.env` key names only,
  what `srv1640993.hstgr.cloud` / `187.127.162.53` is).
- Phase 1: make `scrapers/fois.py` write one `fois_snapshots` row per run, including `status='FAILED'`.
- Phase 3: deploy timers through `mdo-run`, `Persistent=true`, a standing rebuild step, reboot test.
- Phase 4: the one-surface page. Phase 5: kill tests, RUNBOOK, `_log.md`, `OPEN_BOARD.md`.
- Parser fix for the scanner's `deadline` (item 1 above).
- `FOIS_STATION_NAME`: verify against the live portal before touching.

## Owner decisions pending

1. Approve v1.2 reject patterns: `procurement`, `operation and maintenance|o&m`, `housekeeping`,
   `sampling|analysis`, `carriage of material`.
2. Ingest-only daily sync Routine `trig_01HdHtpD1r8D2cfrjUpHdHk5` is paused. Resume or retire it.
3. The ops/sales spec (O0 to O13, Supabase `aman-control-room`) was received but is a separate track
   meant to be run from `/opt/mdo-server`. Nothing in it was started here.

## Acceptance output (2026-10-07)

Score distribution after v1.1: 0 = ~3,105; 95 = 2; 90 = 16; 82 = 8; 80 = 1; 68 = 18 (before the 41 email rows).
Live-deadline shortlist after email ingest: 21 rows score above 0; about 15 look genuine.
