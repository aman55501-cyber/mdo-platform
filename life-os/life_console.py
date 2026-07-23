"""Life OS console — LIFE_HTML.

A single self-contained terminal-styled page served at /life. It adapts to
whoever holds the link: the owner gets the shared toggle per item and the
"copy partner link" control; the partner (share scope) gets a shared-only
board where every add is shared by construction and the shared flag is hidden.

The page is rendered with two values substituted server-side:
    __SCOPE__  → "owner" | "share"
    __TOKEN__  → the caller's own token, so the page can authenticate its own
                 fetch() calls. The holder already has this token; embedding it
                 in their own page leaks nothing new.

Reconstructed from the DESIGN_EXPORT handoff (the original life_console.py was
not carried across in the extraction).
"""

LIFE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LIFE·OS</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
:root{
  --canvas:#07100c; --panel:#0e1712; --panel2:#13201a; --line:#1e2c24; --line2:#2b3d32;
  --text:#e4efe9; --muted:#87a094; --dim:#5b6f64;
  --acc:#3fb488; --acc2:#7ed7b2; --warn:#f0a13c; --down:#f0544c;
  --mono:ui-monospace,'SF Mono','Cascadia Code',Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--canvas);color:var(--text);font-family:var(--sans);line-height:1.5;font-size:15px;
  padding:0 16px calc(48px + env(safe-area-inset-bottom));
  background-image:radial-gradient(120% 60% at 50% -10%,rgba(63,180,136,.12),transparent 70%)}
.wrap{max-width:820px;margin:0 auto}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
header{padding:calc(28px + env(safe-area-inset-top)) 0 18px;border-bottom:1px solid var(--line);
  display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap}
.eyebrow{font-family:var(--mono);text-transform:uppercase;letter-spacing:.2em;font-size:11px;color:var(--acc2)}
h1{font-family:var(--mono);font-weight:600;letter-spacing:.04em;font-size:22px;margin-top:6px}
.scope{font-family:var(--mono);font-size:11px;letter-spacing:.05em;padding:3px 9px;border-radius:2px;
  border:1px solid var(--line2);color:var(--muted)}
.scope.owner{color:var(--acc2);border-color:rgba(126,215,178,.4)}
.scope.share{color:var(--warn);border-color:rgba(240,161,60,.4)}
button{font-family:var(--mono);font-size:12px;cursor:pointer;background:var(--panel2);color:var(--acc2);
  border:1px solid var(--line2);padding:6px 11px;border-radius:2px}
button:hover{border-color:var(--acc)}
button.ghost{color:var(--muted)}
.bar{display:flex;gap:8px;flex-wrap:wrap;padding:16px 0}
input,select,textarea{font-family:var(--sans);font-size:14px;background:var(--panel);color:var(--text);
  border:1px solid var(--line2);border-radius:2px;padding:8px 10px}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--acc)}
.add{display:grid;grid-template-columns:120px 1fr auto;gap:8px;padding:12px;background:var(--panel);
  border:1px solid var(--line);margin-bottom:16px}
.add .row2{grid-column:1/-1;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.add .row2 label{font-family:var(--mono);font-size:12px;color:var(--muted);display:flex;gap:5px;align-items:center}
@media(max-width:560px){.add{grid-template-columns:1fr}}
.list{display:flex;flex-direction:column;border:1px solid var(--line);background:var(--panel)}
.item{display:flex;gap:12px;padding:12px 14px;border-top:1px solid var(--line);align-items:flex-start}
.item:first-child{border-top:0}
.item.done .title{text-decoration:line-through;color:var(--dim)}
.item.overdue{border-left:2px solid var(--down)}
.tick{flex:0 0 auto;width:18px;height:18px;border:1px solid var(--line2);border-radius:3px;background:var(--panel2);
  cursor:pointer;margin-top:2px}
.item.done .tick{background:var(--acc);border-color:var(--acc)}
.body{flex:1;min-width:0}
.title{font-size:14.5px;word-break:break-word}
.meta{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:3px;display:flex;gap:10px;flex-wrap:wrap}
.kind{color:var(--acc2)}
.due.over{color:var(--down)} .due.today{color:var(--warn)}
.chip{font-family:var(--mono);font-size:10.5px;padding:1px 6px;border:1px solid var(--line2);border-radius:2px;color:var(--muted)}
.chip.shared{color:var(--acc2);border-color:rgba(126,215,178,.4)}
.actions{display:flex;gap:6px;flex:0 0 auto}
.actions button{padding:4px 8px;font-size:11px}
.empty{padding:26px 14px;color:var(--dim);font-family:var(--mono);font-size:13px;text-align:center}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:var(--panel2);color:var(--text);
  border:1px solid var(--acc);border-radius:3px;padding:9px 14px;font-family:var(--mono);font-size:12px;
  opacity:0;transition:opacity .2s;pointer-events:none;max-width:90vw}
