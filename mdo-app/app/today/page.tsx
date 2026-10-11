"use client"

// /today — Aman's phone page. One call (/api/today), big touch targets, no sidebar needed.
// Aman, chat 2026-10-11: "an interface for mobile (Android) to keep track and progress from my phone".
// Install: Chrome → ⋮ → Add to Home screen. Actions use the existing /api/plan endpoints.

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, XCircle, Plus, RefreshCw, ListChecks, Target, Activity, FileText, BarChart3 } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

interface PlanItem { id: number; project: string; item: string; owner: string; status: "open" | "done" | "missed"; reason: string; fault: string; carried_from: number | null }
interface TodayData {
  as_of: string; date: string; reasons: string[]
  plan: { projects: Record<string, string>; items: PlanItem[]; done: number; total: number }
  objectives: string[]
  pending: { id: string; item: string; why: string; since: string }[]
  system: { enabled: number | null; late: string[] }
  credits?: string
  tenders: { buyer: string; category: string; due_date: string | null; status: string; notes: string; url: string }[]
  volume: string
  competitors: string
}

const card: React.CSSProperties = { background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: 14, marginBottom: 12 }
const h: React.CSSProperties = { fontSize: 11, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }
const btn: React.CSSProperties = { minHeight: 44, minWidth: 44, borderRadius: 10, border: "1px solid var(--border2)", background: "var(--bg)", color: "var(--text)", padding: "0 12px", fontSize: 14 }

