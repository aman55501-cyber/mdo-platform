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

import asyncio
import logging
import os

from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from fastapi.responses import RedirectResponse

from . import token_store
from .brokers import make_adapter
from .brokers.hdfc import HdfcAdapter, utc_now_iso
from .config import (ACCOUNT_LABELS, DEFAULT_CLIENT_CODES, get_accounts,
                     get_api_token, load_account)
from .exceptions import SharesCFOError, TokenExpiredError
from .models import AccountBook, FundInfo, Holding, Position
from .normalise import normalise
from .sectors import SectorMap

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shares_cfo.server")

app = FastAPI(title="Shares CFO", version="0.1.0")

# CORS: every endpoint is token-gated (token in query, not cookies), so allowing any
# origin lets external design previews / a PWA read the live API without exposing more
# than the token already gates. No credentials (cookies) are used.
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

# Inject any app-connected accounts (added via the Login tab) into the environment
# so config.load_account picks them up alongside .env-defined accounts.
from . import account_store  # noqa: E402
try:
    account_store.apply_to_env()
except Exception:  # never let a bad store block startup
    pass

# Self-contained mobile web dashboard, served at "/". Open it in your phone's
# browser: http://<PC-LAN-IP>:8000/?token=<CFO_API_TOKEN>
DASHBOARD_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Shares CFO</title>
<style>
  :root{color-scheme:dark;
    --bg:#0a0e17;--panel:#111826;--elev:#18202f;--bd:#243049;--hair:#1b2333;
    --tx:#e9eef7;--dim:#8493ab;--faint:#5b6a83;
    --acc:#4c8dff;--up:#2fbd85;--down:#ff5867;--warn:#e0a53a;--purp:#a78bfa;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif}
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  body{background:var(--bg);color:var(--tx);font-family:var(--sans);font-size:15px;line-height:1.45;-webkit-font-smoothing:antialiased}
  .app{max-width:460px;margin:0 auto;padding:calc(56px + env(safe-area-inset-top)) 14px 94px;min-height:100vh}
  .mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
  .dim{color:var(--dim)}.faint{color:var(--faint)}.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn)}
  .card{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:16px;margin-bottom:12px}
  .lbl{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:600}
  .h2{font-weight:700;font-size:15px}.frag{font-size:10.5px;color:var(--acc);border:1px solid rgba(76,141,255,.4);border-radius:6px;padding:2px 7px;font-weight:700}
  .rowline{display:flex;justify-content:space-between;align-items:baseline;margin-top:11px}
  /* accounts (polished) */
  .acct{display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--hair)}
  .acct:first-child{border-top:0}
  .av{width:34px;height:34px;border-radius:10px;flex:none;display:grid;place-items:center;font-weight:800;font-size:13px;color:#08101f}
  .an{font-weight:650;font-size:14.5px}
  .abar{height:5px;border-radius:3px;background:var(--elev);margin-top:7px;overflow:hidden}
  .abar>i{display:block;height:100%;border-radius:3px}
  /* movers (polished) */
  .mv{display:flex;align-items:center;gap:10px;padding:9px 0}
  .mvtag{width:26px;height:26px;border-radius:8px;flex:none;display:grid;place-items:center;font-size:13px;font-weight:800}
  .mvtag.g{background:rgba(51,214,159,.14);color:var(--up)}.mvtag.l{background:rgba(255,93,115,.14);color:var(--down)}
  .mvn{font-weight:650;font-size:14px}
  .mvr{margin-left:auto;text-align:right;font-family:var(--mono)}
  .mvhead{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);font-weight:700;margin:10px 0 2px}
  /* fixed top app bar */
  .appbar{position:fixed;top:0;left:0;right:0;z-index:16;max-width:460px;margin:0 auto;
    background:rgba(12,17,26,.94);backdrop-filter:blur(14px);border-bottom:1px solid var(--bd);
    display:flex;align-items:center;justify-content:space-between;
    padding:calc(env(safe-area-inset-top) + 9px) 15px 9px}
  .ttl{display:flex;align-items:center;gap:9px;font-weight:750;font-size:16px;min-width:0}
  .ttl .mark{width:26px;height:26px;border-radius:8px;flex:none;background:linear-gradient(150deg,var(--acc),#2f6bd0);display:grid;place-items:center;font-size:14px;color:#07101f;font-weight:800}
  .ttl .dot{width:7px;height:7px;border-radius:50%;background:var(--up);flex:none}
  .hdrnw{text-align:right;line-height:1.15;flex:none}
  .hdrnw .v{font-family:var(--mono);font-weight:750;font-size:15px;letter-spacing:-.3px}
  .hdrnw .d{font-size:11px;font-weight:600;margin-top:1px}
  .brand{display:flex;align-items:center;gap:9px;font-weight:700}
  .brand .mark{width:26px;height:26px;border-radius:7px;background:linear-gradient(150deg,var(--acc),#2f6bd0);display:grid;place-items:center;font-size:14px}
  .pill{font-size:11.5px;font-weight:600;padding:5px 10px;border-radius:999px;border:1px solid var(--bd);display:inline-flex;align-items:center;gap:6px;color:var(--dim)}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--up)}
  .nw{font-size:38px;font-weight:800;letter-spacing:-1px;margin-top:3px}
  .spark{width:100%;height:42px;display:block;margin-top:10px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
  .stat .v{font-size:17px;font-weight:700;margin-top:1px}
  .meterrow{display:flex;align-items:center;gap:12px;margin-top:12px}.meterrow .name{width:92px;flex:none}
  .meter{flex:1;height:9px;border-radius:5px;background:var(--elev);overflow:hidden}.meter>i{display:block;height:100%;border-radius:5px;width:0;transition:width .5s}
  .score{width:40px;text-align:right;font-weight:700}
  .counts{display:flex;gap:16px;margin-top:14px;padding-top:13px;border-top:1px solid var(--hair)}.counts b{font-size:19px;font-weight:800;font-family:var(--mono)}
  .chip{font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:3px 7px;border-radius:6px;text-transform:uppercase}
  .chip.s{background:rgba(47,189,133,.14);color:var(--up)}.chip.n{background:rgba(132,147,171,.14);color:var(--dim)}.chip.w{background:rgba(255,88,103,.14);color:var(--down)}
  .filters{display:flex;gap:8px;overflow-x:auto;padding:2px 0 10px;scrollbar-width:none}.filters::-webkit-scrollbar{display:none}
  .fchip{flex:none;font-size:13px;font-weight:600;padding:7px 13px;border-radius:999px;border:1px solid var(--bd);color:var(--dim);background:transparent}
  .fchip[aria-pressed="true"]{background:var(--acc);border-color:var(--acc);color:#04122b}
  .sel{background:var(--elev);color:var(--tx);border:1px solid var(--bd);border-radius:9px;padding:7px 11px;font-size:13px;font-weight:600;font-family:var(--sans);max-width:56%;appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238493ab' stroke-width='3'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px}
  .acctchip{font-size:9.5px;font-weight:700;letter-spacing:.02em;padding:2px 6px;border-radius:5px;background:rgba(76,141,255,.12);color:var(--acc);text-transform:uppercase}
  .snews a:active{opacity:.6}
  .newsitem{display:block;padding:9px 0;border-top:1px solid var(--hair);text-decoration:none;color:var(--tx)}
  .newsitem:first-child{border-top:0}
  .holds{display:flex;flex-direction:column;gap:10px}
  .h{background:var(--panel);border:1px solid var(--bd);border-radius:14px;overflow:hidden}.h.weak{border-color:rgba(255,88,103,.4)}
  .htop{display:flex;align-items:center;gap:12px;padding:13px 14px;cursor:pointer}
  .sev{width:4px;align-self:stretch;border-radius:3px;flex:none;margin:-13px 0;background:var(--dim)}
  .h.strong .sev{background:var(--up)}.h.weak .sev{background:var(--down)}.h.neutral .sev{background:var(--warn)}
  .sym{font-weight:700;font-size:15.5px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
  .sub{font-size:12px;color:var(--dim);margin-top:2px}
  .right{margin-left:auto;text-align:right}.val{font-weight:700;font-size:15px}
  .chev{margin-left:6px;color:var(--faint);transition:transform .18s;flex:none}.h.open .chev{transform:rotate(180deg)}
  .detail{max-height:0;overflow:hidden;transition:max-height .24s ease}.h.open .detail{max-height:520px}
  .metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--hair);border-top:1px solid var(--hair)}
  .m{background:var(--panel);padding:11px 13px}.m .k{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint);font-weight:600}
  .m .d{font-size:15px;font-weight:700;margin-top:3px;font-family:var(--mono)}.m .note{font-size:11px;margin-top:1px}
  .actions{display:flex;gap:8px;padding:12px 13px 13px;background:var(--panel)}
  .btn{flex:1;border:0;border-radius:10px;padding:11px 0;font-weight:700;font-size:14px;font-family:var(--sans)}
  .buy{background:var(--up);color:#04160e}.sell{background:var(--down);color:#210407}.hedge{background:var(--acc);color:#04122b}
  .btn:active{transform:translateY(1px)}
  .regbadge{display:inline-flex;gap:7px;align-items:center;font-weight:800;font-size:14px;padding:7px 13px;border-radius:999px}
  .signals{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:11px;overflow:hidden;margin-top:13px}
  .sig{background:var(--panel);padding:10px}.sig .n{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600}.sig .v{font-size:15px;font-weight:800;margin-top:3px;font-family:var(--mono)}
  .idea{border:1px solid var(--bd);border-radius:14px;overflow:hidden;margin-bottom:11px;background:var(--panel)}
  .itop{display:flex;align-items:center;gap:10px;padding:13px 14px 11px}
  .conv{width:44px;height:44px;border-radius:11px;display:grid;place-items:center;font-weight:800;font-size:17px;font-family:var(--mono);flex:none;background:rgba(47,189,133,.13);color:var(--up);border:1px solid rgba(47,189,133,.3)}
  .isym{font-weight:800;font-size:16px}.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:3px}
  .tag{font-size:10px;font-weight:700;padding:2px 7px;border-radius:5px;text-transform:uppercase}
  .tag.pat{background:rgba(132,147,171,.14);color:var(--dim)}
  .confl{display:flex;gap:6px;padding:0 14px 12px;flex-wrap:wrap}.cf{font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;background:var(--elev);border:1px solid var(--bd)}
  .iact{display:flex;gap:8px;padding:0 14px 13px}
  .ghost{background:var(--elev);border:1px solid var(--bd);color:var(--tx)}
  .barstack{display:flex;height:12px;border-radius:6px;overflow:hidden;margin-top:12px;background:var(--elev)}
  .glob{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:12px;overflow:hidden;margin-top:12px}
  .g{background:var(--panel);padding:10px 12px}.g .n{font-size:12px;color:var(--dim)}.g .v{font-size:15.5px;font-weight:700;margin-top:2px;font-family:var(--mono)}
  .hedgebtns{display:flex;gap:8px;margin-top:14px}.hb{flex:1;border:1px solid var(--bd);background:var(--elev);color:var(--tx);border-radius:10px;padding:10px 0;font-weight:700;font-size:13px}.hb.on{background:var(--acc);border-color:var(--acc);color:#04122b}
  .big{font-size:26px;font-weight:800;letter-spacing:-.5px;margin-top:4px}
  .tr{display:flex;gap:10px;align-items:center;padding:11px 0;border-top:1px solid var(--hair)}
  .side{font-size:10.5px;font-weight:800;padding:3px 7px;border-radius:6px;flex:none}
  .side.b{background:rgba(47,189,133,.15);color:var(--up)}.side.s{background:rgba(255,88,103,.15);color:var(--down)}.side.h{background:rgba(76,141,255,.15);color:var(--acc)}
  .stt{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:6px;margin-left:auto;flex:none}
  .stt.SENT{background:rgba(47,189,133,.15);color:var(--up)}.stt.PROPOSE{background:rgba(132,147,171,.15);color:var(--dim)}.stt.KILL_SWITCH{background:rgba(255,88,103,.15);color:var(--down)}
  .note{font-size:11.5px;color:var(--faint);margin-top:10px;line-height:1.5}
  .nav{position:fixed;left:0;right:0;bottom:0;z-index:15;max-width:460px;margin:0 auto;background:rgba(13,18,28,.92);backdrop-filter:blur(12px);border-top:1px solid var(--bd);display:grid;grid-template-columns:repeat(7,1fr);padding:8px 2px calc(8px + env(safe-area-inset-bottom))}
  .nav button{background:0;border:0;color:var(--faint);font-family:var(--sans);font-size:9.5px;font-weight:600;display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px 0}
  .nav svg{width:21px;height:21px}
  /* income proposals */
  .prop{border:1px solid var(--bd);border-radius:14px;padding:13px 14px;margin-top:10px;background:var(--panel)}
  .ptop{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .psym{font-weight:800;font-size:15.5px}
  .tag{font-size:9px;font-weight:700;padding:2px 6px;border-radius:6px;text-transform:uppercase;letter-spacing:.02em}
  .tag.cc{background:rgba(51,214,159,.14);color:var(--up)}.tag.csp{background:rgba(201,139,255,.15);color:var(--purp)}
  .tag.live{background:rgba(76,141,255,.14);color:var(--acc)}.tag.theo{background:rgba(240,178,74,.14);color:var(--warn)}
  .pinc{font-size:19px;font-weight:800;margin-top:8px}
  .pgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:10px;overflow:hidden;margin-top:10px}
  .pg{background:var(--panel);padding:7px 9px}.pg .k{font-size:8.5px;text-transform:uppercase;letter-spacing:.03em;color:var(--faint);font-weight:700}.pg .v{font-size:13px;font-weight:750;margin-top:2px;font-family:var(--mono)}
  .iseg{display:flex;gap:6px;margin:12px 0 2px}
  .iseg button{flex:1;background:var(--elev);border:1px solid var(--bd);color:var(--dim);border-radius:9px;padding:8px 0;font-weight:700;font-size:12.5px}
  .iseg button.on{background:rgba(51,214,159,.13);border-color:#2f5c4b;color:var(--up)}
  .nav button svg{width:21px;height:21px}
  .nav button{position:relative;transition:color .15s}
  .nav button[aria-current="true"]{color:var(--acc)}
  .nav button[aria-current="true"]::before{content:"";position:absolute;top:-8px;left:50%;transform:translateX(-50%);width:22px;height:3px;border-radius:0 0 3px 3px;background:var(--acc)}
  .scrim{position:fixed;inset:0;background:rgba(4,7,13,.66);opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}.scrim.on{opacity:1;pointer-events:auto}
  .sheet{position:fixed;left:0;right:0;bottom:0;z-index:21;max-width:460px;margin:0 auto;background:var(--panel);border:1px solid var(--bd);border-bottom:0;border-radius:20px 20px 0 0;padding:18px 16px calc(24px + env(safe-area-inset-bottom));transform:translateY(103%);transition:transform .26s cubic-bezier(.2,.7,.2,1)}
  .sheet.on{transform:translateY(0)}
  .grab{width:40px;height:4px;border-radius:2px;background:var(--bd);margin:-6px auto 14px}
  .tk-side{font-size:12px;font-weight:800;padding:4px 9px;border-radius:7px;text-transform:uppercase}
  .rr{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:12px;overflow:hidden;margin-top:14px}
  .rr>div{background:var(--panel);padding:12px 8px;text-align:center}.rr .k{font-size:10px;text-transform:uppercase;color:var(--faint);font-weight:600}.rr .v{font-size:16px;font-weight:800;margin-top:3px;font-family:var(--mono)}
  .rrbar{display:flex;height:8px;border-radius:5px;overflow:hidden;margin-top:12px}
  .guard{display:flex;gap:9px;margin-top:14px;padding:11px 12px;border-radius:11px;background:rgba(224,165,58,.09);border:1px solid rgba(224,165,58,.3);font-size:12.5px;line-height:1.5}
  .confirm{width:100%;margin-top:14px;border:0;border-radius:12px;padding:14px 0;font-weight:800;font-size:15px;background:var(--elev);color:var(--faint)}
  h1.screen{display:none}
  section{display:none}section.on{display:block}
  .load{color:var(--faint);text-align:center;padding:24px;font-size:13px}
  #err{color:var(--down);text-align:center;font-size:13px;margin:6px 0}
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style></head>
<body>
<div class="app">
  <div class="appbar">
    <div class="ttl"><span class="mark">&#8377;</span><span id="hdr-title">Home</span><span class="dot" id="hdr-dot" title=""></span></div>
    <div class="hdrnw"><div class="v" id="hdr-nw">&#8377;&mdash;</div><div class="d dim" id="hdr-day">&hellip;</div></div>
  </div>
  <div id="err"></div>

  <section id="s-home" class="on">
    <div class="card">
      <div class="lbl">Consolidated net worth</div>
      <div class="nw mono" id="nw">&#8377;&mdash;</div>
      <div class="mono" id="day" style="font-weight:700;margin-top:2px">&hellip;</div>
      <canvas class="spark" id="spark" width="920" height="84" aria-hidden="true"></canvas>
      <div class="grid2">
        <div class="stat"><div class="lbl">Unrealised P&amp;L</div><div class="v mono" id="upnl">&mdash;</div></div>
        <div class="stat"><div class="lbl">Cash / margin</div><div class="v mono" id="cash">&mdash;</div></div>
        <div class="stat"><div class="lbl">Invested</div><div class="v mono" id="inv">&mdash;</div></div>
        <div class="stat"><div class="lbl">F&amp;O realised</div><div class="v mono" id="fopnl">&mdash;</div></div>
      </div>
    </div>
    <div class="card"><div class="lbl">Accounts</div><div id="acct-list" style="margin-top:8px"><div class="load" style="padding:8px">…</div></div></div>
    <div class="card"><div class="lbl">Today's movers</div><div id="movers" style="margin-top:6px"><div class="load" style="padding:8px">…</div></div></div>
    <div class="card" style="padding:0;overflow:hidden">
      <div class="htop" style="padding:15px 16px;cursor:pointer" onclick="toggleHoldings()">
        <div style="min-width:0"><div class="h2">All holdings <span class="faint" id="hold-count"></span></div><div class="sub" id="hold-sub">tap to view the full list</div></div>
        <svg class="chev" id="hold-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" style="margin-left:auto"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>
      </div>
      <div id="allhold-body" style="display:none;padding:0 14px 14px">
        <select id="acct-sel" class="sel" style="max-width:100%;width:100%;margin-bottom:8px"><option value="ALL">All accounts</option></select>
        <div class="filters" id="filters"><button class="fchip" aria-pressed="true">All</button><button class="fchip" aria-pressed="false">Strong</button><button class="fchip" aria-pressed="false">Weak</button><button class="fchip" aria-pressed="false">Vol surge</button></div>
        <div class="holds" id="holds"><div class="load">Loading&hellip;</div></div>
      </div>
    </div>
    <div class="card" style="padding:0;overflow:hidden">
      <div class="htop" style="padding:15px 16px;cursor:pointer" onclick="toggleMore()">
        <div style="min-width:0"><div class="h2">More insights</div><div class="sub">book strength &middot; volume &middot; news &middot; Screener</div></div>
        <svg class="chev" id="more-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" style="margin-left:auto"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>
      </div>
      <div id="more-body" style="display:none;padding:2px 15px 15px">
        <div style="border-top:1px solid var(--hair);padding-top:12px">
          <div style="display:flex;justify-content:space-between;align-items:center"><span class="lbl">Book strength</span><span class="faint" id="strengthsub" style="font-size:11px">scoring&hellip;</span></div>
          <div class="meterrow"><span class="name">Fundamental</span><span class="meter"><i id="mfund" style="background:linear-gradient(90deg,var(--warn),#e8b95e)"></i></span><span class="score mono" id="sfund">&mdash;</span></div>
          <div class="meterrow"><span class="name">Technical</span><span class="meter"><i id="mtech" style="background:linear-gradient(90deg,var(--up),#5fd8a6)"></i></span><span class="score mono" id="stech">&mdash;</span></div>
          <div class="counts" id="counts"></div>
        </div>
        <div style="border-top:1px solid var(--hair);padding-top:12px;margin-top:12px">
          <div class="lbl">Volume spikes <span class="faint" style="font-size:10px">vs 20-day avg</span></div>
          <div id="volspikes" style="margin-top:8px"><div class="dim" style="font-size:12px;padding:6px 0">loading…</div></div>
        </div>
        <div style="border-top:1px solid var(--hair);padding-top:12px;margin-top:12px">
          <div style="display:flex;justify-content:space-between;align-items:center"><span class="lbl">News on your holdings</span><span class="faint" style="font-size:10px">Google News</span></div>
          <div id="homenews" style="margin-top:4px"><div class="dim" style="font-size:12px;padding:6px 0">loading…</div></div>
        </div>
        <div style="border-top:1px solid var(--hair);padding-top:12px;margin-top:12px" id="screener">
          <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Screener Premium</span><span class="dim" id="scr-state">&hellip;</span></div>
          <div class="dim" id="scr-detail" style="margin-top:6px;font-size:13px">Upload your Screener export to power fundamentals &amp; ideas.</div>
          <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            <input type="file" id="scr-file" accept=".xlsx,.xls,.csv" style="color:var(--dim);font-size:13px;max-width:60%">
            <button class="btn hedge" id="scr-btn" style="flex:0 0 auto;padding:9px 16px">Upload</button>
          </div>
          <div class="dim" id="scr-msg" style="margin-top:6px;font-size:12px"></div>
          <div class="dim" style="margin-top:8px;font-size:11.5px">screener.in → Watchlist/Screen → Export to Excel → pick it here.</div>
        </div>
      </div>
    </div>
  </section>

  <section id="s-ideas">
    <h1 class="screen">Daily Strategy &amp; ideas</h1>
    <div class="card" id="strategy-card"><div class="load">Building today's strategy…</div></div>
    <div class="card" id="regime-card" style="background:linear-gradient(160deg,#15110a,#111826);border-color:#3a2f18">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Market regime</span><span class="frag">drives sizing</span></div>
      <div id="regime-body"><div class="load">Reading regime&hellip;</div></div>
    </div>
    <div class="card" id="oi-card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">OI build-up</span><span class="frag">futures positioning</span></div>
      <div id="oi-body" style="margin-top:8px"><div class="load">Reading open interest&hellip;</div></div>
    </div>
    <div style="display:flex;justify-content:space-between;margin:2px 2px 10px"><span class="lbl">Ideas</span><span class="faint" id="ideas-sub" style="font-size:11px"></span></div>
    <div id="ideas"><div class="load">Scanning&hellip;</div></div>
  </section>

  <section id="s-hedge">
    <h1 class="screen">Exposure &amp; hedge</h1>
    <div class="card" id="expo-card"><div class="load">Loading exposure&hellip;</div></div>
    <div class="card" id="hedge-card" style="display:none">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Portfolio hedge</span><span class="frag">NIFTY futures</span></div>
      <div class="note" id="hedge-warn" style="margin-top:6px"></div>
      <div class="hedgebtns"><button class="hb" data-f="0.25">25%</button><button class="hb on" data-f="0.5">50%</button><button class="hb" data-f="1.0">100%</button></div>
      <div id="hedge-body"></div>
      <button class="btn hedge" style="width:100%;margin-top:14px" id="hedge-go">Review hedge order →</button>
    </div>
    <div class="card" id="opt-card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Option strategy</span><span class="frag">payoff builder</span></div>
      <div style="display:flex;gap:8px;margin-top:12px">
        <select id="opt-name" style="flex:1;background:var(--elev);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:9px;font-size:13px"></select>
        <select id="opt-under" style="background:var(--elev);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:9px;font-size:13px"><option>NIFTY</option><option>BANKNIFTY</option></select>
      </div>
      <canvas id="opt-canvas" width="860" height="300" style="width:100%;height:auto;margin-top:12px;display:block"></canvas>
      <div id="opt-metrics"></div>
      <div class="note" id="opt-note"></div>
    </div>
  </section>

  <section id="s-income">
    <h1 class="screen">Income &mdash; premium engine</h1>
    <div class="card" id="inc-hero" style="background:linear-gradient(160deg,#0d1a16,#0f1521);border-color:#1f3a30">
      <div class="lbl">Premium available this cycle</div>
      <div class="nw mono up" id="inc-total" style="font-size:32px">&#8377;&mdash;</div>
      <div class="dim" id="inc-sub" style="font-size:12.5px;margin-top:2px">loading proposals&hellip;</div>
      <div class="grid2" style="margin-top:12px">
        <div class="stat"><div class="lbl">Covered calls</div><div class="v mono up" id="inc-cc">&mdash;</div></div>
        <div class="stat"><div class="lbl">Cash puts</div><div class="v mono" id="inc-csp" style="color:var(--purp)">&mdash;</div></div>
      </div>
    </div>
    <div class="iseg"><button id="inc-tab-cc" class="on" onclick="incTab('cc')">Covered calls</button><button id="inc-tab-csp" onclick="incTab('csp')">Cash puts</button></div>
    <div id="inc-list"><div class="load">Scanning your book for premium&hellip;</div></div>
    <div class="note" style="margin-top:12px">Live premium from the NFO chain where liquid, else Black-Scholes (India VIX). Every <b>Place</b> runs the guardrails (caps, allow-list, kill-switch) before it reaches the broker.</div>
  </section>

  <section id="s-mtf">
    <h1 class="screen">MTF — margin funding</h1>
    <div class="card" id="mtf-card"><div class="load">Loading MTF view…</div></div>
  </section>

  <section id="s-trades">
    <h1 class="screen">Trade log</h1>
    <div class="card" id="exec-status"></div>
    <div class="card"><div class="h2">Recent activity</div><div id="trades"><div class="load">Loading log&hellip;</div></div>
      <div class="note">Every proposal + placement is written to an immutable audit file — time, price, R:R, guardrail result.</div></div>
  </section>
</div>

<nav class="nav" id="nav">
  <button data-t="home" aria-current="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>Home</button>
  <button data-t="mtf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 10h18M6 3h12a3 3 0 013 3v12a3 3 0 01-3 3H6a3 3 0 01-3-3V6a3 3 0 013-3z"/><path d="M7 15h4"/></svg>MTF</button>
  <button data-t="ideas"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0012 3z"/></svg>Ideas</button>
  <button data-t="income"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>Income</button>
  <button data-t="hedge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg>Hedge</button>
  <button data-t="trades"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V5M4 15l5-5 4 3 7-8"/></svg>Trades</button>
  <button data-t="login"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><path d="M10 17l5-5-5-5M15 12H3"/></svg>Login</button>
</nav>

<div class="scrim" id="cscrim"></div>
<div class="sheet" id="csheet" role="dialog" aria-modal="true" aria-label="Chart" style="max-height:82vh;overflow-y:auto">
  <div class="grab"></div>
  <div style="display:flex;justify-content:space-between;align-items:baseline"><span id="c-sym" style="font-weight:800;font-size:18px">—</span><span id="c-last" class="mono dim"></span></div>
  <canvas id="cchart" width="900" height="360" style="width:100%;height:auto;margin-top:12px;display:block"></canvas>
  <div style="display:flex;gap:14px;margin-top:6px;font-size:11px" class="dim"><span><span style="color:var(--acc)">━</span> price</span><span><span style="color:var(--warn)">━</span> 50-DMA</span><span><span style="color:var(--purp)">━</span> 200-DMA</span><span><span style="color:var(--up)">┄</span> R</span><span><span style="color:var(--down)">┄</span> S</span></div>
  <div id="c-lvls" class="note" style="margin-top:8px"></div>
</div>

<div class="scrim" id="scrim"></div>
<div class="sheet" id="sheet" role="dialog" aria-modal="true">
  <div class="grab"></div>
  <div style="display:flex;align-items:center;gap:10px"><span class="tk-side" id="tk-side">BUY</span><span style="font-weight:800;font-size:18px" id="tk-sym">—</span><span class="dim mono" id="tk-ltp" style="margin-left:auto">—</span></div>
  <div class="rowline"><span class="dim">Quantity</span><span class="mono" id="tk-qty" style="font-weight:700">—</span></div>
  <div class="rowline"><span class="dim">Entry</span><span class="mono" id="tk-entry" style="font-weight:700">—</span></div>
  <div class="rowline"><span class="dim">Stop-loss</span><span class="mono down" id="tk-stop" style="font-weight:700">—</span></div>
  <div class="rowline"><span class="dim">Target</span><span class="mono up" id="tk-tgt" style="font-weight:700">—</span></div>
  <div class="rr"><div><div class="k">Risk</div><div class="v down" id="tk-risk">—</div></div><div><div class="k">Reward</div><div class="v up" id="tk-rew">—</div></div><div><div class="k">R:R</div><div class="v" id="tk-rr">—</div></div></div>
  <div class="rrbar"><span style="width:33.3%;background:var(--down)"></span><span style="flex:1;background:var(--up)"></span></div>
  <div class="guard"><span style="font-size:15px">🔒</span><div id="tk-guardtxt">Validating…</div></div>
  <button class="confirm" id="tk-confirm" disabled>Review…</button>
</div>

<script>
const token=new URLSearchParams(location.search).get('token')||'';
const Q='token='+encodeURIComponent(token);
const loaded={ideas:0,hedge:0,trades:0,mtf:0,income:0};
let PORT=null,CURR=null,HEDGE=null,acctSelBuilt=false;
const SCORE={},ACCT_LABELS={},HOLD={};
function inr(n){if(n==null||isNaN(n))return '₹—';const a=Math.abs(n),s=n<0?'-':'';if(a>=1e7)return s+'₹'+(a/1e7).toFixed(2)+' Cr';if(a>=1e5)return s+'₹'+(a/1e5).toFixed(2)+' L';return s+'₹'+Math.round(a).toLocaleString('en-IN');}
function pct(f){return f==null||isNaN(f)?'—':(f*100).toFixed(1)+'%';}
function px(n){if(n==null||isNaN(n))return '₹—';return '₹'+(Math.abs(n)<100?(+n).toFixed(2):Math.round(n).toLocaleString('en-IN'));}
function clean(t){return (t||'').toUpperCase().replace(/-(EQ|BE|BZ|BL|SM|ST|IQ)$/,'').split('-')[0];}
function verdictClass(v){return v==='🟢'?'strong':v==='🔴'?'weak':v==='⚪'?'':'neutral';}
async function j(url,opt){const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));return {ok:r.ok,status:r.status,d};}

/* ---- PORTFOLIO ---- */
async function loadPortfolio(){
  const r=await j('/portfolio?'+Q);
  if(!r.ok){document.getElementById('err').textContent='Server '+r.status+' — check the token in your link.';return;}
  document.getElementById('err').textContent='';PORT=r.d;renderHero(PORT);renderAccounts();renderMovers();if(document.getElementById('allhold-body').style.display!=='none')renderHolds();
  if(!window._homeExtras){window._homeExtras=1;loadVolumeSpikes();loadHomeNews();}
}
function renderHero(p){
  const dc=p.day_change>=0,up=p.unrealised_pnl>=0,deg=p.book_health.degraded>0;
  document.getElementById('nw').textContent=inr(p.net_worth);
  document.getElementById('day').innerHTML='<span class="'+(dc?'up':'down')+'">'+(dc?'▲':'▼')+' '+inr(Math.abs(p.day_change))+' &nbsp;'+(dc?'+':'−')+pct(Math.abs(p.day_change_pct))+' today</span>';
  document.getElementById('upnl').innerHTML='<span class="'+(up?'up':'down')+'">'+(up?'+':'−')+inr(Math.abs(p.unrealised_pnl))+'</span> <span class="dim" style="font-size:13px">'+pct(Math.abs(p.unrealised_pnl_pct))+'</span>';
  document.getElementById('cash').textContent=inr(p.cash);document.getElementById('inv').textContent=inr(p.invested_value);
  const fp=p.positions_pnl||0;document.getElementById('fopnl').innerHTML='<span class="'+(fp>=0?'up':'down')+'">'+(fp>=0?'+':'')+inr(fp)+'</span>';
  // fixed header: always-visible net worth + today's move + book-health dot
  document.getElementById('hdr-nw').textContent=inr(p.net_worth);
  const hd=document.getElementById('hdr-day');
  hd.className='d '+(dc?'up':'down');hd.textContent=(dc?'▲':'▼')+' '+(dc?'+':'−')+pct(Math.abs(p.day_change_pct));
  const hdot=document.getElementById('hdr-dot');hdot.style.background=deg?'var(--down)':'var(--up)';
  hdot.title='Book '+(deg?'partial':'complete')+' '+p.book_health.fresh+'/'+p.book_health.accounts;
  const errb=document.getElementById('err');
  if(deg){errb.innerHTML='<a href="/login?'+Q+'" style="color:var(--warn);text-decoration:none">⚠ '+p.book_health.degraded+' account(s) not logged in — net worth is partial. Tap to log in →</a>';}
  else{errb.textContent='';}
  if(!acctSelBuilt){
    const sel=document.getElementById('acct-sel');
    (p.accounts||[]).forEach(a=>{if(a.creds_key){ACCT_LABELS[a.creds_key]=a.label||a.creds_key;
      const o=document.createElement('option');o.value=a.creds_key;o.textContent=(a.label||a.creds_key)+((a.holdings&&a.holdings.length)?' ('+a.holdings.length+')':'');sel.appendChild(o);}});
    sel.onchange=renderHolds;acctSelBuilt=true;
  }
}
function holdRows(){const sel=(document.getElementById('acct-sel')||{}).value||'ALL';const map={};
  (PORT.accounts||[]).forEach(a=>{if(sel!=='ALL'&&a.creds_key!==sel)return;(a.holdings||[]).forEach(h=>{
    const s=clean(h.ticker);const key=sel==='ALL'?s:s+'@'+a.creds_key;
    const m=map[key]||(map[key]={sym:s,quantity:0,market_value:0,invested:0,day_change:0,last_price:h.last_price,average_price:h.average_price,token:h.token,exchange:h.exchange,accts:{}});
    m.quantity+=h.quantity||0;m.market_value+=h.market_value||0;m.invested+=(h.average_price||0)*(h.quantity||0);m.day_change+=h.day_change||0;m.last_price=h.last_price||m.last_price;m.accts[a.creds_key]=1;});});
  return Object.values(map).sort((a,b)=>b.market_value-a.market_value);}
function renderHolds(){
  if(!PORT)return;const rows=holdRows();
  const cnt=document.getElementById('hold-count');if(cnt)cnt.textContent='· '+rows.length;
  if(!rows.length){document.getElementById('holds').innerHTML='<div class="load">No holdings for this account.</div>';return;}
  const sel=(document.getElementById('acct-sel')||{}).value||'ALL';
  let h='';rows.forEach(x=>{
    const e=SCORE[x.sym]||{},cls=verdictClass(e.verdict),pnl=x.market_value-x.invested,gp=pnl>=0,pp=x.invested?pnl/x.invested*100:0;
    const fc=e.fundamental_score!=null?'<span class="chip '+(e.fundamental_score>=65?'s':e.fundamental_score>=40?'n':'w')+'">F '+e.fundamental_score+'</span>':'';
    const tc=e.technical_score!=null?'<span class="chip '+(e.technical_score>=60?'s':e.technical_score>=40?'n':'w')+'">T '+e.technical_score+'</span>':'';
    const flag=(e.flags&&e.flags.length)?'<span class="down" style="font-size:11px">● '+e.flags[0].text+'</span>':'';
    const na=Object.keys(x.accts||{});
    const ac=(sel==='ALL'&&na.length)?'<span class="acctchip">'+(na.length>1?na.length+' accts':(ACCT_LABELS[na[0]]||na[0]))+'</span>':'';
    h+='<div class="h '+cls+'" data-sym="'+x.sym+'" data-vol="'+((e.tech||{}).vol_x||0)+'" data-v="'+cls+'"><div class="htop" onclick="tog(this)">'
      +'<span class="sev"></span><div style="min-width:0"><div class="sym">'+x.sym+' '+fc+tc+' '+ac+'</div><div class="sub">'+x.quantity.toLocaleString('en-IN')+' @ '+px(x.average_price)+' &nbsp;'+flag+'</div></div>'
      +'<div class="right"><div class="val mono">'+inr(x.market_value)+'</div><div class="mono '+(gp?'up':'down')+'" style="font-size:12.5px">'+(gp?'+':'')+inr(pnl)+' <span class="faint">'+(gp?'+':'')+pp.toFixed(1)+'%</span></div></div>'
      +'<svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg></div>'
      +'<div class="detail" id="det-'+x.sym+'"></div></div>';
    HOLD[x.sym]=x;
  });
  document.getElementById('holds').innerHTML=h;applyFilter();
}
function tog(el){const h=el.parentElement;h.classList.toggle('open');if(h.classList.contains('open')&&!h.dataset.loaded){h.dataset.loaded=1;loadStockDetail(h.dataset.sym);}}
async function loadStockDetail(sym){
  const box=document.getElementById('det-'+sym);if(!box)return;
  const x=HOLD[sym]||{},e=SCORE[sym]||{},f=e.fields||{};
  box.innerHTML='<div class="load" style="padding:14px">Loading '+sym+'…</div>';
  const cr=await j('/chart/'+encodeURIComponent(sym)+'?'+Q);const d=cr.ok?cr.d:{};
  const cell=(k,v,note,c)=>'<div class="m"><div class="k">'+k+'</div><div class="d'+(c?' '+c:'')+'">'+v+'</div>'+(note?'<div class="note '+(c||'dim')+'">'+note+'</div>':'')+'</div>';
  const rsi=d.rsi14,vol=d.vol_x,dch=d.day_change_pct;
  let m='';
  m+=cell('Price',px(d.last||x.last_price)+' ',(dch!=null?(dch>=0?'+':'')+dch+'% today':''),dch>=0?'up':'down');
  m+=cell('Day range',(d.day_low!=null?px(d.day_low)+'–'+px(d.day_high):'—'),'',' ');
  m+=cell('52-wk',(d.wk52_low!=null?px(d.wk52_low)+'–'+px(d.wk52_high):'—'),(d.from_52w_high_pct!=null?d.from_52w_high_pct+'% from high':''),' ');
  m+=cell('Volume',vol!=null?vol.toFixed(1)+'×':'—',vol!=null?(vol>=2?'surge':'normal'):'',vol>=2?'':(vol>=1?'up':'dim'));
  m+=cell('RSI 14',rsi!=null?Math.round(rsi):'—',rsi!=null?(rsi>70?'overbought':rsi<35?'oversold':'neutral'):'',rsi>70?'warn':rsi<35?'down':'');
  m+=cell('Trend',d.above_200dma===true?'Up':d.above_200dma===false?'Down':'—',(d.dma_signal||'').replace(/_/g,' '),d.above_200dma?'up':d.above_200dma===false?'down':'');
  if(f.pe!=null)m+=cell('P/E',(+f.pe).toFixed(0),f.pe>60?'rich':f.pe<20?'cheap':'fair',f.pe>60?'down':'');
  if(f.de!=null)m+=cell('Debt/Eq',(+f.de).toFixed(2),f.de>1?'high':'low',f.de>1?'down':'up');
  if(f.roe!=null)m+=cell('ROE',Math.round(f.roe)+'%',f.roe>=15?'strong':'ok',f.roe>=15?'up':'');
  if(f.promoter_holding!=null)m+=cell('Promoter',Math.round(f.promoter_holding)+'%','holding',' ');
  if(f.pledge!=null)m+=cell('Pledge',Math.round(f.pledge)+'%',f.pledge>20?'high':f.pledge>5?'watch':'clean',f.pledge>20?'down':f.pledge>5?'warn':'up');
  if(x.sector)m+=cell('Sector',x.sector,'',' ');
  const L=d.levels||{};const lvl=L.pivot?'<div class="note" style="padding:10px 13px 0;font-size:11.5px"><b>Levels:</b> S '+L.s1+' · P '+L.pivot+' · R '+L.r1+'</div>':'';
  const p=d.last||x.last_price||0;
  box.innerHTML='<div class="metrics">'+m+'</div>'+lvl
    +'<div class="snews" id="news-'+sym+'"><div class="load" style="padding:8px 13px">loading news…</div></div>'
    +'<div style="padding:8px 13px 0"><button class="btn ghost" style="width:100%" onclick="openChart(\''+sym+'\')">📈 Chart &amp; levels</button></div>'
    +'<div class="actions"><button class="btn buy" onclick="ticket(\'BUY\',\''+sym+'\','+p+',\''+(x.token||'')+'\',\''+(x.exchange||'NSE')+'\')">Buy</button>'
    +'<button class="btn sell" onclick="ticket(\'SELL\',\''+sym+'\','+p+',\''+(x.token||'')+'\',\''+(x.exchange||'NSE')+'\')">Sell</button>'
    +'<button class="btn hedge" onclick="go(\'hedge\')">Hedge</button></div>';
  const nr=await j('/news/'+encodeURIComponent(sym)+'?'+Q);const nb=document.getElementById('news-'+sym);
  if(nr.ok&&nr.d.news&&nr.d.news.length){nb.innerHTML='<div class="lbl" style="padding:10px 13px 2px">Latest news</div>'+nr.d.news.slice(0,4).map(a=>'<a href="'+a.link+'" target="_blank" style="display:block;padding:8px 13px;border-top:1px solid var(--hair);text-decoration:none;color:var(--tx)"><div style="font-size:13px;font-weight:600;line-height:1.35">'+a.title+'</div><div class="faint" style="font-size:11px;margin-top:2px">'+(a.source||'')+(a.when?' · '+a.when:'')+'</div></a>').join('');}
  else{nb.innerHTML='<div class="dim" style="padding:8px 13px;font-size:12px">No recent news found.</div>';}
}
async function loadScoring(){
  const r=await j('/screener/holdings?technicals=0&'+Q);if(!r.ok)return;const d=r.d;
  (d.holdings||[]).forEach(x=>SCORE[x.symbol]=x);
  const bs=d.book_strength||{};setMeter('mfund','sfund',bs.fundamental);setMeter('mtech','stech',bs.technical);
  const c=d.counts||{};document.getElementById('counts').innerHTML='<div><b class="up">'+(c['🟢']||0)+'</b> <span class="dim">strong</span></div><div><b class="warn">'+(c['🟡']||0)+'</b> <span class="dim">neutral</span></div><div><b class="down">'+(c['🔴']||0)+'</b> <span class="dim">weak</span></div>';
  document.getElementById('strengthsub').textContent=d.screener_loaded?'Screener + live technicals':'free data — upload Screener to sharpen';
  renderHolds();
}
function setMeter(mi,si,v){if(v==null)return;document.getElementById(mi).style.width=Math.max(3,Math.min(100,v))+'%';const s=document.getElementById(si);s.textContent=v;s.className='score mono '+(v>=65?'up':v>=40?'warn':'down');}

/* ---- IDEAS ---- */
async function loadIdeas(){
  const rg=await j('/market/regime?'+Q);
  if(rg.ok){const d=rg.d,col=d.regime==='calm'?'var(--up)':d.regime==='stressed'?'var(--down)':'var(--warn)';
    const i=d.inputs||{};
    document.getElementById('regime-body').innerHTML=
      '<div style="margin-top:12px"><span class="regbadge" style="background:'+col.replace('var(--','rgba(').replace(')',',.14)').replace('up','47,189,133').replace('down','255,88,103').replace('warn','224,165,58')+';color:'+col+'">'+d.emoji+' '+d.regime.toUpperCase()+'</span></div>'
      +'<div class="signals"><div class="sig"><div class="n">India VIX</div><div class="v">'+(i.india_vix??'—')+'</div></div><div class="sig"><div class="n">NIFTY vs 200D</div><div class="v">'+(i.nifty_vs_200dma_pct!=null?(i.nifty_vs_200dma_pct>=0?'+':'')+i.nifty_vs_200dma_pct+'%':'—')+'</div></div><div class="sig"><div class="n">Risk budget</div><div class="v">'+d.risk_budget_pct+'%</div></div></div>'
      +'<div class="note">'+d.tilt+'</div>';
  }
  const sc=await j('/screener/scan?limit=6&min_score=60&technicals=1&'+Q);
  const box=document.getElementById('ideas');
  if(!sc.ok||!sc.d.ideas||!sc.d.ideas.length){box.innerHTML='<div class="load">'+((sc.d&&sc.d.error)||'No ideas pass the bar right now. Upload a Screener export to widen the universe.')+'</div>';document.getElementById('ideas-sub').textContent='';return;}
  document.getElementById('ideas-sub').textContent=sc.d.ranked+' of '+sc.d.universe_size+' scored';
  box.innerHTML=sc.d.ideas.map(i=>{const f=i.fields||{},bits=[];if(f.roe!=null)bits.push('ROE '+Math.round(f.roe)+'%');if(f.de!=null)bits.push('D/E '+(+f.de).toFixed(2));if(f.pe!=null)bits.push('P/E '+Math.round(f.pe));
    const conv=i.conviction!=null?i.conviction:i.fundamental_score;
    const sig=i.signal;
    const patTag=sig?'<span class="tag pat">'+sig.pattern+' · '+sig.hit_rate+'% ('+sig.occurrences+'×)</span>':'<span class="tag pat">Fundamental screen</span>';
    const fl=(i.flags||[]).map(x=>'<span class="cf">'+x.sev+' '+x.text+'</span>').join('');
    const why=sig?'<div class="why"><b>Why:</b> '+sig.pattern+' fired — backtested <b>'+sig.hit_rate+'% hit-rate</b>, avg '+(sig.avg_return_pct>=0?'+':'')+sig.avg_return_pct+'% over '+sig.horizon+' sessions.</div>':'';
    return '<div class="idea"><div class="itop"><div class="conv">'+Math.round(conv)+'</div><div><div class="isym">'+i.symbol+'</div><div class="tags">'+patTag+'</div></div></div>'
      +why
      +'<div class="confl"><span class="cf">'+bits.join('</span><span class="cf">')+'</span>'+fl+'</div>'
      +'<div class="iact"><button class="btn buy" onclick="analyseIdea(\''+i.symbol+'\')">Analyse &amp; trade →</button></div></div>';}).join('');
}
async function loadDailyStrategy(){
  const r=await j('/strategy/daily?'+Q);const card=document.getElementById('strategy-card');
  if(!r.ok){card.innerHTML='<div class="load">Strategy unavailable — needs the market feed (EODHD).</div>';return;}
  const d=r.d;const col=d.regime==='calm'?'var(--up)':d.regime==='stressed'?'var(--down)':'var(--warn)';
  let h='<div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Daily Strategy</span><span class="frag">levels-first</span></div>'
    +'<div style="margin-top:10px;font-size:20px;font-weight:800">'+(d.regime_emoji||'')+' '+(d.market_bias||'')+'</div>'
    +'<div class="note" style="margin-top:4px;color:var(--dim)">'+(d.guidance||'')+' &nbsp;<span class="faint">VIX '+(d.vix??'—')+' · risk budget '+(d.risk_budget_pct||'—')+'%</span></div>';
  (d.indices||[]).forEach(x=>{const L=x.levels,P=x.plan;
    h+='<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--hair)"><div style="display:flex;justify-content:space-between"><span style="font-weight:700">'+x.name+'</span><span class="mono">'+Math.round(x.last).toLocaleString('en-IN')+'</span></div>'
      +'<div class="mono" style="font-size:12.5px;margin-top:6px;display:flex;gap:10px;flex-wrap:wrap">'
      +'<span class="down">S '+L.s2+' · '+L.s1+'</span><span class="faint">P '+L.pivot+'</span><span class="up">R '+L.r1+' · '+L.r2+'</span></div>'
      +'<div class="note" style="margin-top:6px">'+P.rule+' <span class="faint">('+L.cpr_type+')</span></div></div>';});
  h+='<div class="note" style="margin-top:12px;padding-top:10px;border-top:1px solid var(--hair)"><b>Discipline:</b> '+(d.discipline||[]).join(' · ')+'</div>'
    +'<div class="note faint" style="margin-top:6px">'+d.note+'</div>';
  card.innerHTML=h;
}
async function analyseIdea(sym){
  const r=await j('/strategy/signal/'+encodeURIComponent(sym)+'?'+Q);
  if(r.ok&&r.d.action==='BUY'){ticket('BUY',sym,r.d.entry,'','NSE',r.d);}
  else{ticket('BUY',sym,(r.d&&r.d.entry)||0,'','NSE');}
}

/* ---- HEDGE ---- */
async function loadHedge(){
  const ex=await j('/exposure?hedge=0.5&'+Q);
  const gl=await j('/market/global?'+Q);
  const card=document.getElementById('expo-card');
  if(!ex.ok){card.innerHTML='<div class="load">Exposure unavailable.</div>';return;}
  const n=ex.d.net_exposure||{},nw=ex.d.net_worth||0,eq=n.equity_long||0,fno=n.fno_net_notional||0,cash=(PORT&&PORT.cash)||0;
  const tot=eq+Math.abs(fno)+cash||1;
  let g='';
  if(gl.ok){g='<div class="lbl" style="margin-top:16px">Global backdrop</div><div class="glob">'+(gl.d.markets||[]).map(m=>{const c=m.change_pct==null?'':m.change_pct>=0?'up':'down';return '<div class="g"><div class="n">'+m.name+'</div><div class="v '+c+'">'+(m.change_pct==null?'—':(m.change_pct>=0?'+':'')+m.change_pct+'%')+'</div></div>';}).join('')+'</div>';}
  card.innerHTML='<div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Exposure</span><span class="frag">domestic + global</span></div>'
    +'<div class="lbl" style="margin-top:12px">Net market exposure</div><div class="big mono '+(n.net_market_exposure>=0?'up':'down')+'">'+inr(n.net_market_exposure)+' <span class="dim" style="font-size:14px;font-weight:600">'+(n.tilt||'')+'</span></div>'
    +'<div class="barstack"><span style="width:'+(eq/tot*100)+'%;background:var(--up)"></span><span style="width:'+(Math.abs(fno)/tot*100)+'%;background:var(--down)"></span><span style="width:'+(cash/tot*100)+'%;background:var(--elev)"></span></div>'
    +'<div class="rowline"><span class="dim">Equity long <span class="up">●</span></span><span class="mono">'+inr(eq)+'</span></div>'
    +'<div class="rowline"><span class="dim">F&O net <span class="down">●</span></span><span class="mono '+(fno>=0?'':'down')+'">'+inr(fno)+'</span></div>'
    +'<div class="rowline"><span class="dim">Cash / margin</span><span class="mono">'+inr(cash)+'</span></div>'+g;
  document.getElementById('hedge-card').style.display='block';
  document.getElementById('hedge-warn').innerHTML='Net long '+inr(n.net_market_exposure)+'. A 10% market fall ≈ <b class="down">'+inr(n.net_market_exposure*0.1)+'</b> unhedged.';
  renderHedge(ex.d.hedge_suggestions,0.5);
}
function renderHedge(sugs,frac){
  HEDGE=null;const key=(frac===0.25?'25pct':frac===1?'100pct':'50pct');const s=(sugs||{})[key]||(sugs||{})['50pct'];
  if(!s){document.getElementById('hedge-body').innerHTML='<div class="note">NIFTY spot unavailable — hedge sizing needs it.</div>';return;}
  HEDGE={lots:s.lots_to_short,spot:s.nifty_spot,notional:s.lot_value*s.lots_to_short};
  document.getElementById('hedge-body').innerHTML=
    '<div class="rowline"><span class="dim">Hedge '+Math.round(frac*100)+'% of equity</span><span class="mono">'+inr(s.hedged_value)+'</span></div>'
    +'<div class="rowline"><span class="dim">NIFTY spot / lot ('+s.lot_size+')</span><span class="mono">'+Math.round(s.nifty_spot).toLocaleString('en-IN')+' · '+inr(s.lot_value)+'</span></div>'
    +'<div class="rowline"><span class="dim">Sell</span><span class="mono down" style="font-weight:700">'+s.lots_to_short+' lots ('+(s.lots_to_short*s.lot_size).toLocaleString('en-IN')+')</span></div>'
    +'<div class="rowline"><span class="dim">Covers</span><span class="mono">'+s.hedged_pct_of_book+'% of book</span></div>';
}
document.querySelectorAll('.hb').forEach(b=>b.onclick=async function(){document.querySelectorAll('.hb').forEach(x=>x.classList.remove('on'));this.classList.add('on');const ex=await j('/exposure?hedge='+this.dataset.f+'&'+Q);if(ex.ok)renderHedge(ex.d.hedge_suggestions,parseFloat(this.dataset.f));});
document.getElementById('hedge-go').onclick=function(){if(!HEDGE){return;}ticketHedge();};

/* ---- TRADES ---- */
async function loadTrades(){
  const st=await j('/execution/status?'+Q);
  if(st.ok){const s=st.d;document.getElementById('exec-status').innerHTML='<div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Engine</span><span class="chip '+(s.can_trade?'s':'w')+'">'+(s.can_trade?'ARMED':'TRADING OFF')+'</span></div>'
    +'<div class="rowline"><span class="dim">Orders today</span><span class="mono">'+s.orders_today+' / '+s.caps.max_orders_per_day+'</span></div><div class="rowline"><span class="dim">Kill switch</span><span class="mono '+(s.kill_switch?'down':'')+'">'+(s.kill_switch?'ENGAGED':'off')+'</span></div>';}
  const lg=await j('/execution/log?limit=40&'+Q);const box=document.getElementById('trades');
  if(!lg.ok||!lg.d.events||!lg.d.events.length){box.innerHTML='<div class="load">No trades logged yet. Proposals and placements appear here.</div>';return;}
  box.innerHTML=lg.d.events.map(e=>{const o=e.order||{},side=(o.side||'').toLowerCase(),sc=side==='buy'?'b':side==='sell'?'s':'h';
    const t=(e.ts||'').replace('T',' ').slice(5,16);
    return '<div class="tr"><span class="side '+sc+'">'+(o.side||e.event)+'</span><div><div style="font-weight:600">'+(o.symbol||e.event)+' <span class="dim" style="font-size:12px">'+(o.quantity?o.quantity+' @ '+px(o.price):'')+'</span></div><div class="dim" style="font-size:11.5px">'+(o.stop_loss?'SL '+o.stop_loss+' · R:R '+(o.risk_reward||'—'):t)+'</div></div><span class="stt '+e.event+'">'+e.event.replace('_',' ')+'</span></div>';}).join('');
}

/* ---- CHART ---- */
const cscrim=document.getElementById('cscrim'),csheet=document.getElementById('csheet');
async function openChart(sym){
  document.getElementById('c-sym').textContent=sym;document.getElementById('c-last').textContent='loading…';
  document.getElementById('c-lvls').textContent='';cscrim.classList.add('on');csheet.classList.add('on');
  const ct=document.getElementById('cchart').getContext('2d');ct.clearRect(0,0,900,360);
  const r=await j('/chart/'+encodeURIComponent(sym)+'?'+Q);
  if(!r.ok){document.getElementById('c-last').textContent=(r.d.detail||'chart unavailable');return;}
  drawChart(r.d);
}
function drawChart(d){
  document.getElementById('c-last').textContent=px(d.last)+(d.source?' · '+d.source:'');
  const c=document.getElementById('cchart'),x=c.getContext('2d'),W=c.width,H=c.height,pad=40;
  x.clearRect(0,0,W,H);
  const series=d.closes||[];if(!series.length)return;
  const L=d.levels||{};
  const all=series.concat((d.sma50||[]).filter(v=>v!=null),(d.sma200||[]).filter(v=>v!=null));
  const lvlvals=L.pivot?[L.s2,L.s1,L.pivot,L.r1,L.r2]:[];
  const ymin=Math.min(...all,...lvlvals),ymax=Math.max(...all,...lvlvals),yr=(ymax-ymin)||1;
  const X=i=>pad+i/((series.length-1)||1)*(W-2*pad),Y=v=>H-pad-(v-ymin)/yr*(H-2*pad);
  // level lines
  const drawLvl=(v,col,lbl)=>{if(v==null)return;const yy=Y(v);x.strokeStyle=col;x.setLineDash([5,4]);x.globalAlpha=.6;x.beginPath();x.moveTo(pad,yy);x.lineTo(W-pad,yy);x.stroke();x.globalAlpha=1;x.setLineDash([]);x.fillStyle=col;x.font='10px monospace';x.fillText(lbl+' '+Math.round(v),W-pad-54,yy-3);};
  drawLvl(L.r2,'#2fbd85','R2');drawLvl(L.r1,'#2fbd85','R1');drawLvl(L.pivot,'#8493ab','P');drawLvl(L.s1,'#ff5867','S1');drawLvl(L.s2,'#ff5867','S2');
  const line=(arr,col,w)=>{x.beginPath();let started=false;arr.forEach((v,i)=>{if(v==null){started=false;return;}const xx=X(i),yy=Y(v);if(started)x.lineTo(xx,yy);else x.moveTo(xx,yy);started=true;});x.strokeStyle=col;x.lineWidth=w;x.lineJoin='round';x.stroke();};
  line(d.sma200||[],'#a78bfa',1.5);line(d.sma50||[],'#e0a53a',1.5);line(series,'#4c8dff',2.2);
  const lx=X(series.length-1),ly=Y(series[series.length-1]);x.fillStyle='#4c8dff';x.beginPath();x.arc(lx,ly,3.5,0,7);x.fill();
  if(L.pivot){document.getElementById('c-lvls').innerHTML='<b>Levels:</b> S '+L.s2+' / '+L.s1+' · P '+L.pivot+' · R '+L.r1+' / '+L.r2+' &nbsp;<span class="faint">('+(L.cpr_type||'')+')</span>';}
}
cscrim.addEventListener('click',()=>{cscrim.classList.remove('on');csheet.classList.remove('on');});

/* ---- OPTIONS ---- */
let optStrategiesLoaded=false;
async function loadOptions(){
  if(!optStrategiesLoaded){
    const s=await j('/options/strategies?'+Q);
    if(s.ok){document.getElementById('opt-name').innerHTML=(s.d.strategies||[]).map(x=>'<option value="'+x.key+'">'+x.key.replace(/_/g,' ')+'</option>').join('');optStrategiesLoaded=true;
      document.getElementById('opt-name').onchange=runOptions;document.getElementById('opt-under').onchange=runOptions;}
  }
  runOptions();
}
async function runOptions(){
  const name=document.getElementById('opt-name').value||'bull_call_spread';
  const und=document.getElementById('opt-under').value||'NIFTY';
  document.getElementById('opt-metrics').innerHTML='<div class="load">Pricing…</div>';
  const r=await j('/options/strategy?name='+name+'&underlying='+und+'&'+Q);
  if(!r.ok){document.getElementById('opt-metrics').innerHTML='<div class="load">'+(r.d.detail||'Needs the market feed (EODHD) for spot/IV.')+'</div>';drawPayoff(null);return;}
  const d=r.d;drawPayoff(d);
  const legs=(d.legs||[]).map(l=>l.side+' '+l.type+' '+l.strike+' @'+l.premium).join(' · ');
  const g=d.greeks||{};
  document.getElementById('opt-metrics').innerHTML=
    '<div class="rr" style="margin-top:12px"><div><div class="k">Max profit</div><div class="v up">'+inr(d.max_profit)+(d.max_profit_capped&&d.max_profit>0?'':'')+'</div></div>'
    +'<div><div class="k">Max loss</div><div class="v down">'+inr(d.max_loss)+'</div></div>'
    +'<div><div class="k">R:R</div><div class="v">'+(d.reward_risk||'—')+'</div></div></div>'
    +'<div class="rowline"><span class="dim">Breakeven'+(d.breakevens.length>1?'s':'')+'</span><span class="mono">'+(d.breakevens.join(' / ')||'—')+'</span></div>'
    +'<div class="rowline"><span class="dim">Net premium</span><span class="mono '+(d.net_premium<0?'down':'up')+'">'+(d.net_premium<0?'debit ':'credit ')+inr(Math.abs(d.net_premium))+'</span></div>'
    +'<div class="rowline"><span class="dim">Pricing</span><span class="mono '+(d.priced==='live'?'up':d.priced==='partial'?'warn':'dim')+'">'+(d.priced||'theoretical').toUpperCase()+(d.expiry?' · exp '+d.expiry:'')+'</span></div>'
    +'<div class="rowline"><span class="dim">Spot / IV / DTE</span><span class="mono">'+Math.round(d.spot).toLocaleString('en-IN')+' · '+d.iv_pct+'% · '+d.dte+'d</span></div>'
    +'<div class="rowline"><span class="dim">Net Greeks</span><span class="mono" style="font-size:12px">Δ'+g.delta+' Θ'+g.theta+' V'+g.vega+'</span></div>'
    +'<div class="note" style="margin-top:8px">'+legs+'</div>';
  document.getElementById('opt-note').textContent=d.note||'';
}
function drawPayoff(d){
  const c=document.getElementById('opt-canvas'),x=c.getContext('2d'),W=c.width,H=c.height;
  x.clearRect(0,0,W,H);
  if(!d||!d.curve){return;}
  const cur=d.curve,xs=cur.map(p=>p.underlying),ys=cur.map(p=>p.pnl);
  const xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
  const pad=34,yr=(ymax-ymin)||1;
  const X=u=>pad+(u-xmin)/((xmax-xmin)||1)*(W-2*pad);
  const Y=p=>H-pad-(p-ymin)/yr*(H-2*pad);
  // zero line
  const y0=Y(0);x.strokeStyle='#3a4560';x.lineWidth=1;x.beginPath();x.moveTo(pad,y0);x.lineTo(W-pad,y0);x.stroke();
  // profit/loss fill
  for(let seg=0;seg<2;seg++){x.beginPath();cur.forEach((p,i)=>{const xx=X(p.underlying),yy=Y(p.pnl);i?x.lineTo(xx,yy):x.moveTo(xx,yy);});
    x.lineTo(X(xs[xs.length-1]),y0);x.lineTo(X(xs[0]),y0);x.closePath();
    x.save();x.beginPath();if(seg===0){x.rect(0,0,W,y0);}else{x.rect(0,y0,W,H-y0);}x.clip();
    x.fillStyle=seg===0?'rgba(47,189,133,.18)':'rgba(255,88,103,.18)';x.fill();x.restore();}
  // payoff line
  x.beginPath();cur.forEach((p,i)=>{const xx=X(p.underlying),yy=Y(p.pnl);i?x.lineTo(xx,yy):x.moveTo(xx,yy);});
  x.strokeStyle='#4c8dff';x.lineWidth=2.4;x.lineJoin='round';x.stroke();
  // spot marker
  const sx=X(d.spot);x.strokeStyle='#8493ab';x.setLineDash([4,4]);x.beginPath();x.moveTo(sx,pad);x.lineTo(sx,H-pad);x.stroke();x.setLineDash([]);
  x.fillStyle='#8493ab';x.font='11px monospace';x.fillText('spot '+Math.round(d.spot),sx-30,pad-4>10?pad-4:12);
  // breakeven markers
  (d.breakevens||[]).forEach(be=>{const bx=X(be);x.fillStyle='#e0a53a';x.beginPath();x.arc(bx,y0,3.5,0,7);x.fill();});
}

/* ---- MTF ---- */
async function loadMtf(){
  const r=await j('/mtf?'+Q);const card=document.getElementById('mtf-card');
  if(!r.ok){card.innerHTML='<div class="load">MTF view unavailable.</div>';return;}
  const d=r.d,adj=d.mtf_loan>0;
  const sColor=d.status==='loan_detected'?'var(--up)':d.status==='none_found'?'var(--dim)':'var(--warn)';
  let h='<div class="lbl">True net worth <span class="faint">(after MTF loan)</span></div>'
    +'<div class="nw mono">'+inr(d.true_net_worth)+'</div>';
  if(adj)h+='<div class="dim" style="font-size:13px;margin-top:2px">reported '+inr(d.reported_net_worth)+' − loan '+inr(d.mtf_loan)+'</div>';
  h+='<div class="grid2"><div class="stat"><div class="lbl">Gross holdings</div><div class="v mono">'+inr(d.gross_holdings)+'</div></div>'
    +'<div class="stat"><div class="lbl">MTF loan</div><div class="v mono '+(adj?'down':'')+'">'+(adj?'−'+inr(d.mtf_loan):'—')+'</div></div>'
    +'<div class="stat"><div class="lbl">Interest / day</div><div class="v mono '+(adj?'down':'')+'">'+(adj?inr(d.daily_interest):'—')+'</div></div>'
    +'<div class="stat"><div class="lbl">Leverage</div><div class="v mono">'+(d.leverage||1)+'×</div></div></div>';
  h+='<div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding-top:14px;border-top:1px solid var(--hair)"><span class="h2">MTF positions</span><span class="chip" style="background:rgba(132,147,171,.14);color:'+sColor+'">'+d.status.replace(/_/g,' ')+'</span></div>';
  if(d.mtf_positions&&d.mtf_positions.length){d.mtf_positions.forEach(p=>{h+='<div class="tr"><div><div style="font-weight:600">'+p.ticker+'</div>'+(p.product?'<div class="dim" style="font-size:11.5px">'+p.product+'</div>':'')+'</div><div class="right"><div class="mono">'+inr(p.value)+'</div>'+(p.loan?'<div class="mono down" style="font-size:12px">loan '+inr(p.loan)+'</div>':'')+'</div></div>';});}
  else{h+='<div class="note" style="margin-top:10px">'+d.note+'</div>';}
  if(d.status!=='loan_detected'&&d.fields_seen&&Object.keys(d.fields_seen).length){h+='<div class="note" style="margin-top:8px">Fields seen: '+Object.keys(d.fields_seen).join(', ')+'</div>';}
  h+='<div class="note" style="margin-top:10px">MTF rate assumed '+d.annual_rate_pct+'% p.a. (set CFO_MTF_RATE in .env to change).</div>';
  card.innerHTML=h;
}

/* ---- TICKET ---- */
const scrim=document.getElementById('scrim'),sheet=document.getElementById('sheet');
function ticket(side,sym,ltp,tok,exch,sig){
  const s=document.getElementById('tk-side');s.textContent=side;
  s.style.background=side==='BUY'?'rgba(47,189,133,.16)':side==='SELL'?'rgba(255,88,103,.16)':'rgba(76,141,255,.16)';
  s.style.color=side==='BUY'?'var(--up)':side==='SELL'?'var(--down)':'var(--acc)';
  document.getElementById('tk-sym').textContent=sym;document.getElementById('tk-ltp').textContent=px(ltp);
  let stop,tgt,qty;
  if(sig&&sig.stop_loss){stop=sig.stop_loss;tgt=sig.target;qty=sig.suggested_qty||Math.max(1,Math.floor(5000/((ltp-stop)||1)));}
  else{stop=+(ltp*0.95).toFixed(2);tgt=+(ltp*1.10).toFixed(2);qty=Math.max(1,Math.floor(5000/((ltp-stop)||1)));}
  const risk=qty*(ltp-stop),rew=qty*(tgt-ltp);
  document.getElementById('tk-qty').textContent=qty.toLocaleString('en-IN')+' sh';
  document.getElementById('tk-entry').innerHTML=px(ltp)+' &nbsp;<span class="faint">LIMIT</span>';
  document.getElementById('tk-stop').innerHTML=px(stop);document.getElementById('tk-tgt').innerHTML=px(tgt);
  document.getElementById('tk-risk').textContent=inr(risk);document.getElementById('tk-rew').textContent=inr(rew);document.getElementById('tk-rr').textContent=risk?(rew/risk).toFixed(1):'—';
  CURR={creds_key:(PORT&&PORT.accounts&&PORT.accounts[0]&&PORT.accounts[0].creds_key)||'HDFC1',exchange:exch||'NSE',symbol:sym,token:tok||'',side:side==='HEDGE'?'SELL':side,quantity:qty,product:'CNC',order_type:'LIMIT',price:ltp,trigger_price:0,underlying:sym,stop_loss:stop,target:tgt};
  openSheet();
}
function ticketHedge(){
  const s=document.getElementById('tk-side');s.textContent='HEDGE';s.style.background='rgba(76,141,255,.16)';s.style.color='var(--acc)';
  document.getElementById('tk-sym').textContent='NIFTY FUT';document.getElementById('tk-ltp').textContent=Math.round(HEDGE.spot).toLocaleString('en-IN');
  document.getElementById('tk-qty').textContent=HEDGE.lots+' lots';
  document.getElementById('tk-entry').innerHTML='MKT';document.getElementById('tk-stop').textContent='—';document.getElementById('tk-tgt').textContent='—';
  document.getElementById('tk-risk').textContent=inr(HEDGE.notional);document.getElementById('tk-rew').textContent='hedge';document.getElementById('tk-rr').textContent='—';
  CURR={creds_key:(PORT&&PORT.accounts&&PORT.accounts[0]&&PORT.accounts[0].creds_key)||'HDFC1',exchange:'NFO',symbol:'NIFTY FUT',token:'',side:'SELL',quantity:HEDGE.lots*75,product:'NRML',order_type:'MARKET',price:HEDGE.spot,trigger_price:0,underlying:'NIFTY',stop_loss:0,target:0};
  openSheet();
}
async function openSheet(){
  document.getElementById('tk-confirm').disabled=true;document.getElementById('tk-confirm').textContent='Checking guardrails…';
  document.getElementById('tk-guardtxt').textContent='Validating against guardrails…';scrim.classList.add('on');sheet.classList.add('on');
  const r=await j('/execution/propose?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(CURR)});
  const g=document.getElementById('tk-guardtxt'),btn=document.getElementById('tk-confirm');
  if(r.ok){g.innerHTML='<b class="up">Passes all guardrails.</b> '+(r.d.review||'')+' ';btn.disabled=false;btn.textContent='Confirm '+CURR.side+' →';btn.dataset.pid=r.d.proposal_id;btn.dataset.code=r.d.confirm_code;}
  else{g.innerHTML='<b>Blocked:</b> '+(r.d.detail||('error '+r.status))+'<br><span class="dim">Nothing sent — the guardrail doing its job. (Angel can go live once armed; HDFC needs its order doc.)</span>';btn.disabled=true;btn.textContent='Blocked by guardrail';}
}
document.getElementById('tk-confirm').addEventListener('click',async function(){
  if(this.disabled||!this.dataset.pid)return;this.textContent='Placing…';
  const r=await j('/execution/confirm?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:this.dataset.pid,confirm_code:this.dataset.code})});
  if(r.ok){this.textContent='✅ Order placed';document.getElementById('tk-guardtxt').innerHTML='<b class="up">Sent.</b>';loaded.trades=0;}
  else{this.textContent=r.status===501?'Send not live yet':'Rejected';document.getElementById('tk-guardtxt').innerHTML='<b>'+(r.status===501?'Order-send pending broker docs.':'Rejected.')+'</b> '+(r.d.detail||'');}
});
scrim.addEventListener('click',()=>{scrim.classList.remove('on');sheet.classList.remove('on');});

/* ---- accounts + movers (homepage summary) ---- */
function allHoldings(){const map={};(PORT.accounts||[]).forEach(a=>{const lbl=a.label||a.creds_key;(a.holdings||[]).forEach(h=>{const s=clean(h.ticker);const m=map[s]||(map[s]={sym:s,quantity:0,market_value:0,invested:0,day_change:0,byAcct:{}});m.quantity+=h.quantity||0;m.market_value+=h.market_value||0;m.invested+=(h.average_price||0)*(h.quantity||0);m.day_change+=h.day_change||0;m.byAcct[lbl]=(m.byAcct[lbl]||0)+(h.market_value||0);});});
  return Object.values(map).map(m=>{const ks=Object.keys(m.byAcct);m.holder=ks.sort((a,b)=>m.byAcct[b]-m.byAcct[a])[0]||'';m.holders=ks.length;return m;});}
const ACCT_COLORS=['#6aa6ff','#33d69f','#e8c069','#c98bff','#ff9a62','#5fd8c4'];
function acctStats(a){
  const val=(a.holdings||[]).reduce((s,x)=>s+(x.market_value||0),0);
  const cash=(a.funds||{}).ledger_balance||0;
  const dayC=(a.holdings||[]).reduce((s,x)=>s+(x.day_change||0),0);
  let loan=0,mtf=false;(a.holdings||[]).forEach(h=>{const m=h.raw_mtf||{};
    const ind=((m.mtf_indicator||m.mtfIndicator||m.product||'')+'').toString().toUpperCase();
    if(ind==='Y'||ind.indexOf('MTF')>=0){mtf=true;loan+=(h.market_value||0)*0.75;}});
  return {val,cash,dayC,loan,mtf,n:(a.holdings||[]).length,trueNet:val+cash-loan};
}
function renderAccounts(){
  const accs=(PORT.accounts||[]).map(a=>({a,s:acctStats(a),ok:a.ok!==false&&a.status!=='degraded'}));
  const nw=PORT.net_worth||accs.reduce((s,x)=>s+x.s.val,0)||1;
  const mx=Math.max(1,...accs.map(x=>x.s.val));
  let h='';accs.forEach((x,i)=>{const a=x.a,s=x.s,col=ACCT_COLORS[i%ACCT_COLORS.length],lbl=a.label||a.creds_key;
    const prev=s.val-s.dayC,dpct=prev?s.dayC/prev*100:0,dg=s.dayC>=0;
    const strip='<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;font-size:11.5px" class="faint">'
      +'<span>Cash <span class="mono" style="color:var(--dim)">'+inr(s.cash)+'</span></span>'
      +'<span>Day <span class="mono '+(dg?'up':'down')+'">'+(dg?'▲':'▼')+inr(Math.abs(s.dayC))+' '+(dg?'+':'−')+Math.abs(dpct).toFixed(1)+'%</span></span>'
      +(s.mtf?'<span>MTF loan <span class="mono warn">'+inr(s.loan)+'</span></span><span>True net <span class="mono" style="color:var(--dim)">'+inr(s.trueNet)+'</span></span>':'')
      +'</div>';
    h+='<div class="acct" style="align-items:flex-start"><div class="av" style="background:'+(x.ok?col:'var(--down)')+';margin-top:2px">'+lbl.trim()[0].toUpperCase()+'</div>'
      +'<div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between;align-items:baseline">'
      +'<div class="an">'+lbl+' <span class="faint" style="font-size:11px;font-weight:600">'+a.creds_key+(x.ok?'':' · not logged in')+'</span></div>'
      +'<div style="text-align:right"><span class="mono" style="font-weight:700">'+inr(s.val)+'</span> <span class="faint" style="font-size:11px">'+(s.val/nw*100).toFixed(0)+'% · '+s.n+'</span></div></div>'
      +'<div class="abar"><i style="width:'+(s.val/mx*100).toFixed(0)+'%;background:linear-gradient(90deg,'+col+','+col+'99)"></i></div>'
      +strip+'</div></div>';});
  document.getElementById('acct-list').innerHTML=h||'<div class="dim" style="font-size:13px">No accounts loaded.</div>';
}
function renderMovers(){
  let all=allHoldings();if(!all.length){document.getElementById('movers').innerHTML='<div class="dim" style="font-size:13px;padding:6px 0">No holdings yet.</div>';return;}
  // Ignore stale/tiny lots (< ₹5k) so a single old share can't dominate the movers list.
  all=all.filter(x=>Math.abs(x.market_value)>=5000);
  const anyDay=all.some(x=>Math.abs(x.day_change)>0.5);
  // Daily % is measured vs *yesterday's close value* (market_value − today's rupee move),
  // NOT vs cost basis — dividing by cost inflates a multibagger's move to hundreds of %.
  all.forEach(x=>{x.pnl=x.market_value-x.invested;x.pnlpct=x.invested?x.pnl/x.invested*100:0;const prev=x.market_value-x.day_change;x.daypct=prev?x.day_change/prev*100:0;});
  const key=anyDay?'day_change':'pnl';const pctk=anyDay?'daypct':'pnlpct';const val=key;
  const s=[...all].sort((a,b)=>b[key]-a[key]);
  const gain=s.filter(x=>x[key]>0).slice(0,3),lose=s.filter(x=>x[key]<0).slice(-3).reverse();
  const row=(x,up)=>'<div class="mv" onclick="openChart(\''+x.sym+'\')" style="cursor:pointer">'
    +'<div class="mvtag '+(up?'g':'l')+'">'+(up?'▲':'▼')+'</div>'
    +'<div style="min-width:0"><div class="mvn">'+x.sym+'</div><div class="faint" style="font-size:10.5px">'+(x.holder||'')+(x.holders>1?' +'+(x.holders-1):'')+'</div></div>'
    +'<div class="mvr"><div class="'+(up?'up':'down')+'" style="font-weight:700">'+(x[val]>=0?'+':'')+inr(x[val])+'</div>'
    +'<div class="faint" style="font-size:11px">'+(x[pctk]>=0?'+':'')+x[pctk].toFixed(1)+'%</div></div></div>';
  let h='';
  if(gain.length){h+='<div class="mvhead">Gainers</div>';gain.forEach(x=>h+=row(x,true));}
  if(lose.length){h+='<div class="mvhead"'+(gain.length?' style="margin-top:10px"':'')+'>Losers</div>';lose.forEach(x=>h+=row(x,false));}
  document.getElementById('movers').innerHTML=h||'<div class="dim" style="font-size:13px;padding:6px 0">Flat today.</div>';
}
function toggleHoldings(){const b=document.getElementById('allhold-body'),c=document.getElementById('hold-chev'),open=b.style.display!=='none';b.style.display=open?'none':'block';c.style.transform=open?'':'rotate(180deg)';if(!open)renderHolds();}
function toggleMore(){const b=document.getElementById('more-body'),c=document.getElementById('more-chev'),open=b.style.display!=='none';b.style.display=open?'none':'block';c.style.transform=open?'':'rotate(180deg)';}
async function loadVolumeSpikes(){
  const r=await j('/holdings/volume?'+Q);const box=document.getElementById('volspikes');if(!box)return;
  if(!r.ok||!r.d.volume_spikes||!r.d.volume_spikes.length){box.innerHTML='<div class="dim" style="font-size:12px;padding:4px 0">No unusual volume, or feed loading.</div>';return;}
  const top=r.d.volume_spikes.slice(0,5),mx=Math.max(...top.map(x=>x.vol_x),2);
  box.innerHTML=top.map(x=>{const col=x.vol_x>=2?'var(--purp,#c98bff)':x.vol_x>=1?'var(--up)':'var(--dim)';
    return '<div style="margin:7px 0"><div class="rowline" style="margin:0"><span>'+x.symbol+'</span><span class="mono" style="font-weight:700;color:'+col+'">'+x.vol_x.toFixed(1)+'×</span></div><div class="volbar" style="height:5px;border-radius:3px;background:var(--elev);margin-top:4px;overflow:hidden"><i style="display:block;height:100%;width:'+Math.min(100,x.vol_x/mx*100)+'%;background:'+col+'"></i></div></div>';}).join('');
}
async function loadHomeNews(){
  const box=document.getElementById('homenews');if(!box||!PORT)return;
  const rows=allHoldings().sort((a,b)=>b.market_value-a.market_value).slice(0,3);
  let items=[];
  for(const x of rows){const nr=await j('/news/'+encodeURIComponent(x.sym)+'?'+Q);if(nr.ok&&nr.d.news&&nr.d.news.length){items.push({sym:x.sym,...nr.d.news[0]});}}
  if(!items.length){box.innerHTML='<div class="dim" style="font-size:12px;padding:4px 0">No recent news found.</div>';return;}
  box.innerHTML=items.map(a=>'<a class="newsitem" href="'+a.link+'" target="_blank"><div style="font-size:13.5px;font-weight:600;line-height:1.35">'+a.title+'</div><div class="faint" style="font-size:11px;margin-top:3px">'+a.sym+' · '+(a.source||'')+(a.when?' · '+a.when:'')+'</div></a>').join('');
}

/* ---- Screener upload ---- */
async function loadScreener(){
  try{const r=await j('/fundamentals/screener/status?'+Q);if(!r.ok)return;const s=r.d;
    const st=document.getElementById('scr-state'),d=document.getElementById('scr-detail');
    if(s.loaded){st.textContent='● loaded';st.className='up';d.innerHTML=s.companies+' companies · <span class="dim">'+s.active_file+'</span>';}
    else{st.textContent='● none';st.className='warn';d.textContent='Upload your Screener export to power fundamentals & ideas.';}
  }catch(e){}
}
document.getElementById('scr-btn').onclick=async function(){
  const f=document.getElementById('scr-file').files[0],msg=document.getElementById('scr-msg');
  if(!f){msg.textContent='Pick a file first.';return;}
  msg.className='dim';msg.textContent='Uploading '+f.name+'…';
  const fd=new FormData();fd.append('file',f);
  try{const r=await fetch('/fundamentals/screener/upload?'+Q,{method:'POST',body:fd});const jr=await r.json();
    if(!r.ok){msg.className='down';msg.textContent=(jr&&jr.detail)||'Upload failed';return;}
    msg.className='up';msg.textContent='✅ Loaded '+(jr.status&&jr.status.companies||0)+' companies. Ideas tab is ready.';
    loadScreener();loaded.ideas=0;
  }catch(e){msg.className='down';msg.textContent='Upload failed — try again.';}
};

/* ---- OI build-up (ideas) ---- */
async function loadOI(){
  const box=document.getElementById('oi-body');if(!box)return;
  const r=await j('/ideas/oi?'+Q);
  if(!r.ok||!r.d.signals||!r.d.signals.length){box.innerHTML='<div class="dim" style="font-size:12px;padding:4px 0">No F&amp;O futures for your holdings, or the chain is loading.</div>';return;}
  const col=b=>b==='bullish'?'var(--up)':b==='bearish'?'var(--down)':'var(--dim)';
  const arrow=b=>b==='bullish'?'▲':b==='bearish'?'▼':'•';
  box.innerHTML=r.d.signals.slice(0,8).map(x=>{const c=col(x.bias);
    const chg=x.oi_change_pct==null?'<span class="faint">baseline</span>':'<span style="color:'+c+'">'+(x.oi_change_pct>=0?'+':'')+x.oi_change_pct+'% OI</span>';
    return '<div class="rowline" style="margin-top:9px"><span><span style="color:'+c+'">'+arrow(x.bias)+'</span> '+x.sym+' <span class="faint" style="font-size:11px">'+x.signal+'</span></span>'
      +'<span class="mono" style="font-size:12px">'+chg+' <span class="faint">'+(x.price_change_pct>=0?'+':'')+x.price_change_pct+'%</span></span></div>';}).join('')
    +'<div class="note" style="margin-top:10px;font-size:11px">'+(r.d.note||'')+'</div>';
}

/* ---- income (premium engine) ---- */
let INCOME=null,incSeg='cc';
async function loadIncome(){
  const box=document.getElementById('inc-list');
  const r=await j('/income/ideas?'+Q);
  if(!r.ok){box.innerHTML='<div class="load down">Could not load income ideas ('+r.status+').</div>';return;}
  INCOME=r.d;const s=r.d.summary||{};
  document.getElementById('inc-total').textContent='+'+inr(s.total_premium||0);
  const exp=(r.d.covered_calls&&r.d.covered_calls[0]&&r.d.covered_calls[0].expiry)||(r.d.cash_secured_puts&&r.d.cash_secured_puts[0]&&r.d.cash_secured_puts[0].expiry)||'';
  document.getElementById('inc-sub').textContent='from '+(s.covered_call_count||0)+' covered calls + '+(s.csp_count||0)+' cash puts'+(exp?' · expiry '+exp:'');
  document.getElementById('inc-cc').textContent='+'+inr(s.covered_call_income||0);
  document.getElementById('inc-csp').textContent='+'+inr(s.csp_income||0);
  renderIncome();
}
function incTab(s){incSeg=s;document.getElementById('inc-tab-cc').classList.toggle('on',s==='cc');document.getElementById('inc-tab-csp').classList.toggle('on',s==='csp');renderIncome();}
function renderIncome(){
  if(!INCOME)return;const box=document.getElementById('inc-list');
  const list=incSeg==='cc'?(INCOME.covered_calls||[]):(INCOME.cash_secured_puts||[]);
  if(!list.length){box.innerHTML='<div class="dim" style="font-size:13px;padding:12px 2px">No '+(incSeg==='cc'?'covered-call':'cash-secured-put')+' proposals right now — either no F&O-eligible '+(incSeg==='cc'?'holding of a full lot':'name within your cash')+', or the chain is still loading. Pull to refresh.</div>';return;}
  box.innerHTML=list.map((x,i)=>incRow(x,i)).join('');
}
function incRow(x,i){
  const cc=x.strategy==='covered_call';
  const src=x.premium_source==='live'?'<span class="tag live">live</span>':'<span class="tag theo">theoretical</span>';
  const holder=x.holder?'<span style="margin-left:auto;font-size:11px;color:var(--faint);font-weight:600">'+x.holder+'</span>':'';
  const gold='style="font-family:var(--mono);font-size:13px;font-weight:750;margin-top:2px;color:#e8c069"';
  const g=(k,v,st)=>'<div class="pg"><div class="k">'+k+'</div><div class="v" '+(st||'')+'>'+v+'</div></div>';
  const oi=x.oi!=null?(x.oi/1000).toFixed(1)+'k':'—';
  const grid=cc?
    g('Yield',x.yield_pct+'%')+g('Annualised',x.annualised_pct+'%',gold)+g('Cushion','+'+x.cushion_pct+'%')+g('Assign','~'+x.assignment_prob_pct+'%')+g('OI',oi)+g('DTE',x.dte+'d')
    :g('Yield/cash',x.yield_on_cash_pct+'%')+g('Annualised',x.annualised_pct+'%',gold)+g('Discount','<span class="up">'+x.discount_pct+'%</span>')+g('Capital',inr(x.capital_reserved))+g('OI',oi)+g('DTE',x.dte+'d');
  return '<div class="prop"><div class="ptop"><span class="psym">'+x.symbol+'</span><span class="tag '+(cc?'cc':'csp')+'">'+(cc?'Covered call':'Cash put')+'</span>'+src+holder+'</div>'
    +'<div class="pinc '+(cc?'up':'')+' mono"'+(cc?'':' style="color:var(--purp)"')+'>+'+inr(x.income)+' <span class="dim" style="font-size:13px;font-weight:600">premium</span></div>'
    +'<div class="dim" style="font-size:12px;margin-top:2px">Sell '+x.contracts+' lot'+(x.contracts>1?'s':'')+' of the '+x.strike+' '+(cc?'CE':'PE')+' &middot; '+x.expiry+'</div>'
    +'<div class="pgrid">'+grid+'</div>'
    +'<div class="note" style="font-size:11.5px">'+x.note+'</div>'
    +'<div style="margin-top:11px"><button style="width:100%;background:var(--up);color:#04160e;border:0;border-radius:10px;padding:11px 0;font-weight:700;font-size:13.5px" onclick="incomeTicket(\''+x.strategy+'\','+i+')">Place &middot; one tap</button></div></div>';
}
function angelKey(){const a=((PORT&&PORT.accounts)||[]).find(a=>((a.creds_key||'').toUpperCase()).startsWith('ANGEL'));return a?a.creds_key:(((PORT&&PORT.accounts&&PORT.accounts[0])||{}).creds_key||'ANGEL1');}
function incomeTicket(strat,i){
  const x=strat==='covered_call'?INCOME.covered_calls[i]:INCOME.cash_secured_puts[i];
  if(!x)return;
  const qty=x.contracts*x.lot,prem=x.premium,cc=strat==='covered_call';
  const stop=+(prem*2).toFixed(2),tgt=+(prem*0.2).toFixed(2);
  const s=document.getElementById('tk-side');s.textContent='SELL';s.style.background='rgba(255,88,103,.16)';s.style.color='var(--down)';
  document.getElementById('tk-sym').textContent=x.symbol+' '+x.strike+' '+(cc?'CE':'PE');
  document.getElementById('tk-ltp').textContent=px(prem);
  document.getElementById('tk-qty').textContent=qty.toLocaleString('en-IN')+' ('+x.contracts+'×'+x.lot+')';
  document.getElementById('tk-entry').innerHTML=px(prem)+' &nbsp;<span class="faint">LIMIT · SELL</span>';
  document.getElementById('tk-stop').innerHTML=px(stop)+' <span class="faint">buy-back</span>';
  document.getElementById('tk-tgt').innerHTML=px(tgt)+' <span class="faint">80% profit</span>';
  document.getElementById('tk-risk').textContent=inr(qty*(stop-prem));
  document.getElementById('tk-rew').textContent=inr(qty*prem);
  document.getElementById('tk-rr').textContent='—';
  CURR={creds_key:angelKey(),exchange:'NFO',symbol:x.tradingsymbol,token:x.token,side:'SELL',quantity:qty,product:'NRML',order_type:'LIMIT',price:prem,trigger_price:0,underlying:x.symbol,stop_loss:stop,target:tgt};
  openSheet();
}

/* ---- nav + filters ---- */
const TITLES={home:'Home',mtf:'MTF',ideas:'Ideas',income:'Income',hedge:'Hedge',trades:'Trades'};
function go(t){document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));document.getElementById('s-'+t).classList.add('on');
  document.querySelectorAll('#nav button').forEach(b=>b.setAttribute('aria-current',b.dataset.t===t?'true':'false'));
  const ht=document.getElementById('hdr-title');if(ht)ht.textContent=TITLES[t]||'Shares CFO';window.scrollTo(0,0);
  if(t==='mtf'&&!loaded.mtf){loaded.mtf=1;loadMtf();}
  if(t==='ideas'&&!loaded.ideas){loaded.ideas=1;loadDailyStrategy();loadIdeas();loadOI();}
  if(t==='hedge'&&!loaded.hedge){loaded.hedge=1;loadHedge();loadOptions();}
  if(t==='income'&&!loaded.income){loaded.income=1;loadIncome();}
  if(t==='trades'&&!loaded.trades){loaded.trades=1;loadTrades();}}
document.getElementById('nav').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.t==='login'){location.href='/login?'+Q;return;}go(b.dataset.t);});
document.getElementById('filters').addEventListener('click',e=>{const b=e.target.closest('.fchip');if(!b)return;[...document.querySelectorAll('.fchip')].forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');applyFilter();});
function applyFilter(){const f=(document.querySelector('.fchip[aria-pressed="true"]')||{}).textContent||'All';document.querySelectorAll('#holds .h').forEach(h=>{const v=h.dataset.v,vol=parseFloat(h.dataset.vol||0);let s=true;if(f==='Strong')s=v==='strong';else if(f==='Weak')s=v==='weak';else if(f==='Vol surge')s=vol>=2;h.style.display=s?'':'none';});}

/* sparkline (decorative until history endpoint) */
(function(){const c=document.getElementById('spark');if(!c)return;const x=c.getContext('2d'),W=c.width,Hh=c.height,n=30,pts=[];let v=.8;for(let i=0;i<n;i++){v+=Math.sin(i/3)*.006+.006;pts.push(v);}const mn=Math.min(...pts),mx=Math.max(...pts),X=i=>i/(n-1)*W,Y=val=>Hh-6-((val-mn)/(mx-mn))*(Hh-14);x.beginPath();pts.forEach((p,i)=>{i?x.lineTo(X(i),Y(p)):x.moveTo(X(i),Y(p));});x.lineTo(W,Hh);x.lineTo(0,Hh);x.closePath();const g=x.createLinearGradient(0,0,0,Hh);g.addColorStop(0,'rgba(47,189,133,.25)');g.addColorStop(1,'rgba(47,189,133,0)');x.fillStyle=g;x.fill();x.beginPath();pts.forEach((p,i)=>{i?x.lineTo(X(i),Y(p)):x.moveTo(X(i),Y(p));});x.strokeStyle='#2fbd85';x.lineWidth=2.2;x.lineJoin='round';x.stroke();})();

loadPortfolio().then(loadScoring);loadScreener();
setInterval(()=>{loadPortfolio();},20000);
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


_BOOK_CACHE: dict = {"ts": 0.0, "data": None}
_BOOK_REFRESHING: dict = {"flag": False}


async def _consolidated(force: bool = False) -> dict:
    """Consolidated book across all accounts, cached ~15s so many tabs share one
    fetch (with 5 accounts a full fetch is slow; every tab re-fetching made the app
    crawl)."""
    import time
    data = _BOOK_CACHE["data"]
    age = time.time() - _BOOK_CACHE["ts"]
    if not force and data and age < 15:
        return data
    # Stale-while-revalidate: if we have a recent-ish book, hand it back INSTANTLY and
    # refresh in the background. A slow/hung broker then never freezes the tabs that
    # await this — they just see a book a few seconds old. Only a cold start (no data)
    # or an explicit force blocks on the live fetch.
    if not force and data:
        if not _BOOK_REFRESHING["flag"]:
            _BOOK_REFRESHING["flag"] = True

            async def _bg_refresh() -> None:
                try:
                    result = await _consolidated_uncached()
                    _BOOK_CACHE.update(ts=time.time(), data=result)
                except Exception as exc:  # keep serving the last good book
                    log.warning("book refresh failed: %s", exc)
                finally:
                    _BOOK_REFRESHING["flag"] = False

            asyncio.create_task(_bg_refresh())
        return data
    result = await _consolidated_uncached()
    _BOOK_CACHE.update(ts=time.time(), data=result)
    return result


async def _consolidated_uncached() -> dict:
    sectors = SectorMap()
    # Fetch every account concurrently — a multi-account book was fetched serially
    # before, so one slow broker made the whole book (and every tab awaiting it) crawl.
    books = list(await asyncio.gather(*[_fetch_account(k, sectors) for k in get_accounts()]))

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

    from . import health as _health
    _health.beat("holdings", "sector_map", ok=len(ok_books) > 0)
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
    from .terminal import TERMINAL_HTML
    return TERMINAL_HTML


@app.get("/classic", response_class=HTMLResponse)
async def classic() -> str:
    return DASHBOARD_HTML



# --- PWA: installable full-screen on Android/Z Fold, cached app shell -----------
from fastapi.responses import JSONResponse, Response  # noqa: E402

_PWA_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
    '<rect width="512" height="512" fill="#0b0e13"/>'
    '<rect x="96" y="96" width="320" height="320" fill="none" stroke="#3f8cde" stroke-width="18"/>'
    '<path d="M150 330 L220 250 L280 300 L370 190" fill="none" stroke="#2ebd85" stroke-width="20" '
    'stroke-linecap="square"/></svg>'
)


@app.get("/icon.svg")
async def pwa_icon() -> Response:
    return Response(_PWA_ICON, media_type="image/svg+xml")


@app.get("/manifest.json")
async def pwa_manifest() -> JSONResponse:
    return JSONResponse({
        "name": "Market Console", "short_name": "Console",
        "description": "Shares CFO — live trading & portfolio cockpit",
        "start_url": "/", "scope": "/", "display": "standalone",
        "orientation": "any", "background_color": "#07090d", "theme_color": "#0b0e13",
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
        ],
    })


