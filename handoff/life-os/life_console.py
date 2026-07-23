"""Life OS console — a shared household cockpit, terminal-styled.

Served at /life. Same aesthetic as the Market & Business consoles. The page adapts
to who's holding the link: the owner token unlocks add/edit/share/delete over every
item; Jahnavi's share token shows only the items flagged `shared` and lets her tick
them off or leave a note — nothing else, and never the trading/business book.
"""

LIFE_HTML = r"""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Life OS</title>
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
.app{width:100%;max-width:520px;margin:0 auto;background:var(--bg);min-height:100vh;padding-bottom:120px}
@media(min-width:740px){.app,.tabs,.hdr{max-width:760px}}
.hdr{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--n300);display:flex;align-items:center;justify-content:space-between;padding:calc(env(safe-area-inset-top) + 11px) 16px 11px}
.hti{font-family:var(--fh);font-weight:600;letter-spacing:.14em;font-size:14px}.hti b{color:var(--acc)}
.who{font-family:var(--fh);text-transform:uppercase;letter-spacing:.1em;font-size:10px;color:var(--n500)}
.who b{color:var(--a700)}
.wrap{padding:14px 16px}
.panel{border:1px solid var(--n300);background:var(--panel);margin-bottom:12px}
.ph{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-bottom:1px solid var(--n200)}
.ph .t{font-family:var(--fh);text-transform:uppercase;letter-spacing:.12em;font-size:12px;color:var(--n700);font-weight:600}
.lbl{font-family:var(--fh);text-transform:uppercase;letter-spacing:.11em;color:var(--n600);font-weight:600;font-size:11px}
.stat{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--n200);border:1px solid var(--n200);margin:14px 16px}
.sc{background:var(--panel);padding:11px 12px;text-align:center}.sc .k{font-family:var(--fh);text-transform:uppercase;letter-spacing:.06em;font-size:9.5px;color:var(--n500)}.sc .v{font-family:var(--fm);font-size:20px;font-weight:600;margin-top:3px}
.filters{display:flex;gap:8px;padding:0 16px 4px;overflow-x:auto}
.filters button{background:var(--n100);border:1px solid var(--n300);color:var(--n600);font-family:var(--fh);text-transform:uppercase;letter-spacing:.06em;font-size:10.5px;font-weight:600;padding:7px 12px;cursor:pointer;white-space:nowrap}
.filters button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.item{display:flex;align-items:flex-start;gap:11px;padding:12px 14px;border-top:1px solid var(--n200)}
.item:first-child{border-top:0}
.ck{flex:0 0 auto;width:20px;height:20px;border:1.5px solid var(--n400);background:0;cursor:pointer;margin-top:1px;display:flex;align-items:center;justify-content:center;color:var(--up);font-size:13px;font-family:var(--fm)}
.ck.on{border-color:var(--up);background:rgba(46,189,133,.12)}
.it-main{flex:1;min-width:0}
.it-t{font-weight:500;word-break:break-word}.it-t.done{color:var(--n500);text-decoration:line-through}
.it-meta{font-family:var(--fh);letter-spacing:.04em;font-size:10.5px;color:var(--n500);margin-top:3px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.chip{border:1px solid var(--n300);padding:1px 6px;text-transform:uppercase;letter-spacing:.05em}
.chip.share{border-color:var(--acc);color:var(--a700)}.chip.due{color:var(--warn)}.chip.over{border-color:var(--down);color:var(--down)}
.it-notes{font-size:12px;color:var(--n600);margin-top:5px;white-space:pre-wrap;word-break:break-word}
.it-act{display:flex;gap:6px;flex:0 0 auto}
.iconbtn{background:0;border:0;color:var(--n500);cursor:pointer;font-family:var(--fm);font-size:13px;padding:2px 4px}
.iconbtn:hover{color:var(--text)}
.load{padding:26px;text-align:center;color:var(--n500);font-family:var(--fh);letter-spacing:.1em;font-size:11px;text-transform:uppercase}
.addbar{position:fixed;left:0;right:0;bottom:0;z-index:30;max-width:520px;margin:0 auto;background:var(--panel);border-top:1px solid var(--n300);padding:10px 12px calc(env(safe-area-inset-bottom) + 10px)}
@media(min-width:740px){.addbar{max-width:760px}}
.addrow{display:flex;gap:8px}
.addbar input,.addbar select{background:var(--canvas);border:1px solid var(--n300);color:var(--text);font-family:var(--fb);font-size:13px;padding:9px 10px}
#a-title{flex:1;min-width:0}
.btn{background:var(--acc);color:#fff;border:0;font-family:var(--fh);letter-spacing:.06em;font-size:12px;padding:9px 14px;text-transform:uppercase;cursor:pointer}
.addopts{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center}
.addopts label{font-family:var(--fh);text-transform:uppercase;letter-spacing:.06em;font-size:10px;color:var(--n600);display:flex;align-items:center;gap:5px;cursor:pointer}
a{color:var(--a700);text-decoration:none}
.hint{padding:10px 16px;color:var(--n500);font-family:var(--fh);letter-spacing:.04em;font-size:11px}
</style></head><body>
<div class="app">
  <div class="hdr"><div class="hti">LIFE<b>·</b>OS</div><div class="who" id="who">—</div></div>
  <div class="stat">
    <div class="sc"><div class="k">Open</div><div class="v" id="s-open">—</div></div>
    <div class="sc"><div class="k">Shared</div><div class="v" id="s-shared">—</div></div>
    <div class="sc"><div class="k">Overdue</div><div class="v down" id="s-over">—</div></div>
  </div>
  <div class="filters" id="filters">
    <button data-f="open" class="on">Open</button>
    <button data-f="all">All</button>
    <button data-f="shared">Shared</button>
    <button data-f="today">Today</button>
    <button data-f="done">Done</button>
  </div>
  <div class="wrap"><div class="panel"><div id="list"><div class="load">loading</div></div></div>
    <div id="ownerlinks" style="display:none;margin-top:2px">
      <a class="lbl" id="tolink" href="#">Trading →</a> &nbsp; <a class="lbl" id="bizlink" href="#">Business →</a> &nbsp;
      <a class="lbl" href="#" onclick="shareLink();return false">Jahnavi's link ⧉</a>
      <div class="hint" id="sharemsg" style="padding:8px 0 0"></div>
    </div>
  </div>
</div>
<div class="addbar" id="addbar" style="display:none">
  <div class="addrow">
    <input id="a-title" placeholder="Add to our life… (e.g. Pay society bill)" autocomplete="off">
    <button class="btn" onclick="addItem()">Add</button>
  </div>
  <div class="addopts">
    <select id="a-kind"><option value="task">Task</option><option value="event">Event</option><option value="list">List</option><option value="bill">Bill</option><option value="note">Note</option><option value="goal">Goal</option></select>
    <input id="a-cat" placeholder="category" style="width:110px">
    <input id="a-due" type="date" style="width:150px">
    <label id="sharewrap"><input type="checkbox" id="a-shared"> Share with Jahnavi</label>
  </div>
</div>
<script>
const token=new URLSearchParams(location.search).get('token')||(localStorage.getItem('cfo_token')||'');
const Q='token='+encodeURIComponent(token);
let SCOPE='share', FILTER='open', ITEMS=[];
const today=()=>new Date().toISOString().slice(0,10);
async function j(u,o){try{const r=await fetch(u,o);return {ok:r.ok,s:r.status,d:await r.json().catch(()=>({}))};}catch(e){return {ok:false,d:{}};}}
function esc(s){return (''+s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
async function load(){
  const r=await j('/life/items?'+Q);
  if(!r.ok){document.getElementById('list').innerHTML='<div class="load">'+(r.s===401?'Invalid link — check your token.':'could not load')+'</div>';return;}
  SCOPE=r.d.scope||'share';ITEMS=r.d.items||[];
  const isOwner=SCOPE==='full';
  document.getElementById('who').innerHTML=isOwner?'Owner · <b>full</b>':'Our shared list · <b>you can add & edit</b>';
  document.getElementById('addbar').style.display='block';  // both can add
  document.getElementById('sharewrap').style.display=isOwner?'flex':'none';  // owner-only share toggle
  document.getElementById('ownerlinks').style.display=isOwner?'block':'none';
  if(isOwner){document.getElementById('tolink').href='/?'+Q;document.getElementById('bizlink').href='/biz?'+Q;}
  document.querySelector('#filters [data-f="shared"]').style.display=isOwner?'':'none';
  const open=ITEMS.filter(i=>!i.done).length, shared=ITEMS.filter(i=>i.shared).length;
  const over=ITEMS.filter(i=>!i.done&&i.due&&i.due<today()).length;
  document.getElementById('s-open').textContent=open;document.getElementById('s-shared').textContent=shared;document.getElementById('s-over').textContent=over;
  render();
}
function visible(){
  if(FILTER==='open')return ITEMS.filter(i=>!i.done);
  if(FILTER==='done')return ITEMS.filter(i=>i.done);
  if(FILTER==='shared')return ITEMS.filter(i=>i.shared);
  if(FILTER==='today')return ITEMS.filter(i=>i.due===today());
  return ITEMS;
}
function render(){
  const rows=visible();const owner=SCOPE==='full';
  if(!rows.length){document.getElementById('list').innerHTML='<div class="load">'+(owner?'Nothing here — add something below.':'Nothing shared with you yet.')+'</div>';return;}
  document.getElementById('list').innerHTML=rows.map(i=>{
    const over=!i.done&&i.due&&i.due<today();
    const due=i.due?('<span class="chip '+(over?'over':'due')+'">'+i.due+'</span>'):'';
    const kind='<span class="chip">'+esc(i.kind)+'</span>';
    const cat=i.category?('<span class="chip">'+esc(i.category)+'</span>'):'';
    const sh=(owner&&i.shared)?'<span class="chip share">shared</span>':'';
    const notes=i.notes?('<div class="it-notes">'+esc(i.notes)+'</div>'):'';
    // Owner also gets a share/unshare toggle; both scopes get note + delete on shared items.
    const shareBtn=owner?('<button class="iconbtn" title="'+(i.shared?'unshare':'share')+'" onclick="toggleShare(\''+i.id+'\','+(!i.shared)+')">'+(i.shared?'⚊':'⊕')+'</button>'):'';
    const act='<div class="it-act">'+shareBtn+'<button class="iconbtn" title="note" onclick="addNote(\''+i.id+'\')">✎</button><button class="iconbtn" title="delete" onclick="del(\''+i.id+'\')">✕</button></div>';
    return '<div class="item"><button class="ck '+(i.done?'on':'')+'" onclick="toggleDone(\''+i.id+'\','+(!i.done)+')">'+(i.done?'✓':'')+'</button>'
      +'<div class="it-main"><div class="it-t '+(i.done?'done':'')+'" onclick="rename(\''+i.id+'\')">'+esc(i.title)+'</div>'
      +'<div class="it-meta">'+kind+cat+due+sh+'</div>'+notes+'</div>'+act+'</div>';
  }).join('');
}
async function patch(id,body){const r=await j('/life/items/'+id+'?'+Q,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(r.ok)load();else alert(r.d.detail||'not allowed');}
function toggleDone(id,v){patch(id,{done:v});}
function toggleShare(id,v){patch(id,{shared:v});}
function addNote(id){const it=ITEMS.find(x=>x.id===id);const n=prompt('Note:',it&&it.notes||'');if(n!==null)patch(id,{notes:n});}
function rename(id){const it=ITEMS.find(x=>x.id===id);const t=prompt('Edit:',it&&it.title||'');if(t!==null&&t.trim())patch(id,{title:t.trim()});}
async function del(id){if(!confirm('Delete this item?'))return;const r=await j('/life/items/'+id+'?'+Q,{method:'DELETE'});if(r.ok)load();}
async function addItem(){const t=document.getElementById('a-title');if(!t.value.trim())return;
  const body={title:t.value.trim(),kind:document.getElementById('a-kind').value,category:document.getElementById('a-cat').value,due:document.getElementById('a-due').value,shared:document.getElementById('a-shared').checked};
  const r=await j('/life/items?'+Q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.ok){t.value='';document.getElementById('a-cat').value='';document.getElementById('a-due').value='';load();}else alert(r.d.detail||'failed');}
async function shareLink(){const m=document.getElementById('sharemsg');const r=await j('/life/share-link?'+Q);
  if(!r.ok){m.textContent='could not fetch link';return;}
  if(!r.d.configured){m.textContent=r.d.hint||'Set CFO_SHARE_TOKEN in .env to enable.';return;}
  let url=r.d.url;if(url.startsWith('/'))url=location.origin+url;
  try{await navigator.clipboard.writeText(url);m.innerHTML='<span class="up">Copied — send this to Jahnavi.</span>';}
  catch(e){m.innerHTML='Send Jahnavi: <a href="'+url+'">'+url+'</a>';}}
document.getElementById('a-title').addEventListener('keydown',e=>{if(e.key==='Enter')addItem();});
document.getElementById('filters').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;FILTER=b.dataset.f;document.querySelectorAll('#filters button').forEach(x=>x.classList.toggle('on',x===b));render();});
load();setInterval(load,30000);
</script></body></html>"""
