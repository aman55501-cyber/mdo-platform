"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckSquare, Plus, Calendar, User, Building2, AlertTriangle, Check, X } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function fetchTasks(status?: string, category?: string) {
  const q = new URLSearchParams()
  if (status) q.set("status", status)
  if (category) q.set("category", category)
  const r = await fetch(`${BASE}/api/ops/tasks?${q}`, { cache: "no-store" })
  if (!r.ok) throw new Error("API error")
  return r.json()
}
async function addTask(task: object) {
  const r = await fetch(`${BASE}/api/ops/tasks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(task) })
  return r.json()
}
async function updateTask(id: number, patch: object) {
  const r = await fetch(`${BASE}/api/ops/tasks/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) })
  return r.json()
}

const PRIORITY_COLOR: Record<string, string> = {
  critical: "var(--red)", high: "var(--amber)", medium: "var(--cyan)", low: "var(--text2)"
}
const CATEGORY_COLOR: Record<string, string> = {
  sales: "#6366f1", compliance: "#f59e0b", operations: "#22c55e", trading: "#06b6d4", general: "#94a3b8"
}

function daysUntil(d?: string) {
  if (!d) return null
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000)
  if (diff < 0) return { label: `${Math.abs(diff)}d overdue`, color: "var(--red)" }
  if (diff === 0) return { label: "Due today", color: "var(--red)" }
  if (diff <= 3) return { label: `${diff}d left`, color: "var(--amber)" }
  return { label: `${diff}d`, color: "var(--text2)" }
}

function TaskRow({ task, onComplete, onDelete }: { task: any; onComplete: () => void; onDelete: () => void }) {
  const due = daysUntil(task.due_date)
  const done = task.status === "done" || task.status === "completed"

  return (
    <div className={`flex items-start gap-3 px-4 py-3 border-b transition-opacity ${done ? "opacity-50" : ""}`}
      style={{ borderColor: "var(--border)" }}>
      <button onClick={onComplete} className="mt-0.5 shrink-0 w-5 h-5 rounded border flex items-center justify-center"
        style={{ borderColor: done ? "var(--green)" : "var(--border)", background: done ? "rgba(34,197,94,0.15)" : "transparent" }}>
        {done && <Check size={12} style={{ color: "var(--green)" }} />}
      </button>

      <div className="flex-1 min-w-0">
        <div className={`text-sm font-medium ${done ? "line-through" : ""}`}>{task.title}</div>
        {task.description && <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>{task.description}</div>}
        <div className="flex flex-wrap gap-2 mt-1.5">
          <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
            style={{ color: PRIORITY_COLOR[task.priority], background: PRIORITY_COLOR[task.priority] + "18" }}>
            {task.priority}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full"
            style={{ color: CATEGORY_COLOR[task.category] || "#94a3b8", background: (CATEGORY_COLOR[task.category] || "#94a3b8") + "18" }}>
            {task.category}
          </span>
          {task.entity && (
            <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text2)" }}>
              <Building2 size={9} />{task.entity}
            </span>
          )}
          {task.assigned_to && (
            <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text2)" }}>
              <User size={9} />{task.assigned_to}
            </span>
          )}
          {due && (
            <span className="flex items-center gap-1 text-xs" style={{ color: due.color }}>
              <Calendar size={9} />{due.label}
            </span>
          )}
        </div>
      </div>

      <button onClick={onDelete} className="shrink-0 p-1 rounded opacity-0 hover:opacity-100 transition-opacity"
        style={{ color: "var(--text2)" }}>
        <X size={13} />
      </button>
    </div>
  )
}