@app.get("/sw.js")
async def service_worker() -> Response:
    # Network-first for data (always fresh), cache-first fallback for the shell so the
    # app opens instantly and survives a brief server/network blip.
    sw = """
const CACHE='mc-v3';
self.addEventListener('install',e=>{self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{
  // Purge every old cache bucket so a deploy always wins over a stale shell.
  const ks=await caches.keys();await Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)));
  await clients.claim();
})());});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'){return;}
  // The HTML shell is ALWAYS network-first: fetch fresh, cache only as an offline
  // fallback. So new layouts show on the next load instead of being pinned.
  if(u.pathname==='/'||u.pathname==='/manifest.json'||u.pathname==='/icon.svg'){
    e.respondWith(fetch(e.request,{cache:'no-store'}).then(r=>{const c=r.clone();caches.open(CACHE).then(k=>k.put(e.request,c));return r;})
      .catch(()=>caches.match(e.request)));
  }
});
"""
    return Response(sw, media_type="application/javascript")


# --- External balances (US stocks / crypto / bank / trading cash) -> Total Wealth ---
@app.get("/balances")
async def balances_list(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from . import balances
    return await asyncio.to_thread(balances.summary)


@app.post("/balances")
async def balances_upsert(request: Request, entry: dict = Body(...),
                          token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from . import balances
    try:
        return balances.upsert(entry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/balances/{entry_id}")
async def balances_delete(request: Request, entry_id: str,
                          token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from . import balances
    return {"deleted": balances.delete(entry_id)}


# --- Calls / tips channels (Bantu Mausaji, Anil Singhvi, ...) --------------------
@app.get("/tips")
async def tips_list(request: Request, token: str | None = Query(default=None)) -> dict:
    """All logged calls, enriched with live NSE price + a state read against each
    call's levels, grouped by channel. Read-only; reports each run."""
    _check_token(request, token)
    from . import tips
    from .brokers import angel_scrip
    from . import health as _health
    items = await asyncio.to_thread(tips.all_tips)
    syms = sorted({t.get("symbol") for t in items if t.get("symbol")})
    ltps = await asyncio.to_thread(angel_scrip.equity_ltps, syms) if syms else {}
    toks = await asyncio.to_thread(lambda: {s: angel_scrip.token_for(s) for s in syms})
    by_channel: dict = {}
    actionable = 0
    for t in items:
        ltp = ltps.get(t.get("symbol"))
        st = tips.state(t, ltp)
        row = {**t, "ltp": ltp, "token": toks.get(t.get("symbol")), **st}
        if st.get("actionable"):
            actionable += 1
        by_channel.setdefault(t.get("source", "Other"), []).append(row)
    _health.beat("ideas")
    return {"channels": [{"source": s, "tips": v} for s, v in sorted(by_channel.items())],
            "count": len(items), "actionable": actionable,
            "known_channels": list(tips.CHANNELS)}


@app.post("/tips")
async def tips_upsert(request: Request, entry: dict = Body(...),
                      token: str | None = Query(default=None)) -> dict:
    """Add or edit a call. A trade with no stop gets a default protective stop; an
    investment idea with no levels gets a default accumulation ladder."""
    _check_token(request, token)
    from . import tips
    try:
        return await asyncio.to_thread(tips.upsert, entry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/tips/{tip_id}")
async def tips_delete(request: Request, tip_id: str,
                      token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from . import tips
    return {"deleted": await asyncio.to_thread(tips.delete, tip_id)}


@app.get("/wealth")
async def wealth(request: Request, token: str | None = Query(default=None)) -> dict:
    """Total Wealth = live demat net worth + external balances (kept separate from the
    trading net-worth figure so the live book stays clean)."""
    _check_token(request, token)
    from . import balances
    book = await _consolidated()
    ext = await asyncio.to_thread(balances.summary)
    demat = book.get("net_worth") or 0.0
    return {"demat_net_worth": round(demat, 2),
            "external_total": ext["total_external_inr"],
            "total_wealth": round(demat + ext["total_external_inr"], 2),
            "by_bucket": ext["by_bucket"], "usdinr": ext["usdinr"]}


@app.get("/preview", response_class=HTMLResponse)
async def preview() -> str:
    """Interactive design prototype (mock data, no auth) — the reference for the redesign."""
    from .preview import PREVIEW_HTML
    return PREVIEW_HTML


@app.get("/healthz")
async def healthz() -> dict:
    """Unauthenticated liveness probe for the container healthcheck (no data touched)."""
    return {"status": "ok"}


@app.get("/status", response_class=HTMLResponse)
async def status_page() -> str:
    """Live proof-of-life dashboard (reads /health.json, same origin). No token needed."""
    from .status_page import STATUS_HTML
    return STATUS_HTML


@app.get("/health.json")
async def health_feed() -> Response:
    """Proof-of-life feed for the status dashboard: per-module heartbeats + session
    state. Unauthenticated by design (no secrets, no financials) so a wall-board can
    poll it; every value is a real timestamp the server stamped, never a hardcoded LIVE."""
    from . import health
    return JSONResponse(health.snapshot(), headers={"Cache-Control": "no-store"})


# Auto-heartbeat: stamp a module every time its endpoint actually returns data. A page
# reading /health.json then reflects reality — anything not stamped shows "no signal".
_HEALTH_PATHS = [
    ("/holdings/grouped", ("holdings", "sector_map")),
    ("/portfolio", ("holdings", "sector_map")),
    ("/positions/deep", ("deep",)),
    ("/positions/live", ("positions",)),
    ("/income/ideas", ("income",)),
    ("/chart/", ("charts",)),
    ("/fundamentals/", ("share_page",)),
    ("/execution/", ("execution",)),
]


@app.middleware("http")
async def _health_heartbeat(request: Request, call_next):
    response = await call_next(request)
    try:
        if response.status_code < 400:
            from . import health
            p = request.url.path
            for prefix, mods in _HEALTH_PATHS:
                if p.startswith(prefix):
                    health.beat(*mods)
                    break
    except Exception:
        pass
    return response


@app.get("/auth/status")
async def auth_status() -> dict:
    """Whether the app should show a password screen (no secrets returned)."""
    from .config import get_password
    return {"password_required": bool(get_password())}


_AUTH_FAILS: dict = {"n": 0, "until": 0.0}


@app.post("/auth/login")
async def auth_login(payload: dict = Body(...)) -> dict:
    """Exchange the app password for the API token. Constant-time compare, a rising
    lock-out after repeated wrong tries, and neither password nor token is ever logged."""
    import hmac
    import time
    from .config import get_password
    pw = get_password()
    if not pw:
        raise HTTPException(status_code=400, detail="Password login is not enabled.")
    now = time.time()
    if now < _AUTH_FAILS["until"]:
        wait = int(_AUTH_FAILS["until"] - now) + 1
        raise HTTPException(status_code=429, detail=f"Too many attempts — wait {wait}s.")
    supplied = str(payload.get("password") or "")
    if not hmac.compare_digest(supplied, pw):
        _AUTH_FAILS["n"] += 1
        # brief, rising back-off after 4 misses (2s, 4s, 8s … capped) to kill brute force
        if _AUTH_FAILS["n"] >= 4:
            _AUTH_FAILS["until"] = now + min(2 ** (_AUTH_FAILS["n"] - 3), 300)
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="Wrong password.")
    _AUTH_FAILS.update(n=0, until=0.0)
    return {"token": get_api_token()}


@app.on_event("startup")
async def _start_proactive() -> None:
    """Launch the market-hours proactive agent (pushes alerts to the phone)."""
    try:
        from . import proactive
        proactive.start(_consolidated)
    except Exception as exc:  # never block startup on the agent
        import logging
        logging.getLogger("shares_cfo").warning("proactive agent not started: %s", exc)
    try:
        asyncio.get_event_loop().create_task(_tick_loop())  # warm live-quote cache (REST fallback)
    except Exception as exc:
        import logging
        logging.getLogger("shares_cfo").warning("tick loop not started: %s", exc)
    try:
        from . import angel_ws
        angel_ws.start(_LIVE_TICKS, _STREAM_TOKENS)  # true real-time tick stream
    except Exception as exc:
        import logging
        logging.getLogger("shares_cfo").warning("angel ws not started: %s", exc)


@app.post("/proactive/test")
async def proactive_test(request: Request, token: str | None = Query(default=None)) -> dict:
    """Send a test push so you can confirm alerts reach your phone."""
    _check_token(request, token)
    from . import notify
    ch = notify.configured()
    if not ch:
        return {"sent": [], "note": "No channel set — add CFO_NTFY_TOPIC or Telegram env vars."}
    sent = notify.send("Shares CFO test", "Proactive alerts are wired. ✅")
    return {"channels": ch, "sent": sent}


@app.get("/health")
async def health(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    sectors = SectorMap()
    books = list(await asyncio.gather(*[_fetch_account(k, sectors) for k in get_accounts()]))
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


def _clean_sym(t: str) -> str:
    import re
    return re.sub(r"-(EQ|BE|BZ|BL|SM|ST|IQ)$", "", (t or "").upper()).split("-")[0]


@app.get("/income/ideas")
async def income_ideas(request: Request, token: str | None = Query(default=None)) -> dict:
    """Covered-call + cash-secured-put income proposals across the family book.

    Covered calls are per account/holder (you can only write calls on shares held in
    that account); CSPs are sized against total ledger cash. Proposals only — placement
    goes through the guarded execution path.
    """
    _check_token(request, token)
    from .analysis import income
    from .brokers import angel_scrip
    book = await _consolidated()
    # Per-holding list tagged with the holder (account) — covered calls are per account.
    holdings = []
    seen_syms: dict[str, dict] = {}
    for a in book.get("accounts", []):
        if a.get("ok") is False or a.get("status") == "degraded":
            continue
        label = a.get("label") or a.get("creds_key")
        for h in a.get("holdings", []):
            sym = _clean_sym(h.get("ticker", ""))
            if not sym:
                continue
            row = {"sym": sym, "quantity": h.get("quantity") or 0,
                   "last_price": h.get("last_price") or 0,
                   "holder": label, "account": a.get("creds_key")}
            holdings.append(row)
            # CSP candidate = a stock you already own (so you'd be glad to own more)
            if sym not in seen_syms and row["last_price"]:
                seen_syms[sym] = {"sym": sym, "last_price": row["last_price"]}
    ccs = await asyncio.to_thread(income.covered_calls, holdings, angel_scrip)
    csps = await asyncio.to_thread(income.cash_secured_puts, list(seen_syms.values()),
                                   book.get("cash", 0), angel_scrip)
    # When empty, say WHY (so it's not a mystery blank): F&O universe loaded?, how many
    # holdings are F&O stocks, how many you own a full lot of, and free cash.
    diag = None
    if not ccs and not csps:
        def _diag():
            uni = angel_scrip._load_stock_options()
            elig = full = 0
            for h in holdings:
                m = angel_scrip.fno_meta(h["sym"])
                if m and m["lot"] > 0:
                    elig += 1
                    if int(h.get("quantity") or 0) >= m["lot"]:
                        full += 1
            return {"fno_universe": len(uni), "holdings": len(holdings),
                    "fno_eligible_holdings": elig, "holdings_with_full_lot": full,
                    "free_cash": round(book.get("cash", 0) or 0, 0)}
        diag = await asyncio.to_thread(_diag)
        if diag["fno_universe"] == 0:
            diag["reason"] = "F&O option chain not loaded — log in to Angel (its feed powers the chain)."
        elif diag["fno_eligible_holdings"] == 0:
            diag["reason"] = "None of your holdings are F&O-eligible stocks — covered calls need an F&O name."
        elif diag["holdings_with_full_lot"] == 0:
            diag["reason"] = ("You hold F&O stocks but not a full lot of any — covered calls need "
                              "≥1 lot. Cash-secured puts need free cash ≥ one lot's value.")
        else:
            diag["reason"] = "Chain premiums unavailable right now — try again during market hours."
    return {"as_of": book.get("as_of"), "cash": book.get("cash", 0),
            "covered_calls": ccs, "cash_secured_puts": csps, "diag": diag,
            "summary": income.summarise(ccs, csps),
            "note": "Premiums are live from the NFO chain where available, else Black-Scholes "
                    "(India VIX as IV). Proposals only — nothing is placed."}


@app.get("/ideas/oi")
async def ideas_oi(request: Request, token: str | None = Query(default=None)) -> dict:
    """Near-month futures OI build-up/unwinding across your F&O holdings."""
    _check_token(request, token)
    from .analysis import oi
    from .brokers import angel_scrip
    book = await _consolidated()
    rows, seen = [], set()
    for a in book.get("accounts", []):
        if a.get("ok") is False:
            continue
        for h in a.get("holdings", []):
            sym = _clean_sym(h.get("ticker", ""))
            if not sym or sym in seen:
                continue
            seen.add(sym)
            mv = h.get("market_value") or 0
            dc = h.get("day_change") or 0
            prev = mv - dc
            rows.append({"sym": sym, "price_change_pct": (dc / prev * 100) if prev else 0})
    signals = await asyncio.to_thread(oi.buildup, rows, angel_scrip)
    return {"as_of": book.get("as_of"), "signals": signals,
            "note": "Futures OI vs the prior trading day. Long buildup / short covering read "
                    "bullish; short buildup / long unwinding read bearish. Deltas populate from "
                    "the second day the app runs."}


_EDGE_CACHE: dict = {}


@app.get("/options/edge/{underlying}")
def options_edge(request: Request, underlying: str,
                 token: str | None = Query(default=None)) -> dict:
    """F&O edge for an index: PCR + Max Pain from live option-chain OI. NIFTY/BANKNIFTY."""
    _check_token(request, token)
    import time
    u = underlying.upper()
    hit = _EDGE_CACHE.get(u)
    if hit and (time.time() - hit[0]) < 60:
        return hit[1]
    if u not in ("NIFTY", "BANKNIFTY"):
        return {"underlying": u, "supported": False,
                "note": "PCR/Max-Pain shown for NIFTY & BANKNIFTY."}
    from .brokers import angel_scrip
    from .analysis import eodhd
    step = 50 if u == "NIFTY" else 100
    spot = None
    q = eodhd.quote("^NSEI" if u == "NIFTY" else "^NSEBANK")
    if q:
        spot = q.get("last")
    chain = angel_scrip._load_options().get(u, {})
    exp = angel_scrip.nearest_expiry(u)
    node = chain.get(exp, {}) if exp else {}
    if not node or not spot:
        return {"underlying": u, "supported": True, "spot": spot, "expiry": exp,
                "pcr": None, "max_pain": None, "note": "chain/spot unavailable right now"}
    atm = round(spot / step) * step
    want = [atm + step * i for i in range(-15, 16)]
    toks: dict = {}
    for s in want:
        n = node.get(str(s), {})
        if n.get("CE"):
            toks[str(n["CE"])] = (s, "CE")
        if n.get("PE"):
            toks[str(n["PE"])] = (s, "PE")
    quotes = angel_scrip.option_full(list(toks.keys())) if toks else {}
    calloi: dict = {}
    putoi: dict = {}
    for tk, (s, typ) in toks.items():
        oi = (quotes.get(tk) or {}).get("oi") or 0
        (calloi if typ == "CE" else putoi)[s] = oi
    tot_call, tot_put = sum(calloi.values()), sum(putoi.values())
    pcr = round(tot_put / tot_call, 2) if tot_call else None

    def pain(E: int) -> float:
        return sum(calloi.get(K, 0) * max(0, E - K) + putoi.get(K, 0) * max(0, K - E) for K in want)

    max_pain = min(want, key=pain) if (tot_call or tot_put) else None
    # walls: strikes with the most OI (support = highest put OI, resistance = highest call OI)
    put_wall = max(putoi, key=putoi.get) if putoi else None
    call_wall = max(calloi, key=calloi.get) if calloi else None
    data = {"underlying": u, "supported": True, "spot": round(spot, 2), "expiry": exp,
            "atm": atm, "pcr": pcr, "max_pain": max_pain,
            "total_call_oi": tot_call, "total_put_oi": tot_put,
            "support_wall": put_wall, "resistance_wall": call_wall,
            "bias": ("bullish" if (pcr and pcr > 1.2) else "bearish" if (pcr and pcr < 0.7) else "neutral"),
            "note": "PCR>1.2 supportive, <0.7 heavy calls. Max Pain = expiry magnet."}
    _EDGE_CACHE[u] = (time.time(), data)
    return data


@app.get("/options/contract/{underlying}")
def options_contract(request: Request, underlying: str, kind: str = "fut",
                     token: str | None = Query(default=None)) -> dict:
    """Nearest tradeable F&O contract for an underlying (futures) — for the order ticket."""
    _check_token(request, token)
    from .brokers import angel_scrip
    u = underlying.upper().split()[0]
    c = angel_scrip.fut_contract(u)
    if not c or not c.get("tradingsymbol"):
        return {"underlying": u, "found": False,
                "note": f"{u} has no F&O futures on the NFO chain."}
    return {"underlying": u, "found": True, "kind": "future",
            "tradingsymbol": c["tradingsymbol"], "token": c["token"],
            "lot": c["lot"], "expiry": c["expiry"]}


import re as _re

_POS_RE_OPT = _re.compile(r"^([A-Z0-9&\-]+)\s+(\d+(?:\.\d+)?)(CE|PE)\s*(.*)$", _re.I)
_POS_RE_FUT = _re.compile(r"^([A-Z0-9&\-]+)\s+FUT\s*(.*)$", _re.I)


def _parse_contract(label: str) -> dict:
    """Best-effort split of an HDFC F&O label into underlying/opt/strike/expiry."""
    label = (label or "").strip().upper()
    m = _POS_RE_OPT.match(label)
    if m:
        return {"underlying": m.group(1), "strike": m.group(2), "opt": m.group(3).upper(),
                "expiry": m.group(4).strip(), "kind": "option"}
    m = _POS_RE_FUT.match(label)
    if m:
        return {"underlying": m.group(1), "strike": "", "opt": "", "expiry": m.group(2).strip(),
                "kind": "future"}
    return {"underlying": label.split()[0] if label else "", "strike": "", "opt": "",
            "expiry": "", "kind": "equity"}


# Session OI baseline per contract token, so "OI up/down" reflects today's build-up
# (first value seen this session vs now), refreshed every time positions are polled.
_OI_SNAP: dict = {}


def _oi_trend(token: str | None, oi) -> tuple:
    """(oi_change, oi_change_pct) vs the first OI seen for this token today."""
    if token is None or oi is None:
        return None, None
    import time
    day = time.strftime("%Y-%m-%d")
    snap = _OI_SNAP.get(token)
    if not snap or snap.get("day") != day:
        _OI_SNAP[token] = {"day": day, "base": oi}
        return 0, 0.0
    base = snap.get("base") or 0
    change = oi - base
    return change, (round(change / base * 100.0, 1) if base else 0.0)


def _leg_bias(r: dict) -> int:
    """Directional bias of a leg: +1 bullish, -1 bearish, 0 neutral.
    Long call / short put / long future = bullish; long put / short call / short future = bearish."""
    qty = r.get("quantity") or 0
    long_ = qty > 0
    opt = (r.get("opt") or "").upper()
    if r.get("kind") == "future":
        return 1 if long_ else -1
    if opt == "CE":
        return 1 if long_ else -1
    if opt == "PE":
        return -1 if long_ else 1
    return 0


def _buildup(change_pct, oi_change) -> str | None:
    """Classic OI + price read (the core F&O tell)."""
    if change_pct is None or oi_change is None:
        return None
    pu, pd = change_pct > 0.05, change_pct < -0.05
    ou, od = oi_change > 0, oi_change < 0
    if pu and ou:
        return "Long buildup"
    if pd and ou:
        return "Short buildup"
    if pu and od:
        return "Short covering"
    if pd and od:
        return "Long unwinding"
    return "Flat"


def _leg_risk(r: dict) -> tuple:
    """(level, why) — flags a leg where losses are likely to deepen, to help cut early."""
    pnl = r.get("pnl") or 0
    bias = _leg_bias(r)
    ch = r.get("change_pct")
    oi_c = r.get("oi_change") or 0
    adverse = bias != 0 and ch is not None and ((bias > 0 and ch < 0) or (bias < 0 and ch > 0))
    if pnl < 0 and adverse and oi_c > 0:
        return "danger", "Losing and OI is building against your side — conviction rising the wrong way. Consider cutting or hedging."
    if pnl < 0 and adverse:
        return "danger", "In loss with price moving against your leg. Respect your stop."
    if pnl < 0:
        return "watch", "In loss — keep the stop tight."
    if pnl > 0 and adverse:
        return "watch", "In profit but momentum turning against you — consider trailing your stop."
    return "ok", ""


# --- Warm live-quote cache: a background loop keeps the F&O leg quotes fresh in
# memory (~3s) so /positions/live reads instantly instead of a broker call per poll. ---
_LIVE_TICKS: dict = {"ts": 0.0, "q": {}}
_STREAM_TOKENS: set = set()


def _mkt_open_ist() -> bool:
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if now.weekday() > 4:
        return False
    mins = now.hour * 60 + now.minute
    return 555 <= mins <= 930  # 09:15–15:30 IST


async def _tick_loop() -> None:
    """Refresh the live quotes for the tokens currently on screen, every ~3s in market
    hours. One batched call, off the request path, so the UI never waits on the broker."""
    import time
    from .brokers import angel_scrip
    await asyncio.sleep(15)
    while True:
        try:
            toks = list(_STREAM_TOKENS)
            ws_fresh = (time.time() - _LIVE_TICKS["ts"]) < 6  # WS is handling it
            if toks and _mkt_open_ist() and not ws_fresh:
                q = await asyncio.to_thread(angel_scrip.option_full, toks)
                if q:
                    _LIVE_TICKS["q"].update(q)
                    _LIVE_TICKS["ts"] = time.time()
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(5 if ws_fresh else 20)
        except Exception as exc:
            log.warning("tick loop: %s", exc)
            await asyncio.sleep(10)


def _avg_plausible(kind: str, avg: float, ltp: float) -> bool:
    """Is the avg cost believable given the live price?

    A FUTURE or EQUITY whose LTP is >3x or <1/3 of its avg almost never reflects a
    real move — it's a bad cost basis (a corporate action, a field the broker doesn't
    populate for F&O, or a mis-resolved contract). We refuse to compute MTM/% off it,
    so the app never shows a fake 20x 'gain'. Options are exempt (they really do move
    that much), and a zero/absent avg is left to the caller.
    """
    if kind not in ("future", "equity"):
        return True
    if not avg or not ltp:
        return True
    ratio = ltp / avg
    return 0.33 <= ratio <= 3.0


async def _live_positions() -> dict:
    """Live F&O positions across accounts, enriched with Angel LTP/OI/volume + MTM.
    Reusable core (endpoint + proactive agent both call this)."""
    from .brokers import angel_scrip
    book = await _consolidated()
    # 1) collapse duplicate legs (HDFC returns net + day rows for the same contract)
    byk: dict = {}
    for a in book.get("accounts", []):
        if a.get("ok") is False:
            continue
        holder = a.get("label") or a.get("creds_key")
        for p in a.get("positions", []):
            c = _parse_contract(p.get("ticker", ""))
            k = (a.get("creds_key"), p.get("ticker"))
            r = byk.get(k)
            if not r:
                r = {"account": a.get("creds_key"), "holder": holder, "label": p.get("ticker"),
                     "kind": c["kind"], "opt": c["opt"], "strike": c["strike"],
                     "underlying": c["underlying"], "expiry": c["expiry"],
                     "product": p.get("product_type"), "quantity": 0,
                     "average_price": p.get("average_price"), "last_price": p.get("last_price"),
                     "pnl": 0.0, "day_pnl": 0.0, "oi": None, "volume": None, "change_pct": None}
                byk[k] = r
            r["quantity"] += p.get("quantity") or 0
            r["pnl"] += p.get("pnl") or 0
            r["day_pnl"] += p.get("day_pnl") or 0
    rows = [r for r in byk.values() if r["quantity"]]
    # 2) resolve each F&O leg to an Angel token and enrich (OI, volume, live price)
    tokmap: dict = {}
    for i, r in enumerate(rows):
        if r["kind"] in ("option", "future"):
            atok = angel_scrip.resolve_nfo_token(r["underlying"], r["opt"], r["strike"], r["expiry"])
            if atok:
                tokmap.setdefault(str(atok), []).append(i)
    if tokmap:
        import time
        _STREAM_TOKENS.update(tokmap.keys())   # feed the background tick loop
        tk = _LIVE_TICKS
        if (time.time() - tk["ts"]) < 8 and all(t in tk["q"] for t in tokmap):
            quotes = {t: tk["q"][t] for t in tokmap}   # instant: served from warm ticks
        else:
            try:  # cold: fetch once, off the loop, and seed the tick cache
                quotes = await asyncio.to_thread(angel_scrip.option_full, list(tokmap.keys()))
            except Exception:
                quotes = {}
            if quotes:
                tk["q"].update(quotes)
                tk["ts"] = time.time()
        for atok, idxs in tokmap.items():
            q = quotes.get(str(atok)) or {}
            for i in idxs:
                r = rows[i]
                r["oi"], r["volume"], r["change_pct"] = q.get("oi"), q.get("volume"), q.get("change_pct")
                r["_atok"] = str(atok)
                ltp = q.get("ltp")
                if ltp:
                    r["last_price"] = ltp
                    avg = r["average_price"] or 0
                    # MTM from the live price (broker gives none for positions) — but
                    # ONLY when the avg is believable, else we'd manufacture a fake gain.
                    if avg and _avg_plausible(r["kind"], avg, ltp):
                        r["pnl"] = round(r["quantity"] * (ltp - avg), 2)
                    if q.get("change_pct") is not None:  # today's move on the leg
                        prev = ltp / (1 + q["change_pct"] / 100.0) if q["change_pct"] != -100 else ltp
                        r["day_pnl"] = round(r["quantity"] * (ltp - prev), 2)
    # Real-time decision signals: OI trend vs session base, price+OI buildup, risk flag.
    for r in rows:
        # Live P&L % on cost (direction-correct: pnl already carries the qty sign).
        avg, qty = r.get("average_price") or 0, abs(r.get("quantity") or 0)
        ltp = r.get("last_price") or 0
        if not _avg_plausible(r.get("kind"), avg, ltp):
            # HDFC's cumulative-positions returns the per-unit unrealised P&L in the
            # avg field for FUTURES (verified across the whole book: LTP − field lands
            # on a believable cost every time). When the "avg" is a small fraction of
            # the LTP, reconstruct the true cost basis: real_avg = LTP − field, so
            # P&L = qty × field. Only futures; options legitimately trade far from LTP.
            if r.get("kind") == "future" and avg > 0 and ltp > 0 and (avg / ltp) < 0.5:
                real_avg = round(ltp - avg, 2)
                r["average_price"] = real_avg
                r["pnl"] = round((r.get("quantity") or 0) * avg, 2)  # signed qty × per-unit P&L
                r["pnl_pct"] = round(avg / real_avg * 100, 2) if real_avg else None
                r["avg_reconstructed"] = True
            else:
                # genuinely can't trust it (equity / odd ratio) — flag, don't fake.
                r["avg_suspect"] = True
                r["pnl_pct"] = None
                r["note_flag"] = f"avg {avg} vs live {ltp} looks off — verify cost basis"
        else:
            cost = avg * qty
            r["pnl_pct"] = round((r.get("pnl") or 0) / cost * 100, 2) if cost else None
        if r["kind"] in ("option", "future"):
            r["oi_change"], r["oi_change_pct"] = _oi_trend(r.get("_atok"), r.get("oi"))
            r["buildup"] = _buildup(r.get("change_pct"), r.get("oi_change"))
            r["bias"] = _leg_bias(r)
            r["risk"], r["risk_why"] = _leg_risk(r)
        r.pop("_atok", None)
    # Sort: risk first (danger, then watch), then biggest MTM swing.
    _rank = {"danger": 0, "watch": 1, "ok": 2}
    rows.sort(key=lambda r: (_rank.get(r.get("risk"), 3), -abs(r.get("pnl") or 0)))
    fno = [r for r in rows if r["kind"] in ("option", "future")]
    from . import angel_ws, health as _health
    import time as _t
    _health.beat("positions")
    ws_live = angel_ws.STATE.get("connected") and (_t.time() - angel_ws.STATE.get("last_tick", 0)) < 10
    return {"as_of": book.get("as_of"), "positions": rows, "fno_count": len(fno),
            "at_risk": sum(1 for r in rows if r.get("risk") == "danger"),
            "feed": "websocket" if ws_live else "polling",
            "day_pnl": round(sum((r["day_pnl"] or 0) for r in rows), 2),
            "realized_pnl": round(sum((r["pnl"] or 0) for r in rows), 2),
            "note": "MTM + today's move from Angel live price; OI trend vs session base; "
                    "buildup = price×OI read; risk flags legs where losses may deepen."}


@app.get("/positions/live")
async def positions_live(request: Request, token: str | None = Query(default=None)) -> dict:
    """Live F&O positions across accounts, enriched with Angel LTP / OI / volume."""
    _check_token(request, token)
    return await _live_positions()


@app.get("/debug/ws")
async def debug_ws(request: Request, token: str | None = Query(default=None)) -> dict:
    """Live WebSocket feed status — is the real-time stream connected + ticking?"""
    _check_token(request, token)
    from . import angel_ws
    import time as _t
    s = dict(angel_ws.STATE)
    s["streaming_tokens"] = len(_STREAM_TOKENS)
    s["cached_quotes"] = len(_LIVE_TICKS.get("q", {}))
    s["last_tick_age_s"] = round(_t.time() - s.get("last_tick", 0), 1) if s.get("last_tick") else None
    return s


# Separate caches for the plain and the AI-narrated report (narration is opt-in).
_DEEP_CACHE: dict = {"ts": 0.0, "data": None}
_DEEP_CACHE_AI: dict = {"ts": 0.0, "data": None}


async def _deep_report(refresh: bool = False, narrate: bool = False) -> dict:
    """Deep analysis for every F&O underlying held — the reusable core behind the
    /positions/deep endpoint AND the proactive conflict agent. Cached ~20 min."""
    import time
    cache = _DEEP_CACHE_AI if narrate else _DEEP_CACHE
    if not refresh and cache["data"] and (time.time() - cache["ts"]) < 1200:
        return cache["data"]

    from . import deep, themes
    from .analysis import market

    live = await _live_positions()
    by_sym: dict = {}
    for p in live.get("positions", []):
        if p.get("kind") not in ("option", "future"):
            continue
        u = (p.get("underlying") or "").upper()
        if not u:
            continue
        s = by_sym.setdefault(u, {"bias": 0, "sector": themes.theme_of(u, None)})
        s["bias"] += p.get("bias") or 0
    if not by_sym:
        data = {"as_of": live.get("as_of"), "reports": [], "conflicts": 0,
                "note": "No F&O positions to analyse."}
        cache.update(ts=time.time(), data=data)
        return data

    macro = {"regime": await asyncio.to_thread(market.regime),
             "global": await asyncio.to_thread(market.global_backdrop)}

    async def _one(sym: str, meta: dict) -> dict:
        rep = await asyncio.to_thread(deep.analyze_underlying, sym, meta["sector"], macro)
        bias = 1 if meta["bias"] > 0 else -1 if meta["bias"] < 0 else 0
        st = {"bullish": 1, "bearish": -1, "neutral": 0}.get(rep["stance"], 0)
        rep["position_bias"] = "bullish" if bias > 0 else "bearish" if bias < 0 else "neutral"
        if bias and st:
            rep["alignment"] = "supports" if bias == st else "conflicts"
        else:
            rep["alignment"] = "neutral"
        return rep

    reports = list(await asyncio.gather(*[_one(s, m) for s, m in by_sym.items()]))

    # Optional LLM narration on top of the structured brief (graceful no-op without a key).
    if narrate:
        from . import llm
        if llm.enabled():
            async def _nar(rep: dict) -> None:
                txt = await asyncio.to_thread(llm.narrate, rep)
                if txt:
                    rep["narrative"] = txt
            await asyncio.gather(*[_nar(r) for r in reports])

    _ar = {"conflicts": 0, "neutral": 1, "supports": 2}
    reports = sorted(reports, key=lambda r: (_ar.get(r["alignment"], 1), -abs(r["score"])))
    data = {"as_of": live.get("as_of"), "regime": macro["regime"].get("regime"),
            "conflicts": sum(1 for r in reports if r["alignment"] == "conflicts"),
            "narrated": narrate, "reports": reports,
            "note": "Advisory synthesis from your own data — verify before acting."}
    cache.update(ts=time.time(), data=data)
    from . import health as _health
    _health.beat("deep")
    return data


@app.get("/positions/deep")
async def positions_deep(request: Request, refresh: int = 0, narrate: int = 0,
                         token: str | None = Query(default=None)) -> dict:
    """Deep analysis for every F&O underlying you hold: fundamental + technical + news
    + sector/macro fused into a stance, and whether it agrees with your position.
    Heavy (prices + news per name), so cached ~20 min; refresh=1 forces, narrate=1 adds
    an AI-written paragraph per underlying (needs ANTHROPIC_API_KEY, else silently skipped)."""
    _check_token(request, token)
    return await _deep_report(refresh=bool(refresh), narrate=bool(narrate))


@app.get("/debug/hdfc-positions")
async def debug_hdfc_positions(request: Request, token: str | None = Query(default=None)) -> dict:
    """Raw position labels per account — to refine F&O contract parsing/OI mapping."""
    _check_token(request, token)
    book = await _consolidated()
    out = []
    for a in book.get("accounts", []):
        for p in a.get("positions", []):
            out.append({"account": a.get("creds_key"), "label": p.get("ticker"),
                        "parsed": _parse_contract(p.get("ticker", "")),
                        "product": p.get("product_type"), "qty": p.get("quantity")})
    return {"count": len(out), "positions": out}


_VOL_CACHE: dict = {"ts": 0.0, "data": None}


@app.get("/holdings/volume")
async def holdings_volume(request: Request, top: int = 12,
                          token: str | None = Query(default=None)) -> dict:
    """Volume spikes among your biggest holdings (today vs 20-day avg). Cached ~5 min."""
    _check_token(request, token)
    import time
    if _VOL_CACHE["data"] and (time.time() - _VOL_CACHE["ts"]) < 300:
        return _VOL_CACHE["data"]
    from .analysis.prices import PriceDataUnavailable, get_ohlcv
    book = await _consolidated()
    agg: dict[str, float] = {}
    for acc in book["accounts"]:
        for h in acc.get("holdings", []):
            agg[_clean_symbol(h["ticker"])] = agg.get(_clean_symbol(h["ticker"]), 0.0) + (h.get("market_value") or 0.0)
    syms = [s for s, _ in sorted(agg.items(), key=lambda x: -x[1])[:top]]
    out = []
    for s in syms:
        try:
            d = get_ohlcv(s, period="1y")
            vols = d.get("volumes", [])
            if len(vols) > 21 and vols[-1]:
                v20 = sum(vols[-21:-1]) / 20
                if v20:
                    out.append({"symbol": s, "vol_x": round(vols[-1] / v20, 2)})
        except PriceDataUnavailable:
            continue
    out.sort(key=lambda x: -x["vol_x"])
    result = {"as_of": book["as_of"], "volume_spikes": out}
    _VOL_CACHE.update(ts=time.time(), data=result)
    return result


def _cap_bucket(mcap: float | None) -> str:
    """Absolute ₹-crore market-cap buckets (SEBI-ish; tweak thresholds here)."""
    if mcap is None:
        return "Unclassified"
    if mcap >= 50000:
        return "Large"
    if mcap >= 10000:
        return "Mid"
    if mcap >= 1000:
        return "Small"
    return "Micro"


_CAP_ORDER = {"Large": 0, "Mid": 1, "Small": 2, "Micro": 3, "Unclassified": 4}


@app.get("/holdings/grouped")
async def holdings_grouped(request: Request, token: str | None = Query(default=None)) -> dict:
    """Holdings bucketed by market-cap AND by themed sector, each group with value /
    day% / unrealised P&L and the stocks inside (name, qty, avg, LTP, P&L, weight)."""
    _check_token(request, token)
    from .analysis import fundamentals
    from . import themes
    book = await _consolidated()
    caps = await asyncio.to_thread(fundamentals.market_caps)  # file read, off the loop

    agg: dict = {}
    for a in book.get("accounts", []):
        if a.get("ok") is False:
            continue
        holder = a.get("label") or a.get("creds_key")
        for h in a.get("holdings", []):
            sym = _clean_symbol(h.get("ticker", ""))
            if not sym:
                continue
            o = agg.setdefault(sym, {"symbol": sym, "qty": 0.0, "value": 0.0, "invested": 0.0,
                                     "day_change": 0.0, "sector": h.get("sector"),
                                     "last_price": h.get("last_price"), "holders": set()})
            qty = h.get("quantity") or 0
            o["qty"] += qty
            o["value"] += h.get("market_value") or 0
            o["invested"] += (h.get("average_price") or 0) * qty
            o["day_change"] += h.get("day_change") or 0
            if h.get("last_price"):
                o["last_price"] = h.get("last_price")
            o["holders"].add(holder)

    total = sum(o["value"] for o in agg.values()) or 1.0
    stocks = []
    for o in agg.values():
        mcap = caps.get(o["symbol"])
        prev = o["value"] - o["day_change"]
        stocks.append({
            "symbol": o["symbol"], "qty": round(o["qty"], 2),
            "value": round(o["value"], 2), "invested": round(o["invested"], 2),
            "unrealised": round(o["value"] - o["invested"], 2),
            "unrealised_pct": round((o["value"] / o["invested"] - 1) * 100, 2) if o["invested"] else 0.0,
            "day_change": round(o["day_change"], 2),
            "day_pct": round(o["day_change"] / prev * 100, 2) if prev else 0.0,
            "weight": round(o["value"] / total * 100, 2),
            "last_price": o["last_price"],
            "avg_price": round(o["invested"] / o["qty"], 2) if o["qty"] else None,
            "market_cap": mcap, "cap": _cap_bucket(mcap),
            "sector": themes.theme_of(o["symbol"], o["sector"]),
            "holders": sorted(o["holders"]),
        })

    def _group(key: str) -> list:
        groups: dict = {}
        for s in stocks:
            g = groups.setdefault(s[key], {"name": s[key], "value": 0.0, "invested": 0.0,
                                           "day_change": 0.0, "count": 0, "stocks": []})
            g["value"] += s["value"]
            g["invested"] += s["invested"]
            g["day_change"] += s["day_change"]
            g["count"] += 1
            g["stocks"].append(s)
        out = []
        for g in groups.values():
            prev = g["value"] - g["day_change"]
            g["stocks"].sort(key=lambda x: -x["value"])
            out.append({"name": g["name"], "value": round(g["value"], 2),
                        "day_change": round(g["day_change"], 2),
                        "day_pct": round(g["day_change"] / prev * 100, 2) if prev else 0.0,
                        "unrealised": round(g["value"] - g["invested"], 2),
                        "unrealised_pct": round((g["value"] / g["invested"] - 1) * 100, 2) if g["invested"] else 0.0,
                        "weight": round(g["value"] / total * 100, 2),
                        "count": g["count"], "stocks": g["stocks"]})
        return out

    by_cap = _group("cap")
    by_cap.sort(key=lambda g: _CAP_ORDER.get(g["name"], 9))
    by_sector = _group("sector")
    by_sector.sort(key=lambda g: -g["value"])
    return {"as_of": book.get("as_of"), "total": round(total, 2),
            "by_cap": by_cap, "by_sector": by_sector, "screener_loaded": bool(caps)}


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


@app.get("/news/{ticker}")
async def news(request: Request, ticker: str, token: str | None = Query(default=None)) -> dict:
    """Recent news headlines for a stock (Google News, free)."""
    _check_token(request, token)
    from .analysis import news as news_mod
    items = await asyncio.to_thread(news_mod.get_news, _clean_symbol(ticker))
    return {"ticker": _clean_symbol(ticker).upper(), "news": items}


@app.get("/chart/{ticker}")
async def chart(request: Request, ticker: str, bars: int = 130,
                token: str | None = Query(default=None)) -> dict:
    """Price + 50/200-DMA series + pivot S/R levels for a symbol's chart."""
    _check_token(request, token)
    from .analysis import levels
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    try:
        data = await asyncio.to_thread(get_ohlcv, _clean_symbol(ticker), "NSE", "1y")
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # any provider surprise -> clean 502, never a bare 500
        raise HTTPException(status_code=502, detail=f"Price provider error for {ticker}: {str(exc)[:160]}")
    closes = data.get("closes") or []
    if not closes:
        raise HTTPException(status_code=503, detail=f"No price series available for {ticker}.")

    def sma_series(vals: list[float], w: int) -> list:
        return [None] * min(w - 1, len(vals)) + [
            sum(vals[i - w + 1:i + 1]) / w for i in range(w - 1, len(vals))
        ]

    from .analysis import technicals as tech_mod
    s50, s200 = sma_series(closes, 50), sma_series(closes, 200)
    n = max(1, min(bars, len(closes)))
    lvl = levels.from_ohlcv(data)
    highs, lows, vols = data.get("highs", []), data.get("lows", []), data.get("volumes", [])
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else last
    t = tech_mod.analyze(closes, vols)
    win = closes[-252:] if len(closes) >= 30 else closes
    hi52 = max(highs[-252:]) if highs else max(win)
    lo52 = min(lows[-252:]) if lows else min(win)
    vol20 = (sum(vols[-21:-1]) / 20) if len(vols) > 21 else (sum(vols) / len(vols) if vols else 0)
    return {
        "symbol": _clean_symbol(ticker).upper(),
        "source": data.get("source"),
        "closes": [round(c, 2) for c in closes[-n:]],
        "sma50": [round(x, 2) if x is not None else None for x in s50[-n:]],
        "sma200": [round(x, 2) if x is not None else None for x in s200[-n:]],
        "last": round(last, 2),
        "day_change_pct": round((last / prev - 1) * 100, 2) if prev else 0.0,
        "day_high": round(highs[-1], 2) if highs else None,
        "day_low": round(lows[-1], 2) if lows else None,
        "wk52_high": round(hi52, 2), "wk52_low": round(lo52, 2),
        "from_52w_high_pct": round((last / hi52 - 1) * 100, 1) if hi52 else None,
        "volume": int(vols[-1]) if vols else None,
        "vol_x": round(vols[-1] / vol20, 2) if vol20 else None,
        "rsi14": t.get("rsi14"), "sma50_val": t.get("sma50"), "sma200_val": t.get("sma200"),
        "above_200dma": t.get("above_200dma"), "dma_signal": t.get("dma_signal"),
        "momentum": t.get("momentum"),
        "levels": lvl,
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
    # Family accounts known (client code + name) but not yet connected — one-tap prefill.
    configured = {k.upper() for k in get_accounts()}
    missing = ""
    for key, label in ACCOUNT_LABELS.items():
        if key.upper() in configured:
            continue
        code = DEFAULT_CLIENT_CODES.get(key, "")
        missing += (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:12px;border-bottom:1px solid #2a3038'>"
            f"<div><div>{label}</div><div style='color:#8b949e;font-size:12px'>{key} · {code}</div></div>"
            f"<button onclick=\"prefill('{key}','{code}')\" style='background:#1f6feb;color:#fff;border:0;"
            f"border-radius:8px;padding:8px 14px;font-weight:700'>Connect</button></div>"
        )
    missing_block = (
        "<div style='font-weight:700;margin:18px 2px 6px'>Family accounts not yet connected</div>"
        f"<div style='background:#161b22;border:1px solid #2a3038;border-radius:14px'>{missing}</div>"
    ) if missing else ""
    add_form = (
        "<div style='background:#161b22;border:1px solid #2a3038;border-radius:14px;margin-top:16px;padding:14px' id='addcard'>"
        "<div style='font-weight:700;margin-bottom:4px'>Connect another account</div>"
        "<div style='color:#8b949e;font-size:12px;margin-bottom:10px'>Adds a new account — stored securely on your server, no VPS editing.</div>"
        "<input id='ac_key' placeholder='Account name (e.g. HDFC3 or ANGEL1)' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<input id='ac_apikey' placeholder='API key' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<input id='ac_apisecret' placeholder='API secret (HDFC)' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<input id='ac_client' placeholder='Client code' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<input id='ac_totp' placeholder='TOTP secret (Angel only)' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<input id='ac_mpin' placeholder='MPIN (Angel only)' style='width:100%;margin:4px 0;padding:9px;border-radius:8px;border:1px solid #2a3038;background:#0d1117;color:#e6edf3'>"
        "<button onclick='addAcc()' style='width:100%;margin-top:8px;padding:11px;border:0;border-radius:9px;background:#58a6ff;color:#04122b;font-weight:700'>Connect account</button>"
        "<div id='ac_msg' style='font-size:13px;margin-top:8px;color:#8b949e'></div></div>"
        "<script>async function addAcc(){var m=document.getElementById('ac_msg');m.textContent='Connecting…';"
        "var b={creds_key:ac_key.value,api_key:ac_apikey.value,api_secret:ac_apisecret.value,client_code:ac_client.value,totp_secret:ac_totp.value,mpin:ac_mpin.value};"
        f"var r=await fetch('/accounts/add?token={t}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(b)}});"
        "var j=await r.json();if(r.ok){m.style.color='#3fb950';m.textContent='✅ '+j.account+' connected. '+j.next;setTimeout(function(){location.reload();},1200);}"
        "else{m.style.color='#f85149';m.textContent=j.detail||'Failed';}}"
        "function prefill(k,c){document.getElementById('ac_key').value=k;document.getElementById('ac_client').value=c;"
        "document.getElementById('addcard').scrollIntoView({behavior:'smooth'});document.getElementById('ac_apikey').focus();"
        "document.getElementById('ac_msg').textContent='Enter '+k+'\\'s HDFC API key + secret, then Connect.';}</script>"
    )
    return (
        "<!doctype html><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<div style='font-family:sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh;padding:16px'>"
        "<h2>Shares CFO — accounts &amp; login</h2>"
        "<p style='color:#8b949e'>Tap Log in for each account (2FA on that holder's phone). Same-day tokens.</p>"
        f"<div style='background:#161b22;border:1px solid #2a3038;border-radius:14px;margin-top:12px'>{rows}</div>"
        f"{missing_block}"
        f"{add_form}"
        f"<p style='margin-top:16px'>"
        f"<a href='/?token={t}' style='color:#58a6ff'>→ Dashboard</a></p></div>"
    )


@app.get("/accounts")
async def accounts_list(request: Request, token: str | None = Query(default=None)) -> dict:
    """Configured accounts + which are logged in + which are app-connected."""
    _check_token(request, token)
    armed = set(token_store.armed_accounts())
    stored = set(account_store.load().keys())
    out = []
    for key in get_accounts():
        try:
            acc = load_account(key)
            out.append({"key": key, "label": acc.label, "broker": acc.broker,
                        "client_code": acc.client_code, "logged_in": key in armed,
                        "source": "app" if key in stored else "env"})
        except SharesCFOError:
            out.append({"key": key, "label": key, "broker": "?", "logged_in": False,
                        "needs_setup": True, "source": "app" if key in stored else "env"})
    return {"accounts": out}


@app.post("/accounts/add")
async def accounts_add(request: Request, body: dict = Body(...),
                       token: str | None = Query(default=None)) -> dict:
    """Connect a broker account from the app (persisted to the state volume, no VPS edit).

    Body: {creds_key, api_key, api_secret?, client_code?, totp_secret?, mpin?}.
    Secrets are stored server-side only and never returned.
    """
    _check_token(request, token)
    key = str(body.get("creds_key", "")).strip().upper()
    if not key:
        raise HTTPException(status_code=400, detail="Account name (e.g. HDFC3) is required.")
    # default the HDFC OAuth callback to this host if not supplied
    if not body.get("redirect_url"):
        base = str(request.base_url).rstrip("/")
        body["redirect_url"] = f"{base}/hdfc/callback"
    try:
        result = account_store.add(key, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"connected": True, **result,
            "next": f"Now log in {key} from the Login tab (2FA on that holder's phone)."}


@app.get("/hdfc/login")
async def hdfc_login(request: Request, key: str = "HDFC1", token: str | None = Query(default=None)):
    """Phone login: redirects you to HDFC's 2FA. After you approve, HDFC calls
    /hdfc/callback and the server arms itself — no PC needed. Protected by the token."""
    _check_token(request, token)
    account = load_account(key)
    token_store.set_pending(key)  # remember which account this login is for
    return RedirectResponse(f"{account.base_url}/login?api_key={account.api_key}")


_used_request_tokens: dict[str, str] = {}  # request_token -> account key (per-process replay guard)


@app.get("/hdfc/callback", response_class=HTMLResponse)
async def hdfc_callback(
    requestToken: str | None = Query(default=None),
    request_token: str | None = Query(default=None),
    key: str | None = Query(default=None),
) -> str:
    """HDFC redirects here with the request token; we exchange it and arm the server.

    Idempotent: browsers frequently hit the callback twice (refresh, prefetch). A
    request token is single-use at HDFC's end, so the second exchange used to 401
    and paint a failure over an already-successful login. Replays now short-circuit
    to the success page."""
    rt = requestToken or request_token
    if not rt:
        return "<h3>No request token found in the callback URL.</h3>"
    if rt in _used_request_tokens:
        key = _used_request_tokens[rt]
        return (
            f"<div style='font-family:sans-serif;padding:24px'>"
            f"<h2 style='color:#3fb950'>✅ {key} logged in for today.</h2>"
            f"<p>You can close this tab and open your dashboard.</p></div>"
        )
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
    if len(_used_request_tokens) > 100:
        _used_request_tokens.clear()
    _used_request_tokens[rt] = key
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


@app.get("/alerts/notify-status")
async def alerts_notify_status(request: Request, token: str | None = Query(default=None)) -> dict:
    """Which push channels are configured (ntfy / telegram)."""
    _check_token(request, token)
    from . import notify
    return {"channels": notify.configured()}


@app.get("/alerts/test")
async def alerts_test(request: Request, token: str | None = Query(default=None)) -> dict:
    """Send a test push to your configured channel(s)."""
    _check_token(request, token)
    from . import notify
    if not notify.configured():
        return {"sent": [], "hint": "Set CFO_NTFY_TOPIC (or Telegram) in .env and redeploy."}
    sent = notify.send("Shares CFO", "✅ Test alert — push notifications are working.")
    return {"sent": sent}


async def _alert_poller() -> None:
    """Background: during market hours, push new critical alerts to your phone."""
    import asyncio
    import time
    from datetime import datetime, timedelta, timezone
    from . import notify
    from .analysis import alert_state
    from .analysis import alerts as alerts_mod

    await asyncio.sleep(30)  # let startup settle
    while True:
        try:
            if notify.configured():
                ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
                market = ist.weekday() < 5 and (9 * 60 + 15) <= (ist.hour * 60 + ist.minute) <= (15 * 60 + 45)
                if market:
                    book = await _consolidated()
                    now = time.time()
                    pushable = alert_state.new_pushable(alerts_mod.evaluate(book), now)
                    for a in pushable:
                        body = a.get("why", "")
                        if a.get("action"):
                            body += f"\n→ {a['action']}"
                        notify.send(f"{a.get('severity', '')} {a.get('what', 'Alert')}", body)
                    if pushable:
                        alert_state.mark_pushed(pushable, now)
        except Exception:
            pass
        await asyncio.sleep(600)  # every 10 min


@app.on_event("startup")
async def _start_poller() -> None:
    import asyncio
    asyncio.create_task(_alert_poller())


@app.get("/options/strategies")
async def options_strategies(request: Request, token: str | None = Query(default=None)) -> dict:
    """Available preset option strategies."""
    _check_token(request, token)
    from .analysis import options
    return {"strategies": [{"key": k, "desc": v} for k, v in options.STRATEGIES.items()]}


@app.get("/options/strategy")
async def options_strategy(request: Request, name: str = "bull_call_spread",
                           underlying: str = "NIFTY", dte: int = 30,
                           token: str | None = Query(default=None)) -> dict:
    """Build + analyse a preset strategy at the live spot/IV (Black-Scholes priced)."""
    _check_token(request, token)
    from .analysis import options
    from .analysis.prices import PriceDataUnavailable, get_spot

    sym = "^NSEBANK" if underlying.upper() in ("BANKNIFTY", "NIFTYBANK") else "^NSEI"
    step = 100.0 if sym == "^NSEBANK" else 50.0
    # Real current lot from the scrip master (BANKNIFTY 35, NIFTY 75, …) — never hardcode;
    # the exchange revises these. Falls back to a known table only if the master is offline.
    from .brokers import angel_scrip
    lot = angel_scrip.lot_size("BANKNIFTY" if sym == "^NSEBANK" else "NIFTY") or (35 if sym == "^NSEBANK" else 75)
    try:
        spot = get_spot(sym)
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Need the market feed for spot ({exc}).")
    iv = 0.14
    try:
        iv = max(0.05, get_spot("^INDIAVIX") / 100.0)  # India VIX as IV proxy
    except PriceDataUnavailable:
        pass
    try:
        legs = options.build_strategy(name, spot, iv, dte, lot, step)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Overlay LIVE traded premiums from Angel where available (else keep Black-Scholes).
    priced = "theoretical"
    expiry = None
    try:
        from .brokers import angel_scrip
        u = "BANKNIFTY" if sym == "^NSEBANK" else "NIFTY"
        expiry = angel_scrip.nearest_expiry(u)
        if expiry:
            ltps = angel_scrip.option_ltps(u, expiry, [int(l["strike"]) for l in legs])
            live = 0
            for l in legs:
                px = ltps.get((int(l["strike"]), l["type"]))
                if px and px > 0:
                    l["premium"] = round(px, 2)
                    l["priced"] = "live"
                    live += 1
            if live:
                priced = "live" if live == len(legs) else "partial"
    except Exception:
        pass

    result = options.analyze(legs, spot, iv, dte, lot)
    result["strategy"] = name
    result["underlying"] = underlying.upper()
    result["iv_pct"] = round(iv * 100, 1)
    result["dte"] = dte
    result["priced"] = priced
    result["expiry"] = expiry
    result["note"] = ("Live premiums from Angel." if priced == "live"
                      else "Some premiums live, rest Black-Scholes." if priced == "partial"
                      else "Theoretical (Black-Scholes, VIX as IV) — live chain unavailable.")
    return result


@app.get("/options/chain")
async def options_chain(request: Request, underlying: str = "NIFTY", width: int = 8,
                        token: str | None = Query(default=None)) -> dict:
    """Live option chain (nearest expiry): strikes around spot with CE/PE LTP."""
    _check_token(request, token)
    from .brokers import angel_scrip
    from .analysis.prices import PriceDataUnavailable, get_spot

    u = "BANKNIFTY" if underlying.upper() in ("BANKNIFTY", "NIFTYBANK") else "NIFTY"
    step = 100 if u == "BANKNIFTY" else 50
    sym = "^NSEBANK" if u == "BANKNIFTY" else "^NSEI"
    try:
        spot = get_spot(sym)
    except PriceDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    expiry = angel_scrip.nearest_expiry(u)
    if not expiry:
        return {"underlying": u, "error": "Option chain unavailable — ensure ANGEL1 is connected."}
    atm = round(spot / step) * step
    strikes = [atm + i * step for i in range(-width, width + 1)]
    ltps = angel_scrip.option_ltps(u, expiry, strikes)
    rows = [{"strike": s, "ce": ltps.get((s, "CE")), "pe": ltps.get((s, "PE")),
             "atm": s == atm} for s in strikes]
    return {"underlying": u, "expiry": expiry, "spot": round(spot, 2), "atm": atm, "chain": rows}


@app.post("/options/payoff")
async def options_payoff(request: Request, body: dict = Body(...),
                         token: str | None = Query(default=None)) -> dict:
    """Analyse custom legs: body {spot, legs:[{side,type,strike,premium,lots}], lot_size?, iv?, dte?}."""
    _check_token(request, token)
    from .analysis import options
    legs = body.get("legs") or []
    spot = float(body.get("spot") or 0)
    if not legs or spot <= 0:
        raise HTTPException(status_code=400, detail="Provide spot and at least one leg.")
    return options.analyze(legs, spot, body.get("iv"), int(body.get("dte") or 30),
                           int(body.get("lot_size") or 75))


@app.get("/mtf")
async def mtf_view(request: Request, token: str | None = Query(default=None)) -> dict:
    """MTF view: true net worth after the margin loan + interest, from the live book."""
    _check_token(request, token)
    from . import mtf
    book = await _consolidated()
    result = mtf.analyze(book)
    result["as_of"] = book["as_of"]
    return result


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
        if t:  # raw technical facts for the UI (volume action, RSI, trend)
            sc["tech"] = {"rsi14": t.get("rsi14"), "vol_x": t.get("volume_surge_x"),
                          "above_200dma": t.get("above_200dma"), "dma_signal": t.get("dma_signal"),
                          "sma50": t.get("sma50"), "sma200": t.get("sma200")}
        rows.append(sc)

    # worst-first: reds, then lowest score. None scores (no data) sink to the bottom.
    order = {"🔴": 0, "🟡": 1, "⚪": 2, "🟢": 3}
    rows.sort(key=lambda x: (order.get(x["verdict"], 2), x["score"] if x["score"] is not None else 999))
    counts = {v: sum(1 for x in rows if x["verdict"] == v) for v in ("🔴", "🟡", "🟢", "⚪")}
    fs = [x["fundamental_score"] for x in rows if x["fundamental_score"] is not None]
    ts = [x["technical_score"] for x in rows if x["technical_score"] is not None]
    book_strength = {"fundamental": round(sum(fs) / len(fs)) if fs else None,
                     "technical": round(sum(ts) / len(ts)) if ts else None}
    return {"as_of": book["as_of"], "counts": counts, "book_strength": book_strength,
            "holdings": rows, "screener_loaded": fun.screener_status().get("loaded", False)}


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
        from .analysis import patterns as pat
        for row in top:
            try:
                data = get_ohlcv(row["symbol"])
                t = tech_mod.analyze(data["closes"], data["volumes"])
                blended = scoring.combine(row["symbol"], row["fields"], t, rule)
                row["technical_score"] = blended["technical_score"]
                row["score"] = blended["score"]
                row["verdict"] = blended["verdict"]
                row["flags"] = blended["flags"]
                fired = pat.detect(data)  # patterns that fired today + backtested edge
                row["patterns"] = fired
                # conviction = fundamentals + a pattern with a real edge + volume/trend
                best = max((p for p in fired if p.get("hit_rate")), default=None,
                           key=lambda p: p["hit_rate"])
                row["signal"] = best
                row["conviction"] = round(
                    0.5 * (row["fundamental_score"] or 0)
                    + 0.3 * (blended["technical_score"] or 0)
                    + 0.2 * (best["hit_rate"] if best else 0), 1)
                row["last_price"] = t.get("last_price")
            except PriceDataUnavailable:
                row["technical_score"] = None
        top.sort(key=lambda x: x.get("conviction") or x.get("score") or x["fundamental_score"],
                 reverse=True)

    return {"universe_size": len(universe), "ranked": len(scored),
            "showing": len(top), "ideas": top}


_HC_CACHE: dict = {"ts": 0.0, "data": None}


def _horizon(sessions) -> str:
    try:
        s = int(sessions or 0)
    except (TypeError, ValueError):
        s = 0
    if s <= 0:
        return "Swing · 1–3 wk"
    if s <= 3:
        return "Short · 1–3 d"
    if s <= 15:
        return "Swing · 1–3 wk"
    return "Positional · 1 mo+"


def _high_conviction(min_conviction: float = 62.0) -> dict:
    """Core high-conviction scan (endpoint + proactive agent share this). Cached 15m."""
    import time
    if _HC_CACHE["data"] and (time.time() - _HC_CACHE["ts"]) < 900:
        return _HC_CACHE["data"]
    from .analysis import fundamentals as fun, scoring, technicals as tech_mod, patterns as pat, strategy
    from .analysis.prices import PriceDataUnavailable, get_ohlcv

    universe = fun.load_universe()
    if not universe:
        return {"error": "No Screener export loaded — upload one in Settings → Screener data to power ideas.",
                "ideas": [], "candidates": []}
    rule = scoring.load_rule()
    scored = []
    for item in universe:
        f = scoring.score_fundamental(item["fields"], rule)
        if f["score"] is not None and f["score"] >= 55:
            scored.append({"symbol": item["symbol"], "name": item.get("name"),
                           "fundamental_score": f["score"], "fields": item["fields"]})
    scored.sort(key=lambda x: x["fundamental_score"], reverse=True)
    analysed, priced_ok = [], 0
    for row in scored[:25]:  # only deep-analyse the fundamentally strongest
        try:
            data = get_ohlcv(row["symbol"])
            priced_ok += 1
            t = tech_mod.analyze(data["closes"], data["volumes"])
            blended = scoring.combine(row["symbol"], row["fields"], t, rule)
            fired = pat.detect(data)
            best = max((p for p in fired if p.get("hit_rate")), default=None,
                       key=lambda p: p["hit_rate"])
            conviction = round(0.5 * (row["fundamental_score"] or 0)
                               + 0.3 * (blended["technical_score"] or 0)
                               + 0.2 * (best["hit_rate"] if best else 0), 1)
            last = t.get("last_price") or 0.0
            sig = strategy.signal(row["symbol"], t, last, risk_budget=10000.0)
            analysed.append({
                "symbol": row["symbol"], "name": row.get("name"), "conviction": conviction,
                "fundamental_score": row["fundamental_score"],
                "technical_score": blended["technical_score"], "verdict": blended["verdict"],
                "horizon": _horizon(best.get("horizon") if best else None),
                "action": sig.get("action"),
                "entry": sig.get("entry"), "stop_loss": sig.get("stop_loss"), "target": sig.get("target"),
                "reward_risk": sig.get("reward_risk"), "last_price": last,
                "pattern": best.get("pattern") if best else None,
                "hit_rate": best.get("hit_rate") if best else None,
                "avg_return_pct": best.get("avg_return_pct") if best else None,
                "flags": blended.get("flags", []),
            })
        except (PriceDataUnavailable, Exception):
            continue
    analysed.sort(key=lambda x: x["conviction"], reverse=True)
    ideas = [r for r in analysed if r["conviction"] >= min_conviction and r["action"] == "BUY"]
    # Near-misses so the tab is never a dead end: strong names that just missed the bar.
    candidates = [r for r in analysed if r not in ideas][:6]
    diag = {"universe": len(universe), "fundamentally_strong": len(scored),
            "analysed": len(analysed), "priced": priced_ok}
    if not ideas:
        if priced_ok == 0 and scored:
            diag["reason"] = "Price data unavailable for the scan — log in to Angel / check the feed."
        elif analysed:
            diag["reason"] = "Nothing cleared the high-conviction bar today — see the closest candidates below."
        else:
            diag["reason"] = "No fundamentally strong names in the current export."
    data = {"ideas": ideas[:10], "candidates": candidates, "diag": diag,
            "min_conviction": min_conviction,
            "note": "High-conviction only: strong fundamentals + a backtested pattern edge + a "
                    "defined-risk entry. Advisory — verify before acting."}
    _HC_CACHE.update(ts=time.time(), data=data)
    return data


@app.get("/ideas/high-conviction")
def ideas_high_conviction(request: Request, min_conviction: float = 62.0,
                          token: str | None = Query(default=None)) -> dict:
    """Only high-conviction BUY ideas, each with a time horizon + entry/stop/target/R:R."""
    _check_token(request, token)
    return _high_conviction(min_conviction)


@app.get("/strategy/daily")
async def strategy_daily(request: Request, token: str | None = Query(default=None)) -> dict:
    """Levels-first Daily Strategy: market bias + NIFTY/BANKNIFTY pivots + discipline."""
    _check_token(request, token)
    from .analysis import daily_strategy
    return daily_strategy.build()


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


@app.get("/screener/watchlist")
async def screener_watchlist(request: Request, token: str | None = Query(default=None)) -> dict:
    """Your holding symbols as a ready-to-use list for building a Screener watchlist.

    Copy `symbols` into a Screener watchlist so your Premium export always covers
    exactly what you own — then upload that export back to score every holding.
    """
    _check_token(request, token)
    book = await _consolidated()
    syms = sorted({_clean_symbol(h["ticker"])
                   for acc in book["accounts"] for h in acc.get("holdings", [])})
    return {"count": len(syms), "symbols": syms,
            "as_text": ", ".join(syms),
            "note": "screener.in → Create watchlist → add these names → Export to Excel → upload here."}


def _mprofit_save(file: "UploadFile") -> Path:
    from . import mprofit
    name = (file.filename or "").strip()
    ext = Path(name).suffix.lower()
    if ext not in (".xlsx", ".xls", ".csv"):
        raise HTTPException(status_code=400, detail="Upload an MProfit .xlsx or .csv export.")
    mprofit.MPROFIT_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in Path(name).stem if c.isalnum() or c in ("-", "_"))[:40] or "mprofit"
    return mprofit.MPROFIT_DIR / f"{utc_now_iso().replace(':', '').replace('.', '')}_{safe}{ext}"


@app.get("/reconcile/mprofit/status")
async def mprofit_status(request: Request, token: str | None = Query(default=None)) -> dict:
    """What MProfit export is loaded (active file, position count)."""
    _check_token(request, token)
    from . import mprofit
    return mprofit.status()


@app.post("/reconcile/mprofit/upload")
async def mprofit_upload(request: Request, file: UploadFile = File(...),
                         token: str | None = Query(default=None)) -> dict:
    """Upload an MProfit holdings export straight from your phone → the drop-zone."""
    _check_token(request, token)
    from . import mprofit
    dest = _mprofit_save(file)
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (15 MB max).")
    dest.write_bytes(data)
    return {"uploaded": dest.name, "bytes": len(data), "status": mprofit.status()}


@app.get("/reconcile/mprofit")
async def mprofit_reconcile(request: Request, cost_tol_pct: float = 1.0,
                            token: str | None = Query(default=None)) -> dict:
    """Diff the live broker book against your latest MProfit export.

    Surfaces quantity mismatches, average-cost drift, and holdings that exist on
    only one side — the exact gaps to investigate.
    """
    _check_token(request, token)
    from . import mprofit
    book = await _consolidated()
    broker = [{"symbol": h["ticker"], "quantity": h.get("quantity"),
               "average_price": h.get("average_price")}
              for acc in book["accounts"] for h in acc.get("holdings", [])]
    result = mprofit.reconcile(broker, cost_tol_pct=cost_tol_pct)
    result["as_of"] = book["as_of"]
    return result


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
                 "product", "order_type", "price", "trigger_price", "underlying",
                 "stop_loss", "target", "lot_size")


def _build_order(d: dict):
    """Build an OrderRequest from a request body, auto-filling the F&O lot size.

    For an NFO order the guardrails need the real lot size to enforce whole-lot
    sizing and the lots cap. We resolve it live from Angel's futures scrip master
    (cached to disk) unless the client already supplied one.
    """
    from .execution.models import OrderRequest
    o = OrderRequest(**{k: d[k] for k in _ORDER_FIELDS if k in d})
    if o.is_fno and not o.lot_size and o.underlying:
        try:
            from .brokers import angel_scrip
            o.lot_size = int(angel_scrip.lot_size(o.underlying) or 0)
        except Exception:
            o.lot_size = 0
    return o


async def _day_pnl() -> float:
    """Rough intraday P&L across the book, for the daily-loss halt."""
    try:
        book = await _consolidated()
        return float(book.get("positions_pnl", 0.0)) + float(book.get("unrealised_pnl", 0.0))
    except Exception:
        return 0.0


@app.get("/debug/holdings-fields")
async def debug_holdings_fields(request: Request, key: str | None = Query(default=None),
                                token: str | None = Query(default=None)) -> dict:
    """Show the RAW field NAMES HDFC returns for holdings/margins, so MTF can be
    wired against the real schema. Returns field names + only MTF-ish values —
    not your positions. Temporary; removed once MTF is mapped."""
    _check_token(request, token)
    from .brokers.hdfc import HdfcAdapter
    from .brokers import hdfc_endpoints as ep

    # first account that has a same-day token, unless one is named
    target = key
    if not target:
        armed = token_store.armed_accounts()
        target = armed[0] if armed else "HDFC1"
    account = load_account(target)
    stored = token_store.get_token(target)
    if stored:
        account.access_token = stored
    adapter = HdfcAdapter(account)
    mtf_like = ("mtf", "margin", "fund", "collateral", "loan", "pledge", "emargin",
                "product", "delivery", "cnc", "financed", "leverage")
    try:
        raw_h = await adapter._get(ep.HOLDINGS)
        rows = adapter._rows(raw_h, "holdings", "data", "holding")
        field_names = sorted({k for r in rows if isinstance(r, dict) for k in r.keys()})
        sample_mtf = {}
        if rows and isinstance(rows[0], dict):
            for k, v in rows[0].items():
                if any(t in k.lower() for t in mtf_like):
                    sample_mtf[k] = v
        raw_f = await adapter._get(ep.FUNDS)
        funds_top = list(raw_f.get("data", raw_f).keys()) if isinstance(raw_f.get("data", raw_f), dict) else []
        return {"account": target, "holding_field_names": field_names,
                "mtf_like_fields_on_first_row": sample_mtf,
                "funds_top_level_keys": funds_top,
                "note": "Paste this back — I'll map MTF from the real field names."}
    except SharesCFOError as exc:
        return {"error": str(exc), "hint": "This account may need login first at /login."}
    finally:
        await adapter.close()


@app.get("/debug/hdfc-history")
async def debug_hdfc_history(request: Request, key: str | None = Query(default=None),
                             token: str | None = Query(default=None)) -> dict:
    """Probe HDFC OApi for a historical/candle endpoint so per-stock charts can use it.

    Tries candidate paths against a real instrument from your book and reports which
    return data. Read-only. Temporary; removed once the endpoint is identified.
    """
    _check_token(request, token)
    from datetime import datetime as _dt, timedelta, timezone as _tz
    from .brokers.hdfc import HdfcAdapter

    target = key or (token_store.armed_accounts() or ["HDFC1"])[0]
    account = load_account(target)
    stored = token_store.get_token(target)
    if stored:
        account.access_token = stored
    adapter = HdfcAdapter(account)

    # a real instrument to query with
    tok, exch, sym = "", "NSE", ""
    try:
        hs = await adapter.get_holdings()
        for h in hs:
            if h.get("token"):
                tok, exch, sym = h["token"], h.get("exchange", "NSE"), h.get("ticker", "")
                break
    except SharesCFOError:
        pass

    today = utc_now_iso()[:10]
    frm = (_dt.now(_tz.utc) - timedelta(days=40)).strftime("%Y-%m-%d")
    paths = ["/historical", "/historical-data", "/chart", "/charts", "/candle", "/candles",
             "/historical/candle", "/market/historical", "/instruments/historical",
             "/price/historical", "/historical-chart", "/quote/historical",
             f"/historical/{exch}/{tok}", "/market-data/historical"]
    param_sets = [
        {"exchange": exch, "security_id": tok, "interval": "1D", "from": frm, "to": today},
        {"exchange": exch, "token": tok, "timeframe": "day", "fromDate": frm, "toDate": today},
        {"exchange": exch, "instrument_token": tok, "interval": "day"},
    ]
    results = []
    try:
        for path in paths:
            hit = None
            for ps in param_sets:
                try:
                    r = await adapter._http.get(path, params=ps, headers=adapter._auth_headers())
                    if r.status_code != 404:
                        hit = {"path": path, "status": r.status_code, "snippet": r.text[:140]}
                        break
                except Exception as exc:
                    hit = {"path": path, "error": str(exc)[:80]}
                    break
            if hit and hit.get("status") not in (None,) and hit.get("status") != 404:
                results.append(hit)
        return {"account": target, "sample": {"symbol": sym, "token": tok, "exchange": exch},
                "found": results,
                "note": "Any 200 with candle data = the endpoint to wire. Paste this back."}
    except Exception as exc:
        return {"account": target, "error": str(exc)[:200],
                "sample": {"symbol": sym, "token": tok, "exchange": exch}}
    finally:
        await adapter.close()


@app.get("/execution/status")
async def execution_status(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from .execution import engine
    return engine.status()


@app.get("/execution/preflight")
async def execution_preflight(request: Request, token: str | None = Query(default=None)) -> dict:
    """One-glance 'ready to trade?' — checks every knob + the broker session for
    EQUITY and F&O separately, and names the exact missing item for each.

    Green means an order of that segment can pass the guardrails right now; red
    lists precisely what to set. Reads config only — places nothing."""
    _check_token(request, token)
    from .config import get_trading_config
    from .execution import engine
    cfg = get_trading_config()

    # Is the Angel account logged in (F&O routes through Angel)?
    angel_ready, angel_note = False, "not checked"
    try:
        from .brokers import angel_scrip
        _k, _acc, _jwt = await asyncio.to_thread(angel_scrip._session)
        angel_ready, angel_note = True, "session live"
    except Exception as exc:
        angel_note = str(exc)[:160]

    def _need(label: str, ok: bool, hint: str) -> dict:
        return {"item": label, "ok": bool(ok), "fix": "" if ok else hint}

    st = engine.status()
    shared = [
        _need("master switch", cfg.enabled, "set CFO_TRADING_ENABLED=true"),
        _need("kill-switch clear", not st["kill_switch"], "kill-switch engaged — restart to clear"),
        _need("per-trade risk cap", cfg.max_risk_per_trade > 0, "set CFO_MAX_RISK_PER_TRADE"),
        _need("daily order cap", cfg.max_orders_per_day > 0, "set CFO_MAX_ORDERS_PER_DAY"),
    ]
    equity = shared + [
        _need("qty cap", cfg.max_qty_per_order > 0, "set CFO_MAX_QTY_PER_ORDER"),
        _need("value cap", cfg.max_value_per_order > 0, "set CFO_MAX_VALUE_PER_ORDER"),
        _need("equity allow-list", bool(cfg.allowed_underlyings), "set CFO_ALLOWED_UNDERLYINGS"),
    ]
    fno = shared + [
        _need("F&O switch", cfg.fno_enabled, "set CFO_FNO_ENABLED=true"),
        _need("F&O allow-list", bool(cfg.fno_underlyings()),
              "set CFO_FNO_ALLOWED_UNDERLYINGS (or CFO_ALLOWED_UNDERLYINGS)"),
        _need("lots cap", cfg.max_lots_per_order > 0, "set CFO_MAX_LOTS_PER_ORDER"),
        _need("option premium cap", cfg.max_premium_per_order > 0, "set CFO_MAX_PREMIUM_PER_ORDER"),
        _need("Angel session", angel_ready, f"Angel not logged in: {angel_note}"),
    ]
    return {
        "equity": {"ready": all(c["ok"] for c in equity), "checks": equity},
        "fno": {"ready": all(c["ok"] for c in fno), "checks": fno},
        "notional_fno_cap": cfg.max_notional_fno or None,  # optional, informational
        "angel_session": {"ready": angel_ready, "note": angel_note},
    }


@app.get("/execution/log")
async def execution_log(request: Request, limit: int = 50,
                        token: str | None = Query(default=None)) -> dict:
    """The trade log: recent proposals, placements, and kill events (newest first)."""
    _check_token(request, token)
    from .execution import engine
    return {"events": engine.recent(limit)}


@app.get("/market/global")
async def market_global(request: Request, token: str | None = Query(default=None)) -> dict:
    """Live global-markets backdrop (S&P, Nasdaq, Brent, Gold, USD/INR, India VIX...)."""
    _check_token(request, token)
    from .analysis import market
    return await asyncio.to_thread(market.global_backdrop)


_IDX_CACHE: dict = {"ts": 0.0, "data": None}


@app.get("/market/indices")
async def market_indices(request: Request, token: str | None = Query(default=None)) -> dict:
    """Domestic index strip (NIFTY, BANKNIFTY, SENSEX, VIX, Midcap, Smallcap).

    EODHD-backed; only indices that resolve on the plan are returned, so the ticker
    degrades gracefully rather than showing blanks. Cached ~30s.
    """
    _check_token(request, token)
    import time
    if _IDX_CACHE["data"] and (time.time() - _IDX_CACHE["ts"]) < 30:
        return _IDX_CACHE["data"]
    from .analysis import eodhd
    wanted = [("NIFTY 50", "^NSEI"), ("BANK NIFTY", "^NSEBANK"), ("SENSEX", "^BSESN"),
              ("INDIA VIX", "^INDIAVIX"), ("MIDCAP", "^CNXMIDCAP"), ("SMALLCAP", "^CNXSC")]

    def _fetch() -> list:  # sync EODHD calls, run off the event loop
        o = []
        if eodhd.enabled():
            for name, sym in wanted:
                q = eodhd.quote(sym)
                if q and q.get("last") is not None:
                    o.append({"name": name, "symbol": sym,
                              "last": q["last"], "change_pct": q.get("change_pct")})
        return o

    out = await asyncio.to_thread(_fetch)
    data = {"indices": out, "note": "EODHD; unlisted indices omitted." if out
            else "No index feed — set CFO_EODHD_API_KEY."}
    _IDX_CACHE.update(ts=time.time(), data=data)
    return data


@app.get("/debug/angel-candles")
async def debug_angel_candles(request: Request, symbol: str = "RELIANCE",
                              token: str | None = Query(default=None)) -> dict:
    """Verify Angel is serving NSE stock candles (per-stock chart/technicals source)."""
    _check_token(request, token)
    from .brokers import angel_scrip
    res, dbg = angel_scrip.fetch(symbol)
    if res and res.get("closes"):
        return {"symbol": symbol.upper(), "angel_token": dbg.get("token"), "bars": res["bars"],
                "last_close": res["closes"][-1], "source": "angel", "ok": True}
    return {"ok": False, "debug": dbg,
            "hint": "If login says missing TOTP/MPIN, connect ANGEL1 fully in the Login tab. "
                    "If candle_status is 403/rejected, whitelist VPS IP 72.60.97.133 in SmartAPI."}


@app.get("/debug/angel-holdings")
async def debug_angel_holdings(request: Request, token: str | None = Query(default=None),
                               fresh: int = Query(default=0)) -> dict:
    """Raw Angel getAllHolding structure (keys/counts, not full positions) to fix parsing.

    ?fresh=1 discards any cached JWT and forces a brand-new server-side login first,
    so we can tell a stale-cache rejection from a genuinely refused fresh token.
    """
    _check_token(request, token)
    import httpx
    from . import token_store
    from .brokers import angel_scrip
    from .brokers.angel import HOLDINGS, RMS, _headers, _public_ip
    key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
    if not key:
        return {"error": "no Angel account configured"}
    acc = load_account(key)
    if fresh:
        token_store.set_token(acc.creds_key, "")  # drop cached JWT -> force fresh login
    jwt, note = angel_scrip._login(acc)
    if not jwt:
        return {"login": note, "error": "login failed"}
    # Token *shape* only (never the token): a jwtToken that already carries a
    # "Bearer " prefix would make our f"Bearer {jwt}" a double-Bearer and get
    # every secure call rejected with AG8001. eyJ = a normal unprefixed JWT.
    probe = {"public_ip_header": _public_ip(),
             "login_note": note,
             "jwt_already_has_bearer": jwt.lower().startswith("bearer"),
             "jwt_looks_like_jwt": jwt.startswith("eyJ"),
             "jwt_len": len(jwt)}
    # Candles = a *third* secure endpoint (historical). If it works while RMS/
    # holdings don't, the token is fine and it's a per-endpoint permission gate.
    try:
        cres, _cdbg = angel_scrip.fetch("RELIANCE")
        probe["candles_secure_endpoint"] = "ok" if (cres and cres.get("closes")) else "REJECTED/empty"
    except Exception as exc:
        probe["candles_secure_endpoint"] = f"error: {str(exc)[:120]}"
    # Same JWT against a *different* secure endpoint (RMS/funds). Separates a
    # portfolio-scope problem (RMS ok, holdings rejected) from a blanket IP/token
    # rejection (both rejected). No balances echoed — only the accept/reject verdict.
    try:
        rr = httpx.get(acc.base_url + RMS, headers=_headers(acc, jwt), timeout=30).json()
        probe["rms_secure_endpoint"] = ("ok" if (rr.get("success") or rr.get("status"))
                                        else f"REJECTED: {rr.get('message')} ({rr.get('errorCode') or rr.get('errorcode') or ''})")
    except Exception as exc:
        probe["rms_secure_endpoint"] = f"error: {str(exc)[:120]}"
    try:
        r = httpx.get(acc.base_url + HOLDINGS, headers=_headers(acc, jwt), timeout=30)
        j = r.json()
    except Exception as exc:
        return {"error": str(exc)[:200], **probe}
    data = j.get("data")
    info = {"account": key, "http": r.status_code, "message": j.get("message"),
            "errorcode": j.get("errorCode") or j.get("errorcode"),
            "data_type": type(data).__name__, **probe}
    if isinstance(data, dict):
        info["data_keys"] = list(data.keys())
        h = data.get("holdings")
        info["holdings_count"] = len(h) if isinstance(h, list) else None
        if isinstance(h, list) and h:
            info["first_holding_keys"] = list(h[0].keys())
        info["totalholding"] = data.get("totalholding")
    elif isinstance(data, list):
        info["data_count"] = len(data)
        if data:
            info["first_row_keys"] = list(data[0].keys())
    else:
        info["raw_snippet"] = r.text[:300]
    return info


@app.get("/market/feed-check")
async def market_feed_check(request: Request, token: str | None = Query(default=None)) -> dict:
    """Verify the EODHD feed: which symbols resolve + a sample price. No key printed."""
    _check_token(request, token)
    from .analysis import eodhd
    if not eodhd.enabled():
        return {"enabled": False, "message": "CFO_EODHD_API_KEY not set — add it to .env and redeploy."}
    return eodhd.feed_check()


@app.get("/market/regime")
async def market_regime(request: Request, token: str | None = Query(default=None)) -> dict:
    """Market regime (calm/cautious/stressed) + the risk budget it hands the idea engine."""
    _check_token(request, token)
    from .analysis import market
    return market.regime()


@app.post("/debug/hdfc-order-preview")
async def hdfc_order_preview(request: Request, order: dict = Body(...),
                            token: str | None = Query(default=None)) -> dict:
    """Show the exact HDFC order request that WOULD be sent — nothing is placed.
    Use to verify the endpoint/payload against HDFC docs before enabling trading."""
    _check_token(request, token)
    from .execution.models import OrderRequest
    from .brokers import hdfc_order
    try:
        o = _build_order(order)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Bad order fields: {exc}")
    return hdfc_order.preview(o)


@app.post("/execution/propose")
async def execution_propose(request: Request, order: dict = Body(...),
                            token: str | None = Query(default=None)) -> dict:
    """Validate an order against all guardrails and return a confirm summary. Sends nothing."""
    _check_token(request, token)
    from .execution import engine
    from .execution.guardrails import GuardrailError
    try:
        o = _build_order(order)
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
    except RuntimeError as exc:  # broker rejected / login failed — order NOT placed
        raise HTTPException(status_code=502, detail=f"Broker: {exc}")


@app.post("/execution/kill")
async def execution_kill(request: Request, token: str | None = Query(default=None)) -> dict:
    _check_token(request, token)
    from .execution import engine
    return engine.engage_kill()


# --- Order lifecycle: multi-account order book + cancel + modify ----------------
_OPEN_STATES = ("open", "trigger pending", "pending", "validation pending",
                "modified", "put order req received", "modify pending")


async def _account_orders(creds_key: str) -> dict:
    """Today's orders for ONE account via its own broker adapter. Never raises —
    a failing account degrades to an error string so the others still return."""
    from .brokers import make_adapter
    try:
        acc = load_account(creds_key)
    except Exception as exc:
        return {"key": creds_key, "label": creds_key, "orders": [], "error": str(exc)[:200]}
    stored = token_store.get_token(creds_key)
    if stored:
        acc.access_token = stored
    adapter = make_adapter(acc)
    try:
        orders = await adapter.get_order_book()
        return {"key": creds_key, "label": acc.label, "orders": orders}
    except Exception as exc:
        return {"key": creds_key, "label": acc.label, "orders": [], "error": str(exc)[:200]}
    finally:
        try:
            await adapter.close()
        except Exception:
            pass


@app.get("/orders/book")
async def orders_book(request: Request, token: str | None = Query(default=None)) -> dict:
    """Live broker order book across EVERY connected account (HDFC + Angel).

    Each order is tagged with the account it lives in; a broker that errors is
    surfaced per-account instead of being hidden as 'no orders'. Read-only."""
    _check_token(request, token)
    results = list(await asyncio.gather(*[_account_orders(k) for k in get_accounts()]))
    orders: list[dict] = []
    errors: list[dict] = []
    for r in results:
        orders.extend(r.get("orders") or [])
        if r.get("error"):
            errors.append({"account": r.get("label") or r["key"], "error": r["error"]})
    # actionable (open / trigger-pending / modifiable) first, then the rest
    orders.sort(key=lambda o: 0 if (o.get("status") or "") in _OPEN_STATES else 1)
    return {
        "orders": orders,
        "open": sum(1 for o in orders if (o.get("status") or "") in _OPEN_STATES),
        "errors": errors,
        "accounts": [{"account": r.get("label") or r["key"], "ok": not r.get("error"),
                      "count": len(r.get("orders") or [])} for r in results],
    }


@app.get("/reconcile/live")
async def reconcile_live_endpoint(request: Request, token: str | None = Query(default=None)) -> dict:
    """Reconcile execution + risk across EVERY connected account.

    Not 'console vs broker' (same source, always agrees) but integrity between what
    we did and what the broker holds: orders we recorded sending vs the live order
    book, protective stops that actually landed, and open positions with no stop."""
    _check_token(request, token)
    from . import reconcile_live as R
    from .execution import engine

    # 1) live order book across all accounts (reuse the aggregator helper)
    obooks = list(await asyncio.gather(*[_account_orders(k) for k in get_accounts()]))
    broker_orders: list[dict] = []
    order_errors: list[dict] = []
    for r in obooks:
        broker_orders.extend(r.get("orders") or [])
        if r.get("error"):
            order_errors.append({"account": r.get("label") or r["key"], "error": r["error"]})

    # A resting GTT rule protects a position just like a trigger order does. Fold the
    # Angel GTT book in as pseudo-orders so a GTT-protected leg isn't flagged naked.
    # (GTT is Angel-only here — HDFC futures have no GTT in the system, so they stay
    # flagged, which is correct: they genuinely have no automated stop.)
    try:
        from .brokers import angel_scrip
        akey = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
        gtts = await asyncio.to_thread(angel_scrip.gtt_list)
        for g in gtts or []:
            broker_orders.append({
                "orderid": f"gtt:{g.get('id')}", "side": (g.get("side") or "").upper(),
                "trigger": g.get("trigger") or 0, "status": "trigger pending",
                "symbol": g.get("symbol"), "symboltoken": str(g.get("symboltoken") or ""),
                "creds_key": akey, "is_gtt": True,
            })
    except Exception:
        pass  # GTT unavailable shouldn't break reconciliation

    # 2) open positions across accounts (from the consolidated book)
    book = await _consolidated()
    positions: list[dict] = []
    for a in book.get("accounts", []):
        if a.get("ok") is False:
            continue
        for p in a.get("positions", []):
            positions.append({
                "creds_key": a.get("creds_key"),
                "account": a.get("label") or a.get("creds_key"),
                "ticker": p.get("ticker"), "token": p.get("token"),
                "quantity": p.get("quantity") or 0,
                "kind": _parse_contract(p.get("ticker", "")).get("kind"),
            })

    # 3) suspect cost-basis legs from the live (MTM-enriched) view
    try:
        live = await _live_positions()
        suspect = [{"account": r.get("holder"), "symbol": r.get("label"),
                    "avg": r.get("average_price"), "ltp": r.get("last_price")}
                   for r in live.get("positions", []) if r.get("avg_suspect")]
    except Exception:
        suspect = []

    # 4) match recorded sends against the broker book
    sent = [e for e in engine.recent(300) if e.get("event") == "SENT"]
    orders = R.match_orders(sent, broker_orders)
    naked = R.naked_positions(positions, broker_orders)
    summary = R.summarize(orders, naked, suspect, order_errors)

    from . import mprofit
    return {
        "summary": summary,
        "orders": orders,
        "naked_positions": naked,
        "suspect_cost_basis": suspect,
        "account_read_errors": order_errors,
        "accounts_checked": [r.get("label") or r["key"] for r in obooks],
        "mprofit": mprofit.status(),  # holdings-vs-book reconciliation availability
        "as_of": book.get("as_of"),
    }


def _trading_on() -> None:
    """Master switch guard for live broker writes (cancel/modify)."""
    from .config import get_trading_config
    if not get_trading_config().enabled:
        raise HTTPException(status_code=403,
                            detail="Trading is OFF (master switch CFO_TRADING_ENABLED not set).")


@app.post("/orders/cancel")
async def orders_cancel(request: Request, payload: dict = Body(...),
                        token: str | None = Query(default=None)) -> dict:
    """Cancel an open / trigger-pending order. Gated on the master switch."""
    _check_token(request, token)
    _trading_on()
    oid = str(payload.get("orderid") or "").strip()
    if not oid:
        raise HTTPException(status_code=400, detail="orderid required.")
    broker = (payload.get("broker") or "angel").lower()
    if broker == "hdfc":
        raise HTTPException(status_code=501,
                            detail="HDFC order cancel isn't wired yet — cancel it in the HDFC app. "
                                   "Angel orders cancel here.")
    from .brokers import angel_scrip
    try:
        res = await asyncio.to_thread(angel_scrip.cancel_order, oid,
                                      payload.get("variety") or "NORMAL")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:200])
    from .execution import engine
    engine._audit("CANCEL", {"orderid": oid, "result": res})
    return res


@app.post("/orders/modify")
async def orders_modify(request: Request, payload: dict = Body(...),
                        token: str | None = Query(default=None)) -> dict:
    """Modify a pending order's price / qty / trigger. Gated on the master switch."""
    _check_token(request, token)
    _trading_on()
    req = {k: payload.get(k) for k in ("orderid", "variety", "tradingsymbol", "symboltoken",
                                       "exchange", "order_type", "quantity", "price",
                                       "trigger_price", "product")}
    if not req.get("orderid"):
        raise HTTPException(status_code=400, detail="orderid required.")
    if (payload.get("broker") or "angel").lower() == "hdfc":
        raise HTTPException(status_code=501,
                            detail="HDFC order modify isn't wired yet — modify it in the HDFC app. "
                                   "Angel orders modify here.")
    from .brokers import angel_scrip
    try:
        res = await asyncio.to_thread(
            angel_scrip.modify_order, str(req["orderid"]), req.get("variety") or "NORMAL",
            req.get("tradingsymbol") or "", str(req.get("symboltoken") or ""),
            req.get("exchange") or "NSE", req.get("order_type") or "LIMIT",
            int(req.get("quantity") or 0), float(req.get("price") or 0),
            float(req.get("trigger_price") or 0), req.get("product") or "CNC")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:200])
    from .execution import engine
    engine._audit("MODIFY", {"orderid": req["orderid"], "result": res})
    return res


# --- GTT: Good-Till-Triggered resting orders (persist at the broker) ------------
@app.get("/gtt/list")
async def gtt_list(request: Request, token: str | None = Query(default=None)) -> dict:
    """Active GTT rules. Read-only."""
    _check_token(request, token)
    from .brokers import angel_scrip
    try:
        rules = await asyncio.to_thread(angel_scrip.gtt_list)
    except Exception as exc:
        return {"gtt": [], "error": str(exc)[:200]}
    return {"gtt": rules, "count": len(rules)}


@app.post("/gtt/create")
async def gtt_create(request: Request, payload: dict = Body(...),
                     token: str | None = Query(default=None)) -> dict:
    """Create a GTT rule (master-switch gated + a light cap check)."""
    _check_token(request, token)
    _trading_on()
    need = ("tradingsymbol", "symboltoken", "exchange", "side", "price", "qty", "trigger")
    if any(not payload.get(k) for k in need):
        raise HTTPException(status_code=400, detail=f"GTT needs: {', '.join(need)}.")
    # Reuse the order caps so a fat-finger GTT is blocked the same way a live order is.
    from .config import get_trading_config
    cfg = get_trading_config()
    qty, price = int(payload["qty"]), float(payload["price"])
    if cfg.max_qty_per_order and qty > cfg.max_qty_per_order:
        raise HTTPException(status_code=403, detail=f"Qty {qty} over cap {cfg.max_qty_per_order}.")
    if cfg.max_value_per_order and qty * price > cfg.max_value_per_order:
        raise HTTPException(status_code=403, detail=f"Value over cap ₹{cfg.max_value_per_order:,.0f}.")
    from .brokers import angel_scrip
    try:
        res = await asyncio.to_thread(
            angel_scrip.gtt_create, payload["tradingsymbol"], str(payload["symboltoken"]),
            payload["exchange"], payload["side"], payload.get("product", "CNC"),
            price, qty, float(payload["trigger"]), int(payload.get("timeperiod", 365)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:200])
    from .execution import engine
    engine._audit("GTT_CREATE", {"payload": {k: payload.get(k) for k in need}, "result": res})
    return res


@app.post("/gtt/cancel")
async def gtt_cancel(request: Request, payload: dict = Body(...),
                     token: str | None = Query(default=None)) -> dict:
    """Cancel a GTT rule (master-switch gated)."""
    _check_token(request, token)
    _trading_on()
    if not payload.get("id"):
        raise HTTPException(status_code=400, detail="GTT id required.")
    from .brokers import angel_scrip
    try:
        res = await asyncio.to_thread(angel_scrip.gtt_cancel, str(payload["id"]),
                                      str(payload.get("symboltoken") or ""),
                                      payload.get("exchange") or "NSE")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:200])
    return res


