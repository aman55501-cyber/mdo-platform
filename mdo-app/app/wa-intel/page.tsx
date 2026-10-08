"use client"

// Business Intel — Aman's review surface for the WhatsApp intelligence layer.
//
// Four jobs on one page: decide which chats are business, act on the signals the
// model pulled out of them, keep the register of facts current, and read the weekly
// pulse. The backend may be empty for days after launch, so every section has an
// honest empty state and never fabricates a number.

import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Radar, Users, MessageCircle, Briefcase, User, HelpCircle, Zap, Activity, Clock,
  Check, X, RotateCcw, Plus, Loader2, FileText, Hash, Calendar, IndianRupee,
  AlertTriangle, ListChecks, TrendingDown, Gauge, Ban, BookOpen,
} from "lucide-react"
import { api } from "@/lib/api"
import type {
  WaChat, WaSignal, WaSignalStatus, WaRegisterItem, WaRegisterInput, WaStats,
  WaPulseEfficiencyRow, WaPulseNextStep,
} from "@/lib/types"

// ── Constants ─────────────────────────────────────────────────────────

const ENTITIES = [
  "VWLR", "Hotel ANS International", "ANS Inn Pvt Ltd", "Dadu Developers", "Dadu Builders",
  "Raigarh Land Venture", "Rukmani Infrastructure", "Aditi Investments", "Eureka",
  "MD's Office", "other",
] as const

type Tab = "classify" | "signals" | "register" | "pulse"
const TABS: { id: Tab; label: string }[] = [
  { id: "classify", label: "To classify" },
  { id: "signals",  label: "Signals" },
  { id: "register", label: "Register" },
  { id: "pulse",    label: "Pulse" },
]

const KIND_COLOR: Record<string, string> = {
  payment: "var(--green)", receivable: "var(--green)", payable: "var(--amber)", due: "var(--amber)",
  deadline: "var(--red)", risk: "var(--red)", complaint: "var(--red)", escalation: "var(--red)",
  order: "var(--cyan)", enquiry: "var(--cyan)", lead: "var(--cyan)", sales: "var(--cyan)",
  decision: "var(--accent2)", task: "var(--accent2)", followup: "var(--accent2)", approval: "var(--accent2)",
}
const kindColor = (k: string) => KIND_COLOR[(k || "").toLowerCase()] || "var(--text2)"

// ── Helpers ───────────────────────────────────────────────────────────

