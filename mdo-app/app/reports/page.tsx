"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { FileText, AlertTriangle, Info, Clock, Wrench } from "lucide-react"
import { Markdown } from "@/lib/markdown"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type Finding = {
  level?: string; title?: string; detail?: string; action?: string
  owner?: string; entity?: string; domain?: string
}
type Report = {
  id: number; cadence: string; agent: string; title: string; summary: string
  body: string; findings_json: string
  n_critical: number; n_important: number; n_info: number; created_at: string
}

async function apiFetch<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" })
  if (!r.ok) throw new Error(String(r.status))
  return r.json()
}

const CADENCES = ["all", "hourly", "daily", "weekly", "monthly", "quarterly", "annual"]

function levelColor(level = "") {
  const l = level.toLowerCase()
  if (l.startsWith("crit")) return "var(--red)"
  if (l.startsWith("imp")) return "var(--amber)"
  return "var(--green)"
}

function ago(ts: string) {
  const t = new Date(ts.replace(" ", "T") + (ts.includes("Z") ? "" : "Z")).getTime()
  const mins = Math.floor((Date.now() - t) / 60000)
  if (mins < 60) return `${Math.max(mins, 0)}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
  return `${Math.floor(mins / 1440)}d ago`
}

export default function ReportsPage() {
  const [cadence, setCadence] = useState("all")
  const [openId, setOpenId] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["agent-reports", cadence],
    queryFn: () => apiFetch<{ reports: Report[] }>(
      `${BASE}/api/agent/reports?limit=40${cadence !== "all" ? `&cadence=${cadence}` : ""}`),
    refetchInterval: 60_000,
  })

  const { data: checksData } = useQuery({
    queryKey: ["checks-summary"],
    queryFn: () => apiFetch<{ checks: any[]; count: number; blocked: string[] }>(`${BASE}/api/checks`),
    refetchInterval: 120_000,
  })

  const reports = data?.reports || []
  const checks = checksData?.checks || []

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div className="flex items-center gap-3 mb-1">
        <FileText size={20} style={{ color: "var(--accent2)" }} />
        <h1 className="text-2xl font-bold">Agent Reports</h1>
      </div>
      <p className="text-xs mb-5" style={{ color: "var(--text2)" }}>
        Written by the autonomous agents running on your VPS — hourly watcher and daily brief.
        Silence from the hourly agent means nothing crossed a threshold.
      </p>

      {/* Checks coverage strip */}
      {checks.length > 0 && (
        <div className="glass rounded-xl px-4 py-3 mb-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold" style={{ letterSpacing: ".04em" }}>
              Coverage — {checks.filter(c => c.status === "active").length} active /{" "}
              {checks.filter(c => c.status === "blocked").length} blocked
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {checks.map(c => (
              <span key={c.code} title={c.status === "blocked" ? c.blocker : (c.threshold || c.title)}
                className="text-[10px] px-2 py-1 rounded-full"
                style={{
                  background: c.status === "blocked" ? "rgba(248,113,113,0.12)" : "rgba(52,211,153,0.10)",
                  color: c.status === "blocked" ? "var(--red)" : "var(--green)",
                  border: "1px solid " + (c.status === "blocked" ? "rgba(248,113,113,0.25)" : "rgba(52,211,153,0.2)"),
                }}>
                {c.cadence} · {c.code}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Cadence filter */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {CADENCES.map(c => (
          <button key={c} onClick={() => setCadence(c)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold capitalize"
            style={{
              background: cadence === c ? "rgba(109,106,248,0.15)" : "var(--bg2)",
              color: cadence === c ? "var(--accent2)" : "var(--text2)",
              border: `1px solid ${cadence === c ? "var(--accent)" : "var(--border)"}`,
              cursor: "pointer",
            }}>
            {c}
          </button>
        ))}
      </div>

      {isLoading && <div style={{ color: "var(--text2)", fontSize: 13 }}>Loading…</div>}

      {!isLoading && reports.length === 0 && (
        <div className="glass rounded-xl p-10 text-center">
          <FileText size={30} style={{ color: "var(--text2)", margin: "0 auto 12px" }} />
          <div className="font-semibold mb-2">No reports yet</div>
          <div style={{ fontSize: 13, color: "var(--text2)", maxWidth: 420, margin: "0 auto" }}>
            The daily brief files at 06:57 IST; the hourly watcher files only when something
            crosses a threshold. If this stays empty for a full day, check
            <code style={{ margin: "0 4px" }}>/var/log/mdo-agent.log</code> on the VPS.
          </div>
        </div>
      )}

      <div className="space-y-3">
        {reports.map(r => {
          let findings: Finding[] = []
          try { findings = JSON.parse(r.findings_json || "[]") } catch {}
          const open = openId === r.id
          return (
            <div key={r.id} className="glass card-hover rounded-xl overflow-hidden">
              <button onClick={() => setOpenId(open ? null : r.id)}
                className="w-full text-left px-4 py-3"
                style={{ background: "none", border: "none", cursor: "pointer" }}>
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-[10px] px-2 py-0.5 rounded-full uppercase font-bold"
                    style={{ background: "rgba(143,140,255,0.12)", color: "var(--accent2)", letterSpacing: ".08em" }}>
                    {r.cadence}
                  </span>
                  <span className="text-sm font-semibold" style={{ color: "var(--text)" }}>{r.title}</span>
                  <span className="flex items-center gap-1 text-[11px] ml-auto" style={{ color: "var(--text2)" }}>
                    <Clock size={10} /> {ago(r.created_at)}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] mb-1.5" style={{ color: "var(--text2)" }}>
                  {r.n_critical > 0 && <span style={{ color: "var(--red)" }}>🔴 {r.n_critical}</span>}
                  {r.n_important > 0 && <span style={{ color: "var(--amber)" }}>🟡 {r.n_important}</span>}
                  {r.n_info > 0 && <span style={{ color: "var(--green)" }}>🟢 {r.n_info}</span>}
                  {r.agent && <span className="flex items-center gap-1"><Wrench size={9} />{r.agent}</span>}
                </div>
                <div style={{ fontSize: 12.5, color: "var(--text2)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                  {r.summary}
                </div>
              </button>

              {open && (
                <div className="px-4 pb-4 fade-up" style={{ borderTop: "1px solid var(--border)" }}>
                  {findings.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {findings.map((f, i) => (
                        <div key={i} className="rounded-lg px-3 py-2"
                          style={{ background: "var(--bg2)", borderLeft: `2px solid ${levelColor(f.level)}` }}>
                          <div className="flex items-center gap-2 mb-1">
                            {String(f.level || "").toLowerCase().startsWith("crit")
                              ? <AlertTriangle size={12} style={{ color: "var(--red)" }} />
                              : <Info size={12} style={{ color: levelColor(f.level) }} />}
                            <span className="text-[13px] font-semibold">{f.title}</span>
                            {f.entity && <span className="text-[10px] px-1.5 py-0.5 rounded"
                              style={{ background: "var(--bg3)", color: "var(--text2)" }}>{f.entity}</span>}
                          </div>
                          {f.detail && <div style={{ fontSize: 12.5, color: "var(--text2)", lineHeight: 1.55 }}>{f.detail}</div>}
                          {f.action && (
                            <div style={{ fontSize: 12.5, marginTop: 4, color: "var(--accent2)" }}>
                              → {f.action}{f.owner ? ` (${f.owner})` : ""}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {r.body && (
                    <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
                      <Markdown text={r.body} />
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