# --- Pro order pad: 5-level depth, live margin, basket orders -------------------
@app.get("/quote/{symboltoken}")
async def quote_depth(request: Request, symboltoken: str, exchange: str = "NFO",
                      token: str | None = Query(default=None)) -> dict:
    """5-level market depth + LTP for a token. Read-only."""
    _check_token(request, token)
    from .brokers import angel_scrip
    try:
        return await asyncio.to_thread(angel_scrip.quote_full, symboltoken, exchange)
    except Exception as exc:
        return {"error": str(exc)[:160]}


@app.get("/margin/rms")
async def margin_rms(request: Request, token: str | None = Query(default=None)) -> dict:
    """Live funds & margin (real F&O buying power). Read-only."""
    _check_token(request, token)
    from .brokers import angel_scrip
    try:
        return await asyncio.to_thread(angel_scrip.rms)
    except Exception as exc:
        return {"error": str(exc)[:160]}


@app.post("/margin/order")
async def margin_order(request: Request, payload: dict = Body(...),
                       token: str | None = Query(default=None)) -> dict:
    """Margin required for one or many legs (basket benefit included). Read-only."""
    _check_token(request, token)
    legs = payload.get("legs") or []
    if not legs:
        raise HTTPException(status_code=400, detail="No legs.")
    from .brokers import angel_scrip
    try:
        return await asyncio.to_thread(angel_scrip.order_margin, legs)
    except Exception as exc:
        return {"error": str(exc)[:160]}


