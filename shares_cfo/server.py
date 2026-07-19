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

from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from fastapi.responses import RedirectResponse

from . import token_store
from .brokers import make_adapter
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
  <div class="card" id="health" style="display:none">
    <div class="row"><span style="font-weight:700">Holdings health</span><span class="dim" id="health-counts">…</span></div>
    <div id="health-list"></div>
    <div class="dim" style="font-size:12px;margin-top:8px">Upload Screener data below to sharpen this (debt, pledge, valuation, ROE).</div>
  </div>
  <div id="app"></div>
  <div class="card" id="ideas" style="display:none">
    <div class="row"><span style="font-weight:700">Top ideas</span><span class="dim" id="ideas-sub"></span></div>
    <div id="ideas-list"></div>
    <div class="dim" style="font-size:12px;margin-top:8px">Ranked from your Screener universe by quality/value. Not advice — a shortlist.</div>
  </div>
  <div class="card" id="screener">
    <div class="row"><span style="font-weight:700">Screener Premium</span><span class="dim" id="scr-state">…</span></div>
    <div class="dim" id="scr-detail" style="margin-top:6px">Checking loaded data…</div>
    <div style="margin-top:10px">
      <input type="file" id="scr-file" accept=".xlsx,.xls,.csv" style="color:var(--dim);font-size:13px">
      <button id="scr-btn" style="margin-top:8px;background:var(--bl);color:#04122b;border:0;border-radius:8px;padding:9px 14px;font-weight:700">Upload export</button>
      <div class="dim" id="scr-msg" style="margin-top:6px"></div>
    </div>
    <div class="dim" style="margin-top:8px;font-size:12px">Screener → open a Screen/Watchlist → <b>Export to Excel</b> → pick the file above.</div>
  </div>
  <p class="dim" style="text-align:center;margin-top:16px">prices as of last pull</p>
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
    if(a.positions&&a.positions.length){ h+='<div class="tag">F&O positions ('+a.positions.length+')</div>';
      a.positions.forEach(x=>{const g=x.pnl>=0; h+='<div class="hrow"><div><div>'+x.ticker+'</div><div class="dim">'+x.product_type+' · '+(x.quantity>0?'+':'')+x.quantity+' @ '+px(x.average_price)+'</div></div><div style="text-align:right"><div>'+px(x.last_price)+'</div><div class="'+(g?'gr':'rd')+'" style="font-size:12px">'+(g?'+':'')+inr(x.pnl)+'</div></div></div>';});
    }
    h+='</div>';
  });
  document.getElementById('app').innerHTML=h;
}
function scoreColor(s){ if(s==null)return 'var(--dim)'; if(s>=65)return 'var(--gr)'; if(s>=40)return 'var(--am)'; return 'var(--rd)'; }
async function loadHealth(){
  try{
    const r=await fetch('/screener/holdings?technicals=0&token='+encodeURIComponent(token));
    if(!r.ok)return; const d=await r.json();
    if(!d.holdings||!d.holdings.length)return;
    document.getElementById('health').style.display='block';
    const c=d.counts||{};
    document.getElementById('health-counts').textContent=
      (c['🔴']||0)+' 🔴  '+(c['🟡']||0)+' 🟡  '+(c['🟢']||0)+' 🟢';
    let h='';
    d.holdings.forEach(x=>{
      const fl=(x.flags&&x.flags.length)?x.flags.map(f=>f.sev+f.text).join(' · '):'looks clean';
      h+='<div class="hrow"><div><div>'+x.verdict+' '+x.symbol+'</div><div class="dim" style="font-size:12px">'+fl+'</div></div>'
        +'<div style="text-align:right"><div style="font-weight:700;color:'+scoreColor(x.score)+'">'+(x.score==null?'—':x.score)+'</div><div class="dim" style="font-size:11px">'+inr(x.market_value)+'</div></div></div>';
    });
    document.getElementById('health-list').innerHTML=h;
  }catch(e){}
}
async function loadIdeas(){
  try{
    const r=await fetch('/screener/scan?limit=8&min_score=55&token='+encodeURIComponent(token));
    if(!r.ok)return; const d=await r.json();
    if(!d.ideas||!d.ideas.length)return;
    document.getElementById('ideas').style.display='block';
    document.getElementById('ideas-sub').textContent=d.ranked+' of '+d.universe_size+' scored';
    let h='';
    d.ideas.forEach(x=>{
      const f=x.fields||{};
      const bits=[];
      if(f.roe!=null)bits.push('ROE '+Math.round(f.roe)+'%');
      if(f.de!=null)bits.push('D/E '+f.de);
      if(f.pe!=null)bits.push('P/E '+Math.round(f.pe));
      h+='<div class="hrow"><div><div>'+x.symbol+'</div><div class="dim" style="font-size:12px">'+bits.join(' · ')+'</div></div>'
        +'<div style="text-align:right"><div style="font-weight:700;color:'+scoreColor(x.fundamental_score)+'">'+x.fundamental_score+'</div></div></div>';
    });
    document.getElementById('ideas-list').innerHTML=h;
  }catch(e){}
}
async function loadScreener(){
  try{
    const r=await fetch('/fundamentals/screener/status?token='+encodeURIComponent(token));
    if(!r.ok)return; const s=await r.json();
    const st=document.getElementById('scr-state'), d=document.getElementById('scr-detail');
    if(s.loaded){ st.textContent='● loaded'; st.className='gr';
      d.innerHTML=s.companies+' companies · <span class="dim">'+s.active_file+'</span><br>fields: '
        +Object.keys(s.fields_detected||{}).join(', ')
        +(s.fields_missing&&s.fields_missing.length?' · <span class="am">missing: '+s.fields_missing.join(', ')+'</span>':''); }
    else { st.textContent='● none'; st.className='am'; d.textContent=s.reason||'no export loaded yet'; }
  }catch(e){}
}
document.getElementById('scr-btn').onclick=async function(){
  const f=document.getElementById('scr-file').files[0], msg=document.getElementById('scr-msg');
  if(!f){ msg.textContent='Pick a file first.'; return; }
  msg.textContent='Uploading '+f.name+'…';
  const fd=new FormData(); fd.append('file', f);
  try{
    const r=await fetch('/fundamentals/screener/upload?token='+encodeURIComponent(token),{method:'POST',body:fd});
    const j=await r.json();
    if(!r.ok){ msg.className='rd dim'; msg.textContent=(j&&j.detail)||('Upload failed ('+r.status+')'); return; }
    msg.className='gr dim'; msg.textContent='✅ Loaded '+(j.status&&j.status.companies||0)+' companies from '+f.name;
    loadScreener(); loadHealth(); loadIdeas();
  }catch(e){ msg.className='rd dim'; msg.textContent='Upload failed — server reachable?'; }
};
load(); loadScreener(); loadHealth(); loadIdeas(); setInterval(load, 20000);
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

    # On Railway the token comes from the daily phone-login (in-memory), not .env.
    stored = token_store.get_token(creds_key)
    if stored:
        account.access_token = stored

    book = AccountBook(creds_key=creds_key, client_code=account.client_code, label=account.label)
    adapter = make_adapter(account)  # HDFC or Angel by account.broker
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

        # Live prices (fetch-ltp) for equity holdings + F&O positions. Non-fatal:
        # any failure just leaves last-known prices in place.
        try:
            instruments = (
                [{"token": h.token, "exchange": h.exchange} for h in book.holdings if h.token]
                + [{"token": p.token, "exchange": p.exchange} for p in book.positions if p.token]
            )
            ltp = await adapter.fetch_ltp(instruments) if instruments else {}
            if ltp:
                for h in book.holdings:
                    q = ltp.get(h.token)
                    if q and q["ltp"]:
                        h.last_price = q["ltp"]
                        h.pnl = round(h.quantity * (h.last_price - h.average_price), 2)
                        if q["prev_close"]:
                            h.day_change = round(h.quantity * (h.last_price - q["prev_close"]), 2)
                for p in book.positions:
                    q = ltp.get(p.token)
                    if q and q["ltp"]:
                        p.last_price = q["ltp"]
                        p.pnl = round(p.quantity * (p.last_price - p.average_price), 2)
                        if q["prev_close"]:
                            p.day_pnl = round(p.quantity * (p.last_price - q["prev_close"]), 2)
                book.holdings.sort(key=lambda h: h.market_value, reverse=True)
            else:
                book.notes.append("live prices unavailable (fetch-ltp returned nothing)")
        except SharesCFOError as exc:
            book.notes.append(f"live prices unavailable ({exc})")
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


