"""Live system-status page (/status) — reads /health.json and proves life, never asserts it.

Same origin as the feed, so no CORS. Every tile shows a real heartbeat age: green =
reporting, amber = stale (>20 min), red = down (>24 h) or never seen. If the whole feed
is older than 24 h it's treated as dead with a banner. Refreshes every 30 s.
"""

STATUS_HTML = r"""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>System Status</title>
<style>
:root{--canvas:#07090d;--bg:#0b0e13;--panel:#11151c;--text:#dde3ea;
  --n200:#1d232d;--n300:#28303d;--n400:#3b475a;--n500:#75818f;--n600:#94a0af;--n700:#b6c0cc;
  --acc:#3f8cde;--up:#2ebd85;--down:#f0544c;--warn:#f0a13c;
  --fh:'IBM Plex Sans Condensed',system-ui,sans-serif;--fb:system-ui,-apple-system,sans-serif;--fm:ui-monospace,'SF Mono',Menlo,monospace;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--canvas);color:var(--text);font-family:var(--fb);font-size:14px;line-height:1.45;padding:0 16px 40px}
.wrap{max-width:820px;margin:0 auto}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums}
.lbl{font-family:var(--fh);text-transform:uppercase;letter-spacing:.12em;font-size:11px;color:var(--n600);font-weight:600}
.hdr{position:sticky;top:0;background:var(--canvas);padding:calc(env(safe-area-inset-top) + 16px) 0 12px;border-bottom:1px solid var(--n300);z-index:5}
.hti{font-family:var(--fh);font-weight:600;letter-spacing:.14em;font-size:15px}.hti b{color:var(--acc)}
.pulse{margin-top:6px;font-family:var(--fm);font-size:13px}
.banner{background:#3a1113;color:#f0a0a0;border:1px solid #7a2a2a;padding:9px 12px;margin:12px 0;font-family:var(--fm);font-size:12.5px;display:none}
.strip{display:grid;grid-template-columns:repeat(2,1fr);gap:1px;background:var(--n200);border:1px solid var(--n200);margin:14px 0}
@media(min-width:620px){.strip{grid-template-columns:repeat(4,1fr)}}
.sc{background:var(--panel);padding:11px 12px}
.sc .k{font-family:var(--fh);text-transform:uppercase;letter-spacing:.05em;font-size:9.5px;color:var(--n500)}
.sc .v{font-family:var(--fm);font-size:15px;font-weight:600;margin-top:4px}
.grid{display:grid;grid-template-columns:1fr;gap:8px;margin-top:6px}
@media(min-width:620px){.grid{grid-template-columns:1fr 1fr}}
.card{border:1px solid var(--n300);background:var(--panel);border-left:3px solid var(--n400);padding:12px 14px;display:flex;align-items:center;gap:12px}
.card.ok{border-left-color:var(--up)}.card.stale{border-left-color:var(--warn)}.card.down{border-left-color:var(--down)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--n500);flex:0 0 auto}
.dot.ok{background:var(--up)}.dot.stale{background:var(--warn)}.dot.down{background:var(--down)}
.cn{font-weight:600}.cs{margin-left:auto;text-align:right;font-family:var(--fm);font-size:12px}
.cs .st{text-transform:uppercase;letter-spacing:.05em;font-size:10px}
.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn)}.muted{color:var(--n500)}
.foot{margin-top:20px;color:var(--n500);font-family:var(--fm);font-size:11px;line-height:1.7}
a{color:var(--acc);text-decoration:none}
</style></head><body>
<div class="wrap">
  <div class="hdr"><div class="hti">SYSTEM<b>·</b>STATUS</div><div class="pulse" id="pulse">contacting server…</div></div>
  <div class="banner" id="banner"></div>
  <div class="strip" id="strip"></div>
  <div class="grid" id="grid"></div>
  <div class="foot">Proof-of-life feed — a tile is green only while the server keeps stamping it. Nothing here is hardcoded. <a href="/health.json">raw /health.json</a></div>
</div>
<script>
const LABELS={sector_map:'Sector map',holdings:'Holdings',share_page:'Share page',positions:'Positions · live',
  deep:'Deep analysis',income:'Income engine',charts:'Charts',execution:'Execution',agent:'Proactive agent'};
const ORDER=['agent','holdings','positions','sector_map','deep','income','charts','share_page','execution'];
function ageMin(iso){if(!iso)return null;const t=Date.parse(iso);if(isNaN(t))return null;return (Date.now()-t)/60000;}
function fmtAge(m){if(m==null)return 'no signal';if(m<1)return 'just now';if(m<60)return Math.round(m)+'m ago';if(m<1440)return Math.round(m/60)+'h ago';return Math.round(m/1440)+'d ago';}
function cls(m){if(m==null)return 'down';if(m<=20)return 'ok';if(m<=1440)return 'stale';return 'down';}
function mktOpen(){const p=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
  const g=t=>p.find(x=>x.type===t).value;const wd=g('weekday'),hm=+g('hour')*60+ +g('minute');
  return ['Mon','Tue','Wed','Thu','Fri'].includes(wd)&&hm>=555&&hm<=930;}
async function load(){
  let d;try{const r=await fetch('/health.json',{cache:'no-store'});d=await r.json();}catch(e){
    document.getElementById('pulse').innerHTML='<span class="down">● NO CONNECTION — server unreachable</span>';return;}
  const mods=d.modules||{};const feedAge=ageMin(d.ts);
  const reporting=ORDER.filter(k=>{const a=ageMin((mods[k]||{}).last);return a!=null&&a<=20;}).length;
  const dead=feedAge!=null&&feedAge>1440;
  const b=document.getElementById('banner');
  if(dead){b.style.display='block';b.textContent='⚠ Feed is '+fmtAge(feedAge)+' old — treat the whole system as DOWN until it refreshes.';}
  else b.style.display='none';
  const openMkt=mktOpen();
  document.getElementById('pulse').innerHTML=dead?'<span class="down">● SNAPSHOT — no proof of life</span>'
    :('<span class="'+(reporting>=ORDER.length?'up':(reporting>0?'warn':'down'))+'">● '+reporting+'/'+ORDER.length+' modules reporting</span> · '+(openMkt?'market open':'market closed'));
  document.getElementById('strip').innerHTML=[
    ['Market',openMkt?'<span class="up">OPEN</span>':'<span class="muted">CLOSED</span>'],
    ['HDFC 2FA',d.hdfc_session?'<span class="up">done</span>':'<span class="down">NOT DONE</span>'],
    ['Angel feed',d.angel_session?'<span class="up">live</span>':'<span class="down">off</span>'],
    ['Health as-of',(d.ts||'—').slice(11,19)],
  ].map(([k,v])=>'<div class="sc"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>').join('');
  document.getElementById('grid').innerHTML=ORDER.map(k=>{const a=ageMin((mods[k]||{}).last);const c=cls(a);
    const st=c==='ok'?'reporting':(c==='stale'?'stale':'down');
    return '<div class="card '+c+'"><span class="dot '+c+'"></span><span class="cn">'+(LABELS[k]||k)+'</span>'
      +'<span class="cs"><div class="st '+(c==='ok'?'up':(c==='stale'?'warn':'down'))+'">'+st+'</div><div class="muted">'+fmtAge(a)+'</div></span></div>';}).join('');
}
load();setInterval(load,30000);
</script></body></html>"""
