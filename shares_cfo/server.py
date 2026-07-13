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

# Self-contained mobile web dashboard, served at "/". Open it in your phone's
# browser: http://<PC-LAN-IP>:8000/?token=<CFO_API_TOKEN>
DASHBOARD_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Shares CFO</title>
<style>
  :root{--bg:#0d1117;--card:#161b22;--card2:#1c2330;--bd:#2a3038;--tx:#e6edf3;--dim:#8b949e;--gr:#3fb950;--rd:#f85149;--bl:#58a6ff;--am:#d29922}
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  body{background:var(--bg);color:var(--tx);font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:14px 14px 40px}
  .dim{color:var(--dim);font-size:13px}
  .card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:16px;margin-top:12px}
  .row{display:flex;justify-content:space-between;align-items:center}
  h1{font-size:22px;font-weight:700}
  .hero{font-size:38px;font-weight:800;margin-top:2px}
  .metric{font-size:17px;font-weight:600;margin-top:2px}
  .bar{height:8px;background:var(--card2);border-radius:4px;margin-top:4px;overflow:hidden}
  .fill{height:8px;background:var(--bl);border-radius:4px}
  .hrow{display:flex;justify-content:space-between;padding:7px 0;border-top:1px solid var(--bd)}
  .gr{color:var(--gr)} .rd{color:var(--rd)} .am{color:var(--am)}
  .tag{font-size:11px;color:var(--dim);margin-top:12px;margin-bottom:2px}
  #err{color:var(--rd)}
</style></head>
<body>
  <div class="row"><h1>Shares CFO</h1><span class="dim" id="asof">…</span></div>
  <div id="err"></div>
  <div id="app"></div>
  <p class="dim" style="text-align:center;margin-top:16px">read-only • prices as of last pull</p>
<script>
const token = new URLSearchParams(location.search).get('token') || '';
function inr(n,sym){ if(sym===undefined)sym=true; const s=sym?'₹':''; if(n==null||isNaN(n))return s+'—';
  const a=Math.abs(n), sg=n<0?'-':''; if(a>=1e7)return sg+s+(a/1e7).toFixed(2)+' Cr'; if(a>=1e5)return sg+s+(a/1e5).toFixed(2)+' L';
  return sg+s+Math.round(a).toLocaleString('en-IN'); }