@app.get("/login", response_class=HTMLResponse)
async def login_hub(request: Request, token: str | None = Query(default=None)) -> str:
    """One page listing every account + its login status, with a Log-in link each."""
    _check_token(request, token)
    t = token or ""
    armed = set(token_store.armed_accounts())
    rows = ""
    for key in get_accounts():
        try:
            acc = load_account(key)
            label, code, broker = acc.label, acc.client_code, acc.broker
        except SharesCFOError:
            label, code, broker = key, "", "hdfc"
        on = key in armed
        badge = "#3fb950" if on else "#8b949e"
        status = "logged in" if on else "not logged in"
        if broker == "hdfc":
            link = f"<a href='/hdfc/login?key={key}&token={t}' style='color:#58a6ff'>Log in →</a>"
        else:
            link = "<span style='color:#8b949e'>Angel (separate)</span>"
        rows += (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:12px;border-bottom:1px solid #2a3038'>"
            f"<div><div>{label}</div><div style='color:#8b949e;font-size:12px'>{key} · {code}</div></div>"
            f"<div style='text-align:right'><div style='color:{badge};font-size:12px'>● {status}</div>{link}</div></div>"
        )
    return (
        "<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<div style='font-family:sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh;padding:16px'>"
        "<h2>Shares CFO — morning login</h2>"
        "<p style='color:#8b949e'>Tap Log in for each account (2FA on that holder's phone). Same-day tokens.</p>"
        f"<div style='background:#161b22;border:1px solid #2a3038;border-radius:14px;margin-top:12px'>{rows}</div>"
        f"<p style='margin-top:16px'><a href='/?token={t}' style='color:#58a6ff'>→ Open dashboard</a></p></div>"
    )


