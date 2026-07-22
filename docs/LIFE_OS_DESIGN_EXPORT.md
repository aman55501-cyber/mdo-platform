# Life OS — design export (pastable brief for analysis)

> A shared household cockpit that lives inside the AMAN Console (the same always-on
> app that runs my trading + business OS). It's built and deployed. This is a complete,
> self-contained description you can analyse and redesign against — data model, scoping,
> API, screen, aesthetic and the open questions. Nothing here needs the codebase.

---

## 1. What it is (one line)
A single shared to-do / plan / bills / events board for **me (Aman)** and **Jahnavi** — she
gets her own link that shows *only what I've shared*, and on those shared items she can
**read, add, edit, tick and delete**. My private items never appear on her link.

## 2. Who uses it, and the trust model
Two audiences, one data store, two secrets — no accounts, no passwords, just links:

| Role | Token | Sees | Can do |
|------|-------|------|--------|
| **Owner (Aman)** | `CFO_API_TOKEN` (the master app token) | Everything — private + shared | Full CRUD + toggle `shared` on/off + get Jahnavi's link |
| **Partner (Jahnavi)** | `CFO_SHARE_TOKEN` (a separate secret) | **Only items flagged `shared`** | Read / add / edit / tick / delete **on shared items** |

Hard guarantees (already enforced server-side):
- The **share token authenticates ONLY the `/life/*` endpoints**. It is rejected everywhere
  else — it cannot reach the portfolio, orders, broker tokens, or the business book.
- On the partner's link, non-shared items are filtered out *before the response leaves the
  server* — they're never sent to her browser at all.
- The partner **cannot flip the `shared` flag** (so she can't accidentally un-share an item
  and lose her own access). Un/re-sharing stays with the owner.
- A partner "add" always lands in the shared space and is tagged `owner: "jahnavi"` so I can
  see who added what.

## 3. Data model (one flat item)
Stored as plain JSON on the persistent state volume (`data/state/life/items.json`), so it
survives container rebuilds. One item =

```json
{
  "id": "a1b2c3d4e5f6",         // server-generated, 12-hex
  "title": "Pay society maintenance",
  "kind": "bill",               // task | event | list | bill | note | goal
  "category": "home",           // free text: home, health, travel, money, family, us…
  "due": "2026-07-25",          // YYYY-MM-DD or ""
  "done": false,
  "shared": true,               // visible on Jahnavi's link when true
  "priority": "",               // free text (high / low / …)
  "notes": "UPI to society a/c",
  "owner": "aman",              // "aman" or "jahnavi"
  "created_at": "2026-07-22T…Z",
  "updated_at": "2026-07-22T…Z"
}
```

Field-level write rules (server-enforced):
- **Owner** may patch: `title, kind, category, due, done, shared, priority, notes`.
- **Partner** may patch: `title, kind, category, due, done, priority, notes` — **not** `shared`.

## 4. API surface (all live)
Token in `?token=` or `X-CFO-Token` header. Scope is derived from which token matches.

| Method | Path | Owner | Partner |
|--------|------|-------|---------|
| GET | `/life` | HTML console (adapts to scope) | same page, partner mode |
| GET | `/life/items` | all items + counts | only shared items + counts |
| POST | `/life/items` | add (any) | add (forced `shared:true`, `owner:jahnavi`) |
| PATCH | `/life/items/{id}` | any field | shared items only, no `shared` flag |
| DELETE | `/life/items/{id}` | any | shared items only |
| GET | `/life/share-link` | returns Jahnavi's link (owner-only) | 403 |

`GET /life/items` response shape:
```json
{ "scope": "full", "items": [ … sorted: open first, then by due, then newest ],
  "count": 12, "open": 5, "shared": 4 }
```

## 5. The screen (what's built — redesign target)
Terminal aesthetic, single column on a folded Z Fold, widens on unfold/desktop.
Self-refreshes every 30s. Structure:

- **Header** — `LIFE·OS` + a "who am I" strip (`Owner · full` vs `Our shared list · you can add & edit`).
- **Stat row** — Open · Shared · Overdue (3 tiles).
- **Filter chips** — Open · All · Shared(owner-only) · Today · Done.
- **Item rows** — a square checkbox (tick = done), title (tap to rename), a meta line of
  chips (kind / category / due — due turns amber when near, red when overdue / `shared`),
  optional notes, and per-row actions (share-toggle for owner, ✎ note, ✕ delete).
- **Add bar** (fixed bottom, both roles) — title + kind + category + date, plus a
  "Share with Jahnavi" checkbox that only the owner sees.
- **Owner links** — Trading → / Business → / "Jahnavi's link ⧉" (copies her URL to clipboard).

Aesthetic tokens (match the rest of the console):
```
canvas #07090d  bg #0b0e13  panel #11151c  text #dde3ea
accent #3f8cde  up #2ebd85  down #f0544c  warn #f0a13c
fonts: IBM Plex Sans / Sans Condensed (labels, uppercase, letter-spaced) / Mono (numbers)
square corners, 1px hairline borders, tabular-nums, no shadows/gradients.
Folded ≤ 520px 1-col; ≥ 740px widens to ~760px.
```

## 6. Proactive agent integration (already wired)
A `_life_agent` runs in the multi-agent loop (every 15 min, gated on a notify channel):
- Pushes a 🟡/🔴 phone alert for any **not-done life item due today / tomorrow / overdue**,
  in the same `ENTITY / WHY / ACTION` format as the trading + business agents.
- The **daily MIS digest** (08:15–08:45 IST) now includes a `Life N open, M overdue` line
  alongside net worth, tenders and receivables.

## 7. Open questions for you (design) to analyse
1. **Structure vs. flat.** Right now it's one flat item list with `kind`. Should shared
   *lists* (groceries, packing, home-reno) be first-class nested lists instead of individual rows?
2. **Two-way presence.** Should Jahnavi's edits notify me (and vice-versa) on the phone,
   or is the shared view + agent enough?
3. **Recurrence.** Bills/chores repeat. Add a `repeat` rule, or keep it manual?
4. **Calendar surface.** `event` + `due` could render as a week/month strip for "us" —
   worth it, or is the list enough on a phone?
5. **Categories as lanes.** Turn `category` into swimlanes (Home / Money / Health / Travel /
   Us) with per-lane counts?
6. **Attachments/links.** Do household items need a URL or photo (e.g. a bill screenshot)?
7. **Warmth vs. terminal.** The whole app is a Bloomberg-style terminal. The *life* surface
   is the one place a softer, warmer treatment might fit — should Life OS keep the terminal
   look for consistency, or get its own gentler skin (still dark, still square)?

## 8. Deployment context (so a redesign stays feasible)
- FastAPI single service, self-contained HTML strings (no build step, no external JS/CSS
  beyond Google Fonts). Runs 24/7 on a Hostinger VPS behind Caddy + autoheal, PWA-installable.
- To turn on sharing: set `CFO_SHARE_TOKEN` (a fresh random secret) in `backend/.env`,
  restart, then tap **Jahnavi's link ⧉** in the owner view to copy her URL and send it to her.
- No secret values in this doc by design.
