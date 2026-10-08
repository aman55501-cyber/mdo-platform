"""Self-contained interactive prototype served at /preview (mock data, no auth).

A design reference the user can open on their own domain. Not wired to live data;
once approved its layout is ported into the real dashboard at /.
"""

PREVIEW_HTML = r'''<title>Shares CFO — prototype</title>
<style>
  :root{color-scheme:dark;
    --bg:#0a0e17;--panel:#111826;--elev:#18202f;--bd:#243049;--hair:#1b2333;
    --tx:#e9eef7;--dim:#8493ab;--faint:#5b6a83;
    --acc:#4c8dff;--up:#2fbd85;--down:#ff5867;--warn:#e0a53a;--purp:#a78bfa;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif}
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  body{background:var(--bg);color:var(--tx);font-family:var(--sans);font-size:15px;line-height:1.45;-webkit-font-smoothing:antialiased}
  .app{max-width:460px;margin:0 auto;padding:14px 14px 92px;min-height:100vh}
  .mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
  .dim{color:var(--dim)}.faint{color:var(--faint)}.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn)}
  .card{background:var(--panel);border:1px solid var(--bd);border-radius:16px;padding:16px;margin-bottom:12px}
  .lbl{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:600}
  .h2{font-weight:700;font-size:15px}.frag{font-size:10.5px;color:var(--acc);border:1px solid rgba(76,141,255,.4);border-radius:6px;padding:2px 7px;font-weight:700}
  .rowline{display:flex;justify-content:space-between;align-items:baseline;margin-top:11px}
  .bar{display:flex;align-items:center;justify-content:space-between;padding:4px 2px 12px}
  .brand{display:flex;align-items:center;gap:9px;font-weight:700}
  .brand .mark{width:26px;height:26px;border-radius:7px;background:linear-gradient(150deg,var(--acc),#2f6bd0);display:grid;place-items:center;font-size:14px}
  .pill{font-size:11.5px;font-weight:600;padding:5px 10px;border-radius:999px;border:1px solid var(--bd);display:inline-flex;align-items:center;gap:6px;color:var(--dim)}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--up)}
  /* hero */
  .nw{font-size:38px;font-weight:800;letter-spacing:-1px;margin-top:3px}
  .spark{width:100%;height:42px;display:block;margin-top:10px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
  .stat .v{font-size:17px;font-weight:700;margin-top:1px}
  /* meters */
  .meterrow{display:flex;align-items:center;gap:12px;margin-top:12px}.meterrow .name{width:92px;flex:none}
  .meter{flex:1;height:9px;border-radius:5px;background:var(--elev);overflow:hidden}.meter>i{display:block;height:100%;border-radius:5px}
  .score{width:40px;text-align:right;font-weight:700}
  .counts{display:flex;gap:16px;margin-top:14px;padding-top:13px;border-top:1px solid var(--hair)}.counts b{font-size:19px;font-weight:800;font-family:var(--mono)}
  .chip{font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:3px 7px;border-radius:6px;text-transform:uppercase}
  .chip.s{background:rgba(47,189,133,.14);color:var(--up)}.chip.n{background:rgba(132,147,171,.14);color:var(--dim)}.chip.w{background:rgba(255,88,103,.14);color:var(--down)}
  .filters{display:flex;gap:8px;overflow-x:auto;padding:2px 0 10px;scrollbar-width:none}.filters::-webkit-scrollbar{display:none}
  .fchip{flex:none;font-size:13px;font-weight:600;padding:7px 13px;border-radius:999px;border:1px solid var(--bd);color:var(--dim);background:transparent}
  .fchip[aria-pressed="true"]{background:var(--acc);border-color:var(--acc);color:#04122b}
  /* holdings */
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
  .volbar{height:5px;border-radius:3px;background:var(--elev);margin-top:6px;overflow:hidden}.volbar>i{display:block;height:100%;border-radius:3px}
  .actions{display:flex;gap:8px;padding:12px 13px 13px;background:var(--panel)}
  .btn{flex:1;border:0;border-radius:10px;padding:11px 0;font-weight:700;font-size:14px;font-family:var(--sans)}
  .buy{background:var(--up);color:#04160e}.sell{background:var(--down);color:#210407}.hedge{background:var(--acc);color:#04122b}
  .btn:active{transform:translateY(1px)}
  /* regime + ideas */
  .regbadge{display:inline-flex;gap:7px;align-items:center;font-weight:800;font-size:14px;padding:7px 13px;border-radius:999px}
  .signals{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:11px;overflow:hidden;margin-top:13px}
  .sig{background:var(--panel);padding:10px}.sig .n{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);font-weight:600}.sig .v{font-size:15px;font-weight:800;margin-top:3px;font-family:var(--mono)}
  .idea{border:1px solid var(--bd);border-radius:14px;overflow:hidden;margin-bottom:11px;background:var(--panel)}
  .itop{display:flex;align-items:center;gap:10px;padding:13px 14px 11px}
  .conv{width:44px;height:44px;border-radius:11px;display:grid;place-items:center;font-weight:800;font-size:17px;font-family:var(--mono);flex:none;background:rgba(47,189,133,.13);color:var(--up);border:1px solid rgba(47,189,133,.3)}
  .isym{font-weight:800;font-size:16px}.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:3px}
  .tag{font-size:10px;font-weight:700;padding:2px 7px;border-radius:5px;text-transform:uppercase}
  .tag.pos{background:rgba(76,141,255,.14);color:var(--acc)}.tag.st{background:rgba(224,165,58,.14);color:var(--warn)}.tag.hg{background:rgba(167,139,250,.16);color:var(--purp)}.tag.pat{background:rgba(132,147,171,.14);color:var(--dim)}
  .why{padding:0 14px 12px;font-size:12.5px;color:var(--dim);line-height:1.55}.why b{color:var(--tx)}
  .confl{display:flex;gap:6px;padding:0 14px 12px;flex-wrap:wrap}.cf{font-size:11px;font-weight:600;padding:3px 8px;border-radius:999px;background:var(--elev);border:1px solid var(--bd)}.cf.ok::before{content:"✓ ";color:var(--up)}
  .plan{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1px;background:var(--hair);border-top:1px solid var(--hair)}
  .p{background:var(--panel);padding:10px 8px;text-align:center}.p .k{font-size:9.5px;text-transform:uppercase;color:var(--faint);font-weight:600}.p .v{font-size:14px;font-weight:800;margin-top:2px;font-family:var(--mono)}
  .iact{display:flex;gap:8px;padding:11px 14px 13px}
  .ghost{background:var(--elev);border:1px solid var(--bd);color:var(--tx)}
  /* exposure */
  .barstack{display:flex;height:12px;border-radius:6px;overflow:hidden;margin-top:12px;background:var(--elev)}
  .glob{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:12px;overflow:hidden;margin-top:12px}
  .g{background:var(--panel);padding:10px 12px}.g .n{font-size:12px;color:var(--dim)}.g .v{font-size:15.5px;font-weight:700;margin-top:2px;font-family:var(--mono)}
  .hedgebtns{display:flex;gap:8px;margin-top:14px}.hb{flex:1;border:1px solid var(--bd);background:var(--elev);color:var(--tx);border-radius:10px;padding:10px 0;font-weight:700;font-size:13px}.hb.on{background:var(--acc);border-color:var(--acc);color:#04122b}
  .big{font-size:26px;font-weight:800;letter-spacing:-.5px;margin-top:4px}
  /* trades */
  .tr{display:flex;gap:10px;align-items:center;padding:11px 0;border-top:1px solid var(--hair)}
  .side{font-size:10.5px;font-weight:800;padding:3px 7px;border-radius:6px;flex:none}
  .side.b{background:rgba(47,189,133,.15);color:var(--up)}.side.s{background:rgba(255,88,103,.15);color:var(--down)}.side.h{background:rgba(76,141,255,.15);color:var(--acc)}
  .stt{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:6px;margin-left:auto;flex:none}
  .stt.placed{background:rgba(47,189,133,.15);color:var(--up)}.stt.blocked{background:rgba(224,165,58,.15);color:var(--warn)}.stt.prop{background:rgba(132,147,171,.15);color:var(--dim)}
  .note{font-size:11.5px;color:var(--faint);margin-top:10px;line-height:1.5}
  /* bottom nav */
  .nav{position:fixed;left:0;right:0;bottom:0;z-index:15;max-width:460px;margin:0 auto;background:rgba(13,18,28,.92);backdrop-filter:blur(12px);border-top:1px solid var(--bd);display:grid;grid-template-columns:repeat(4,1fr);padding:8px 6px calc(8px + env(safe-area-inset-bottom))}
  .nav button{background:0;border:0;color:var(--faint);font-family:var(--sans);font-size:10.5px;font-weight:600;display:flex;flex-direction:column;align-items:center;gap:4px;padding:4px 0}
  .nav button svg{width:22px;height:22px}
  .nav button[aria-current="true"]{color:var(--acc)}
  /* sheets */
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
  h1.screen{font-size:20px;font-weight:800;margin:2px 2px 12px}
  section{display:none}section.on{display:block}
  @media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div class="app">
  <div class="bar">
    <div class="brand"><span class="mark">&#8377;</span>Shares CFO</div>
    <span class="pill"><span class="dot"></span>Book complete · 6/6</span>
  </div>

  <!-- ===== PORTFOLIO ===== -->
  <section id="s-home" class="on">
    <div class="card">
      <div class="lbl">Consolidated net worth</div>
      <div class="nw mono">₹5.99 Cr</div>
      <div class="up mono" style="font-weight:700;margin-top:2px">▲ ₹1.84 L &nbsp;+0.31% today</div>
      <canvas class="spark" id="spark" width="920" height="84" aria-hidden="true"></canvas>
      <div class="grid2">
        <div class="stat"><div class="lbl">Unrealised P&amp;L</div><div class="v up mono">+₹1.12 Cr <span class="dim" style="font-size:13px">+23%</span></div></div>
        <div class="stat"><div class="lbl">Cash / margin</div><div class="v mono">₹42.6 L</div></div>
        <div class="stat"><div class="lbl">Invested</div><div class="v mono">₹4.87 Cr</div></div>
        <div class="stat"><div class="lbl">F&amp;O realised</div><div class="v up mono">+₹38,400</div></div>
      </div>
    </div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="lbl">Book strength</span><span class="faint" style="font-size:11px">Screener + technicals</span></div>
      <div class="meterrow"><span class="name">Fundamental</span><span class="meter"><i style="width:58%;background:linear-gradient(90deg,var(--warn),#e8b95e)"></i></span><span class="score warn mono">58</span></div>
      <div class="meterrow"><span class="name">Technical</span><span class="meter"><i style="width:71%;background:linear-gradient(90deg,var(--up),#5fd8a6)"></i></span><span class="score up mono">71</span></div>
      <div class="counts"><div><b class="up">4</b> <span class="dim">strong</span></div><div><b class="warn">4</b> <span class="dim">neutral</span></div><div><b class="down">2</b> <span class="dim">weak</span></div></div>
    </div>
    <div style="display:flex;align-items:baseline;justify-content:space-between;margin:4px 2px 10px"><span class="lbl">Holdings</span><span class="faint" style="font-size:11px">tap for numbers &amp; actions</span></div>
    <div class="filters" id="filters"><button class="fchip" aria-pressed="true">All</button><button class="fchip" aria-pressed="false">Strong</button><button class="fchip" aria-pressed="false">Weak</button><button class="fchip" aria-pressed="false">Vol surge</button></div>
    <div class="holds" id="holds"></div>
  </section>

  <!-- ===== IDEAS ===== -->
  <section id="s-ideas">
    <h1 class="screen">High-conviction ideas</h1>
    <div class="card" style="background:linear-gradient(160deg,#15110a,#111826);border-color:#3a2f18">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Market regime</span><span class="frag">drives sizing</span></div>
      <div style="margin-top:12px"><span class="regbadge" style="background:rgba(224,165,58,.14);color:var(--warn)">⚠ CAUTIOUS</span></div>
      <div class="signals"><div class="sig"><div class="n">India VIX</div><div class="v warn">14.8 ▲</div></div><div class="sig"><div class="n">Breadth</div><div class="v warn">0.82</div></div><div class="sig"><div class="n">NIFTY vs 200D</div><div class="v up">+3.1%</div></div></div>
      <div class="note">Trend up but volatility rising, breadth weak → <b class="warn">new risk capped at 50%</b>, quality favoured.</div>
    </div>
    <div style="display:flex;justify-content:space-between;margin:2px 2px 10px"><span class="lbl">Ideas today</span><span class="faint" style="font-size:11px">3 passed of 41 scanned</span></div>
    <div id="ideas"></div>
  </section>

  <!-- ===== HEDGE / EXPOSURE ===== -->
  <section id="s-hedge">
    <h1 class="screen">Exposure &amp; hedge</h1>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Exposure</span><span class="frag">domestic + global</span></div>
      <div class="lbl" style="margin-top:12px">Net long — Indian equities</div>
      <div class="big mono up">₹5.57 Cr <span class="dim" style="font-size:14px;font-weight:600">93% invested</span></div>
      <div class="barstack"><span style="width:78%;background:var(--up)"></span><span style="width:7%;background:var(--down)"></span><span style="width:15%;background:var(--elev)"></span></div>
      <div class="rowline"><span class="dim">Equity long <span class="up">●</span></span><span class="mono">₹5.99 Cr</span></div>
      <div class="rowline"><span class="dim">F&amp;O net <span class="down">●</span></span><span class="mono down">−₹42 L notional</span></div>
      <div class="rowline"><span class="dim">Cash / margin</span><span class="mono">₹42.6 L</span></div>
      <div class="rowline"><span class="dim">Portfolio beta</span><span class="mono">1.08</span></div>
      <div class="lbl" style="margin-top:16px">Global backdrop</div>
      <div class="glob"><div class="g"><div class="n">S&amp;P 500</div><div class="v up">+0.4%</div></div><div class="g"><div class="n">Nasdaq</div><div class="v up">+0.7%</div></div><div class="g"><div class="n">Brent</div><div class="v down">−1.2% · $71</div></div><div class="g"><div class="n">USD/INR</div><div class="v warn">83.4 ▲</div></div><div class="g"><div class="n">Gold</div><div class="v up">+0.6%</div></div><div class="g"><div class="n">India VIX</div><div class="v warn">14.8 ▲</div></div></div>
    </div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Portfolio hedge</span><span class="frag">NIFTY futures</span></div>
      <div class="note" style="margin-top:6px">93% net long, beta 1.08. A 10% fall ≈ <b class="down">−₹64.7 L</b> unhedged.</div>
      <div class="hedgebtns"><button class="hb" onclick="setHedge(this,25)">25%</button><button class="hb on" onclick="setHedge(this,50)">50%</button><button class="hb" onclick="setHedge(this,100)">100%</button></div>
      <div class="rowline"><span class="dim">Hedge <span id="hpct">50</span>% of ₹5.99 Cr</span><span class="mono" id="hval">₹3.23 Cr</span></div>
      <div class="rowline"><span class="dim">Sell NIFTY futures</span><span class="mono down" style="font-weight:700" id="hlots">18 lots (1,350)</span></div>
      <div class="rowline"><span class="dim">Margin (≈)</span><span class="mono" id="hmar">₹32.6 L</span></div>
      <button class="btn hedge" style="width:100%;margin-top:14px" onclick="hedgeTicket()">Review hedge order →</button>
    </div>
  </section>

  <!-- ===== TRADES ===== -->
  <section id="s-trades">
    <h1 class="screen">Trade log</h1>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center"><span class="h2">Today</span><span class="dim mono" id="today">19 Jul</span></div>
      <div class="rowline"><span class="dim">Realised today</span><span class="mono up" style="font-weight:700">+₹12,400</span></div>
      <div class="rowline"><span class="dim">Open risk (Σ stops)</span><span class="mono down">−₹14,900</span></div>
      <div class="tr"><span class="side b">BUY</span><div><div style="font-weight:600">GLENMARK <span class="dim" style="font-size:12px">40 @ ₹2,410</span></div><div class="dim" style="font-size:11.5px">SL 2,289 · tgt 2,651 · R:R 2.0</div></div><span class="stt placed">PLACED</span></div>
      <div class="tr"><span class="side h">HEDGE</span><div><div style="font-weight:600">NIFTY FUT <span class="dim" style="font-size:12px">−18 lots</span></div><div class="dim" style="font-size:11.5px">hedge 50% · @ 24,150</div></div><span class="stt prop">PROPOSED</span></div>
      <div class="tr"><span class="side s">SELL</span><div><div style="font-weight:600">SARVESHWAR <span class="dim" style="font-size:12px">10000 @ ₹6.20</span></div><div class="dim" style="font-size:11.5px">exit — pledge 34% flag</div></div><span class="stt blocked">TRADING OFF</span></div>
      <div class="note">Every proposal + placement is logged to an immutable audit file — time, price, R:R, guardrail result. Your daily record.</div>
    </div>
    <div class="card">
      <div class="h2">This week</div>
      <div class="rowline"><span class="dim">Trades</span><span class="mono">7</span></div>
      <div class="rowline"><span class="dim">Win rate</span><span class="mono up">57%</span></div>
      <div class="rowline"><span class="dim">Net P&amp;L</span><span class="mono up">+₹41,200</span></div>
      <div class="rowline"><span class="dim">Best / worst</span><span class="mono">+₹18k / −₹7k</span></div>
    </div>
  </section>
</div>

<!-- bottom nav -->
<nav class="nav" id="nav">
  <button data-t="home" aria-current="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>Portfolio</button>
  <button data-t="ideas"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0012 3z"/></svg>Ideas</button>
  <button data-t="hedge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/></svg>Hedge</button>
  <button data-t="trades"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V5M4 15l5-5 4 3 7-8"/></svg>Trades</button>
</nav>

<!-- trade ticket -->
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
  <div class="guard"><span style="font-size:15px">🔒</span><div><b>Trading is OFF.</b> Validated against every guardrail (qty, value, risk ≤ ₹5k, stop mandatory) but won't send until you arm the master switch + wire the broker. <b>Angel can go live now; HDFC needs its order doc.</b></div></div>
  <button class="confirm" id="tk-confirm" disabled>Arm trading to confirm →</button>
</div>

<script>
const rupee=n=>(n>=1e7?'₹'+(n/1e7).toFixed(2)+' Cr':n>=1e5?'₹'+(n/1e5).toFixed(2)+' L':'₹'+Math.round(n).toLocaleString('en-IN'));
const H=[
 {sym:'NSIL',qty:100,avg:8110,ltp:7900,day:-0.9,vol:0.8,rsi:44,pe:41,de:0.10,roe:12,v:'neutral',f:'NEUTRAL',t:'NEUTRAL'},
 {sym:'GLENMARK',qty:200,avg:2300,ltp:2410,day:2.1,vol:2.3,rsi:64,pe:34,de:0.15,roe:14,v:'strong',f:'STRONG',t:'STRONG'},
 {sym:'THOMASCOOK',qty:2000,avg:111,ltp:128,day:1.1,vol:1.2,rsi:61,pe:40,de:0.55,roe:9,v:'neutral',f:'NEUTRAL',t:'STRONG'},
 {sym:'TRENT',qty:10,avg:2931,ltp:5985,day:1.2,vol:1.4,rsi:68,pe:118,de:0.42,roe:22,v:'neutral',f:'WEAK',t:'STRONG',flag:'expensive P/E 118'},
 {sym:'SARVESHWAR',qty:10000,avg:6.75,ltp:6.20,day:-1.5,vol:3.1,rsi:39,pe:22,de:0.9,roe:11,v:'weak',f:'WEAK',t:'WEAK',flag:'promoter pledge 34%'},
 {sym:'INDHOTEL',qty:50,avg:663,ltp:780,day:0.8,vol:0.9,rsi:58,pe:62,de:0.30,roe:15,v:'neutral',f:'NEUTRAL',t:'STRONG'},
 {sym:'PRAJIND',qty:500,avg:350,ltp:402,day:0.9,vol:1.1,rsi:60,pe:38,de:0.05,roe:18,v:'strong',f:'STRONG',t:'STRONG'},
 {sym:'POKARNA',qty:10,avg:940,ltp:1020,day:1.8,vol:1.6,rsi:66,pe:24,de:0.35,roe:19,v:'strong',f:'STRONG',t:'STRONG'},
 {sym:'HAWKINCOOK',qty:1,avg:7542,ltp:8200,day:0.4,vol:0.7,rsi:55,pe:45,de:0.20,roe:30,v:'strong',f:'STRONG',t:'NEUTRAL'},
 {sym:'TATAGOLD',qty:2000,avg:13.70,ltp:14.10,day:0.6,vol:1.0,rsi:57,etf:true,v:'neutral',f:'—',t:'STRONG'},
];
const cc={STRONG:'s',NEUTRAL:'n',WEAK:'w','—':'n'};
const volColor=x=>x>=2?'var(--acc)':x>=1?'var(--up)':'var(--dim)';
function holdRow(h){
  const mv=h.qty*h.ltp,pnl=h.qty*(h.ltp-h.avg),gp=pnl>=0;
  const cell=(k,d,note,c,style)=>`<div class="m"><div class="k">${k}</div><div class="d${c?' '+c:''}"${style||''}>${d}</div>${note?`<div class="note ${c||'dim'}">${note}</div>`:''}</div>`;
  let met='';
  met+=cell('Price action',(h.day>=0?'+':'')+h.day+'%','LTP ₹'+h.ltp.toLocaleString('en-IN'),h.day>=0?'up':'down');
  met+=cell('Volume 20d',h.vol.toFixed(1)+'×',h.vol>=2?'surge':'normal','',` style="color:${volColor(h.vol)}"`);
  met+=cell('RSI 14',h.rsi,h.rsi>70?'overbought':h.rsi<35?'oversold':'neutral',h.rsi>70?'warn':h.rsi<35?'down':'');
  if(!h.etf){met+=cell('P/E',h.pe,h.pe>60?'rich':h.pe<20?'cheap':'fair',h.pe>60?'down':'');
    met+=cell('Debt/Eq',h.de,h.de>1?'high':'low',h.de>1?'down':'up');
    met+=cell('ROE',h.roe+'%',h.roe>=15?'strong':'ok',h.roe>=15?'up':'');}
  else{met+=cell('Type','ETF','gold tracker','');met+=cell('','','');}
  const flag=h.flag?`<span class="down" style="font-size:11px">● ${h.flag}</span>`:'';
  return `<div class="h ${h.v}" data-v="${h.v}" data-vol="${h.vol}"><div class="htop" onclick="tog(this)">
    <span class="sev"></span><div><div class="sym">${h.sym} <span class="chip ${cc[h.f]}">F ${h.f}</span> <span class="chip ${cc[h.t]}">T ${h.t}</span></div>
    <div class="sub">${h.qty.toLocaleString('en-IN')} @ ₹${h.avg.toLocaleString('en-IN')} ${flag}</div></div>
    <div class="right"><div class="val mono">${rupee(mv)}</div><div class="mono ${gp?'up':'down'}" style="font-size:12.5px">${gp?'+':''}${rupee(pnl)}</div></div>
    <svg class="chev" width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg></div>
    <div class="detail"><div class="metrics">${met}</div><div class="actions">
      <button class="btn buy" onclick="ticket('BUY','${h.sym}',${h.ltp})">Buy</button>
      <button class="btn sell" onclick="ticket('SELL','${h.sym}',${h.ltp})">Sell</button>
      <button class="btn hedge" onclick="go('hedge')">Hedge</button></div></div></div>`;
}
document.getElementById('holds').innerHTML=H.map(holdRow).join('');
function tog(el){el.parentElement.classList.toggle('open');}

const IDEAS=[
 {conv:88,sym:'PRAJIND',cls:'pos',ctag:'Positional',pat:'200-DMA reclaim',why:'reclaimed its 200-DMA 4 sessions ago on <b>1.9× volume</b>, fundamentals STRONG (ROE 18%, D/E 0.05), pattern <b>61% hit-rate</b> over 6 yrs.',cf:['Fundamentals 82','Pattern','Volume 1.9×','Regime-fit'],e:'₹402',s:'₹380',tg:'₹446',rr:'2.0'},
 {conv:84,sym:'GLENMARK',cls:'st',ctag:'Short-term',pat:'Oversold-in-uptrend',why:'RSI dipped to 34 while above the 200-DMA — pullback in an uptrend on a <b>volume surge (2.3×)</b>. Hit-rate <b>58%</b>, avg hold 7 sessions.',cf:['Fundamentals 84','RSI 34','Volume 2.3×','Above 200-DMA'],e:'₹2,410',s:'₹2,300',tg:'₹2,630',rr:'2.0'},
 {conv:79,sym:'NIFTY — Bull Call Spread',cls:'hg',ctag:'Hedged',pat:'Defined-risk',purp:1,why:'trend up but VIX elevated → a defined-risk debit spread beats naked longs. Buy 24,200 CE / sell 24,600 CE.',cf:['Trend up','Defined risk','VIX-fit'],e:'Debit ₹9,750',s:'Max ₹9,750',tg:'₹20,250',rr:'2.1'},
];
document.getElementById('ideas').innerHTML=IDEAS.map(i=>`<div class="idea"><div class="itop">
  <div class="conv"${i.purp?' style="background:rgba(167,139,250,.14);color:var(--purp);border-color:rgba(167,139,250,.3)"':''}>${i.conv}</div>
  <div><div class="isym">${i.sym}</div><div class="tags"><span class="tag ${i.cls}">${i.ctag}</span><span class="tag pat">${i.pat}</span></div></div></div>
  <div class="why"><b>Why it fired:</b> ${i.why}</div>
  <div class="confl">${i.cf.map(c=>`<span class="cf ok">${c}</span>`).join('')}</div>
  <div class="plan"><div class="p"><div class="k">Entry</div><div class="v">${i.e}</div></div><div class="p"><div class="k">Stop</div><div class="v down">${i.s}</div></div><div class="p"><div class="k">Target</div><div class="v up">${i.tg}</div></div><div class="p"><div class="k">R:R</div><div class="v">${i.rr}</div></div></div>
  <div class="iact"><button class="btn buy" onclick="ticket('BUY','${i.sym.split(' ')[0]}',${parseFloat(i.e.replace(/[^0-9.]/g,''))||402})">Trade this →</button><button class="btn ghost" onclick="go('trades')">Backtest</button></div></div>`).join('');

// nav
function go(t){
  document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));
  document.getElementById('s-'+t).classList.add('on');
  document.querySelectorAll('#nav button').forEach(b=>b.setAttribute('aria-current',b.dataset.t===t?'true':'false'));
  window.scrollTo(0,0);
}
document.getElementById('nav').addEventListener('click',e=>{const b=e.target.closest('button');if(b)go(b.dataset.t);});

// filters
document.getElementById('filters').addEventListener('click',e=>{const b=e.target.closest('.fchip');if(!b)return;[...document.querySelectorAll('.fchip')].forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');const f=b.textContent;
  document.querySelectorAll('#holds .h').forEach(h=>{const v=h.dataset.v,vol=parseFloat(h.dataset.vol);let s=true;if(f==='Strong')s=v==='strong';else if(f==='Weak')s=v==='weak';else if(f==='Vol surge')s=vol>=2;h.style.display=s?'':'none';});});

// hedge sizing
function setHedge(el,p){document.querySelectorAll('.hb').forEach(x=>x.classList.remove('on'));el.classList.add('on');
  const val=5.99e7*p/100,lots=Math.round(val*1.08/(24150*75)),margin=lots*75*24150*0.12;
  document.getElementById('hpct').textContent=p;document.getElementById('hval').textContent=rupee(val);
  document.getElementById('hlots').textContent=lots+' lots ('+(lots*75).toLocaleString('en-IN')+')';
  document.getElementById('hmar').textContent=rupee(margin);}
function hedgeTicket(){const l=document.getElementById('hlots').textContent;ticket('HEDGE','NIFTY FUT',24150,l);}

// ticket
const scrim=document.getElementById('scrim'),sheet=document.getElementById('sheet');
function ticket(side,sym,ltp,extra){
  const s=document.getElementById('tk-side');s.textContent=side;
  s.style.background=side==='BUY'?'rgba(47,189,133,.16)':side==='SELL'?'rgba(255,88,103,.16)':'rgba(76,141,255,.16)';
  s.style.color=side==='BUY'?'var(--up)':side==='SELL'?'var(--down)':'var(--acc)';
  document.getElementById('tk-sym').textContent=sym;document.getElementById('tk-ltp').textContent='₹'+ltp.toLocaleString('en-IN');
  const stop=+(ltp*0.95).toFixed(2),tgt=+(ltp*1.10).toFixed(2),qty=extra||Math.max(1,Math.floor(5000/(ltp-stop)))+' sh';
  const q=extra?18*75:Math.max(1,Math.floor(5000/(ltp-stop)));
  document.getElementById('tk-qty').textContent=extra?extra:qty;
  document.getElementById('tk-entry').innerHTML='₹'+ltp.toLocaleString('en-IN')+' &nbsp;<span class="faint">LIMIT</span>';
  document.getElementById('tk-stop').innerHTML='₹'+stop.toLocaleString('en-IN')+' &nbsp;−5.0%';
  document.getElementById('tk-tgt').innerHTML='₹'+tgt.toLocaleString('en-IN')+' &nbsp;+10.0%';
  const risk=q*(ltp-stop),rew=q*(tgt-ltp);
  document.getElementById('tk-risk').textContent=rupee(risk);document.getElementById('tk-rew').textContent=rupee(rew);document.getElementById('tk-rr').textContent=(rew/risk).toFixed(1);
  scrim.classList.add('on');sheet.classList.add('on');
}
scrim.addEventListener('click',()=>{scrim.classList.remove('on');sheet.classList.remove('on');});

// sparkline
(function(){const c=document.getElementById('spark');if(!c)return;const x=c.getContext('2d'),W=c.width,Hh=c.height,n=30,pts=[];let v=.78;
 for(let i=0;i<n;i++){v+=Math.sin(i/3)*.006+.0075+(i%5===0?-.004:.002);pts.push(v);}
 const mn=Math.min(...pts),mx=Math.max(...pts),X=i=>i/(n-1)*W,Y=val=>Hh-6-((val-mn)/(mx-mn))*(Hh-14);
 x.beginPath();pts.forEach((p,i)=>{i?x.lineTo(X(i),Y(p)):x.moveTo(X(i),Y(p));});x.lineTo(W,Hh);x.lineTo(0,Hh);x.closePath();
 const g=x.createLinearGradient(0,0,0,Hh);g.addColorStop(0,'rgba(47,189,133,.28)');g.addColorStop(1,'rgba(47,189,133,0)');x.fillStyle=g;x.fill();
 x.beginPath();pts.forEach((p,i)=>{i?x.lineTo(X(i),Y(p)):x.moveTo(X(i),Y(p));});x.strokeStyle='#2fbd85';x.lineWidth=2.2;x.lineJoin='round';x.stroke();
 x.beginPath();x.arc(X(n-1),Y(pts[n-1]),3.4,0,7);x.fillStyle='#2fbd85';x.fill();})();
</script>
'''
