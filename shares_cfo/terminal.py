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
  display:grid;grid-template-columns:repeat(7,1fr);padding-bottom:env(safe-area-inset-bottom)}
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
</style></head><body>
<div class="app">
  <div class="hdr">
    <div><div class="hti">MARKET<b>·</b>CONSOLE</div>
      <div class="mkt"><span class="sd" id="sd"></span><span id="mstat">—</span></div></div>
    <div class="hnw"><div class="v" id="hnw">₹—</div><div class="d muted" id="hday">—</div></div>
  </div>
  <div class="tick"><div class="tickrow" id="tickrow"><span class="ti muted">loading feed…</span></div></div>
  <a class="banner" id="banner" href="#"></a>

  <section id="s-settings"><div class="wrap">
    <div class="panel span2"><div class="ph"><span class="t">Accounts &amp; login</span><span class="lbl" id="set-acc-n"></span></div><div id="set-accs"><div class="load">loading</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Data feeds</span></div><div class="pb" id="set-feeds"><div class="load">checking</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Trading</span></div><div class="pb" id="set-trade"><div class="sec" style="font-size:12px">Order execution is guarded (caps, allow-list, kill-switch). Master switch is set in the server env.</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Views</span></div><div class="pb" style="display:flex;flex-direction:column;gap:10px"><a id="set-biz" href="#" class="lbl" style="color:var(--a700)">Open Business OS →</a><a id="set-life" href="#" class="lbl" style="color:var(--a700)">Open Life OS →</a><a id="set-classic" href="#" class="lbl" style="color:var(--a700)">Open classic dashboard →</a></div></div>
  </div></section>

  <section id="s-portfolio" class="on"><div class="wrap" id="markets-wrap">
    <div class="panel span2"><div class="pb">
      <div class="lbl">Consolidated net worth</div>
      <div class="nwbig" id="nw">₹—</div><div class="mono" id="nwday" style="font-size:12px;margin-top:3px">—</div>
      <div class="nwrow">
        <div><div class="k">Unrealised</div><div class="v" id="nwu">—</div></div>
        <div><div class="k">Cash</div><div class="v" id="nwc">—</div></div>
        <div><div class="k">Invested</div><div class="v" id="nwi">—</div></div>
      </div></div></div>
    <div class="panel"><div class="ph"><span class="t">Accounts</span><span class="lbl" id="acc-n"></span></div><div id="accs"><div class="load">loading</div></div></div>
    <div class="panel"><div class="ph"><span class="t">Sector heatmap</span><span class="lbl">your book · today</span></div><div class="pb"><div class="heat" id="heat"></div></div></div>
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
    <div class="panel span2"><div class="pb" style="display:flex;gap:20px">
      <div><div class="lbl">Today</div><div class="mono" id="pos-day" style="font-size:20px;font-weight:600">—</div></div>
      <div><div class="lbl">Open MTM</div><div class="mono" id="pos-real" style="font-size:20px;font-weight:600">—</div></div>
      <div style="margin-left:auto;text-align:right"><div class="lbl">F&amp;O legs</div><div class="mono" id="pos-n" style="font-size:20px;font-weight:600">—</div></div>
    </div></div>
    <div class="panel span2"><div class="ph"><span class="t">Live positions</span><span class="lbl">HDFC + Angel · OI/vol</span></div><div id="pos-list"><div class="load">loading positions</div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Order book</span><span class="lbl">audit log</span></div><div id="ob-list"><div class="load">—</div></div></div>
  </div></section>

  <section id="s-ideas"><div class="wrap">
    <div style="display:flex;gap:6px;margin-bottom:12px;grid-column:1/-1"><button class="segb on" id="ist-ideas" onclick="istTab('ideas')" style="flex:1;padding:10px 0">Ideas</button><button class="segb" id="ist-income" onclick="istTab('income')" style="flex:1;padding:10px 0">Income</button></div>
    <div class="panel span2" id="ideas-panel"><div class="ph"><span class="t">High-conviction ideas</span><span class="lbl">fundamental + technical + backtest</span></div><div id="ideas-list"><div class="load">scanning for setups</div></div></div>
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
  <div class="ssub">Account</div><select id="tk-acct" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fh);letter-spacing:.03em"></select>
  <div class="ssub">Product</div><div style="display:flex;gap:6px" id="tk-prods"><button class="segb tk-prod on" onclick="tkProd(this)">CNC</button><button class="segb tk-prod" onclick="tkProd(this)">MIS</button></div>
  <div class="ssub">Order type</div><div style="display:flex;gap:6px" id="tk-ots"><button class="segb tk-ot on" onclick="tkOt('MARKET',this)">MKT</button><button class="segb tk-ot" onclick="tkOt('LIMIT',this)">LMT</button></div>
  <div id="tk-price-wrap" style="display:none"><div class="ssub">Limit price</div><input id="tk-price" inputmode="decimal" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fm);font-size:15px"></div>
  <div class="ssub" id="tk-qtylbl">Quantity (shares)</div>
  <div style="display:flex;align-items:center;gap:12px"><button class="segb" onclick="tkQty(-1)" style="width:48px;padding:12px 0;font-size:16px">−</button><span class="mono" id="tk-qty" style="font-size:22px;min-width:64px;text-align:center">1</span><button class="segb" onclick="tkQty(1)" style="width:48px;padding:12px 0;font-size:16px">+</button><span class="rsub mono" id="tk-val" style="margin-left:auto"></span></div>
  <div class="ssub">Stop-loss (required)</div><input id="tk-stop" inputmode="decimal" style="width:100%;background:var(--n100);border:1px solid var(--n400);color:var(--text);padding:11px;font-family:var(--fm);font-size:15px">
  <div id="tk-guard" class="fg" style="margin-top:14px;border:1px solid var(--n300);display:none"></div>
  <button class="segb" id="tk-go" onclick="tkReview()" style="width:100%;padding:14px 0;margin-top:14px;font-size:13px">Review order</button>
  <div class="rsub" style="margin-top:8px;color:var(--n500)">Guarded: propose → confirm. Nothing places unless the master switch is on.</div>
