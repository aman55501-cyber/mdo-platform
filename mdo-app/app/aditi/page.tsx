"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLiveStore } from "@/lib/store"
import {
  TrendingUp, TrendingDown, IndianRupee, BarChart3, Shield, Zap, Lock, Sprout,
  CheckCircle, XCircle, Info, ExternalLink, Globe, Newspaper, Flame, AlertTriangle,
  TrendingDown as TDown, ChevronUp, ChevronDown, Minus, Activity, DollarSign,
  Calendar, Clock, Target, AlertCircle, ArrowUpRight, ArrowDownRight
} from "lucide-react"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, PieChart, Pie, Legend
} from "recharts"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${n.toLocaleString("en-IN")}`
}

function fmtCompact(n: number) {
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)} L`
  return `₹${Math.abs(n).toLocaleString("en-IN")}`
}

// ─── Pool meta ───────────────────────────────────────────────────────────────

const POOL_META = {
  A: { icon: Zap,        color: "#f59e0b", label: "Operating",    desc: "Working capital & liquidity" },
  B: { icon: TrendingUp, color: "#6366f1", label: "Liquid Growth", desc: "Active trading — Capital algo" },
  C: { icon: Sprout,     color: "#22c55e", label: "Strategic",    desc: "NPA, unlisted, real estate" },
  D: { icon: Shield,     color: "#06b6d4", label: "Preservation", desc: "Bonds, SGB, debt MF" },
}

// ─── Signal helpers ────────────────────────────────────────────────────────────

function sigProfit(s: any) { return Math.abs((s.target_price - s.entry_price) * s.quantity) }
function sigLoss(s: any)   { return Math.abs((s.entry_price - s.stop_loss) * s.quantity) }
function sigRR(s: any)     { const l = sigLoss(s); return l > 0 ? (sigProfit(s) / l).toFixed(1) : "∞" }

const BLOCK_DEALS = [
  { date: "23 Apr 2026", stock: "TATAMOTORS", buyer: "Nippon India MF", seller: "FII Block", qty: 12_50_000, price: 914.5,  amount: 114.3, type: "Block" },
  { date: "23 Apr 2026", stock: "WIPRO",      buyer: "HDFC AMC",        seller: "Promoter",  qty: 8_00_000,  price: 441.2,  amount: 35.3,  type: "Bulk" },
  { date: "22 Apr 2026", stock: "SUNPHARMA",  buyer: "SBI MF",          seller: "FII",       qty: 5_50_000,  price: 1582.0, amount: 87.0,  type: "Block" },
  { date: "22 Apr 2026", stock: "ICICIBANK",  buyer: "LIC",             seller: "FII Block", qty: 10_00_000, price: 1227.0, amount: 122.7, type: "Block" },
  { date: "21 Apr 2026", stock: "BAJFINANCE", buyer: "Mirae Asset",     seller: "Promoter",  qty: 3_00_000,  price: 8940.0, amount: 268.2, type: "Bulk" },
]

const CORP_ACTIONS = [
  { date: "18 Apr 2026", stock: "INFY",       action: "Q4 Results",          detail: "Q4 FY26 earnings — beat expected by 3%",     type: "results",  sentiment: "bullish" },
  { date: "22 Apr 2026", stock: "TCS",        action: "Dividend ₹28",        detail: "Ex-dividend date — ₹28/share payout",        type: "dividend", sentiment: "neutral" },
  { date: "25 Apr 2026", stock: "HDFCBANK",   action: "Q4 Results",          detail: "Expected NIM compression, watch provision",  type: "results",  sentiment: "neutral" },
  { date: "30 Apr 2026", stock: "RELIANCE",   action: "Bonus 1:1",           detail: "1 extra share for every 1 held",             type: "bonus",    sentiment: "bullish" },
  { date: "05 May 2026", stock: "BAJAJ-AUTO", action: "Stock Split 5:1",     detail: "Face value from ₹10 → ₹2",                  type: "split",    sentiment: "bullish" },
]

const FII_DII = {
  fii_net_today:  -1240e6,
  dii_net_today:   890e6,
  fii_net_month: -8400e6,
  dii_net_month:  6200e6,
}

const GLOBAL_TRIGGERS = [
  { label: "S&P 500",         value: "5,248",  change: "+0.42%", dir: "up",   cat: "US Markets",   note: "US markets up = global sentiment positive → Nifty may open higher" },
  { label: "NASDAQ",          value: "16,390", change: "-0.18%", dir: "down", cat: "US Markets",   note: "Tech selling in US can pull IT stocks like TCS, Infy down at open" },
  { label: "Dow Jones",       value: "39,118", change: "+0.31%", dir: "up",   cat: "US Markets",   note: "Dow up signals broad US economy health — mild positive for India" },
  { label: "WTI Crude",       value: "$82.4",  change: "+1.2%",  dir: "up",   cat: "Commodities",  note: "Crude UP is bad for India — we import oil. Higher costs = inflation, rupee weaker" },
  { label: "Brent Crude",     value: "$86.1",  change: "+0.9%",  dir: "up",   cat: "Commodities",  note: "Brent rising hits petro companies and airlines hardest. Watch ONGC, IndiGo" },
  { label: "USD / INR",       value: "83.42",  change: "+0.08",  dir: "up",   cat: "Currency",     note: "Rupee weakening: IT exporters (TCS, Wipro) earn more. Importers (pharma) pay more" },
  { label: "Gold (10g)",      value: "₹72,400",change: "+0.3%",  dir: "up",   cat: "Commodities",  note: "Gold rising = risk-off mood. Often means money leaving equities for safety" },
  { label: "US 10Y Yield",    value: "4.32%",  change: "+0.03",  dir: "up",   cat: "Bonds",        note: "Higher US yields attract foreign money away from India → FII selling likely" },
  { label: "SGX Nifty",       value: "24,215", change: "+0.22%", dir: "up",   cat: "Pre-market",   note: "SGX Nifty trades before India opens — best pre-market indicator for Nifty direction" },
  { label: "India VIX",       value: "14.2",   change: "-0.8%",  dir: "down", cat: "Fear Gauge",   note: "VIX below 15 = calm market. Above 20 = fear. Options get expensive when VIX rises" },
  { label: "Shanghai Comp",   value: "3,041",  change: "-0.55%", dir: "down", cat: "Asia Markets", note: "China weak = Asia-wide risk-off. May affect metals (steel, copper) and export-heavy stocks" },
  { label: "Hang Seng",       value: "17,284", change: "-0.41%", dir: "down", cat: "Asia Markets", note: "HK market weakness often mirrors China sentiment and drags broader EM (India) sentiment" },
]

