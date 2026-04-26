"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, AlertCircle, Info, RefreshCw, CheckCircle,
  Clock, Building2, ShieldAlert, TrendingUp, Briefcase, Target
} from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...opts })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

const DOMAIN_META: Record<string, { icon: any; color: string }> = {
  Compliance:   { icon: ShieldAlert, color: "var(--red)" },
  Sales:        { icon: Briefcase,   color: "var(--accent2)" },
  Investments:  { icon: TrendingUp,  color: "var(--green)" },
  Operations:   { icon: Building2,   color: "var(--cyan)" },
  Strategic:    { icon: Target,      color: "var(--amber)" },
}

const LEVEL_META: Record<string, { icon: any; bg: string; border: string; text: string; label: string; emoji: string }> = {
  critical:  { icon: AlertTriangle, bg: "rgba(239,68,68,0.10)",  border: "rgba(239,68,68,0.5)",  text: "var(--red)",   label: "Critical",      emoji: "🔴" },
  important: { icon: AlertCircle,   bg: "rgba(245,158,11,0.10)", border: "rgba(245,158,11,0.5)", text: "var(--amber)", label: "Important",     emoji: "🟡" },
  info:      { icon: Info,          bg: "rgba(34,197,94,0.10)",  border: "rgba(34,197,94,0.4)",  text: "var(--green)", label: "Informational", emoji: "🟢" },
}

function AlertCard({ alert, onAck }: { alert: any; onAck: () => void }) {
  const lvl = LEVEL_META[alert.level] || LEVEL_META.info
  const dom = DOMAIN_META[alert.domain] || { icon: Info, color: "var(--text2)" }
  const DomainIcon = dom.icon

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: lvl.bg, border: `1px solid ${lvl.border}` }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <DomainIcon size={14} style={{ color: dom.color, flexShrink: 0 }} />
          <span className="text-xs font-semibold uppercase" style={{ color: dom.color, letterSpacing: "0.05em" }}>
            {alert.domain}
          </span>
          <span className="text-xs" style={{ color: "var(--text2)" }}>·</span>
          <span className="text-xs" style={{ color: "var(--text2)" }}>
            {new Date(alert.created_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
        <button
          onClick={onAck}
          title="Acknowledge"
          className="text-xs px-2 py-1 rounded transition-all flex items-center gap-1"
          style={{ background: "var(--bg)", color: "var(--text2)", border: "1px solid var(--border)" }}
        >
          <CheckCircle size={11} /> Ack
        </button>
      </div>

      <div className="font-bold text-base mb-3" style={{ color: "var(--text)" }}>
        {alert.title}
      </div>

      <div className="space-y-2 text-sm">
        {alert.what_changed && (
          <div className="flex gap-2">
            <span style={{ color: "var(--text2)", fontWeight: 600, minWidth: 110, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 2 }}>
              What changed
            </span>
            <span style={{ color: "var(--text)" }}>{alert.what_changed}</span>
          </div>
        )}
        {alert.why_matters && (
          <div className="flex gap-2">
            <span style={{ color: "var(--text2)", fontWeight: 600, minWidth: 110, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 2 }}>
              Why it matters
            </span>
            <span style={{ color: "var(--text)" }}>{alert.why_matters}</span>
          </div>
        )}
        {alert.recommended_action && (
          <div className="flex gap-2">
            <span style={{ color: lvl.text, fontWeight: 700, minWidth: 110, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", marginTop: 2 }}>
              → Action
            </span>
            <span style={{ color: lvl.text, fontWeight: 600 }}>{alert.recommended_action}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function BriefingPage() {
  const qc = useQueryClient()
  const [scanning, setScanning] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["briefing"],
    queryFn: () => apiFetch<any>("/api/intelligence/briefing"),
    refetchInterval: 60_000,
  })

  const ack = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/intelligence/alerts/${id}/ack`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["briefing"] }),
  })

  const runScan = async () => {
    setScanning(true)
    try {
      await apiFetch("/api/intelligence/scan", { method: "POST" })
      await refetch()
    } finally {
      setScanning(false)
    }
  }

  const critical  = data?.critical  || []
  const important = data?.important || []
  const info      = data?.info      || []
  const total     = critical.length + important.length + info.length

  const now = new Date()
  const dateStr = now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto" }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-2 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">Daily Briefing</h1>
          <div style={{ fontSize: 13, color: "var(--text2)" }}>
            {dateStr} · Chief of Staff + Risk + Analyst
          </div>
        </div>
        <button
          onClick={runScan}
          disabled={scanning}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{ background: scanning ? "var(--bg3)" : "var(--accent)", color: "#fff" }}
        >
          <RefreshCw size={14} style={{ animation: scanning ? "spin 1s linear infinite" : "none" }} />
          {scanning ? "Scanning…" : "Run Intelligence Scan"}
        </button>
      </div>

      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3 mb-6 mt-5">
        {[
          { level: "critical",  count: critical.length,  label: "Critical",      desc: "Immediate action" },
          { level: "important", count: important.length, label: "Important",     desc: "Attention soon" },
          { level: "info",      count: info.length,      label: "Informational", desc: "No action needed" },
        ].map(({ level, count, label, desc }) => {
          const lvl = LEVEL_META[level]
          return (
            <div key={level} className="rounded-xl p-4"
              style={{ background: lvl.bg, border: `1px solid ${lvl.border}` }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span style={{ fontSize: 16 }}>{lvl.emoji}</span>
                <span className="font-semibold text-sm" style={{ color: lvl.text }}>{label}</span>
              </div>
              <div className="text-3xl font-bold" style={{ color: lvl.text }}>{count}</div>
              <div style={{ fontSize: 11, color: "var(--text2)", marginTop: 2 }}>{desc}</div>
            </div>
          )
        })}
      </div>

      {/* Empty state */}
      {!isLoading && total === 0 && (
        <div className="rounded-xl p-12 text-center" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
          <CheckCircle size={36} style={{ color: "var(--green)", margin: "0 auto 14px" }} />
          <div className="font-bold text-lg mb-1">All clear</div>
          <div className="text-sm mb-4" style={{ color: "var(--text2)" }}>
            No alerts pending. Run the intelligence scan to refresh.
          </div>
          <button
            onClick={runScan}
            className="px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            Run First Scan
          </button>
        </div>
      )}

      {/* Critical */}
      {critical.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <span style={{ fontSize: 18 }}>🔴</span>
            <h2 className="text-lg font-bold" style={{ color: "var(--red)" }}>
              CRITICAL — Immediate action required
            </h2>
          </div>
          <div className="space-y-3">
            {critical.map((a: any) => <AlertCard key={a.id} alert={a} onAck={() => ack.mutate(a.id)} />)}
          </div>
        </div>
      )}

      {/* Important */}
      {important.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <span style={{ fontSize: 18 }}>🟡</span>
            <h2 className="text-lg font-bold" style={{ color: "var(--amber)" }}>
              IMPORTANT — Needs attention soon
            </h2>
          </div>
          <div className="space-y-3">
            {important.map((a: any) => <AlertCard key={a.id} alert={a} onAck={() => ack.mutate(a.id)} />)}
          </div>
        </div>
      )}

      {/* Info */}
      {info.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <span style={{ fontSize: 18 }}>🟢</span>
            <h2 className="text-lg font-bold" style={{ color: "var(--green)" }}>
              INFORMATIONAL
            </h2>
          </div>
          <div className="space-y-3">
            {info.map((a: any) => <AlertCard key={a.id} alert={a} onAck={() => ack.mutate(a.id)} />)}
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
