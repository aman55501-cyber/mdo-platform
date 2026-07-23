# Business OS — session handoff

You're picking up the **Business OS** as its own Claude Code project. It used to live
inside the Shares CFO trading console (FastAPI app in `shares_cfo/`) and was pulled out
so it can evolve independently. This folder has the complete, working source; the
console no longer references it. Everything you need to continue is below.

Owner: Aman Agrawal. Deployed always-on to a Hostinger VPS (`/docker/sharecfo`) via
Docker + Caddy + autoheal. Same deploy model applies if you keep it there, or stand up
a new service.

---

## What it is
An **import-driven** business operations layer — no manual data entry. You upload the
sheets already kept (tenders, receivables, hotel daily, cash-flow, tasks, projects,
compliance); it stores them, computes KPIs, and runs background agents that push phone
alerts so nothing slips (overdue receivables, milestones, filings, a daily MIS digest).

## Files in this folder
- **`business.py`** — data layer + KPIs. Import Excel/CSV → JSON on disk; keyword-based
  column detection; per-module KPIs (receivables aging, tender pipeline, hotel RevPAR)
  and a generic numeric/date summary fallback.
- **`biz.py`** — `BIZ_HTML`, a self-contained terminal-styled console (tabs: Brief /
  Tenders / Recv / Hotel / Board / Import). Was served at `GET /biz`.
- **`agents.py`** — the ops agents: `_tasks_agent`, `_projects_agent`,
  `_receivables_agent`, `_compliance_agent`, `_mis_agent(get_book)` (morning digest),
  plus `_life_agent` (belongs to the **Life OS** — see that handoff; split it out).
  `start(get_book)` launches a background loop every 900s.

## Data model / storage
- Datasets: `tenders, receivables, hotel, cashflow, tasks, projects, compliance`
  (`business.KNOWN`); any other name imports generically.
- Stored as JSON on the state volume: `data/state/business/<dataset>.json`, shape:
  `{"dataset", "rows":[{header:value}], "count", "columns":[...], "imported_at"}`.
- Column detection is by keyword (`business._find(cols, "amount","value","due",...)`),
  so whatever headers the source sheet uses generally just work.

## HTTP API (these routes were removed from the console — re-create them in your app)
```
POST /business/import/{dataset}   multipart file=<xlsx/xls/csv>  -> saves + replaces dataset
GET  /business/summary            -> {datasets, receivables, tenders, hotel}  (Brief screen)
GET  /business/datasets           -> per-dataset counts + imported_at + columns
GET  /business/{dataset}?limit=200-> rows + the dataset's KPI (or generic_summary)
GET  /biz                         -> BIZ_HTML console
```
Import handler (reference — reused a temp file + the fundamentals Excel/CSV reader):
```python
suffix = os.path.splitext(file.filename or "")[1].lower() or ".xlsx"
tmp = Path(tempfile.gettempdir()) / f"biz_upload{suffix}"; tmp.write_bytes(await file.read())
rows = business._rows_from_file(tmp)     # -> list[{header: value}]
return {"imported": True, **business.save(dataset, rows)}
```

## Dependencies to rebuild when standalone
`business.py` and `agents.py` currently borrow three things from the trading console —
port or replace them:
1. **Excel/CSV reader** — `business._rows_from_file` calls
   `shares_cfo/analysis/fundamentals._rows_from_file(path)`: reads `.xlsx/.xls` via
   pandas (`pd.read_excel(dtype=str).fillna("")`) or `.csv` via `csv.DictReader`,
   returning `list[dict]`. Copy that ~15-line function in.
2. **Number normaliser** — `business._num` calls `normalise.to_float(v)` (strips
   commas/₹/%, returns float|None). Copy it. **Any field compared to a threshold must
   pass this first** (hard rule from the owner).
3. **Agents' alert plumbing** — `agents.py` imports from `proactive`: `IST, _alert,
   _fresh, _inr, _now`. `_alert(level, entity, what, why, action, tab)` formats a
   🔴🟡🟢 push and sends via `notify.send()` (ntfy/Telegram); `_fresh(key, cooldown)` is
   the de-dupe gate; `_inr` formats rupees; `_now()` is IST now. Recreate a small
   notify module (ntfy topic or Telegram bot) + these helpers. `_mis_agent` also takes a
   `get_book` async callable for the net-worth line — drop it or wire your own source.

## KPIs (in `business.py`)
- `receivables_aging()` → buckets 0-30/31-60/61-90/90+, `overdue_60_plus`, worst debtors.
- `tender_pipeline()` → total pipeline value, by-status, upcoming deadlines.
- `hotel_kpis()` → latest occupancy/ADR, RevPAR, MTD revenue.
- `generic_summary(name)` → row count + numeric column totals + date span.
- **Open task (#14):** tune these to Aman's *real* sheet headers once he imports —
  the keyword lists in each KPI are best-guesses.

## Env / config
- `CFO_AGENTS_ENABLED` (default "1"; "0" disables the agent loop).
- A notification channel: `CFO_NTFY_TOPIC` or Telegram (`CFO_TELEGRAM_*`).
- `CFO_APP_URL` for deep-links in alerts.

## Security constraints (verbatim, non-negotiable)
- API keys/secrets live in `.env` only. Never print, echo, log, or repeat a key value.
- Never scrape Screener.in — premium CSV/Excel export only.
- Any new data field must pass the number-normaliser before being compared to a threshold.
- Don't put model identifiers in commits/PRs/code.

## Suggested first moves for the new session
1. Copy `_rows_from_file`, `to_float`, and a minimal `notify`+alert-helper module in, so
   `business.py`/`agents.py` import cleanly with no trading-console dependency.
2. Stand up a small FastAPI app that mounts the routes above + serves `BIZ_HTML`.
3. Mount a persistent `data/state/business` volume.
4. Have Aman import one real sheet, then tune the KPI keyword maps to his headers (#14).
5. Deepen the console: tasks/projects/compliance editing, not just viewing.