</div>

<div class="tabs" id="tabs">
  <button data-t="settings">Settings</button>
  <button data-t="portfolio" class="on">Portfolio</button>
  <button data-t="positions">Positions</button>
  <button data-t="ideas">Ideas</button>
  <button data-t="chart">Chart</button>
  <button data-t="news">News</button>
  <button data-t="login">Login</button>
</div>

<script>
let token=new URLSearchParams(location.search).get('token')||'';
try{token=token||localStorage.getItem('cfo_token')||'';if(token)localStorage.setItem('cfo_token',token);}catch(e){}
const Q='token='+encodeURIComponent(token);
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));}
const _fails={};function _failbar(){let b=document.getElementById('failbar');if(!b){b=document.createElement('div');b.id='failbar';b.style.cssText='position:sticky;top:0;z-index:99;background:#3a1113;color:#f0a0a0;font:500 12px IBM Plex Mono,monospace;padding:6px 12px;border-bottom:1px solid #7a2a2a;display:none';document.body.prepend(b);}const k=Object.keys(_fails);if(k.length){b.style.display='block';b.textContent='DATA FEED ERROR: '+k.map(u=>u.split('?')[0]+' ('+_fails[u]+')').join(' · ')+' — retrying automatically';}else{b.style.display='none';}return b;}
async function j(u){try{const r=await fetch(u);if(!r.ok){_fails[u]='HTTP '+r.status;_failbar();return {ok:false,d:{}};}delete _fails[u];_failbar();return {ok:true,d:await r.json()};}catch(e){_fails[u]=String(e&&e.message||'network');_failbar();return {ok:false,d:{}};}}
const inr=n=>{if(n==null||isNaN(n))return '₹—';const a=Math.abs(n),s=n<0?'-':'';if(a>=1e7)return s+'₹'+(a/1e7).toFixed(2)+'Cr';if(a>=1e5)return s+'₹'+(a/1e5).toFixed(2)+'L';return s+'₹'+Math.round(a).toLocaleString('en-IN');};
const sp=p=>(p>=0?'+':'')+(p==null||isNaN(p)?'—':p.toFixed(2)+'%');
const cl=v=>v>=0?'up':'down';
const clean=t=>(t||'').toUpperCase().replace(/-(EQ|BE|BZ|BL|SM|ST|IQ)$/,'').split('-')[0];

