# LIFE·OS — Design Export

Design state at extraction, plus the open questions to work through. The
`/life/*` contract, the item model, and the two-token security model are
**settled** (see `HANDOFF.md` and the `life-os/` implementation). What follows
is what is *not* yet decided.

## Settled

- **Two tokens, one store.** `CFO_API_TOKEN` = owner (all), `CFO_SHARE_TOKEN` =
  Jahnavi (shared only). Distinct secrets, constant-time match in `_life_scope`,
  server-side filtering, `/life`-only surface.
- **Flat item store** with a `kind` and a `shared` flag; partner adds forced
  shared; partner can't flip the flag.
- **Nudges** over shared, due/overdue items via `_life_agent`.
- **Storage**: one JSON list on the persistent volume, atomic writes.

## Open questions

### 1. Nested lists
A `list` item currently holds a flat `items: []`. Do we want checkable
sub-items, nesting depth > 1, or lists that reference other items? Decision
affects the data model (sub-item id/`done` shape) and the console rendering.

### 2. Recurrence
Bills and events repeat (rent monthly, a weekly event). Options:
- store a recurrence rule (RRULE-ish) and materialise instances on read, or
- keep single items and let `_life_agent` roll the `due` forward on tick.
Affects nudges (don't nag on an already-handled recurring instance) and the
store shape.

### 3. Calendar
Events have a `due`/date but there's no calendar view or external calendar
sync. Question: in-app month/week view only, or two-way sync (Google Calendar)?
Sync raises its own scope question — a shared event on a shared calendar.

### 4. Category lanes
There's a reserved `category` field but no lanes in the UI. Do we group the
board into lanes (Home / Money / Kids / …), and are categories a fixed set or
free-form? Affects filtering and whether the partner sees lane structure.

### 5. Warmer skin
The console is the trading terminal's green-on-near-black. For a shared *home*
board a warmer, softer skin may fit better — especially the partner's view.
Question: one theme for both, or a distinct partner skin? Keep the mono type or
go softer?

## Working notes

Add decisions here as we settle them; promote settled items up to the top
section and reflect them in `life-os/`.
