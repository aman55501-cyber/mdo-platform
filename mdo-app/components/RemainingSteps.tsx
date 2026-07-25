"use client"

import { useState } from "react"
import Link from "next/link"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Circle, ListTodo, ChevronDown, ChevronRight } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type RoadmapTask = {
  id: number; title: string; description: string
  entity: string; priority: string; status: string
}

const PRIORITY_COLOR: Record<string, string> = {
  critical: "var(--red)", high: "var(--amber)", medium: "var(--accent2)", low: "var(--text2)",
}

async function fetchRoadmap(): Promise<RoadmapTask[]> {
  const r = await fetch(`${BASE}/api/ops/tasks?category=roadmap`, { cache: "no-store" })
  if (!r.ok) throw new Error()
  const data = await r.json()
  return data.tasks ?? []
}

export function useRoadmap() {
  const qc = useQueryClient()
  const query = useQuery({ queryKey: ["roadmap"], queryFn: fetchRoadmap })
  const toggle = useMutation({
    mutationFn: (t: RoadmapTask) =>
      fetch(`${BASE}/api/ops/tasks/${t.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: t.status === "done" ? "open" : "done" }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roadmap"] })
      qc.invalidateQueries({ queryKey: ["ops_tasks"] })
    },
  })
  return { ...query, toggle }
}

/** Full panel — lives on /lifemap, always above the map. */
export function RemainingStepsPanel() {
  const { data, isLoading, toggle } = useRoadmap()
  const [showDone, setShowDone] = useState(false)
  if (isLoading || !data) return null

  const open = data.filter(t => t.status !== "done")
  const done = data.filter(t => t.status === "done")
  const shown = showDone ? [...open, ...done] : open

  // group by phase (entity field)
  const phases = Array.from(new Set(shown.map(t => t.entity)))

  return (
    <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <ListTodo size={15} style={{ color: "var(--accent2)" }} />
          <span className="font-semibold text-sm">Remaining Steps</span>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            {open.length} open · {done.length} done
          </span>
        </div>
        <button onClick={() => setShowDone(!showDone)} className="text-xs" style={{ color: "var(--text2)" }}>
          {showDone ? "hide done" : "show done"}
        </button>
      </div>

      {/* progress bar */}
      <div className="h-1 rounded-full mb-3 overflow-hidden" style={{ background: "var(--bg3)" }}>
        <div className="h-full rounded-full transition-all"
          style={{ width: `${data.length ? Math.round((done.length / data.length) * 100) : 0}%`, background: "var(--green)" }} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
        {phases.map(phase => (
          <div key={phase} className="mb-1">
            <div className="text-[10px] uppercase tracking-wider py-1" style={{ color: "var(--text2)", opacity: 0.6 }}>
              {phase}
            </div>
            {shown.filter(t => t.entity === phase).map(t => {
              const isDone = t.status === "done"
              return (
                <button key={t.id} onClick={() => toggle.mutate(t)}
                  className="w-full flex items-start gap-2 py-1 text-left group" title={t.description}>
                  {isDone
                    ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" style={{ color: "var(--green)" }} />
                    : <Circle size={14} className="mt-0.5 shrink-0" style={{ color: PRIORITY_COLOR[t.priority] || "var(--text2)" }} />}
                  <span className="min-w-0">
                    <span className="text-xs font-medium block leading-snug"
                      style={{ color: isDone ? "var(--text2)" : "var(--text)", textDecoration: isDone ? "line-through" : "none" }}>
                      {t.title}
                    </span>
                    <span className="text-[10px] leading-snug block" style={{ color: "var(--text2)", opacity: 0.75 }}>
                      {t.description}
                    </span>
                  </span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Compact variant — lives in the sidebar so the next steps are ALWAYS visible. */
export function NextStepsMini() {
  const { data } = useRoadmap()
  const [collapsed, setCollapsed] = useState(false)
  if (!data) return null
  const open = data.filter(t => t.status !== "done")
  if (open.length === 0) return null
  const top = open.slice(0, 3)

  return (
    <div className="px-3 py-3 shrink-0" style={{ borderTop: "1px solid var(--border)" }}>
      <button onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-1 mb-1"
        style={{ color: "var(--text2)" }}>
        <span className="uppercase tracking-wider" style={{ fontSize: 9, fontWeight: 500, opacity: 0.4, letterSpacing: "0.12em" }}>
          Next Steps ({open.length})
        </span>
        {collapsed ? <ChevronRight size={10} style={{ opacity: 0.4 }} /> : <ChevronDown size={10} style={{ opacity: 0.4 }} />}
      </button>
      {!collapsed && (
        <div className="space-y-0.5">
          {top.map(t => (
            <Link key={t.id} href="/lifemap" title={t.description}
              className="flex items-start gap-1.5 px-1 py-1 rounded transition-colors"
              style={{ color: "var(--text2)" }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#6366f115" }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent" }}>
              <span className="w-1.5 h-1.5 rounded-full mt-1 shrink-0"
                style={{ background: PRIORITY_COLOR[t.priority] || "var(--text2)" }} />
              <span className="text-[11px] leading-snug">{t.title}</span>
            </Link>
          ))}
          {open.length > 3 && (
            <Link href="/lifemap" className="block px-1 py-0.5 text-[10px]" style={{ color: "var(--accent2)" }}>
              +{open.length - 3} more →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