function pct(f){ return f==null||isNaN(f)?'—':(f*100).toFixed(1)+'%'; }
function px(n){ if(n==null||isNaN(n))return '₹—'; return '₹'+(Math.abs(n)<100? n.toFixed(2): Math.round(n).toLocaleString('en-IN')); }
function el(h){ const d=document.createElement('div'); d.innerHTML=h; return d; }
async function load(){
  try{
    const r=await fetch('/portfolio?token='+encodeURIComponent(token));
    if(!r.ok){ document.getElementById('err').textContent='Server '+r.status+' — check the token in the link.'; return; }
    document.getElementById('err').textContent='';
    render(await r.json());
  }catch(e){ document.getElementById('err').textContent='Cannot reach server. Same Wi-Fi? Firewall open?'; }
}
function render(p){
  document.getElementById('asof').textContent=new Date(p.as_of).toLocaleTimeString();
  const dc=p.day_change>=0, up=p.unrealised_pnl>=0, deg=p.book_health.degraded>0;
  let h='';
  h+='<div class="card"><div class="dim">Net worth</div><div class="hero">'+inr(p.net_worth)+'</div>'
    +'<div class="'+(dc?'gr':'rd')+'" style="font-weight:600">'+(dc?'▲':'▼')+' '+inr(Math.abs(p.day_change))+' ('+pct(Math.abs(p.day_change_pct))+') today</div>'
    +'<div class="'+(up?'gr':'rd')+'" style="font-size:13px">Unrealised P&L '+(up?'+':'−')+inr(Math.abs(p.unrealised_pnl))+' ('+pct(Math.abs(p.unrealised_pnl_pct))+')</div>'
    +'<div class="row" style="margin-top:10px">'
    +'<div><div class="dim">Holdings</div><div class="metric">'+inr(p.holdings_value)+'</div></div>'
    +'<div><div class="dim">Cash</div><div class="metric">'+inr(p.cash)+'</div></div>'
    +'</div></div>';
  h+='<div class="card" style="border-color:'+(deg?'var(--rd)':'var(--bd)')+'"><div class="row">'
    +'<span style="font-weight:700" class="'+(deg?'rd':'gr')+'">'+(deg?'Book incomplete':'Book complete')+'</span>'
    +'<span class="dim">'+p.book_health.fresh+'/'+p.book_health.accounts+' fresh</span></div>';
  (p.accounts||[]).forEach(a=>{(a.notes||[]).forEach(n=>{h+='<div class="am" style="font-size:12px;margin-top:6px">• '+n+'</div>';});});
  h+='</div>';
  if(p.sector_concentration&&p.sector_concentration.length){
    h+='<div class="card"><div class="dim" style="margin-bottom:8px">Sector concentration</div>';
    p.sector_concentration.slice(0,12).forEach(s=>{h+='<div style="margin:5px 0"><div class="row"><span>'+s.sector+'</span><span>'+pct(s.pct)+'</span></div><div class="bar"><div class="fill" style="width:'+Math.min(100,s.pct*100)+'%"></div></div></div>';});
    h+='</div>';
  }
  (p.accounts||[]).forEach(a=>{
    h+='<div class="card"><div class="row" style="margin-bottom:6px"><span style="font-weight:700">'+(a.label||a.creds_key)+'</span><span class="dim">'+a.client_code+'</span></div>';
    (a.holdings||[]).forEach(x=>{const g=x.pnl>=0; h+='<div class="hrow"><div><div>'+x.ticker+'</div><div class="dim">'+x.quantity+' @ '+px(x.average_price)+'</div></div><div style="text-align:right"><div>'+inr(x.market_value)+'</div><div class="'+(g?'gr':'rd')+'" style="font-size:12px">'+(g?'+':'')+inr(x.pnl)+'</div></div></div>';});
    if(a.positions&&a.positions.length){ h+='<div class="tag">F&O positions ('+a.positions.length+') · live P&L pending feed</div>';
      a.positions.forEach(x=>{h+='<div class="hrow"><div><div>'+x.ticker+'</div><div class="dim">'+x.product_type+'</div></div><div style="text-align:right"><div>'+(x.quantity>0?'+':'')+x.quantity+'</div><div class="dim">@ '+px(x.average_price)+'</div></div></div>';});
    }
    h+='</div>';
  });
  document.getElementById('app').innerHTML=h;
}
load(); setInterval(load, 20000);
</script>
</body></html>"""


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

    book = AccountBook(creds_key=creds_key, client_code=account.client_code, label=account.label)
    adapter = HdfcAdapter(account)
    try:
        # Holdings is the core of the book. A token-expiry here degrades everything;
        # any other holdings failure degrades the account.
        try:
            raw_holdings = await adapter.get_holdings()
            # Prefer HDFC's own sector_name; fall back to our map only when missing.
            book.holdings = [
                Holding(**{**h, "sector": h.get("sector") or sectors.sector_of(h["ticker"])})
                for h in raw_holdings
            ]
            book.holdings.sort(key=lambda h: h.market_value, reverse=True)  # biggest first
            book.ok = True
            book.status = "ok"
            book.fetched_at = utc_now_iso()
            if adapter.last_holdings_excluded:
                book.notes.append(
                    f"{adapter.last_holdings_excluded} F&O contracts excluded from holdings "
                    f"value (they appear under positions; holdings = equity delivery only)"
                )
        except TokenExpiredError as exc:
            book.ok = False; book.status = "degraded"; book.reason = exc.action
            return book
        except SharesCFOError as exc:
            book.ok = False; book.status = "degraded"; book.reason = str(exc)
            return book

        # Positions and funds are secondary: a failure here must NOT hide holdings.
        try:
            book.positions = [Position(**p) for p in await adapter.get_positions()]
        except TokenExpiredError as exc:
            book.ok = False; book.status = "degraded"; book.reason = exc.action; return book
        except SharesCFOError as exc:
            book.notes.append(f"positions unavailable ({exc})")

        try:
            book.funds = FundInfo(**await adapter.get_funds())
        except TokenExpiredError as exc:
            book.ok = False; book.status = "degraded"; book.reason = exc.action; return book
        except SharesCFOError as exc:
            book.notes.append(f"funds unavailable ({exc})")
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
    # Net worth cash = broker ledger balance (actual money), not the "cash limit"
    # field, which goes negative when F&O margin is deployed.
    cash = sum(normalise("available", b.funds.ledger_balance) or 0.0 for b in ok_books)
    # F&O realised P&L (overall). cumulative-positions has no LTP, so no unrealised MTM yet.
    positions_pnl = sum(p.pnl for b in ok_books for p in b.positions)
    net_worth = holdings_value + cash

    # Today's move on the holdings book (HDFC gives per-holding day_change).
    day_change = sum(h.day_change for h in all_holdings)
    prev_value = holdings_value - day_change
    day_change_pct = (day_change / prev_value) if prev_value else 0.0

    # Overall unrealised P&L on equity (computed: qty * (price - avg cost)).
    invested_value = sum(h.average_price * h.quantity for h in all_holdings)
    unrealised_pnl = holdings_value - invested_value
    unrealised_pnl_pct = (unrealised_pnl / invested_value) if invested_value else 0.0

    return {
        "as_of": utc_now_iso(),
        "complete": len(degraded) == 0,
        "net_worth": round(net_worth, 2),
        "holdings_value": round(holdings_value, 2),
        "invested_value": round(invested_value, 2),
        "unrealised_pnl": round(unrealised_pnl, 2),
        "unrealised_pnl_pct": round(unrealised_pnl_pct, 4),
        "cash": round(cash, 2),
        "day_change": round(day_change, 2),
        "day_change_pct": round(day_change_pct, 4),
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
    return DASHBOARD_HTML


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


@app.get("/analysis/{ticker}")
async def analysis(request: Request, ticker: str, token: str | None = Query(default=None)) -> dict:
    """Technical read for one NSE symbol (e.g. /analysis/COALINDIA). Free (yfinance)."""
    _check_token(request, token)
    # Lazy import so the core server runs even without pandas/yfinance installed.
    from .analysis import technicals
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    try:
        data = get_ohlcv(ticker)
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    tech = technicals.analyze(data["closes"], data["volumes"])
    return {
        "ticker": ticker.upper(),
        "source": data["source"],
        "confidence": data["confidence"],
        "bars": data["bars"],
        "technicals": tech,
    }


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("CFO_HOST", "0.0.0.0")
    port = int(os.environ.get("CFO_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
