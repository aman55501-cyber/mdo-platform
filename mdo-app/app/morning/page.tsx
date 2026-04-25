"use client"

import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Sun, Plus, Trash2, CheckCircle, XCircle, Youtube, Edit3,
  TrendingUp, TrendingDown, Minus, Clock, Zap, AlertTriangle,
  ChevronRight, RefreshCw, Send
} from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...opts })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function useISTTime() {
  const [time, setTime] = useState("")
  useEffect(() => {
    const tick = () => {
      const ist = new Date(Date.now() + 5.5 * 3600 * 1000)
      setTime(ist.toISOString().substring(11, 19))
    }
    tick(); const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  return time
}

function marketStatus(istTime: string) {
  if (!istTime) return { label: "—", color: "var(--text2)" }
  const [h, m] = istTime.split(":").map(Number)
  const mins = h * 60 + m
  if (mins < 9 * 60 + 15) return { label: "Pre-Market", color: "var(--amber)" }
  if (mins <= 15 * 60 + 30) return { label: "LIVE", color: "var(--green)" }
  return { label: "Closed", color: "var(--red)" }
}

function rr(entry: number, sl: number, tgt: number, dir: string) {
  const risk = dir === "BUY" ? entry - sl : sl - entry
  const reward = dir === "BUY" ? tgt - entry : entry - tgt
  if (risk <= 0) return null
  return (reward / risk).toFixed(1)
}

function dirColor(d: string) {
  if (d === "BUY") return "var(--green)"
  if (d === "SELL") return "var(--red)"
  return "var(--amber)"
}

const EMPTY_FORM = {
  ticker: "", exchange: "NSE", instrument: "EQ",
  direction: "BUY", entry_price: "", stop_loss: "",
  target_price: "", quantity: "", timeframe: "Intraday",
  notes: "", source: "manual",
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RRBar({ entry, sl, tgt, dir }: { entry: number; sl: number; tgt: number; dir: string }) {
  const rrVal = rr(entry, sl, tgt, dir)
  if (!rrVal) return null
  const ratio = parseFloat(rrVal)
  const riskW = Math.min(100 / (1 + ratio), 80)
  const rewardW = 100 - riskW
  return (
    <div>
      <div className="flex" style={{ height: 6, borderRadius: 3, overflow: "hidden", gap: 2 }}>
        <div style={{ width: `${riskW}%`, background: "var(--red)", opacity: 0.7, borderRadius: 3 }} />
        <div style={{ width: `${rewardW}%`, background: "var(--green)", opacity: 0.7, borderRadius: 3 }} />
      </div>
      <div className="flex justify-between mt-1" style={{ fontSize: 10, color: "var(--text2)" }}>
        <span style={{ color: "var(--red)" }}>Risk ₹{Math.abs((dir === "BUY" ? entry - sl : sl - entry) * 1).toFixed(0)}/unit</span>
        <span style={{ color: "var(--green)" }}>Reward ₹{Math.abs((dir === "BUY" ? tgt - entry : entry - tgt) * 1).toFixed(0)}/unit</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--accent2)", fontWeight: 600, marginTop: 2 }}>
        For every ₹1 you risk → earn ₹{rrVal}
      </div>
    </div>
  )
}

function CallCard({ call, onApprove, onReject, onDelete }: {
  call: any
  onApprove: () => void
  onReject: () => void
  onDelete: () => void
}) {
  const entry = Number(call.entry_price)
  const sl    = Number(call.stop_loss)
  const tgt   = Number(call.target_price)
  const qty   = Number(call.quantity) || 1

  const approved = call.status === "approved"
  const rejected = call.status === "rejected"

  return (
    <div
      className="rounded-xl border p-4"
      style={{
        background: "var(--bg2)",
        borderColor: approved ? "rgba(34,197,94,0.4)" : rejected ? "rgba(239,68,68,0.25)" : "var(--border)",
        opacity: rejected ? 0.5 : 1,
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-bold text-base">{call.ticker}</span>
          <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            {call.instrument}
          </span>
          <span
            className="text-xs font-bold px-2 py-0.5 rounded-full"
            style={{ background: dirColor(call.direction) + "22", color: dirColor(call.direction) }}
          >
            {call.direction}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {call.source === "youtube" && (
            <Youtube size={12} style={{ color: "#ef4444" }} />
          )}
          <span className="text-xs" style={{ color: "var(--text2)" }}>{call.timeframe}</span>
          <button onClick={onDelete} style={{ color: "var(--text2)", marginLeft: 4 }}>
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Price levels */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { label: "Entry", val: entry, color: "var(--text)" },
          { label: "Stop Loss", val: sl, color: "var(--red)" },
          { label: "Target", val: tgt, color: "var(--green)" },
        ].map(({ label, val, color }) => (
          <div key={label} className="rounded-lg p-2 text-center" style={{ background: "var(--bg3)" }}>
            <div style={{ fontSize: 10, color: "var(--text2)" }}>{label}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color, fontFamily: "monospace" }}>
              ₹{val.toLocaleString("en-IN")}
            </div>
          </div>
        ))}
      </div>

      {/* R:R Bar */}
      {entry > 0 && sl > 0 && tgt > 0 && (
        <div className="mb-3">
          <RRBar entry={entry} sl={sl} tgt={tgt} dir={call.direction} />
        </div>
      )}

      {/* P&L estimate */}
      {qty > 0 && entry > 0 && sl > 0 && tgt > 0 && (
        <div className="flex gap-2 mb-3">
          <div className="flex-1 rounded-lg p-2 text-center" style={{ background: "rgba(239,68,68,0.1)" }}>
            <div style={{ fontSize: 10, color: "var(--text2)" }}>Max Loss ({qty} qty)</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--red)" }}>
              -₹{(Math.abs((call.direction === "BUY" ? entry - sl : sl - entry) * qty)).toLocaleString("en-IN")}
            </div>
          </div>
          <div className="flex-1 rounded-lg p-2 text-center" style={{ background: "rgba(34,197,94,0.1)" }}>
            <div style={{ fontSize: 10, color: "var(--text2)" }}>Max Profit ({qty} qty)</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--green)" }}>
              +₹{(Math.abs((call.direction === "BUY" ? tgt - entry : entry - tgt) * qty)).toLocaleString("en-IN")}
            </div>
          </div>
        </div>
      )}

      {/* Notes */}
      {call.notes && (
        <div className="mb-3 text-xs rounded p-2" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          {call.notes}
        </div>
      )}

      {/* Source tag */}
      {call.source === "youtube" && call.raw_text && (
        <div className="mb-3 text-xs rounded p-2 border" style={{ background: "rgba(239,68,68,0.06)", borderColor: "rgba(239,68,68,0.2)", color: "var(--text2)" }}>
          <span style={{ color: "#ef4444", fontWeight: 600 }}>Singhvi said: </span>"{call.raw_text.slice(0, 120)}{call.raw_text.length > 120 ? "…" : ""}"
        </div>
      )}

      {/* Actions */}
      {!rejected && (
        <div className="flex gap-2">
          {!approved ? (
            <>
              <button
                onClick={onApprove}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold transition-all"
                style={{ background: "rgba(34,197,94,0.15)", color: "var(--green)", border: "1px solid rgba(34,197,94,0.3)" }}
              >
                <CheckCircle size={14} /> Approve
              </button>
              <button
                onClick={onReject}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold"
                style={{ background: "rgba(239,68,68,0.1)", color: "var(--red)", border: "1px solid rgba(239,68,68,0.25)" }}
              >
                <XCircle size={14} /> Skip
              </button>
            </>
          ) : (
            <div
              className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-semibold"
              style={{ background: "rgba(34,197,94,0.1)", color: "var(--green)", border: "1px solid rgba(34,197,94,0.3)" }}
            >
              <CheckCircle size={14} /> Approved for Execution
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ManualEntryForm({ onSubmit, onCancel }: { onSubmit: (data: any) => void; onCancel: () => void }) {
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  const entry = Number(form.entry_price)
  const sl    = Number(form.stop_loss)
  const tgt   = Number(form.target_price)

  const inputStyle = {
    width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid var(--border)",
    background: "var(--bg)", color: "var(--text)", fontSize: 13, outline: "none",
  }

  const labelStyle = { fontSize: 11, color: "var(--text2)", marginBottom: 4, display: "block" as const }

  return (
    <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--accent)", borderWidth: 1.5 }}>
      <div className="flex items-center gap-2 mb-4">
        <Edit3 size={14} style={{ color: "var(--accent2)" }} />
        <span className="font-semibold text-sm">Manual Trade Entry</span>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label style={labelStyle}>Stock / Ticker *</label>
          <input style={inputStyle} placeholder="e.g. RELIANCE" value={form.ticker}
            onChange={e => set("ticker", e.target.value.toUpperCase())} />
        </div>
        <div>
          <label style={labelStyle}>Instrument</label>
          <select style={inputStyle} value={form.instrument} onChange={e => set("instrument", e.target.value)}>
            {["EQ", "FUT", "OPT-CE", "OPT-PE"].map(o => <option key={o}>{o}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Direction *</label>
          <select style={inputStyle} value={form.direction} onChange={e => set("direction", e.target.value)}>
            {["BUY", "SELL", "AVOID"].map(o => <option key={o}>{o}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Timeframe</label>
          <select style={inputStyle} value={form.timeframe} onChange={e => set("timeframe", e.target.value)}>
            {["Intraday", "Swing", "Positional", "Long-term"].map(o => <option key={o}>{o}</option>)}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Entry Price *</label>
          <input style={inputStyle} type="number" placeholder="₹0.00" value={form.entry_price}
            onChange={e => set("entry_price", e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Quantity / Lots *</label>
          <input style={inputStyle} type="number" placeholder="1" value={form.quantity}
            onChange={e => set("quantity", e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Stop Loss *</label>
          <input style={{ ...inputStyle, borderColor: "rgba(239,68,68,0.4)" }} type="number" placeholder="₹0.00"
            value={form.stop_loss} onChange={e => set("stop_loss", e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Target *</label>
          <input style={{ ...inputStyle, borderColor: "rgba(34,197,94,0.4)" }} type="number" placeholder="₹0.00"
            value={form.target_price} onChange={e => set("target_price", e.target.value)} />
        </div>
      </div>

      {/* Live R:R preview */}
      {entry > 0 && sl > 0 && tgt > 0 && (
        <div className="rounded-lg p-3 mb-3" style={{ background: "var(--bg3)" }}>
          <RRBar entry={entry} sl={sl} tgt={tgt} dir={form.direction} />
        </div>
      )}

      <div className="mb-3">
        <label style={labelStyle}>Notes / Singhvi Quote</label>
        <textarea
          style={{ ...inputStyle, minHeight: 52, resize: "vertical" }}
          placeholder="What did Singhvi say? Any conditions?"
          value={form.notes}
          onChange={e => set("notes", e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => {
            if (!form.ticker || !form.entry_price || !form.stop_loss || !form.target_price) return
            onSubmit(form)
          }}
          className="flex-1 py-2.5 rounded-lg font-semibold text-sm"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          Add to Queue
        </button>
        <button onClick={onCancel} className="px-4 py-2.5 rounded-lg text-sm"
          style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function MorningSetupPage() {
  const qc = useQueryClient()
  const istTime = useISTTime()
  const mkt = marketStatus(istTime)
  const [showForm, setShowForm] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [executeLoading, setExecuteLoading] = useState(false)

  // Fetch today's calls
  const { data: calls = [], isLoading, refetch } = useQuery({
    queryKey: ["singhvi-today"],
    queryFn: () => apiFetch<{ calls: any[] }>("/api/singhvi/today").then(r => r.calls),
    refetchInterval: 15_000,
  })

  const pending  = calls.filter(c => c.status === "pending")
  const approved = calls.filter(c => c.status === "approved")
  const rejected = calls.filter(c => c.status === "rejected")

  // Mutations
  const patchCall = async (id: number, action: string) => {
    await apiFetch(`/api/singhvi/calls/${id}/${action}`, { method: "POST" })
    qc.invalidateQueries({ queryKey: ["singhvi-today"] })
  }

  const addCall = useMutation({
    mutationFn: (data: any) => apiFetch("/api/singhvi/calls", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["singhvi-today"] }); setShowForm(false) },
  })

  const deleteCall = async (id: number) => {
    await apiFetch(`/api/singhvi/calls/${id}`, { method: "DELETE" })
    qc.invalidateQueries({ queryKey: ["singhvi-today"] })
  }

  const triggerExtract = async () => {
    setExtracting(true)
    try {
      await apiFetch("/api/singhvi/extract", { method: "POST" })
      await refetch()
    } finally {
      setExtracting(false)
    }
  }

  const executeAll = async () => {
    setExecuteLoading(true)
    try {
      await apiFetch("/api/singhvi/execute", { method: "POST" })
      qc.invalidateQueries({ queryKey: ["singhvi-today"] })
    } finally {
      setExecuteLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Sun size={20} style={{ color: "var(--amber)" }} />
          <div>
            <h1 className="text-2xl font-bold">Morning Setup</h1>
            <div style={{ fontSize: 12, color: "var(--text2)" }}>Pre-market trade queue — enter calls before 9:15 AM</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            <Clock size={12} style={{ color: "var(--text2)" }} />
            <span style={{ fontFamily: "monospace", fontSize: 13 }}>IST {istTime}</span>
            <span className="text-xs font-semibold px-1.5 py-0.5 rounded-full" style={{ background: mkt.color + "22", color: mkt.color }}>
              {mkt.label}
            </span>
          </div>
        </div>
      </div>

      {/* ── Status bar ── */}
      <div className="rounded-xl p-4 mb-6 flex items-center justify-between flex-wrap gap-3"
        style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
        <div className="flex gap-6">
          {[
            { label: "Pending Review", val: pending.length,  color: "var(--amber)" },
            { label: "Approved",       val: approved.length, color: "var(--green)" },
            { label: "Skipped",        val: rejected.length, color: "var(--red)"   },
            { label: "Total Today",    val: calls.length,    color: "var(--text)"  },
          ].map(({ label, val, color }) => (
            <div key={label}>
              <div style={{ fontSize: 10, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color }}>{val}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-2 flex-wrap">
          <button
            onClick={triggerExtract}
            disabled={extracting}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium"
            style={{ background: "rgba(239,68,68,0.12)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.25)" }}
          >
            <Youtube size={14} />
            {extracting ? "Extracting…" : "Extract from Zee Business"}
          </button>
          <button
            onClick={() => setShowForm(v => !v)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium"
            style={{ background: "var(--bg3)", color: "var(--text)", border: "1px solid var(--border)" }}
          >
            <Plus size={14} />
            Add Manual Call
          </button>
        </div>
      </div>

      {/* ── Manual form ── */}
      {showForm && (
        <div className="mb-6">
          <ManualEntryForm
            onSubmit={(data) => addCall.mutate({ ...data, source: "manual", status: "pending" })}
            onCancel={() => setShowForm(false)}
          />
        </div>
      )}

      <div className="grid gap-6" style={{ gridTemplateColumns: "1fr 380px" }}>

        {/* ── Left: Pending calls ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="font-semibold text-sm" style={{ color: "var(--text2)" }}>
              REVIEW QUEUE ({pending.length + approved.length})
            </span>
            <button onClick={() => refetch()} style={{ color: "var(--text2)" }}>
              <RefreshCw size={13} />
            </button>
          </div>

          {isLoading && (
            <div className="text-center py-12 text-sm" style={{ color: "var(--text2)" }}>Loading…</div>
          )}

          {!isLoading && calls.length === 0 && (
            <div className="rounded-xl p-8 text-center" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
              <Youtube size={32} style={{ color: "var(--text2)", margin: "0 auto 12px" }} />
              <div className="font-semibold mb-1">No calls yet today</div>
              <div className="text-sm" style={{ color: "var(--text2)" }}>
                Run the Zee Business extractor after 8 AM,<br />or add calls manually above.
              </div>
            </div>
          )}

          <div className="space-y-3">
            {/* Pending first, then approved */}
            {[...pending, ...approved].map(call => (
              <CallCard
                key={call.id}
                call={call}
                onApprove={() => patchCall(call.id, "approve")}
                onReject={() => patchCall(call.id, "reject")}
                onDelete={() => deleteCall(call.id)}
              />
            ))}
            {rejected.map(call => (
              <CallCard
                key={call.id}
                call={call}
                onApprove={() => patchCall(call.id, "approve")}
                onReject={() => patchCall(call.id, "reject")}
                onDelete={() => deleteCall(call.id)}
              />
            ))}
          </div>
        </div>

        {/* ── Right: Execution panel ── */}
        <div className="space-y-4">

          {/* HDFC connection status */}
          <div className="rounded-xl p-4" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} style={{ color: "var(--accent2)" }} />
              <span className="font-semibold text-sm">HDFC Connection</span>
            </div>
            <HDFCStatus />
          </div>

          {/* Execute panel */}
          <div className="rounded-xl p-4" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-3">
              <Send size={14} style={{ color: "var(--green)" }} />
              <span className="font-semibold text-sm">Execute at Market Open</span>
            </div>

            {approved.length === 0 ? (
              <div className="text-sm py-4 text-center" style={{ color: "var(--text2)" }}>
                Approve calls on the left to add them here
              </div>
            ) : (
              <>
                <div className="space-y-2 mb-4">
                  {approved.map(c => (
                    <div key={c.id} className="flex items-center justify-between rounded-lg px-3 py-2"
                      style={{ background: "var(--bg3)" }}>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm">{c.ticker}</span>
                        <span className="text-xs font-semibold" style={{ color: dirColor(c.direction) }}>{c.direction}</span>
                      </div>
                      <div className="text-xs" style={{ color: "var(--text2)" }}>
                        ₹{Number(c.entry_price).toLocaleString("en-IN")} · qty {c.quantity || "—"}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="rounded-lg p-3 mb-4" style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.25)" }}>
                  <div className="flex items-start gap-2">
                    <AlertTriangle size={13} style={{ color: "var(--amber)", marginTop: 1, flexShrink: 0 }} />
                    <div style={{ fontSize: 12, color: "var(--amber)" }}>
                      Orders will be placed on HDFC at market open (9:15 AM IST).
                      Confirm that margins are available.
                    </div>
                  </div>
                </div>

                <button
                  onClick={executeAll}
                  disabled={executeLoading}
                  className="w-full py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2"
                  style={{ background: executeLoading ? "var(--bg3)" : "var(--green)", color: executeLoading ? "var(--text2)" : "#000" }}
                >
                  <Zap size={15} />
                  {executeLoading ? "Sending to HDFC…" : `Execute ${approved.length} Trade${approved.length > 1 ? "s" : ""} on HDFC`}
                </button>
              </>
            )}
          </div>

          {/* Today's summary */}
          <div className="rounded-xl p-4" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            <div className="font-semibold text-sm mb-3" style={{ color: "var(--text2)" }}>HOW TO USE</div>
            <div className="space-y-2" style={{ fontSize: 12, color: "var(--text2)" }}>
              {[
                ["8:00 AM", "Extractor pulls Zee Business audio"],
                ["8:15 AM", "Review extracted calls — approve or skip"],
                ["8:45 AM", "Add any calls you heard manually"],
                ["9:00 AM", "Verify approved queue + margins"],
                ["9:15 AM", "Hit Execute — orders placed at open"],
              ].map(([time, action]) => (
                <div key={time} className="flex gap-3">
                  <span style={{ color: "var(--accent2)", fontWeight: 600, minWidth: 52 }}>{time}</span>
                  <span>{action}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── HDFC Status widget ────────────────────────────────────────────────────────

function HDFCStatus() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["hdfc-status"],
    queryFn: () => apiFetch<any>("/api/hdfc/status"),
    refetchInterval: 60_000,
  })

  const initAuth = async () => {
    const res = await apiFetch<any>("/api/hdfc/auth/init", { method: "POST" })
    if (res.login_url) window.open(res.login_url, "_blank", "width=500,height=700")
    setTimeout(() => refetch(), 5000)
  }

  if (isLoading) return <div style={{ fontSize: 12, color: "var(--text2)" }}>Checking…</div>

  if (data?.connected) {
    return (
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)" }} />
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--green)" }}>Connected</span>
        </div>
        <div style={{ fontSize: 12, color: "var(--text2)" }}>
          Client: 45889297 · Available: ₹{data?.available_margin?.toLocaleString("en-IN") || "—"}
        </div>
        <div style={{ fontSize: 11, color: "var(--text2)", marginTop: 4 }}>
          Token expires: {data?.token_expiry || "Today EOD"}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--red)" }} />
        <span style={{ fontSize: 13, color: "var(--red)" }}>Not connected</span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 10 }}>
        Login once daily to activate trading. OTP takes ~30 seconds.
      </div>
      <button
        onClick={initAuth}
        className="w-full py-2 rounded-lg text-sm font-semibold"
        style={{ background: "var(--accent)", color: "#fff" }}
      >
        Login to HDFC (Daily)
      </button>
    </div>
  )
}
