"use client"

import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Sun, Plus, Trash2, CheckCircle, XCircle, Youtube, Edit3,
  TrendingUp, TrendingDown, Minus, Clock, Zap, AlertTriangle,
  ChevronRight, RefreshCw, Send, Crosshair, FileSpreadsheet, Download, Upload, MessageCircle, Calendar
} from "lucide-react"
import { api } from "@/lib/api"
import type { ShareLevel, PortfolioImportResult, WaSweepFlag, WaSweepChat, ComplianceUpcomingItem } from "@/lib/types"

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

      {/* ── Share Master: the one workbook (share-master-daily bot) ── */}
      <ShareMasterCard />

      {/* ── Share buy/sell levels (levels-alert bot) ── */}
      <LevelsCard />

      {/* ── WhatsApp sweep (wa-sweep bot): Mausaji share lines, site-group bottlenecks, silence ── */}
      <WaSweepCard />

      {/* ── Compliance (compliance-reminder bot): statutory dates in the next 30 days ── */}
      <ComplianceCard />

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

// ── Levels card — Aman's whole buy/sell list, every share, live distance ───────
// Aman, chat 2026-10-09: always the entire list, both sides, including shares not yet at their level.

function fmtN(x: number | null | undefined) {
  if (x === null || x === undefined) return "—"
  return Number.isInteger(x) ? x.toLocaleString("en-IN") : x.toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

function Distance({ pct, at, side }: { pct: number | null; at: boolean; side: "buy" | "sell" }) {
  if (at) return <span style={{ color: side === "buy" ? "var(--green)" : "var(--red)", fontWeight: 700 }}>{side === "buy" ? "AT BUY" : "AT SELL"}</span>
  if (pct === null) return <span style={{ color: "var(--text2)" }}>—</span>
  return <span style={{ color: "var(--text2)" }}>{pct < 0 ? "−" : "+"}{Math.abs(pct).toFixed(1)}% away</span>
}

function LevelsCard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["levels"],
    queryFn: api.levels.list,
    refetchInterval: 60_000,
  })
  const levels: ShareLevel[] = data?.levels ?? []
  const hits = data?.hits_today ?? []
  const asOf = data?.ltp_as_of ? data.ltp_as_of.slice(11, 16) + " IST" : "no price yet"
  const th: React.CSSProperties = { fontSize: 10, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border)" }
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid var(--border)", fontSize: 13, whiteSpace: "nowrap" }
  return (
    <div className="rounded-xl p-4 mb-6" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Crosshair size={15} style={{ color: "var(--amber)" }} />
          <span className="font-semibold text-sm" style={{ color: "var(--text2)" }}>
            LEVELS ({data?.active ?? 0} shares{hits.length ? ` · ${hits.length} hit today` : ""})
          </span>
        </div>
        <div className="flex items-center gap-3" style={{ fontSize: 11, color: "var(--text2)" }}>
          <span>ltp as of {asOf} · {data?.market_open ? "market open" : "market closed"}</span>
          <button onClick={() => refetch()} style={{ color: "var(--text2)" }} title="refresh"><RefreshCw size={13} /></button>
        </div>
      </div>
      {isLoading && <div style={{ fontSize: 12, color: "var(--text2)" }}>Loading…</div>}
      {error && <div style={{ fontSize: 12, color: "var(--red)" }}>Levels unavailable: {String((error as Error).message)}</div>}
      {!isLoading && !error && levels.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--text2)" }}>
          Empty. Tell the Chief of Staff on WhatsApp: <span style={{ color: "var(--text)" }}>"add TCS buy 3500 sell 4200"</span>.
        </div>
      )}
      {levels.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              <th style={th}>Share</th><th style={th}>LTP</th>
              <th style={th}>Buy ≤</th><th style={th}>Distance</th>
              <th style={th}>Sell ≥</th><th style={th}>Distance</th>
              <th style={th}>Held by</th>
              <th style={{ ...th, whiteSpace: "normal" }}>Note</th>
            </tr></thead>
            <tbody>
              {levels.map(l => {
                const hot = l.active && (l.at_buy || l.at_sell)
                return (
                  <tr key={l.ticker} style={{ opacity: l.active ? 1 : 0.45, background: hot ? (l.at_buy ? "rgba(52,211,153,0.08)" : "rgba(248,113,113,0.08)") : undefined }}>
                    <td style={{ ...td, fontWeight: 700 }}>{l.ticker}{!l.active && <span style={{ color: "var(--text2)", fontWeight: 400 }}> (paused)</span>}</td>
                    {/* Directive 17: a missing price shows the reason, never a blank */}
                    <td style={{ ...td, fontFamily: "monospace" }}>{l.ltp === null ? <span style={{ color: "var(--red)", fontSize: 11 }}>no price (Yahoo n/a)</span> : `₹${fmtN(l.ltp)}`}</td>
                    <td style={{ ...td, fontFamily: "monospace", color: "var(--green)" }}>
                      {l.buy_level === null ? "—" : fmtN(l.buy_level)}
                      {l.best_entry != null && <span style={{ color: "var(--text2)", fontSize: 11 }}> (best {fmtN(l.best_entry)})</span>}
                    </td>
                    <td style={td}>{l.buy_level === null ? "" : <Distance pct={l.buy_distance_pct} at={l.at_buy} side="buy" />}</td>
                    <td style={{ ...td, fontFamily: "monospace", color: "var(--red)" }}>{l.sell_level === null ? "—" : fmtN(l.sell_level)}</td>
                    <td style={td}>{l.sell_level === null ? "" : <Distance pct={l.sell_distance_pct} at={l.at_sell} side="sell" />}</td>
                    {/* Directive 18: who holds it and how many, or "nobody" */}
                    <td style={{ ...td, whiteSpace: "normal", fontSize: 12, color: l.held_text && l.held_text !== "nobody" ? "var(--text)" : "var(--text2)" }}>{l.held_text ?? "nobody"}</td>
                    <td style={{ ...td, whiteSpace: "normal", color: "var(--text2)", fontSize: 12 }}>{l.note}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {hits.length > 0 && (
        <div className="mt-3" style={{ fontSize: 12, color: "var(--text2)" }}>
          hits today: {hits.map(h => `${h.ticker} ${h.side} ₹${fmtN(h.ltp)} vs ₹${fmtN(h.level)} (${String(h.hit_at).slice(11, 16)})`).join("; ")}
        </div>
      )}
    </div>
  )
}

// ── WhatsApp sweep card — open flags from the wa-sweep bot, one ack button each ────────────────
// Aman, chat 2026-10-09. Rule-based, no model. Directive 17: nothing is drawn until both the flags and the
// chat list have arrived; an error says so instead of showing half a card.

const KIND_LABEL: Record<WaSweepFlag["kind"], { text: string; color: string }> = {
  call:       { text: "CALL",       color: "var(--green)" },
  mention:    { text: "SHARE",      color: "var(--amber)" },
  bottleneck: { text: "BOTTLENECK", color: "var(--red)" },
  silence:    { text: "SILENT",     color: "var(--text2)" },
}

function istClock(iso: string | null | undefined) {
  if (!iso) return "—"
  const d = new Date(iso)
  if (isNaN(d.getTime())) return String(iso).slice(11, 16)
  return d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false })
}

function WaSweepCard() {
  const qc = useQueryClient()
  const flagsQ = useQuery({ queryKey: ["wa-sweep-flags"], queryFn: () => api.waSweep.flags("open"), refetchInterval: 60_000 })
  const chatsQ = useQuery({ queryKey: ["wa-sweep-chats"], queryFn: api.waSweep.chats, refetchInterval: 5 * 60_000 })
  const ack = useMutation({
    mutationFn: (id: number) => api.waSweep.ack(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wa-sweep-flags"] }),
  })
  const loading = flagsQ.isLoading || chatsQ.isLoading
  const error = flagsQ.error || chatsQ.error
  const flags: WaSweepFlag[] = flagsQ.data?.flags ?? []
  const chats: WaSweepChat[] = chatsQ.data?.chats ?? []
  const th: React.CSSProperties = { fontSize: 10, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border)" }
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid var(--border)", fontSize: 13, verticalAlign: "top" }
  return (
    <div className="rounded-xl p-4 mb-6" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <MessageCircle size={15} style={{ color: "var(--green)" }} />
          <span className="font-semibold text-sm" style={{ color: "var(--text2)" }}>
            WHATSAPP SWEEP{!loading && !error ? ` (${flagsQ.data?.open ?? 0} open · ${chats.length} chats watched)` : ""}
          </span>
        </div>
        <div className="flex items-center gap-3" style={{ fontSize: 11, color: "var(--text2)" }}>
          {!loading && !error && chatsQ.data && (
            <span>Mausaji chat "{chatsQ.data.mausaji_chat}": {chatsQ.data.mausaji_found ? "found" : "not seen yet"} · idle &gt; {chatsQ.data.idle_hours}h</span>
          )}
          <button onClick={() => { flagsQ.refetch(); chatsQ.refetch() }} style={{ color: "var(--text2)" }} title="refresh"><RefreshCw size={13} /></button>
        </div>
      </div>
      {loading && <div style={{ fontSize: 12, color: "var(--text2)" }}>Loading…</div>}
      {!loading && error && <div style={{ fontSize: 12, color: "var(--red)" }}>Sweep unavailable: {String((error as Error).message)}</div>}
      {!loading && !error && (
        <>
          <div className="mb-3" style={{ fontSize: 12, color: "var(--text2)", lineHeight: 1.6 }}>
            {chats.length === 0
              ? <>No chat matches yet — WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env decide the set.</>
              : <>watching: {chats.map(c => (
                  <span key={c.jid} style={{ marginRight: 10, color: c.mode === "mausaji" ? "var(--amber)" : "var(--text)" }}>
                    {c.name}
                    <span style={{ color: "var(--text2)" }}> ({c.mode}{c.priority !== "normal" ? ` · ${c.priority}` : ""} · last {istClock(c.last_message_at)})</span>
                  </span>
                ))}</>}
          </div>
          {flags.length === 0 && <div style={{ fontSize: 12, color: "var(--text2)" }}>0 open flags. The bot reports every run even when it finds nothing.</div>}
          {flags.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>
                  <th style={th}>When</th><th style={th}>Chat</th><th style={th}>Kind</th><th style={th}>Who</th>
                  <th style={{ ...th, whiteSpace: "normal" }}>Said</th><th style={th}>Pushed</th><th style={th}></th>
                </tr></thead>
                <tbody>
                  {flags.map(f => {
                    const k = KIND_LABEL[f.kind] ?? { text: f.kind.toUpperCase(), color: "var(--text2)" }
                    const tag = f.kind === "silence"
                      ? `silent ${f.detail?.silent_hours ?? "?"}h`
                      : f.ticker ? f.ticker : (f.detail?.words ?? []).slice(0, 3).join(", ")
                    return (
                      <tr key={f.id}>
                        <td style={{ ...td, whiteSpace: "nowrap", fontFamily: "monospace" }}>{f.day.slice(5)} {istClock(f.msg_at)}</td>
                        <td style={{ ...td, whiteSpace: "nowrap", fontWeight: 600 }}>{f.chat_name || f.chat_jid}</td>
                        <td style={{ ...td, whiteSpace: "nowrap" }}>
                          <span style={{ color: k.color, fontWeight: 700, fontSize: 11 }}>{k.text}</span>
                          {tag && <span style={{ color: "var(--text2)", fontSize: 11 }}> {tag}</span>}
                        </td>
                        <td style={{ ...td, whiteSpace: "nowrap", color: "var(--text2)" }}>{f.sender || "—"}</td>
                        <td style={{ ...td, whiteSpace: "normal", minWidth: 240 }}>{f.kind === "silence" ? `no message since ${istClock(f.msg_at)} IST` : f.text}</td>
                        <td style={{ ...td, whiteSpace: "nowrap", fontSize: 11, color: f.pushed_at ? "var(--green)" : "var(--red)" }}>{f.pushed_at ? istClock(f.pushed_at) : "not sent"}</td>
                        <td style={{ ...td, whiteSpace: "nowrap" }}>
                          <button onClick={() => ack.mutate(f.id)} disabled={ack.isPending}
                            className="px-2 py-1 rounded text-xs flex items-center gap-1"
                            style={{ border: "1px solid var(--border)", color: "var(--text2)", opacity: ack.isPending ? 0.6 : 1 }} title="acknowledge">
                            <CheckCircle size={12} /> ack
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Compliance card — the statutory calendar's next 30 days (compliance-reminder bot) ──
// Aman, chat 2026-10-09: governmentally fixed dates, reminder a week before, no questions. Rows come from
// /api/compliance/upcoming (calendar rules × entity list); until the CoS loads compliance_entities every row is
// group-level and the card says so. Loading state first, never a half table (Directive 17).

function dueTag(d: ComplianceUpcomingItem): { text: string; color: string } {
  if (d.done) return { text: "done", color: "var(--green)" }
  if (d.days_left <= 0) return { text: "today", color: "var(--red)" }
  if (d.days_left === 1) return { text: "tomorrow", color: "var(--red)" }
  if (d.days_left <= 7) return { text: `${d.days_left} days`, color: "var(--amber)" }
  return { text: `${d.days_left} days`, color: "var(--text2)" }
}

function ComplianceCard() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ["compliance-upcoming"], queryFn: () => api.complianceCalendar.upcoming(30), refetchInterval: 10 * 60_000 })
  const done = useMutation({
    mutationFn: (id: number) => api.complianceCalendar.done(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["compliance-upcoming"] }),
  })
  const items: ComplianceUpcomingItem[] = q.data?.items ?? []
  const th: React.CSSProperties = { fontSize: 10, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--border)" }
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid var(--border)", fontSize: 13, verticalAlign: "top" }
  const fmt = (iso: string) => {
    const d = new Date(iso + "T00:00:00")
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" })
  }
  return (
    <div className="rounded-xl p-4 mb-6" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Calendar size={15} style={{ color: "var(--amber)" }} />
          <span className="font-semibold text-sm" style={{ color: "var(--text2)" }}>
            COMPLIANCE{!q.isLoading && !q.error && q.data ? ` (next 30 days · ${items.length} dated)` : ""}
          </span>
        </div>
        <div className="flex items-center gap-3" style={{ fontSize: 11, color: "var(--text2)" }}>
          {!q.isLoading && !q.error && q.data && (
            <span>{q.data.entities_loaded ? `${q.data.entity_count} entities loaded` : "entity list not loaded — group level"}</span>
          )}
          <button onClick={() => q.refetch()} style={{ color: "var(--text2)" }} title="refresh"><RefreshCw size={13} /></button>
        </div>
      </div>
      {q.isLoading && <div style={{ fontSize: 12, color: "var(--text2)" }}>Loading…</div>}
      {!q.isLoading && q.error && <div style={{ fontSize: 12, color: "var(--red)" }}>Compliance unavailable: {String((q.error as Error).message)}</div>}
      {!q.isLoading && !q.error && q.data && (
        <>
          {items.length === 0 && <div style={{ fontSize: 12, color: "var(--text2)" }}>Nothing dated in the next 30 days. The bot reports every run even when nothing is due.</div>}
          {items.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead><tr>
                  <th style={th}>Due</th><th style={th}>In</th><th style={{ ...th, whiteSpace: "normal" }}>Item</th>
                  <th style={{ ...th, whiteSpace: "normal" }}>Who</th><th style={th}>Reminded</th><th style={th}></th>
                </tr></thead>
                <tbody>
                  {items.map(it => {
                    const tag = dueTag(it)
                    const last = it.reminders.filter(r => r.sent_at).slice(-1)[0]
                    const open = it.reminders.find(r => r.status !== "done")
                    return (
                      <tr key={`${it.item_id}-${it.due}`} style={{ opacity: it.done ? 0.55 : 1 }}>
                        <td style={{ ...td, whiteSpace: "nowrap", fontFamily: "monospace" }}>{fmt(it.due)}</td>
                        <td style={{ ...td, whiteSpace: "nowrap", color: tag.color, fontWeight: 700, fontSize: 11 }}>{tag.text}</td>
                        <td style={{ ...td, whiteSpace: "normal", minWidth: 220 }} title={it.source}>
                          {it.label}
                          {it.payment && <span style={{ color: "var(--amber)", fontSize: 11 }}> · payment (your click)</span>}
                          {it.extendable && <span style={{ color: "var(--text2)", fontSize: 11 }}> · extendable by notification</span>}
                        </td>
                        <td style={{ ...td, whiteSpace: "normal", color: it.level === "group" ? "var(--text2)" : "var(--text)" }}>{it.targets.join(", ")}</td>
                        <td style={{ ...td, whiteSpace: "nowrap", fontSize: 11, color: last ? "var(--green)" : "var(--text2)" }}>
                          {last ? `${last.stage} · ${istClock(last.sent_at)}` : "not yet"}
                        </td>
                        <td style={{ ...td, whiteSpace: "nowrap" }}>
                          {open && !it.done && (
                            <button onClick={() => done.mutate(open.id)} disabled={done.isPending}
                              className="px-2 py-1 rounded text-xs flex items-center gap-1"
                              style={{ border: "1px solid var(--border)", color: "var(--text2)", opacity: done.isPending ? 0.6 : 1 }} title="filed / paid — stop further reminders">
                              <CheckCircle size={12} /> done
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-2" style={{ fontSize: 11, color: "var(--text2)" }}>{q.data.footer}</div>
        </>
      )}
    </div>
  )
}

// ── Share Master card — the one workbook Aman opens: Portfolio · Mausaji Calls · Levels · Summary ──
// Aman, chat 2026-10-09. Numbers come from /api/share-master (the last refresh); the button downloads the
// same .xlsx the bot saves to the vault. The upload box takes the HDFC Securities portfolio export (CSV)
// for a named holder — the Portfolio fallback until that broker session is live again.

function inr(x: number | null | undefined) {
  if (x === null || x === undefined) return "—"
  return "₹" + Math.round(x).toLocaleString("en-IN")
}

function ShareMasterCard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["share-master"],
    queryFn: api.shareMaster.get,
    refetchInterval: 5 * 60_000,
  })
  const [busy, setBusy] = useState<"" | "download" | "refresh" | "upload">("")
  const [msg, setMsg] = useState<string>("")
  const [holder, setHolder] = useState<string>("")
  const [file, setFile] = useState<File | null>(null)
  const s = data?.summary
  const accounts = data?.portfolio.accounts ?? []
  const stale = accounts.filter(a => !a.ok)

  const run = async (what: "download" | "refresh" | "upload", fn: () => Promise<string>) => {
    setBusy(what); setMsg("")
    try { setMsg(await fn()) } catch (e) { setMsg(`${what} failed: ${(e as Error).message}`) } finally { setBusy("") }
  }
  const upload = () => run("upload", async () => {
    if (!holder.trim()) throw new Error("whose account? type the holder name first")
    if (!file) throw new Error("choose the HDFC portfolio CSV first")
    const csv = await file.text()
    const r: PortfolioImportResult = await api.shareMaster.importPortfolio(holder.trim(), csv)
    setFile(null)
    await refetch()
    const unv = r.unverified.length ? ` · ${r.unverified.length} unverified ticker(s): ${r.unverified.join(", ")}` : ""
    const skipped = r.skipped.length ? ` · ${r.skipped.length} row(s) skipped` : ""
    return `${r.holder}: ${r.count} holdings stored from the CSV${unv}${skipped}. The next refresh uses them while the broker session is down.`
  })

  const Stat = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div style={{ minWidth: 110 }}>
      <div style={{ fontSize: 10, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "monospace", color: color || "var(--text)" }}>{value}</div>
    </div>
  )
  const pnlColor = (s?.total.pnl ?? 0) >= 0 ? "var(--green)" : "var(--red)"

  return (
    <div className="rounded-xl p-4 mb-6" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <FileSpreadsheet size={15} style={{ color: "var(--accent)" }} />
          <span className="font-semibold text-sm" style={{ color: "var(--text2)" }}>SHARE MASTER</span>
          <span style={{ fontSize: 11, color: "var(--text2)" }}>
            {data?.portfolio.snap_date ? `portfolio snapshot ${data.portfolio.snap_date}` : "no snapshot yet"} · Mausaji chat “{data?.mausaji_chat ?? "Bantu Mausaji"}”
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => run("refresh", async () => { const r = await api.shareMaster.refresh(); await refetch(); return r.vault?.saved ? `refreshed · saved ${r.vault.path}` : `refreshed · vault save failed: ${r.vault?.error ?? "?"}` })}
            disabled={busy !== ""} className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1"
            style={{ border: "1px solid var(--border)", color: "var(--text2)", opacity: busy ? 0.6 : 1 }} title="fetch broker holdings + prices now, rebuild the workbook">
            <RefreshCw size={12} /> {busy === "refresh" ? "Refreshing…" : "Refresh now"}
          </button>
          <button onClick={() => run("download", async () => `downloaded ${await api.shareMaster.download()}`)}
            disabled={busy !== ""} className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1"
            style={{ background: "var(--accent)", color: "#fff", opacity: busy ? 0.6 : 1 }}>
            <Download size={12} /> {busy === "download" ? "Preparing…" : "Download Share_Master.xlsx"}
          </button>
        </div>
      </div>
      {isLoading && <div style={{ fontSize: 12, color: "var(--text2)" }}>Loading…</div>}
      {error && <div style={{ fontSize: 12, color: "var(--red)" }}>Share Master unavailable: {String((error as Error).message)}</div>}
      {s && (
        <div className="flex flex-wrap gap-5 mb-3">
          <Stat label="Holdings" value={`${s.total.n}`} />
          <Stat label="Invested" value={inr(s.total.invested)} />
          <Stat label="Value" value={inr(s.total.value)} />
          <Stat label="Unrealised P&L" value={`${inr(s.total.pnl)}${s.total.pnl_pct !== null ? ` (${s.total.pnl_pct >= 0 ? "+" : ""}${s.total.pnl_pct.toFixed(1)}%)` : ""}`} color={pnlColor} />
          <Stat label="Flags" value={`${s.flagged}`} color={s.flagged ? "var(--amber)" : undefined} />
          <Stat label="Mausaji calls" value={`${s.calls.total} · ${s.calls.open} open`} />
          <Stat label="Hit / stopped" value={`${s.calls.hit_target} / ${s.calls.hit_stop}`} />
          <Stat label="Levels" value={`${s.levels}`} />
          <Stat label="Positions P&L" value={`${inr(s.positions?.pl)} (${s.positions?.n ?? 0}${s.positions?.expiring_7d ? `, ${s.positions.expiring_7d} expiring ≤7d` : ""})`}
            color={(s.positions?.pl ?? 0) >= 0 ? "var(--green)" : "var(--red)"} />
          {s.unverified > 0 && <Stat label="Unverified tickers" value={`${s.unverified}`} color="var(--amber)" />}
        </div>
      )}
      {accounts.length > 0 && (
        <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 8 }}>
          {accounts.map(a => (
            <div key={a.account} style={{ color: a.ok ? "var(--text2)" : "var(--red)" }}>{a.ok ? "●" : "○"} {a.note}</div>
          ))}
        </div>
      )}
      {s && (s.top_gainers.length > 0 || s.top_losers.length > 0) && (
        <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 8 }}>
          {s.top_gainers.length > 0 && <div>top gainers: {s.top_gainers.map(g => `${g.ticker} +${g.pnl_pct.toFixed(1)}%`).join(" · ")}</div>}
          {s.top_losers.length > 0 && <div>top losers: {s.top_losers.map(g => `${g.ticker} ${g.pnl_pct.toFixed(1)}%`).join(" · ")}</div>}
        </div>
      )}
      <div className="flex items-center gap-2 flex-wrap mt-2 pt-3" style={{ borderTop: "1px solid var(--border)" }}>
        <Upload size={13} style={{ color: "var(--text2)" }} />
        <span style={{ fontSize: 12, color: "var(--text2)" }}>HDFC portfolio CSV{stale.length ? ` (fallback for ${stale.map(a => a.account).join(", ")})` : ""}:</span>
        <input value={holder} onChange={e => setHolder(e.target.value)} placeholder="holder, e.g. Aditi"
          className="px-2 py-1 rounded text-xs" style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)", width: 140 }} />
        <input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files?.[0] ?? null)} style={{ fontSize: 12, color: "var(--text2)" }} />
        <button onClick={upload} disabled={busy !== "" || !file || !holder.trim()}
          className="px-3 py-1 rounded-lg text-xs font-semibold" style={{ border: "1px solid var(--border)", color: "var(--text2)", opacity: (busy || !file || !holder.trim()) ? 0.5 : 1 }}>
          {busy === "upload" ? "Uploading…" : "Upload"}
        </button>
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.includes("failed") ? "var(--red)" : "var(--green)", marginTop: 6 }}>{msg}</div>}
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
