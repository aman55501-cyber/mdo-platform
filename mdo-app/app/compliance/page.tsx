"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ShieldAlert, AlertTriangle, CheckCircle2, Clock, Filter, ExternalLink, Phone } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function fetchFilings(entity?: string, status?: string) {
  const q = new URLSearchParams()
  if (entity) q.set("entity", entity)
  if (status) q.set("status", status)
  const r = await fetch(`${BASE}/api/compliance/filings?${q}`, { cache: "no-store" })
  if (!r.ok) throw new Error("API error")
  return r.json()
}

async function updateFiling(id: number, body: object) {
  const r = await fetch(`${BASE}/api/compliance/filings/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  return r.json()
}

function daysUntil(d?: string) {
  if (!d) return null
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000)
  if (diff < 0)  return { label: `${Math.abs(diff)}d overdue`, color: "var(--red)",   bg: "rgba(239,68,68,0.12)"  }
  if (diff === 0) return { label: "Due today",                   color: "var(--red)",   bg: "rgba(239,68,68,0.12)"  }
  if (diff <= 7)  return { label: `${diff}d left`,               color: "var(--amber)", bg: "rgba(245,158,11,0.12)" }
  return           { label: `${diff}d left`,                     color: "var(--text2)", bg: "transparent" }
}

const STATUS_META: Record<string, { icon: any; color: string; label: string }> = {
  pending:  { icon: Clock,         color: "var(--amber)",  label: "Pending"  },
  overdue:  { icon: AlertTriangle, color: "var(--red)",    label: "Overdue"  },
  filed:    { icon: CheckCircle2,  color: "var(--green)",  label: "Filed"    },
  na:       { icon: CheckCircle2,  color: "var(--text2)",  label: "N/A"      },
}

const FILING_TYPE_COLOR: Record<string, string> = {
  "ROC Annual Return":    "#6366f1",
  "GST Return":          "#f59e0b",
  "Income Tax Return":   "#22c55e",
  "TDS Return":          "#06b6d4",
  "Advance Tax":         "#ec4899",
  "DIR-3 KYC":          "#8b5cf6",
}

function FilingRow({ f, onMarkFiled, onMarkPending }: { f: any; onMarkFiled: () => void; onMarkPending: () => void }) {
  const due = daysUntil(f.due_date)
  const meta = STATUS_META[f.status] ?? STATUS_META.pending
  const Icon = meta.icon
  const typeColor = FILING_TYPE_COLOR[f.filing_type] || "#94a3b8"
  const filed = f.status === "filed" || f.status === "na"

  return (
    <tr className="border-b transition-all" style={{ borderColor: "var(--border)", opacity: filed ? 0.6 : 1 }}>
      <td className="px-4 py-3">
        <div className="font-medium text-sm">{f.entity_name}</div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>{f.entity_type}</div>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs px-2 py-0.5 rounded-full font-medium"
          style={{ background: typeColor + "18", color: typeColor }}>
          {f.filing_type}
        </span>
        {f.period && <div className="text-xs mt-1" style={{ color: "var(--text2)" }}>{f.period}</div>}
      </td>
      <td className="px-4 py-3 text-sm">{f.due_date ? new Date(f.due_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—"}</td>
      <td className="px-4 py-3">
        {due && (
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: due.bg, color: due.color }}>
            {due.label}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="flex items-center gap-1 text-xs" style={{ color: meta.color }}>
          <Icon size={12} />{meta.label}
        </span>
        {f.filed_on && <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>Filed {f.filed_on}</div>}
      </td>
      <td className="px-4 py-3">
        {f.notes && <div className="text-xs" style={{ color: "var(--text2)" }}>{f.notes}</div>}
      </td>
      <td className="px-4 py-3 text-right">
        {!filed ? (
          <button onClick={onMarkFiled}
            className="text-xs px-3 py-1 rounded-lg font-medium transition-colors"
            style={{ background: "rgba(34,197,94,0.15)", color: "var(--green)" }}>
            Mark Filed
          </button>
        ) : (
          <button onClick={onMarkPending}
            className="text-xs px-2 py-1 rounded-lg"
            style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            Reopen
          </button>
        )}
      </td>
    </tr>
  )
}

const STATUS_FILTERS = ["all", "pending", "overdue", "filed"] as const

export default function CompliancePage() {
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [entityFilter, setEntityFilter] = useState<string>("")
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["filings", statusFilter, entityFilter],
    queryFn: () => fetchFilings(entityFilter || undefined, statusFilter === "all" ? undefined : statusFilter),
    refetchInterval: 60_000,
  })

  const filings: any[] = data?.filings ?? []

  const mutUpdate = useMutation({
    mutationFn: ({ id, body }: { id: number; body: object }) => updateFiling(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["filings"] }),
  })

  const overdue = filings.filter(f => f.status === "overdue").length
  const pending = filings.filter(f => f.status === "pending").length
  const filed   = filings.filter(f => f.status === "filed").length

  // Group by entity for display
  const entities = Array.from(new Set(filings.map(f => f.entity_name))).sort()

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <ShieldAlert size={20} style={{ color: "var(--amber)" }} />
          <h1 className="text-2xl font-bold">Compliance</h1>
        </div>
        <div className="flex gap-3">
          {[
            { label: "Overdue",  count: overdue, color: "var(--red)"   },
            { label: "Pending",  count: pending, color: "var(--amber)" },
            { label: "Filed",    count: filed,   color: "var(--green)" },
          ].map(({ label, count, color }) => (
            <div key={label} className="text-center px-4 py-2 rounded-xl border" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
              <div className="text-xl font-bold" style={{ color }}>{count}</div>
              <div className="text-xs" style={{ color: "var(--text2)" }}>{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* CA Contact — always visible */}
      <div className="rounded-xl border p-4 flex items-center justify-between" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        <div>
          <div className="text-xs font-bold uppercase tracking-wide mb-1" style={{ color: "var(--text2)" }}>CA Contact</div>
          <div className="font-semibold">CA Vimal Agrawal</div>
          <div className="text-sm mt-0.5" style={{ color: "var(--text2)" }}>All 26 entity compliance</div>
        </div>
        <a href="tel:9755220259" className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium"
          style={{ background: "rgba(99,102,241,0.15)", color: "var(--accent2)" }}>
          <Phone size={14} /> 9755220259
        </a>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {STATUS_FILTERS.map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className="px-3 py-1.5 text-xs font-medium capitalize transition-colors"
              style={{ background: statusFilter === s ? "var(--bg3)" : "var(--bg2)", color: statusFilter === s ? "var(--text)" : "var(--text2)" }}>
              {s}
            </button>
          ))}
        </div>
        <select value={entityFilter} onChange={e => setEntityFilter(e.target.value)}
          className="px-3 py-1.5 rounded-xl text-xs border outline-none"
          style={{ background: "var(--bg2)", borderColor: "var(--border)", color: "var(--text2)" }}>
          <option value="">All Entities</option>
          {entities.map(e => <option key={e} value={e}>{e}</option>)}
        </select>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text2)" }}>
          <Filter size={11} />{filings.length} filings
        </div>
      </div>

      {isError && (
        <div className="text-sm text-center py-8" style={{ color: "var(--red)" }}>
          Backend offline — run: <code className="px-1 py-0.5 rounded" style={{ background: "var(--bg3)" }}>python mdo_server.py</code>
        </div>
      )}

      {/* Filings table */}
      <div className="rounded-xl border overflow-hidden" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        {isLoading && <div className="px-4 py-8 text-center text-sm" style={{ color: "var(--text2)" }}>Loading…</div>}
        {!isLoading && filings.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--text2)", borderBottom: "1px solid var(--border)" }}>
                  {["Entity", "Filing Type", "Due Date", "Timeline", "Status", "Notes", "Action"].map(h => (
                    <th key={h} className="px-4 py-3 text-xs text-left font-semibold uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filings.map(f => (
                  <FilingRow key={f.id} f={f}
                    onMarkFiled={() => mutUpdate.mutate({ id: f.id, body: { status: "filed" } })}
                    onMarkPending={() => mutUpdate.mutate({ id: f.id, body: { status: "pending" } })} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!isLoading && filings.length === 0 && (
          <div className="px-4 py-10 text-center text-sm" style={{ color: "var(--text2)" }}>
            No filings found for the selected filters.
          </div>
        )}
      </div>

      {/* External links */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          { label: "MCA Portal",    url: "https://www.mca.gov.in" },
          { label: "GST Portal",    url: "https://www.gst.gov.in" },
          { label: "Income Tax",    url: "https://www.incometax.gov.in" },
          { label: "TRACES (TDS)",  url: "https://www.tdscpc.gov.in" },
        ].map(({ label, url }) => (
          <a key={label} href={url} target="_blank" rel="noopener noreferrer"
            className="flex items-center justify-between px-3 py-2.5 rounded-xl border text-sm transition-colors"
            style={{ background: "var(--bg2)", borderColor: "var(--border)", color: "var(--text2)" }}>
            {label} <ExternalLink size={11} />
          </a>
        ))}
      </div>
    </div>
  )
}