const MARKET_CALENDAR = [
  { date: "24 Apr 2026", event: "F&O Expiry (Monthly)",   type: "expiry",   note: "High volatility day — rollover activity" },
  { date: "07 May 2026", event: "US Fed Meeting",          type: "macro",    note: "Rate decision — major market mover globally" },
  { date: "09 May 2026", event: "India Industrial Output", type: "macro",    note: "IIP data — economic health indicator" },
  { date: "13 May 2026", event: "India CPI Inflation",     type: "macro",    note: "Inflation data — affects RBI rate path" },
  { date: "Jun 2026",    event: "Q4 Results Season ends",  type: "results",  note: "Most NIFTY 50 companies report by June" },
]

const NEWS_ITEMS = [
  {
    headline: "RBI holds repo rate at 6.25% — signals rate cut possible in June",
    source: "Economic Times", time: "2h ago",
    impact: "BULLISH",
    stocks: ["HDFCBANK", "ICICIBANK", "KOTAKBANK"],
    summary: "Rate pause means borrowing stays stable. If June cut happens, banking stocks and real estate will rally. Good for Pool B positions.",
  },
  {
    headline: "FII outflows cross ₹8,400 Cr in April — risk-off as US yields rise",
    source: "Moneycontrol", time: "4h ago",
    impact: "BEARISH",
    stocks: ["NIFTY", "SENSEX"],
    summary: "Foreign investors pulling money out = selling pressure on markets. Algo should be cautious with fresh BUY trades this week.",
  },
  {
    headline: "Reliance Q4 profit ₹19,407 Cr — up 7.8% YoY, Jio & retail beat estimates",
    source: "BSE Filings", time: "6h ago",
    impact: "BULLISH",
    stocks: ["RELIANCE"],
    summary: "Strong results confirm our BUY signal on Reliance. Target of ₹1,360 looks achievable in near term.",
  },
  {
    headline: "Crude oil jumps 3% — OPEC+ hints at further supply cuts in May",
    source: "Reuters", time: "8h ago",
    impact: "BEARISH",
    stocks: ["ONGC", "BPCL", "INDIGO"],
    summary: "Oil rising hurts India's trade balance. Aviation and OMC stocks under pressure. Watch our open positions.",
  },
  {
    headline: "IT sector hiring picks up — TCS, Wipro see deal pipeline improve",
    source: "Mint", time: "1d ago",
    impact: "BULLISH",
    stocks: ["TCS", "WIPRO", "INFY"],
    summary: "IT recovery could be a Q1 FY27 theme. Worth watching for fresh entry opportunities.",
  },
  {
    headline: "India PMI Manufacturing at 59.1 — strongest reading in 14 months",
    source: "Moneycontrol", time: "1d ago",
    impact: "BULLISH",
    stocks: ["LTIM", "TITAN", "MARUTI"],
    summary: "Strong manufacturing = broad economic growth. Positive backdrop for cyclicals and consumer stocks.",
  },
]

// ─── Sub-components ────────────────────────────────────────────────────────────

