"use client"

import { useEffect, useMemo, useRef, useState, useCallback } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Network, Plus, RotateCcw, Trash2, X, Link2 } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

// ── types ────────────────────────────────────────────────────────────────
type Layer = { key: string; label: string; hint: string }
type MapNode = {
  id: string; layer: string; label: string; detail: string
  status: string; kind: string; icon: string; notes: string; sort: number
}
type MapEdge = { id: number; from_node: string; to_node: string; label: string }
type LifeMap = { layers: Layer[]; nodes: MapNode[]; edges: MapEdge[] }

const STATUS: Record<string, { color: string; label: string }> = {
  live:     { color: "var(--green)", label: "live"     },
  building: { color: "var(--amber)", label: "building" },
  planned:  { color: "var(--accent2)", label: "planned"  },
  parked:   { color: "var(--red)",   label: "parked"   },
}
const STATUSES = Object.keys(STATUS)

async function fetchMap(): Promise<LifeMap> {
  const r = await fetch(`${BASE}/api/lifemap`, { cache: "no-store" })
  if (!r.ok) throw new Error()
  return r.json()
}
async function call(path: string, method: string, body?: unknown) {
  const r = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`)
  return r.json()
}

// ── node card ────────────────────────────────────────────────────────────
function NodeCard({ node, dim, active, related, onClick, setRef }: {
  node: MapNode; dim: boolean; active: boolean; related: boolean
  onClick: () => void; setRef: (el: HTMLDivElement | null) => void
}) {
  const st = STATUS[node.status] || STATUS.planned
  return (
    <div ref={setRef} onClick={onClick}
      className="rounded-lg border p-2.5 cursor-pointer transition-all"
      style={{
        background: active ? "var(--bg3)" : "var(--bg2)",
        borderColor: active ? "var(--accent)" : related ? "var(--accent2)" : "var(--border)",
        opacity: dim ? 0.25 : 1,
      }}>
      <div className="flex items-center gap-1.5">
        <span style={{ fontSize: 13 }}>{node.icon || "•"}</span>
        <span className="text-xs font-semibold leading-tight flex-1">{node.label}</span>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: st.color }} title={st.label} />
      </div>
      {node.detail && (
        <div className="text-[10px] mt-1 leading-snug" style={{ color: "var(--text2)" }}>{node.detail}</div>
      )}
    </div>
  )
}

// ── detail / edit drawer ─────────────────────────────────────────────────
function NodeDrawer({ node, map, onClose }: { node: MapNode; map: LifeMap; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ ...node })
  const [linkTarget, setLinkTarget] = useState("")
  useEffect(() => { setForm({ ...node }) }, [node])

  const invalidate = () => qc.invalidateQueries({ queryKey: ["lifemap"] })
  const save = useMutation({
    mutationFn: () => call(`/api/lifemap/nodes/${node.id}`, "PUT", form),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: () => call(`/api/lifemap/nodes/${node.id}`, "DELETE"),
    onSuccess: () => { invalidate(); onClose() },
  })
  const addEdge = useMutation({
    mutationFn: (to: string) => call("/api/lifemap/edges", "POST", { from_node: node.id, to_node: to }),
    onSuccess: () => { invalidate(); setLinkTarget("") },
  })
  const delEdge = useMutation({
    mutationFn: (id: number) => call(`/api/lifemap/edges/${id}`, "DELETE"),
    onSuccess: invalidate,
  })

  const outgoing = map.edges.filter(e => e.from_node === node.id)
  const incoming = map.edges.filter(e => e.to_node === node.id)
  const byId = Object.fromEntries(map.nodes.map(n => [n.id, n]))
  const linkable = map.nodes.filter(n =>
    n.id !== node.id && !outgoing.some(e => e.to_node === n.id))

  const inp = "w-full px-2.5 py-1.5 rounded-lg text-sm outline-none border bg-transparent"
  const inpStyle = { borderColor: "var(--border)", color: "var(--text)", background: "var(--bg3)" }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(0,0,0,0.5)" }} onClick={onClose}>
      <div className="w-full max-w-md h-full overflow-y-auto" style={{ background: "var(--bg2)" }}
        onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b flex items-center justify-between sticky top-0 z-10"
          style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2">
            <span style={{ fontSize: 18 }}>{node.icon}</span>
            <div>
              <div className="font-bold text-sm">{node.label}</div>
              <div className="text-xs" style={{ color: "var(--text2)" }}>
                {map.layers.find(l => l.key === node.layer)?.label} · {node.kind || "node"}
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{ color: "var(--text2)" }}><X size={16} /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Edit form */}
          <div className="space-y-2">
            <input className={inp} style={inpStyle} value={form.label}
              onChange={e => setForm({ ...form, label: e.target.value })} placeholder="Label" />
            <input className={inp} style={inpStyle} value={form.detail}
              onChange={e => setForm({ ...form, detail: e.target.value })} placeholder="One-line detail" />
            <textarea className={inp} style={{ ...inpStyle, minHeight: 70 }} value={form.notes}
              onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Notes — refine freely" />
            <div className="flex gap-2">
              <select className={inp} style={inpStyle} value={form.status}
                onChange={e => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <select className={inp} style={inpStyle} value={form.layer}
                onChange={e => setForm({ ...form, layer: e.target.value })}>
                {map.layers.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select>
              <input className={inp} style={{ ...inpStyle, width: 60 }} value={form.icon}
                onChange={e => setForm({ ...form, icon: e.target.value })} placeholder="🔹" />
            </div>
            <div className="flex gap-2">
              <button onClick={() => save.mutate()}
                className="flex-1 py-1.5 rounded-lg text-sm font-medium"
                style={{ background: "var(--accent)", color: "#fff" }}>
                {save.isPending ? "Saving…" : "Save changes"}
              </button>
              <button onClick={() => { if (confirm(`Delete "${node.label}" and its connections?`)) remove.mutate() }}
                className="px-3 py-1.5 rounded-lg border" style={{ borderColor: "var(--red)", color: "var(--red)" }}>
                <Trash2 size={14} />
              </button>
            </div>
          </div>

          {/* Connections */}
          <div>
            <div className="font-semibold text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text2)" }}>
              Feeds into ({outgoing.length})
            </div>
            <div className="space-y-1.5">
              {outgoing.map(e => (
                <div key={e.id} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-sm"
                  style={{ background: "var(--bg3)" }}>
                  <span className="flex-1">{byId[e.to_node]?.icon} {byId[e.to_node]?.label || e.to_node}</span>
                  {e.label && <span className="text-[10px]" style={{ color: "var(--text2)" }}>{e.label}</span>}
                  <button onClick={() => delEdge.mutate(e.id)} style={{ color: "var(--text2)" }}><X size={12} /></button>
                </div>
              ))}
              {outgoing.length === 0 && <div className="text-xs" style={{ color: "var(--text2)" }}>Nothing yet</div>}
            </div>
            <div className="flex gap-2 mt-2">
              <select className={inp} style={inpStyle} value={linkTarget} onChange={e => setLinkTarget(e.target.value)}>
                <option value="">+ connect to…</option>
                {linkable.map(n => <option key={n.id} value={n.id}>{n.label}</option>)}
              </select>
              <button disabled={!linkTarget} onClick={() => addEdge.mutate(linkTarget)}
                className="px-3 rounded-lg border disabled:opacity-40"
                style={{ borderColor: "var(--border)", color: "var(--accent2)" }}>
                <Link2 size={14} />
              </button>
            </div>
          </div>

          <div>
            <div className="font-semibold text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text2)" }}>
              Fed by ({incoming.length})
            </div>
            <div className="space-y-1.5">
              {incoming.map(e => (
                <div key={e.id} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-sm"
                  style={{ background: "var(--bg3)" }}>
                  <span className="flex-1">{byId[e.from_node]?.icon} {byId[e.from_node]?.label || e.from_node}</span>
                  <button onClick={() => delEdge.mutate(e.id)} style={{ color: "var(--text2)" }}><X size={12} /></button>
                </div>
              ))}
              {incoming.length === 0 && <div className="text-xs" style={{ color: "var(--text2)" }}>Nothing yet</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── add-node modal ───────────────────────────────────────────────────────
function AddNodeModal({ layer, layers, onClose }: { layer: string; layers: Layer[]; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ label: "", detail: "", layer, status: "planned", icon: "", notes: "" })
  const add = useMutation({
    mutationFn: () => call("/api/lifemap/nodes", "POST", form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["lifemap"] }); onClose() },
  })
  const inp = "w-full px-2.5 py-1.5 rounded-lg text-sm outline-none border"
  const inpStyle = { borderColor: "var(--border)", color: "var(--text)", background: "var(--bg3)" }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.5)" }} onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl border p-5 space-y-2"
        style={{ background: "var(--bg2)", borderColor: "var(--border)" }} onClick={e => e.stopPropagation()}>
        <div className="font-bold text-sm mb-1">Add node</div>
        <input autoFocus className={inp} style={inpStyle} placeholder="Label (e.g. Screener API, Notion MCP…)"
          value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} />
        <input className={inp} style={inpStyle} placeholder="One-line detail"
          value={form.detail} onChange={e => setForm({ ...form, detail: e.target.value })} />
        <div className="flex gap-2">
          <select className={inp} style={inpStyle} value={form.layer}
            onChange={e => setForm({ ...form, layer: e.target.value })}>
            {layers.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
          </select>
          <select className={inp} style={inpStyle} value={form.status}
            onChange={e => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input className={inp} style={{ ...inpStyle, width: 56 }} placeholder="🔹"
            value={form.icon} onChange={e => setForm({ ...form, icon: e.target.value })} />
        </div>
        <button disabled={!form.label.trim()} onClick={() => add.mutate()}
          className="w-full py-2 rounded-lg text-sm font-medium disabled:opacity-40"
          style={{ background: "var(--accent)", color: "#fff" }}>
          {add.isPending ? "Adding…" : "Add to map"}
        </button>
      </div>
    </div>
  )
}

// ── page ─────────────────────────────────────────────────────────────────
export default function LifeMapPage() {
  const qc = useQueryClient()
  const { data, isLoading, isError } = useQuery({ queryKey: ["lifemap"], queryFn: fetchMap })
  const [selected, setSelected] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [adding, setAdding] = useState<string | null>(null)

  const containerRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef<Map<string, HTMLDivElement>>(new Map())
  const [lines, setLines] = useState<{ x1: number; y1: number; x2: number; y2: number; hot: boolean; key: string }[]>([])

  const reset = useMutation({
    mutationFn: () => call("/api/lifemap/reset", "POST", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lifemap"] }),
  })

  const relatedIds = useMemo(() => {
    if (!selected || !data) return new Set<string>()
    const s = new Set<string>()
    for (const e of data.edges) {
      if (e.from_node === selected) s.add(e.to_node)
      if (e.to_node === selected) s.add(e.from_node)
    }
    return s
  }, [selected, data])

  // measure node positions → SVG lines
  const measure = useCallback(() => {
    if (!data || !containerRef.current) return
    const box = containerRef.current.getBoundingClientRect()
    const pos = new Map<string, { x1: number; y: number; x2: number }>()
    for (const [id, el] of nodeRefs.current) {
      const r = el.getBoundingClientRect()
      pos.set(id, {
        x1: r.left - box.left + containerRef.current.scrollLeft,
        x2: r.right - box.left + containerRef.current.scrollLeft,
        y: r.top - box.top + containerRef.current.scrollTop + r.height / 2,
      })
    }
    const ls: typeof lines = []
    for (const e of data.edges) {
      const a = pos.get(e.from_node), b = pos.get(e.to_node)
      if (!a || !b) continue
      const [from, to] = a.x2 <= b.x1 ? [a, b] : [b, a]
      ls.push({
        x1: from.x2, y1: from.y, x2: to.x1, y2: to.y, key: `${e.id}`,
        hot: !!selected && (e.from_node === selected || e.to_node === selected),
      })
    }
    setLines(ls)
  }, [data, selected])

  useEffect(() => {
    measure()
    const t = setTimeout(measure, 150) // after fonts/layout settle
    window.addEventListener("resize", measure)
    return () => { clearTimeout(t); window.removeEventListener("resize", measure) }
  }, [measure])

  if (isError) return (
    <div className="text-center py-16 text-sm" style={{ color: "var(--red)" }}>
      Backend offline — run: <code>python mdo_server.py</code>
    </div>
  )
  if (isLoading || !data) return (
    <div className="text-center py-16 text-sm" style={{ color: "var(--text2)" }}>Loading map…</div>
  )

  const selectedNode = data.nodes.find(n => n.id === selected) || null
  const counts = data.nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.status] = (acc[n.status] || 0) + 1; return acc
  }, {})

  return (
    <div className="space-y-4">
      {selectedNode && <NodeDrawer node={selectedNode} map={data} onClose={() => setSelected(null)} />}
      {adding && <AddNodeModal layer={adding} layers={data.layers} onClose={() => setAdding(null)} />}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Network size={20} style={{ color: "var(--accent2)" }} />
          <h1 className="text-2xl font-bold">Life LLM Map</h1>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            {data.nodes.length} nodes · {data.edges.length} connections
          </span>
        </div>
        <div className="flex items-center gap-2">
          {STATUSES.map(s => (
            <button key={s} onClick={() => setStatusFilter(statusFilter === s ? null : s)}
              className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border transition-colors"
              style={{
                borderColor: statusFilter === s ? STATUS[s].color : "var(--border)",
                color: statusFilter === s ? STATUS[s].color : "var(--text2)",
                background: statusFilter === s ? STATUS[s].color + "15" : "transparent",
              }}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATUS[s].color }} />
              {s} {counts[s] || 0}
            </button>
          ))}
          <button onClick={() => { if (confirm("Reset the whole map back to the seed? Your edits will be lost.")) reset.mutate() }}
            title="Reset to seed" className="p-1.5 rounded-lg border"
            style={{ borderColor: "var(--border)", color: "var(--text2)" }}>
            <RotateCcw size={13} />
          </button>
        </div>
      </div>

      <div className="text-xs" style={{ color: "var(--text2)" }}>
        Click a node to inspect, edit, or rewire it. Nothing here is absolute — refine as the system grows.
      </div>

      {/* Map canvas */}
      <div ref={containerRef} className="relative overflow-x-auto rounded-xl border p-4"
        style={{ background: "var(--bg)", borderColor: "var(--border)" }}>
        <svg className="absolute inset-0 pointer-events-none" style={{ width: "100%", height: "100%", minWidth: 1400 }}>
          {lines.map(l => {
            const mx = (l.x1 + l.x2) / 2
            return (
              <path key={l.key}
                d={`M ${l.x1} ${l.y1} C ${mx} ${l.y1}, ${mx} ${l.y2}, ${l.x2} ${l.y2}`}
                fill="none"
                stroke={l.hot ? "var(--accent)" : "var(--border)"}
                strokeWidth={l.hot ? 1.8 : 1}
                opacity={selected ? (l.hot ? 0.95 : 0.12) : 0.45}
              />
            )
          })}
        </svg>

        <div className="flex gap-4 relative" style={{ minWidth: 1400 }}>
          {data.layers.map(layer => {
            const nodes = data.nodes.filter(n => n.layer === layer.key)
            return (
              <div key={layer.key} className="flex-1 min-w-44">
                <div className="mb-2 px-1">
                  <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--accent2)" }}>
                    {layer.label}
                  </div>
                  <div className="text-[10px]" style={{ color: "var(--text2)", opacity: 0.7 }}>{layer.hint}</div>
                </div>
                <div className="space-y-2">
                  {nodes.map(n => (
                    <NodeCard key={n.id} node={n}
                      dim={!!statusFilter && n.status !== statusFilter}
                      active={selected === n.id}
                      related={relatedIds.has(n.id)}
                      onClick={() => setSelected(selected === n.id ? null : n.id)}
                      setRef={el => {
                        if (el) nodeRefs.current.set(n.id, el)
                        else nodeRefs.current.delete(n.id)
                      }} />
                  ))}
                  <button onClick={() => setAdding(layer.key)}
                    className="w-full flex items-center justify-center gap-1 py-1.5 rounded-lg border border-dashed text-[11px] transition-colors"
                    style={{ borderColor: "var(--border)", color: "var(--text2)", opacity: 0.6 }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = "1" }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = "0.6" }}>
                    <Plus size={11} /> add
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