@app.get("/hdfc/login")
async def hdfc_login(request: Request, key: str = "HDFC1", token: str | None = Query(default=None)):
    """Phone login: redirects you to HDFC's 2FA. After you approve, HDFC calls
    /hdfc/callback and the server arms itself — no PC needed. Protected by the token."""
    _check_token(request, token)
    account = load_account(key)
    token_store.set_pending(key)  # remember which account this login is for
    return RedirectResponse(f"{account.base_url}/login?api_key={account.api_key}")


@app.get("/hdfc/callback", response_class=HTMLResponse)
async def hdfc_callback(
    requestToken: str | None = Query(default=None),
    request_token: str | None = Query(default=None),
    key: str | None = Query(default=None),
) -> str:
    """HDFC redirects here with the request token; we exchange it and arm the server."""
    rt = requestToken or request_token
    if not rt:
        return "<h3>No request token found in the callback URL.</h3>"
    key = (key or token_store.get_pending()).upper()  # which account we're arming
    account = load_account(key)
    adapter = HdfcAdapter(account)
    try:
        access_token = await adapter.exchange_request_token(rt)
    except SharesCFOError as exc:
        return f"<h3>Login failed: {exc}</h3>"
    finally:
        await adapter.close()
    token_store.set_token(key, access_token)
    return (
        f"<div style='font-family:sans-serif;padding:24px'>"
        f"<h2 style='color:#3fb950'>✅ {key} logged in for today.</h2>"
        f"<p>You can close this tab and open your dashboard.</p></div>"
    )


@app.get("/reconcile")
async def reconcile(request: Request, cadence: str = "daily",
                    token: str | None = Query(default=None)) -> dict:
    """Diff today's book vs the last snapshot: new trades, qty & cash changes."""
    _check_token(request, token)
    from . import reconcile as recon
    book = await _consolidated()
    return recon.run_daily(book)


@app.get("/events/{ticker}")
async def events(request: Request, ticker: str, token: str | None = Query(default=None)) -> dict:
    """Corporate actions + earnings date + headlines for a symbol (free)."""
    _check_token(request, token)
    from .analysis import events as ev
    return ev.get(ticker)


@app.get("/alerts")
async def alerts(request: Request, token: str | None = Query(default=None)) -> dict:
    """Current alerts on the live book (🔴/🟡/🟢), most severe first."""
    _check_token(request, token)
    from .analysis import alerts as alerts_mod
    book = await _consolidated()
    items = alerts_mod.evaluate(book)
    counts = {s: sum(1 for a in items if a["severity"] == s) for s in ("🔴", "🟡", "🟢")}
    return {"as_of": book["as_of"], "counts": counts, "alerts": items}


@app.get("/alerts/push")
async def alerts_push(request: Request, token: str | None = Query(default=None)) -> dict:
    """New critical alerts to actually push (max 5, 72h cooldown). App polls this."""
    _check_token(request, token)
    import time
    from .analysis import alert_state
    from .analysis import alerts as alerts_mod
    book = await _consolidated()
    now = time.time()
    pushable = alert_state.new_pushable(alerts_mod.evaluate(book), now)
    alert_state.mark_pushed(pushable, now)
    return {"push": pushable}