function PoolCard({ pool }: { pool: any }) {
  const meta = POOL_META[pool.pool_code as keyof typeof POOL_META]
  if (!meta) return null
  const Icon = meta.icon
  const pct = pool.target_allocation > 0 ? (pool.current_value / pool.target_allocation * 100) : 0
  const diff = pool.current_value - pool.target_allocation

  return (
    <div className="rounded-xl border p-5" style={{ background: "var(--bg2)", borderColor: meta.color + "40" }}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: meta.color + "18" }}>
            <Icon size={18} style={{ color: meta.color }} />
          </div>
          <div>
            <div className="font-bold text-sm">Pool {pool.pool_code} — {meta.label}</div>
            <div className="text-xs" style={{ color: "var(--text2)" }}>{meta.desc}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-bold" style={{ color: meta.color }}>{fmt(pool.current_value)}</div>
          <div className="text-xs" style={{ color: diff >= 0 ? "var(--green)" : "var(--red)" }}>
            {diff >= 0 ? "+" : ""}{fmt(Math.abs(diff))} vs target
          </div>
        </div>
      </div>
      <div className="h-1.5 rounded-full mb-3" style={{ background: "var(--bg3)" }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(pct, 100)}%`, background: meta.color }} />
      </div>
      <div className="flex justify-between text-xs" style={{ color: "var(--text2)" }}>
        <span>Target: {fmt(pool.target_allocation)}</span>
        <span>{pct.toFixed(0)}% allocated</span>
      </div>
      <div className="mt-2 text-xs px-2 py-1 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
        {pool.instruments}
      </div>
      {pool.notes && <div className="mt-1 text-xs" style={{ color: "var(--text2)" }}>{pool.notes}</div>}
    </div>
  )
}

function RiskRewardBar({ entry, target, sl }: { entry: number; target: number; sl: number }) {
  const profit = target - entry
  const loss = entry - sl
  const total = profit + loss
  const profitPct = total > 0 ? (profit / total) * 100 : 50

  return (
    <div className="mt-2">
      <div className="flex text-xs mb-1 justify-between" style={{ color: "var(--text2)" }}>
        <span style={{ color: "var(--red)" }}>Loss zone</span>
        <span style={{ color: "var(--green)" }}>Profit zone</span>
      </div>
      <div className="h-3 rounded-full overflow-hidden flex" style={{ background: "var(--bg3)" }}>
        <div className="h-full rounded-l-full" style={{ width: `${100 - profitPct}%`, background: "rgba(239,68,68,0.7)" }} />
        <div className="h-full rounded-r-full" style={{ width: `${profitPct}%`, background: "rgba(34,197,94,0.7)" }} />
      </div>
      <div className="flex text-xs mt-1 justify-between" style={{ color: "var(--text2)" }}>
        <span>SL ₹{sl.toLocaleString("en-IN")}</span>
        <span>Entry ₹{entry.toLocaleString("en-IN")}</span>
        <span>Target ₹{target.toLocaleString("en-IN")}</span>
      </div>
    </div>
  )
}

function SignalCard({ sig, poolB, onConfirm, onReject }: {
  sig: any
  poolB: number
  onConfirm: () => void
  onReject: () => void
}) {
  const [showDetails, setShowDetails] = useState(false)
  const isBuy = sig.action === "BUY"
  const profit = sigProfit(sig)
  const loss   = sigLoss(sig)
  const rrRatio = sigRR(sig)
  const sideColor = isBuy ? "var(--green)" : "var(--red)"
  const confColor = sig.confidence >= 70 ? "var(--green)" : sig.confidence >= 60 ? "#f59e0b" : "var(--red)"
  const isExecuted = sig.status === "executed"
  const isConfirmed = sig.status === "confirmed"
  const isRejected = sig.status === "rejected"

  if (isRejected) return (
    <div className="rounded-xl border p-5 flex items-center gap-3 opacity-40"
      style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
      <XCircle size={20} style={{ color: "var(--text2)" }} />
      <span className="text-sm" style={{ color: "var(--text2)" }}>Skipped — {sig.ticker}</span>
    </div>
  )

  if (isExecuted) return (
    <div className="rounded-xl border p-5" style={{ background: "var(--bg2)", borderColor: "#22c55e40" }}>
      <div className="flex items-center gap-2 mb-2">
        <CheckCircle size={18} style={{ color: "var(--green)" }} />
        <span className="font-bold text-sm" style={{ color: "var(--green)" }}>Executed — {sig.ticker}</span>
        {sig.order_id && <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>Order #{sig.order_id}</span>}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="p-2 rounded-lg text-center" style={{ background: "var(--bg3)" }}>
          <div style={{ color: "var(--text2)" }}>Executed at</div>
          <div className="font-bold">₹{(sig.executed_price || sig.entry_price).toLocaleString("en-IN")}</div>
        </div>
        <div className="p-2 rounded-lg text-center" style={{ background: sig.pnl >= 0 ? "#22c55e18" : "#ef444418" }}>
          <div style={{ color: "var(--text2)" }}>P&L</div>
          <div className="font-bold" style={{ color: sig.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
            {sig.pnl >= 0 ? "+" : ""}₹{sig.pnl?.toLocaleString("en-IN") || "—"}
          </div>
        </div>
        <div className="p-2 rounded-lg text-center" style={{ background: "var(--bg3)" }}>
          <div style={{ color: "var(--text2)" }}>Target</div>
          <div className="font-bold" style={{ color: "var(--green)" }}>₹{sig.target_price.toLocaleString("en-IN")}</div>
        </div>
      </div>
    </div>
  )

  if (isConfirmed) return (
    <div className="rounded-xl border p-5" style={{ background: "var(--bg2)", borderColor: "#6366f140" }}>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#6366f1" }} />
        <span className="font-bold text-sm" style={{ color: "var(--accent2)" }}>Confirmed — {sig.ticker} · Awaiting execution</span>
      </div>
      <div className="text-xs" style={{ color: "var(--text2)" }}>
        Capital engine will execute at next market opportunity. Entry: ₹{sig.entry_price.toLocaleString("en-IN")}
      </div>
    </div>
  )

  return (
    <div className="rounded-xl border p-5" style={{ background: "var(--bg2)", borderColor: sideColor + "30" }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="font-bold text-base">{sig.ticker}</span>
          <span className="w-2 h-2 rounded-full" style={{ background: sideColor }} />
          <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ background: sideColor + "20", color: sideColor }}>
            {sig.action} CALL
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>{sig.instrument_type}</span>
          {/* Live pulse — pending signal */}
          <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#f59e0b" }} title="Awaiting your decision" />
        </div>
      </div>

      <div className="my-3 border-t" style={{ borderColor: "var(--border)" }} />

      {/* Plain English summary */}
      {sig.plain_english && (
        <div className="text-sm mb-3 p-3 rounded-lg italic leading-relaxed" style={{ background: "var(--bg3)", color: "var(--text)" }}>
          "{sig.plain_english}"
        </div>
      )}

      {/* Entry / Target / SL */}
      <div className="grid grid-cols-3 gap-2 text-center mb-3">
        <div className="p-2 rounded-lg" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>📈 Entry</div>
          <div className="font-bold text-sm">₹{sig.entry_price.toLocaleString("en-IN")}</div>
        </div>
        <div className="p-2 rounded-lg" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>🎯 Target</div>
          <div className="font-bold text-sm" style={{ color: "var(--green)" }}>₹{sig.target_price.toLocaleString("en-IN")}</div>
        </div>
        <div className="p-2 rounded-lg" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>🛑 Stop Loss</div>
          <div className="font-bold text-sm" style={{ color: "var(--red)" }}>₹{sig.stop_loss.toLocaleString("en-IN")}</div>
        </div>
      </div>

      {/* Max Profit / Max Loss */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="p-2.5 rounded-lg" style={{ background: "#22c55e18", border: "1px solid #22c55e30" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>
            Best case ({sig.quantity} {sig.instrument_type === "futures" ? "lots" : "shares"})
          </div>
          <div className="font-bold" style={{ color: "var(--green)" }}>+{fmt(profit)}</div>
        </div>
        <div className="p-2.5 rounded-lg" style={{ background: "#ef444418", border: "1px solid #ef444430" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>Worst case (SL hit)</div>
          <div className="font-bold" style={{ color: "var(--red)" }}>−{fmt(loss)}</div>
        </div>
      </div>

      {/* Risk-Reward */}
      <div className="p-3 rounded-lg mb-3" style={{ background: "var(--bg3)" }}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold">Risk-Reward</span>
          <span className="text-base font-bold" style={{ color: "var(--accent2)" }}>1 : {rrRatio}</span>
        </div>
        <div className="text-xs mb-2" style={{ color: "var(--text2)" }}>
          Risk ₹1 → potentially earn ₹{rrRatio}. Rule: only trade if ratio ≥ 1:2.
        </div>
        <RiskRewardBar entry={sig.entry_price} target={sig.target_price} sl={sig.stop_loss} />
      </div>

      {/* Expandable details */}
      {showDetails && (
        <div className="mb-3 p-3 rounded-lg text-xs space-y-1.5" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          <div className="flex justify-between"><span>Quantity</span><span className="font-medium" style={{ color: "var(--text)" }}>{sig.quantity}</span></div>
          <div className="flex justify-between"><span>Strategy</span><span className="font-medium" style={{ color: "var(--text)" }}>{sig.strategy}</span></div>
          {sig.rationale && <div><span>Rationale: </span><span style={{ color: "var(--text)" }}>{sig.rationale}</span></div>}
          <div className="flex justify-between"><span>Best case % on Pool B</span>
            <span className="font-medium" style={{ color: "var(--green)" }}>{poolB > 0 ? ((profit/poolB)*100).toFixed(3) : "—"}%</span>
          </div>
          <div className="flex justify-between"><span>Worst case % on Pool B</span>
            <span className="font-medium" style={{ color: "var(--red)" }}>{poolB > 0 ? ((loss/poolB)*100).toFixed(3) : "—"}%</span>
          </div>
          <div className="flex justify-between"><span>Signal ID</span><span>#{sig.id}</span></div>
          <div className="flex justify-between"><span>Created</span><span>{new Date(sig.created_at).toLocaleTimeString("en-IN")}</span></div>
        </div>
      )}

      {/* Confidence + strategy row */}
      <div className="flex items-center justify-between text-xs mb-3" style={{ color: "var(--text2)" }}>
        <span>Confidence: <span className="font-bold" style={{ color: confColor }}>{sig.confidence}%</span></span>
        <span>Strategy: {sig.strategy || "Capital Algo"}</span>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button onClick={onConfirm}
          className="flex-1 py-2.5 rounded-lg text-sm font-bold transition-all hover:opacity-90"
          style={{ background: sideColor, color: "#fff" }}>
          ✓ Confirm Trade
        </button>
        <button onClick={() => setShowDetails(v => !v)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          {showDetails ? "Less" : "Details"}
        </button>
        <button onClick={onReject}
          className="px-3 py-2 rounded-lg text-sm hover:opacity-80"
          style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          Skip
        </button>
      </div>
    </div>
  )
}

function RiskMeter({ poolB, signals }: { poolB: number; signals: any[] }) {
  const maxLossTotal = signals.reduce((s, sig) => s + sigLoss(sig), 0)
  const pct = poolB > 0 ? (maxLossTotal / poolB) * 100 : 0
  const barColor = pct < 2 ? "#22c55e" : pct < 4 ? "#f59e0b" : "#ef4444"
  const label = pct < 2 ? "SAFE" : pct < 4 ? "CAUTION" : "HIGH RISK"

  return (
    <div className="rounded-xl border p-4 mb-6" style={{ background: "var(--bg2)", borderColor: barColor + "40" }}>
      <div className="flex items-center gap-2 mb-3">
        <Activity size={16} style={{ color: barColor }} />
        <span className="font-semibold text-sm">Portfolio Risk Meter — Today</span>
        <span className="ml-auto text-xs font-bold px-2 py-0.5 rounded" style={{ background: barColor + "20", color: barColor }}>{label}</span>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="p-2 rounded-lg text-center" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>Pool B (Trading)</div>
          <div className="font-bold text-sm" style={{ color: "#6366f1" }}>{fmt(poolB)}</div>
        </div>
        <div className="p-2 rounded-lg text-center" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>Max Loss Today</div>
          <div className="font-bold text-sm" style={{ color: "var(--red)" }}>−{fmt(maxLossTotal)}</div>
        </div>
        <div className="p-2 rounded-lg text-center" style={{ background: "var(--bg3)" }}>
          <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>Risk % of Pool</div>
          <div className="font-bold text-sm" style={{ color: barColor }}>{pct.toFixed(2)}%</div>
        </div>
      </div>
      <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--bg3)" }}>
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${Math.min(pct / 5 * 100, 100)}%`, background: barColor }}
        />
      </div>
      <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text2)" }}>
        <span>0%</span><span>2% — Safe limit</span><span>4% — Caution</span><span>5% max</span>
      </div>
    </div>
  )
}