function ago(iso?: string | null) {
  if (!iso) return "never"
  const norm = iso.replace(" ", "T")
  const t = new Date(norm.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(norm) ? norm : norm + "Z").getTime()
  if (Number.isNaN(t)) return iso
  const m = Math.round((Date.now() - t) / 60000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  if (m < 48 * 60) return `${Math.round(m / 60)}h ago`
  return `${Math.round(m / 1440)}d ago`
}

function fmtAmount(amount: number | null | undefined, currency?: string | null) {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) return null
  const cur = (currency || "INR").toUpperCase()
  const n = Number(amount)
  if (cur === "INR") return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
  return `${cur} ${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
}

function fmtNum(v: number) {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

function pct(c: number | null | undefined) {
  if (c === null || c === undefined) return null
  const n = Number(c)
  if (Number.isNaN(n)) return null
  return `${Math.round(n <= 1 ? n * 100 : n)}%`
}

function dueTone(due: string | null | undefined) {
  if (!due) return "var(--text2)"
  const d = new Date(due).getTime()
  if (Number.isNaN(d)) return "var(--text2)"
  const days = (d - Date.now()) / 86400000
  if (days < 0) return "var(--red)"
  if (days < 3) return "var(--amber)"
  return "var(--text2)"
}

// Pulse sections arrive as free-form lists. Render whatever shape they take without
// inventing structure: strings as text, objects as "key: value" pairs.
function Loose({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span style={{ color: "var(--text2)" }}>—</span>
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return <>{String(v)}</>
  if (Array.isArray(v)) return <>{v.map((x, i) => <span key={i}>{i > 0 && ", "}<Loose v={x} /></span>)}</>
  if (typeof v === "object") {
    const o = v as Record<string, unknown>
    const title = o.title ?? o.summary ?? o.text ?? o.item ?? o.name
    const rest = Object.entries(o).filter(([k]) => !["title", "summary", "text", "item", "name"].includes(k))
    return (
      <span>
        {title !== undefined && <span className="font-medium">{String(title)}</span>}
        {rest.length > 0 && (
          <span className="text-xs" style={{ color: "var(--text2)" }}>
            {title !== undefined && " · "}
            {rest.map(([k, val], i) => (
              <span key={k}>{i > 0 && " · "}{k}: <Loose v={val} /></span>
            ))}
          </span>
        )}
      </span>
    )
  }
  return <>{String(v)}</>
}

// ── Primitives ────────────────────────────────────────────────────────

function Panel({ title, icon: Icon, children, aside }: {
  title: string; icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>
  children: React.ReactNode; aside?: React.ReactNode
}) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: "var(--border)", background: "var(--bg2)" }}>
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold"><Icon size={15} style={{ color: "var(--accent2)" }} />{title}</div>
        {aside}
      </div>
      {children}
    </div>
  )
}

function Empty({ icon: Icon, title, hint }: {
  icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>; title: string; hint?: string
}) {
  return (
    <div className="text-center py-12 px-4 rounded-xl" style={{ border: "1px dashed var(--border)", color: "var(--text2)" }}>
      <Icon size={26} style={{ opacity: 0.5, display: "inline-block" }} />
      <div className="mt-2 text-sm" style={{ color: "var(--text)" }}>{title}</div>
      {hint && <div className="mt-1 text-xs">{hint}</div>}
    </div>
  )
}

function Chip({ active, onClick, children, tone }: {
  active: boolean; onClick: () => void; children: React.ReactNode; tone?: string
}) {
  return (
    <button onClick={onClick}
      className="px-2.5 py-1 text-xs font-medium rounded-full transition-colors"
      style={{
        background: active ? (tone ? tone + "22" : "rgba(109,106,248,0.16)") : "var(--bg2)",
        color: active ? (tone || "var(--accent2)") : "var(--text2)",
        border: `1px solid ${active ? (tone ? tone + "66" : "rgba(143,140,255,0.4)") : "var(--border)"}`,
      }}>
      {children}
    </button>
  )
}

function Badge({ children, color = "var(--text2)" }: { children: React.ReactNode; color?: string }) {
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold whitespace-nowrap"
      style={{ color, background: color.startsWith("var(") ? "rgba(143,140,255,0.08)" : color + "18", border: `1px solid ${color.startsWith("var(") ? "var(--border)" : color + "44"}` }}>
      {children}
    </span>
  )
}

const KIND_BG: Record<string, string> = {
  "var(--green)": "rgba(52,211,153,0.12)", "var(--amber)": "rgba(251,191,36,0.12)", "var(--red)": "rgba(248,113,113,0.12)",
  "var(--cyan)": "rgba(34,211,238,0.12)", "var(--accent2)": "rgba(143,140,255,0.14)", "var(--text2)": "rgba(139,147,171,0.12)",
}
function KindBadge({ kind }: { kind: string }) {
  const c = kindColor(kind)
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide whitespace-nowrap"
      style={{ color: c, background: KIND_BG[c] || KIND_BG["var(--text2)"] }}>
      {kind || "signal"}
    </span>
  )
}

const inputStyle: React.CSSProperties = {
  background: "var(--bg3)", border: "1px solid var(--border)", color: "var(--text)",
  borderRadius: 8, padding: "6px 10px", fontSize: 13, width: "100%", minWidth: 0,
}
const btn = (bg: string, color = "#fff"): React.CSSProperties => ({
  background: bg, color, border: "1px solid transparent", borderRadius: 8,
  padding: "6px 12px", fontSize: 12, fontWeight: 600, display: "inline-flex",
  alignItems: "center", gap: 6, cursor: "pointer", whiteSpace: "nowrap",
})
const ghostBtn: React.CSSProperties = {
  ...btn("transparent", "var(--text2)"), border: "1px solid var(--border)",
}

// ── Stat strip ────────────────────────────────────────────────────────

function Stat({ label, value, icon: Icon, tone, sub }: {
  label: string; value: React.ReactNode; icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>
  tone?: string; sub?: string
}) {
  return (
    <div className="glass rounded-xl px-3 py-2.5 min-w-0">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider" style={{ color: "var(--text2)" }}>
        <Icon size={11} style={{ color: tone || "var(--text2)" }} /> {label}
      </div>
      <div className="text-lg font-bold leading-tight mt-0.5 truncate" style={{ color: tone || "var(--text)" }}>{value}</div>
      {sub && <div className="text-[11px] truncate" style={{ color: "var(--text2)" }}>{sub}</div>}
    </div>
  )
}

function StatStrip({ stats, loading }: { stats: WaStats | undefined; loading: boolean }) {
  const chats = stats?.chats
  const openSignals = Object.values(stats?.signals_open_by_kind || {}).reduce((a, b) => a + Number(b || 0), 0)
  const topKinds = Object.entries(stats?.signals_open_by_kind || {}).sort((a, b) => b[1] - a[1]).slice(0, 3)
  const v = (n: number | undefined) => (loading && n === undefined ? "…" : (n ?? 0).toLocaleString("en-IN"))
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
      <Stat label="Business chats" value={v(chats?.business)} icon={Briefcase} tone="var(--green)" />
      <Stat label="Personal" value={v(chats?.personal)} icon={User} />
      <Stat label="Unclear" value={v(chats?.unclear)} icon={HelpCircle} tone={chats?.unclear ? "var(--amber)" : undefined}
        sub={chats?.unclear ? "waiting on you" : "nothing to sort"} />
      <Stat label="Open signals" value={loading && !stats ? "…" : openSignals.toLocaleString("en-IN")} icon={Zap}
        tone={openSignals ? "var(--cyan)" : undefined}
        sub={topKinds.length ? topKinds.map(([k, n]) => `${k} ${n}`).join(" · ") : "none open"} />
      <Stat label="Msgs 7d" value={v(stats?.msgs_7d)} icon={Activity} />
      <Stat label="Last pulse" value={loading && !stats ? "…" : ago(stats?.last_pulse_at)} icon={Clock}
        sub={stats?.last_pulse_at ? undefined : "Sunday 07:00 IST"} />
    </div>
  )
}

// ── To classify ───────────────────────────────────────────────────────

function ChatCard({ chat, onClassify, busy }: {
  chat: WaChat; onClassify: (c: WaChat, cls: "business" | "personal", entity: string) => void; busy: boolean
}) {
  const guess = ENTITIES.includes((chat.entity || "") as (typeof ENTITIES)[number]) ? (chat.entity as string) : "other"
  const [entity, setEntity] = useState<string>(guess)
  const conf = pct(chat.confidence)
  const guessLabel = chat.classification && chat.classification !== "unclear" ? chat.classification : null

  return (
    <div className="rounded-xl border p-3.5 card-hover" style={{ background: "var(--bg2)", borderColor: "var(--border)", opacity: busy ? 0.6 : 1 }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-sm leading-snug truncate">{chat.name || chat.jid}</div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
            <Badge color="var(--accent2)">{chat.account || "account ?"}</Badge>
            <Badge>{chat.kind === "group" ? <><Users size={10} className="inline mr-1" />group{chat.participants ? ` · ${chat.participants}` : ""}</> : <><MessageCircle size={10} className="inline mr-1" />dm</>}</Badge>
            <Badge><Hash size={10} className="inline mr-1" />{(chat.msg_count ?? 0).toLocaleString("en-IN")} msgs</Badge>
            {chat.last_seen && <span className="text-[11px]" style={{ color: "var(--text2)" }}>last {ago(chat.last_seen)}</span>}
          </div>
        </div>
      </div>

      <div className="mt-2.5 text-xs rounded-lg px-2.5 py-2" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
        <span className="font-semibold" style={{ color: "var(--text)" }}>Model guess:</span>{" "}
        {chat.entity || guessLabel ? (
          <>
            {chat.entity && <span style={{ color: "var(--accent2)" }}>{chat.entity}</span>}
            {chat.entity && guessLabel && " · "}
            {guessLabel && <span className="capitalize">{guessLabel}</span>}
            {conf && <span> · {conf}</span>}
          </>
        ) : <span>none</span>}
        {chat.reason && <div className="mt-1 leading-relaxed">{chat.reason}</div>}
      </div>

      <div className="mt-3 flex flex-col sm:flex-row gap-2">
        <select value={entity} onChange={e => setEntity(e.target.value)} disabled={busy}
          style={{ ...inputStyle, flex: 1 }} aria-label="Entity">
          {ENTITIES.map(en => <option key={en} value={en}>{en}</option>)}
        </select>
        <div className="flex gap-2">
          <button disabled={busy} onClick={() => onClassify(chat, "business", entity)} style={{ ...btn("rgba(52,211,153,0.16)", "var(--green)"), flex: 1, justifyContent: "center" }}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Briefcase size={13} />} Business
          </button>
          <button disabled={busy} onClick={() => onClassify(chat, "personal", "")} style={{ ...ghostBtn, flex: 1, justifyContent: "center" }}>
            <User size={13} /> Personal
          </button>
        </div>
      </div>
    </div>
  )
}

function ClassifyTab() {
  const qc = useQueryClient()
  const [note, setNote] = useState("")
  const { data: chats = [], isLoading, isError } = useQuery({
    queryKey: ["wa-chats", "unclear"],
    queryFn: () => api.wa.chats("unclear"),
    refetchInterval: 60_000,
  })

  const classify = useMutation({
    mutationFn: (v: { chat: WaChat; classification: "business" | "personal"; entity: string }) =>
      api.wa.classify({ jid: v.chat.jid, classification: v.classification, entity: v.entity }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ["wa-chats", "unclear"] })
      const prevChats = qc.getQueryData<WaChat[]>(["wa-chats", "unclear"])
      const prevStats = qc.getQueryData<WaStats>(["wa-stats"])
      qc.setQueryData<WaChat[]>(["wa-chats", "unclear"], (old = []) => old.filter(c => c.jid !== v.chat.jid))
      if (prevStats) {
        qc.setQueryData<WaStats>(["wa-stats"], {
          ...prevStats,
          chats: {
            ...prevStats.chats,
            unclear: Math.max(0, (prevStats.chats?.unclear ?? 0) - 1),
            [v.classification]: (prevStats.chats?.[v.classification] ?? 0) + 1,
          },
        })
      }
      setNote("")
      return { prevChats, prevStats }
    },
    onError: (e, v, ctx) => {
      if (ctx?.prevChats) qc.setQueryData(["wa-chats", "unclear"], ctx.prevChats)
      if (ctx?.prevStats) qc.setQueryData(["wa-stats"], ctx.prevStats)
      setNote(`Could not save "${v.chat.name || v.chat.jid}": ${(e as Error).message}`)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["wa-chats"] })
      qc.invalidateQueries({ queryKey: ["wa-stats"] })
    },
  })

  const busyJid = classify.isPending ? classify.variables?.chat.jid : null

  return (
    <div className="space-y-3">
      <div className="text-xs" style={{ color: "var(--text2)" }}>
        Chats the model could not place. Pick the entity and tap Business, or mark Personal. Decisions are recorded as yours.
      </div>
      {note && <div className="text-xs rounded-lg px-3 py-2" style={{ border: "1px solid var(--red)", color: "var(--red)" }}>{note}</div>}
      {isError && <Empty icon={AlertTriangle} title="Backend unreachable" hint="The WhatsApp intel API did not answer. Nothing here is stale by choice — it is missing." />}
      {isLoading && !isError && <div className="text-sm" style={{ color: "var(--text2)" }}>Loading…</div>}
      {!isLoading && !isError && chats.length === 0 && (
        <Empty icon={Check} title="Nothing to classify" hint="Every chat the model has seen is placed. New ones land here as they appear." />
      )}
      <div className="grid md:grid-cols-2 gap-3">
        {chats.map(c => (
          <ChatCard key={c.jid} chat={c} busy={busyJid === c.jid}
            onClassify={(chat, classification, entity) => classify.mutate({ chat, classification, entity })} />
        ))}
      </div>
    </div>
  )
}

// ── Signals ───────────────────────────────────────────────────────────

function SignalRow({ s, onStatus, busy }: { s: WaSignal; onStatus: (s: WaSignal, st: WaSignalStatus) => void; busy: boolean }) {
  const amt = fmtAmount(s.amount, s.currency)
  const conf = pct(s.confidence)
  const evidence = Array.isArray(s.evidence_ids) ? s.evidence_ids.length : 0
  return (
    <div className="px-3.5 py-3 border-t" style={{ borderColor: "var(--border)", opacity: busy ? 0.6 : 1, borderLeft: `3px solid ${kindColor(s.kind)}` }}>
      <div className="flex flex-wrap items-center gap-1.5">
        <KindBadge kind={s.kind} />
        {s.entity && <span className="text-xs font-medium" style={{ color: "var(--accent2)" }}>{s.entity}</span>}
        {s.counterparty && <span className="text-xs" style={{ color: "var(--text)" }}>· {s.counterparty}</span>}
        {amt && <span className="text-xs font-semibold font-mono" style={{ color: "var(--green)" }}>{amt}</span>}
        {s.due_date && (
          <span className="text-xs inline-flex items-center gap-1" style={{ color: dueTone(s.due_date) }}>
            <Calendar size={11} /> due {s.due_date}
          </span>
        )}
      </div>
      <div className="mt-1.5 text-sm leading-relaxed">{s.summary || <span style={{ color: "var(--text2)" }}>(no summary)</span>}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]" style={{ color: "var(--text2)" }}>
        {s.chat_name && <span>in {s.chat_name}</span>}
        <span><FileText size={10} className="inline mr-1" />{evidence} evidence</span>
        {conf && <span>{conf} conf.</span>}
        {s.owner && <span>owner {s.owner}</span>}
        <span>{ago(s.created_at)}</span>
        {s.status !== "open" && <Badge>{s.status}</Badge>}
      </div>
      <div className="mt-2 flex gap-2">
        {s.status === "open" ? (
          <>
            <button disabled={busy} onClick={() => onStatus(s, "done")} style={btn("rgba(52,211,153,0.16)", "var(--green)")}>
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Done
            </button>
            <button disabled={busy} onClick={() => onStatus(s, "dismissed")} style={ghostBtn}>
              <X size={12} /> Dismiss
            </button>
          </>
        ) : (
          <button disabled={busy} onClick={() => onStatus(s, "open")} style={ghostBtn}>
            <RotateCcw size={12} /> Reopen
          </button>
        )}
      </div>
    </div>
  )
}

function SignalsTab({ stats }: { stats: WaStats | undefined }) {
  const qc = useQueryClient()
  const [status, setStatus] = useState<WaSignalStatus>("open")
  const [kind, setKind] = useState<string>("all")
  const [entity, setEntity] = useState<string>("all")
  const [note, setNote] = useState("")

  const key = ["wa-signals", status]
  const { data: signals = [], isLoading, isError } = useQuery({
    queryKey: key,
    queryFn: () => api.wa.signals({ status, limit: 200 }),
    refetchInterval: 60_000,
  })

  // Chips come from what is actually present (plus the open-kind counts from stats),
  // so a filter never points at an empty set the data does not contain.
  const kinds = useMemo(() => {
    const set = new Set<string>(Object.keys(stats?.signals_open_by_kind || {}))
    signals.forEach(s => s.kind && set.add(s.kind))
    return Array.from(set).sort()
  }, [signals, stats])
  const entities = useMemo(() => {
    const set = new Set<string>()
    signals.forEach(s => s.entity && set.add(s.entity))
    return Array.from(set).sort()
  }, [signals])

  const visible = signals.filter(s => (kind === "all" || s.kind === kind) && (entity === "all" || s.entity === entity))

  const setSt = useMutation({
    mutationFn: (v: { s: WaSignal; to: WaSignalStatus }) => api.wa.setSignalStatus(v.s.id, v.to),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: key })
      const prev = qc.getQueryData<WaSignal[]>(key)
      const prevStats = qc.getQueryData<WaStats>(["wa-stats"])
      qc.setQueryData<WaSignal[]>(key, (old = []) => old.filter(x => x.id !== v.s.id))
      if (prevStats && v.s.status === "open" && v.to !== "open") {
        const k = v.s.kind
        const by = { ...(prevStats.signals_open_by_kind || {}) }
        if (k in by) by[k] = Math.max(0, by[k] - 1)
        qc.setQueryData<WaStats>(["wa-stats"], { ...prevStats, signals_open_by_kind: by })
      }
      setNote("")
      return { prev, prevStats }
    },
    onError: (e, v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev)
      if (ctx?.prevStats) qc.setQueryData(["wa-stats"], ctx.prevStats)
      setNote(`Could not update signal #${v.s.id}: ${(e as Error).message}`)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["wa-signals"] })
      qc.invalidateQueries({ queryKey: ["wa-stats"] })
    },
  })
  const busyId = setSt.isPending ? setSt.variables?.s.id : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
          {(["open", "done", "dismissed"] as WaSignalStatus[]).map(s => (
            <button key={s} onClick={() => setStatus(s)}
              className="px-3 py-1.5 text-xs font-medium capitalize transition-colors"
              style={{ background: status === s ? "var(--bg3)" : "var(--bg2)", color: status === s ? "var(--text)" : "var(--text2)" }}>
              {s}
            </button>
          ))}
        </div>
        <span className="text-xs" style={{ color: "var(--text2)" }}>{visible.length} of {signals.length}</span>
      </div>

      {kinds.length > 0 && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] uppercase tracking-wider mr-1" style={{ color: "var(--text2)" }}>Kind</span>
          <Chip active={kind === "all"} onClick={() => setKind("all")}>all</Chip>
          {kinds.map(k => {
            const n = status === "open" ? stats?.signals_open_by_kind?.[k] : undefined
            return <Chip key={k} active={kind === k} onClick={() => setKind(k)} tone={kindColor(k)}>{k}{n !== undefined ? ` ${n}` : ""}</Chip>
          })}
        </div>
      )}
      {entities.length > 0 && (
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-[10px] uppercase tracking-wider mr-1" style={{ color: "var(--text2)" }}>Entity</span>
          <Chip active={entity === "all"} onClick={() => setEntity("all")}>all</Chip>
          {entities.map(e => <Chip key={e} active={entity === e} onClick={() => setEntity(e)}>{e}</Chip>)}
        </div>
      )}

      {note && <div className="text-xs rounded-lg px-3 py-2" style={{ border: "1px solid var(--red)", color: "var(--red)" }}>{note}</div>}
      {isError && <Empty icon={AlertTriangle} title="Backend unreachable" hint="Signals could not be loaded." />}
      {isLoading && !isError && <div className="text-sm" style={{ color: "var(--text2)" }}>Loading…</div>}
      {!isLoading && !isError && visible.length === 0 && (
        <Empty icon={Zap} title={signals.length === 0 ? `No ${status} signals` : "No signals match these filters"}
          hint={signals.length === 0 && status === "open" ? "The extractor posts here when a business chat carries a payment, order, deadline or decision." : undefined} />
      )}
      {visible.length > 0 && (
        <div className="rounded-xl border overflow-hidden" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div style={{ marginTop: -1 }}>
            {visible.map(s => <SignalRow key={s.id} s={s} busy={busyId === s.id} onStatus={(sig, to) => setSt.mutate({ s: sig, to })} />)}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Register ──────────────────────────────────────────────────────────

const EMPTY_FORM: WaRegisterInput = { category: "", entity: ENTITIES[0], item: "", value: "", unit: "", as_of: "", source: "", notes: "" }

function RegisterTab() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<WaRegisterInput>(EMPTY_FORM)
  const [note, setNote] = useState("")
  const { data: items = [], isLoading, isError } = useQuery({
    queryKey: ["wa-register"],
    queryFn: () => api.wa.register(),
    refetchInterval: 120_000,
  })

  const groups = useMemo(() => {
    const by = new Map<string, WaRegisterItem[]>()
    items.forEach(it => {
      const c = it.category || "uncategorised"
      by.set(c, [...(by.get(c) || []), it])
    })
    return Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [items])
  const categories = groups.map(([c]) => c)

  const add = useMutation({
    mutationFn: (v: WaRegisterInput) => api.wa.addRegister({
      ...v,
      value: v.value === "" || v.value === null ? null : (Number.isNaN(Number(v.value)) ? v.value : Number(v.value)),
    }),
    onSuccess: () => {
      setForm(EMPTY_FORM); setShowForm(false); setNote("")
      qc.invalidateQueries({ queryKey: ["wa-register"] })
    },
    onError: (e) => setNote(`Could not add: ${(e as Error).message}`),
  })

  const set = (k: keyof WaRegisterInput) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))
  const canSubmit = form.category.trim() && form.item.trim() && !add.isPending

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs" style={{ color: "var(--text2)" }}>
          Facts the business runs on — rates, balances, headcounts, dues — each with a date and a source.
        </div>
        <button onClick={() => setShowForm(v => !v)} style={showForm ? ghostBtn : btn("var(--accent)")}>
          {showForm ? <X size={13} /> : <Plus size={13} />} {showForm ? "Cancel" : "Add item"}
        </button>
      </div>

      {showForm && (
        <form className="rounded-xl border p-3.5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2"
          style={{ background: "var(--bg2)", borderColor: "var(--glass-brd)" }}
          onSubmit={e => { e.preventDefault(); if (canSubmit) add.mutate(form) }}>
          <label className="text-xs" style={{ color: "var(--text2)" }}>Category *
            <input list="wa-register-cats" value={form.category} onChange={set("category")} placeholder="e.g. receivables" style={inputStyle} required />
            <datalist id="wa-register-cats">{categories.map(c => <option key={c} value={c} />)}</datalist>
          </label>
          <label className="text-xs" style={{ color: "var(--text2)" }}>Entity
            <select value={form.entity} onChange={set("entity")} style={inputStyle}>
              {ENTITIES.map(en => <option key={en} value={en}>{en}</option>)}
            </select>
          </label>
          <label className="text-xs sm:col-span-2" style={{ color: "var(--text2)" }}>Item *
            <input value={form.item} onChange={set("item")} placeholder="What is being recorded" style={inputStyle} required />
          </label>
          <label className="text-xs" style={{ color: "var(--text2)" }}>Value
            <input value={form.value ?? ""} onChange={set("value")} placeholder="number or text" style={inputStyle} />
          </label>
          <label className="text-xs" style={{ color: "var(--text2)" }}>Unit
            <input value={form.unit} onChange={set("unit")} placeholder="INR, MT, %, rooms…" style={inputStyle} />
          </label>
          <label className="text-xs" style={{ color: "var(--text2)" }}>As of
            <input type="date" value={form.as_of} onChange={set("as_of")} style={inputStyle} />
          </label>
          <label className="text-xs" style={{ color: "var(--text2)" }}>Source
            <input value={form.source} onChange={set("source")} placeholder="chat name, invoice, person" style={inputStyle} />
          </label>
          <label className="text-xs sm:col-span-2 lg:col-span-3" style={{ color: "var(--text2)" }}>Notes
            <input value={form.notes} onChange={set("notes")} style={inputStyle} />
          </label>
          <div className="flex items-end">
            <button type="submit" disabled={!canSubmit} style={{ ...btn("var(--accent)"), width: "100%", justifyContent: "center", opacity: canSubmit ? 1 : 0.5 }}>
              {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Save
            </button>
          </div>
        </form>
      )}

      {note && <div className="text-xs rounded-lg px-3 py-2" style={{ border: "1px solid var(--red)", color: "var(--red)" }}>{note}</div>}
      {isError && <Empty icon={AlertTriangle} title="Backend unreachable" hint="The register could not be loaded." />}
      {isLoading && !isError && <div className="text-sm" style={{ color: "var(--text2)" }}>Loading…</div>}
      {!isLoading && !isError && items.length === 0 && (
        <Empty icon={BookOpen} title="Register is empty" hint="Bots propose entries from chats; you can also add one above." />
      )}

      {groups.map(([cat, rows]) => {
        const nums = rows.map(r => Number(r.value)).filter((n, i) => rows[i].value !== null && rows[i].value !== "" && !Number.isNaN(n))
        const total = nums.reduce((a, b) => a + b, 0)
        const units = new Set(rows.filter(r => r.value !== null && r.value !== "" && !Number.isNaN(Number(r.value))).map(r => (r.unit || "").trim()))
        const unit = units.size === 1 ? Array.from(units)[0] : ""
        return (
          <div key={cat} className="rounded-xl border overflow-hidden" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
            <div className="px-3.5 py-2 flex items-center justify-between gap-2 text-xs font-bold uppercase tracking-wide border-b"
              style={{ borderColor: "var(--border)", background: "rgba(143,140,255,0.06)" }}>
              <span>{cat} <span style={{ color: "var(--text2)", fontWeight: 500 }}>· {rows.length}</span></span>
              {nums.length > 0 && (
                <span className="font-mono normal-case tracking-normal" style={{ color: "var(--accent2)" }}>
                  total {unit === "INR" ? `₹${fmtNum(total)}` : `${fmtNum(total)}${unit ? " " + unit : ""}`}
                  {nums.length < rows.length && <span style={{ color: "var(--text2)" }}> ({nums.length}/{rows.length} valued)</span>}
                </span>
              )}
            </div>
            {/* Desktop: table. Mobile: stacked rows. Never a sideways scroll. */}
            <table className="hidden md:table w-full text-sm">
              <thead>
                <tr className="text-left text-[11px]" style={{ color: "var(--text2)" }}>
                  <th className="px-3.5 py-1.5 font-medium">Item</th><th className="pr-3 font-medium">Entity</th>
                  <th className="pr-3 font-medium text-right">Value</th><th className="pr-3 font-medium">As of</th>
                  <th className="pr-3 font-medium">Source</th><th className="pr-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-3.5 py-2">
                      <div>{r.item}</div>
                      {r.notes && <div className="text-xs" style={{ color: "var(--text2)" }}>{r.notes}</div>}
                    </td>
                    <td className="pr-3 text-xs" style={{ color: "var(--accent2)" }}>{r.entity || "—"}</td>
                    <td className="pr-3 text-right font-mono text-xs whitespace-nowrap">
                      {r.value === null || r.value === "" ? "—" : (Number.isNaN(Number(r.value)) ? String(r.value) : fmtNum(Number(r.value)))}
                      {r.unit && <span style={{ color: "var(--text2)" }}> {r.unit}</span>}
                    </td>
                    <td className="pr-3 text-xs whitespace-nowrap">{r.as_of || "—"}</td>
                    <td className="pr-3 text-xs" style={{ color: "var(--text2)" }}>{r.source || "—"}</td>
                    <td className="pr-3 text-xs">{r.status ? <Badge>{r.status}</Badge> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="md:hidden">
              {rows.map(r => (
                <div key={r.id} className="px-3.5 py-2.5 border-t text-sm" style={{ borderColor: "var(--border)" }}>
                  <div className="flex justify-between gap-2">
                    <span className="min-w-0">{r.item}</span>
                    <span className="font-mono text-xs whitespace-nowrap">
                      {r.value === null || r.value === "" ? "—" : (Number.isNaN(Number(r.value)) ? String(r.value) : fmtNum(Number(r.value)))}
                      {r.unit && <span style={{ color: "var(--text2)" }}> {r.unit}</span>}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px]" style={{ color: "var(--text2)" }}>
                    {r.entity && <span style={{ color: "var(--accent2)" }}>{r.entity}</span>}
                    {r.as_of && <span>as of {r.as_of}</span>}
                    {r.source && <span>src {r.source}</span>}
                    {r.status && <span>[{r.status}]</span>}
                  </div>
                  {r.notes && <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>{r.notes}</div>}
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Pulse ─────────────────────────────────────────────────────────────

function PulseTab() {
  const { data: pulse, isLoading, isError } = useQuery({
    queryKey: ["wa-pulse"],
    queryFn: () => api.wa.pulseLatest(),
    refetchInterval: 300_000,
  })

  if (isError) return <Empty icon={AlertTriangle} title="Backend unreachable" hint="The latest pulse could not be loaded." />
  if (isLoading) return <div className="text-sm" style={{ color: "var(--text2)" }}>Loading…</div>
  if (!pulse) return <Empty icon={Radar} title="No pulse yet" hint="First run Sunday 07:00 IST or on demand." />

  const r = pulse.report || {}
  const salesGap = Array.isArray(r.sales_gap) ? r.sales_gap : []
  const efficiency: WaPulseEfficiencyRow[] = Array.isArray(r.efficiency) ? r.efficiency : []
  const bottlenecks = Array.isArray(r.bottlenecks) ? r.bottlenecks : []
  const regChanges = Array.isArray(r.register_changes) ? r.register_changes : []
  const nextSteps: WaPulseNextStep[] = Array.isArray(r.next_steps) ? r.next_steps : []
  const none = <div className="text-xs" style={{ color: "var(--text2)" }}>Nothing reported.</div>

  return (
    <div className="space-y-3">
      <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--glass-brd)" }}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold flex items-center gap-2"><Radar size={15} style={{ color: "var(--accent2)" }} /> Pulse #{pulse.id}</div>
          <div className="text-xs" style={{ color: "var(--text2)" }}>{pulse.period_start} → {pulse.period_end}</div>
        </div>
        <p className="mt-2 text-sm leading-relaxed whitespace-pre-wrap">{pulse.summary || <span style={{ color: "var(--text2)" }}>No summary.</span>}</p>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <Panel title="Sales gap" icon={TrendingDown}>
          {salesGap.length ? <ul className="space-y-1.5 text-sm">{salesGap.map((x, i) => <li key={i} className="flex gap-2"><span style={{ color: "var(--amber)" }}>•</span><span><Loose v={x} /></span></li>)}</ul> : none}
        </Panel>
        <Panel title="Bottlenecks" icon={Ban}>
          {bottlenecks.length ? <ul className="space-y-1.5 text-sm">{bottlenecks.map((x, i) => <li key={i} className="flex gap-2"><span style={{ color: "var(--red)" }}>•</span><span><Loose v={x} /></span></li>)}</ul> : none}
        </Panel>
      </div>

      <Panel title="Reply efficiency" icon={Gauge}>
        {efficiency.length ? (
          <div className="space-y-1">
            <div className="hidden sm:grid grid-cols-[1fr_1fr_auto_auto] gap-3 text-[11px] px-1" style={{ color: "var(--text2)" }}>
              <span>Chat</span><span>Sender</span><span className="text-right">Median reply</span><span className="text-right">Unanswered 24h</span>
            </div>
            {efficiency.map((e, i) => (
              <div key={i} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto_auto] gap-x-3 gap-y-0.5 text-sm px-1 py-1.5 border-t" style={{ borderColor: "var(--border)" }}>
                <span className="truncate">{e.chat || "—"}</span>
                <span className="truncate text-xs sm:text-sm" style={{ color: "var(--text2)" }}>{e.sender || "—"}</span>
                <span className="font-mono text-xs sm:text-right"><span className="sm:hidden" style={{ color: "var(--text2)" }}>median reply </span>{e.median_reply_min === null || e.median_reply_min === undefined ? "—" : `${fmtNum(Number(e.median_reply_min))} min`}</span>
                <span className="font-mono text-xs sm:text-right" style={{ color: Number(e.unanswered_24h) > 0 ? "var(--amber)" : "inherit" }}>
                  <span className="sm:hidden" style={{ color: "var(--text2)" }}>unanswered 24h </span>{e.unanswered_24h ?? "—"}
                </span>
              </div>
            ))}
          </div>
        ) : none}
      </Panel>

      <Panel title="Register changes" icon={IndianRupee}>
        {regChanges.length ? <ul className="space-y-1.5 text-sm">{regChanges.map((x, i) => <li key={i} className="flex gap-2"><span style={{ color: "var(--cyan)" }}>•</span><span><Loose v={x} /></span></li>)}</ul> : none}
      </Panel>

      <Panel title="Next steps" icon={ListChecks}>
        {nextSteps.length ? (
          <ol className="space-y-2 text-sm">
            {nextSteps.map((n, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="font-mono text-xs mt-0.5" style={{ color: "var(--accent2)" }}>{i + 1}.</span>
                <div>
                  <div>{n.step}</div>
                  <div className="text-[11px] flex flex-wrap gap-x-3" style={{ color: "var(--text2)" }}>
                    {n.owner && <span>owner {n.owner}</span>}
                    {n.eta && <span>ETA {n.eta}</span>}
                    {Array.isArray(n.cites) && n.cites.length > 0 && <span>cites {n.cites.map(c => `#${c}`).join(", ")}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        ) : none}
      </Panel>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────

export default function WaIntelPage() {
  const [tab, setTab] = useState<Tab>("classify")
  const stats = useQuery({ queryKey: ["wa-stats"], queryFn: () => api.wa.stats(), refetchInterval: 60_000 })
  const s = stats.data
  const openSignals = Object.values(s?.signals_open_by_kind || {}).reduce((a, b) => a + Number(b || 0), 0)
  const counts: Partial<Record<Tab, number>> = { classify: s?.chats?.unclear ?? 0, signals: openSignals }

  return (
    <div className="max-w-6xl mx-auto space-y-4 fade-up">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Radar size={20} style={{ color: "var(--accent2)" }} /> Business Intel</h1>
          <div className="text-xs" style={{ color: "var(--text2)" }}>
            What WhatsApp is telling the businesses. You decide; the model only proposes.
          </div>
        </div>
        {stats.isError && (
          <div className="text-xs flex items-center gap-1.5" style={{ color: "var(--red)" }}>
            <AlertTriangle size={13} /> WA intel API unreachable
          </div>
        )}
      </div>

      <StatStrip stats={s} loading={stats.isLoading} />

      <div className="flex flex-wrap gap-1">
        {TABS.map(t => {
          const n = counts[t.id]
          const active = tab === t.id
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="px-3 py-1.5 text-xs font-medium rounded-lg flex items-center gap-1.5"
              style={{ background: active ? "var(--bg3)" : "var(--bg2)", color: active ? "var(--text)" : "var(--text2)", border: `1px solid ${active ? "var(--border)" : "transparent"}` }}>
              {t.label}
              {n ? (
                <span className="text-[10px] px-1.5 rounded-full font-bold"
                  style={{ background: t.id === "classify" ? "rgba(251,191,36,0.16)" : "rgba(34,211,238,0.14)", color: t.id === "classify" ? "var(--amber)" : "var(--cyan)" }}>
                  {n}
                </span>
              ) : null}
            </button>
          )
        })}
      </div>

      {tab === "classify" && <ClassifyTab />}
      {tab === "signals"  && <SignalsTab stats={s} />}
      {tab === "register" && <RegisterTab />}
      {tab === "pulse"    && <PulseTab />}
    </div>
  )
}
