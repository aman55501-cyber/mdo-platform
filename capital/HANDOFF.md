# Capital desk — hand-off report (written 7 Oct 2026, for the next session)

Read this first. It says what exists, what was actually verified, what was not, and what to do next.
Scope is shares and capital only. Operations, sales and comms are a separate track (OPERATIONS_SALES_COMMS_TASKS.md).

## 1. What exists
**App** `capital/` (FastAPI, server-rendered, own `Dockerfile.capital`, `requirements_capital.txt`):
Desk (gainers, losers, trade ideas, Bantu Mausaji's calls) is the opening page and carries no rupee totals.
Holdings, Net worth (behind a PIN; fails closed with no PIN), Health. HTTP Basic on every route except `/healthz`.
Read-only database session. No code path sends messages or places orders.
**Jobs** `capital/jobs/parse_calls.py` (his WhatsApp calls -> `wb.calls`) and `quote_poll.py` (intraday quotes -> `wb.quotes`).
**Database** (applied to Supabase `aman-control-room` / `gogtdnlknbmhdvunpeqo`; source in `capital/migrations/`, undo script alongside):
tables `wb.portfolio_owner`, `manual_holdings`, `quotes`, `calls`, `target_history` (+ audit trigger on `wb.targets`);
views `holdings_raw`, `price_now`, `holdings_view`, `held_symbols`, `ideas_view`, `calls_view`, `desk_hidden`, `actions_view`,
`balance_latest`, `net_worth_lines`, `by_bucket`, `desk_freshness`. It reuses `public.holdings` (Angel pull) and `public.desk_ideas`;
there is no second holdings table. Data rows added: one `portfolio_owner` row (A1504046 -> aditi_inv), two inactive `job_schedule`
rows (bantu_calls, quote_poll), one open question in `wb.conflicts`.
**Tests** `tests/test_capital_app.py`, `tests/test_capital_jobs.py` (38). With LIFEOS: 84 pass.

## 2. Verified, and how
- Views on live data: 73 Angel holdings, priced, owner aditi_inv. Held-check: marking VAML held inside a rolled-back transaction hid that idea and
  raised the removed count to 1; after rollback, nothing remained.
- Bantu parser on his real message formats (entry range, stop, multi-line targets, horizon; ignores news, links, chat).
- App behaviour against a fake database; 390px width has no sideways scroll (light and dark); login + PIN flow over real HTTP locally.
- Advisor: no new warnings from these objects.

## 3. NOT verified
- The app has never connected to the real database (no DATABASE_URL here). The SQL it runs was checked through the Supabase tool instead.
- `quote_poll` has never run against the live Angel API. Endpoint and field names follow Angel's documented quote API.
- Neither job is installed on the server. The app is not deployed. Nothing about the VPS was touched from this session.

## 4. Live snapshot (7 Oct ~12:30 IST)
Healthy: heartbeat, pull-holdings (holdings pulled ~5h ago), deadman_check, wa_bridge_heartbeat, wa2 (888 messages, live).
Dead: wa1 (no message for 268h; last 26 Sep), mdo_agent_hourly/daily (backend still crash-looping on the mcp 2.x API; Mechanism B never built).
Telegram: bot @amancoo_bot is live, but every `wb.channel_map` row is still EMPTY (no chat/topic ids), so no alert can be delivered.
`wb.outbox` has 61 failed rows in 24h, all "no token / no chat id" noise from the deadman retrying every 20 minutes.
When channel_map is filled, the first deadman page will list 3 DEAD jobs at once (wa1_sync, mdo_agent_hourly, mdo_agent_daily).
Counts: calls 0, manual_holdings 0, targets 0, quotes 0. Bantu chat last message 273h ago.
Open questions: Aditi Investments holdings personal vs company; HDFC 2231 / 5555 owner and type.

## 5. Decisions and why
- Reused existing tables instead of building `holdings_snapshot`: the Angel pull already fills `public.holdings` daily.
- The app talks to Postgres directly with DATABASE_URL (session pooler), because `wb` is not exposed over the REST API.
- Net worth is its own PIN page and says "partial" with a list of gaps. It never presents a confident total.
- Plan levels flag only exact crossings; no invented "near" threshold. No levels exist yet.
- `levels.yaml` (24 Apr, mostly NIFTY/blue-chips) was deliberately NOT imported as plan levels: stale.
- Jobs ship inactive in `wb.job_schedule` so the deadman does not page for jobs that are not deployed.
- Chosen without an answer from the owner: calls parsed automatically; movers cover holdings only; Net worth has a PIN.

## 6. Gotchas learned
- The Supabase migration tool waits for a confirmation on any statement containing DROP and then times out here. Use `create or replace`.
- Keep each migration small; two large ones timed out at 60s.
- `grep -rE "(sk-|ghp_|AIza|password\s*=|token\s*=)"` must stay clean: avoid variable names like `x_token =`.
- Do not use `pkill -f` with a pattern that appears in your own command line.
- Holdings are pulled ~07:45 IST, before the market opens, so day-change is the last completed move until quote_poll runs.
- The HDFC demats (Aman, Sudha, Ashok) are not in the system. The held-check and net worth cannot see them.

## 7. Next steps, in order
1. Owner supplies HDFC holdings (or the export) -> ingest, or fill `wb.manual_holdings` meanwhile.
2. Deploy per `capital/DEPLOY.md`: set DATABASE_URL, CAPITAL_USER/PASSWORD/PIN/COOKIE_SECRET; HTTPS only.
3. Run `python3 -m capital.jobs.quote_poll --force` once by hand on the server and read the output before enabling cron.
4. Install both cron lines; then `update wb.job_schedule set active = true where job in ('bantu_calls','quote_poll');`.
5. Re-link wa1 (QR) so Bantu's calls resume. Finish the Telegram handshake (fill `wb.channel_map`).
6. Resolve the two open questions above.
7. Then the rest of the task file: bank-alert parsing, statements and reconciliation, liabilities, backups, evidence links on every figure.


## 8. Added 7 Oct (later)
- Held stocks are **marked, not hidden** (migration `0002_show_held_up.sql`; undo with `_down`). Ideas and calls carry a `held` flag.
- New **Daily login** tab (`capital/daily_login.py`): needs `CAPITAL_CFO_URL` + `CFO_API_TOKEN`.
- Parser fixed against the real Bantu formats (closing `*` before `@`, `to` ranges, `STOP-LOSS #`, "3 to 6 months", "Added more.").
  It also re-matches earlier unresolved names when the ticker list arrives.
- `wb.calls` backfilled with 10 calls (ids 1-10, `needs_review = true`; unresolved tickers). Messages 32, 179, 237 are chat, not calls.
- Backend crash (`mdo_brain.py` vs `mcp 2.x`): the file is **not in this repo**; fix is on the VPS checkout, see runbook. Unverified.