function GlobalCard({ item }: { item: typeof GLOBAL_TRIGGERS[0] }) {
  const isUp = item.dir === "up"
  const ArrowIcon = isUp ? ChevronUp : ChevronDown
  const changeColor = item.dir === "up" ? "var(--green)" : "var(--red)"
  const [showNote, setShowNote] = useState(false)

  return (
    <div
      className="rounded-xl border p-3 cursor-pointer transition-all hover:border-opacity-80"
      style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
      onClick={() => setShowNote(v => !v)}
    >
      <div className="text-xs mb-1 font-medium" style={{ color: "var(--text2)" }}>{item.cat}</div>
      <div className="flex items-end justify-between mb-0.5">
        <div className="font-bold text-sm">{item.label}</div>
        <div className="flex items-center gap-0.5" style={{ color: changeColor }}>
          <ArrowIcon size={12} />
          <span className="text-xs font-semibold">{item.change}</span>
        </div>
      </div>
      <div className="text-lg font-bold" style={{ color: "var(--text)" }}>{item.value}</div>
      {showNote && (
        <div className="mt-2 text-xs p-2 rounded" style={{ background: "var(--bg3)", color: "var(--text2)", borderLeft: `2px solid ${changeColor}` }}>
          {item.note}
        </div>
      )}
      {!showNote && (
        <div className="text-xs mt-1" style={{ color: "var(--text2)", opacity: 0.6 }}>Tap for impact</div>
      )}
    </div>
  )
}

