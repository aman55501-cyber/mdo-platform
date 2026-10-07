"""Capital desk web app. Read-only database session; HTTP Basic on every route; PIN-gated Net worth page."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import desk as desk_data
from . import fmt, pin
from .auth import BasicAuthMiddleware
from .config import auth_credentials, cookie_key, optional, port, unlock_code
from .db import DB

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), autoescape=select_autoescape(["html"]))
_env.filters.update({"inr": fmt.inr, "price": fmt.price, "pct": fmt.pct, "tone": fmt.tone, "clock": fmt.ist_clock})

BANTU_STALE_HOURS = 24


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth_credentials()          # refuse to start ungated
    if unlock_code():
        cookie_key()            # a PIN needs a signing key
    yield


app = FastAPI(title="Capital", lifespan=lifespan)
app.state.db = None
app.state.guard = pin.PinGuard()
app.add_middleware(BasicAuthMiddleware)


@app.middleware("http")
async def no_store(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _db() -> DB:
    return app.state.db or DB(readonly=True)


def _render(page: str, **ctx) -> HTMLResponse:
    return HTMLResponse(_env.get_template("app.html").render(page=page, error=ctx.pop("error", None), **ctx))


def _load(fn):
    """Run a data loader; on failure return (None, reason) so the page says UNREACHABLE instead of 500."""
    try:
        return fn(_db()), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {str(exc)[:160]}"


@app.get("/healthz")
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
def desk_page():
    d, err = _load(desk_data.desk)
    if d:
        bantu = d["fresh"].get("bantu_chat", {}).get("at")
        d["bantu_stale"] = bantu is None or (d["now"] - bantu).total_seconds() > BANTU_STALE_HOURS * 3600
    return _render("desk", d=d, error=err)


@app.get("/holdings", response_class=HTMLResponse)
def holdings_page():
    d, err = _load(desk_data.holdings)
    return _render("holdings", d=d, error=err)


@app.get("/health", response_class=HTMLResponse)
def health_page():
    d, err = _load(desk_data.health)
    return _render("health", d=d, error=err)


def _unlocked(request: Request) -> bool:
    return bool(unlock_code()) and pin.cookie_valid(request.cookies.get(pin.COOKIE), cookie_key())


@app.get("/networth", response_class=HTMLResponse)
def networth_page(request: Request):
    if not _unlocked(request):
        return _render("networth", locked=True, pin_set=bool(unlock_code()), message=None, d=None)
    d, err = _load(desk_data.networth)
    return _render("networth", locked=False, d=d, error=err)


@app.post("/unlock")
async def unlock(request: Request):
    form = parse_qs((await request.body()).decode("utf-8", "ignore"))
    supplied = (form.get("pin") or [""])[0]
    guard: pin.PinGuard = app.state.guard
    if guard.locked():
        return _render("networth", locked=True, pin_set=True, d=None, message="Too many attempts. Locked for 5 minutes.")
    if not guard.attempt(supplied, unlock_code()):
        return _render("networth", locked=True, pin_set=bool(unlock_code()), d=None,
                       message="That PIN is not right." if unlock_code() else None)
    resp = RedirectResponse("/networth", status_code=303)
    resp.set_cookie(pin.COOKIE, pin.make_cookie(cookie_key()), max_age=pin.TTL_SECONDS, httponly=True,
                    samesite="strict", secure=request.url.scheme == "https", path="/")
    return resp


@app.post("/lock")
def lock():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(pin.COOKIE, path="/")
    return resp


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port())


if __name__ == "__main__":
    main()