/* market status from IST (Asia/Kolkata), never device tz */
function mktStatus(){
  const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
  const g=t=>p.find(x=>x.type===t).value;const wd=g('weekday'),hm=+g('hour')*60+ +g('minute');
  const open=['Mon','Tue','Wed','Thu','Fri'].includes(wd)&&hm>=555&&hm<=930;
  document.getElementById('sd').className='sd'+(open?' open':'');
  document.getElementById('mstat').textContent=open?'MARKET OPEN':'MARKET CLOSED';
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
  renderAccounts(p);renderHeat(p);renderMovers(p);renderHoldings(p);
}
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
function renderHeat(p){const m=sectorMap(p);
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
  document.getElementById('pos-day').innerHTML='<span class="'+cl(d.day_pnl)+'">'+inr(d.day_pnl)+'</span>';
  document.getElementById('pos-real').innerHTML='<span class="'+cl(d.realized_pnl)+'">'+inr(d.realized_pnl)+'</span>';
  document.getElementById('pos-n').textContent=d.fno_count||0;
  if(!ps.length){box.innerHTML='<div class="load">No open positions in HDFC1 / HDFC2. F&amp;O legs appear here live.</div>';return;}
  box.innerHTML=ps.map(p=>{
    const mtm=p.pnl||0,tag=p.product||'',ch=p.change_pct;
    const meta=[]; if(p.oi!=null)meta.push('OI '+kfmt(p.oi)); if(p.volume!=null)meta.push('Vol '+kfmt(p.volume));
    if(ch!=null)meta.push('<span class="'+cl(ch)+'">'+sp(ch)+'</span>');
    return '<div class="row" onclick="openShare(\''+(p.underlying||'')+'\')" style="cursor:pointer"><div style="flex:1;min-width:0">'
      +'<div class="rn">'+p.label+'  <span class="rsub" style="border:1px solid var(--n400);padding:0 4px">'+tag+'</span></div>'
      +'<div class="rsub" style="margin-top:3px">Qty '+p.quantity+' · Avg '+(p.average_price||0).toFixed(1)+' · LTP '+(p.last_price||0).toFixed(1)+'</div>'
      +(meta.length?'<div class="rsub mono" style="margin-top:3px;color:var(--n600)">'+meta.join('  ·  ')+'</div>':'')
      +'</div><div class="rr"><div class="p '+cl(mtm)+'">'+inr(mtm)+'</div><div class="c muted">'+p.holder+'</div></div></div>';
  }).join('');
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
  const hasScr=Object.keys(ff).length>0;
  let h='<div class="ssub">Screener fundamentals'+(hasScr?' · '+conf+' confidence':'')+'</div>';
  if(hasScr){h+='<div class="fgrid">'+g('P/E',ff.pe)+g('P/B',ff.pb)+g('ROE',ff.roe,'%')+g('D/E',ff.de)+g('Promoter',ff.promoter_holding,'%')+g('Pledge',ff.pledge,'%')+'</div>';
    if(ff.dividend_yield!=null)h+='<div class="fgrid" style="grid-template-columns:1fr">'+g('Dividend yield',ff.dividend_yield,'%')+'</div>';}
  else h+='<div class="fg" style="border:1px solid var(--n300)"><div class="k" style="color:var(--down)">not in Screener export</div><div class="rsub" style="margin-top:4px">Upload your Screener Premium sheet (classic dashboard) to see P/E, ROE, D/E, pledge…</div></div>';
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
  document.getElementById('tk-go').textContent='Review order';tkVal();
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
function closeTicket(){document.getElementById('tscrim').classList.remove('on');document.getElementById('tsheet').classList.remove('on');}
function tkReset(){TK.pid=null;document.getElementById('tk-go').textContent='Review order';}
function tkSide(s){TK.side=s;tkReset();document.querySelectorAll('#tsheet .tk-side').forEach(b=>b.classList.toggle('on',b.dataset.s===s));const st=document.getElementById('tk-stop');if(st&&TK.ltp)st.value=(TK.ltp*(s==='BUY'?0.95:1.05)).toFixed(2);}
function tkProd(el){TK.product=el.textContent.trim();tkReset();[...el.parentElement.children].forEach(b=>b.classList.toggle('on',b===el));}
function tkOt(v,el){TK.ot=v;tkReset();[...el.parentElement.children].forEach(b=>b.classList.toggle('on',b===el));document.getElementById('tk-price-wrap').style.display=v==='LIMIT'?'block':'none';tkVal();}
function tkQty(d){TK.qty=Math.max(1,TK.qty+d);document.getElementById('tk-qty').textContent=TK.qty;tkReset();tkVal();}
function tkUnits(){return TK.qty*(TK.seg==='FUT'?TK.lot:1);}
function tkVal(){const px=TK.ot==='LIMIT'?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;document.getElementById('tk-val').textContent=px?inr(tkUnits()*px):'';}
async function tkReview(){
  if(TK.pid){return tkConfirm();}
  const px=TK.ot==='LIMIT'?(+document.getElementById('tk-price').value||TK.ltp):TK.ltp;
  const fut=TK.seg==='FUT'&&TK.fut;
  const stop=+document.getElementById('tk-stop').value||0;
  const tgt=px?+((TK.side==='BUY'?px*1.1:px*0.9).toFixed(2)):0;
  const acct=(document.getElementById('tk-acct')||{}).value||angelKey();
  const order={creds_key:acct,exchange:TK.exch,symbol:fut?TK.fut.tradingsymbol:TK.sym,token:fut?TK.fut.token:'',side:TK.side,quantity:tkUnits(),product:TK.product,order_type:TK.ot,price:px,trigger_price:0,underlying:TK.sym,stop_loss:stop,target:tgt};
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
async function loadOrderBook(){const box=document.getElementById('ob-list');if(!box)return;const r=await j('/execution/log?'+Q);
  const ev=(r.ok&&r.d.events)||[];if(!ev.length){box.innerHTML='<div class="load">No orders yet.</div>';return;}
  box.innerHTML=ev.slice(0,20).map(e=>{const o=e.order||{},side=o.side||'';
    return '<div class="row"><div style="flex:1;min-width:0"><div class="rn">'+(o.symbol||e.event||'—')+' <span class="rsub">'+(o.quantity?o.quantity+' @ '+(o.price||'—'):'')+'</span></div><div class="rsub">'+((e.event||'').replace(/_/g,' '))+(o.risk_reward?' · R:R '+o.risk_reward:'')+'</div></div><div class="rr"><div class="c '+(side==='BUY'?'up':side==='SELL'?'down':'muted')+'">'+(side||'')+'</div></div></div>';}).join('');}
function renderHoldings(p){
  const box=document.getElementById('hold-list');if(!box)return;
  const rows=allHoldings(p).filter(x=>Math.abs(x.mv)>=1000).sort((a,b)=>b.mv-a.mv);
  document.getElementById('hold-n').textContent=rows.length+' · tap for Screener';
  box.innerHTML=rows.map(x=>'<div class="row" onclick="openShare(\''+x.s+'\')" style="cursor:pointer">'
    +'<div style="flex:1;min-width:0"><div class="rn">'+x.s+' <span class="rsub">'+(x.hold||'')+'</span></div></div>'
    +'<div class="rr"><div class="p">'+inr(x.mv)+'</div><div class="c '+cl(x.pct)+'">'+sp(x.pct)+'</div></div></div>').join('')||'<div class="load">no holdings</div>';
}
function angelKey(){const a=((PORT&&PORT.accounts)||[]).find(a=>((a.creds_key||'').toUpperCase()).startsWith('ANGEL'));return a?a.creds_key:(((PORT&&PORT.accounts&&PORT.accounts[0])||{}).creds_key||'ANGEL1');}
/* ---- income engine (covered calls + cash puts, guarded one-tap) ---- */
let INCOME_DATA={cc:[],cp:[]},incLoaded=0;
function istTab(t){const ideas=t==='ideas';
  document.getElementById('ist-ideas').classList.toggle('on',ideas);document.getElementById('ist-income').classList.toggle('on',!ideas);
  document.getElementById('ideas-panel').style.display=ideas?'':'none';document.getElementById('income-panel').style.display=ideas?'none':'';
  if(!ideas&&!incLoaded){incLoaded=1;loadIncomeT();}}
async function loadIncomeT(){
  const box=document.getElementById('income-list');const r=await j('/income/ideas?'+Q);
  if(!r.ok){box.innerHTML='<div class="load">could not load</div>';return;}
  const d=r.d,s=d.summary||{};INCOME_DATA={cc:d.covered_calls||[],cp:d.cash_secured_puts||[]};
  document.getElementById('inc-sum').textContent='+'+inr(s.total_premium||0)+' this cycle';
  const cc=INCOME_DATA.cc,cp=INCOME_DATA.cp;
  if(!cc.length&&!cp.length){box.innerHTML='<div class="load">No income setups — need an F&O holding of a full lot (calls) or cash (puts), and the chain live.</div>';return;}
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
  if(r.d.error){box.innerHTML='<div class="load">'+r.d.error+'</div>';return;}
  const ii=r.d.ideas||[];
  if(!ii.length){box.innerHTML='<div class="load">No high-conviction setups right now — the bar is intentionally high.</div>';return;}
  box.innerHTML=ii.map(i=>{
    const flag=(i.flags&&i.flags.length)?(i.flags[0].text||i.flags[0]):'';
    return '<div class="row" onclick="openShare(\''+i.symbol+'\')" style="flex-direction:column;align-items:stretch;gap:8px;cursor:pointer">'
      +'<div style="display:flex;align-items:baseline"><span class="rn" style="font-size:16px;font-weight:600">'+i.symbol+'</span>'
      +'<span class="rsub" style="margin-left:9px;border:1px solid var(--n400);padding:1px 6px">'+i.horizon+'</span>'
      +'<span class="mono" style="margin-left:auto;font-weight:600;color:var(--a700)">CONV '+i.conviction+'</span></div>'
      +'<div class="mono" style="display:flex;gap:16px;font-size:13px;flex-wrap:wrap"><span class="sec">Entry <b style="color:var(--text)">'+i.entry+'</b></span><span class="down">SL '+i.stop_loss+'</span><span class="up">TGT '+i.target+'</span><span class="sec">R:R <b style="color:var(--text)">'+i.reward_risk+'</b></span></div>'
      +(i.pattern?'<div class="rsub" style="color:var(--n600)">'+i.pattern.replace(/_/g,' ')+' · '+i.hit_rate+'% hit · avg '+(i.avg_return_pct>=0?'+':'')+i.avg_return_pct+'% over horizon</div>':'')
      +'<div class="rsub">F '+i.fundamental_score+' · T '+(i.technical_score!=null?i.technical_score:'—')+(flag?' · <span class="down">⚠ '+flag+'</span>':'')+'</div>'
      +'</div>';
  }).join('')+'<div class="pb rsub" style="color:var(--n500)">'+(r.d.note||'')+'</div>';
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
  const bz=document.getElementById('set-biz');if(bz)bz.href='/biz?'+Q;
  const lf=document.getElementById('set-life');if(lf)lf.href='/life?'+Q;
}
async function loadNews(){
  const box=document.getElementById('news-list');if(!PORT){box.innerHTML='<div class="load">load portfolio first</div>';return;}
  const top=allHoldings(PORT).sort((a,b)=>b.mv-a.mv).slice(0,6);let items=[];
  for(const x of top){const r=await j('/news/'+encodeURIComponent(x.s)+'?'+Q);if(r.ok&&r.d.news&&r.d.news.length)items.push({sym:x.s,...r.d.news[0]});}
  if(!items.length){box.innerHTML='<div class="load">no recent news</div>';return;}
  box.innerHTML=items.map(a=>'<a class="row" href="'+a.link+'" target="_blank" style="display:block"><div class="rn" style="font-size:13px;line-height:1.35">'+a.title+'</div><div class="rsub" style="margin-top:4px">'+a.sym+' · '+(a.source||'')+(a.when?' · '+a.when:'')+'</div></a>').join('');
}
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  const t=b.dataset.t;
  if(t==='login'){location.href='/login?'+Q;return;}
  document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));
  document.getElementById('s-'+t).classList.add('on');
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));window.scrollTo(0,0);
  if(t==='positions'){loadPositions();loadOrderBook();}
  if(t==='settings'&&!setLoaded){setLoaded=1;loadSettings();}
  if(t==='ideas'&&!ideasLoaded){ideasLoaded=1;loadIdeas();}
  if(t==='chart'){if(!chartLoaded){chartLoaded=1;chartChips();}loadChart();}
  if(t==='news'&&!newsLoaded){newsLoaded=1;loadNews();}});

/* single 30s heartbeat — refreshes header/portfolio/ticker + the active tab.
   Fetches are error-tolerant (keep last data on failure), so a server blip never
   blanks the screen; the next tick recovers automatically. */
async function heartbeat(){
  try{mktStatus();}catch(e){}
  try{await loadTicker();}catch(e){}
  try{await loadHome();}catch(e){}
  try{const on=document.querySelector('section.on');if(on&&on.id==='s-positions')loadPositions();}catch(e){}
}
document.getElementById('tk-price').addEventListener('input',tkVal);
heartbeat();setInterval(heartbeat,30000);
</script></body></html>"""
