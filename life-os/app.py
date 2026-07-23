"""Life OS — FastAPI app.

Serves the /life console and the /life/* CRUD + share-link API. Every data
route resolves a scope through the `_life_scope` two-token guard, so the same
endpoints serve the owner (full) and the partner (shared-only) with the
filtering done server-side in life.py.

This app mounts ONLY /life routes. That is deliberate: the share token has no
other endpoint in this process to reach, so it can never touch trading or
business data — the invariant holds by construction, not just by filtering.

Run:
    pip install -r requirements.txt
    python app.py                 # serves on $PORT (default 8600)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Load .env for local dev — containers inject env vars directly (no-op there).
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import life
from life import (
    LifeAuthError,
    LifeScope,
    _life_scope,
    create_item,
    delete_item,
    list_items,
    update_item,
)
from life_console import LIFE_HTML
from agents import _life_agent

PORT = int(os.environ.get("PORT", os.environ.get("LIFE_PORT", 8600)))

app = FastAPI(title="Life OS", version="1.0.0")


# ── token plumbing ───────────────────────────────────────────────────────────
def _extract_token(
    x_life_token: Optional[str],
    authorization: Optional[str],
    q_token: Optional[str],
) -> Optional[str]:
    """Pull the presented token from, in order: X-Life-Token header, an
    Authorization: Bearer header, or the `t`/`token` query param. The query
    param path exists because the partner opens a share LINK in a browser —
    GET /life?t=… — where a header can't be set."""
    if x_life_token:
        return x_life_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if q_token:
        return q_token
    return None


def _resolve(
    x_life_token: Optional[str],
    authorization: Optional[str],
    q_token: Optional[str],
) -> LifeScope:
    """Resolve a scope or raise 401. Never echoes the token in the error."""
    presented = _extract_token(x_life_token, authorization, q_token)
    try:
        return _life_scope(presented)
    except LifeAuthError:
        raise HTTPException(status_code=401, detail="unauthorized")
    except RuntimeError as e:
        # Misconfiguration (missing/identical secrets) — surface without leaking.
        raise HTTPException(status_code=500, detail=str(e))


# ── console ──────────────────────────────────────────────────────────────────
_GATE = (
    "<!doctype html><meta charset=utf-8>"
    "<body style='font-family:ui-monospace,monospace;background:#07100c;color:#87a094;"
    "padding:48px;text-align:center'>"
    "<h1 style='color:#7ed7b2;letter-spacing:.06em'>LIFE&middot;OS</h1>"
    "<p>This board is private. Open it with your link.</p></body>"
)


@app.get("/life", response_class=HTMLResponse)
def life_console(
    t: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """The console. Adapts to scope; renders a gate page (no data) if the token
    is missing/invalid, so an un-linked visitor learns nothing."""
    presented = _extract_token(x_life_token, authorization, t or token)
    try:
        scope = _life_scope(presented)
    except (LifeAuthError, RuntimeError):
        return HTMLResponse(_GATE, status_code=401)
    html = LIFE_HTML.replace("__SCOPE__", scope.scope).replace("__TOKEN__", presented or "")
    return HTMLResponse(html)


# ── items CRUD ───────────────────────────────────────────────────────────────
@app.get("/life/items")
def get_items(
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    scope = _resolve(x_life_token, authorization, t)
    return list_items(scope)  # owner: all · share: only shared (filtered server-side)


@app.post("/life/items", status_code=201)
async def post_item(
    request: Request,
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    scope = _resolve(x_life_token, authorization, t)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    try:
        return create_item(scope, payload)  # partner add forced shared in the store
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/life/items/{item_id}")
async def patch_item(
    item_id: str,
    request: Request,
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    scope = _resolve(x_life_token, authorization, t)
    patch = await request.json()
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    item = update_item(scope, item_id, patch)  # share: shared items, never the flag
    if item is None:
        raise HTTPException(status_code=404, detail="not found")
    return item


@app.delete("/life/items/{item_id}", status_code=204)
def del_item(
    item_id: str,
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    scope = _resolve(x_life_token, authorization, t)
    if not delete_item(scope, item_id):  # share: shared items only
        raise HTTPException(status_code=404, detail="not found")
    return Response(status_code=204)


# ── share link — owner only ──────────────────────────────────────────────────
@app.get("/life/share-link")
def share_link(
    request: Request,
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    """Build Jahnavi's link. Owner-only — the partner can't mint or see it."""
    scope = _resolve(x_life_token, authorization, t)
    if not scope.is_owner:
        raise HTTPException(status_code=403, detail="owner only")
    share_token = os.environ.get("CFO_SHARE_TOKEN", "")
    base = os.environ.get("LIFE_BASE_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    return {"url": f"{base}/life?t={share_token}"}


# ── nudges digest (the _life_agent) ──────────────────────────────────────────
@app.get("/life/nudges")
def nudges(
    x_life_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    t: Optional[str] = Query(default=None),
):
    """Due/overdue shared-item digest. Both scopes may read it — it is built
    only from shared items, so it exposes nothing private."""
    _resolve(x_life_token, authorization, t)  # authenticate (either scope)
    return _life_agent()


@app.get("/life/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    # Ensure the persistent volume path exists before serving.
    life.STATE_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
