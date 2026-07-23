# LIFE·OS — Handoff

> A shared home board. **You see all; she sees what's shared.**
> Extracted from the trading console — now its own project.

This is the brief for the Life OS extraction. It was reconstructed from the
"Life OS — Handoff Overview" design artifact after the original
`handoff/life-os/` sources (`life.py`, `life_console.py`, and this doc set) did
not survive the extraction. The live, working project is in `life-os/`.

## What it is

One flat item store — **tasks, events, bills, lists, notes** — that two people
work from. Not a per-user database; a single board with a `shared` flag on each
item, and a token that decides how much of the board you get.

- **One board.** Everything is one item type with a `kind`.
- **Scoped, server-side.** The partner never *receives* private items — they're
  filtered before the response leaves the server, not hidden in the UI.
- **Nudges.** Due / overdue *shared* items surface as phone alerts and in the
  morning digest, so home doesn't slip either.
- **Terminal-styled.** The `/life` screen adapts to whoever holds the link:
  owner controls vs. partner's shared-only board.

## The security model — two tokens, one store

| Holder | Token | Sees / can do |
| --- | --- | --- |
| **Owner** | `CFO_API_TOKEN` | Everything, private + shared. Toggles what's shared, copies the partner link. |
| **Jahnavi** | `CFO_SHARE_TOKEN` | Only items flagged `shared`. Read / add / edit / tick / delete those — never the trading or business book. Can't flip the `shared` flag. |

The core invariant: **the share token reaches ONLY `/life` and only shared
items, filtered server-side.** Two things guarantee it:

1. **`_life_scope`** (in `life.py`) resolves the presented token to `owner` or
   `share` with a constant-time compare, or 401s. The two secrets must be
   distinct — the store refuses to start otherwise.
2. This app mounts **only `/life` routes**. The share token has no other
   endpoint in the process, so it structurally cannot reach trading/business
   data — filtering is the second line, not the only line.

Hard rules carried from the console: **secrets live in `.env` only**, a token is
**never logged**, and **no model IDs** go into commits.

## The API (re-created)

```
GET    /life              → console (adapts to scope)
GET    /life/items        → owner: all · share: only shared
POST   /life/items        → partner add is forced shared
PATCH  /life/items/{id}   → share: shared items, not the `shared` flag
DELETE /life/items/{id}   → share: shared items only
GET    /life/share-link   → owner-only: builds Jahnavi's link
GET    /life/nudges       → due/overdue shared digest (_life_agent)
```

## Files & wiring

| | |
| --- | --- |
| **Source** | `life-os/` — `life.py` (scoped store + guard), `life_console.py` (LIFE_HTML), `agents.py` (`_life_agent`), `app.py` (routes) |
| **Storage** | `life-os/data/state/life/items.json` — a JSON list on the persistent volume |
| **Tokens** | `CFO_API_TOKEN` (owner) + `CFO_SHARE_TOKEN` (Jahnavi — a different secret) |
| **Agent** | `_life_agent` lifted out of `handoff/business-os/agents.py` into `life-os/agents.py` |
| **Next** | Open design questions live in `DESIGN_EXPORT.md` |

## Item data model

```jsonc
{
  "id": "hex",
  "kind": "task | event | bill | list | note",
  "title": "string",
  "notes": "string",
  "shared": false,            // owner-only flag; partner adds are forced true
  "done": false,              // the tick
  "due": "2026-07-25",        // ISO date/datetime or null — drives nudges
  "amount": null,             // bills
  "category": null,           // reserved for category lanes (open question)
  "items": [],                // `list` kind — flat for now (open question)
  "created_at": "…", "updated_at": "…",
  "created_by": "owner | share"
}
```

## What was reconstructed vs. carried

The `/life/*` **contract**, the item model, and the two-token model came through
the design artifact verbatim. The **implementation** of `_life_scope`,
`LIFE_HTML`, and `_life_agent` was re-authored to satisfy that contract — the
original code did not survive the extraction, so treat these as faithful
re-creations, not byte copies. See `DESIGN_EXPORT.md` for the open questions.