export default function TodayPage() {
  const qc = useQueryClient()
  const q = useQuery<TodayData>({
    queryKey: ["today"],
    queryFn: async () => { const r = await fetch(`${BASE}/api/today`, { cache: "no-store" }); if (!r.ok) throw new Error(`today ${r.status}`); return r.json() },
    refetchInterval: 60_000,
  })
  const [missFor, setMissFor] = useState<number | null>(null)
  const [newText, setNewText] = useState("")
  const [newProject, setNewProject] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")

  const call = async (path: string, body: unknown) => {
    setBusy(true); setErr("")
    try {
      const r = await fetch(`${BASE}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      if (!r.ok) throw new Error(`${r.status}`)
      await qc.invalidateQueries({ queryKey: ["today"] })
    } catch (e) { setErr(`Could not save (${(e as Error).message}). Try again.`) }
    setBusy(false)
  }

  const d = q.data
  const projects = d ? Object.entries(d.plan.projects) : []
  const proj = newProject || (projects[0]?.[0] ?? "")
  const pct = d && d.plan.total ? Math.round((100 * d.plan.done) / d.plan.total) : 0
  const bar = "█".repeat(Math.round(pct / 10)) + "░".repeat(10 - Math.round(pct / 10))

  return (
    <div style={{ maxWidth: 560, margin: "0 auto", paddingBottom: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>Today</div>
          <div style={{ fontSize: 12, color: "var(--text2)" }}>{d ? `${new Date(d.date).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" })} · updated ${d.as_of.slice(11, 16)} IST` : "loading…"}</div>
        </div>
        <button style={btn} onClick={() => q.refetch()} aria-label="refresh"><RefreshCw size={16} /></button>
      </div>
      {q.error && <div style={{ ...card, borderColor: "var(--red)", color: "var(--red)" }}>Could not load: {(q.error as Error).message}. Pull to refresh or check your connection.</div>}
      {err && <div style={{ ...card, borderColor: "var(--red)", color: "var(--red)" }}>{err}</div>}

      {d && (<>
        <div style={card}>
          <div style={h}><ListChecks size={14} /> Waiting on you ({d.pending.length})</div>
          {d.pending.length === 0 && <div style={{ fontSize: 14 }}>Nothing is waiting on you.</div>}
          {d.pending.slice(0, 8).map(p => (
            <div key={p.id} style={{ padding: "8px 0", borderTop: "1px solid var(--border)", fontSize: 14, lineHeight: 1.35 }}>
              <b style={{ color: "var(--accent2)" }}>{p.id}</b> {p.item.length > 170 ? p.item.slice(0, 170) + "…" : p.item}
            </div>
          ))}
          {d.pending.length > 8 && <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>+{d.pending.length - 8} more — ask the CoS on WhatsApp: "pending"</div>}
        </div>

        <div style={card}>
          <div style={h}><Target size={14} /> Today's plan · {d.plan.done}/{d.plan.total} done</div>
          {d.plan.total > 0 && <div style={{ fontFamily: "monospace", fontSize: 13, color: "var(--green)", marginBottom: 8 }}>{bar} {pct}%</div>}
          {d.plan.total === 0 && <div style={{ fontSize: 14, color: "var(--text2)" }}>Nothing planned yet. Add the first item below.</div>}
          {d.plan.items.map(it => (
            <div key={it.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}>
              <div style={{ fontSize: 11, color: "var(--text2)" }}>{d.plan.projects[it.project] || it.project}{it.owner ? ` · @${it.owner}` : ""}{it.carried_from ? " · carried over" : ""}</div>
              <div style={{ fontSize: 15, margin: "2px 0 8px", opacity: it.status === "open" ? 1 : 0.7 }}>
                {it.status === "done" ? "✅ " : it.status === "missed" ? "❌ " : "⏳ "}#{it.id} {it.item}
                {it.status === "missed" && <span style={{ color: "var(--amber)", fontSize: 12 }}> — {it.reason}{it.fault && it.fault !== it.reason ? ` (${it.fault})` : ""}</span>}
              </div>
              {it.status === "open" && missFor !== it.id && (
                <div style={{ display: "flex", gap: 8 }}>
                  <button disabled={busy} style={{ ...btn, flex: 1, borderColor: "var(--green)", color: "var(--green)" }} onClick={() => call(`/api/plan/items/${it.id}/close`, { status: "done" })}><CheckCircle2 size={16} style={{ display: "inline", marginRight: 6 }} />Done</button>
                  <button disabled={busy} style={{ ...btn, flex: 1, borderColor: "var(--amber)", color: "var(--amber)" }} onClick={() => setMissFor(it.id)}><XCircle size={16} style={{ display: "inline", marginRight: 6 }} />Missed</button>
                </div>
              )}
              {it.status === "open" && missFor === it.id && (
                <div>
                  <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 6 }}>Why? Tap one:</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {d.reasons.map(r => (
                      <button key={r} disabled={busy} style={btn} onClick={async () => { await call(`/api/plan/items/${it.id}/close`, { status: "missed", reason: r }); setMissFor(null) }}>{r}</button>
                    ))}
                    <button style={{ ...btn, color: "var(--text2)" }} onClick={() => setMissFor(null)}>cancel</button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 6 }}>
            <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 6 }}>Add to today's plan</div>
            <select value={proj} onChange={e => setNewProject(e.target.value)} style={{ ...btn, width: "100%", marginBottom: 8 }}>
              {projects.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
            </select>
            <div style={{ display: "flex", gap: 8 }}>
              <input value={newText} onChange={e => setNewText(e.target.value)} placeholder="e.g. pour slab C2 @Ramesh" style={{ ...btn, flex: 1, padding: "0 12px" }} />
              <button disabled={busy || !newText.trim()} style={{ ...btn, borderColor: "var(--accent)", color: "var(--accent2)" }}
                onClick={async () => {
                  const m = newText.match(/^(.*?)\s@\s*([A-Za-z][A-Za-z .'-]{0,30})$/)
                  await call("/api/plan/items", { project: proj, date: d.date, items: [{ item: (m ? m[1] : newText).trim(), owner: m ? m[2].trim() : "" }] })
                  setNewText("")
                }}><Plus size={18} /></button>
            </div>
          </div>
        </div>

        <div style={card}>
          <div style={h}><Target size={14} /> Objectives</div>
          {d.objectives.map((o, i) => <div key={i} style={{ fontSize: 13, padding: "6px 0", borderTop: i ? "1px solid var(--border)" : "none", lineHeight: 1.35 }}>{o.replace(/^•\s*/, "")}</div>)}
        </div>

        <div style={card}>
          <div style={h}><FileText size={14} /> Tenders open now</div>
          {d.tenders.length === 0 && <div style={{ fontSize: 14, color: "var(--text2)" }}>None in the pipeline.</div>}
          {d.tenders.map((t, i) => (
            <div key={i} style={{ padding: "8px 0", borderTop: i ? "1px solid var(--border)" : "none", fontSize: 13, lineHeight: 1.35 }}>
              <b>{t.buyer}</b> · {t.category}{t.due_date ? ` · due ${t.due_date}` : ""}<div style={{ color: "var(--text2)" }}>{t.notes}</div>
            </div>
          ))}
          {d.competitors && <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 8 }}>{d.competitors}</div>}
        </div>

        <div style={card}>
          <div style={h}><BarChart3 size={14} /> Markets</div>
          <div style={{ fontSize: 13, lineHeight: 1.4 }}>{d.volume || "Volume watch has not run yet (first run 19:15 IST on a trading day)."}</div>
        </div>

        <div style={card}>
          <div style={h}><Activity size={14} /> System</div>
          <div style={{ fontSize: 13, lineHeight: 1.4 }}>
            {d.system.enabled != null ? `${d.system.enabled} agents on` : "agents: unknown"}{d.system.late.length ? ` · late: ${d.system.late.join(", ")}` : " · all on time"}
          </div>
          {d.credits && <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 6 }}>{d.credits}</div>}
        </div>
      </>)}
    </div>
  )
}