.toast.show{opacity:1}
.digest{font-family:var(--mono);font-size:12px;color:var(--muted);padding:10px 0 0}
.digest b{color:var(--acc2)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <div class="eyebrow">Shared home board</div>
      <h1>LIFE·OS</h1>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <span id="scopeBadge" class="scope"></span>
      <button id="shareBtn" class="ghost" style="display:none">copy partner link</button>
    </div>
  </header>

  <div class="digest" id="digest"></div>

  <div class="add">
    <select id="kind">
      <option value="task">task</option>
      <option value="event">event</option>
      <option value="bill">bill</option>
      <option value="list">list</option>
      <option value="note">note</option>
    </select>
    <input id="title" placeholder="add to the board…" autocomplete="off">
    <button id="addBtn">add</button>
    <div class="row2">
      <label>due <input id="due" type="date"></label>
      <label id="sharedWrap">shared <input id="shared" type="checkbox"></label>
    </div>
  </div>

  <div class="list" id="list"><div class="empty">loading…</div></div>
</div>
<div class="toast" id="toast"></div>

<script>
const SCOPE = "__SCOPE__";                 // "owner" | "share"
const TOKEN = "__TOKEN__";                 // caller's own token
const isOwner = SCOPE === "owner";
const H = {"X-Life-Token": TOKEN, "Content-Type": "application/json"};

const $ = s => document.querySelector(s);
function toast(m){const t=$("#toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),1800);}
function todayISO(){return new Date().toISOString().slice(0,10);}

// scope-dependent chrome
$("#scopeBadge").textContent = isOwner ? "owner · full" : "Jahnavi · shared";
$("#scopeBadge").classList.add(isOwner ? "owner" : "share");
if(!isOwner){ $("#sharedWrap").style.display = "none"; }   // partner add is always shared
if(isOwner){ $("#shareBtn").style.display = ""; }

async function api(method, path, body){
  const r = await fetch(path, {method, headers:H, body: body ? JSON.stringify(body) : undefined});
  if(r.status === 401){ toast("unauthorized"); throw new Error("401"); }
  if(!r.ok){ toast("error "+r.status); throw new Error(String(r.status)); }
  return r.status === 204 ? null : r.json();
}

function dueClass(due){
  if(!due) return "";
  const d = due.slice(0,10), t = todayISO();
  if(d < t) return "over";
  if(d === t) return "today";
  return "";
}

function render(items){
  const list = $("#list");
  if(!items.length){ list.innerHTML = '<div class="empty">nothing here yet</div>'; return; }
  list.innerHTML = "";
  for(const it of items){
    const el = document.createElement("div");
    const dc = dueClass(it.due);
    el.className = "item" + (it.done ? " done":"") + (dc==="over" ? " overdue":"");
    const shareChip = isOwner
      ? `<span class="chip ${it.shared?'shared':''}" data-share="${it.id}" title="toggle shared" style="cursor:pointer">${it.shared?'shared':'private'}</span>`
      : "";
    const dueTxt = it.due ? `<span class="due ${dc}">due ${it.due.slice(0,10)}</span>` : "";
    const amtTxt = (it.amount!=null) ? `<span>₹${it.amount}</span>` : "";
    el.innerHTML =
      `<div class="tick" data-tick="${it.id}"></div>
       <div class="body">
         <div class="title"></div>
         <div class="meta"><span class="kind">${it.kind}</span>${dueTxt}${amtTxt}${shareChip}</div>
       </div>
       <div class="actions"><button data-del="${it.id}" class="ghost">del</button></div>`;
    el.querySelector(".title").textContent = it.title || "(untitled)";
    list.appendChild(el);
  }
}

async function refresh(){
  const items = await api("GET", "/life/items");
  render(items);
  renderDigest(items);
}

function renderDigest(items){
  const t = todayISO();
  const due = items.filter(i => !i.done && i.due && i.due.slice(0,10) <= t);
  const over = due.filter(i => i.due.slice(0,10) < t).length;
  const today = due.length - over;
  const d = $("#digest");
  if(!due.length){ d.innerHTML = "<b>&#9679;</b> nothing shared is due — board is clear"; return; }
  const bits = [];
  if(over) bits.push(`<b>${over}</b> overdue`);
  if(today) bits.push(`<b>${today}</b> due today`);
  d.innerHTML = "&#9679; " + bits.join(" · ");
}

// add
$("#addBtn").onclick = async () => {
  const title = $("#title").value.trim();
  if(!title){ toast("title?"); return; }
  const body = {kind: $("#kind").value, title, due: $("#due").value || null};
  if(isOwner){ body.shared = $("#shared").checked; }   // partner: server forces shared
  await api("POST", "/life/items", body);
  $("#title").value = ""; $("#due").value = ""; if(isOwner) $("#shared").checked = false;
  toast("added"); refresh();
};
$("#title").addEventListener("keydown", e => { if(e.key === "Enter") $("#addBtn").click(); });

// delegated clicks: tick / delete / share-toggle
$("#list").addEventListener("click", async (e) => {
  const tick = e.target.closest("[data-tick]");
  const del  = e.target.closest("[data-del]");
  const shr  = e.target.closest("[data-share]");
  if(tick){
    const id = tick.getAttribute("data-tick");
    const done = tick.closest(".item").classList.contains("done");
    await api("PATCH", `/life/items/${id}`, {done: !done}); refresh();
  } else if(del){
    await api("DELETE", `/life/items/${del.getAttribute("data-del")}`); toast("deleted"); refresh();
  } else if(shr && isOwner){
    const id = shr.getAttribute("data-share");
    const nowShared = shr.classList.contains("shared");
    await api("PATCH", `/life/items/${id}`, {shared: !nowShared}); refresh();
  }
});

// owner-only: copy partner link
$("#shareBtn").onclick = async () => {
  const {url} = await api("GET", "/life/share-link");
  try { await navigator.clipboard.writeText(url); toast("partner link copied"); }
  catch { toast(url); }
};

refresh();
</script>
</body>
</html>"""
