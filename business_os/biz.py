"""
Business OS — the console (BIZ_HTML).

A single self-contained page served at GET /biz. It talks only to the
/business/* JSON API: import a sheet per dataset, see the KPI brief, and browse
rows. No build step, no external assets.
"""

BIZ_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Business OS</title>
<style>
:root{
  --canvas:#0a0810; --panel:#150f1d; --panel2:#1b1426; --line:#2a2036; --line2:#3a2e4a;
  --text:#e8e2f0; --muted:#9a8bad; --dim:#6b5d7d;
  --acc:#b07be0; --acc2:#cfa8ee; --up:#2ebd85; --warn:#f0a13c; --danger:#f0556b;
  --mono:ui-monospace,'SF Mono','Cascadia Code',Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--canvas);color:var(--text);font-family:var(--sans);line-height:1.5;
  font-size:15px;padding:0 16px calc(48px + env(safe-area-inset-bottom));
  background-image:radial-gradient(120% 60% at 50% -10%,rgba(176,123,224,.12),transparent 70%)}
.wrap{max-width:1000px;margin:0 auto}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
header{padding:calc(30px + env(safe-area-inset-top)) 0 20px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);text-transform:uppercase;letter-spacing:.2em;font-size:11px;color:var(--acc2)}
h1{font-family:var(--mono);font-weight:600;letter-spacing:.04em;font-size:22px;margin-top:6px}
.sub{margin-top:8px;color:var(--muted);font-size:13px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:18px 0}
.tab{font-family:var(--mono);font-size:12px;letter-spacing:.04em;color:var(--muted);
  background:var(--panel);border:1px solid var(--line);padding:6px 11px;border-radius:2px;cursor:pointer}
.tab.active{color:var(--canvas);background:var(--acc);border-color:var(--acc);font-weight:600}
.stitle{font-family:var(--mono);text-transform:uppercase;letter-spacing:.13em;font-size:12px;
  font-weight:600;color:var(--acc2);margin:22px 0 12px}
.up{display:flex;gap:10px;flex-wrap:wrap;align-items:center;background:var(--panel);
  border:1px solid var(--line);padding:12px 14px;border-radius:2px}
input[type=file]{color:var(--muted);font-size:13px;max-width:100%}
button{font-family:var(--mono);font-size:12px;letter-spacing:.04em;color:var(--canvas);
  background:var(--acc2);border:0;padding:8px 14px;border-radius:2px;cursor:pointer;font-weight:600}
button.ghost{background:var(--panel2);color:var(--acc2);border:1px solid var(--line2)}
button:disabled{opacity:.5;cursor:default}
.cards{display:grid;grid-template-columns:1fr;gap:9px}
@media(min-width:640px){.cards{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
  border-left:2px solid var(--acc);padding:13px 14px;border-radius:2px}
.card .lbl{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.card .val{font-family:var(--mono);font-size:20px;font-weight:600;margin-top:6px}
.card .val.warn{color:var(--warn)} .card .val.danger{color:var(--danger)} .card .val.up{color:var(--up)}
.card .sub2{font-size:12px;color:var(--dim);margin-top:3px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px;display:block;overflow-x:auto;white-space:nowrap}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
th{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--acc2);position:sticky;top:0;background:var(--panel)}
td{color:var(--text)} tr:hover td{background:var(--panel)}
.empty{color:var(--dim);font-size:13px;padding:18px 0}
.msg{margin-top:10px;font-family:var(--mono);font-size:12px}
.msg.ok{color:var(--up)} .msg.err{color:var(--danger)}
.brief{display:flex;flex-direction:column;gap:14px}
.bwrap{border:1px solid var(--line);border-radius:2px;overflow:hidden}
.bhead{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--acc2);background:var(--panel);padding:9px 13px;border-bottom:1px solid var(--line);
  display:flex;justify-content:space-between}
