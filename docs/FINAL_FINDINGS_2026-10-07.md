# VWLR tender + FOIS — final findings (draft)

7 Oct 2026. Everything here was checked directly against Supabase unless marked [UNVERIFIED].

## Bottom line
- The data pipeline is alive. The scoring and the deadlines are what you can't trust yet.
- The scanner's relevance score is badly miscalibrated.
- 88% of scanner deadlines are fake (they equal the scan date).
- Nothing was run on the VPS. I have no route to it from the cloud session.

## What is done (cloud only, reversible)
- `fois_snapshots` table created. RLS on, service key only, empty until the VPS writes to it.
- `vwlr_score` / `vwlr_reason` columns added beside the scanner's own score. Scanner columns untouched.
- Scorer `vwlr_score()` v1.1 applied to every row. Rejected rows kept.
- 41 new tenders ingested from the Tender247 email feed (13 digests, 30 Sep to 6 Oct), with real closing dates.
- Earlier: expired tenders now purge themselves every 15 min (pg_cron). The web dashboard no longer shows expired ones.
- Handoff doc committed: `docs/VWLR_TUNNEL_HANDOFF.md`.

## Findings
1. Scanner score is unreliable. It gave road strengthening, speed breakers, fire fighting and structural inspection the same 75 as an RCR haulage tender.
2. Deadline defect confirmed: 2,733 of 3,102 deadlines equal the scan date. "Closing within N days" from the scanner is fiction. Only the email rows carry real dates. The fix belongs in the scanner's parser on the VPS.
3. Email coverage gap: each digest shows only 5 tenders in its markup. The rest sit behind a "view all" link. 16 advertised tenders in the last 7 days could not be recovered. The email feed is a floor, not the full inflow.
4. `RESULT:` rows are award notices for closed tenders. Now scored 0 and kept as competitor data.
5. `corrigendum :` means an amended tender that is still open. Now scored with the prefix stripped.

## Current shortlist quality
- 21 live-deadline candidates score above 0. About 15 look genuine, e.g. WCL Junad coal transport, SCCL GDK to OCP-1, MCL payloaders to siding, RVUNL rate contract.
- About 6 are not coal logistics: SCCL conveyor-belt procurement, MPPGCL CHP O&M and housekeeping (Rs 89 Cr), MPPGCL coal sampling, MSPGCL bunker cleaning, SECL "carriage of material" underground, and APGENCO manual wagon unloading (borderline).
- The scorer is [UNVERIFIED]. It was built from your org profile and the July rules. It has not been diffed against `config.py`, which I could not reach.

## Not done
- Anything on the VPS: image-vs-source drift check, `fois.py` writing snapshots, systemd timers via `mdo-run`, the one-surface page, the reboot test, the RUNBOOK.
- The second VPS (187.127.162.53) was not identified.
- `FOIS_STATION_NAME` was not touched. It must be checked against the live FOIS portal first.
- Your ops/sales spec (O0 to O13) was received and not started. It is written for a session at `/opt/mdo-server`.
- Eligibility verdicts: the tender portals return 403 from here, so thresholds can't be read. They need pasted NIT clauses.
- I did not confirm the Android app picks up the dashboard fix. It refreshes only on tap or cold start.

## Decisions for you
1. Say "apply v1.2" to reject: procurement, O&M, housekeeping, sampling, carriage of material. I held off because you said not to tune your criteria silently.
2. The daily sync Routine is still paused. Resume or retire it.
3. Move the VPS phases and the ops/sales spec to Claude Code on the tunnel machine. Point it at `docs/VWLR_TUNNEL_HANDOFF.md`.

## First three jobs on the tunnel machine
1. Diff `config.py` and `tender_relevance.py` against `vwlr_score()` and reconcile.
2. Fix the scanner's `deadline` parser.
3. Make `fois.py` write one `fois_snapshots` row per run, including `FAILED` rows with the error text.
