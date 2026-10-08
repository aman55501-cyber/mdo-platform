# Life OS — session handoff

You're picking up the **Life OS** as its own Claude Code project. It used to live inside
the Shares CFO trading console (FastAPI app in `shares_cfo/`) and was pulled out so it
can evolve on its own. This folder has the complete, working source; the console no
longer references it. `DESIGN_EXPORT.md` (in this folder) is the fuller product brief —
read it too.

Owner: Aman Agrawal; shared with **Jahnavi**. Deployed always-on to a Hostinger VPS
(`/docker/sharecfo`) via Docker + Caddy + autoheal.

---

## What it is
A **shared household board** — tasks, events, bills, lists, notes — for a couple.
Two audiences, one store, two secrets:
- **Owner** (full token) sees & edits *everything* (private + shared).
- **Partner / Jahnavi** (a *separate* share token) sees **only items flagged `shared`**,
  and can read / add / edit / tick / delete those — never the trading or business book.

## Files in this folder
- **`life.py`** — data layer. JSON-backed item store on the state volume; scope-aware
  `list_items(scope)`, `add(fields, scope)`, `update(id, patch, scope)`, `delete(id,
  scope)`, `stats()`. Field-level write rules enforce the partner can change everything
  on a *shared* item **except** the `shared` flag (so she can't accidentally un-share and
  lose access), and a partner `add` always lands in the shared space tagged to her.
- **`life_console.py`** — `LIFE_HTML`, terminal-styled `/life` screen that adapts to
  scope: owner gets add/share-toggle/delete over everything; partner gets a shared-only
  board she can add to and edit. Includes an owner "copy Jahnavi's link" action.
- **`DESIGN_EXPORT.md`** — the design brief (data model, UX, open questions).

## Data model / storage
- One flat item: `{id, title, kind(task|event|list|bill|note|goal), category, due,
  done, shared, priority, notes, owner("aman"|"jahnavi"), created_at, updated_at}`.
- Stored at `data/state/life/items.json` (a JSON list). Survives rebuilds on the volume.

## The two-token scope (this is the whole security model)
Two env secrets:
- `CFO_API_TOKEN` — owner / full.
- `CFO_SHARE_TOKEN` — partner / share-only. **Never accepted on any non-`/life` route.**

The console mapped a request to a scope with this helper (removed from the console —
recreate it in your app):
```python
def _life_scope(request, token) -> str:
    supplied = request.headers.get("X-CFO-Token") or token
    owner = get_api_token()          # CFO_API_TOKEN
    share = get_share_token()        # CFO_SHARE_TOKEN
    if not owner:      return "full"          # unauthenticated local mode
    if supplied == owner: return "full"
    if share and supplied == share: return "share"
    raise HTTPException(status_code=401, detail="Missing or invalid token.")
```
Server-side, the partner NEVER receives non-shared items: `list_items("share")` filters
to `shared==True` before the response is built — filtering is not a UI concern.

## HTTP API (removed from the console — re-create in your app)
```
GET    /life                 -> LIFE_HTML (adapts to scope from the token)
GET    /life/items           -> owner: all; share: only shared  {items,count,open,shared}
POST   /life/items           -> add; partner add is forced shared + owner="jahnavi"
PATCH  /life/items/{id}      -> owner: any field; partner: shared items only, not `shared`
DELETE /life/items/{id}      -> owner: any; partner: shared items only
GET    /life/share-link      -> owner-only: builds  <CFO_APP_URL>/life?token=<share>
```
Endpoint bodies map 403 (PermissionError → "you can only edit shared items"), 404
(KeyError), 400 (ValueError from `add`).

## Life agent (lives in the Business OS handoff's `agents.py`)
`_life_agent()` nudges due/overdue **shared** items and adds a Life line to the morning
MIS digest. It's currently inside `../business-os/agents.py` because both agent sets
shared one loop — lift `_life_agent` out into this project and give it its own small
scheduler (it only needs `life.list_items("full")` + an `_alert`/notify helper).

## Dependencies to rebuild when standalone
1. `_life_scope` above (needs `get_api_token()`/`get_share_token()` = read `CFO_API_TOKEN`
   / `CFO_SHARE_TOKEN` from env).
2. A FastAPI app to host the routes + serve `LIFE_HTML`.
3. A persistent `data/state/life` volume.
4. If you want nudges: `_life_agent` + a notify channel (ntfy/Telegram).

## Env / config
- `CFO_API_TOKEN` (owner), `CFO_SHARE_TOKEN` (Jahnavi — a *different* random secret).
- `CFO_APP_URL` for the share link.

## Security constraints (verbatim)
- Secrets in `.env` only; never print/log/echo a token. The share token is designed to
  be handed to Jahnavi, but generate it fresh and keep it distinct from `CFO_API_TOKEN`.
- The share scope must never reach trading/business data — enforce at the scope check
  AND by filtering server-side.
- No model identifiers in commits/PRs/code.

## Suggested first moves
1. Re-create `_life_scope` + a 2-route-guard FastAPI app; serve `LIFE_HTML`.
2. Lift `_life_agent` out of the business `agents.py` into this project.
3. Open `DESIGN_EXPORT.md` — it lists the open design questions (nested lists,
   recurrence, calendar view, category lanes, warmer vs terminal skin) to take further.