@app.post("/basket/place")
async def basket_place(request: Request, payload: dict = Body(...),
                       token: str | None = Query(default=None)) -> dict:
    """Place a multi-leg basket — each leg through every guardrail + the master switch.
    Partial failures are reported per leg; nothing is placed unless trading is ON."""
    _check_token(request, token)
    legs = payload.get("legs") or []
    if not legs:
        raise HTTPException(status_code=400, detail="Basket has no legs.")
    from .execution import engine
    from .execution.guardrails import GuardrailError
    day = await _day_pnl()
    results = []
    for i, leg in enumerate(legs):
        try:
            o = _build_order(leg)
            res = await asyncio.to_thread(engine.place_now, o, day)
            results.append({"leg": i, "symbol": leg.get("symbol"), "ok": True, "result": res})
        except GuardrailError as exc:
            results.append({"leg": i, "symbol": leg.get("symbol"), "ok": False, "error": str(exc)})
        except Exception as exc:
            results.append({"leg": i, "symbol": leg.get("symbol"), "ok": False, "error": str(exc)[:200]})
    return {"placed": sum(1 for r in results if r["ok"]), "total": len(legs), "legs": results}


def main() -> None:
    import os
    import uvicorn

    host = os.environ.get("CFO_HOST", "0.0.0.0")
    # Railway injects PORT; fall back to CFO_PORT, then 8000 for local.
    port = int(os.environ.get("PORT", os.environ.get("CFO_PORT", "8000")))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
