"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Brain, Check, Clock, BellOff, AlertTriangle, Info, Zap, ChevronDown } from "lucide-react"
import type { IntelItem, Urgency, IntelCategory } from "@/lib/types"

const URGENCY_COLOR: Record<Urgency, string> = {
  CRITICAL: "var(--red)",
  HIGH:     "var(--amber)",
  MEDIUM:   "var(--cyan)",
  LOW:      "var(--text2)",
}
const URGENCY_BG: Record<Urgency, string> = {
  CRITICAL: "rgba(239,68,68,0.12)",
  HIGH:     "rgba(245,158,11,0.12)",
  MEDIUM:   "rgba(6,182,212,0.12)",
  LOW:      "rgba(148,163,184,0.08)",
}
const URGENCY_ICON: Record<Urgency, typeof AlertTriangle> = {
  CRITICAL: Zap,
  HIGH:     AlertTriangle,
  MEDIUM:   Clock,
  LOW:      Info,
}

function UrgencyBadge({ u }: { u: Urgency }) {
  const Icon = URGENCY_ICON[u]
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-semibold"
      style={{ background: URGENCY_BG[u], color: URGENCY_COLOR[u] }}>
      <Icon size={10} />
      {u}
    </span>
  )
}

function IntelCard({ item }: { item: IntelItem }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)

  const mutOpts = { onSuccess: () => qc.invalidateQueries({ queryKey: ["intel"] }) }
  const resolve     = useMutation({ mutationFn: () => api.intel.resolve(item.id), ...mutOpts })
  const acknowledge = useMutation({ mutationFn: () => api.intel.acknowledge(item.id), ...mutOpts })
  const snooze      = useMutation({ mutationFn: () => api.intel.snooze(item.id, 1), ...mutOpts })

  const isDone = item.status === "resolved"

  return (
    <div className="rounded-xl border overflow-hidden"
      style={{ background: "var(--bg2)", borderColor: isDone ? "var(--border)" : URGENCY_COLOR[item.urgency] + "40", opacity: isDone ? 0.6 : 1 }}>
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <UrgencyBadge u={item.urgency} />
              <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                {item.category}
              </span>
              {item.entity && <span className="text-xs font-medium" style={{ color: "var(--accent2)" }}>{item.entity}</span>}
            </div>
            <div className="mt-1.5 font-semibold text-sm leading-snug">{item.title}</div>
          </div>
          <button onClick={() => setExpanded((v) => !v)} style={{ color: "var(--text2)" }}>
            <ChevronDown size={16} className={expanded ? "rotate-180" : ""} style={{ transition: "transform 0.2s" }} />
          </button>
        </div>

        {expanded && (
          <div className="mt-2 text-sm leading-relaxed" style={{ color: "var(--text2)" }}>
            {item.body}
            {item.due_date && <div className="mt-1 text-xs">Due: {item.due_date}</div>}
          </div>
        )}
      </div>

      {!isDone && (
        <div className="px-4 pb-3 flex gap-2">
          <button onClick={() => resolve.mutate()}
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg"
            style={{ background: "rgba(34,197,94,0.12)", color: "var(--green)" }}>
            <Check size={11} /> Resolve
          </button>
          {item.status === "open" && (
            <button onClick={() => acknowledge.mutate()}
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg"
              style={{ background: "rgba(99,102,241,0.12)", color: "var(--accent2)" }}>
              <Check size={11} /> Ack
            </button>
          )}
          <button onClick={() => snooze.mutate()}
            className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg"
            style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            <BellOff size={11} /> Snooze 1d
          </button>
        </div>
      )}
    </div>
  )
}

const CATEGORIES: ("all" | IntelCategory)[] = ["all", "trading", "vwlr", "compliance", "wealth", "market"]
const URGENCIES: ("all" | Urgency)[] = ["all", "CRITICAL", "HIGH", "MEDIUM", "LOW"]

export default function IntelPage() {
  const [cat, setCat]     = useState<"all" | IntelCategory>("all")
  const [urg, setUrg]     = useState<"all" | Urgency>("all")
  const [status, setStatus] = useState<"open" | "all">("open")

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["intel", cat, urg, status],
    queryFn: () => api.intel.list({
      category: cat === "all" ? undefined : cat,
      urgency:  urg === "all" ? undefined : urg,
      status:   status === "all" ? undefined : status,
    }),
    refetchInterval: 30_000,
  })

  const grouped = items.reduce<Record<Urgency, IntelItem[]>>((acc, item) => {
    acc[item.urgency] = [...(acc[item.urgency] || []), item]
    return acc
  }, {} as Record<Urgency, IntelItem[]>)

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Brain size={20} style={{ color: "var(--accent2)" }} />
        <h1 className="text-2xl font-bold">Intel Centre</h1>
        {items.length > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full font-bold"
            style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>
            {items.filter(i => i.urgency === "CRITICAL" || i.urgency === "HIGH").length} urgent
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {(["open", "all"] as const).map((s) => (
            <button key={s} onClick={() => setStatus(s)}
              className="px-3 py-1.5 text-xs font-medium transition-colors"
              style={{ background: status === s ? "var(--bg3)" : "var(--bg2)", color: status === s ? "var(--text)" : "var(--text2)" }}>
              {s === "open" ? "Open" : "All"}
            </button>
          ))}
        </div>
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {URGENCIES.map((u) => (
            <button key={u} onClick={() => setUrg(u)}
              className="px-3 py-1.5 text-xs font-medium transition-colors"
              style={{ background: urg === u ? "var(--bg3)" : "var(--bg2)", color: urg === u ? "var(--text)" : "var(--text2)" }}>
              {u === "all" ? "All" : u}
            </button>
          ))}
        </div>
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {CATEGORIES.map((c) => (
            <button key={c} onClick={() => setCat(c)}
              className="px-3 py-1.5 text-xs font-medium capitalize transition-colors"
              style={{ background: cat === c ? "var(--bg3)" : "var(--bg2)", color: cat === c ? "var(--text)" : "var(--text2)" }}>
              {c}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <div className="text-sm" style={{ color: "var(--text2)" }}>Loading…</div>}

      {/* Urgency buckets */}
      {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as Urgency[]).map((u) => {
        const bucket = grouped[u]
        if (!bucket?.length) return null
        return (
          <div key={u}>
            <div className="text-xs font-bold mb-2 uppercase tracking-wider" style={{ color: URGENCY_COLOR[u] }}>
              {u} · {bucket.length}
            </div>
            <div className="space-y-2">
              {bucket.map((item) => <IntelCard key={item.id} item={item} />)}
            </div>
          </div>
        )
      })}

      {!isLoading && items.length === 0 && (
        <div className="text-center py-16 text-sm" style={{ color: "var(--text2)" }}>
          No intel items found
        </div>
      )}
    </div>
  )
}
