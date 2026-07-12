"""Shares CFO local server — read-only portfolio API.

Endpoints:
    GET /            -> tiny status page
    GET /health      -> per-account ok/degraded (book health)
    GET /portfolio   -> consolidated holdings, F&O positions, cash, net worth,
                        sector concentration, and degraded-account flags

Auth: if CFO_API_TOKEN is set in .env, every /portfolio and /health call must send
it (header `X-CFO-Token: <token>` or `?token=<token>`). If it's unset, calls are
allowed (local first-run) but a warning is logged.

Run (bind 0.0.0.0 so your phone can reach it):
    uvicorn shares_cfo.server:app --host 0.0.0.0 --port 8000
    # or:  python -m shares_cfo.server
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from .brokers.hdfc import HdfcAdapter, utc_now_iso
from .config import get_accounts, get_api_token, load_account
from .exceptions import SharesCFOError, TokenExpiredError
from .models import AccountBook, FundInfo, Holding, Position
from .normalise import normalise
from .sectors import SectorMap

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shares_cfo.server")

app = FastAPI(title="Shares CFO", version="0.1.0")


def _check_token(request: Request, token: str | None) -> None:
    expected = get_api_token()
    if not expected:
        log.warning("CFO_API_TOKEN is not set — server is unauthenticated (fine for local LAN, set it before exposing).")
        return
    supplied = request.headers.get("X-CFO-Token") or token
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid CFO token.")


async def _fetch_account(creds_key: str, sectors: SectorMap) -> AccountBook:
    """Fetch one account; degrade gracefully (never raise) so the book still completes."""
    try:
        account = load_account(creds_key)
    except SharesCFOError as exc:
        return AccountBook(creds_key=creds_key, ok=False, status="degraded", reason=str(exc))

    book = AccountBook(creds_key=creds_key, client_code=account.client_code)
    adapter = HdfcAdapter(account)
    try:
        raw_holdings = await adapter.get_holdings()
        raw_positions = await adapter.get_positions()
        raw_funds = await adapter.get_funds()

        book.holdings = [
            Holding(sector=sectors.sector_of(h["ticker"]), **h) for h in raw_holdings
        ]
        book.positions = [Position(**p) for p in raw_positions]
        book.funds = FundInfo(**raw_funds)
        book.fetched_at = utc_now_iso()
        book.ok = True
        book.status = "ok"
    except TokenExpiredError as exc:
        book.ok = False
        book.status = "degraded"
        book.reason = exc.action
    except SharesCFOError as exc:
        book.ok = False
        book.status = "degraded"
        book.reason = str(exc)
    finally:
        await adapter.close()
    return book


async def _consolidated() -> dict:
    sectors = SectorMap()
    books = [await _fetch_account(k, sectors) for k in get_accounts()]

    ok_books = [b for b in books if b.ok]
    degraded = [
        {"creds_key": b.creds_key, "reason": b.reason} for b in books if not b.ok
    ]

    all_holdings = [h for b in ok_books for h in b.holdings]
    holdings_value = sum(normalise("market_value", h.market_value) or 0.0 for h in all_holdings)
    cash = sum(normalise("available", b.funds.available) or 0.0 for b in ok_books)
    positions_pnl = sum(p.pnl + p.day_pnl for b in ok_books for p in b.positions)
    net_worth = holdings_value + cash

    return {
        "as_of": utc_now_iso(),
        "complete": len(degraded) == 0,
        "net_worth": round(net_worth, 2),
        "holdings_value": round(holdings_value, 2),
        "cash": round(cash, 2),
        "positions_pnl": round(positions_pnl, 2),
        "sector_concentration": sectors.concentration(all_holdings),
        "unmapped_sectors": sectors.missing(),
        "book_health": {
            "accounts": len(books),
            "fresh": len(ok_books),
            "degraded": len(degraded),
            "degraded_accounts": degraded,
        },
        "accounts": [b.to_dict() for b in books],
    }


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return (
        "<h2>Shares CFO — read-only</h2>"
        "<p>Endpoints: <code>/portfolio</code>, <code>/health</code></p>"
    )


@app.get("/health")
async def health(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    sectors = SectorMap()
    books = [await _fetch_account(k, sectors) for k in get_accounts()]
    degraded = [{"creds_key": b.creds_key, "reason": b.reason} for b in books if not b.ok]
    overall = "ok" if not degraded else "degraded"
    return {
        "status": overall,
        "as_of": utc_now_iso(),
        "accounts": [{"creds_key": b.creds_key, "status": b.status, "reason": b.reason} for b in books],
        "degraded_accounts": degraded,
    }


@app.get("/portfolio")
async def portfolio(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    return await _consolidated()


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("CFO_HOST", "0.0.0.0")
    port = int(os.environ.get("CFO_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