.bhead .n{color:var(--dim)}
.pad{padding:12px 13px}
footer{margin-top:34px;padding:16px 0;border-top:1px solid var(--line);color:var(--dim);
  font-family:var(--mono);font-size:11px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="eyebrow">Business OS</div>
    <h1>BUSINESS·OS</h1>
    <div class="sub">Import the sheets you keep. The books watch themselves.</div>
  </header>

  <div class="tabs" id="tabs"></div>
  <div id="view"></div>

  <footer>Import Excel/CSV per dataset · KPIs auto-computed · data on the persistent volume</footer>
</div>

<script>
const DATASETS = ["summary","tenders","receivables","hotel","cash-flow","tasks","projects","compliance"];
let active = "summary";

const $ = (s,el=document)=>el.querySelector(s);
const el = (t,attrs={},...kids)=>{const e=document.createElement(t);
  for(const[k,v]of Object.entries(attrs)){if(k==="class")e.className=v;else if(k==="html")e.innerHTML=v;else e.setAttribute(k,v);}
  for(const k of kids)e.append(k);return e;};
const fmtNum = n => (n==null||isNaN(n))?"–":Number(n).toLocaleString("en-IN",{maximumFractionDigits:2});
const fmtINR = n => { if(n==null||isNaN(n))return "–"; const a=Math.abs(n);
  if(a>=1e7)return "₹"+(n/1e7).toFixed(2)+" Cr"; if(a>=1e5)return "₹"+(n/1e5).toFixed(2)+" L";
  return "₹"+fmtNum(n); };

function renderTabs(){
  const t = $("#tabs"); t.innerHTML="";
  for(const d of DATASETS){
    const tab = el("div",{class:"tab"+(d===active?" active":"")}, d);
    tab.onclick = ()=>{active=d; renderTabs(); route();};
    t.append(tab);
  }
}

async function api(path, opts){ const r = await fetch(path, opts);
  if(!r.ok){ throw new Error((await r.text())||("HTTP "+r.status)); } return r.json(); }

function card(lbl, val, cls, sub){
  return el("div",{class:"card"},
    el("div",{class:"lbl"},lbl),
    el("div",{class:"val"+(cls?" "+cls:"")}, val),
    sub?el("div",{class:"sub2"},sub):"");
}

function kpiCards(k){
  if(!k) return [];
  if(k.kind==="receivables"){
    const a=k.aging||{};
    return [
      card("Outstanding", fmtINR(k.total_outstanding)),
      card("60+ days", fmtINR(k.overdue_60_plus), (k.overdue_60_plus>0?"danger":"up")),
      card("0–30", fmtINR(a["0-30"])), card("31–60", fmtINR(a["31-60"])),
      card("61–90", fmtINR(a["61-90"]), "warn"), card("90+", fmtINR(a["90+"]), "danger"),
    ];
  }
  if(k.kind==="tenders"){
    return [
      card("Pipeline", fmtNum(k.pipeline_count)),
      card("Total value", fmtINR(k.total_value)),
      card("Closing ≤7d", fmtNum(k.closing_this_week), (k.closing_this_week>0?"warn":"")),
    ];
  }
  if(k.kind==="hotel"){
    return [
      card("RevPAR", fmtINR(k.revpar)), card("ADR", fmtINR(k.adr)),
      card("Occupancy", (k.occupancy_pct==null?"–":k.occupancy_pct+"%")),
      card("MTD revenue", fmtINR(k.mtd_revenue), "up"),
    ];
  }
  if(k.kind==="generic"){
    const out=[card("Rows", fmtNum(k.count))];
    for(const[col,s]of Object.entries(k.numeric||{}))
      out.push(card(col, fmtNum(s.sum), "", "avg "+fmtNum(s.avg)+" · n="+s.count));
    return out;
  }
  return [];
}

async function route(){
  const v = $("#view"); v.innerHTML="Loading…";
  try{ active==="summary" ? await renderSummary(v) : await renderDataset(v, active); }
  catch(e){ v.innerHTML=""; v.append(el("div",{class:"msg err"}, "Error: "+e.message)); }
}

async function renderSummary(v){
  const s = await api("/business/summary");
  v.innerHTML="";
  const counts = s.datasets||{};
  if(Object.keys(counts).length===0){
    v.append(el("div",{class:"stitle"},"The Brief"),
             el("div",{class:"empty"},"No datasets yet. Pick a tab and import a sheet."));
    return;
  }
  v.append(el("div",{class:"stitle"},"The Brief"));
  const brief = el("div",{class:"brief"});
  for(const[name,k]of Object.entries(s.kpis||{})){
    const bwrap = el("div",{class:"bwrap"});
    bwrap.append(el("div",{class:"bhead"}, el("span",{},name),
      el("span",{class:"n"},(counts[name]||0)+" rows")));
    const pad = el("div",{class:"pad"});
    const cs = el("div",{class:"cards"}); kpiCards(k).forEach(c=>cs.append(c));
    pad.append(cs); bwrap.append(pad); brief.append(bwrap);
  }
  v.append(brief);
}

async function renderDataset(v, name){
  v.innerHTML="";
  // Import panel
  const up = el("div",{class:"up"});
  const file = el("input",{type:"file",accept:".xlsx,.xlsm,.csv,.tsv,.txt"});
  const btn = el("button",{}, "Import "+name);
  const refresh = el("button",{class:"ghost"}, "Refresh");
  const msg = el("div",{class:"msg"});
  btn.onclick = async ()=>{
    if(!file.files.length){ msg.className="msg err"; msg.textContent="Choose a file first."; return; }
    btn.disabled=true; msg.className="msg"; msg.textContent="Uploading…";
    try{
      const fd = new FormData(); fd.append("file", file.files[0]);
      const r = await api("/business/import/"+name, {method:"POST", body:fd});
      msg.className="msg ok"; msg.textContent="Imported "+r.rows+" rows · columns: "+(r.columns||[]).join(", ");
      loadRows(v, name);
    }catch(e){ msg.className="msg err"; msg.textContent="Import failed: "+e.message; }
    finally{ btn.disabled=false; }
  };
  refresh.onclick = ()=>loadRows(v, name);
  up.append(file, btn, refresh);
  v.append(el("div",{class:"stitle"},name+" · import"), up, msg);
  await loadRows(v, name);
}

async function loadRows(v, name){
  // Remove any prior kpi/table block
  [...v.querySelectorAll("[data-block]")].forEach(n=>n.remove());
  const block = el("div",{"data-block":"1"});
  const d = await api("/business/"+name+"?limit=200");
  const rows = d.rows||[];
  const cs = el("div",{class:"cards"}); kpiCards(d.kpi).forEach(c=>cs.append(c));
  block.append(el("div",{class:"stitle"},"KPI"), cs);
  block.append(el("div",{class:"stitle"},"Rows ("+(d.count||rows.length)+")"));
  if(rows.length===0){ block.append(el("div",{class:"empty"},"No rows. Import a sheet above.")); }
  else{
    const headers = Object.keys(rows[0]);
    const table = el("table"); const thead = el("tr");
    headers.forEach(h=>thead.append(el("th",{},h))); table.append(thead);
    rows.forEach(r=>{ const tr=el("tr");
      headers.forEach(h=>tr.append(el("td",{}, r[h]==null?"":String(r[h])))); table.append(tr); });
    block.append(table);
  }
  v.append(block);
}

renderTabs(); route();
</script>
</body>
</html>
"""
