"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Building2, Users, Calculator, MapPin, Phone, Calendar, TrendingUp,
  ExternalLink, Plus, ChevronRight, AlertTriangle, Loader2, RefreshCw,
  FileText, Target, Copy, Printer, X, CheckCircle2, Clock, ShieldAlert,
} from "lucide-react"

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`${res.status}: ${text || res.statusText}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface Lead {
  id: string | number
  company: string
  contact_person?: string
  phone?: string
  location?: string
  distance_km?: number
  potential_volume?: string | number
  priority?: "High" | "Medium" | "Low"
  status?: string
  next_followup?: string
  notes?: string
}

interface Tender {
  id: string | number
  buyer?: string
  title?: string
  volume?: number | string
  unit?: string
  category?: string
  due_date?: string
  status?: string
  eligibility_score?: number
  url?: string
  notes?: string
  location?: string
  tender_id?: string
}

interface Competitor {
  id: string | number
  name: string
  type?: string
  locations?: string
  threat_level?: "High" | "Medium" | "Low"
  strengths?: string
  recent_activity?: string
}

interface BidResult {
  gate_price?: number
  fois_freight?: number
  landed_cost: number
  suggested_bid: number
  margin_pct: number
  total_revenue: number
  total_margin?: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtDate(d?: string) {
  if (!d) return "—"
  return new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" })
}

function daysUntil(d?: string): number | null {
  if (!d) return null
  return Math.ceil((new Date(d).getTime() - Date.now()) / 86400000)
}

function priorityColor(p?: string) {
  if (p === "High") return "var(--red)"
  if (p === "Medium") return "var(--amber)"
  return "var(--text2)"
}

function statusColor(s?: string) {
  const l = (s || "").toLowerCase()
  if (l === "active") return "var(--green)"
  if (l === "expired") return "var(--red)"
  if (l === "evaluating") return "var(--amber)"
  return "var(--text2)"
}

function threatColor(t?: string) {
  if (t === "High") return "var(--red)"
  if (t === "Medium") return "var(--amber)"
  return "var(--green)"
}

// ---------------------------------------------------------------------------
// Input / Select reusable atoms
// ---------------------------------------------------------------------------
const inputStyle: React.CSSProperties = {
  background: "var(--bg3)",
  borderColor: "var(--border)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "6px 10px",
  fontSize: 13,
  width: "100%",
  outline: "none",
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ fontSize: 11, color: "var(--text2)", display: "block", marginBottom: 4 }}>{label}</label>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TABS
// ---------------------------------------------------------------------------
const TABS = ["Dashboard", "Coal Tenders", "Leads", "Bid Calculator", "Competitors"] as const
type Tab = typeof TABS[number]

// ---------------------------------------------------------------------------
// COMMISSIONING BANNER
// ---------------------------------------------------------------------------
function CommissioningBanner() {
  return (
    <div style={{
      background: "rgba(245,158,11,0.12)",
      border: "1px solid rgba(245,158,11,0.4)",
      borderRadius: 10,
      padding: "10px 14px",
      display: "flex",
      alignItems: "center",
      gap: 10,
    }}>
      <AlertTriangle size={16} style={{ color: "var(--amber)", flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: "var(--amber)", fontWeight: 500 }}>
        Washery commissioning: ~50% operational — building sales pipeline for full launch. Win tenders NOW before capacity is live.
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TAB 1: DASHBOARD
// ---------------------------------------------------------------------------
function DashboardTab({ setTab }: { setTab: (t: Tab) => void }) {
  const { data: leadsData } = useQuery({
    queryKey: ["leads"],
    queryFn: () => apiFetch<{ leads: Lead[] }>("/api/vwlr/leads").then(r => r.leads).catch(() => [] as Lead[]),
  })
  const { data: tendersData } = useQuery({
    queryKey: ["tenders"],
    queryFn: () => apiFetch<{ tenders: Tender[] }>("/api/vwlr/tenders").then(r => r.tenders).catch(() => [] as Tender[]),
  })
  const { data: followupsData, isLoading: fuLoading } = useQuery({
    queryKey: ["followups"],
    queryFn: () => apiFetch<{ leads: Lead[] }>("/api/vwlr/followups").then(r => r.leads).catch(() => [] as Lead[]),
  })

  const leads = leadsData || []
  const tenders = tendersData || []
  const followups = (followupsData || []).slice(0, 5)

  const nextFollowup = leads
    .filter(l => l.next_followup)
    .sort((a, b) => new Date(a.next_followup!).getTime() - new Date(b.next_followup!).getTime())[0]

  const statCards = [
    { label: "Active Leads", value: leads.length, icon: <Users size={18} style={{ color: "var(--cyan)" }} />, color: "var(--cyan)" },
    { label: "Tenders Tracked", value: tenders.length, icon: <FileText size={18} style={{ color: "var(--accent)" }} />, color: "var(--accent)" },
    { label: "Next Follow-up", value: nextFollowup ? fmtDate(nextFollowup.next_followup) : "None", icon: <Calendar size={18} style={{ color: "var(--green)" }} />, color: "var(--green)" },
  ]

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <CommissioningBanner />

      {/* Stat Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        {statCards.map(c => (
          <div key={c.label} style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>{c.icon}<span style={{ fontSize: 12, color: "var(--text2)" }}>{c.label}</span></div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "var(--text2)" }}>QUICK ACTIONS</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <a href="https://tender247.com" target="_blank" rel="noreferrer"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 500, textDecoration: "none" }}>
            <ExternalLink size={14} /> Open Tender247
          </a>
          <button onClick={() => setTab("Coal Tenders")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, background: "var(--bg3)", color: "var(--text)", fontSize: 13, fontWeight: 500, border: "1px solid var(--border)", cursor: "pointer" }}>
            <Plus size={14} /> Add Lead
          </button>
          <button onClick={() => setTab("Bid Calculator")}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 8, background: "var(--bg3)", color: "var(--text)", fontSize: 13, fontWeight: 500, border: "1px solid var(--border)", cursor: "pointer" }}>
            <Calculator size={14} /> Calculate Bid
          </button>
        </div>
      </div>

      {/* Follow-up Reminders */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, color: "var(--text2)" }}>FOLLOW-UP REMINDERS</div>
        {fuLoading && <div style={{ fontSize: 13, color: "var(--text2)", display: "flex", alignItems: "center", gap: 6 }}><Loader2 size={14} className="animate-spin" /> Loading…</div>}
        {!fuLoading && followups.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text2)" }}>No follow-ups due — all clear.</div>
        )}
        {followups.map(l => {
          const days = daysUntil(l.next_followup)
          const overdue = days !== null && days <= 0
          return (
            <div key={l.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{l.company}</div>
                <div style={{ fontSize: 11, color: "var(--text2)", marginTop: 2 }}>{l.contact_person} {l.phone ? `· ${l.phone}` : ""}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 20, background: priorityColor(l.priority) + "22", color: priorityColor(l.priority), fontWeight: 600 }}>{l.priority}</span>
                <span style={{ fontSize: 12, color: overdue ? "var(--red)" : "var(--amber)", fontWeight: 500 }}>
                  {overdue ? `${Math.abs(days!)}d overdue` : days === 0 ? "Today" : `in ${days}d`}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TAB 2: COAL TENDERS
// ---------------------------------------------------------------------------
const TENDER247_SHORTCUTS = [
  { label: "RCR Coal", url: "https://tender247.com/keyword/rcr+coal+handling" },
  { label: "Coal Loading/Unloading", url: "https://tender247.com/keyword/coal+loading+unloading" },
  { label: "Rake Handling ROM", url: "https://tender247.com/keyword/rake+handling+rom+coal" },
  { label: "Open Tender247", url: "https://tender247.com" },
]

const TENDER_CATEGORIES = ["RCR", "Loading-Unloading", "Rake Handling ROM", "Other"] as const

function CoalTendersTab() {
  const [showAddForm, setShowAddForm] = useState(false)
  const [form, setForm] = useState({ buyer: "", volume: "", category: "RCR", due_date: "", url: "", notes: "" })
  const [addStatus, setAddStatus] = useState<"idle" | "ok" | "err">("idle")
  const queryClient = useQueryClient()

  const { data: tenders = [], isLoading, error } = useQuery({
    queryKey: ["tenders"],
    queryFn: () => apiFetch<{ tenders: Tender[] }>("/api/vwlr/tenders").then(r => r.tenders).catch(() => [] as Tender[]),
  })

  const addMutation = useMutation({
    mutationFn: (body: typeof form) => apiFetch("/api/vwlr/tenders/add", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setAddStatus("ok")
      setShowAddForm(false)
      setForm({ buyer: "", volume: "", category: "RCR", due_date: "", url: "", notes: "" })
      queryClient.invalidateQueries({ queryKey: ["tenders"] })
      setTimeout(() => setAddStatus("idle"), 3000)
    },
    onError: () => setAddStatus("err"),
  })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Tender247 Quick Launch */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text2)", marginBottom: 12 }}>TENDER247 QUICK LAUNCH</div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
          {TENDER247_SHORTCUTS.map(s => (
            <a key={s.label} href={s.url} target="_blank" rel="noreferrer"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 13px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 500, textDecoration: "none" }}>
              🔍 {s.label}
            </a>
          ))}
        </div>
        <a href="https://tender247.com/login" target="_blank" rel="noreferrer"
          style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 13px", borderRadius: 8, background: "var(--bg3)", color: "var(--text)", fontSize: 13, border: "1px solid var(--border)", textDecoration: "none" }}>
          <ExternalLink size={13} /> Login to Tender247
        </a>
      </div>

      {/* Pipeline Table */}
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text2)" }}>TENDER PIPELINE</div>
          <button onClick={() => setShowAddForm(v => !v)}
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 500, border: "none", cursor: "pointer" }}>
            <Plus size={13} /> Add Tender to Pipeline
          </button>
        </div>

        {addStatus === "ok" && (
          <div style={{ background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.3)", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "var(--green)", marginBottom: 12 }}>
            Tender added successfully.
          </div>
        )}
        {addStatus === "err" && (
          <div style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "var(--red)", marginBottom: 12 }}>
            Failed to add tender (API may not be available).
          </div>
        )}

        {showAddForm && (
          <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 10, padding: 14, marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text2)", marginBottom: 12 }}>NEW TENDER</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <Field label="Buyer">
                <input style={inputStyle} value={form.buyer} onChange={e => setForm(f => ({ ...f, buyer: e.target.value }))} placeholder="e.g. SECL" />
              </Field>
              <Field label="Volume (MT)">
                <input style={inputStyle} value={form.volume} onChange={e => setForm(f => ({ ...f, volume: e.target.value }))} placeholder="e.g. 10000" />
              </Field>
              <Field label="Category">
                <select style={inputStyle} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                  {TENDER_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Due Date">
                <input style={inputStyle} type="date" value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
              </Field>
              <Field label="Tender URL">
                <input style={inputStyle} value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} placeholder="https://..." />
              </Field>
              <Field label="Notes">
                <input style={inputStyle} value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes" />
              </Field>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => addMutation.mutate(form)} disabled={addMutation.isPending}
                style={{ padding: "7px 16px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, border: "none", cursor: "pointer", opacity: addMutation.isPending ? 0.7 : 1 }}>
                {addMutation.isPending ? "Saving…" : "Save Tender"}
              </button>
              <button onClick={() => setShowAddForm(false)}
                style={{ padding: "7px 16px", borderRadius: 8, background: "var(--bg2)", color: "var(--text2)", fontSize: 13, border: "1px solid var(--border)", cursor: "pointer" }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {isLoading && <div style={{ padding: "20px 0", textAlign: "center", color: "var(--text2)", fontSize: 13, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><Loader2 size={14} className="animate-spin" /> Loading tenders…</div>}
        {error && <div style={{ fontSize: 12, color: "var(--red)", padding: 10 }}>Error loading tenders.</div>}

        {!isLoading && tenders.length === 0 && (
          <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text2)", fontSize: 13 }}>
            No tenders tracked yet — use Tender247 shortcuts above to find tenders, then add them manually.
          </div>
        )}

        {tenders.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Buyer", "Volume", "Category", "Due Date", "Status", "Eligibility", "Link"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text2)", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tenders.map(t => {
                  const days = daysUntil(t.due_date)
                  return (
                    <tr key={t.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 8px" }}><div style={{ fontWeight: 600 }}>{t.buyer || "—"}</div><div style={{ fontSize: 11, color: "var(--text2)" }}>{t.title || ""}</div></td>
                      <td style={{ padding: "8px 8px" }}>{t.volume ? `${Number(t.volume).toLocaleString("en-IN")} ${t.unit || "MT"}` : "—"}</td>
                      <td style={{ padding: "8px 8px" }}>{t.category || "—"}</td>
                      <td style={{ padding: "8px 8px", color: days !== null && days <= 3 ? "var(--red)" : "var(--text)" }}>
                        {fmtDate(t.due_date)}
                        {days !== null && <span style={{ fontSize: 11, color: days <= 0 ? "var(--red)" : "var(--text2)", display: "block" }}>{days <= 0 ? "Expired" : `${days}d left`}</span>}
                      </td>
                      <td style={{ padding: "8px 8px" }}>
                        <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 11, background: statusColor(t.status) + "22", color: statusColor(t.status), fontWeight: 600 }}>{t.status || "—"}</span>
                      </td>
                      <td style={{ padding: "8px 8px" }}>
                        {t.eligibility_score != null
                          ? <span style={{ color: (t.eligibility_score || 0) > 0.7 ? "var(--green)" : "var(--amber)", fontWeight: 600 }}>{((t.eligibility_score || 0) * 100).toFixed(0)}%</span>
                          : "—"}
                      </td>
                      <td style={{ padding: "8px 8px" }}>
                        {t.url
                          ? <a href={t.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}><ExternalLink size={12} /> View</a>
                          : <span style={{ color: "var(--text2)", fontSize: 12 }}>—</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TAB 3: LEADS
// ---------------------------------------------------------------------------
type LeadFilter = "All" | "High Priority" | "Follow-up Today"

function LogCallModal({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  const [outcome, setOutcome] = useState("")
  const [followUpDate, setFollowUpDate] = useState("")
  const [status, setStatus] = useState<"idle" | "ok" | "err">("idle")

  const mutation = useMutation({
    mutationFn: () => apiFetch("/api/vwlr/interactions", {
      method: "POST",
      body: JSON.stringify({ lead_id: lead.id, outcome, follow_up_date: followUpDate }),
    }),
    onSuccess: () => { setStatus("ok"); setTimeout(onClose, 1500) },
    onError: () => setStatus("err"),
  })

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: 20, width: 340, maxWidth: "90vw" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Log Call — {lead.company}</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text2)" }}><X size={16} /></button>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Field label="Outcome / Notes">
            <textarea style={{ ...inputStyle, height: 80, resize: "vertical" }} value={outcome} onChange={e => setOutcome(e.target.value)} placeholder="What happened on the call?" />
          </Field>
          <Field label="Next Follow-up Date">
            <input style={inputStyle} type="date" value={followUpDate} onChange={e => setFollowUpDate(e.target.value)} />
          </Field>
        </div>
        {status === "ok" && <div style={{ fontSize: 12, color: "var(--green)", marginTop: 10 }}>Call logged.</div>}
        {status === "err" && <div style={{ fontSize: 12, color: "var(--red)", marginTop: 10 }}>Failed to log. API may be unavailable.</div>}
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button onClick={() => mutation.mutate()} disabled={mutation.isPending}
            style={{ padding: "7px 16px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, border: "none", cursor: "pointer" }}>
            {mutation.isPending ? "Saving…" : "Save"}
          </button>
          <button onClick={onClose} style={{ padding: "7px 16px", borderRadius: 8, background: "var(--bg3)", color: "var(--text2)", fontSize: 13, border: "1px solid var(--border)", cursor: "pointer" }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

function AddLeadModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ company: "", contact_person: "", phone: "", location: "", distance_km: "", potential_volume: "", priority: "Medium", notes: "" })
  const [status, setStatus] = useState<"idle" | "ok" | "err">("idle")

  const mutation = useMutation({
    mutationFn: () => apiFetch("/api/vwlr/leads", { method: "POST", body: JSON.stringify({ ...form, distance_km: Number(form.distance_km) || 0 }) }),
    onSuccess: () => {
      setStatus("ok")
      queryClient.invalidateQueries({ queryKey: ["leads"] })
      setTimeout(onClose, 1500)
    },
    onError: () => setStatus("err"),
  })

  const f = (key: keyof typeof form, val: string) => setForm(p => ({ ...p, [key]: val }))

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: 20, width: 420, maxWidth: "90vw", maxHeight: "90vh", overflowY: "auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Add Lead</span>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text2)" }}><X size={16} /></button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
          <Field label="Company *"><input style={inputStyle} value={form.company} onChange={e => f("company", e.target.value)} placeholder="Company name" /></Field>
          <Field label="Contact Person"><input style={inputStyle} value={form.contact_person} onChange={e => f("contact_person", e.target.value)} placeholder="Name" /></Field>
          <Field label="Phone"><input style={inputStyle} value={form.phone} onChange={e => f("phone", e.target.value)} placeholder="+91 XXXXX XXXXX" /></Field>
          <Field label="Location"><input style={inputStyle} value={form.location} onChange={e => f("location", e.target.value)} placeholder="City / District" /></Field>
          <Field label="Distance (km)"><input style={inputStyle} value={form.distance_km} onChange={e => f("distance_km", e.target.value)} placeholder="0" type="number" /></Field>
          <Field label="Potential Volume"><input style={inputStyle} value={form.potential_volume} onChange={e => f("potential_volume", e.target.value)} placeholder="e.g. 5000 MT/mo" /></Field>
          <Field label="Priority">
            <select style={inputStyle} value={form.priority} onChange={e => f("priority", e.target.value)}>
              <option>High</option><option>Medium</option><option>Low</option>
            </select>
          </Field>
        </div>
        <Field label="Notes">
          <textarea style={{ ...inputStyle, height: 64, resize: "vertical" }} value={form.notes} onChange={e => f("notes", e.target.value)} placeholder="Any notes..." />
        </Field>
        {status === "ok" && <div style={{ fontSize: 12, color: "var(--green)", marginTop: 10 }}>Lead added.</div>}
        {status === "err" && <div style={{ fontSize: 12, color: "var(--red)", marginTop: 10 }}>Failed to add lead.</div>}
        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button onClick={() => mutation.mutate()} disabled={mutation.isPending}
            style={{ padding: "7px 16px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, border: "none", cursor: "pointer" }}>
            {mutation.isPending ? "Saving…" : "Add Lead"}
          </button>
          <button onClick={onClose} style={{ padding: "7px 16px", borderRadius: 8, background: "var(--bg3)", color: "var(--text2)", fontSize: 13, border: "1px solid var(--border)", cursor: "pointer" }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

function LeadCard({ l, onLogCall }: { l: Lead; onLogCall: (l: Lead) => void }) {
  const days = daysUntil(l.next_followup)
  const pColor = priorityColor(l.priority)

  return (
    <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{l.company}</div>
          <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 2 }}>{l.contact_person}</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: pColor + "22", color: pColor }}>{l.priority}</span>
          {l.status && <span style={{ fontSize: 11, color: "var(--text2)", padding: "2px 8px", borderRadius: 20, background: "var(--bg3)" }}>{l.status}</span>}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, fontSize: 12, color: "var(--text2)", marginBottom: 10 }}>
        {l.phone && <a href={`tel:${l.phone}`} style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--cyan)", textDecoration: "none" }}><Phone size={11} />{l.phone}</a>}
        {l.location && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><MapPin size={11} />{l.location}{l.distance_km ? ` (${l.distance_km} km)` : ""}</span>}
        {l.potential_volume && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><TrendingUp size={11} />{l.potential_volume}</span>}
      </div>
      {l.next_followup && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: 11, padding: "4px 10px", borderRadius: 6, background: "var(--bg3)", color: "var(--cyan)", display: "inline-flex", alignItems: "center", gap: 4 }}>
            <Calendar size={10} /> Follow-up: {fmtDate(l.next_followup)}
            {days !== null && <span style={{ color: days <= 0 ? "var(--red)" : "var(--text2)", marginLeft: 4 }}>({days <= 0 ? `${Math.abs(days)}d overdue` : `in ${days}d`})</span>}
          </div>
          <button onClick={() => onLogCall(l)}
            style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 7, background: "var(--bg3)", color: "var(--accent)", fontSize: 12, border: "1px solid var(--border)", cursor: "pointer" }}>
            <Phone size={11} /> Log Call
          </button>
        </div>
      )}
      {!l.next_followup && (
        <button onClick={() => onLogCall(l)}
          style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 7, background: "var(--bg3)", color: "var(--accent)", fontSize: 12, border: "1px solid var(--border)", cursor: "pointer" }}>
          <Phone size={11} /> Log Call
        </button>
      )}
    </div>
  )
}

function LeadsTab() {
  const [filter, setFilter] = useState<LeadFilter>("All")
  const [showAddModal, setShowAddModal] = useState(false)
  const [logCallLead, setLogCallLead] = useState<Lead | null>(null)

  const { data: leads = [], isLoading, error } = useQuery({
    queryKey: ["leads"],
    queryFn: () => apiFetch<{ leads: Lead[] }>("/api/vwlr/leads").then(r => r.leads).catch(() => [] as Lead[]),
  })

  const today = new Date().toISOString().slice(0, 10)

  const filtered = leads.filter(l => {
    if (filter === "High Priority") return l.priority === "High"
    if (filter === "Follow-up Today") return l.next_followup === today
    return true
  })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {showAddModal && <AddLeadModal onClose={() => setShowAddModal(false)} />}
      {logCallLead && <LogCallModal lead={logCallLead} onClose={() => setLogCallLead(null)} />}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 6 }}>
          {(["All", "High Priority", "Follow-up Today"] as LeadFilter[]).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{ padding: "5px 12px", borderRadius: 8, fontSize: 12, fontWeight: filter === f ? 600 : 400, background: filter === f ? "var(--bg3)" : "transparent", color: filter === f ? "var(--text)" : "var(--text2)", border: "1px solid var(--border)", cursor: "pointer" }}>
              {f}
            </button>
          ))}
        </div>
        <button onClick={() => setShowAddModal(true)}
          style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 500, border: "none", cursor: "pointer" }}>
          <Plus size={13} /> Add Lead
        </button>
      </div>

      {isLoading && <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text2)", fontSize: 13 }}>Loading leads…</div>}
      {error && <div style={{ fontSize: 12, color: "var(--red)" }}>Error loading leads.</div>}
      {!isLoading && filtered.length === 0 && <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text2)", fontSize: 13 }}>No leads found.</div>}
      {filtered.map(l => <LeadCard key={l.id} l={l} onLogCall={setLogCallLead} />)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TAB 4: BID CALCULATOR
// ---------------------------------------------------------------------------
const ROUTES = ["Raigarh", "Bilaspur", "Raipur", "Nagpur", "Korba", "Bokaro", "Jamshedpur"]

function BidCalcTab() {
  const [buyer, setBuyer] = useState("")
  const [vol, setVol] = useState("")
  const [route, setRoute] = useState(ROUTES[0])
  const [gate, setGate] = useState("")
  const [copied, setCopied] = useState(false)

  const { data: result, refetch, isFetching, error } = useQuery<BidResult>({
    queryKey: ["bid", buyer, vol, route, gate],
    queryFn: () => apiFetch<BidResult>(`/api/vwlr/bid?buyer=${encodeURIComponent(buyer)}&volume=${vol}&route=${encodeURIComponent(route)}&gate_price=${gate}`),
    enabled: false,
  })

  const halfVol = vol ? Math.floor(Number(vol) / 2).toLocaleString("en-IN") : "—"

  const handleCopy = useCallback(() => {
    if (!result) return
    const lines = [
      `Bid Summary — ${buyer || "N/A"} | Route: ${route}`,
      `Volume: ${vol} MT (50% commissioning: ${halfVol} MT)`,
      `Gate Price: ₹${Number(gate).toLocaleString("en-IN")}`,
      result.fois_freight != null ? `FOIS Freight: ₹${result.fois_freight.toLocaleString("en-IN")}` : null,
      `Landed Cost: ₹${result.landed_cost.toLocaleString("en-IN")}`,
      `Suggested Bid: ₹${result.suggested_bid.toLocaleString("en-IN")}`,
      `Margin: ${result.margin_pct.toFixed(1)}%`,
      `Total Revenue: ₹${(result.total_revenue / 1e5).toFixed(2)} L`,
      result.total_margin != null ? `Total Margin: ₹${(result.total_margin / 1e5).toFixed(2)} L` : null,
    ].filter(Boolean).join("\n")
    navigator.clipboard.writeText(lines).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
  }, [result, buyer, route, vol, gate, halfVol])

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 560 }}>
      {/* Commissioning Note */}
      <div style={{ background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.35)", borderRadius: 10, padding: "10px 14px", display: "flex", gap: 10, alignItems: "flex-start" }}>
        <AlertTriangle size={15} style={{ color: "var(--amber)", marginTop: 1, flexShrink: 0 }} />
        <span style={{ fontSize: 12, color: "var(--amber)" }}>
          <strong>Commissioning Adjustment:</strong> At ~50% capacity, halve the volume commitment in bids. Full volume: {vol ? Number(vol).toLocaleString("en-IN") : "—"} MT → Safe bid qty: <strong>{halfVol} MT</strong>
        </span>
      </div>

      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <Calculator size={16} style={{ color: "var(--accent)" }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Bid Optimiser</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
          <Field label="Buyer">
            <input style={inputStyle} value={buyer} onChange={e => setBuyer(e.target.value)} placeholder="e.g. VEDANTA" />
          </Field>
          <Field label="Volume (MT)">
            <input style={inputStyle} value={vol} onChange={e => setVol(e.target.value)} placeholder="e.g. 5000" type="number" />
          </Field>
          <Field label="Route">
            <select style={inputStyle} value={route} onChange={e => setRoute(e.target.value)}>
              {ROUTES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          <Field label="Gate Price (₹/MT)">
            <input style={inputStyle} value={gate} onChange={e => setGate(e.target.value)} placeholder="e.g. 4200" type="number" />
          </Field>
        </div>
        <button onClick={() => refetch()} disabled={isFetching}
          style={{ width: "100%", padding: "9px 0", borderRadius: 8, background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 500, border: "none", cursor: "pointer", opacity: isFetching ? 0.7 : 1 }}>
          {isFetching ? "Calculating…" : "Calculate Bid"}
        </button>
        {error && <div style={{ fontSize: 12, color: "var(--red)", marginTop: 8 }}>API error — check backend.</div>}
      </div>

      {result && (
        <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text2)" }}>BREAKDOWN</span>
            <button onClick={handleCopy}
              style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 7, background: "var(--bg3)", color: copied ? "var(--green)" : "var(--text2)", fontSize: 12, border: "1px solid var(--border)", cursor: "pointer" }}>
              {copied ? <><CheckCircle2 size={12} /> Copied</> : <><Copy size={12} /> Copy Summary</>}
            </button>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <tbody>
              {[
                ["Gate Price", result.gate_price != null ? `₹${result.gate_price.toLocaleString("en-IN")}` : `₹${Number(gate).toLocaleString("en-IN")}`],
                ["FOIS Freight", result.fois_freight != null ? `₹${result.fois_freight.toLocaleString("en-IN")}` : "—"],
                ["Landed Cost", `₹${result.landed_cost.toLocaleString("en-IN")}`, "var(--cyan)"],
                ["Suggested Bid", `₹${result.suggested_bid.toLocaleString("en-IN")}`, "var(--accent)"],
                ["Margin %", `${result.margin_pct.toFixed(1)}%`, result.margin_pct >= 10 ? "var(--green)" : "var(--amber)"],
                ["Total Revenue", `₹${(result.total_revenue / 1e5).toFixed(2)} L`],
                result.total_margin != null ? ["Total Margin", `₹${(result.total_margin / 1e5).toFixed(2)} L`, "var(--green)"] as [string, string, string?] : null,
              ].filter(Boolean).map(row => {
                const [k, v, color] = row as [string, string, string?]
                return (
                  <tr key={k} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "7px 0", color: "var(--text2)", fontSize: 12 }}>{k}</td>
                    <td style={{ padding: "7px 0", textAlign: "right", fontWeight: 600, color: color || "var(--text)" }}>{v}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TAB 5: COMPETITORS
// ---------------------------------------------------------------------------
function CompetitorsTab() {
  const { data: competitors = [], isLoading, error } = useQuery({
    queryKey: ["competitors"],
    queryFn: () => apiFetch<{ competitors: Competitor[] }>("/api/vwlr/competitors").then(r => r.competitors).catch(() => [] as Competitor[]),
  })

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 12, padding: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text2)", marginBottom: 14 }}>COMPETITOR LANDSCAPE</div>

        {isLoading && <div style={{ textAlign: "center", padding: "20px 0", color: "var(--text2)", fontSize: 13 }}>Loading…</div>}
        {error && <div style={{ fontSize: 12, color: "var(--red)" }}>Error loading competitors.</div>}

        {!isLoading && competitors.length === 0 && (
          <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text2)", fontSize: 13 }}>No competitor data yet.</div>
        )}

        {competitors.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Name", "Type", "Locations", "Threat", "Strengths", "Recent Activity"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "6px 8px", fontSize: 11, color: "var(--text2)", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {competitors.map(c => (
                  <tr key={c.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "9px 8px", fontWeight: 600 }}>{c.name}</td>
                    <td style={{ padding: "9px 8px", color: "var(--text2)" }}>{c.type || "—"}</td>
                    <td style={{ padding: "9px 8px", color: "var(--text2)" }}>{c.locations || "—"}</td>
                    <td style={{ padding: "9px 8px" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 700, background: threatColor(c.threat_level) + "22", color: threatColor(c.threat_level) }}>
                        {c.threat_level || "—"}
                      </span>
                    </td>
                    <td style={{ padding: "9px 8px", color: "var(--text2)", fontSize: 12 }}>{c.strengths || "—"}</td>
                    <td style={{ padding: "9px 8px", color: "var(--text2)", fontSize: 12 }}>{c.recent_activity || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ROOT PAGE
// ---------------------------------------------------------------------------
export default function VWLRPage() {
  const [tab, setTab] = useState<Tab>("Dashboard")

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, background: "rgba(99,102,241,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Building2 size={20} style={{ color: "var(--accent)" }} />
        </div>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>VWLR — Washery Sales</h1>
          <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 2 }}>Vedanta Washery Linked Revenue · Coal Handling Tenders</div>
        </div>
      </div>

      {/* Tab Bar */}
      <div style={{ display: "flex", gap: 2, marginBottom: 20, borderBottom: "1px solid var(--border)", paddingBottom: 0 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: tab === t ? 600 : 400,
              background: "transparent",
              color: tab === t ? "var(--accent)" : "var(--text2)",
              border: "none",
              borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
              cursor: "pointer",
              marginBottom: -1,
              transition: "color 0.15s",
            }}>
            {t}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "Dashboard" && <DashboardTab setTab={setTab} />}
      {tab === "Coal Tenders" && <CoalTendersTab />}
      {tab === "Leads" && <LeadsTab />}
      {tab === "Bid Calculator" && <BidCalcTab />}
      {tab === "Competitors" && <CompetitorsTab />}
    </div>
  )
}
