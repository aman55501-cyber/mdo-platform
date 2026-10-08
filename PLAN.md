# Plan: The Decision Feed — one place decisions arrive, with one tap to act

**One-line goal:** Findings from every domain — capital, VWLR, hotel, compliance — stop
living in two apps and start arriving as a single threshold-gated feed on Aman's phone,
each item carrying a drafted action he approves with one tap.

## Classification

Track: **Feature** — code exists and this adds a capability to it (merged MDO + Shares CFO
tree). Parked secondary asks: full UI consolidation of Shares CFO's server-rendered
terminal into the Next.js app (named, deferred — v1 unifies the *decision path*, not every
screen); the React Native `mobile/` app (untouched in v1).

## Interview Ledger

- **Q1** feed vs chat as v1 → *the one feed*, threshold-gated push (accepted recommendation)
- **Q2** inform-only vs propose-and-approve → *propose-and-approve*, money actions excluded (accepted)
- **Q3** approve in-notification vs deep-link into app → *deep link*, honouring the 2026-04-25 decision log entry (accepted)
- Human then delegated all remaining forks ("I will follow all your recommendations") — everything below is default-and-tagged in the Assumptions Ledger.

**Questions spent: 3 of 14.**

## Goal & Success Criteria

- G1. One surface: Aman opens **one** page (`/feed`) to see everything that needs him, across
  capital and business. Measured: places opened per morning goes from 2 apps + WhatsApp to 1.
- G2. Nothing that matters waits to be discovered: a `critical` item reaches his phone
  unprompted within one agent cycle of being detected.
- G3. Nothing that doesn't matter interrupts: an item that repeats inside its cooldown window
  is suppressed, not re-pushed. Measured: zero duplicate pushes for the same `key` in cooldown.
- G4. A decision costs one tap: an approved item's action executes and is audited, without
  Aman writing anything.
- G5. Money never moves without a deliberate, separate switch-on. Measured: an action of kind
  `money` cannot execute in v1 even when approved — it is recorded and refused.

## Current State