// ─── Trade Ideas Tab (live signals) ──────────────────────────────────────────

function TradeIdeasTab({ poolB }: { poolB: number }) {
  const qc = useQueryClient()

  const { data: signals = [], isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["trading_signals"],
    queryFn:  () => (api as any).trading.signals(),
    refetchInterval: 8_000,  // poll every 8s for new signals
  })

  const mutConfirm = useMutation({
    mutationFn: (id: number) => (api as any).trading.confirm(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trading_signals"] }),
  })
  const mutReject = useMutation({
    mutationFn: (id: number) => (api as any).trading.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trading_signals"] }),
  })

  const pending   = signals.filter((s: any) => s.status === "pending")
  const confirmed = signals.filter((s: any) => s.status === "confirmed")
  const executed  = signals.filter((s: any) => s.status === "executed")

  const lastUpdated = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString("en-IN") : "—"

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-bold text-lg">Live Trade Ideas</h2>
          <p className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
            Real signals from Capital algo engine · Confirm to execute via HDFC · Updated {lastUpdated}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {pending.length > 0 && (
            <span className="flex items-center gap-1 px-2 py-1 rounded-full font-bold animate-pulse"
              style={{ background: "#f59e0b20", color: "#f59e0b" }}>
              ● {pending.length} new signal{pending.length > 1 ? "s" : ""}
            </span>
          )}
          <span className="px-2 py-1 rounded" style={{ background: "var(--bg2)", color: "var(--text2)" }}>
            {isLoading ? "Loading…" : isError ? "Backend offline" : "Live ✓"}
          </span>
        </div>
      </div>

      {/* Risk meter — only when there are signals */}
      {signals.length > 0 && <RiskMeter poolB={poolB} signals={signals} />}

      {/* No signals state */}
      {!isLoading && signals.length === 0 && (
        <div className="rounded-xl border p-8 text-center" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <Activity size={32} style={{ color: "var(--text2)", margin: "0 auto 12px" }} />
          <div className="font-semibold mb-1">No active signals</div>
          <div className="text-xs" style={{ color: "var(--text2)" }}>
            Capital algo engine will post signals here as it finds opportunities during market hours (9:15 AM – 3:30 PM).
            <br />Connect HDFC API in <code className="px-1 rounded" style={{ background: "var(--bg3)" }}>.env</code> to enable live trading.
          </div>
        </div>
      )}

      {/* Pending signals — action required */}
      {pending.length > 0 && (
        <div>
          <div className="text-xs font-bold uppercase tracking-wide mb-2 flex items-center gap-2" style={{ color: "#f59e0b" }}>
            <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#f59e0b" }} />
            Action Required ({pending.length})
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {pending.map((sig: any) => (
              <SignalCard key={sig.id} sig={sig} poolB={poolB}
                onConfirm={() => mutConfirm.mutate(sig.id)}
                onReject={() => mutReject.mutate(sig.id)} />
            ))}
          </div>
        </div>
      )}

      {/* Confirmed — awaiting execution */}
      {confirmed.length > 0 && (
        <div>
          <div className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: "var(--accent2)" }}>
            Confirmed — Awaiting Execution ({confirmed.length})
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {confirmed.map((sig: any) => (
              <SignalCard key={sig.id} sig={sig} poolB={poolB}
                onConfirm={() => {}} onReject={() => mutReject.mutate(sig.id)} />
            ))}
          </div>
        </div>
      )}

      {/* Executed trades today */}
      {executed.length > 0 && (
        <div>
          <div className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: "var(--green)" }}>
            Executed Today ({executed.length})
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {executed.map((sig: any) => (
              <SignalCard key={sig.id} sig={sig} poolB={poolB}
                onConfirm={() => {}} onReject={() => {}} />
            ))}
          </div>
        </div>
      )}

      {/* How-to card */}
      <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        <div className="font-semibold text-sm mb-3">How to read these signals</div>
        <div className="text-xs space-y-2" style={{ color: "var(--text2)" }}>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Entry price:</span> The exact price Capital wants to buy/sell at. Don't enter if price has moved more than 0.5% away.</p>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Target (🎯):</span> Where we expect the trade to reach. Capital will auto-book profits here.</p>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Stop Loss (🛑):</span> The safety exit. If market goes against us, Capital exits here to limit damage. Never remove the SL.</p>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Risk-Reward 1:2+:</span> For every ₹1 you risk, you should stand to make at least ₹2. Skip any trade below 1:1.5.</p>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Confidence:</span> Below 60% = skip. 65-70% = acceptable. 75%+ = strong. Never override a 55% signal with "gut feeling".</p>
          <p><span className="font-semibold" style={{ color: "var(--text)" }}>Confirm = execute:</span> Clicking Confirm tells Capital to place the actual order on HDFC Securities. There is no undo once confirmed.</p>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

const TABS = ["Portfolio", "Trade Ideas", "Market Intel", "Global Triggers", "News"] as const
type Tab = typeof TABS[number]

