"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLiveStore } from "@/lib/store"
import { TrendingUp, BarChart3, Wallet, LineChart } from "lucide-react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts"

function fmt(n: number) { return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

export default function TradingPage() {
  const { data: positions = [] } = useQuery({ queryKey: ["positions"], queryFn: api.positions })
  const { data: holdings = [] }  = useQuery({ queryKey: ["holdings"],  queryFn: api.holdings })
  const { data: pnl }            = useQuery({ queryKey: ["pnl"],       queryFn: api.pnl })
  const { data: funds }          = useQuery({ queryKey: ["funds"],     queryFn: api.funds })
  const prices = useLiveStore((s) => s.prices)

  const pnlData = positions.map((p) => {
    const ltp = prices[p.ticker] ?? p.ltp
    const pnl_ = (ltp - p.entry_price) * p.quantity * (p.side === "BUY" ? 1 : -1)
    return { name: p.ticker, pnl: parseFloat(pnl_.toFixed(2)) }
  })

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center gap-3">
        <TrendingUp size={20} style={{ color: "var(--accent2)" }} />
        <h1 className="text-2xl font-bold">Trading</h1>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Realised P&L",   val: pnl ? `₹${fmt(pnl.realized_pnl)}`   : "—", color: pnl && pnl.realized_pnl >= 0 ? "var(--green)" : "var(--red)" },
          { label: "Unrealised P&L", val: pnl ? `₹${fmt(pnl.unrealized_pnl)}` : "—", color: pnl && pnl.unrealized_pnl >= 0 ? "var(--green)" : "var(--red)" },
          { label: "Trades Today",   val: String(pnl?.trades_today ?? 0), color: "var(--text)" },
          { label: "Win Rate",       val: pnl ? `${(pnl.win_rate * 100).toFixed(0)}%` : "—", color: "var(--cyan)" },
        ].map(({ label, val, color }) => (
          <div key={label} className="rounded-xl p-4 border" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
            <div className="text-xs mb-1" style={{ color: "var(--text2)" }}>{label}</div>
            <div className="text-xl font-bold" style={{ color }}>{val}</div>
          </div>
        ))}
      </div>

      {/* P&L chart */}
      {pnlData.length > 0 && (
        <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={15} style={{ color: "var(--accent2)" }} />
            <span className="font-semibold text-sm">Position P&L</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={pnlData}>
              <XAxis dataKey="name" tick={{ fill: "var(--text2)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text2)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)" }}
                formatter={(v: number) => [`₹${fmt(v)}`, "P&L"]}
              />
              <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                {pnlData.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? "var(--green)" : "var(--red)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Funds */}
      {funds && (
        <div className="rounded-xl border p-4" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2 mb-3">
            <Wallet size={15} style={{ color: "var(--accent2)" }} />
            <span className="font-semibold text-sm">Funds — Aditi Investments</span>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Available", val: funds.available },
              { label: "Used Margin", val: funds.used_margin },
              { label: "Total", val: funds.total },
            ].map(({ label, val }) => (
              <div key={label}>
                <div className="text-xs" style={{ color: "var(--text2)" }}>{label}</div>
                <div className="font-bold mt-0.5">₹{fmt(val)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Holdings */}
      {holdings.length > 0 && (
        <div className="rounded-xl border" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
          <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: "var(--border)" }}>
            <LineChart size={15} style={{ color: "var(--accent2)" }} />
            <span className="font-semibold text-sm">Holdings</span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--text2)" }}>
                {["Ticker", "Qty", "Avg Price", "LTP", "Value", "P&L"].map((h) => (
                  <th key={h} className={`px-4 py-2 text-xs ${h !== "Ticker" ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.ticker} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="px-4 py-2.5 font-medium">{h.ticker}</td>
                  <td className="px-4 py-2.5 text-right">{h.quantity}</td>
                  <td className="px-4 py-2.5 text-right" style={{ color: "var(--text2)" }}>₹{fmt(h.average_price)}</td>
                  <td className="px-4 py-2.5 text-right">₹{fmt(prices[h.ticker] ?? h.ltp)}</td>
                  <td className="px-4 py-2.5 text-right">₹{fmt(h.current_value)}</td>
                  <td className="px-4 py-2.5 text-right" style={{ color: h.pnl >= 0 ? "var(--green)" : "var(--red)" }}>
                    {h.pnl >= 0 ? "+" : ""}₹{fmt(h.pnl)} ({h.pnl >= 0 ? "+" : ""}{h.pnl_pct.toFixed(2)}%)
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
