# Life OS

A shared home board. **You see all; she sees what's shared.**

Extracted from the trading console into its own project. One flat item store —
tasks, events, bills, lists, notes — that two people work from over the *same*
endpoints, separated only by which token they hold.

## The security model — two tokens, one store

| Holder | Token | Sees / can do |
| --- | --- | --- |
| **Owner** | `CFO_API_TOKEN` | Everything, private + shared. Toggles what's shared, copies the partner link. |
| **Jahnavi** | `CFO_SHARE_TOKEN` | **Only items flagged `shared`.** Read / add / edit / tick / delete those — never trading or business data, and can't flip the `shared` flag. |

The invariant is enforced **server-side**: private items are filtered out in
`life.py` before any share-scope response is serialised, so the partner never
*receives* them — they aren't merely hidden in the UI. And because this app
mounts **only** `/life` routes, the share token has no other endpoint in the
process to reach.

The two tokens must be **distinct** secrets — `life.py` refuses to start if they
are equal.

## API

```
GET    /life              → console (adapts to scope)
GET    /life/items        → owner: all · share: only shared
POST   /life/items        → partner add is forced shared
PATCH  /life/items/{id}   → share: shared items, NOT the `shared` flag
DELETE /life/items/{id}   → share: shared items only
GET    /life/share-link   → owner-only: builds Jahnavi's link
GET    /life/nudges       → due/overdue shared-item digest (_life_agent)
GET    /life/health       → liveness
```

Token is presented via the `X-Life-Token` header, `Authorization: Bearer …`, or
a `?t=…` query param (the share link uses the query param, since the partner
opens a URL in a browser).

## Run

```bash
cp .env.example .env          # then fill in two DISTINCT secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"   # generate each
pip install -r requirements.txt
python app.py                 # http://localhost:8600/life?t=<owner-token>
```

Or with Docker (mounts the persistent volume at `/app/data/state/life`):

```bash
docker build -t life-os . && docker run -p 8600:8600 --env-file .env life-os
```

## Storage

`data/state/life/items.json` — a JSON list on the persistent volume. Writes are
atomic (temp file + replace). The file is gitignored; the directory is kept via
`.gitkeep`.

## Layout

```
life-os/
  app.py           FastAPI wiring — /life routes only
  life.py          scoped store, item model, _life_scope two-token guard, CRUD
  life_console.py  LIFE_HTML — terminal console that adapts to scope
  agents.py        _life_agent — due/overdue nudges + morning digest
```

## Provenance

`life.py`, `life_console.py`, and `agents.py` were **reconstructed from the
handoff design** (`handoff/life-os/DESIGN_EXPORT.md`) — the original extracted
sources were not carried across. Behaviour matches the documented `/life/*`
contract. Open design questions are tracked in `DESIGN_EXPORT.md`.