@app.get("/exposure")
async def exposure(request: Request, hedge: float = 0.5, beta: float = 1.0,
                   token: str | None = Query(default=None)) -> dict:
    """Net market exposure across ALL accounts + a NIFTY-futures hedge suggestion.
    `hedge` = fraction of equity to hedge (0.5 = 50%); `beta` = portfolio beta."""
    _check_token(request, token)
    from .analysis import exposure as expo
    from .analysis.prices import PriceDataUnavailable, get_spot

    book = await _consolidated()
    positions = [p for acc in book["accounts"] for p in acc.get("positions", [])]
    net = expo.net_exposure(book["holdings_value"], positions)

    hedge_block: dict = {}
    try:
        nifty = get_spot("^NSEI")
        hedge_block = {
            f"{int(f*100)}pct": expo.hedge_with_nifty_futures(book["holdings_value"], nifty, f, beta)
            for f in (0.25, hedge, 1.0)
        }
    except PriceDataUnavailable as exc:
        hedge_block = {"error": f"NIFTY spot unavailable ({exc})"}

    return {
        "as_of": book["as_of"],
        "accounts": book["book_health"]["accounts"],
        "net_worth": book["net_worth"],
        "net_exposure": net,
        "hedge_suggestions": hedge_block,
        "note": "Advisory only. Assumes beta≈1 and premium-notional for options; "
                "delta-aware exposure comes later. You execute any hedge yourself.",
    }


@app.get("/fundamentals/{ticker}")
async def fundamentals(request: Request, ticker: str, token: str | None = Query(default=None)) -> dict:
    """Fundamentals for a symbol (yfinance free + Screener CSV if exported)."""
    _check_token(request, token)
    from .analysis import fundamentals as fun
    return fun.get(ticker)


@app.get("/fundamentals/screener/status")
async def screener_status(request: Request, token: str | None = Query(default=None)) -> dict:
    """What Screener Premium data is loaded (active file, company count, mapped fields)."""
    _check_token(request, token)
    from .analysis import fundamentals as fun
    return fun.screener_status()


@app.post("/fundamentals/screener/upload")
async def screener_upload(request: Request, file: UploadFile = File(...),
                          token: str | None = Query(default=None)) -> dict:
    """Upload a Screener Premium export straight from your phone → the drop-zone.

    No git, no file manager. The newest file always wins on the next read.
    """
    _check_token(request, token)
    from .analysis import fundamentals as fun

    name = (file.filename or "").strip()
    ext = Path(name).suffix.lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400,
                            detail="Upload a Screener .xlsx (Export to Excel) or .csv file.")
    fun.SCREENER_DIR.mkdir(parents=True, exist_ok=True)
    # Timestamped, sanitised name so the newest upload sorts last (== wins).
    safe = "".join(c for c in Path(name).stem if c.isalnum() or c in ("-", "_"))[:40] or "screener"
    dest = fun.SCREENER_DIR / f"{utc_now_iso().replace(':', '').replace('.', '')}_{safe}{ext}"
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (15 MB max).")
    dest.write_bytes(data)
    status = fun.screener_status()
    return {"uploaded": dest.name, "bytes": len(data), "status": status}


def _clean_symbol(ticker: str) -> str:
    """Strip NSE series suffixes so 'TRENT-EQ' / 'SARVESHWAR-BE' -> matchable symbol."""
    s = (ticker or "").upper().strip()
    for suf in ("-EQ", "-BE", "-BZ", "-BL", "-SM", "-ST", "-IQ"):
        if s.endswith(suf):
            return s[:-len(suf)]
    return s.split("-")[0] if "-" in s else s


