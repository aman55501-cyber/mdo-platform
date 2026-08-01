# Business OS

Import-driven back-office KPIs + ops agents. Extracted from the trading console
into its own project — **no trading/broker dependency**. Upload the Excel/CSV
sheets you already keep; columns are auto-detected by keyword and KPIs compute
themselves. Ops agents watch the books and push phone alerts so nothing slips.

## What's here

| File | Role |
|------|------|
| `helpers.py` | The three ported helpers: Excel/CSV reader, number normaliser, notify/`_alert`/`_fresh` |
| `business.py` | Data model + KPIs (receivables aging, tender pipeline, hotel RevPAR, generic numeric summary) |
| `agents.py` | Ops watchers (tasks, milestones, 60+ receivables, statutory filings) + morning MIS |
| `biz.py` | `BIZ_HTML` — the single-page console |
| `app.py` | FastAPI app mounting the `/business/*` API + serving `/biz` |

## API

```
POST /business/import/{dataset}   multipart file  -> save + replace
GET  /business/summary            -> the Brief: datasets + KPIs
GET  /business/datasets           -> per-dataset row counts
GET  /business/{dataset}?limit=N  -> rows + computed KPI
GET  /biz                         -> the console
POST /business/agents/run         -> run ops watchers now
POST /business/agents/mis         -> build + push morning MIS
GET  /healthz                     -> liveness
```

Datasets: `tenders`, `receivables`, `hotel`, `cash-flow`, `tasks`, `projects`,
`compliance`.

## Storage

Each dataset is a JSON array of `{header: value}` rows at
`data/state/business/<dataset>.json`. In Docker that path is a mounted volume
(`BUSINESS_DATA_DIR`), so data survives restarts and rebuilds. Dataset JSON is
gitignored — it's user data on the volume, not source.

## Run locally

```bash
pip install -r business_os/requirements.txt
cp business_os/.env.example business_os/.env    # optional: fill in alert secrets
python -m business_os                            # -> http://localhost:8600/biz
```

## Deploy (Docker on Hostinger VPS)

```bash
cp business_os/.env.example business_os/.env     # fill in secrets
docker compose -f business_os/docker-compose.yml up -d --build
```

The container runs `python -m business_os` on port 8600 with the dataset volume
mounted at `/data/state/business`.

## Hard rules (verbatim from the handoff)

- **Secrets in `.env` only** — read via `os.getenv`, never hard-coded.
- **Never log a key** — notify helpers redact any token-like string before logging.
- **Every threshold field passes the normaliser first** — agent thresholds and
  KPI amounts all go through `helpers.normalise()`.
- **Screener export only** — any stock/fundamental data enters via a Screener.in
  export, never scraped. (Business OS itself imports back-office sheets; this
  rule governs any future stock-data feature.)

## Open item #14

`business.KEYWORD_MAPS` holds the column-detection keyword lists per dataset.
They're first-pass guesses. **Import one real sheet and we tune each dataset's
keywords to your actual headers** — that's the first task after this runs.
