"""
Business OS — FastAPI app.

Mounts the /business/* API and serves the console (BIZ_HTML) at /biz. This is
the whole HTTP surface that was removed from the trading console, re-created
standalone with no trading/broker dependency.

Routes:
  POST /business/import/{dataset}   multipart file  -> save + replace
  GET  /business/summary            -> the Brief: datasets + KPIs
  GET  /business/datasets           -> per-dataset row counts
  GET  /business/{dataset}?limit=N  -> rows + computed KPI
  GET  /biz                         -> the console
  POST /business/agents/run         -> run the ops watchers now (optional)
  GET  /healthz                     -> liveness
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

# Load .env before anything reads os.getenv (secrets live in .env only).
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("business_os")

from . import agents, business  # noqa: E402  (after load_dotenv/logging)
from .biz import BIZ_HTML  # noqa: E402

app = FastAPI(title="Business OS", version="0.1.0", docs_url="/business/docs")


@app.get("/healthz")
async def healthz():
    return {"ok": True, "datasets": business.dataset_counts()}


@app.get("/biz", response_class=HTMLResponse)
async def biz_console():
    return HTMLResponse(BIZ_HTML)


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(BIZ_HTML)


# ---------------------------------------------------------------------------
# /business/* API
# ---------------------------------------------------------------------------

@app.post("/business/import/{dataset}")
async def business_import(dataset: str, file: UploadFile):
    if not file:
        raise HTTPException(400, "no file uploaded")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        result = business.import_bytes(dataset, data, file.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # parsing errors -> 400, not 500
        log.warning("import failed for %s: %s", dataset, exc)
        raise HTTPException(400, f"could not parse sheet: {exc}")
    return JSONResponse(result)


@app.get("/business/summary")
async def business_summary():
    return business.summary()


@app.get("/business/datasets")
async def business_datasets():
    return {"datasets": business.dataset_counts()}


@app.post("/business/agents/run")
async def business_agents_run():
    """Run the ops watchers once (fires phone alerts for anything overdue)."""
    return {"sent": agents.run_all()}


@app.post("/business/agents/mis")
async def business_agents_mis():
    """Build + push the morning MIS digest now."""
    return {"digest": agents.morning_mis(send=True)}


# Keep this LAST — it's a catch-all path param under /business.
@app.get("/business/{dataset}")
async def business_get(
    dataset: str = Path(...),
    limit: int = Query(200, ge=1, le=5000),
):
    rows = business.load_dataset(dataset)
    return {
        "dataset": dataset,
        "count": len(rows),
        "rows": rows[:limit],
        "kpi": business.compute_kpi(dataset, rows),
    }


def main():
    import uvicorn

    port = int(os.getenv("PORT", "8600"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