@app.get("/screener/holdings")
async def screener_holdings(request: Request, technicals: int = 1,
                            token: str | None = Query(default=None)) -> dict:
    """Score every stock you OWN (fundamental + optional technical), worst-first.

    The CFO watchdog: which holdings carry high debt, promoter pledge, rich
    valuation, or a broken trend. `technicals=0` for a faster fundamental-only pass.
    """
    _check_token(request, token)
    from .analysis import fundamentals as fun
    from .analysis import scoring
    from .analysis import technicals as tech_mod
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    book = await _consolidated()
    # Aggregate market value per unique symbol across all accounts.
    agg: dict[str, dict] = {}
    for acc in book["accounts"]:
        for h in acc.get("holdings", []):
            sym = _clean_symbol(h["ticker"])
            slot = agg.setdefault(sym, {"symbol": sym, "market_value": 0.0})
            slot["market_value"] += h.get("market_value") or 0.0

    rule = scoring.load_rule()
    rows = []
    for sym, slot in agg.items():
        f = fun.get(sym)
        t = None
        if technicals:
            try:
                data = get_ohlcv(sym)
                t = tech_mod.analyze(data["closes"], data["volumes"])
            except PriceDataUnavailable:
                t = None
        sc = scoring.combine(sym, f.get("fields", {}), t, rule)
        sc["market_value"] = round(slot["market_value"], 2)
        sc["confidence"] = f.get("confidence")
        rows.append(sc)

    # worst-first: reds, then lowest score. None scores (no data) sink to the bottom.
    order = {"🔴": 0, "🟡": 1, "⚪": 2, "🟢": 3}
    rows.sort(key=lambda x: (order.get(x["verdict"], 2), x["score"] if x["score"] is not None else 999))
    counts = {v: sum(1 for x in rows if x["verdict"] == v) for v in ("🔴", "🟡", "🟢", "⚪")}
    return {"as_of": book["as_of"], "counts": counts, "holdings": rows,
            "screener_loaded": fun.screener_status().get("loaded", False)}


@app.get("/screener/scan")
async def screener_scan(request: Request, limit: int = 20, min_score: float = 0.0,
                        technicals: int = 0, token: str | None = Query(default=None)) -> dict:
    """Rank the uploaded Screener universe as BUY ideas (fundamental score, then
    optional technicals on the top names). Needs a Screener export loaded."""
    _check_token(request, token)
    from .analysis import fundamentals as fun
    from .analysis import scoring
    from .analysis import technicals as tech_mod
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    universe = fun.load_universe()
    if not universe:
        return {"error": "No Screener export loaded — upload one from the dashboard first.",
                "ideas": []}
    rule = scoring.load_rule()
    scored = []
    for item in universe:
        fnd = scoring.score_fundamental(item["fields"], rule)
        if fnd["score"] is None or fnd["score"] < min_score:
            continue
        scored.append({"symbol": item["symbol"], "name": item.get("name"),
                       "fundamental_score": fnd["score"], "flags": fnd["flags"],
                       "fields": item["fields"], "coverage": fnd["coverage"]})
    scored.sort(key=lambda x: x["fundamental_score"], reverse=True)
    top = scored[: max(1, min(limit, 100))]

    if technicals:
        for row in top:
            try:
                data = get_ohlcv(row["symbol"])
                t = tech_mod.analyze(data["closes"], data["volumes"])
                blended = scoring.combine(row["symbol"], row["fields"], t, rule)
                row["technical_score"] = blended["technical_score"]
                row["score"] = blended["score"]
                row["verdict"] = blended["verdict"]
                row["flags"] = blended["flags"]
            except PriceDataUnavailable:
                row["technical_score"] = None
        top.sort(key=lambda x: x.get("score") or x["fundamental_score"], reverse=True)

    return {"universe_size": len(universe), "ranked": len(scored),
            "showing": len(top), "ideas": top}


@app.get("/screener/rule")
async def screener_rule_get(request: Request, token: str | None = Query(default=None)) -> dict:
    """The active scoring rule (defaults merged with any saved custom rule)."""
    _check_token(request, token)
    from .analysis import scoring
    return {"rule": scoring.load_rule(), "defaults": scoring.DEFAULT_RULE}


@app.post("/screener/rule")
async def screener_rule_set(request: Request, rule: dict = Body(...),
                            token: str | None = Query(default=None)) -> dict:
    """Save a custom scoring rule (any subset of thresholds/weights). Persisted."""
    _check_token(request, token)
    from .analysis import scoring
    return {"saved": True, "rule": scoring.save_rule(rule)}


@app.get("/idea/{ticker}")
async def idea(request: Request, ticker: str, token: str | None = Query(default=None)) -> dict:
    """Technicals + fundamentals + where they agree/disagree, for one symbol."""
    _check_token(request, token)
    from .analysis import fundamentals as fun
    from .analysis import technicals as tech
    from .analysis.prices import PriceDataUnavailable, get_ohlcv
    try:
        data = get_ohlcv(ticker)
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    t = tech.analyze(data["closes"], data["volumes"])
    f = fun.get(ticker)
    return {"ticker": ticker.upper(), "technicals": t, "fundamentals": f, "verdict": fun.combine(t, f)}


