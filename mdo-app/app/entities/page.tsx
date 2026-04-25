"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Building2, User, ExternalLink, Search, AlertTriangle } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function fetchEntities(type?: string) {
  const q = type ? `?type=${type}` : ""
  const r = await fetch(`${BASE}/api/entities${q}`, { cache: "no-store" })
  if (!r.ok) throw new Error()
  return r.json()
}
async function fetchFilings(entity?: string) {
  const q = entity ? `?entity=${encodeURIComponent(entity)}` : ""
  const r = await fetch(`${BASE}/api/compliance/filings${q}`, { cache: "no-store" })
  if (!r.ok) return { filings: [] }
  return r.json()
}

const STATUS_COLOR: Record<string, string> = {
  active: "var(--green)", inactive: "var(--text2)", dormant: "var(--amber)", dissolved: "var(--red)"
}
const TYPE_ICON: Record<string, typeof Building2> = {
  company: Building2, individual: User, huf: User, firm: Building2,
}

function EntityCard({ e, onClick }: { e: any; onClick: () => void }) {
  const Icon = TYPE_ICON[e.entity_type] || Building2
  const hasAlert = e.notes?.toLowerCase().includes("critical") || e.notes?.toLowerCase().includes("§454")

  return (
    <div onClick={onClick} className="rounded-xl border p-4 cursor-pointer transition-colors hover:border-indigo-500/50"
      style={{ background: "var(--bg2)", borderColor: hasAlert ? "var(--red)" : "var(--border)" }}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: "var(--bg3)" }}>
            <Icon size={15} style={{ color: "var(--text2)" }} />
          </div>
          <div className="min-w-0">
            <div className="font-semibold text-sm leading-snug truncate">{e.name}</div>
            <div className="text-xs" style={{ color: "var(--text2)" }}>{e.business || e.entity_type}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {hasAlert && <AlertTriangle size={13} style={{ color: "var(--red)" }} />}
          <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: STATUS_COLOR[e.status] || "var(--text2)", background: (STATUS_COLOR[e.status] || "var(--text2)") + "18" }}>
            {e.status}
          </span>
        </div>
      </div>
      {e.location && <div className="text-xs mt-2" style={{ color: "var(--text2)" }}>{e.location}</div>}
      {e.annual_turnover && (
        <div className="text-xs mt-1 font-medium" style={{ color: "var(--accent2)" }}>{e.annual_turnover}</div>
      )}
      {e.notes && (
        <div className="text-xs mt-1 px-2 py-1 rounded" style={{ background: hasAlert ? "rgba(239,68,68,0.08)" : "var(--bg3)", color: hasAlert ? "var(--red)" : "var(--text2)" }}>
          {e.notes}
        </div>
      )}
    </div>
  )
}