- Merged tree: MDO + Shares CFO in one repo, one compose stack, 29/29 tests pass (verified:
  this session's merge commit `11ec9c5`, `pytest tests/ -q`).
- Two front doors: `mdo-app/` Next.js with 17 pages; Shares CFO serves its own HTML
  (`shares_cfo/terminal.py`) plus a separate React Native app in `mobile/` (verified:
  `find mdo-app/app -name page.tsx`, `shares_cfo/terminal.py`).
- Two LLM layers: `mdo_brain.py` exposes 22 tools; `shares_cfo/mcp_server.py` exposes 15.
  Exactly one of MDO's 22 (`get_portfolio`) reaches capital (verified: `mdo_brain.py` TOOLS).
- Two push paths already exist: `shares_cfo/proactive.py` (market-hours background task →
  ntfy/Telegram, with per-key dedup + cooldown) and `mdo_server.py:_send_whatsapp()` → WhatsApp
  self-message (verified: those files).
- A cadence check registry and agent runtime exist: `checks` table + `mdo_agent.py`, filing into
  `agent_reports` and `intel_items` (verified: `mdo_server.py` schema, `mdo_agent.py`).
- A complete Telegram approve/reject inline-keyboard loop exists but is legacy and deprecated by
  owner decision (verified: `vega/telegram_bot/handlers.py:610-620`; `MDO_VISION.md:450`).
- 198 HTTP endpoints across the two backends (verified: route counts over `mdo_server.py`,
  `shares_cfo/server.py`).

## Scope (v1)

The decision path only: **detect → dedup → push → deep link → approve → execute → audit.**
One new module (`mdo_feed.py`), its routes, one new page (`/feed`), one unified notifier, and
the capital tools the brain currently can't reach.

## Out of Scope & Parked Items

- Consolidating Shares CFO's terminal UI into Next.js — big, cosmetic-adjacent, and doesn't
  serve the decision path. Parked by name.
- The `mobile/` React Native app — not rewired in v1; `/feed` is responsive and reachable in a
  phone browser.
- Any money-moving action — refused by policy in v1 (G5), not merely unbuilt.
- Meta WhatsApp Business API migration — the Baileys bridge is what exists; unchanged.
- Retiring `vega/` — untouched; its Telegram bot stays dormant per the decision log.

## Approach

A single feed table is the spine. Producers (the agent runtime, CFO's proactive watcher, any
check) call one function, `publish()`, instead of each inventing its own alerting. `publish()`
owns dedup, cooldown and severity — the discipline `shares_cfo/proactive.py` already proved,
lifted to serve both halves. Severity decides delivery: `critical` pushes immediately,
`important` batches into a digest, `info` waits in the app.

Each item may carry a **proposed action** — a typed, JSON-payload instruction with a *kind*:

| Kind | Meaning | v1 policy |
|---|---|---|
| `internal` | changes only our own data (file a task, file intel) | executes on approval |
| `outward` | reaches a real person (a WhatsApp message) | executes on approval, full text shown on the confirm screen first, always audited |
| `money` | moves money or places an order | **refused on approval** — recorded, never executed |

The push carries a deep link to `/feed/<id>`; approval happens in the app (Q3). Executor's
choice: internal module layout, component structure, CSS specifics.

## Requirements

- **R1.** WHEN a producer calls `publish()` with a `key` already published inside that
  severity's cooldown window THE SYSTEM SHALL suppress the new item and record the suppression,
  not create a duplicate. *Check: `test_dedup_within_cooldown`.*
- **R2.** WHEN cooldown has elapsed for a `key` THE SYSTEM SHALL publish a fresh item.
  *Check: `test_republish_after_cooldown`.*
- **R3.** WHEN an item is `critical` THE SYSTEM SHALL mark it for immediate push; `important`
  for digest; `info` for silent. *Check: `test_notify_policy`.*
- **R4.** WHEN an item carrying an `internal` action is approved THE SYSTEM SHALL execute the
  registered handler and record status `executed` with its result. *Check: `test_approve_executes_internal`.*
- **R5.** WHEN an item carrying a `money` action is approved THE SYSTEM SHALL refuse execution,
  set status `refused`, and write an audit row naming the policy. *Check: `test_money_action_refused`.*
- **R6.** WHEN an item is rejected THE SYSTEM SHALL never execute its action and SHALL record
  the rejection. *Check: `test_reject_never_executes`.*
- **R7.** WHEN an action handler raises THE SYSTEM SHALL record status `failed` with the error
  and SHALL NOT lose the item. *Check: `test_failed_action_is_recorded`.*
- **R8.** THE SYSTEM SHALL write an append-only audit row for every state change of every item.
  *Check: `test_audit_trail_is_appended`.*
- **R9.** THE SYSTEM SHALL expose the feed at `GET /api/feed`, one item at `GET /api/feed/{id}`,
  and decisions at `POST /api/feed/{id}/approve|reject`, all behind the existing `X-MDO-Key`
  middleware. *Check: routes respond; auth inherited from `mdo_server.py` middleware.*
- **R10.** THE SYSTEM SHALL let the brain answer capital questions with the same depth the
  capital surface has — not a single summary keyhole. *Check: `test_brain_has_capital_tools`.*

## Key Decisions

- v1 shape: threshold-gated push feed, not a chat surface — (user, Q1)
- Alerts carry drafted actions approved in one tap — (user, Q2)
- Approval happens in-app via deep link from the push — (user, Q3; corroborated by `MDO_VISION.md:450`)
- Money actions refused in v1 — [assumed: default from Q2's "money excluded" — if wrong: flip
  `MONEY_ACTIONS_ENABLED`, which gates one branch in `decide()`]
- Product name "Decision Feed", module `mdo_feed.py`, route `/feed` — executor's choice
- Reuse the existing SQLite DB rather than adding a store — [A2]
- Notification channel: every configured channel, best-effort — [A1]

## Data & State Changes

Two new tables in the existing `vega_data.db` (created idempotently by `ensure_schema()`,
matching the `CREATE TABLE IF NOT EXISTS` convention already used for all 21 tables):

- `feed_items` — `id, key, source, domain, severity, title, body, evidence_json,
  action_type, action_payload_json, action_kind, status, notified_at, decided_at, decided_by,
  executed_at, result, created_at, updated_at`
- `feed_audit` — `id, item_id, event, detail, at` (append-only)

No migration needed: additive tables only, no existing table altered. Rollback = drop the two
tables; nothing else reads them.

## Interfaces, Integrations & Credentials

- Exposed: `GET /api/feed`, `GET /api/feed/{id}`, `POST /api/feed/{id}/approve`,
  `POST /api/feed/{id}/reject`, `POST /api/feed/publish`, `GET /api/feed/digest`,
  `POST /api/feed/notify-pending`.
- Consumed: the Shares CFO service via the existing `_cfo_get()` bridge at `${CFO_API_URL}`
  with `${CFO_API_TOKEN}` (verified: `mdo_server.py:814-827`).
- Notification channels, all optional, all best-effort: `${ALERT_WHATSAPP_TO}` +
  `${WA_BRIDGE_URL}` (existing), `${CFO_NTFY_TOPIC}`, `${CFO_TELEGRAM_BOT_TOKEN}` +
  `${CFO_TELEGRAM_CHAT_ID}` (existing, verified: `shares_cfo/notify.py`).
- New: `${MDO_APP_URL}` — public base URL used to build the deep link.
- Fixed contract: `X-MDO-Key` auth middleware applies to all new routes automatically; the
  frontend's patched `fetch` already attaches it (verified: `mdo-app/components/AuthGate.tsx`).

## Edge Cases & Failure Handling

- Notifier unreachable / no channel configured → item still stored and visible in the app;
  send result recorded. Never blocks publication.
- Action handler raises → status `failed`, error recorded, item retained (R7).
- Approving an already-decided item → rejected as a conflict, no double execution.
- Approving an item with no action → decision recorded, nothing executed.
- CFO bridge down → capital tools return the bridge's own error string, never a fabricated
  number (existing `_cfo_get` behaviour, preserved).
- Unknown action type on approval → `failed` with "no handler registered", never a silent pass.
- Empty feed → the page renders an explicit "nothing needs you" state, not a blank screen.

## Risks, Landmines & Adaptations

- **Real money, four live broker accounts** → v1 refuses `money` actions at the policy layer,
  not merely by omitting a button (R5). A flag exists but defaults off.
- **Messaging real people is irreversible** → `outward` is its own kind: full message text is
  shown on the confirm screen before approval and every send is audited.
- **The owner already deprecated Telegram for confirmations** → surfaced in Q3 rather than
  silently reviving `vega/telegram_bot`; the plan deep-links into the app instead.
- **Alert fatigue kills the product** → dedup + cooldown + severity routing are in the core
  `publish()` path, so no producer can bypass them.
- **Duplicate push paths persist** → residual. `shares_cfo/proactive.py` still pushes on its own;
  v1 adds the unified path without ripping it out. Mitigation: Phase 6 points it at `publish()`.

## Assumptions Ledger

| ID | Assumption | Basis | Blast radius if wrong | Check |
|----|-----------|-------|----------------------|-------|
| A1 | Send to every configured channel best-effort rather than picking one | `shares_cfo/notify.py` already does exactly this (verified) | Noise on 2 channels; one-line change | Phase 3 |
| A2 | Reuse `vega_data.db` rather than a new store | All 21 existing tables live there (verified) | Migration if the DB is later split | Phase 1 |
| A3 | Cooldowns: critical 180min, important 720min, info 1440min | No source; chosen so a critical repeats at most ~4×/day | Too chatty or too quiet; env-tunable | Phase 1, tunable |
| A4 | v1 severity mapping: 🔴→critical, 🟡→important, 🟢→info | Matches the existing `n_critical/n_important/n_info` counters in `agent_reports` (verified) | Wrong things push | Phase 6 |
| A5 | `${MDO_APP_URL}` is reachable from Aman's phone | Required for Q3's deep link to work at all | Deep link dead; push text still readable | Phase 3 — falls back to including the item body in the push |
| A6 | The 15 CFO MCP tools map 1:1 onto brain tools via `_cfo_get` | Both call the same HTTP surface (verified: `shares_cfo/mcp_server.py` calls `_get`) | Some tools need params the bridge lacks | Phase 4 |
| A7 | Items expire after 7 days unless decided | No source; keeps the feed from becoming a graveyard | Stale items linger or vanish early; env-tunable | Phase 1 |

## Open Items (none blocking)

- Live VPS address and whether the four broker accounts are authenticated today — unknown;
  proceed with the bridge's error-reporting path, which already degrades honestly.
- Whether Aman wants the digest at a fixed hour — proceed with digest-on-demand via
  `GET /api/feed/digest` plus the existing agent cadence.

## Verification

- `python -m pytest tests/ -q` — all pre-existing tests plus the new feed suite pass.
- `python -c "import mdo_feed, mdo_server, mdo_brain"` — imports clean.
- `docker compose config -q` — stack still valid.
- Human check: open `/feed`, see items grouped by severity; tap an item with a proposed action;
  approve it; confirm the task appears on the ops board and the audit row exists.

## Build Phases

> **Status: Phases 1–6 built and verified; Phase 7 added mid-build at the human's
> request (site data over both VPN tunnels) and built. 67 tests pass.**

- [x] **Phase 1: Build the feed core and prove its safety rules**
      Done when: `pytest tests/test_feed.py -q` passes, covering R1–R8.
      Steps: write `mdo_feed.py` (schema, `publish`, dedup/cooldown, action registry,
      `decide`, `execute`, audit); write the test suite first; verify money-refusal and
      failure recording explicitly.
      Covers: R1–R8; checks: A2, A3, A7
- [x] **Phase 2: Expose the feed over HTTP**
      Done when: the routes exist and return JSON; `import mdo_server` is clean.
      Steps: call `ensure_schema` from `_ensure_schema`; add the 7 routes; register the
      `internal` action handlers (`add_task`, `file_intel`) against the existing tables.
      Covers: R9
- [x] **Phase 3: One notifier, with the deep link**
      Done when: a published critical item produces a push attempt on every configured
      channel and the message contains `${MDO_APP_URL}/feed/<id>`; unconfigured = no crash.
      Steps: unify WhatsApp + ntfy + Telegram behind one function; include the deep link;
      record send results on the item.
      Covers: G2; checks: A1, A5
- [x] **Phase 4: Give the brain the capital tools it lacks**
      Done when: `test_brain_has_capital_tools` passes — the brain exposes the CFO depth
      tools, not just `get_portfolio`.
      Steps: add tool definitions mapping to `_cfo_get` paths; wire dispatch.
      Covers: R10; checks: A6
- [x] **Phase 5: The one page**
      Done when: `/feed` renders items grouped by severity, an item page shows the proposed
      action in full, and Approve/Reject call the API; empty state renders.
      Steps: `mdo-app/app/feed/page.tsx` + item view; extend `lib/api.ts` and `lib/types.ts`;
      add to nav.
      Covers: G1, G4
- [x] **Phase 6: Point the producers at it**
      Done when: the agent runtime publishes through `publish()` and its 🔴 findings appear
      in the feed instead of only in `agent_reports`.
      Steps: map agent findings to severities (A4); route `mdo_agent.py` output through the
      feed; leave `shares_cfo/proactive.py` in place but pointed at the same path.
      Covers: G3; checks: A4
- [x] **Phase 7: Read the site networks over both VPN tunnels** *(added mid-build)*
      Done when: `pytest tests/test_sites.py -q` passes and `GET /api/sites` reports both
      tunnels plus what is configured to be read through them.
      Steps: `mdo_sites.py` — proxy-based read-only fetch per site, tunnel health,
      configured (never invented) sources, dead-tunnel findings into the feed; routes
      `/api/sites`, `/api/sites/{site}`, `/api/sites/check`; agent reads site data.
      Covers: accurate-data-at-source; checks: A8, A9

## Addendum — site integration (added after the interview)

The human asked mid-build to "integrate both VPN of vedanta and hotel ANS for accurate
data". The sidecars already existed and `HOTEL_PROXY_URL`/`VEDANTA_PROXY_URL` were passed
into the backend container, but **no code read them** (verified: grep over `mdo_server.py`
before the change). Phase 7 is that missing layer.

Two constraints shaped it, both inherited from `docs/PLAN_VPN_SITE_ACCESS.md`:

- **Read-only.** That plan's R9 forbids writing to or authenticating against site systems
  in v1. `SAFE_METHODS = ("GET",)` is the single enforcement point; POST/PUT/DELETE are
  refused with a reason.
- **The site hosts have not been discovered yet.** That plan's Phase 3 is the discovery
  step and has not run. So sources are *configured*, never hardcoded: `MDO_SITE_SOURCES`
  or `site_sources.json`. With nothing configured the API answers "no sources configured"
  — it does not guess a hostname, and a missing JSON field is an error rather than a zero.

| ID | Assumption | Basis | Blast radius if wrong | Check |
|----|-----------|-------|----------------------|-------|
| A8 | Site hosts speak HTTP, so an HTTP proxy is the right shape | `docs/PLAN_VPN_SITE_ACCESS.md` A5 (verified) | Wrong access shape; needs a TCP forwarder | Discovery — `site_sources.json` stays empty until proven |
| A9 | Tunnel liveness needs a probe URL inside the LAN to be meaningful | Proxy-answering only proves the sidecar is up, not the tunnel | Tunnel reported up while down | `tunnel_status()` says which of the two it verified |
