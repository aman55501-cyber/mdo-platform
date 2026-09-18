"""LIFEOS FastAPI app.

Serves the last rendered snapshot at ``/`` (a static page, not a live-querying
client — all the work happens in the 06:30 run). A protected ``/run`` triggers a
run on demand; ``/runs.json`` exposes the run history so silent death is visible in
the data, not just the page. The 06:30 IST schedule is an APScheduler cron job.

Boot sequence fails loudly (rule 6): if the HTTP Basic credentials are missing the
process refuses to start rather than coming up ungated.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse

from . import __version__, db
from . import ask as ask_mod
from .auth import BasicAuthMiddleware
from .config import IST, RUN_HOUR, RUN_MINUTE, auth_credentials, port
from .run import execute_run

_scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail loudly if the gate is not configured — never come up open.
    auth_credentials()
    db.init_db()

    global _scheduler
    _scheduler = BackgroundScheduler(timezone=IST)
    _scheduler.add_job(
        execute_run,
        CronTrigger(hour=RUN_HOUR, minute=RUN_MINUTE, timezone=IST),
        kwargs={"trigger": "scheduled"},
        id="morning_run",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()

    # If no snapshot exists yet (fresh deploy), do one boot run so ``/`` is never blank.
    if db.latest_snapshot() is None:
        try:
            execute_run(trigger="boot")
        except Exception:  # noqa: BLE001 — never let a boot run stop the server
            pass
    try:
        yield
    finally:
        if _scheduler:
            _scheduler.shutdown(wait=False)


app = FastAPI(title="LIFEOS", version=__version__, lifespan=lifespan)
app.add_middleware(BasicAuthMiddleware)


@app.get("/healthz")
def healthz() -> PlainTextResponse:
    # Data-free, unauthenticated — Railway health check only.
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    html = db.latest_snapshot()
    if html is None:
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8>"
            "<body style='font-family:system-ui;padding:24px'>"
            "<h3>LIFEOS</h3><p>No run has completed yet. Trigger one with "
            "<code>POST /run</code> or wait for the 06:30 IST run.</p></body>",
            status_code=200,
        )
    return HTMLResponse(html)


@app.post("/run")
def run_now() -> JSONResponse:
    """Trigger a run immediately (for testing and acceptance checks)."""
    summary = execute_run(trigger="manual")
    return JSONResponse(summary)


@app.post("/ask")
async def ask(request: Request):
    """The ask bar. capture:/remind: writes to the Inbox and confirms (JSON);
    anything else streams the model's answer. Behind the same Basic gate."""
    body = await request.json()
    question = (body.get("q") or body.get("question") or "").strip()
    if not question:
        return JSONResponse({"ok": False, "message": "empty question"}, status_code=400)

    capture = ask_mod.parse_capture(question)
    if capture:
        kind, text = capture
        try:
            message = ask_mod.write_capture(kind, text)
            return JSONResponse({"ok": True, "captured": True, "message": message})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"ok": False, "captured": True, "message": f"capture failed: {exc}"},
                status_code=502,
            )

    return StreamingResponse(ask_mod.stream_answer(question), media_type="text/plain")


@app.get("/runs.json")
def runs_json() -> JSONResponse:
    """Raw run history — proof-of-life data. A started row with finished_at=null is
    a run that did not complete."""
    rows = db.recent_runs(30)
    return JSONResponse(
        [
            {
                "id": r["id"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "sources_ok": r["sources_ok"],
                "sources_unreachable": r["sources_unreachable"],
                "trigger": r["trigger"],
                "note": r["note"],
                "complete": r["finished_at"] is not None,
            }
            for r in rows
        ]
    )


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port())


if __name__ == "__main__":
    main()
