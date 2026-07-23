"""Market Console — terminal-styled unified UI, wired to the real engines.

A ground-up reskin to the trading-terminal aesthetic (IBM Plex, square corners,
hairline borders, steel-blue accent) that surfaces everything ShareCFO already
computes: consolidated net worth + accounts, live indices + global cues, a sector
heatmap and movers from your own book, per-instrument charts, the income engine,
OI signals, and the guarded order flow. Built as deployable slices — this file
grows screen by screen. Served at '/', with the classic dashboard kept at '/classic'.
"""

TERMINAL_HTML = r"""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Market Console</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0b0e13">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Console">
<link rel="apple-touch-icon" href="/icon.svg"><link rel="icon" href="/icon.svg">
<script>try{var _t=new URLSearchParams(location.search).get('token');if(_t)localStorage.setItem('cfo_token',_t);}catch(e){}</script>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --canvas:#07090d;--bg:#0b0e13;--panel:#11151c;--text:#dde3ea;
  --n100:#151a22;--n200:#1d232d;--n300:#28303d;--n400:#3b475a;--n500:#75818f;--n600:#94a0af;--n700:#b6c0cc;--n900:#e9edf2;
  --acc:#3f8cde;--a100:#122238;--a300:#27476e;--a700:#82b4ec;--a900:#d3e4f8;
  --up:#2ebd85;--down:#f0544c;
  --fh:'IBM Plex Sans Condensed',sans-serif;--fb:'IBM Plex Sans',sans-serif;--fm:'IBM Plex Mono',monospace;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--canvas);color:var(--text);font-family:var(--fb);font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums;letter-spacing:-.2px}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--n500)}.sec{color:var(--n600)}
.lbl{font-family:var(--fh);text-transform:uppercase;letter-spacing:.12em;color:var(--n600);font-weight:600;font-size:11px}
.app{width:100%;max-width:520px;margin:0 auto;background:var(--bg);min-height:100vh;padding-bottom:118px}
/* Samsung Z Fold 7 + tablets: unfolded inner screen is wide + near-square, so the
   single 520px column wastes it. Widen and flow panels into two terminal columns;
   the cover (folded) screen stays single-column. */
@media (min-width:740px){
  .app,.tabs,.hdr{max-width:900px}
  .wrap{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}
  .wrap>.panel{margin-bottom:0}
  .span2{grid-column:1/-1}
  .nwbig{font-size:36px}
}
@media (min-width:1100px){
  .app,.tabs,.hdr{max-width:1180px}
  .wrap{grid-template-columns:1fr 1fr 1fr}
}
/* header */
.hdr{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--n300);
  display:flex;align-items:center;justify-content:space-between;padding:calc(env(safe-area-inset-top) + 10px) 16px 10px}
.hti{font-family:var(--fh);font-weight:600;letter-spacing:.14em;font-size:13px}
.hti b{color:var(--acc)}
.mkt{display:flex;align-items:center;gap:6px;font-family:var(--fh);letter-spacing:.1em;font-size:10px;color:var(--n500)}
.sd{width:7px;height:7px;background:var(--n500)}
.sd.open{background:var(--up);box-shadow:0 0 8px var(--up);animation:pulse 1.6s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.hnw{text-align:right}.hnw .v{font-family:var(--fm);font-weight:600;font-size:15px}.hnw .d{font-size:11px;font-family:var(--fm);font-weight:500}
.lgn{font-family:var(--fh);letter-spacing:.1em;font-size:10px;color:var(--a700);border:1px solid var(--a300);padding:3px 8px;margin-left:8px;text-transform:uppercase;white-space:nowrap}
.banner{display:none;background:rgba(240,84,76,.12);border-bottom:1px solid var(--down);color:var(--down);padding:11px 16px;font-family:var(--fh);letter-spacing:.05em;font-size:12px;text-transform:uppercase;font-weight:600}
.segb{background:var(--n100);border:1px solid var(--n400);color:var(--n600);font-family:var(--fh);letter-spacing:.05em;font-size:11px;padding:6px 12px;text-transform:uppercase;cursor:pointer;white-space:nowrap}
.segb.on{background:var(--acc);border-color:var(--acc);color:#fff}
/* ticker */
.tick{overflow:hidden;white-space:nowrap;border-bottom:1px solid var(--n300);background:var(--n100);padding:6px 0}
.tickrow{display:inline-block;padding-left:100%;animation:mar 40s linear infinite}
.ti{display:inline-block;margin:0 14px;font-size:12px}
.ti .n{font-family:var(--fh);letter-spacing:.08em;color:var(--n600);margin-right:6px}
.ti .v{font-family:var(--fm)}
@keyframes mar{0%{transform:translateX(0)}100%{transform:translateX(-100%)}}
/* panels */
.wrap{padding:14px 16px}
.panel{border:1px solid var(--n300);background:var(--panel);margin-bottom:12px}
.ph{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--n200)}
.ph .t{font-family:var(--fh);text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--n700);font-weight:600}
.pb{padding:13px 14px}
/* net worth hero */
.nwbig{font-family:var(--fm);font-size:34px;font-weight:600;letter-spacing:-.5px;margin-top:2px}
.nwrow{display:grid;grid-template-columns:1fr 1fr 1fr;border-top:1px solid var(--n200);margin-top:12px}
.nwrow>div{padding:10px 4px 2px;border-right:1px solid var(--n200)}.nwrow>div:last-child{border-right:0}
.nwrow .k{font-family:var(--fh);text-transform:uppercase;letter-spacing:.07em;font-size:9.5px;color:var(--n600)}
.nwrow .v{font-family:var(--fm);font-size:14px;font-weight:600;margin-top:4px}
/* rows */
.row{display:flex;align-items:center;gap:10px;padding:12px 13px;border-top:1px solid var(--n200);min-height:52px}
.row:first-child{border-top:0}
.rn{font-weight:500;font-size:14px}.rsub{font-size:11px;color:var(--n600);font-family:var(--fh);letter-spacing:.04em}
.rr{margin-left:auto;text-align:right}
.rr .p{font-family:var(--fm);font-weight:600}.rr .c{font-family:var(--fm);font-size:11px}
.bar{height:4px;background:var(--n200);margin-top:5px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--acc)}
.gtog{display:flex;gap:0;border:1px solid var(--n300);margin:0 13px 4px}
.gtog button{flex:1;background:0;border:0;color:var(--n500);font-family:var(--fh);text-transform:uppercase;letter-spacing:.08em;font-size:11px;font-weight:600;padding:9px 0;cursor:pointer}
.gtog button.on{background:var(--acc);color:#fff}
.grow{display:flex;align-items:center;gap:10px;padding:12px 13px;border-top:1px solid var(--n200);min-height:56px;cursor:pointer}
.grow:hover{background:var(--n100)}
.rchip{font-family:var(--fh);font-size:10px;letter-spacing:.05em;text-transform:uppercase;padding:1px 6px;border:1px solid;font-weight:600}
.rchip.dgr{color:var(--down);border-color:var(--down)}
.rchip.wch{color:var(--warn);border-color:var(--warn)}
.row.dngr{border-left:2px solid var(--down)}.row.wtch{border-left:2px solid var(--warn)}
.livedot{width:7px;height:7px;border-radius:50%;background:var(--up);display:inline-block;animation:lp 1.6s ease-in-out infinite}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.25}}
/* heatmap */
.heat{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--n200);border:1px solid var(--n200)}
.hc{background:var(--panel);padding:10px 9px;min-height:58px;display:flex;flex-direction:column;justify-content:space-between}
.hc .hn{font-family:var(--fh);text-transform:uppercase;letter-spacing:.05em;font-size:10.5px;color:var(--n700);font-weight:500}
.hc .hp{font-family:var(--fm);font-size:13px;font-weight:600}
/* two-col movers */
.two{display:grid;grid-template-columns:1fr 1fr}
.two>div{padding:10px 12px}.two>div:first-child{border-right:1px solid var(--n200)}
.mvh{font-family:var(--fh);text-transform:uppercase;letter-spacing:.1em;font-size:9.5px;color:var(--n500);margin-bottom:6px}
.mv{display:flex;justify-content:space-between;padding:4px 0;font-size:12px}
.mv .s{font-weight:500}.mv .c{font-family:var(--fm)}
/* tabs */
.tabs{position:fixed;left:0;right:0;bottom:0;z-index:20;max-width:520px;margin:0 auto;background:var(--panel);border-top:1px solid var(--n300);
  display:grid;grid-template-columns:repeat(6,1fr);padding-bottom:env(safe-area-inset-bottom)}
.tabs button{background:0;border:0;border-top:2px solid transparent;color:var(--n500);font-family:var(--fh);
  letter-spacing:.01em;font-size:9.5px;font-weight:600;text-transform:uppercase;padding:14px 1px 13px;cursor:pointer;min-height:50px;white-space:nowrap}
.tabs button.on{color:var(--a700);border-top-color:var(--acc)}
section{display:none}section.on{display:block}
.load{padding:26px;text-align:center;color:var(--n500);font-family:var(--fh);letter-spacing:.1em;font-size:11px;text-transform:uppercase}
.soon{padding:40px 20px;text-align:center;color:var(--n500)}
.soon .b{font-family:var(--fh);letter-spacing:.14em;text-transform:uppercase;font-size:13px;color:var(--n700)}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:var(--n400)}
a{color:var(--a700);text-decoration:none}
/* share-detail sheet (Screener + price/volume on tap) */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:30;opacity:0;pointer-events:none;transition:opacity .2s}
.scrim.on{opacity:1;pointer-events:auto}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:31;max-width:560px;margin:0 auto;background:var(--panel);border-top:1px solid var(--acc);
  transform:translateY(100%);transition:transform .25s;max-height:84vh;overflow-y:auto;padding:0 16px 26px}
.sheet.on{transform:translateY(0)}
.sgrab{width:40px;height:4px;background:var(--n400);margin:10px auto 12px}
.sh{display:flex;align-items:baseline;gap:10px;padding:2px 0 12px;border-bottom:1px solid var(--n200);position:sticky;top:0;background:var(--panel)}
.ssym{font-family:var(--fh);font-weight:600;font-size:21px;letter-spacing:.03em}
.fgrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--n200);border:1px solid var(--n200);margin-top:10px}
.fg{background:var(--panel);padding:10px 11px}
.fg .k{font-family:var(--fh);text-transform:uppercase;letter-spacing:.05em;font-size:9.5px;color:var(--n500)}
.fg .v{font-family:var(--fm);font-size:15px;font-weight:600;margin-top:4px}
.ssub{font-family:var(--fh);text-transform:uppercase;letter-spacing:.1em;font-size:11px;color:var(--n600);margin:16px 0 2px;font-weight:600}
.tpin{background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:10px;font-family:var(--fb);font-size:14px;width:100%}
</style></head><body>
<div id="gate" style="display:none;position:fixed;inset:0;z-index:9999;background:var(--canvas);flex-direction:column;align-items:center;justify-content:center;padding:24px">
  <div style="font-family:var(--fh);font-weight:600;letter-spacing:.14em;font-size:15px;margin-bottom:4px">MARKET<b style="color:var(--acc)">·</b>CONSOLE</div>
  <div class="lbl" style="margin-bottom:18px">enter password</div>
  <input id="gate-pw" type="password" inputmode="text" autocomplete="current-password" placeholder="Password"
    style="width:100%;max-width:300px;background:var(--panel);border:1px solid var(--n300);color:var(--text);font-family:var(--fb);font-size:16px;padding:13px 14px;text-align:center">
  <button class="btn" onclick="unlock()" style="width:100%;max-width:300px;margin-top:12px;background:var(--acc);color:#fff;border:0;font-family:var(--fh);letter-spacing:.06em;font-size:13px;padding:13px 0;text-transform:uppercase;cursor:pointer">Unlock</button>
  <div class="rsub" id="gate-msg" style="margin-top:10px;min-height:16px;color:var(--down)"></div>
</div>
<div class="app">
  <div class="hdr">
    <div><div class="hti">MARKET<b>·</b>CONSOLE</div>
      <div class="mkt"><span class="sd" id="sd"></span><span id="mstat">—</span></div></div>
    <div class="hnw"><div class="d" id="hday">—</div><div class="v" id="hnw" style="display:none"></div></div>
  </div>
  <div class="tick"><div class="tickrow" id="tickrow"><span class="ti muted">loading feed…</span></div></div>
  <a class="banner" id="banner" href="#"></a>

  <section id="s-settings"><div class="wrap">
    <div class="panel span2"><div class="pb">
      <div class="lbl">Total Wealth · demat + external</div>
      <div class="nwbig" id="tw-total">₹—</div>
      <div class="mono" id="tw-split" style="font-size:12px;margin-top:3px;color:var(--n600)">—</div>
    </div></div>
    <div class="panel span2"><div class="ph"><span class="t">Accounts &amp; login</span><span class="lbl" id="set-acc-n"></span></div><div id="set-accs"><div class="load">loading</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">External balances</span><span class="lbl" id="bal-usd"></span></div>
      <div id="bal-list"><div class="load">loading</div></div>
      <div class="pb" style="border-top:1px solid var(--n200);display:flex;flex-wrap:wrap;gap:7px;align-items:center">
        <input id="bal-label" placeholder="e.g. Binance" style="flex:1;min-width:110px">
        <select id="bal-bucket"><option>US Stocks</option><option>Crypto</option><option>Bank</option><option>Trading Cash</option><option>Other</option></select>
        <input id="bal-amt" type="number" inputmode="decimal" placeholder="amount" style="width:110px">
        <select id="bal-cur"><option>INR</option><option>USD</option></select>
        <button class="segb" style="padding:9px 14px" onclick="saveBal()">Add</button>
      </div></div>
    <div class="panel span2"><div class="ph"><span class="t">Screener data</span><span class="lbl" id="scr-stat">—</span></div>
      <div class="pb rsub" id="scr-detail" style="color:var(--n600)">checking…</div>
      <div class="pb" style="border-top:1px solid var(--n200);display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="file" id="scr-file" accept=".xlsx,.xls,.csv" style="flex:1;min-width:0;font-size:12px;color:var(--n500)">
        <button class="segb" style="padding:9px 16px" onclick="uploadScreener()">Upload</button>
      </div>
      <div class="pb rsub" style="border-top:1px solid var(--n200);color:var(--n500)">screener.in → your screen or watchlist → <b style="color:var(--n700)">Export to Excel</b> → pick it here. Powers Ideas, deep-analysis fundamentals (P/E vs industry, ROE, ROCE) and market-cap buckets.</div>
    </div>
    <div class="panel span2"><div class="ph"><span class="t">Data feeds</span></div><div class="pb" id="set-feeds"><div class="load">checking</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Trading</span></div><div class="pb" id="set-trade"><div class="sec" style="font-size:12px">Order execution is guarded (caps, allow-list, kill-switch). Master switch is set in the server env.</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Views</span></div><div class="pb" style="display:flex;flex-direction:column;gap:10px"><a id="set-status" href="#" class="lbl" style="color:var(--a700)">Open system status →</a><a id="set-classic" href="#" class="lbl" style="color:var(--a700)">Open classic dashboard →</a></div></div>
  </div></section>

  <section id="s-portfolio" class="on"><div class="wrap" id="markets-wrap">
    <div class="panel span2"><div class="ph"><span class="t">Sector map</span><span class="lbl" id="hday2">your book · today</span></div><div class="pb"><div class="heat" id="heat"></div>
      <div id="tw-home" onclick="twToggle()" style="margin-top:12px;padding-top:10px;border-top:1px solid var(--n200);display:flex;align-items:center;justify-content:space-between;cursor:pointer">
        <span class="lbl">Total Wealth <span class="rsub" style="text-transform:none">tap to reveal</span></span>
        <span class="mono" id="tw-home-v" style="font-weight:600">••••••</span></div>
    </div></div>
    <!-- net-worth figures kept out of the top view (privacy); values live in the Hub. Hidden stubs keep the refresh loop happy. -->
    <div style="display:none"><span id="nw"></span><span id="nwday"></span><span id="nwu"></span><span id="nwc"></span><span id="nwi"></span></div>
    <div class="panel"><div class="ph"><span class="t">Accounts</span><span class="lbl" id="acc-n"></span></div><div id="accs"><div class="load">loading</div></div></div>
    <div class="panel"><div class="ph"><span class="t">Movers</span><span class="lbl">today</span></div><div class="two"><div><div class="mvh">Gainers</div><div id="gain"></div></div><div><div class="mvh">Losers</div><div id="lose"></div></div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Holdings</span><span class="lbl" id="hold-n">tap for Screener</span></div><div id="hold-list"><div class="load">loading</div></div></div>
  </div></section>

  <section id="s-chart"><div class="wrap">
    <div class="panel span2"><div class="pb">
      <div style="display:flex;align-items:baseline;gap:10px"><span class="ssym" id="ch-sym" style="font-size:20px">NIFTY 50</span><span class="mono" id="ch-px" style="font-size:20px;margin-left:auto">—</span></div>
      <div id="ch-chips" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px"></div>
      <div style="display:flex;gap:6px;margin-top:10px" id="ch-range">
        <button class="segb on" data-r="66">3M</button><button class="segb" data-r="132">6M</button><button class="segb" data-r="252">1Y</button>
      </div>
      <canvas id="ch-canvas" width="900" height="360" style="width:100%;height:auto;margin-top:12px;display:block"></canvas>
      <div class="rsub" id="ch-lvl" style="margin-top:6px"></div>
    </div></div>
    <div class="panel span2"><div class="ph"><span class="t">F&amp;O edge</span><span class="lbl" id="ch-edge-exp"></span></div>
      <div class="pb"><div class="fgrid" id="ch-edge"></div><div class="rsub" id="ch-edge-note" style="margin-top:8px"></div></div>
    </div>
  </div></section>

  <section id="s-positions"><div class="wrap">
    <div class="panel span2"><div class="pb">
      <div style="display:flex;align-items:baseline;gap:8px"><span class="lbl">Live P&amp;L</span><span class="livedot" id="pos-live"></span><span class="lbl" id="pos-updated" style="margin-left:auto;text-transform:none;color:var(--n500)"></span></div>
      <div class="mono" id="pos-net" style="font-size:32px;font-weight:600;letter-spacing:-.5px;margin-top:2px">—</div>
      <div style="display:flex;gap:20px;margin-top:12px">
        <div><div class="lbl">Today</div><div class="mono" id="pos-day" style="font-size:17px;font-weight:600">—</div></div>
        <div><div class="lbl">Open MTM</div><div class="mono" id="pos-real" style="font-size:17px;font-weight:600">—</div></div>
        <div style="margin-left:auto;text-align:right"><div class="lbl">F&amp;O legs</div><div class="mono" id="pos-n" style="font-size:17px;font-weight:600">—</div></div>
      </div>
    </div></div>
    <div class="panel span2"><div class="ph"><span class="t">Live positions</span><span class="lbl">HDFC + Angel · OI/vol</span></div><div id="pos-list"><div class="load">loading positions</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Deep analysis</span><span class="lbl" id="deep-meta">fundamental · technical · news · macro</span></div>
      <div id="deep-list"><div class="pb"><button class="segb" style="padding:11px 16px" onclick="loadDeep(1)">Run deep analysis →</button>
        <div class="rsub" style="margin-top:8px">Fuses fundamentals, technicals, current news and market regime per F&amp;O underlying, and flags any that conflict with how you're positioned. Cached ~20 min.</div></div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Order book</span><span class="lbl" id="ob-meta">broker · live</span></div><div id="ob-list"><div class="load">—</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">GTT · resting orders</span><span class="lbl" id="gtt-meta">good till triggered</span></div><div id="gtt-list"><div class="load">—</div></div></div>
    <div class="panel span2" id="basket-panel" style="display:none"><div class="ph"><span class="t">Basket</span><span class="lbl" id="basket-meta"></span></div><div id="basket-list"></div>
      <div class="pb" style="display:flex;gap:8px;border-top:1px solid var(--n200)"><button class="segb" style="flex:1;padding:11px 0" onclick="placeBasket()">Place basket</button><button class="segb" style="flex:0 0 auto;padding:11px 16px" onclick="clearBasket()">Clear</button></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Reconcile · all accounts</span><span class="lbl" id="recon-meta">tap to run</span></div>
      <div id="recon-list"><div class="load">Cross-checks orders we sent vs the broker book, protective stops that landed, and open positions with no stop.</div></div>
      <div class="pb" style="border-top:1px solid var(--n200)"><button class="segb" style="flex:1;padding:11px 0" onclick="loadRecon()">⚖ Run reconciliation</button></div></div>
  </div></section>

  <section id="s-ideas"><div class="wrap">
    <div style="display:flex;gap:6px;margin-bottom:12px;grid-column:1/-1"><button class="segb on" id="ist-ideas" onclick="istTab('ideas')" style="flex:1;padding:10px 0">Ideas</button><button class="segb" id="ist-calls" onclick="istTab('calls')" style="flex:1;padding:10px 0">Calls</button><button class="segb" id="ist-income" onclick="istTab('income')" style="flex:1;padding:10px 0">Income</button></div>
    <div class="panel span2" id="ideas-panel"><div class="ph"><span class="t">High-conviction ideas</span><span class="lbl">fundamental + technical + backtest</span></div><div id="ideas-list"><div class="load">scanning for setups</div></div></div>
    <div class="panel span2" id="calls-panel" style="display:none"><div class="ph"><span class="t">Advisor calls</span><span class="lbl" id="calls-meta">Bantu Mausaji · Anil Singhvi</span></div>
      <div style="padding:12px 14px;border-bottom:1px solid var(--n200)">
        <div class="ssub">Log a call</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
          <select id="tp-src" class="tpin"><option>Bantu Mausaji</option><option>Anil Singhvi</option></select>
          <input id="tp-sym" class="tpin" placeholder="Symbol e.g. RELIANCE">
          <select id="tp-kind" class="tpin" onchange="tpKind()"><option value="trade">Trade (buy/target/stop)</option><option value="invest">Invest (accumulate)</option></select>
          <input id="tp-buy" class="tpin" inputmode="decimal" placeholder="Buy price">
          <input id="tp-tgt" class="tpin" inputmode="decimal" placeholder="Target / sell">
          <input id="tp-stop" class="tpin" inputmode="decimal" placeholder="Stop (auto if blank)">
        </div>
        <input id="tp-note" class="tpin" style="width:100%;margin-top:6px" placeholder="note (optional)">
        <button class="segb" style="width:100%;margin-top:8px;padding:11px 0" onclick="addTip()">＋ Add call</button>
        <div id="tp-msg" class="rsub" style="margin-top:6px;min-height:14px"></div>
      </div>
      <div id="calls-list"><div class="load">No calls logged yet. Add one above.</div></div></div>
    <div class="panel span2" id="income-panel" style="display:none"><div class="ph"><span class="t">Income engine</span><span class="lbl" id="inc-sum">covered calls + cash puts</span></div><div id="income-list"><div class="load">—</div></div></div>
  </div></section>

  <section id="s-news"><div class="wrap">
    <div class="panel span2"><div class="ph"><span class="t">News on your holdings</span><span class="lbl">Google News</span></div><div id="news-list"><div class="load">loading news</div></div></div>
  </div></section>
</div>

<div class="scrim" id="scrim" onclick="closeShare()"></div>
<div class="sheet" id="sheet"><div class="sgrab"></div>
  <div class="sh"><span class="ssym" id="sh-sym">—</span><span class="mono" id="sh-px" style="margin-left:auto;font-size:16px"></span></div>
  <div id="sh-body"><div class="load">loading</div></div>
</div>

<div class="scrim" id="tscrim" onclick="closeTicket()"></div>
<div class="sheet" id="tsheet"><div class="sgrab"></div>
  <div class="sh"><span class="ssym" id="tk-sym">—</span><span class="mono muted" id="tk-ltp" style="margin-left:auto;font-size:15px"></span></div>
  <div style="display:flex;gap:6px;margin-top:12px"><button class="segb tk-side on" data-s="BUY" onclick="tkSide('BUY')" style="flex:1;padding:12px 0;font-size:13px">BUY</button><button class="segb tk-side" data-s="SELL" onclick="tkSide('SELL')" style="flex:1;padding:12px 0;font-size:13px">SELL</button></div>
  <div class="ssub">Segment</div><div style="display:flex;gap:6px" id="tk-segs"><button class="segb tk-seg on" onclick="tkSeg('CASH',this)">CASH</button><button class="segb tk-seg" onclick="tkSeg('FUT',this)">FUT</button></div>
  <div class="rsub" id="tk-contract" style="margin-top:6px;color:var(--n500)"></div>
  <div id="tk-depth" class="mono" style="margin-top:8px;font-size:11.5px;display:none"></div>
  <div class="ssub">Account</div><select id="tk-acct" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fh);letter-spacing:.03em"></select>
  <div class="ssub">Product</div><div style="display:flex;gap:6px" id="tk-prods"><button class="segb tk-prod on" onclick="tkProd(this)">CNC</button><button class="segb tk-prod" onclick="tkProd(this)">MIS</button></div>
  <div class="ssub">Order type</div><div style="display:flex;gap:6px" id="tk-ots"><button class="segb tk-ot on" onclick="tkOt('MARKET',this)">MKT</button><button class="segb tk-ot" onclick="tkOt('LIMIT',this)">LMT</button><button class="segb tk-ot" onclick="tkOt('SL',this)">SL</button><button class="segb tk-ot" onclick="tkOt('SL-M',this)">SL-M</button></div>
  <div id="tk-price-wrap" style="display:none"><div class="ssub">Limit price</div><input id="tk-price" inputmode="decimal" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fm);font-size:15px"></div>
  <div id="tk-trig-wrap" style="display:none"><div class="ssub">Trigger price</div><input id="tk-trig" inputmode="decimal" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fm);font-size:15px"></div>
  <div class="ssub" id="tk-qtylbl">Quantity (shares)</div>
  <div style="display:flex;align-items:center;gap:12px"><button class="segb" onclick="tkQty(-1)" style="width:48px;padding:12px 0;font-size:16px">−</button><span class="mono" id="tk-qty" style="font-size:22px;min-width:64px;text-align:center">1</span><button class="segb" onclick="tkQty(1)" style="width:48px;padding:12px 0;font-size:16px">+</button><span class="rsub mono" id="tk-val" style="margin-left:auto"></span></div>
  <div class="rsub mono" id="tk-funds" style="margin-top:7px;color:var(--n500)"></div>
  <div class="ssub">Stop-loss (required)</div><input id="tk-stop" inputmode="decimal" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fm);font-size:15px">
  <div id="tk-guard" class="fg" style="margin-top:14px;border:1px solid var(--n300);display:none"></div>
  <div style="display:flex;gap:8px;margin-top:14px">
    <button class="segb" id="tk-go" onclick="tkReview()" style="flex:1;padding:14px 0;font-size:13px">Review order</button>
    <button class="segb" onclick="setGtt()" style="flex:0 0 auto;padding:14px 16px;font-size:13px" title="Good Till Triggered — a resting order at the broker">Set GTT</button>
    <button class="segb" onclick="addToBasket()" style="flex:0 0 auto;padding:14px 16px;font-size:13px" title="Add as a basket leg">+Basket</button>
  </div>
  <div class="rsub" style="margin-top:8px;color:var(--n500)">Guarded: propose → confirm. Nothing places unless the master switch is on. GTT rests at the broker up to a year.</div>
</div>

<div class="tabs" id="tabs">
  <button data-t="settings">Settings</button>
  <button data-t="portfolio" class="on">Portfolio</button>
  <button data-t="positions">Positions</button>
  <button data-t="ideas">Ideas</button>
  <button data-t="chart">Chart</button>
  <button data-t="news">News</button>
</div>

<script>
let token=new URLSearchParams(location.search).get('token')||'';
try{token=token||localStorage.getItem('cfo_token')||'';if(token)localStorage.setItem('cfo_token',token);}catch(e){}
let Q='token='+encodeURIComponent(token);
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));}
const _fails={};function _failbar(){let b=document.getElementById('failbar');if(!b){b=document.createElement('div');b.id='failbar';b.style.cssText='position:sticky;top:0;z-index:99;background:#3a1113;color:#f0a0a0;font:500 12px IBM Plex Mono,monospace;padding:6px 12px;border-bottom:1px solid #7a2a2a;display:none';document.body.prepend(b);}const k=Object.keys(_fails);if(k.length){b.style.display='block';b.textContent='DATA FEED ERROR: '+k.map(u=>u.split('?')[0]+' ('+_fails[u]+')').join(' · ')+' — retrying automatically';}else{b.style.display='none';}return b;}
async function j(u){const c=new AbortController();const to=setTimeout(()=>c.abort(),30000);
  try{const r=await fetch(u,{signal:c.signal});clearTimeout(to);if(!r.ok){if(r.status===401)reauth();_fails[u]='HTTP '+r.status;_failbar();return {ok:false,d:{},s:r.status};}delete _fails[u];_failbar();return {ok:true,d:await r.json()};}
  catch(e){clearTimeout(to);_fails[u]=(e&&e.name==='AbortError')?'timeout':String(e&&e.message||'network');_failbar();return {ok:false,d:{}};}}
const inr=n=>{if(n==null||isNaN(n))return '₹—';const a=Math.abs(n),s=n<0?'-':'';if(a>=1e7)return s+'₹'+(a/1e7).toFixed(2)+'Cr';if(a>=1e5)return s+'₹'+(a/1e5).toFixed(2)+'L';return s+'₹'+Math.round(a).toLocaleString('en-IN');};
const sp=p=>(p>=0?'+':'')+(p==null||isNaN(p)?'—':p.toFixed(2)+'%');
const cl=v=>v>=0?'up':'down';
const clean=t=>(t||'').toUpperCase().replace(/-(EQ|BE|BZ|BL|SM|ST|IQ)$/,'').split('-')[0];

/* market status from IST (Asia/Kolkata), never device tz */
let MKT_OPEN=false;
function mktStatus(){
  const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
  const g=t=>p.find(x=>x.type===t).value;const wd=g('weekday'),hm=+g('hour')*60+ +g('minute');
  const open=['Mon','Tue','Wed','Thu','Fri'].includes(wd)&&hm>=555&&hm<=930;
  MKT_OPEN=open;
  document.getElementById('sd').className='sd'+(open?' open':'');
  document.getElementById('mstat').textContent=open?'MARKET OPEN':'MARKET CLOSED';
  return open;
}

async function loadTicker(){
  const [ix,gl]=await Promise.all([j('/market/indices?'+Q),j('/market/global?'+Q)]);
  let items=[];
  (ix.ok&&ix.d.indices||[]).forEach(x=>items.push([x.name,x.last,x.change_pct]));
  (gl.ok&&gl.d.markets||[]).forEach(x=>items.push([x.name,x.last,x.change_pct]));
  if(!items.length){document.getElementById('tickrow').innerHTML='<span class="ti muted">index feed unavailable</span>';return;}
  const one=items.map(([n,v,c])=>'<span class="ti"><span class="n">'+n+'</span><span class="v '+(c==null?'':cl(c))+'">'+(v!=null?v.toLocaleString('en-IN'):'—')+' '+(c==null?'':sp(c))+'</span></span>').join('');
  document.getElementById('tickrow').innerHTML=one+one;
}

let PORT=null;
async function loadHome(){
  const r=await j('/portfolio?'+Q);if(!r.ok){document.getElementById('accs').innerHTML='<div class="load">token?</div>';return;}
  PORT=r.d;const p=r.d;
  document.getElementById('nw').textContent=inr(p.net_worth);
  document.getElementById('hnw').textContent=inr(p.net_worth);
  const dc=p.day_change>=0;
  document.getElementById('nwday').innerHTML='<span class="'+cl(p.day_change)+'">'+(dc?'▲':'▼')+' '+inr(Math.abs(p.day_change))+'  '+sp((p.day_change_pct||0)*100)+'</span>';
  const hd=document.getElementById('hday');hd.className='d '+cl(p.day_change);hd.textContent=sp((p.day_change_pct||0)*100);
  const bh=p.book_health||{},bn=document.getElementById('banner');
  if((bh.degraded||0)>0){const names=(bh.degraded_accounts||[]).map(x=>x.creds_key).join(', ');
    bn.style.display='block';bn.href='/login?'+Q;bn.textContent='⚠ '+names+' logged out — net worth partial · tap to log in';}
  else bn.style.display='none';
  document.getElementById('nwu').innerHTML='<span class="'+cl(p.unrealised_pnl)+'">'+inr(p.unrealised_pnl)+'</span>';
  document.getElementById('nwc').textContent=inr(p.cash);
  document.getElementById('nwi').textContent=inr(p.invested_value);
  renderAccounts(p);renderHeat(p);renderMovers(p);renderHoldings(p);loadWealthHome();
}
/* Total Wealth on the home: masked by default (tap to reveal), so nothing shows on a glance/screen-share. */
let TW_VAL=null,TW_SHOW=false;
async function loadWealthHome(){const r=await j('/wealth?'+Q);if(r.ok)TW_VAL=r.d.total_wealth;renderTW();}
function renderTW(){const e=document.getElementById('tw-home-v');if(!e)return;e.textContent=(TW_SHOW&&TW_VAL!=null)?inr(TW_VAL):'••••••';}
function twToggle(){TW_SHOW=!TW_SHOW;renderTW();}
function acctVal(a){return (a.holdings||[]).reduce((s,x)=>s+(x.market_value||0),0);}
function renderAccounts(p){
  const accs=(p.accounts||[]).map(a=>({a,v:acctVal(a),ok:a.ok!==false&&a.status!=='degraded'}));
  const mx=Math.max(1,...accs.map(x=>x.v)),nw=p.net_worth||1;
  document.getElementById('acc-n').textContent=accs.length+' linked';
  document.getElementById('accs').innerHTML=accs.map(x=>{const a=x.a,lbl=a.label||a.creds_key;
    return '<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+lbl+' <span class="rsub">'+a.creds_key+(x.ok?'':' · off')+'</span></div>'
      +'<div class="bar"><i style="width:'+(x.v/mx*100).toFixed(0)+'%;background:'+(x.ok?'var(--acc)':'var(--down)')+'"></i></div></div>'
      +'<div class="rr"><div class="p">'+inr(x.v)+'</div><div class="c muted">'+(x.v/nw*100).toFixed(0)+'%</div></div></div>';}).join('');
}
function sectorMap(p){const m={};(p.accounts||[]).forEach(a=>(a.holdings||[]).forEach(h=>{
  const s=(h.sector||'UNKNOWN').toUpperCase();const o=m[s]||(m[s]={v:0,d:0});o.v+=h.market_value||0;o.d+=h.day_change||0;}));return m;}
function heatColor(pct){const cap=1.8,f=Math.max(-1,Math.min(1,pct/cap)),a=Math.abs(f)*0.38;
  const c=f>=0?'46,189,133':'240,84,76';return 'linear-gradient(0deg,rgba('+c+','+a.toFixed(2)+'),rgba('+c+','+a.toFixed(2)+')),var(--panel)';}
function renderHeat(p){
  // Prefer the grouped-by-sector data (themed + drillable); fall back to a quick client map.
  if(GROUPED&&GROUPED.by_sector&&GROUPED.by_sector.length){
    const arr=GROUPED.by_sector.filter(g=>g.value>=5000).slice(0,12);
    document.getElementById('heat').innerHTML=arr.map(g=>'<div class="hc" style="cursor:pointer;background:'+heatColor(g.day_pct)+'" onclick="drillSector(\''+encodeURIComponent(g.name)+'\')"><div class="hn">'+g.name+'</div><div class="hp '+cl(g.day_pct)+'">'+sp(g.day_pct)+'</div></div>').join('')
      ||'<div class="hc"><div class="hn muted">no sectors</div></div>';
    return;
  }
  const m=sectorMap(p);
  const arr=Object.entries(m).map(([s,o])=>{const prev=o.v-o.d;return {s,pct:prev?o.d/prev*100:0,v:o.v};})
    .filter(x=>x.v>=5000).sort((a,b)=>b.v-a.v).slice(0,12);
  document.getElementById('heat').innerHTML=arr.map(x=>'<div class="hc" style="background:'+heatColor(x.pct)+'"><div class="hn">'+x.s+'</div><div class="hp '+cl(x.pct)+'">'+sp(x.pct)+'</div></div>').join('')
    ||'<div class="hc"><div class="hn muted">no sectors</div></div>';
}
function allHoldings(p){const m={};(p.accounts||[]).forEach(a=>{const l=a.label||a.creds_key;(a.holdings||[]).forEach(h=>{
  const s=clean(h.ticker);const o=m[s]||(m[s]={s,mv:0,d:0,acc:{}});o.mv+=h.market_value||0;o.d+=h.day_change||0;o.acc[l]=1;});});
  return Object.values(m).map(o=>{o.hold=Object.keys(o.acc)[0]||'';const prev=o.mv-o.d;o.pct=prev?o.d/prev*100:0;return o;});}
function renderMovers(p){
  let all=allHoldings(p).filter(x=>Math.abs(x.mv)>=5000).sort((a,b)=>b.d-a.d);
  const g=all.filter(x=>x.d>0).slice(0,5),l=all.filter(x=>x.d<0).slice(-5).reverse();
  const row=x=>'<div class="mv" onclick="openShare(\''+x.s+'\')" style="cursor:pointer"><span class="s">'+x.s+'</span><span class="c '+cl(x.d)+'">'+sp(x.pct)+'</span></div>';
  document.getElementById('gain').innerHTML=g.map(row).join('')||'<div class="mv muted">—</div>';
  document.getElementById('lose').innerHTML=l.map(row).join('')||'<div class="mv muted">—</div>';
}

const kfmt=n=>{if(n==null)return '—';const a=Math.abs(n);if(a>=1e7)return (n/1e7).toFixed(2)+'Cr';if(a>=1e5)return (n/1e5).toFixed(2)+'L';if(a>=1e3)return (n/1e3).toFixed(1)+'k';return ''+n;};
let posLoaded=0;
async function loadPositions(){
  const box=document.getElementById('pos-list');const r=await j('/positions/live?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">could not load</div>';return;}
  const d=r.d,ps=(d.positions||[]);
  const net=d.realized_pnl||0;
  document.getElementById('pos-net').innerHTML='<span class="'+cl(net)+'">'+(net>=0?'+':'')+inr(net)+'</span>';
  document.getElementById('pos-day').innerHTML='<span class="'+cl(d.day_pnl)+'">'+inr(d.day_pnl)+'</span>';
  document.getElementById('pos-real').innerHTML='<span class="'+cl(d.realized_pnl)+'">'+inr(d.realized_pnl)+'</span>';
  document.getElementById('pos-n').innerHTML=(d.fno_count||0)+(d.at_risk?' · <span class="down">'+d.at_risk+' at risk</span>':'');
  try{const dot=document.getElementById('pos-live');if(dot)dot.style.display=MKT_OPEN?'inline-block':'none';
    const t=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date());
    const stream=d.feed==='websocket';
    document.getElementById('pos-updated').innerHTML=(!MKT_OPEN?'at close · '+t:(stream?'<span class="up">● streaming live</span> · '+t:'updated '+t));}catch(e){}
  if(!ps.length){box.innerHTML='<div class="load">No open positions in HDFC1 / HDFC2. F&amp;O legs appear here live.</div>';return;}
  box.innerHTML=ps.map(p=>{
    const mtm=p.pnl||0,tag=p.product||'',ch=p.change_pct;
    const danger=p.risk==='danger',watch=p.risk==='watch';
    const bu=p.buildup||'';
    const buCls=(bu==='Long buildup'||bu==='Short covering')?'up':(bu==='Short buildup'||bu==='Long unwinding')?'down':'muted';
    const oiArrow=p.oi_change>0?'▲':(p.oi_change<0?'▼':'');
    const meta=[];
    if(p.oi!=null)meta.push('OI '+kfmt(p.oi)+(p.oi_change_pct?(' <span class="'+(p.oi_change>0?'up':'down')+'">'+oiArrow+Math.abs(p.oi_change_pct)+'%</span>'):''));
    if(p.volume!=null)meta.push('Vol '+kfmt(p.volume));
    if(ch!=null)meta.push('Px <span class="'+cl(ch)+'">'+sp(ch)+'</span>');
    const riskChip=danger?'<span class="rchip dgr">● risk</span>':(watch?'<span class="rchip wch">● watch</span>':'');
    const suspChip=p.avg_suspect?'<span class="rchip wch">⚠ avg?</span>':(p.avg_reconstructed?'<span class="rsub" style="color:var(--n500);border:1px solid var(--n400);padding:0 4px" title="cost basis reconstructed from broker P&L">≈ avg</span>':'');
    return '<div class="row'+(danger?' dngr':(watch?' wtch':''))+'" onclick="openShare(\''+(p.underlying||'')+'\')" style="cursor:pointer;flex-direction:column;align-items:stretch;gap:5px">'
      +'<div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap"><span class="rn">'+p.label+'</span>'
      +'<span class="rsub" style="border:1px solid var(--n400);padding:0 4px">'+tag+'</span>'
      +(bu?'<span class="rsub '+buCls+'" style="border:1px solid var(--n400);padding:0 4px">'+bu+'</span>':'')
      +riskChip+suspChip+'<span class="p '+cl(mtm)+'" style="margin-left:auto;font-family:var(--fm);font-weight:600">'+(mtm>=0?'+':'')+inr(mtm)+(p.pnl_pct!=null?' <span style="font-size:11px">('+(p.pnl_pct>=0?'+':'')+p.pnl_pct+'%)</span>':'')+'</span></div>'
      +'<div class="rsub">Qty '+p.quantity+' · '+(p.avg_reconstructed?'≈':'')+'Avg '+(p.average_price||0).toFixed(1)+' · LTP '+(p.last_price||0).toFixed(1)+' · '+p.holder+'</div>'
      +(meta.length?'<div class="rsub mono" style="color:var(--n600)">'+meta.join('  ·  ')+'</div>':'')
      +(p.risk_why?'<div class="rsub" style="color:'+(danger?'var(--down)':'var(--warn)')+'">'+p.risk_why+'</div>':'')
      +(p.note_flag?'<div class="rsub" style="color:var(--warn)">⚠ '+p.note_flag+'</div>':'')
      +'</div>';
  }).join('');
}
/* ---- deep analysis per F&O underlying (fundamental+technical+news+macro) ---- */
async function loadDeep(refresh,ai){
  const box=document.getElementById('deep-list');
  box.innerHTML='<div class="load">analysing your F&amp;O book — fundamentals, charts, news, macro'+(ai?', AI narrative':'')+'…</div>';
  const r=await j('/positions/deep?'+(refresh?'refresh=1&':'')+(ai?'narrate=1&':'')+Q);
  if(!r.ok){box.innerHTML='<div class="pb"><button class="segb" style="padding:11px 16px" onclick="loadDeep(1)">Retry →</button> <span class="rsub">'+((r.d&&r.d.detail)||'could not run')+'</span></div>';return;}
  const reps=r.d.reports||[];
  document.getElementById('deep-meta').innerHTML='regime '+(r.d.regime||'—')+(r.d.conflicts?' · <span class="down">'+r.d.conflicts+' conflict'+(r.d.conflicts>1?'s':'')+'</span>':'');
  if(!reps.length){box.innerHTML='<div class="load">'+(r.d.note||'No F&amp;O positions to analyse.')+'</div>';return;}
  const aiNote=(ai&&!reps.some(x=>x.narrative))?'<div class="rsub" style="padding:0 14px 6px;color:var(--warn)">AI narrative needs ANTHROPIC_API_KEY set on the server — showing the structured read.</div>':'';
  box.innerHTML=reps.map(deepCard).join('')+aiNote
    +'<div class="pb" style="display:flex;gap:8px"><button class="segb" style="padding:9px 14px" onclick="loadDeep(1)">↻ Refresh</button>'
    +'<button class="segb" style="padding:9px 14px" onclick="loadDeep(1,1)">✨ AI narrative</button></div>';
}
function stChip(s){const c=s==='bullish'?'up':(s==='bearish'?'down':'muted');return '<span class="'+c+'" style="font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.06em">'+s+'</span>';}
function deepFac(arr,color,mk){return (arr||[]).map(t=>'<div class="rsub" style="color:'+color+';margin-top:2px">'+mk+' '+t+'</div>').join('');}
function deepCard(x){
  const a=x.alignment;
  const alignChip=a==='conflicts'?'<span class="rchip dgr">⚠ conflicts with your '+x.position_bias+'</span>'
    :(a==='supports'?'<span class="rchip" style="color:var(--up);border-color:var(--up)">supports your '+x.position_bias+'</span>':'');
  const px=x.price||{},t=x.technical||{},f=x.fundamental||{},m=x.macro||{};
  const news=(x.news||[]).slice(0,3).map(n=>'<a class="rsub" href="'+n.link+'" target="_blank" style="display:block;color:var(--a700);margin-top:3px">• '+n.title+(n.when?' <span class="muted">· '+n.when+'</span>':'')+'</a>').join('');
  return '<div style="padding:13px 14px;border-top:1px solid var(--n200)">'
    +'<div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap"><span class="rn" style="font-size:15px">'+x.symbol+'</span>'
    +stChip(x.stance)+alignChip
    +'<span class="mono" style="margin-left:auto">'+(px.last!=null?px.last:'')+(px.day_change_pct!=null?' <span class="'+cl(px.day_change_pct)+'">'+sp(px.day_change_pct)+'</span>':'')+'</span></div>'
    +'<div class="rsub" style="margin-top:4px;color:var(--n600)">'+(x.sector||'')+' · composite score '+x.score+'</div>'
    +(x.narrative?'<div style="margin-top:8px;padding:9px 11px;border-left:2px solid var(--acc);background:var(--n100);font-size:13px;line-height:1.5">'+x.narrative+'</div>':'')
    +deepFac(x.bull,'var(--up)','✓')+deepFac(x.bear,'var(--down)','✗')
    +'<div class="rsub" style="margin-top:8px;color:var(--n500)">Technical: '+(t.verdict||'—')+' · RSI '+(t.rsi14!=null?t.rsi14:'—')+(t.support?' · S '+t.support:'')+(t.resistance?' / R '+t.resistance:'')+'</div>'
    +'<div class="rsub" style="color:var(--n500)">Fundamental: '+(f.have_data?f.verdict:'no Screener data — upload export')+' · Macro: '+(m.regime||'—')+'</div>'
    +(news?'<div style="margin-top:8px"><div class="rsub" style="color:var(--n500);text-transform:uppercase;letter-spacing:.06em">News</div>'+news+'</div>':'')
    +'</div>';
}
/* ---- share detail: Screener Premium + price/volume on tap ---- */
async function openShare(sym){
  if(!sym)return;sym=(sym+'').toUpperCase();
  document.getElementById('sh-sym').textContent=sym;
  document.getElementById('sh-px').textContent='';
  document.getElementById('sh-body').innerHTML='<div class="load">loading '+sym+'</div>';
  document.getElementById('scrim').classList.add('on');document.getElementById('sheet').classList.add('on');
  const [f,c]=await Promise.all([j('/fundamentals/'+encodeURIComponent(sym)+'?'+Q),j('/chart/'+encodeURIComponent(sym)+'?'+Q)]);
  const ff=(f.ok&&f.d.fields)||{},conf=(f.ok&&f.d.confidence)||'',d=c.ok?c.d:{};
  if(d.last!=null)document.getElementById('sh-px').innerHTML='<span class="'+cl(d.day_change_pct)+'">'+d.last+'  '+sp(d.day_change_pct)+'</span>';
  const g=(k,v,suf)=>'<div class="fg"><div class="k">'+k+'</div><div class="v">'+(v!=null&&v!==''?v+(suf||''):'—')+'</div></div>';
  const mcf=c=>c==null?'—':(c>=100000?'₹'+(c/100000).toFixed(2)+'L Cr':'₹'+Math.round(c).toLocaleString('en-IN')+' Cr');
  const pos=POSMAP[sym];
  let h='';
  if(pos){const pnl=pos.unrealised>=0,dp=pos.day_change>=0;
    h+='<div class="ssub">Your position</div>'
      +'<div class="fgrid">'+g('Qty',pos.qty)+g('Avg',pos.avg_price)+g('LTP',pos.last_price)+'</div>'
      +'<div class="fgrid">'+g('Invested',inr(pos.invested))+g('Value',inr(pos.value))+g('Weight',pos.weight,'%')+'</div>'
      +'<div class="fgrid" style="grid-template-columns:1fr 1fr">'
      +'<div class="fg"><div class="k">Unrealised P&L</div><div class="v '+(pnl?'up':'down')+'">'+(pnl?'+':'')+inr(pos.unrealised)+' ('+(pnl?'+':'')+pos.unrealised_pct+'%)</div></div>'
      +'<div class="fg"><div class="k">Day P&L</div><div class="v '+cl(pos.day_pct)+'">'+(dp?'+':'')+inr(pos.day_change)+' ('+sp(pos.day_pct)+')</div></div></div>'
      +'<div class="fgrid" style="grid-template-columns:1fr 1fr">'+g('Cap',pos.cap)+g('Sector',pos.sector)+'</div>'
      +(pos.holders&&pos.holders.length?'<div class="rsub" style="margin-top:6px">Held in: '+pos.holders.join(', ')+'</div>':'');}
  const hasScr=Object.keys(ff).length>0;
  const peCmp=(ff.pe!=null&&ff.industry_pe!=null)?(ff.pe<ff.industry_pe?'up':'down'):'';
  h+='<div class="ssub">Screener fundamentals'+(hasScr?' · '+conf+' confidence':'')+'</div>';
  if(hasScr){
    h+='<div class="fgrid">'
      +'<div class="fg"><div class="k">P/E · Ind</div><div class="v '+peCmp+'">'+(ff.pe!=null?ff.pe:'—')+' · '+(ff.industry_pe!=null?ff.industry_pe:'—')+'</div></div>'
      +g('P/B',ff.pb)+g('ROE',ff.roe,'%')+g('ROCE',ff.roce,'%')+g('D/E',ff.de)
      +'<div class="fg"><div class="k">Mkt Cap</div><div class="v">'+mcf(pos&&pos.market_cap!=null?pos.market_cap:ff.market_cap)+'</div></div>'+'</div>'
      +'<div class="fgrid">'+g('Promoter',ff.promoter_holding,'%')+g('Pledge',ff.pledge,'%')+g('Div yld',ff.dividend_yield,'%')+'</div>'
      +(peCmp?'<div class="rsub" style="margin-top:6px">P/E '+(peCmp==='up'?'below':'above')+' industry median — '+(peCmp==='up'?'cheaper vs peers':'richer vs peers')+'.</div>':'');
  }
  else h+='<div class="fg" style="border:1px solid var(--n300)"><div class="k" style="color:var(--down)">not in Screener export</div><div class="rsub" style="margin-top:4px">Upload your Screener Premium sheet to see P/E vs industry, ROE, ROCE, D/E, pledge…</div></div>';
  h+='<div class="ssub">Price / volume action</div><div class="fgrid">'
    +g('Day range',(d.day_low!=null?d.day_low+'–'+d.day_high:null))+g('52-wk',(d.wk52_low!=null?d.wk52_low+'–'+d.wk52_high:null))+g('From 52wH',d.from_52w_high_pct,'%')
    +g('Volume',d.vol_x,'×')+g('RSI 14',d.rsi14)+g('Trend',(d.above_200dma==null?null:(d.above_200dma?'above 200D':'below 200D')))+'</div>';
  const lv=d.levels||{};
  if(lv.support||lv.resistance)h+='<div class="ssub">Levels</div><div class="fgrid">'+g('Support',lv.support)+g('Pivot',lv.pivot)+g('Resistance',lv.resistance)+'</div>';
  h+='<div style="display:flex;gap:8px;margin-top:14px">'
    +'<button class="segb" style="flex:1;padding:12px 0;font-size:13px;color:var(--up);border-color:#1f5c46" onclick="openTicket(\''+sym+'\','+(d.last||0)+',\'BUY\')">Buy</button>'
    +'<button class="segb" style="flex:1;padding:12px 0;font-size:13px;color:var(--down);border-color:#5c2b2b" onclick="openTicket(\''+sym+'\','+(d.last||0)+',\'SELL\')">Sell</button>'
    +'<button class="segb" style="flex:1;padding:12px 0;font-size:13px" onclick="goChart(\''+sym+'\')">Chart</button></div>';
  document.getElementById('sh-body').innerHTML=h;
}
function closeShare(){document.getElementById('scrim').classList.remove('on');document.getElementById('sheet').classList.remove('on');}
/* ---- order ticket (guarded: propose -> confirm) ---- */
let TK={sym:'',ltp:0,side:'BUY',seg:'CASH',exch:'NSE',product:'CNC',ot:'MARKET',qty:1,lot:1,fut:null,pid:null,code:null};
function fillTkAccts(sel){const s=document.getElementById('tk-acct');if(!s)return;const accs=(PORT&&PORT.accounts)||[];
  s.innerHTML=accs.map(a=>'<option value="'+a.creds_key+'">'+(a.label||a.creds_key)+' · '+a.creds_key+'</option>').join('')||'<option value="ANGEL1">ANGEL1</option>';
  if(sel)s.value=sel;}
function openTicket(sym,ltp,side,acct){closeShare();TK={sym:(sym||'').toUpperCase(),ltp:+ltp||0,side:side||'BUY',seg:'CASH',exch:'NSE',product:'CNC',ot:'MARKET',qty:1,lot:1,fut:null,pid:null,code:null};
  fillTkAccts(acct);
  document.getElementById('tk-sym').textContent=TK.sym;document.getElementById('tk-ltp').textContent=TK.ltp?('LTP '+TK.ltp):'';
  document.getElementById('tk-price').value=TK.ltp||'';document.getElementById('tk-qty').textContent='1';
  document.getElementById('tk-stop').value=TK.ltp?(TK.ltp*0.95).toFixed(2):'';
  document.getElementById('tk-contract').textContent='';document.getElementById('tk-qtylbl').textContent='Quantity (shares)';
  document.querySelectorAll('#tsheet .tk-side').forEach(b=>b.classList.toggle('on',b.dataset.s===TK.side));
  document.querySelectorAll('.tk-seg').forEach((b,i)=>b.classList.toggle('on',i===0));
  document.querySelectorAll('.tk-prod').forEach((b,i)=>b.classList.toggle('on',i===0));
  document.querySelectorAll('.tk-ot').forEach((b,i)=>b.classList.toggle('on',i===0));
  document.getElementById('tk-price-wrap').style.display='none';document.getElementById('tk-guard').style.display='none';
  document.getElementById('tk-go').textContent='Review order';tkVal();tkExtras();
  clearInterval(TK_TIMER);TK_TIMER=setInterval(()=>{if(MKT_OPEN)tkDepth();},4000);  // live depth while open
  document.getElementById('tscrim').classList.add('on');document.getElementById('tsheet').classList.add('on');}
async function tkSeg(v,el){[...el.parentElement.children].forEach(b=>b.classList.toggle('on',b===el));tkReset();TK.seg=v;
  const ci=document.getElementById('tk-contract');
  if(v==='FUT'){ci.textContent='resolving futures…';const r=await j('/options/contract/'+encodeURIComponent(TK.sym)+'?'+Q);
    if(r.ok&&r.d.found){TK.exch='NFO';TK.fut=r.d;TK.lot=r.d.lot||1;TK.product='NRML';
      ci.textContent=r.d.tradingsymbol+' · lot '+TK.lot+' · exp '+r.d.expiry;
      document.getElementById('tk-qtylbl').textContent='Quantity (lots × '+TK.lot+')';
      document.querySelectorAll('.tk-prod').forEach(b=>{b.textContent=b.textContent==='CNC'?'NRML':b.textContent;});
      document.querySelectorAll('.tk-prod').forEach((b,i)=>b.classList.toggle('on',i===0));}
    else{ci.textContent=(r.d&&r.d.note)||'no futures';TK.seg='CASH';el.parentElement.children[0].classList.add('on');el.classList.remove('on');}}
  else{TK.exch='NSE';TK.fut=null;TK.lot=1;TK.product='CNC';ci.textContent='';document.getElementById('tk-qtylbl').textContent='Quantity (shares)';
    document.querySelectorAll('.tk-prod').forEach(b=>{if(b.textContent==='NRML')b.textContent='CNC';});
    document.querySelectorAll('.tk-prod').forEach((b,i)=>b.classList.toggle('on',i===0));}
  tkVal();}
let TK_TIMER=null;
function closeTicket(){document.getElementById('tscrim').classList.remove('on');document.getElementById('tsheet').classList.remove('on');
  clearInterval(TK_TIMER);TK_TIMER=null;const dp=document.getElementById('tk-depth');if(dp)dp.style.display='none';}
function tkReset(){TK.pid=null;document.getElementById('tk-go').textContent='Review order';tkExtras();}
/* ---- pro order pad: 5-level depth + live margin ---- */
function tkTok(){return (TK.seg==='FUT'&&TK.fut)?TK.fut.token:TK.token;}
let TK_EX_T=null;
function tkExtras(){clearTimeout(TK_EX_T);TK_EX_T=setTimeout(()=>{tkDepth();tkMargin();},300);}
async function tkDepth(){const el=document.getElementById('tk-depth');if(!el)return;const tok=tkTok();
  if(!tok){el.style.display='none';return;}
  const r=await j('/quote/'+encodeURIComponent(tok)+'?exchange='+encodeURIComponent(TK.exch)+'&'+Q);
  const d=r.ok?r.d:null;if(!d||d.error||!(d.buy&&d.buy.length)){el.style.display='none';return;}
  el.style.display='block';let rows='';
  for(let i=0;i<5;i++){const b=d.buy[i]||{},s=d.sell[i]||{};
    rows+='<div style="display:flex;gap:6px;justify-content:space-between"><span class="up" style="flex:1">'+(b.qty!=null?kfmt(b.qty):'')+'</span><span class="up" style="width:64px;text-align:right">'+(b.price||'')+'</span><span style="width:64px" class="down">'+(s.price||'')+'</span><span class="down" style="flex:1;text-align:right">'+(s.qty!=null?kfmt(s.qty):'')+'</span></div>';}
  el.innerHTML='<div class="rsub" style="color:var(--n500);text-transform:uppercase;letter-spacing:.05em;display:flex;justify-content:space-between"><span>bid</span><span>ask</span></div>'+rows
    +'<div class="rsub" style="color:var(--n600);margin-top:3px">Σ buy '+kfmt(d.total_buy)+' · sell '+kfmt(d.total_sell)+(d.oi?' · OI '+kfmt(d.oi):'')+'</div>';}
let RMS_CACHE={ts:0,v:null};
async function tkMargin(){const f=document.getElementById('tk-funds');if(!f)return;
  if(TK.exch!=='NFO'){return;}  // equity affordability handled by tkVal (cash)
  if(!RMS_CACHE.v||Date.now()-RMS_CACHE.ts>30000){const rr=await j('/margin/rms?'+Q);if(rr.ok&&!rr.d.error)RMS_CACHE={ts:Date.now(),v:rr.d};}
  const avail=RMS_CACHE.v?RMS_CACHE.v.available_margin:((PORT&&PORT.cash)||0);const tok=tkTok();if(!tok)return;
  const px=(TK.ot==='LIMIT'||TK.ot==='SL')?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;
  const r=await j2('/margin/order?'+Q,'POST',{legs:[{exchange:TK.exch,token:tok,product:TK.product,side:TK.side,qty:tkUnits(),price:px}]});
  if(r.ok&&r.d&&!r.d.error&&r.d.total){const need=r.d.total,ok=need<=avail;
    f.innerHTML='Margin '+inr(need)+(r.d.span?' · SPAN '+inr(r.d.span):'')+' · Avail '+inr(avail)+(ok?'':' · <span class="down">short</span>');}}
function tkSide(s){TK.side=s;tkReset();document.querySelectorAll('#tsheet .tk-side').forEach(b=>b.classList.toggle('on',b.dataset.s===s));const st=document.getElementById('tk-stop');if(st&&TK.ltp)st.value=(TK.ltp*(s==='BUY'?0.95:1.05)).toFixed(2);}
function tkProd(el){TK.product=el.textContent.trim();tkReset();[...el.parentElement.children].forEach(b=>b.classList.toggle('on',b===el));}
function tkOt(v,el){TK.ot=v;tkReset();[...el.parentElement.children].forEach(b=>b.classList.toggle('on',b===el));
  document.getElementById('tk-price-wrap').style.display=(v==='LIMIT'||v==='SL')?'block':'none';   // SL is a stop-LIMIT
  document.getElementById('tk-trig-wrap').style.display=(v==='SL'||v==='SL-M')?'block':'none';
  tkVal();}
function tkQty(d){TK.qty=Math.max(1,TK.qty+d);document.getElementById('tk-qty').textContent=TK.qty;tkReset();tkVal();}
function tkUnits(){return TK.qty*(TK.seg==='FUT'?TK.lot:1);}
function tkVal(){const px=(TK.ot==='LIMIT'||TK.ot==='SL')?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;
  const val=px?tkUnits()*px:0;document.getElementById('tk-val').textContent=val?inr(val):'';
  // Kite/Angel-style affordability: show available cash and flag a delivery buy you can't fund.
  const f=document.getElementById('tk-funds');if(!f)return;const cash=(PORT&&PORT.cash)||0;
  if(!val){f.textContent='';return;}
  const overCnc=TK.side==='BUY'&&TK.product==='CNC'&&val>cash;
  f.innerHTML='Order '+inr(val)+' · Available cash '+inr(cash)+(overCnc?' · <span class="down">exceeds cash</span>':'');}
async function tkReview(){
  if(TK.pid){return tkConfirm();}
  const px=(TK.ot==='LIMIT'||TK.ot==='SL')?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;
  const trig=(TK.ot==='SL'||TK.ot==='SL-M')?(+document.getElementById('tk-trig').value||0):0;
  if((TK.ot==='SL'||TK.ot==='SL-M')&&!trig){const g=document.getElementById('tk-guard');g.style.display='block';g.innerHTML='<div class="rsub" style="color:var(--down)">Enter a trigger price for an SL order.</div>';return;}
  const fut=TK.seg==='FUT'&&TK.fut;
  const stop=+document.getElementById('tk-stop').value||0;
  const tgt=px?+((TK.side==='BUY'?px*1.1:px*0.9).toFixed(2)):0;
  const acct=(document.getElementById('tk-acct')||{}).value||angelKey();
  const order={creds_key:acct,exchange:TK.exch,symbol:fut?TK.fut.tradingsymbol:TK.sym,token:fut?TK.fut.token:'',side:TK.side,quantity:tkUnits(),product:TK.product,order_type:TK.ot,price:px,trigger_price:trig,underlying:TK.sym,stop_loss:stop,target:tgt};
  const g=document.getElementById('tk-guard');g.style.display='block';g.innerHTML='<div class="rsub">checking guardrails…</div>';
  const r=await j('/execution/propose?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(order)});
  if(r.ok){TK.pid=r.d.proposal_id;TK.code=r.d.confirm_code;g.innerHTML='<div class="rsub" style="color:var(--up)">Passes all guardrails.</div><div class="rsub" style="margin-top:4px">'+(r.d.review||'')+'</div>';document.getElementById('tk-go').textContent='Confirm '+TK.side+' →';}
  else{g.innerHTML='<div class="rsub" style="color:var(--down)">Blocked: '+(r.d.detail||('error '+r.status))+'</div><div class="rsub" style="margin-top:4px;color:var(--n500)">Nothing sent — the guardrail did its job.</div>';tkReset();}
}
async function tkConfirm(){
  const g=document.getElementById('tk-guard');document.getElementById('tk-go').textContent='Placing…';
  const r=await j('/execution/confirm?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:TK.pid,confirm_code:TK.code})});
  if(r.ok){g.innerHTML='<div class="rsub" style="color:var(--up)">✅ Order placed.</div>';document.getElementById('tk-go').textContent='Done';setTimeout(closeTicket,1200);loadOrderBook();}
  else{g.innerHTML='<div class="rsub" style="color:var(--down)">'+(r.status===501?'Order-send pending broker enablement.':(r.d.detail||'Rejected.'))+'</div>';tkReset();}
}
function obStatusCls(s){if(/complete|filled/.test(s))return 'up';if(/reject|cancel/.test(s))return 'down';if(/open|pending|trigger/.test(s))return 'warn';return 'muted';}
async function loadOrderBook(){const box=document.getElementById('ob-list'),meta=document.getElementById('ob-meta');if(!box)return;
  const r=await j('/orders/book?'+Q);
  if(!r.ok){  // whole call failed (auth/network) — fall back to the local audit log
    meta.textContent='audit log';const a=await j('/execution/log?'+Q);const ev=(a.ok&&a.d.events)||[];
    if(!ev.length){box.innerHTML='<div class="load">Order book unavailable — '+(r.d.detail||('error '+(r.s||'')))+'</div>';return;}
    box.innerHTML=ev.slice(0,20).map(e=>{const o=e.order||{},side=o.side||'';
      return '<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+(o.symbol||e.event||'—')+' <span class="rsub">'+(o.quantity?o.quantity+' @ '+(o.price||'—'):'')+'</span></div><div class="rsub">'+((e.event||'').replace(/_/g,' '))+'</div></div><div class="rr"><div class="c '+(side==='BUY'?'up':side==='SELL'?'down':'muted')+'">'+(side||'')+'</div></div></div>';}).join('');return;}
  const os=r.d.orders||[],errs=r.d.errors||[];
  meta.textContent='broker · '+(r.d.open||0)+' open'+(errs.length?' · '+errs.length+' acct issue':'');
  OBMAP={};os.forEach(o=>{OBMAP[o.orderid]=o;});
  let html='';
  // surface any per-account failure instead of pretending the book is empty
  if(errs.length){html+=errs.map(e=>'<div class="rsub down" style="padding:5px 0;border-bottom:1px solid var(--n200)">'+e.account+': '+e.error+'</div>').join('');}
  if(!os.length){box.innerHTML=html+'<div class="load">No orders today'+(errs.length?' (accounts above could not be read)':'')+'.</div>';return;}
  html+=os.slice(0,40).map(o=>{const cancellable=/open|pending|trigger|modif/.test(o.status||'');const hd=o.broker==='hdfc';
    return '<div class="row" style="flex-direction:column;align-items:stretch;gap:4px">'
      +'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="rn">'+(o.symbol||'—')+'</span>'
      +'<span class="rsub '+(o.side==='BUY'?'up':'down')+'">'+(o.side||'')+'</span>'
      +'<span class="rsub" style="border:1px solid var(--n400);padding:0 4px">'+(o.type||'')+'</span>'
      +'<span class="rsub" style="color:var(--n500)">'+(o.account||'')+'</span>'
      +'<span class="'+obStatusCls(o.status||'')+'" style="margin-left:auto;font-family:var(--fh);text-transform:uppercase;font-size:10px;letter-spacing:.05em">'+(o.status||'')+'</span></div>'
      +'<div class="rsub mono" style="color:var(--n600)">Qty '+o.qty+(o.filled?' ('+o.filled+' filled)':'')+' · '+(o.type==='MARKET'?'MKT':(o.price||'—'))+(o.trigger?' · trig '+o.trigger:'')+'</div>'
      +(o.reason&&/reject/.test(o.status||'')?'<div class="rsub down">'+o.reason+'</div>':'')
      +(cancellable?'<div style="display:flex;gap:6px">'+(hd?'<span class="rsub" style="color:var(--n500);padding:6px 0">manage in HDFC app</span>':'<button class="segb" style="padding:6px 12px;font-size:11px" onclick="modifyOrder(\''+o.orderid+'\')">Modify</button><button class="segb" style="padding:6px 12px;font-size:11px;color:var(--down);border-color:#5c2b2b" onclick="cancelOrder(\''+o.orderid+'\',\''+(o.variety||'NORMAL')+'\',\''+(o.broker||'angel')+'\')">Cancel</button>')+'</div>':'')
      +'</div>';}).join('');
  box.innerHTML=html;}
async function cancelOrder(oid,variety,broker){if(!confirm('Cancel this order?'))return;
  const r=await j2('/orders/cancel?'+Q,'POST',{orderid:oid,variety:variety,broker:broker||'angel'});
  if(r.ok){loadOrderBook();}else alert(r.d.detail||'cancel failed');}
async function loadRecon(){const box=document.getElementById('recon-list'),meta=document.getElementById('recon-meta');if(!box)return;
  box.innerHTML='<div class="load">reconciling every account — orders, stops, positions…</div>';
  const r=await j('/reconcile/live?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">'+((r.d&&r.d.detail)||'could not run reconciliation')+'</div>';return;}
  const s=r.d.summary||{},c=s.counts||{},o=r.d.orders||{};
  meta.innerHTML=s.clean?'<span class="up">✓ clean</span>':'<span class="down">'+s.flags+' flag'+(s.flags>1?'s':'')+'</span>';
  const sec=(title,items,cls,render)=>{if(!items||!items.length)return '';return '<div class="ssub">'+title+' ('+items.length+')</div>'+items.map(x=>'<div class="rsub '+cls+'" style="padding:2px 0">'+render(x)+'</div>').join('');};
  let h='';
  h+=sec('⛔ Naked positions — NO protective stop',r.d.naked_positions,'down',x=>(x.symbol||'—')+' · '+x.side+' '+Math.abs(x.quantity)+' · '+x.account+' · needs '+x.needs);
  h+=sec('Stop-loss issues',o.sl_issues,'down',x=>(x.symbol||'')+' · '+x.issue+(x.detail?' — '+x.detail:''));
  h+=sec('Rejected orders',o.rejected,'down',x=>(x.symbol||'')+' · '+(x.reason||x.status||''));
  h+=sec('Unaccounted sends',o.unaccounted,'',x=>(x.symbol||'')+' · '+x.why);
  h+=sec('⚠ Suspect cost basis',r.d.suspect_cost_basis,'',x=>(x.symbol||'')+' · avg '+x.avg+' vs ltp '+x.ltp);
  h+=sec('Account read errors',r.d.account_read_errors,'down',x=>x.account+' · '+x.error);
  const head='<div class="rsub" style="color:var(--n500);padding-bottom:6px">'+(r.d.accounts_checked||[]).length+' accounts · '+(c.orders_matched||0)+' orders matched</div>';
  if(!h)h='<div class="load"><span class="up">✓ All clean — '+(c.orders_matched||0)+' orders matched the broker book, every open position has a protective stop, no flags.</span></div>';
  box.innerHTML=head+h;}
let OBMAP={};
async function modifyOrder(oid){const o=OBMAP[oid];if(!o)return;
  const np=prompt('New limit price (blank = keep '+o.price+'):',o.price);if(np===null)return;
  const nq=prompt('New quantity (blank = keep '+o.qty+'):',o.qty);if(nq===null)return;
  const body={orderid:o.orderid,variety:o.variety||'NORMAL',tradingsymbol:o.symbol,symboltoken:o.symboltoken||'',exchange:o.exchange||'NSE',order_type:o.type||'LIMIT',quantity:+nq||o.qty,price:+np||o.price,trigger_price:o.trigger||0,product:o.product||'CNC',broker:o.broker||'angel'};
  const r=await j2('/orders/modify?'+Q,'POST',body);
  if(r.ok){loadOrderBook();}else alert(r.d.detail||'modify failed');}
/* ---- GTT: good-till-triggered resting orders ---- */
async function loadGtt(){const box=document.getElementById('gtt-list'),meta=document.getElementById('gtt-meta');if(!box)return;
  const r=await j('/gtt/list?'+Q);
  if(!r.ok||r.d.error){box.innerHTML='<div class="load">'+((r.d&&r.d.error)?('GTT: '+r.d.error):'could not load')+'</div>';return;}
  const gs=r.d.gtt||[];meta.textContent=gs.length+' active';
  if(!gs.length){box.innerHTML='<div class="load">No GTT rules. Set one from any order ticket.</div>';return;}
  box.innerHTML=gs.map(g=>'<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+(g.symbol||'—')+' <span class="rsub '+(g.side==='BUY'?'up':'down')+'">'+(g.side||'')+'</span></div>'
    +'<div class="rsub mono">Qty '+g.qty+' @ '+g.price+' · trigger '+g.trigger+' · '+(g.status||'')+'</div></div>'
    +'<div class="rr"><button class="segb" style="padding:6px 12px;font-size:11px;color:var(--down);border-color:#5c2b2b" onclick="cancelGtt(\''+g.id+'\',\''+(g.symboltoken||'')+'\',\''+(g.exchange||'NSE')+'\')">Cancel</button></div></div>').join('');}
async function cancelGtt(id,tok,exch){if(!confirm('Cancel this GTT?'))return;
  const r=await j2('/gtt/cancel?'+Q,'POST',{id:id,symboltoken:tok,exchange:exch});
  if(r.ok)loadGtt();else alert(r.d.detail||'cancel failed');}
/* ---- basket orders (multi-leg, combined margin, guarded placement) ---- */
let BASKET=[];
function addToBasket(){const tok=tkTok();if(TK.exch==='NFO'&&!tok){alert('No token — open from Holdings/Positions.');return;}
  const px=(TK.ot==='LIMIT'||TK.ot==='SL')?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;
  const trig=(TK.ot==='SL'||TK.ot==='SL-M')?(+document.getElementById('tk-trig').value||0):0;
  const fut=TK.seg==='FUT'&&TK.fut,acct=(document.getElementById('tk-acct')||{}).value||angelKey();
  BASKET.push({creds_key:acct,exchange:TK.exch,symbol:fut?TK.fut.tradingsymbol:TK.sym,token:tok||'',side:TK.side,quantity:tkUnits(),product:TK.product,order_type:TK.ot,price:px,trigger_price:trig,underlying:TK.sym,stop_loss:0,target:0});
  closeTicket();renderBasket();}
function clearBasket(){BASKET=[];renderBasket();}
function rmBasket(i){BASKET.splice(i,1);renderBasket();}
async function renderBasket(){const panel=document.getElementById('basket-panel');if(!panel)return;
  const list=document.getElementById('basket-list'),meta=document.getElementById('basket-meta');
  if(!BASKET.length){panel.style.display='none';return;}panel.style.display='block';
  list.innerHTML=BASKET.map((l,i)=>'<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+l.symbol+' <span class="rsub '+(l.side==='BUY'?'up':'down')+'">'+l.side+'</span></div><div class="rsub mono">'+l.quantity+' · '+l.order_type+(l.price?' @ '+l.price:'')+'</div></div><div class="rr"><button class="segb" style="padding:5px 10px;font-size:11px" onclick="rmBasket('+i+')">✕</button></div></div>').join('');
  const legs=BASKET.filter(l=>l.exchange==='NFO'&&l.token).map(l=>({exchange:l.exchange,token:l.token,product:l.product,side:l.side,qty:l.quantity,price:l.price}));
  if(legs.length){const r=await j2('/margin/order?'+Q,'POST',{legs:legs});
    if(r.ok&&r.d&&r.d.total)meta.innerHTML='margin '+inr(r.d.total)+(r.d.benefit?' <span class="up">saved '+inr(r.d.benefit)+'</span>':'');else meta.textContent=BASKET.length+' legs';}
  else meta.textContent=BASKET.length+' legs';}
async function placeBasket(){if(!BASKET.length)return;
  if(!confirm('Place all '+BASKET.length+' legs? Each passes guardrails + the master switch.'))return;
  const r=await j2('/basket/place?'+Q,'POST',{legs:BASKET});
  if(r.ok){const p=r.d.placed||0;alert('Placed '+p+'/'+r.d.total+' legs.'+(p<r.d.total?' Some failed — check the order book.':''));BASKET=[];renderBasket();loadOrderBook();}
  else alert(r.d.detail||'basket failed');}
async function setGtt(){
  const tok=(TK.seg==='FUT'&&TK.fut)?TK.fut.token:TK.token;
  if(!tok){alert('No instrument token for this symbol — open it from Holdings to set a GTT.');return;}
  const price=+document.getElementById('tk-price').value||TK.ltp;
  let trig=+document.getElementById('tk-trig').value||0;
  if(!trig){const p=prompt('GTT trigger price (fires when LTP crosses this):',price);trig=+p||0;}
  if(!trig){return;}
  const sym=(TK.seg==='FUT'&&TK.fut)?TK.fut.tradingsymbol:(/-EQ$/.test(TK.sym)?TK.sym:TK.sym+'-EQ');
  if(!confirm('GTT · '+TK.side+' '+tkUnits()+' '+sym+' when LTP hits '+trig+' (limit '+price+'). Set it?'))return;
  const r=await j2('/gtt/create?'+Q,'POST',{tradingsymbol:sym,symboltoken:tok,exchange:TK.exch,side:TK.side,product:TK.product,price:price,qty:tkUnits(),trigger:trig});
  if(r.ok){alert('GTT set ✓');closeTicket();}else alert(r.d.detail||'GTT failed');}
/* Holdings are shown grouped (market-cap or sector), each group drilling into its
   stocks, then into the enriched share page. Data from /holdings/grouped. */
let GROUPED=null,GVIEW='cap',POSMAP={};
function renderHoldings(p){loadGrouped();}   // kicks off the grouped fetch on each home refresh
async function loadGrouped(){
  const r=await j('/holdings/grouped?'+Q);const box=document.getElementById('hold-list');if(!box)return;
  if(!r.ok){if(!GROUPED)box.innerHTML='<div class="load">could not load</div>';return;}
  GROUPED=r.d;POSMAP={};
  ((GROUPED.by_cap&&GROUPED.by_cap.length?GROUPED.by_cap:GROUPED.by_sector)||[]).forEach(g=>(g.stocks||[]).forEach(s=>{POSMAP[s.symbol]=s;}));
  renderGrouped();
}
function setGView(v){GVIEW=v;renderGrouped();}
function renderGrouped(){
  if(!GROUPED)return;const box=document.getElementById('hold-list');
  const groups=(GVIEW==='cap'?GROUPED.by_cap:GROUPED.by_sector)||[];
  document.getElementById('hold-n').textContent=(GROUPED.total?inr(GROUPED.total):'')+' · tap a group';
  const tog='<div class="gtog"><button class="'+(GVIEW==='cap'?'on':'')+'" onclick="setGView(\'cap\')">Market Cap</button><button class="'+(GVIEW==='sector'?'on':'')+'" onclick="setGView(\'sector\')">Sector</button></div>';
  const rows=groups.map((g,i)=>{const pnl=g.unrealised>=0;
    return '<div class="grow" onclick="drillGroup('+i+')"><div style="flex:1;min-width:0">'
      +'<div class="rn">'+g.name+' <span class="rsub">'+g.count+' · '+g.weight+'%</span></div>'
      +'<div class="bar"><i style="width:'+Math.min(100,g.weight)+'%"></i></div></div>'
      +'<div class="rr"><div class="p">'+inr(g.value)+'</div><div class="c '+cl(g.day_pct)+'">'+sp(g.day_pct)+'</div>'
      +'<div class="rsub '+(pnl?'up':'down')+'">'+(pnl?'+':'')+inr(g.unrealised)+'</div></div></div>';}).join('')||'<div class="load">no holdings</div>';
  let extra='';
  if(GROUPED.screener_loaded===false&&GVIEW==='cap')extra='<div class="rsub" style="padding:10px 13px;color:var(--warn)">Cap buckets need a Screener export — upload one to classify large/mid/small/micro. Sector view works without it.</div>';
  box.innerHTML=tog+rows+extra;
  if(PORT)renderHeat(PORT);   // now that grouped sectors are in, make the sector map drillable
}
function drillGroup(i){const groups=(GVIEW==='cap'?GROUPED.by_cap:GROUPED.by_sector)||[];if(groups[i])showGroup(groups[i]);}
function drillSector(enc){const name=decodeURIComponent(enc);const g=((GROUPED&&GROUPED.by_sector)||[]).find(x=>x.name===name);if(g)showGroup(g);}
function showGroup(g){
  const pnl0=g.unrealised>=0;
  document.getElementById('sh-sym').textContent=g.name;
  document.getElementById('sh-px').innerHTML=inr(g.value)+' · <span class="'+cl(g.day_pct)+'">'+sp(g.day_pct)+'</span> · <span class="'+(pnl0?'up':'down')+'">'+(pnl0?'+':'')+inr(g.unrealised)+'</span>';
  document.getElementById('sh-body').innerHTML='<div class="rsub" style="margin-bottom:6px;color:var(--n500)">'+g.count+' stocks · '+g.weight+'% of book · tap a name for full detail</div>'
    +(g.stocks||[]).map(s=>{const pnl=s.unrealised>=0;
    return '<div class="row" onclick="openShare(\''+s.symbol+'\')" style="cursor:pointer;flex-direction:column;align-items:stretch;gap:3px">'
      +'<div style="display:flex;align-items:baseline;gap:8px"><span class="rn">'+s.symbol+'</span>'
      +'<span class="rsub">'+(s.cap||'')+' · '+(s.holders||[]).join(', ')+' · '+s.weight+'%</span>'
      +'<span class="p" style="margin-left:auto;font-family:var(--fm)">'+inr(s.value)+' <span class="'+cl(s.day_pct)+'" style="font-size:11px">'+sp(s.day_pct)+'</span></span></div>'
      +'<div class="rsub mono" style="color:var(--n600)">Qty '+s.qty+' · Avg '+(s.avg_price!=null?s.avg_price:'—')+' · LTP '+(s.last_price!=null?s.last_price:'—')+' · Inv '+inr(s.invested)+'</div>'
      +'<div class="rsub"><span class="'+(pnl?'up':'down')+'">Unrealised '+(pnl?'+':'')+inr(s.unrealised)+' ('+(pnl?'+':'')+s.unrealised_pct+'%)</span></div>'
      +'</div>';}).join('')||'<div class="load">no stocks</div>';
  document.getElementById('scrim').classList.add('on');document.getElementById('sheet').classList.add('on');
}
function angelKey(){const a=((PORT&&PORT.accounts)||[]).find(a=>((a.creds_key||'').toUpperCase()).startsWith('ANGEL'));return a?a.creds_key:(((PORT&&PORT.accounts&&PORT.accounts[0])||{}).creds_key||'ANGEL1');}
/* ---- income engine (covered calls + cash puts, guarded one-tap) ---- */
let INCOME_DATA={cc:[],cp:[]},incLoaded=0;
function istTab(t){
  ['ideas','calls','income'].forEach(x=>{const b=document.getElementById('ist-'+x);if(b)b.classList.toggle('on',x===t);
    const p=document.getElementById(x+'-panel');if(p)p.style.display=(x===t)?'':'none';});
  if(t==='income'&&!incLoaded){incLoaded=1;loadIncomeT();}
  if(t==='calls'){loadCalls();}}
function tpKind(){const inv=document.getElementById('tp-kind').value==='invest';
  document.getElementById('tp-tgt').style.display=inv?'none':'';document.getElementById('tp-stop').style.display=inv?'none':'';}
async function addTip(){const m=document.getElementById('tp-msg');
  const body={source:document.getElementById('tp-src').value,symbol:document.getElementById('tp-sym').value,
    kind:document.getElementById('tp-kind').value,buy:+document.getElementById('tp-buy').value||null,
    target:+document.getElementById('tp-tgt').value||null,stop:+document.getElementById('tp-stop').value||null,
    note:document.getElementById('tp-note').value};
  if(!body.symbol){m.textContent='Enter a symbol.';m.style.color='var(--down)';return;}
  const r=await j2('/tips?'+Q,'POST',body);
  if(r.ok){m.textContent='Added.';m.style.color='var(--up)';['tp-sym','tp-buy','tp-tgt','tp-stop','tp-note'].forEach(id=>document.getElementById(id).value='');loadCalls();}
  else{m.textContent=r.d.detail||'could not add';m.style.color='var(--down)';}}
async function delTip(id){if(!confirm('Delete this call?'))return;const r=await j2('/tips/'+id+'?'+Q,'DELETE',{});if(r.ok)loadCalls();}
function tradeTip(sym,buy,stop){istRun&&clearTimeout(istRun);openTicket(sym,buy||0,'BUY');
  const lmt=[...document.querySelectorAll('.tk-ot')].find(b=>b.textContent.trim()==='LMT');if(lmt&&buy)tkOt('LIMIT',lmt);
  if(buy)document.getElementById('tk-price').value=buy;if(stop)document.getElementById('tk-stop').value=stop;tkVal&&tkVal();}
let istRun=null;
async function loadCalls(){const box=document.getElementById('calls-list'),meta=document.getElementById('calls-meta');if(!box)return;
  const r=await j('/tips?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">'+((r.d&&r.d.detail)||'could not load calls')+'</div>';return;}
  const chs=r.d.channels||[];meta.textContent=(r.d.count||0)+' calls · '+(r.d.actionable||0)+' actionable';
  if(!chs.length){box.innerHTML='<div class="load">No calls logged yet. Add one above.</div>';return;}
  box.innerHTML=chs.map(ch=>'<div class="ssub" style="padding:10px 14px 2px">'+ch.source+'</div>'+ch.tips.map(t=>tipCard(t)).join('')).join('');}
function tipCard(t){const ltp=t.ltp,act=t.actionable,alert=t.alert;
  const badge='<span class="rchip '+(alert?'dgr':(act?'':'')) +'" style="'+(alert?'':(act?'color:var(--up);border-color:var(--up)':'color:var(--n500)'))+'">'+(t.state||'')+'</span>';
  const px=(v)=>v?(+v).toFixed(1):'—';
  let levels='';
  if(t.kind==='invest'){const lv=t.levels||[];levels='<div class="rsub mono" style="color:var(--n600)">Ladder: '+lv.map(x=>'<span style="'+(ltp&&ltp<=x?'color:var(--up)':'')+'">'+(+x).toFixed(1)+'</span>').join(' · ')+'</div>';}
  else{levels='<div class="rsub mono" style="color:var(--n600)">Buy '+px(t.buy)+' · Target '+px(t.target)+' · Stop <span class="down">'+px(t.stop)+'</span></div>';}
  const actions='<div style="display:flex;gap:6px;margin-top:2px">'
    +(t.kind==='trade'?'<button class="segb" style="padding:6px 12px;font-size:11px;color:var(--up);border-color:#1f5c46" onclick="tradeTip(\''+t.symbol+'\','+(t.buy||0)+','+(t.stop||0)+')">Trade →</button>':'')
    +'<button class="segb" style="padding:6px 12px;font-size:11px;color:var(--down);border-color:#5c2b2b" onclick="delTip(\''+t.id+'\')">Delete</button></div>';
  return '<div class="row" style="flex-direction:column;align-items:stretch;gap:5px">'
    +'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="rn">'+t.symbol+'</span>'
    +'<span class="rsub" style="border:1px solid var(--n400);padding:0 4px">'+t.kind+'</span>'
    +badge+'<span class="mono" style="margin-left:auto">'+(ltp?('LTP '+ltp.toFixed(1)):'—')+'</span></div>'
    +levels+(t.note?'<div class="rsub" style="color:var(--n500)">'+t.note+'</div>':'')+actions+'</div>';}
async function loadIncomeT(){
  const box=document.getElementById('income-list');const r=await j('/income/ideas?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">could not load</div>';return;}
  const d=r.d,s=d.summary||{};INCOME_DATA={cc:d.covered_calls||[],cp:d.cash_secured_puts||[]};
  document.getElementById('inc-sum').textContent='+'+inr(s.total_premium||0)+' this cycle';
  const cc=INCOME_DATA.cc,cp=INCOME_DATA.cp;
  if(!cc.length&&!cp.length){const dg=d.diag||{};
    const why=dg.reason||'Need an F&O holding of a full lot (calls) or cash (puts), and the chain live.';
    const stat=dg.fno_universe!=null?('<div class="rsub" style="margin-top:8px;color:var(--n600)">F&O universe: '+dg.fno_universe+' stocks · your F&O holdings: '+(dg.fno_eligible_holdings||0)+' · with a full lot: '+(dg.holdings_with_full_lot||0)+' · free cash '+inr(dg.free_cash||0)+'</div>'):'';
    box.innerHTML='<div class="pb"><div class="rn">No income setups right now</div><div class="rsub" style="margin-top:6px;color:var(--warn)">'+why+'</div>'+stat+'</div>';return;}
  box.innerHTML=cc.map((x,i)=>incCard(x,i,true)).join('')+cp.map((x,i)=>incCard(x,i,false)).join('');
}
function incCard(x,i,isCC){
  const src=x.premium_source==='live'?'':' <span class="rsub" style="color:var(--warn)">theo</span>';
  const line=isCC?('Yield '+x.yield_pct+'% · Ann '+x.annualised_pct+'% · cushion +'+x.cushion_pct+'% · assign '+x.assignment_prob_pct+'%')
                 :('Yield/cash '+x.yield_on_cash_pct+'% · Ann '+x.annualised_pct+'% · disc '+x.discount_pct+'% · cap '+inr(x.capital_reserved));
  return '<div class="row" style="flex-direction:column;align-items:stretch;gap:6px">'
    +'<div style="display:flex;align-items:baseline"><span class="rn" style="font-size:15px">'+x.symbol+'</span>'
    +'<span class="rsub" style="margin-left:8px">'+(isCC?'CC':'CSP')+' '+x.strike+(isCC?'CE':'PE')+' · '+x.expiry+src+'</span>'
    +'<span class="mono" style="margin-left:auto;font-weight:600;color:'+(isCC?'var(--up)':'#a78bfa')+'">+'+inr(x.income)+'</span></div>'
    +'<div class="rsub mono" style="color:var(--n600)">'+line+' · OI '+(x.oi!=null?kfmt(x.oi):'—')+' · DTE '+x.dte+'</div>'
    +'<button class="segb" style="width:100%;padding:10px 0;font-size:12px" onclick="incPlace(\''+x.strategy+'\','+i+',this)">Place · sell '+x.contracts+' lot'+(x.contracts>1?'s':'')+'</button></div>';
}
async function incPlace(strat,i,btn){
  const x=strat==='covered_call'?INCOME_DATA.cc[i]:INCOME_DATA.cp[i];if(!x)return;
  if(btn.dataset.pid){btn.textContent='Placing…';
    const r=await j('/execution/confirm?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({proposal_id:btn.dataset.pid,confirm_code:btn.dataset.code})});
    btn.textContent=r.ok?'✅ Placed':(r.status===501?'Send pending':'Rejected');return;}
  const qty=x.contracts*x.lot;
  const order={creds_key:x.account||angelKey(),exchange:'NFO',symbol:x.tradingsymbol,token:x.token,side:'SELL',quantity:qty,product:'NRML',order_type:'LIMIT',price:x.premium,trigger_price:0,underlying:x.symbol,stop_loss:+(x.premium*2).toFixed(2),target:+(x.premium*0.2).toFixed(2)};
  btn.textContent='Checking guardrails…';
  const r=await j('/execution/propose?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(order)});
  if(r.ok){btn.dataset.pid=r.d.proposal_id;btn.dataset.code=r.d.confirm_code;btn.textContent='Confirm SELL '+x.contracts+' lot →';}
  else{btn.textContent='Blocked: '+((r.d.detail||'error')+'').slice(0,42);}
}

/* ---- chart + F&O edge ---- */
let CHART_SYM='NIFTY 50',CHART_EDGE='NIFTY',CHART_RANGE=66,CHART_DATA=null,chartLoaded=0;
function chartChips(){const holds=PORT?allHoldings(PORT).sort((a,b)=>b.mv-a.mv).slice(0,6).map(x=>x.s):[];
  const base=[['NIFTY 50','NIFTY'],['BANK NIFTY','BANKNIFTY']].concat(holds.map(s=>[s,s]));
  document.getElementById('ch-chips').innerHTML=base.map(([s,e])=>'<button class="segb'+(s===CHART_SYM?' on':'')+'" onclick="setChart(\''+s+'\',\''+e+'\')">'+s+'</button>').join('');}
function setChart(sym,edge){CHART_SYM=sym;CHART_EDGE=edge||sym;document.getElementById('ch-sym').textContent=sym;chartChips();loadChart();}
function goChart(sym){closeShare();setChart(sym,sym);document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t==='chart'));document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));document.getElementById('s-chart').classList.add('on');if(!chartLoaded){chartLoaded=1;}window.scrollTo(0,0);}
function drawChart(d){
  const c=document.getElementById('ch-canvas');if(!c||!d)return;const x=c.getContext('2d'),W=c.width,H=c.height;x.clearRect(0,0,W,H);
  let clz=(d.closes||[]),s50=(d.sma50||[]),s200=(d.sma200||[]);const n=Math.min(CHART_RANGE,clz.length);if(!n)return;
  clz=clz.slice(-n);s50=s50.slice(-n);s200=s200.slice(-n);
  const all=clz.concat(s50.filter(v=>v!=null),s200.filter(v=>v!=null));let mn=Math.min(...all),mx=Math.max(...all);const pd=(mx-mn)*0.08||1;mn-=pd;mx+=pd;
  const X=i=>i/(n-1)*W,Y=v=>H-((v-mn)/(mx-mn))*H;
  x.strokeStyle='#1d232d';x.lineWidth=1;for(let gi=1;gi<3;gi++){const yy=H*gi/3;x.beginPath();x.moveTo(0,yy);x.lineTo(W,yy);x.stroke();}
  x.beginPath();clz.forEach((v,i)=>i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v)));x.lineTo(W,H);x.lineTo(0,H);x.closePath();
  const gr=x.createLinearGradient(0,0,0,H);gr.addColorStop(0,'rgba(63,140,222,.25)');gr.addColorStop(1,'rgba(63,140,222,0)');x.fillStyle=gr;x.fill();
  x.beginPath();clz.forEach((v,i)=>i?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v)));x.strokeStyle='#3f8cde';x.lineWidth=2;x.lineJoin='round';x.stroke();
  const dS=(arr,col)=>{x.beginPath();let st=false;arr.forEach((v,i)=>{if(v==null)return;st?x.lineTo(X(i),Y(v)):x.moveTo(X(i),Y(v));st=true;});x.strokeStyle=col;x.lineWidth=1.2;x.stroke();};
  dS(s50,'#f0a13c');dS(s200,'#a78bfa');
  const lv=d.levels||{};x.setLineDash([4,4]);[['#2ebd85',lv.support],['#f0544c',lv.resistance]].forEach(p=>{const val=p[1];if(val==null||val<mn||val>mx)return;x.beginPath();x.moveTo(0,Y(val));x.lineTo(W,Y(val));x.strokeStyle=p[0];x.lineWidth=1;x.stroke();});x.setLineDash([]);
}
async function loadChart(){
  const r=await j('/chart/'+encodeURIComponent(CHART_SYM)+'?'+Q);
  if(r.ok&&r.d.last!=null){const d=r.d;CHART_DATA=d;
    document.getElementById('ch-px').innerHTML='<span class="'+cl(d.day_change_pct)+'">'+d.last+'  '+sp(d.day_change_pct)+'</span>';
    const lv=d.levels||{};document.getElementById('ch-lvl').innerHTML='<span style="color:#f0a13c">━</span> 50D  <span style="color:#a78bfa">━</span> 200D  ·  S '+(lv.support||'—')+' · Pivot '+(lv.pivot||'—')+' · R '+(lv.resistance||'—')+' · RSI '+(d.rsi14||'—');
    drawChart(d);}
  else document.getElementById('ch-px').textContent='no data';
  const e=await j('/options/edge/'+encodeURIComponent(CHART_EDGE)+'?'+Q),box=document.getElementById('ch-edge');
  const g=(k,v)=>'<div class="fg"><div class="k">'+k+'</div><div class="v">'+(v!=null&&v!==''?v:'—')+'</div></div>';
  if(e.ok&&e.d.supported&&e.d.pcr!=null){const d=e.d;document.getElementById('ch-edge-exp').textContent=d.expiry||'';
    box.innerHTML=g('PCR',d.pcr)+g('Max Pain',d.max_pain)+g('Spot',d.spot)+g('Put wall',d.support_wall)+g('Call wall',d.resistance_wall)+g('Bias',(d.bias||'').toUpperCase());
    document.getElementById('ch-edge-note').textContent=d.note||'';}
  else{document.getElementById('ch-edge-exp').textContent='';box.innerHTML='<div class="fg" style="grid-column:1/-1"><div class="rsub">'+((e.ok&&e.d.note)||'PCR / Max Pain available for NIFTY & BANK NIFTY.')+'</div></div>';document.getElementById('ch-edge-note').textContent='';}
}
document.getElementById('ch-range').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;CHART_RANGE=+b.dataset.r;document.querySelectorAll('#ch-range .segb').forEach(x=>x.classList.toggle('on',x===b));if(CHART_DATA)drawChart(CHART_DATA);});
let newsLoaded=0,setLoaded=0,ideasLoaded=0;
async function loadIdeas(){
  const box=document.getElementById('ideas-list');const r=await j('/ideas/high-conviction?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">could not load</div>';return;}
  if(r.d.error){box.innerHTML='<div class="pb"><div class="rn">Ideas need data</div><div class="rsub" style="margin-top:6px;color:var(--warn)">'+r.d.error+'</div></div>';return;}
  const ii=r.d.ideas||[];const cand=r.d.candidates||[];const dg=r.d.diag||{};
  const ideaCard=(i,dim)=>{const flag=(i.flags&&i.flags.length)?(i.flags[0].text||i.flags[0]):'';
    return '<div class="row" onclick="openShare(\''+i.symbol+'\')" style="flex-direction:column;align-items:stretch;gap:8px;cursor:pointer'+(dim?';opacity:.9':'')+'">'
      +'<div style="display:flex;align-items:baseline"><span class="rn" style="font-size:16px;font-weight:600">'+i.symbol+'</span>'
      +'<span class="rsub" style="margin-left:9px;border:1px solid var(--n400);padding:1px 6px">'+(i.horizon||'—')+'</span>'
      +(dim&&i.action&&i.action!=='BUY'?'<span class="rsub" style="margin-left:6px;color:var(--warn)">'+i.action+'</span>':'')
      +'<span class="mono" style="margin-left:auto;font-weight:600;color:var(--a700)">CONV '+i.conviction+'</span></div>'
      +(i.entry!=null?'<div class="mono" style="display:flex;gap:16px;font-size:13px;flex-wrap:wrap"><span class="sec">Entry <b style="color:var(--text)">'+i.entry+'</b></span><span class="down">SL '+i.stop_loss+'</span><span class="up">TGT '+i.target+'</span><span class="sec">R:R <b style="color:var(--text)">'+i.reward_risk+'</b></span></div>':'')
      +(i.pattern?'<div class="rsub" style="color:var(--n600)">'+i.pattern.replace(/_/g,' ')+' · '+i.hit_rate+'% hit · avg '+(i.avg_return_pct>=0?'+':'')+i.avg_return_pct+'% over horizon</div>':'')
      +'<div class="rsub">F '+i.fundamental_score+' · T '+(i.technical_score!=null?i.technical_score:'—')+(flag?' · <span class="down">⚠ '+flag+'</span>':'')+'</div>'
      +'</div>';};
  if(ii.length){box.innerHTML=ii.map(i=>ideaCard(i,false)).join('')+'<div class="pb rsub" style="color:var(--n500)">'+(r.d.note||'')+'</div>';return;}
  // No high-conviction pass → explain + show closest candidates so it's never empty.
  let h='<div class="pb"><div class="rn">No high-conviction setups</div><div class="rsub" style="margin-top:6px;color:var(--warn)">'+(dg.reason||'The bar is intentionally high.')+'</div>';
  if(dg.universe!=null)h+='<div class="rsub" style="margin-top:6px;color:var(--n600)">Universe '+dg.universe+' · fundamentally strong '+(dg.fundamentally_strong||0)+' · analysed '+(dg.analysed||0)+'</div>';
  h+='</div>';
  if(cand.length)h+='<div class="ssub" style="padding:0 13px">Closest candidates</div>'+cand.map(i=>ideaCard(i,true)).join('');
  box.innerHTML=h;
}
async function loadSettings(){
  const r=await j('/accounts?'+Q),box=document.getElementById('set-accs');
  if(r.ok&&r.d.accounts){document.getElementById('set-acc-n').textContent=r.d.accounts.length+' configured';
    box.innerHTML=r.d.accounts.map(a=>{const on=a.logged_in;return '<div class="row"><div style="flex:1"><div class="rn">'+(a.label||a.key)+' <span class="rsub">'+a.key+'</span></div><div class="rsub" style="margin-top:2px;color:'+(on?'var(--up)':'var(--down)')+'">'+(on?'● logged in':'● logged out')+'</div></div>'+(a.broker==='hdfc'&&!on?'<a class="lgn" href="/hdfc/login?key='+a.key+'&'+Q+'">Log in</a>':'')+'</div>';}).join('');}
  else box.innerHTML='<div class="load">open Login tab</div>';
  const f=await j('/market/indices?'+Q),fb=document.getElementById('set-feeds');
  const n=(f.ok&&f.d.indices||[]).length;
  fb.innerHTML='<div class="rsub">EODHD indices: <span class="'+(n?'up':'down')+'">'+(n?n+' live':'down')+'</span></div>'
    +'<div class="rsub" style="margin-top:6px">Angel candles / quotes / OI: wired</div>'
    +'<div class="rsub" style="margin-top:6px">News: Google RSS</div>';
  document.getElementById('set-classic').href='/classic?'+Q;
  const ss=document.getElementById('set-status');if(ss)ss.href='/status';
  loadBalances();loadScreener();
}
async function loadScreener(){
  const r=await j('/fundamentals/screener/status?'+Q);if(!r.ok)return;const s=r.d;
  const st=document.getElementById('scr-stat'),el=document.getElementById('scr-detail');
  if(s.loaded){st.innerHTML='<span class="up">loaded</span>';
    const nf=s.fields_detected?Object.keys(s.fields_detected).length:0,miss=(s.fields_missing||[]).length;
    el.innerHTML=(s.companies||0)+' companies · '+nf+' fields mapped'+(miss?(' · <span class="warn">'+miss+' missing</span>'):'')+' · <span class="muted">'+(s.active_file||'')+'</span>';}
  else{st.innerHTML='<span class="down">none</span>';el.textContent=s.reason||'No Screener export uploaded yet.';}
}
async function uploadScreener(){
  const f=document.getElementById('scr-file').files[0],el=document.getElementById('scr-detail');
  if(!f){el.textContent='Pick a .xlsx or .csv first.';return;}
  el.textContent='Uploading '+f.name+'…';const fd=new FormData();fd.append('file',f);
  try{const r=await fetch('/fundamentals/screener/upload?'+Q,{method:'POST',body:fd});const d=await r.json().catch(()=>({}));
    if(r.ok){el.innerHTML='<span class="up">✅ uploaded — '+((d.status&&d.status.companies)||0)+' companies</span>';loadScreener();}
    else el.innerHTML='<span class="down">'+(d.detail||'upload failed')+'</span>';
  }catch(e){el.innerHTML='<span class="down">network error</span>';}
}
async function loadBalances(){
  const [b,w]=await Promise.all([j('/balances?'+Q),j('/wealth?'+Q)]);
  if(w.ok){document.getElementById('tw-total').textContent=inr(w.d.total_wealth);
    document.getElementById('tw-split').innerHTML='Demat '+inr(w.d.demat_net_worth)+' + External '+inr(w.d.external_total)+' · USDINR '+(w.d.usdinr||'—');}
  const box=document.getElementById('bal-list');if(!b.ok){box.innerHTML='<div class="load">could not load</div>';return;}
  const its=b.d.items||[];document.getElementById('bal-usd').textContent='USDINR '+(b.d.usdinr||'—');
  if(!its.length){box.innerHTML='<div class="load">No external balances yet — add US stocks, crypto, bank, trading cash below.</div>';return;}
  box.innerHTML=its.map(x=>'<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+x.label+' <span class="rsub">'+x.bucket+'</span></div>'
    +'<div class="rsub">'+(x.currency==='USD'?('$'+(x.amount).toLocaleString('en-US')+' → '):'')+inr(x.inr_value)+'</div></div>'
    +'<div class="rr"><button class="iconbtn" onclick="event.stopPropagation();delBal(\''+x.id+'\')" style="color:var(--n500);font-size:14px;background:0;border:0;cursor:pointer">✕</button></div></div>').join('');
}
async function saveBal(){
  const label=document.getElementById('bal-label').value.trim();const amt=document.getElementById('bal-amt').value;
  if(!label||amt===''){return;}
  const body={label,bucket:document.getElementById('bal-bucket').value,amount:parseFloat(amt),currency:document.getElementById('bal-cur').value};
  const r=await j2('/balances?'+Q,'POST',body);
  if(r.ok){document.getElementById('bal-label').value='';document.getElementById('bal-amt').value='';loadBalances();}
  else alert(r.d.detail||'failed');
}
async function delBal(id){if(!confirm('Remove this balance?'))return;const r=await j2('/balances/'+id+'?'+Q,'DELETE');if(r.ok)loadBalances();}
async function j2(u,m,body){try{const o={method:m,headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);const r=await fetch(u,o);return {ok:r.ok,d:await r.json().catch(()=>({}))};}catch(e){return {ok:false,d:{}};}}
async function loadNews(){
  const box=document.getElementById('news-list');if(!PORT){box.innerHTML='<div class="load">load portfolio first</div>';return;}
  const top=allHoldings(PORT).sort((a,b)=>b.mv-a.mv).slice(0,6);let items=[];
  for(const x of top){const r=await j('/news/'+encodeURIComponent(x.s)+'?'+Q);if(r.ok&&r.d.news&&r.d.news.length)items.push({sym:x.s,...r.d.news[0]});}
  if(!items.length){box.innerHTML='<div class="load">no recent news</div>';return;}
  box.innerHTML=items.map(a=>'<a class="row" href="'+a.link+'" target="_blank" style="display:block"><div class="rn" style="font-size:13px;line-height:1.35">'+a.title+'</div><div class="rsub" style="margin-top:4px">'+a.sym+' · '+(a.source||'')+(a.when?' · '+a.when:'')+'</div></a>').join('');
}
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  let t=b.dataset.t;
  if(t==='login')t='settings';          // Login + Settings are one combined hub now
  document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));
  document.getElementById('s-'+t).classList.add('on');
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));window.scrollTo(0,0);
  if(t==='positions'){loadPositions();loadOrderBook();loadGtt();renderBasket();}
  if(t==='settings'&&!setLoaded){setLoaded=1;loadSettings();}
  if(t==='ideas'&&!ideasLoaded){ideasLoaded=1;loadIdeas();}
  if(t==='chart'){if(!chartLoaded){chartLoaded=1;chartChips();}loadChart();}
  if(t==='news'&&!newsLoaded){newsLoaded=1;loadNews();}});

/* single 30s heartbeat — refreshes header/portfolio/ticker + the active tab.
   Fetches are error-tolerant (keep last data on failure), so a server blip never
   blanks the screen; the next tick recovers automatically. */
let LOADED=false;
async function heartbeat(){
  try{mktStatus();}catch(e){}   // clock/status is local — always update
  // After market close nothing moves, so fetch ONCE (first load) then freeze — no
  // wasteful polling. During market hours, refresh normally.
  if(LOADED && !MKT_OPEN) return;
  LOADED=true;
  try{await loadTicker();}catch(e){}
  try{await loadHome();}catch(e){}
  try{const on=document.querySelector('section.on');
    if(on&&on.id==='s-positions'){loadPositions();}
    else if(on&&on.id==='s-ideas'){loadIdeas();}
    else if(on&&on.id==='s-settings'){loadBalances();}
  }catch(e){}
}
document.getElementById('tk-price').addEventListener('input',tkVal);
let BOOTED=false;
function boot(){
  if(BOOTED)return;BOOTED=true;
  heartbeat();setInterval(heartbeat,30000);
  /* Positions refresh every 5s in market hours — served from the warm ~3s tick cache. */
  setInterval(()=>{try{const on=document.querySelector('section.on');
    if(MKT_OPEN&&on&&on.id==='s-positions')loadPositions();}catch(e){}},5000);
}
/* Password gate: if there's no token yet and the server has a password set, show the
   unlock screen; otherwise boot straight in. Unlock exchanges the password for the token. */
async function unlock(){
  const pw=document.getElementById('gate-pw').value,m=document.getElementById('gate-msg');
  if(!pw){return;}m.textContent='';
  try{
    const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
    const d=await r.json().catch(()=>({}));
    if(r.ok&&d.token){token=d.token;Q='token='+encodeURIComponent(token);_reauthing=false;try{localStorage.setItem('cfo_token',token);}catch(e){}
      document.getElementById('gate').style.display='none';boot();}
    else{m.textContent=d.detail||'Wrong password.';}
  }catch(e){m.textContent='Network error — try again.';}
}
let _reauthing=false;
function showGate(msg){const g=document.getElementById('gate');if(!g)return;g.style.display='flex';
  const pw=document.getElementById('gate-pw');if(pw){pw.focus();pw.onkeydown=e=>{if(e.key==='Enter')unlock();};}
  const m=document.getElementById('gate-msg');if(m&&msg)m.textContent=msg;}
/* A 401 means the stored token is dead (e.g. it was rotated). Wipe it and, if the
   server has a password, show the unlock screen — so the app self-heals on the phone
   without needing a manual cache clear. */
async function reauth(){
  if(_reauthing)return;_reauthing=true;
  try{localStorage.removeItem('cfo_token');}catch(e){}
  token='';Q='token=';
  let need=false;
  try{const r=await fetch('/auth/status');const d=await r.json();need=!!d.password_required;}catch(e){}
  if(need)showGate('Session expired — re-enter your password.');
}
async function initApp(){
  if(token){boot();return;}
  let need=false;
  try{const r=await fetch('/auth/status');const d=await r.json();need=!!d.password_required;}catch(e){}
  if(need)showGate();
  else boot();   // no password configured + no token = local/open mode
}
initApp();
</script></body></html>"""