function EntityDrawer({ entity, onClose }: { entity: any; onClose: () => void }) {
  const { data } = useQuery({
    queryKey: ["filings_entity", entity.name],
    queryFn: () => fetchFilings(entity.name),
  })
  const filings: any[] = data?.filings ?? []
  const pending = filings.filter(f => f.status === "pending" || f.status === "overdue")

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(0,0,0,0.5)" }} onClick={onClose}>
      <div className="w-full max-w-lg h-full overflow-y-auto flex flex-col" style={{ background: "var(--bg2)" }}
        onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 border-b flex items-center justify-between sticky top-0"
          style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div>
            <div className="font-bold">{entity.name}</div>
            <div className="text-xs" style={{ color: "var(--text2)" }}>{entity.entity_type} · {entity.location}</div>
          </div>
          <button onClick={onClose} className="text-xl leading-none" style={{ color: "var(--text2)" }}>×</button>
        </div>

        <div className="flex-1 p-6 space-y-5">
          {/* Key fields */}
          <div className="grid grid-cols-2 gap-3">
            {[
              { l: "Business",  v: entity.business      },
              { l: "Turnover",  v: entity.annual_turnover || "—" },
              { l: "Directors", v: entity.directors || "—"  },
              { l: "Status",    v: entity.status            },
              { l: "CIN",       v: entity.cin || "—"        },
              { l: "GST",       v: entity.gstin || "—"      },
            ].map(({ l, v }) => (
              <div key={l} className="px-3 py-2 rounded-lg" style={{ background: "var(--bg3)" }}>
                <div className="text-xs" style={{ color: "var(--text2)" }}>{l}</div>
                <div className="text-sm font-medium">{v}</div>
              </div>
            ))}
          </div>

          {entity.notes && (
            <div className="px-3 py-2 rounded-lg text-sm" style={{ background: "rgba(239,68,68,0.08)", color: "var(--red)" }}>
              {entity.notes}
            </div>
          )}

          {/* Compliance filings */}
          <div>
            <div className="font-semibold text-sm mb-3">
              Compliance Filings
              {pending.length > 0 && (
                <span className="ml-2 text-xs px-1.5 py-0.5 rounded-full" style={{ background: "rgba(245,158,11,0.15)", color: "var(--amber)" }}>
                  {pending.length} pending
                </span>
              )}
            </div>
            <div className="space-y-2">
              {filings.length === 0 && <div className="text-sm" style={{ color: "var(--text2)" }}>No filings recorded</div>}
              {filings.map(f => (
                <div key={f.id} className="flex items-start justify-between px-3 py-2 rounded-lg"
                  style={{ background: "var(--bg3)", borderLeft: `3px solid ${f.status === "overdue" ? "var(--red)" : f.status === "filed" ? "var(--green)" : "var(--amber)"}` }}>
                  <div>
                    <div className="text-sm font-medium">{f.filing_type} — {f.description}</div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
                      {f.period} · Due: {f.due_date || "—"} · {f.assigned_to}
                    </div>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full ml-2 shrink-0"
                    style={{ color: f.status === "filed" ? "var(--green)" : f.status === "overdue" ? "var(--red)" : "var(--amber)", background: "transparent", border: "1px solid currentColor" }}>
                    {f.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* External links */}
          <div>
            <div className="font-semibold text-sm mb-2">Quick Actions</div>
            <div className="flex flex-wrap gap-2">
              {[
                { l: "MCA Search", url: `https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do` },
                { l: "GST Portal",  url: "https://www.gst.gov.in" },
                { l: "Income Tax",  url: "https://www.incometax.gov.in" },
                { l: "NCLT",        url: "https://nclt.gov.in" },
              ].map(({ l, url }) => (
                <a key={l} href={url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border"
                  style={{ borderColor: "var(--border)", color: "var(--text2)" }}>
                  <ExternalLink size={10} /> {l}
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const TYPES = ["all","company","individual","huf","firm"] as const

export default function EntitiesPage() {
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [search, setSearch]         = useState("")
  const [selected, setSelected]     = useState<any>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["entities", typeFilter],
    queryFn: () => fetchEntities(typeFilter === "all" ? undefined : typeFilter),
    refetchInterval: 60_000,
  })
  const entities: any[] = data?.entities ?? []

  const filtered = entities.filter(e =>
    !search || e.name.toLowerCase().includes(search.toLowerCase()) ||
    e.business?.toLowerCase().includes(search.toLowerCase())
  )

  const alerts = entities.filter(e => e.notes?.toLowerCase().includes("critical") || e.status === "inactive")

  return (
    <div className="space-y-5 max-w-5xl">
      {selected && <EntityDrawer entity={selected} onClose={() => setSelected(null)} />}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Building2 size={20} style={{ color: "var(--accent2)" }} />
          <h1 className="text-2xl font-bold">ANS Group Entities</h1>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            {entities.length} entities
          </span>
        </div>
        {alerts.length > 0 && (
          <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full" style={{ background: "rgba(239,68,68,0.12)", color: "var(--red)" }}>
            <AlertTriangle size={11} /> {alerts.length} need attention
          </span>
        )}
      </div>

      {/* Search + filter */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border flex-1 min-w-48"
          style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <Search size={14} style={{ color: "var(--text2)" }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search entities…"
            className="flex-1 bg-transparent text-sm outline-none" style={{ color: "var(--text)" }} />
        </div>
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {TYPES.map(t => (
            <button key={t} onClick={() => setTypeFilter(t)}
              className="px-3 py-2 text-xs font-medium capitalize transition-colors"
              style={{ background: typeFilter === t ? "var(--bg3)" : "var(--bg2)", color: typeFilter === t ? "var(--text)" : "var(--text2)" }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {isError && (
        <div className="text-center py-8 text-sm" style={{ color: "var(--red)" }}>
          Backend offline — run: <code>python mdo_server.py</code>
        </div>
      )}
      {isLoading && <div className="text-sm py-8 text-center" style={{ color: "var(--text2)" }}>Loading…</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {filtered.map(e => <EntityCard key={e.id} e={e} onClick={() => setSelected(e)} />)}
      </div>
    </div>
  )
}