@app.get("/watchlist")
async def watchlist(request: Request, token: str | None = Query(default=None)) -> dict:
    """Scan the watchlist: technical + fundamental read + conflict flag, per name."""
    _check_token(request, token)
    from .analysis import fundamentals as fun
    from .analysis import technicals as tech
    from .analysis.prices import PriceDataUnavailable, get_ohlcv
    from .sectors import DEFAULT_WATCHLIST
    rows = []
    for sym in DEFAULT_WATCHLIST:
        try:
            data = get_ohlcv(sym)
            t = tech.analyze(data["closes"], data["volumes"])
            f = fun.get(sym)
            rows.append({"ticker": sym, "last_price": t.get("last_price"),
                         "dma_signal": t.get("dma_signal"), "rsi14": t.get("rsi14"),
                         "verdict": fun.combine(t, f), "confidence": f.get("confidence")})
        except PriceDataUnavailable:
            rows.append({"ticker": sym, "error": "no price data"})
    return {"watchlist": rows}


@app.get("/strategy/signal/{ticker}")
async def strategy_signal(request: Request, ticker: str, risk: float = 5000.0,
                          token: str | None = Query(default=None)) -> dict:
    """A risk-defined live-bet proposal for a symbol (entry/stop/target/size, R:R).
    `risk` = ₹ you're willing to lose on the bet; size is derived from it. Advisory."""
    _check_token(request, token)
    from .analysis import strategy, technicals as tech
    from .analysis.prices import PriceDataUnavailable, get_ohlcv
    try:
        data = get_ohlcv(ticker)
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    t = tech.analyze(data["closes"], data["volumes"])
    return strategy.signal(ticker, t, t.get("last_price") or 0.0, risk)


@app.get("/backtest/{ticker}")
async def backtest(request: Request, ticker: str, strategy: str = "dma_cross",
                   token: str | None = Query(default=None)) -> dict:
    """Backtest a rule on an NSE symbol, e.g. /backtest/RELIANCE?strategy=dma_cross.
    Strategies: dma_cross | price_above_200dma | rsi_meanrev. Free (yfinance)."""
    _check_token(request, token)
    from .analysis import backtest as bt
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    if strategy not in bt.STRATEGIES:
        raise HTTPException(status_code=400, detail=f"strategy must be one of {list(bt.STRATEGIES)}")
    try:
        data = get_ohlcv(ticker, period="5y")
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    result = bt.run(data["closes"], strategy)
    return {"ticker": ticker.upper(), "source": data["source"], "confidence": data["confidence"], **result}


_ORDER_FIELDS = ("creds_key", "exchange", "symbol", "token", "side", "quantity",
                 "product", "order_type", "price", "trigger_price", "underlying")


async def _day_pnl() -> float:
    """Rough intraday P&L across the book, for the daily-loss halt."""
    try:
        book = await _consolidated()
        return float(book.get("positions_pnl", 0.0)) + float(book.get("unrealised_pnl", 0.0))
    except Exception:
        return 0.0


@app.get("/execution/status")
async def execution_status(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from .execution import engine
    return engine.status()


@app.post("/execution/propose")
async def execution_propose(request: Request, order: dict = Body(...),
                            token: str | None = Query(default=None)) -> dict:
    """Validate an order against all guardrails and return a confirm summary. Sends nothing."""
    _check_token(request, token)
    from .execution import engine
    from .execution.guardrails import GuardrailError
    from .execution.models import OrderRequest
    try:
        o = OrderRequest(**{k: order[k] for k in _ORDER_FIELDS if k in order})
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad order fields: {exc}")
    try:
        return engine.propose(o, await _day_pnl())
    except GuardrailError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@app.post("/execution/confirm")
async def execution_confirm(request: Request, payload: dict = Body(...),
                            token: str | None = Query(default=None)) -> dict:
    """Confirm and place a previously-proposed order (blocked until the send is wired)."""
    _check_token(request, token)
    from .execution import engine
    from .execution.guardrails import GuardrailError
    pid, code = payload.get("proposal_id", ""), payload.get("confirm_code", "")
    try:
        return engine.confirm(pid, code, await _day_pnl())
    except GuardrailError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@app.post("/execution/kill")
async def execution_kill(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from .execution import engine
    return engine.engage_kill()


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("CFO_HOST", "0.0.0.0")
    # Railway injects PORT; fall back to CFO_PORT, then 8000 for local.
    port = int(os.environ.get("PORT", os.environ.get("CFO_PORT", "8000")))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