function AddTaskModal({ onClose, onAdd }: { onClose: () => void; onAdd: (t: object) => void }) {
  const [form, setForm] = useState({
    title: "", description: "", entity: "", assigned_to: "Aman",
    priority: "medium", category: "general", due_date: ""
  })
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.6)" }}>
      <div className="w-full max-w-md rounded-2xl border p-6 space-y-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between">
          <div className="font-bold">Add Task</div>
          <button onClick={onClose} style={{ color: "var(--text2)" }}><X size={18} /></button>
        </div>
        {[
          { key: "title",       label: "Title *",       type: "text"   },
          { key: "description", label: "Description",   type: "text"   },
          { key: "entity",      label: "Entity/Company",type: "text"   },
          { key: "assigned_to", label: "Assigned To",   type: "text"   },
          { key: "due_date",    label: "Due Date",      type: "date"   },
        ].map(({ key, label, type }) => (
          <div key={key}>
            <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>{label}</label>
            <input type={type} value={(form as any)[key]}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
              style={{ background: "var(--bg3)", borderColor: "var(--border)", color: "var(--text)" }} />
          </div>
        ))}
        <div className="grid grid-cols-2 gap-3">
          {[
            { key: "priority", label: "Priority", opts: ["critical","high","medium","low"] },
            { key: "category", label: "Category", opts: ["sales","compliance","operations","trading","general"] },
          ].map(({ key, label, opts }) => (
            <div key={key}>
              <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>{label}</label>
              <select value={(form as any)[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                style={{ background: "var(--bg3)", borderColor: "var(--border)", color: "var(--text)" }}>
                {opts.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
        </div>
        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 py-2 rounded-lg text-sm border"
            style={{ borderColor: "var(--border)", color: "var(--text2)" }}>Cancel</button>
          <button onClick={() => { if (form.title) { onAdd(form); onClose() } }}
            className="flex-1 py-2 rounded-lg text-sm font-medium"
            style={{ background: "var(--accent)", color: "#fff" }}>Add Task</button>
        </div>
      </div>
    </div>
  )
}

const TABS = ["all","sales","compliance","operations","trading"] as const

export default function OpsPage() {
  const [tab, setTab]       = useState<string>("all")
  const [showDone, setShowDone] = useState(false)
  const [adding, setAdding] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ops_tasks", tab, showDone],
    queryFn: () => fetchTasks(showDone ? undefined : "open", tab === "all" ? undefined : tab),
    refetchInterval: 30_000,
  })
  const tasks: any[] = data?.tasks ?? []

  const mutComplete = useMutation({
    mutationFn: ({ id, done }: { id: number; done: boolean }) =>
      updateTask(id, { status: done ? "open" : "done" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ops_tasks"] }),
  })
  const mutDelete = useMutation({
    mutationFn: (id: number) => updateTask(id, { status: "deleted" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ops_tasks"] }),
  })
  const mutAdd = useMutation({
    mutationFn: addTask,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ops_tasks"] }),
  })

  const critical = tasks.filter(t => t.priority === "critical" && t.status !== "done")
  const rest      = tasks.filter(t => t.priority !== "critical" || t.status === "done")

  return (
    <div className="space-y-5 max-w-4xl">
      {adding && <AddTaskModal onClose={() => setAdding(false)} onAdd={(t) => mutAdd.mutate(t)} />}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <CheckSquare size={20} style={{ color: "var(--accent2)" }} />
          <h1 className="text-2xl font-bold">Operations</h1>
          {critical.length > 0 && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-bold"
              style={{ background: "rgba(239,68,68,0.15)", color: "var(--red)" }}>
              <AlertTriangle size={10} />{critical.length} critical
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowDone(v => !v)}
            className="text-xs px-3 py-1.5 rounded-lg border"
            style={{ borderColor: "var(--border)", background: showDone ? "var(--bg3)" : "var(--bg2)", color: "var(--text2)" }}>
            {showDone ? "Hide done" : "Show done"}
          </button>
          <button onClick={() => setAdding(true)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium"
            style={{ background: "var(--accent)", color: "#fff" }}>
            <Plus size={13} /> Add Task
          </button>
        </div>
      </div>

      {/* Category tabs */}
      <div className="flex flex-wrap gap-1">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg capitalize"
            style={{ background: tab === t ? "var(--bg3)" : "var(--bg2)", color: tab === t ? "var(--text)" : "var(--text2)", border: `1px solid ${tab === t ? "var(--border)" : "transparent"}` }}>
            {t}
          </button>
        ))}
      </div>

      {isError && (
        <div className="text-sm text-center py-8" style={{ color: "var(--red)" }}>
          Backend offline — run: <code>python mdo_server.py</code>
        </div>
      )}

      <div className="rounded-xl border overflow-hidden" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        {isLoading && <div className="px-4 py-6 text-sm text-center" style={{ color: "var(--text2)" }}>Loading…</div>}

        {critical.length > 0 && (
          <div>
            <div className="px-4 py-2 text-xs font-bold uppercase tracking-wide border-b"
              style={{ background: "rgba(239,68,68,0.08)", borderColor: "var(--border)", color: "var(--red)" }}>
              Critical
            </div>
            {critical.map(t => (
              <TaskRow key={t.id} task={t}
                onComplete={() => mutComplete.mutate({ id: t.id, done: t.status === "done" })}
                onDelete={() => mutDelete.mutate(t.id)} />
            ))}
          </div>
        )}

        {rest.map(t => (
          <TaskRow key={t.id} task={t}
            onComplete={() => mutComplete.mutate({ id: t.id, done: t.status === "done" })}
            onDelete={() => mutDelete.mutate(t.id)} />
        ))}

        {!isLoading && tasks.length === 0 && (
          <div className="px-4 py-10 text-center text-sm" style={{ color: "var(--text2)" }}>
            No tasks — add one above
          </div>
        )}
      </div>
    </div>
  )
}
