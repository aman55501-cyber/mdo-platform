"""Business OS console — imported tenders / receivables / hotel / cash, terminal-styled.

Served at /biz. Shares the Market Console aesthetic. Reads the business datasets you
import (Excel/CSV) via /business/* and renders KPIs + tables, with an Import screen
to upload/replace each dataset. Token-gated like everything else.
"""

BIZ_HTML = r"""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Business OS</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{--canvas:#07090d;--bg:#0b0e13;--panel:#11151c;--text:#dde3ea;
  --n100:#151a22;--n200:#1d232d;--n300:#28303d;--n400:#3b475a;--n500:#75818f;--n600:#94a0af;--n700:#b6c0cc;
  --acc:#3f8cde;--a700:#82b4ec;--up:#2ebd85;--down:#f0544c;--warn:#f0a13c;
  --fh:'IBM Plex Sans Condensed',sans-serif;--fb:'IBM Plex Sans',sans-serif;--fm:'IBM Plex Mono',monospace;}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--canvas);color:var(--text);font-family:var(--fb);font-size:14px;line-height:1.45}
.mono{font-family:var(--fm);font-variant-numeric:tabular-nums}.muted{color:var(--n500)}.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn)}
.app{width:100%;max-width:520px;margin:0 auto;background:var(--bg);min-height:100vh;padding-bottom:96px}
@media(min-width:740px){.app,.tabs,.hdr{max-width:900px}.wrap{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}.span2{grid-column:1/-1}}
.hdr{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--n300);display:flex;align-items:center;justify-content:space-between;padding:calc(env(safe-area-inset-top) + 11px) 16px 11px}
.hti{font-family:var(--fh);font-weight:600;letter-spacing:.14em;font-size:14px}.hti b{color:var(--acc)}
.wrap{padding:14px 16px}
.panel{border:1px solid var(--n300);background:var(--panel);margin-bottom:12px}
.ph{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid var(--n200)}
.ph .t{font-family:var(--fh);text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--n700);font-weight:600}
.lbl{font-family:var(--fh);text-transform:uppercase;letter-spacing:.11em;color:var(--n600);font-weight:600;font-size:11px}
.pb{padding:13px 14px}
.big{font-family:var(--fm);font-size:28px;font-weight:600;letter-spacing:-.5px}
.kg{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--n200);border:1px solid var(--n200);margin-top:10px}
.kc{background:var(--panel);padding:10px 11px}.kc .k{font-family:var(--fh);text-transform:uppercase;letter-spacing:.05em;font-size:9.5px;color:var(--n500)}.kc .v{font-family:var(--fm);font-size:16px;font-weight:600;margin-top:4px}
.row{display:flex;align-items:center;gap:10px;padding:11px 13px;border-top:1px solid var(--n200);min-height:48px}.row:first-child{border-top:0}
.rn{font-weight:500}.rr{margin-left:auto;text-align:right;font-family:var(--fm)}
.rsub{font-size:11px;color:var(--n600);font-family:var(--fh);letter-spacing:.04em}
table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--n200);white-space:nowrap}th{font-family:var(--fh);text-transform:uppercase;letter-spacing:.06em;font-size:9.5px;color:var(--n500)}
.tblwrap{overflow-x:auto}
.tabs{position:fixed;left:0;right:0;bottom:0;z-index:20;max-width:520px;margin:0 auto;background:var(--panel);border-top:1px solid var(--n300);display:grid;grid-template-columns:repeat(5,1fr);padding-bottom:env(safe-area-inset-bottom)}
.tabs button{background:0;border:0;border-top:2px solid transparent;color:var(--n500);font-family:var(--fh);letter-spacing:.03em;font-size:10px;font-weight:600;text-transform:uppercase;padding:14px 1px 13px;cursor:pointer;min-height:50px}
.tabs button.on{color:var(--a700);border-top-color:var(--acc)}
section{display:none}section.on{display:block}
.load{padding:26px;text-align:center;color:var(--n500);font-family:var(--fh);letter-spacing:.1em;font-size:11px;text-transform:uppercase}
input[type=file]{color:var(--n500);font-size:12px;max-width:100%}
.btn{background:var(--acc);color:#fff;border:0;font-family:var(--fh);letter-spacing:.06em;font-size:12px;padding:10px 16px;text-transform:uppercase;cursor:pointer}
a{color:var(--a700);text-decoration:none}
</style></head><body>
<div class="app">
  <div class="hdr"><div class="hti">AMAN<b>·</b>BUSINESS</div><a class="lbl" id="tolink" href="#">Trading →</a></div>

  <section id="s-brief" class="on"><div class="wrap">
    <div class="panel span2"><div class="ph"><span class="t">Tenders — pipeline</span><span class="lbl" id="t-cnt"></span></div><div class="pb"><div class="big up mono" id="t-val">₹—</div><div id="t-up" class="rsub" style="margin-top:6px"></div></div></div>
    <div class="panel"><div class="ph"><span class="t">Receivables</span><span class="lbl" id="r-cnt"></span></div><div class="pb"><div class="big mono" id="r-val">₹—</div><div class="kg" id="r-buckets"></div></div></div>
    <div class="panel"><div class="ph"><span class="t">Hotel</span><span class="lbl" id="h-cnt"></span></div><div class="pb"><div class="kg" id="h-kpi"></div></div></div>
    <div class="panel span2"><div class="ph"><span class="t">Datasets</span><span class="lbl">imported</span></div><div id="ds-list"><div class="load">loading</div></div></div>
  </div></section>

  <section id="s-tenders"><div class="wrap"><div class="panel span2"><div class="ph"><span class="t">Tenders</span><span class="lbl" id="td-meta"></span></div><div id="td-body"><div class="load">—</div></div></div></div></section>
  <section id="s-recv"><div class="wrap"><div class="panel span2"><div class="ph"><span class="t">Receivables</span><span class="lbl" id="rc-meta"></span></div><div id="rc-body"><div class="load">—</div></div></div></div></section>
  <section id="s-hotel"><div class="wrap"><div class="panel span2"><div class="ph"><span class="t">Hotel</span><span class="lbl" id="ht-meta"></span></div><div id="ht-body"><div class="load">—</div></div></div></div></section>

  <section id="s-import"><div class="wrap">
    <div class="panel span2"><div class="ph"><span class="t">Import data</span><span class="lbl">.xlsx / .csv</span></div>
      <div class="pb" id="imp-box"></div>
      <div class="pb rsub" style="border-top:1px solid var(--n200)">Each import replaces that dataset. Columns are auto-detected by keyword (amount/value/due/date/party…), so your existing sheet headers work as-is.</div>
    </div>
  </div></section>
</div>

<div class="tabs" id="tabs">
  <button data-t="brief" class="on">Brief</button>
  <button data-t="tenders">Tenders</button>
  <button data-t="recv">Recv</button>
  <button data-t="hotel">Hotel</button>
  <button data-t="import">Import</button>
</div>
<script>
const token=new URLSearchParams(location.search).get('token')||(localStorage.getItem('cfo_token')||'');
const Q='token='+encodeURIComponent(token);
document.getElementById('tolink').href='/?'+Q;
async function j(u,o){try{const r=await fetch(u,o);return {ok:r.ok,d:await r.json()};}catch(e){return {ok:false,d:{}};}}
const inr=n=>{if(n==null||isNaN(n))return '₹—';const a=Math.abs(n),s=n<0?'-':'';if(a>=1e7)return s+'₹'+(a/1e7).toFixed(2)+'Cr';if(a>=1e5)return s+'₹'+(a/1e5).toFixed(2)+'L';return s+'₹'+Math.round(a).toLocaleString('en-IN');};
async function loadBrief(){
  const r=await j('/business/summary?'+Q);if(!r.ok)return;const d=r.d;
  const t=d.tenders||{};document.getElementById('t-val').textContent=inr(t.pipeline_value||0);document.getElementById('t-cnt').textContent=(t.count||0)+' tenders';
  document.getElementById('t-up').innerHTML=(t.upcoming||[]).slice(0,4).map(x=>'▸ '+(x.tender||'—')+' · '+inr(x.value)+' · due '+x.due_in_days+'d').join('<br>')||'no upcoming deadlines';
  const rc=d.receivables||{};document.getElementById('r-val').textContent=inr(rc.total_outstanding||0);document.getElementById('r-cnt').textContent=(rc.count||0)+' rows';
  const bk=rc.buckets||{};document.getElementById('r-buckets').innerHTML=Object.keys(bk).map(k=>'<div class="kc"><div class="k">'+k+'d</div><div class="v'+(k==='90+'?' down':'')+'">'+inr(bk[k])+'</div></div>').join('');
  const h=d.hotel||{};document.getElementById('h-cnt').textContent=(h.count||0)+' days';
  document.getElementById('h-kpi').innerHTML=h.count?['Occupancy '+(h.latest_occupancy!=null?h.latest_occupancy+'%':'—'),'ADR '+inr(h.latest_adr),'RevPAR '+inr(h.revpar),'MTD '+inr(h.mtd_revenue)].map((s,i)=>{const p=s.split(' ');return '<div class="kc"><div class="k">'+p[0]+'</div><div class="v">'+p.slice(1).join(' ')+'</div></div>';}).join(''):'<div class="kc"><div class="k muted">no hotel data</div></div>';
  document.getElementById('ds-list').innerHTML=(d.datasets||[]).map(x=>'<div class="row"><div class="rn">'+x.dataset+' <span class="rsub">'+(x.imported_at?('imported '+x.imported_at.slice(0,10)):'not imported')+'</span></div><div class="rr">'+x.count+' rows</div></div>').join('');
}
function tableHTML(cols,rows){if(!rows.length)return '<div class="load">No rows — import this dataset.</div>';
  const c=cols.slice(0,7);return '<div class="tblwrap"><table><thead><tr>'+c.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'+rows.slice(0,60).map(r=>'<tr>'+c.map(h=>'<td>'+(r[h]!=null?(''+r[h]).slice(0,28):'')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}
async function loadDS(ds,metaEl,bodyEl){const r=await j('/business/'+ds+'?'+Q);const el=document.getElementById(bodyEl);
  if(!r.ok){el.innerHTML='<div class="load">could not load</div>';return;}
  document.getElementById(metaEl).textContent=r.d.count+' rows'+(r.d.imported_at?(' · '+r.d.imported_at.slice(0,10)):'');
  el.innerHTML=tableHTML(r.d.columns||[],r.d.rows||[]);}
function buildImport(){const sets=['tenders','receivables','hotel','cashflow','tasks','projects','compliance'];
  document.getElementById('imp-box').innerHTML=sets.map(s=>'<div class="row"><div class="rn">'+s+'</div><div class="rr" style="display:flex;gap:8px;align-items:center"><input type="file" accept=".xlsx,.xls,.csv" id="f-'+s+'"><button class="btn" onclick="imp(\''+s+'\')">Import</button></div></div>').join('')+'<div class="rsub" id="imp-msg" style="padding:10px 0"></div>';}
async function imp(ds){const f=document.getElementById('f-'+ds).files[0],m=document.getElementById('imp-msg');if(!f){m.textContent='Pick a file for '+ds+'.';return;}
  m.textContent='Importing '+ds+'…';const fd=new FormData();fd.append('file',f);
  const r=await fetch('/business/import/'+ds+'?'+Q,{method:'POST',body:fd});const d=await r.json().catch(()=>({}));
  m.innerHTML=r.ok?('<span class="up">✅ '+ds+': '+(d.count||0)+' rows imported.</span>'):('<span class="down">'+(d.detail||'failed')+'</span>');if(r.ok)loadBrief();}
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;const t=b.dataset.t;
  document.querySelectorAll('section').forEach(s=>s.classList.remove('on'));document.getElementById('s-'+t).classList.add('on');
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));window.scrollTo(0,0);
  if(t==='tenders')loadDS('tenders','td-meta','td-body');
  if(t==='recv')loadDS('receivables','rc-meta','rc-body');
  if(t==='hotel')loadDS('hotel','ht-meta','ht-body');
  if(t==='import')buildImport();});
loadBrief();setInterval(loadBrief,60000);
</script></body></html>"""