export default function AditiPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Portfolio")

  const { data: pools = []  }    = useQuery({ queryKey: ["aditi_pools"],  queryFn: () => api.aditi.pools() })
  const { data: positions = [] } = useQuery({ queryKey: ["positions"],    queryFn: api.positions })
  const { data: holdings = [] }  = useQuery({ queryKey: ["holdings"],     queryFn: api.holdings })
  const { data: pnl }            = useQuery({ queryKey: ["pnl"],          queryFn: api.pnl })
  const { data: funds }          = useQuery({ queryKey: ["funds"],        queryFn: api.funds })
  const prices = useLiveStore(s => s.prices)

  const totalAUM = pools.reduce((s: number, p: any) => s + (p.current_value || 0), 0)
  const poolB = pools.find((p: any) => p.pool_code === "B")?.current_value ?? 16_00_00_000

  const pnlData = positions.map((p: any) => {
    const ltp = prices[p.ticker] ?? p.ltp
    const pnl_ = (ltp - p.entry_price) * p.quantity * (p.side === "BUY" ? 1 : -1)
    return { name: p.ticker, pnl: parseFloat(pnl_.toFixed(0)) }
  })

  const pieData = pools.map((p: any) => ({
    name: `Pool ${p.pool_code}`,
    value: p.current_value,
    color: POOL_META[p.pool_code as keyof typeof POOL_META]?.color || "#888",
  }))

  return (
    <div className="max-w-5xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold">Aditi Investments</h1>
          <div className="text-sm mt-0.5" style={{ color: "var(--text2)" }}>Capital management · Raigarh, CG</div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold" style={{ color: "var(--accent2)" }}>{fmt(totalAUM || 25_40_00_000)}</div>
          <div className="text-xs" style={{ color: "var(--text2)" }}>Total AUM across 4 pools</div>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 p-1 rounded-xl" style={{ background: "var(--bg2)" }}>
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="flex-1 py-2 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: activeTab === tab ? "var(--accent2)" : "transparent",
              color: activeTab === tab ? "#000" : "var(--text2)",
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── TAB 1: Portfolio ─────────────────────────────────────────────── */}
      {activeTab === "Portfolio" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {pools.length > 0
              ? pools.map((p: any) => <PoolCard key={p.pool_code} pool={p} />)
              : [
                  { pool_code: "A", current_value: 1_80_00_000, target_allocation: 2_00_00_000, instruments: "HDFC Bank savings, FD, current a/c", notes: "" },
                  { pool_code: "B", current_value: 16_00_00_000, target_allocation: 15_00_00_000, instruments: "NSE equities + F&O via HDFC Securities", notes: "Capital algo active" },
                  { pool_code: "C", current_value: 4_50_00_000, target_allocation: 5_00_00_000, instruments: "NPA investments, unlisted equity, RE parcels", notes: "" },
                  { pool_code: "D", current_value: 3_10_00_000, target_allocation: 3_00_00_000, instruments: "SGB, G-Sec, debt MF, bonds", notes: "" },
                ].map((p: any) => <PoolCard key={p.pool_code} pool={p} />)
            }
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {(pieData.length > 0 || pools.length === 0) && (
              <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
                <div className="font-semibold text-sm mb-3">Capital Allocation</div>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={pieData.length > 0 ? pieData : [
                        { name: "Pool A", value: 1_80_00_000, color: "#f59e0b" },
                        { name: "Pool B", value: 16_00_00_000, color: "#6366f1" },
                        { name: "Pool C", value: 4_50_00_000, color: "#22c55e" },
                        { name: "Pool D", value: 3_10_00_000, color: "#06b6d4" },
                      ]}
                      cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                      dataKey="value" paddingAngle={3}
                    >
                      {(pieData.length > 0 ? pieData : [
                        { color: "#f59e0b" }, { color: "#6366f1" }, { color: "#22c55e" }, { color: "#06b6d4" }
                      ]).map((entry: any, i: number) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Legend formatter={(v) => <span style={{ fontSize: 11, color: "var(--text2)" }}>{v}</span>} />
                    <Tooltip
                      formatter={(v: number) => fmt(v)}
                      contentStyle={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 8 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}

            <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
              <div className="font-semibold text-sm mb-3" style={{ color: "#6366f1" }}>Pool B — Live Trading (Capital)</div>
              <div className="grid grid-cols-2 gap-3 mb-4">
                {[
                  { l: "Today P&L",    v: pnl ? (pnl.total_pnl >= 0 ? "+" : "") + fmt(pnl.total_pnl) : "—", c: pnl && pnl.total_pnl >= 0 ? "var(--green)" : "var(--red)" },
                  { l: "Win Rate",     v: pnl ? (pnl.win_rate * 100).toFixed(0) + "%" : "—", c: "var(--cyan)" },
                  { l: "Trades",       v: String(pnl?.trades_today ?? 0), c: "var(--text)" },
                  { l: "Available",    v: funds ? fmt(funds.available) : "—", c: "var(--text)" },
                ].map(({ l, v, c }) => (
                  <div key={l} className="px-3 py-2 rounded-lg" style={{ background: "var(--bg3)" }}>
                    <div className="text-xs" style={{ color: "var(--text2)" }}>{l}</div>
                    <div className="font-bold text-sm" style={{ color: c }}>{v}</div>
                  </div>
                ))}
              </div>
              {pnlData.length > 0 ? (
                <ResponsiveContainer width="100%" height={100}>
                  <BarChart data={pnlData}>
                    <XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 8 }}
                      formatter={(v: number) => [fmt(v), "P&L"]}
                    />
                    <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                      {pnlData.map((e: any, i: number) => <Cell key={i} fill={e.pnl >= 0 ? "var(--green)" : "var(--red)"} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-xs text-center py-4" style={{ color: "var(--text2)" }}>No open positions</div>
              )}
            </div>
          </div>

          {holdings.length > 0 && (
            <div className="rounded-xl border" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
              <div className="px-4 py-3 border-b font-semibold text-sm" style={{ borderColor: "var(--border)" }}>Holdings — Pool B</div>
              <table className="w-full text-sm">
                <thead>
                  <tr style={{ color: "var(--text2)" }}>
                    {["Ticker", "Qty", "Avg", "LTP", "Value", "P&L"].map(h => (
                      <th key={h} className={`px-4 py-2 text-xs ${h === "Ticker" ? "text-left" : "text-right"}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h: any) => (
                    <tr key={h.ticker} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="px-4 py-2.5 font-medium">{h.ticker}</td>
                      <td className="px-4 py-2.5 text-right">{h.quantity}</td>
                      <td className="px-4 py-2.5 text-right" style={{ color: "var(--text2)" }}>₹{h.average_price.toFixed(2)}</td>
                      <td className="px-4 py-2.5 text-right">₹{(prices[h.ticker] ?? h.ltp).toFixed(2)}</td>
                      <td className="px-4 py-2.5 text-right">₹{h.current_value.toLocaleString("en-IN")}</td>
                      <td className="px-4 py-2.5 text-right" style={{ color: h.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                        {h.pnl >= 0 ? "+" : ""}₹{h.pnl.toFixed(0)} ({h.pnl_pct.toFixed(1)}%)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: Trade Ideas (Live) ────────────────────────────────────── */}
      {activeTab === "Trade Ideas" && (
        <TradeIdeasTab poolB={poolB} />
      )}

      {/* ── TAB 3: Market Intelligence ───────────────────────────────────── */}
      {activeTab === "Market Intel" && (
        <div className="space-y-6">
          <div>
            <h2 className="font-bold text-lg">Market Intelligence</h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
              Block deals, corporate actions and FII/DII flows — the "smart money" signals.
            </p>
          </div>

          {/* Block & Bulk Deals */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold text-sm">Block & Bulk Deals</div>
              <div className="flex gap-2">
                <a href="https://www.nseindia.com/market-data/block-deals" target="_blank" rel="noreferrer"
                  className="text-xs px-2 py-1 rounded flex items-center gap-1 hover:opacity-80 transition-opacity"
                  style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                  NSE Block <ExternalLink size={10} />
                </a>
                <a href="https://www.nseindia.com/market-data/bulk-deals" target="_blank" rel="noreferrer"
                  className="text-xs px-2 py-1 rounded flex items-center gap-1 hover:opacity-80 transition-opacity"
                  style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                  NSE Bulk <ExternalLink size={10} />
                </a>
              </div>
            </div>
            <div className="text-xs mb-2 p-2 rounded" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
              Block deals = big trades (&gt;₹5Cr or 0.5% of equity) executed at specific time windows. They signal institutional conviction.
            </div>
            <div className="rounded-xl border overflow-hidden" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                    {["Date", "Stock", "Buyer", "Seller", "Qty (L)", "Price", "Amt (Cr)", "Type"].map(h => (
                      <th key={h} className="px-3 py-2 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {BLOCK_DEALS.map((d, i) => (
                    <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="px-3 py-2" style={{ color: "var(--text2)" }}>{d.date}</td>
                      <td className="px-3 py-2 font-bold">{d.stock}</td>
                      <td className="px-3 py-2" style={{ color: "var(--green)" }}>{d.buyer}</td>
                      <td className="px-3 py-2" style={{ color: "var(--red)" }}>{d.seller}</td>
                      <td className="px-3 py-2">{(d.qty / 1e5).toFixed(1)}</td>
                      <td className="px-3 py-2">₹{d.price.toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 font-semibold">₹{d.amount}Cr</td>
                      <td className="px-3 py-2">
                        <span className="px-1.5 py-0.5 rounded text-xs" style={{
                          background: d.type === "Block" ? "#6366f120" : "#f59e0b20",
                          color: d.type === "Block" ? "#6366f1" : "#f59e0b"
                        }}>{d.type}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Corporate Actions */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold text-sm">Corporate Actions</div>
              <a href="https://www.nseindia.com/companies-listing/corporate-filings-actions" target="_blank" rel="noreferrer"
                className="text-xs px-2 py-1 rounded flex items-center gap-1 hover:opacity-80"
                style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                NSE Actions <ExternalLink size={10} />
              </a>
            </div>
            <div className="space-y-2">
              {CORP_ACTIONS.map((a, i) => {
                const typeColors: Record<string, string> = {
                  results: "#6366f1", dividend: "#22c55e", bonus: "#f59e0b", split: "#06b6d4"
                }
                const sentimentColor = a.sentiment === "bullish" ? "var(--green)" : a.sentiment === "bearish" ? "var(--red)" : "var(--text2)"
                return (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-xl border" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
                    <div className="text-xs px-2 py-0.5 rounded min-w-fit" style={{ background: (typeColors[a.type] || "#888") + "20", color: typeColors[a.type] || "#888" }}>
                      {a.action}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm">{a.stock}</span>
                        <span className="text-xs" style={{ color: "var(--text2)" }}>{a.detail}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs" style={{ color: "var(--text2)" }}>{a.date}</div>
                      <div className="text-xs font-semibold capitalize" style={{ color: sentimentColor }}>{a.sentiment}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* FII / DII */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="font-semibold text-sm">FII / DII Activity</div>
                <div className="text-xs" style={{ color: "var(--text2)" }}>
                  FII = Foreign investors buying/selling Indian stocks. DII = Indian institutions (MFs, LIC).
                </div>
              </div>
              <a href="https://www.nseindia.com/market-data/fii-dii-trading-activity" target="_blank" rel="noreferrer"
                className="text-xs px-2 py-1 rounded flex items-center gap-1 hover:opacity-80"
                style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                NSE Data <ExternalLink size={10} />
              </a>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { l: "FII Today",   v: FII_DII.fii_net_today,  sub: "Foreign investors net" },
                { l: "DII Today",   v: FII_DII.dii_net_today,  sub: "Domestic institutions net" },
                { l: "FII Month",   v: FII_DII.fii_net_month,  sub: "April 2026 total" },
                { l: "DII Month",   v: FII_DII.dii_net_month,  sub: "April 2026 total" },
              ].map(({ l, v, sub }) => {
                const isPos = v >= 0
                const c = isPos ? "var(--green)" : "var(--red)"
                return (
                  <div key={l} className="rounded-xl border p-3" style={{ background: "var(--bg2)", borderColor: c + "30" }}>
                    <div className="text-xs mb-0.5" style={{ color: "var(--text2)" }}>{l}</div>
                    <div className="font-bold text-lg flex items-center gap-1" style={{ color: c }}>
                      {isPos ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
                      {isPos ? "+" : "−"}{fmtCompact(Math.abs(v))}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>{sub}</div>
                  </div>
                )
              })}
            </div>
            <div className="mt-3 p-3 rounded-lg text-xs" style={{ background: "var(--bg2)", borderColor: "var(--border)", border: "1px solid" }}>
              <span className="font-semibold">What this means: </span>
              <span style={{ color: "var(--text2)" }}>
                FIIs have sold ₹8,400 Cr in April — that's foreign money leaving India. Markets are under pressure.
                But DIIs (mutual funds, LIC) are absorbing the selling with ₹6,200 Cr in buying.
                Net effect: markets declining slowly, not crashing. Watch for FII reversal as a buy signal.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 4: Global Triggers ───────────────────────────────────────── */}
      {activeTab === "Global Triggers" && (
        <div className="space-y-6">
          <div>
            <h2 className="font-bold text-lg">Global Triggers</h2>
            <p className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
              Global factors that move Indian markets. Tap any card to see what it means for your portfolio.
            </p>
          </div>

          {/* US Markets */}
          <div>
            <div className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: "var(--text2)" }}>US Markets</div>
            <div className="grid grid-cols-3 gap-3">
              {GLOBAL_TRIGGERS.filter(t => t.cat === "US Markets").map((item, i) => (
                <GlobalCard key={i} item={item} />
              ))}
            </div>
          </div>

          {/* Commodities & Currency */}
          <div>
            <div className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: "var(--text2)" }}>Commodities & Currency</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {GLOBAL_TRIGGERS.filter(t => ["Commodities", "Currency"].includes(t.cat)).map((item, i) => (
                <GlobalCard key={i} item={item} />
              ))}
            </div>
          </div>

          {/* India & Asia */}
          <div>
            <div className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: "var(--text2)" }}>India & Asia Indicators</div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {GLOBAL_TRIGGERS.filter(t => ["Bonds", "Pre-market", "Fear Gauge", "Asia Markets"].includes(t.cat)).map((item, i) => (
                <GlobalCard key={i} item={item} />
              ))}
            </div>
          </div>

          {/* Market Calendar */}
          <div>
            <div className="font-semibold text-sm mb-3 flex items-center gap-2">
              <Calendar size={14} />
              Market Calendar — Upcoming Events
            </div>
            <div className="space-y-2">
              {MARKET_CALENDAR.map((ev, i) => {
                const typeColors: Record<string, string> = {
                  expiry: "#ef4444", macro: "#6366f1", results: "#f59e0b"
                }
                const c = typeColors[ev.type] || "#888"
                return (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-xl border" style={{ background: "var(--bg2)", borderColor: c + "30" }}>
                    <div className="min-w-[90px] text-xs font-semibold" style={{ color: c }}>{ev.date}</div>
                    <div className="flex-1">
                      <div className="font-semibold text-sm">{ev.event}</div>
                      <div className="text-xs" style={{ color: "var(--text2)" }}>{ev.note}</div>
                    </div>
                    <div className="text-xs px-2 py-0.5 rounded capitalize" style={{ background: c + "20", color: c }}>{ev.type}</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 5: News Feed ─────────────────────────────────────────────── */}
      {activeTab === "News" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-bold text-lg">News Feed</h2>
              <p className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>Market news filtered for Aditi portfolio impact.</p>
            </div>
          </div>

          {/* Quick links */}
          <div className="flex flex-wrap gap-2">
            {[
              { label: "ET Markets",         url: "https://economictimes.indiatimes.com/markets" },
              { label: "Moneycontrol",        url: "https://www.moneycontrol.com/news/business/markets/" },
              { label: "NSE Announcements",   url: "https://www.nseindia.com/companies-listing/corporate-filings-announcements" },
              { label: "BSE Filings",         url: "https://www.bseindia.com/corporates/ann.html" },
            ].map(({ label, url }) => (
              <a
                key={label}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg hover:opacity-80 transition-opacity"
                style={{ background: "var(--bg2)", color: "var(--text2)", border: "1px solid var(--border)" }}
              >
                <ExternalLink size={10} /> {label}
              </a>
            ))}
          </div>

          {/* News cards */}
          <div className="space-y-3">
            {NEWS_ITEMS.map((item, i) => {
              const impactColor = item.impact === "BULLISH" ? "#22c55e" : item.impact === "BEARISH" ? "#ef4444" : "#6366f1"
              return (
                <div key={i} className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: impactColor + "25" }}>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="font-semibold text-sm leading-snug flex-1">{item.headline}</div>
                    <span
                      className="text-xs font-bold px-2 py-0.5 rounded whitespace-nowrap"
                      style={{ background: impactColor + "20", color: impactColor }}
                    >
                      {item.impact}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs mb-2" style={{ color: "var(--text2)" }}>
                    <span className="font-medium">{item.source}</span>
                    <span>·</span>
                    <Clock size={10} />
                    <span>{item.time}</span>
                  </div>
                  <div className="text-xs p-2.5 rounded-lg mb-2" style={{ background: "var(--bg3)", color: "var(--text2)", borderLeft: `3px solid ${impactColor}` }}>
                    <span className="font-semibold" style={{ color: "var(--text)" }}>Impact on Portfolio: </span>
                    {item.summary}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {item.stocks.map(s => (
                      <span key={s} className="text-xs px-1.5 py-0.5 rounded font-mono" style={{ background: "var(--bg3)", color: "var(--accent2)" }}>{s}</span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
