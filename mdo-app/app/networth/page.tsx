"use client"

// Live net worth. The rule this page follows: it must never look live when it
// isn't. Every number is stamped with the broker's own as_of, and if sharecfo
// stops refreshing the page says so loudly instead of showing a confident stale
// figure. A wrong number here is worse than no number.

import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  IndianRupee, TrendingUp, TrendingDown, RefreshCw, AlertTriangle,
  Radio, Clock, Wallet, PieChart as PieIcon,
} from "lucide-react"
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type Live = {
  market_open: boolean
  poll_seconds: number
  as_of: string | null
  stale_hours: number | null
  net_worth: number | null
  day_change: number | null
  day_change_pct: number | null
  holdings_value: number | null
  invested_value: number | null
  cash: number | null
  unrealised_pnl: number | null
  points_today: number
  track: Array<{ t: string; as_of: string; net_worth: number; day_change_pct: number }>
  observed_refresh: {
    samples: number
    median_seconds: number | null
    fastest_seconds?: number
    slowest_seconds?: number
    note: string
  }
  warnings: string[]
  is_live: boolean
}

async function fetchLive(): Promise<Live> {
  const r = await fetch(`${BASE}/api/capital/networth/live`, { cache: "no-store" })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

// Indian formatting — lakh/crore, as everything else in MDO does.
function inr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—"
  const a = Math.abs(n)
  if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`
  return `₹${Math.round(n).toLocaleString("en-IN")}`
}

function clock(ts: string | null): string {
  if (!ts) return "—"
  const d = new Date(ts.includes("Z") || ts.includes("+") ? ts : ts + "Z")
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleTimeString("en-IN", {
    hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
  })
}

function ageLabel(hours: number | null): string {
  if (hours === null || hours === undefined) return "unknown age"
  const mins = Math.round(hours * 60)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min old`
  return `${hours.toFixed(1)} h old`
}

export default function NetWorthPage() {
  const qc = useQueryClient()
  const [tick, setTick] = useState(0)

  const { data, isLoading, error } = useQuery({
    queryKey: ["networth-live"],
    queryFn: fetchLive,
    // Poll the backend a little faster than it polls sharecfo, so a new broker
    // figure shows up promptly. Slow right down when the market is shut.
    refetchInterval: (q) => {
      const d = q.state.data as Live | undefined
      if (!d) return 30_000
      return d.market_open ? Math.max(15_000, (d.poll_seconds * 1000) / 3) : 300_000
    },
    refetchOnWindowFocus: true,
  })

  const capture = useMutation({
    mutationFn: async () => {
      const r = await fetch(`${BASE}/api/capital/networth/capture`, { method: "POST" })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json() as Promise<{ stored: boolean; reason?: string }>
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["networth-live"] }),
  })

  // Re-render once a second purely so the "as of" age counts up honestly.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const up = (data?.day_change_pct ?? 0) >= 0
  const track = (data?.track ?? []).map((p) => ({
    time: clock(p.t),
    value: p.net_worth,
  }))
  const opening =
    data?.net_worth != null && data?.day_change != null
      ? data.net_worth - data.day_change
      : null

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 space-y-5">
      {/* header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Wallet className="h-6 w-6" /> Live Net Worth
          </h1>
          <p className="text-sm text-white/50 mt-1">
            All broker accounts via sharecfo · read-only
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.is_live ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-300">
              <Radio className="h-3.5 w-3.5 animate-pulse" /> LIVE
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/60">
              <Clock className="h-3.5 w-3.5" />
              {data?.market_open ? "NOT LIVE" : "MARKET CLOSED"}
            </span>
          )}
          <button
            onClick={() => capture.mutate()}
            disabled={capture.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 hover:bg-white/15 px-3 py-1.5 text-sm disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${capture.isPending ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* the loud part: say when this is not live */}
      {(data?.warnings?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 space-y-1.5">
          {data!.warnings.map((w, i) => (
            <div key={i} className="flex gap-2 text-sm text-amber-200">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          Could not reach the MDO backend: {String((error as Error).message)}
        </div>
      )}

      {/* the number */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
        <div className="text-sm text-white/50 flex items-center gap-1.5">
          <IndianRupee className="h-4 w-4" /> Net worth — liquid book only
        </div>
        <div className="mt-2 flex items-baseline gap-4 flex-wrap">
          <span className="text-4xl sm:text-5xl font-semibold tabular-nums">
            {isLoading ? "…" : inr(data?.net_worth ?? null)}
          </span>
          {data?.day_change != null && (
            <span
              className={`inline-flex items-center gap-1 text-lg font-medium tabular-nums ${
                up ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {up ? <TrendingUp className="h-5 w-5" /> : <TrendingDown className="h-5 w-5" />}
              {inr(data.day_change)}
              {data.day_change_pct != null && ` (${(data.day_change_pct * 100).toFixed(2)}%)`}
            </span>
          )}
        </div>
        <div className="mt-3 text-xs text-white/40">
          Broker as of <span className="text-white/70">{clock(data?.as_of ?? null)} IST</span>
          {" · "}
          <span className={(data?.stale_hours ?? 0) > 1 ? "text-amber-300" : ""}>
            {ageLabel(data?.stale_hours ?? null)}
          </span>
          {" · "}
          {data?.points_today ?? 0} points today
        </div>
        <p className="mt-3 text-xs text-white/35 max-w-2xl">
          This is the tradeable book — holdings, cash and F&amp;O across the broker
          accounts. It is <strong className="text-white/50">not</strong> your net worth:
          property, unlisted equity, plant and every liability are not counted. See
          LIFE_LLM/domains/personal-assets-liabilities.md §4–§5.
        </p>
      </div>

      {/* breakdown */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        {[
          { label: "Holdings value", value: data?.holdings_value },
          { label: "Invested cost", value: data?.invested_value },
          { label: "Cash", value: data?.cash },
          { label: "Unrealised P&L", value: data?.unrealised_pnl },
        ].map((c) => (
          <div key={c.label} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <div className="text-xs text-white/45">{c.label}</div>
            <div className="mt-1 text-xl font-semibold tabular-nums">{inr(c.value ?? null)}</div>
          </div>
        ))}
      </div>

      {/* intraday track */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-medium flex items-center gap-2">
            <PieIcon className="h-4 w-4" /> Today&apos;s track
          </h2>
          <span className="text-xs text-white/40">
            one point per distinct broker figure — not per poll
          </span>
        </div>
        {track.length < 2 ? (
          <p className="mt-6 mb-4 text-sm text-white/40">
            {data?.market_open
              ? "Waiting for a second distinct broker figure. If this stays empty through the session, sharecfo is not refreshing — that is the thing to fix, not the poll interval."
              : "No track for today. The poller runs 09:00–15:45 IST on weekdays."}
          </p>
        ) : (
          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={track} margin={{ top: 5, right: 5, left: 5, bottom: 0 }}>
                <defs>
                  <linearGradient id="nw" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={up ? "#34d399" : "#f87171"} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={up ? "#34d399" : "#f87171"} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" tick={{ fontSize: 11, fill: "rgba(255,255,255,.4)" }}
                       axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "rgba(255,255,255,.4)" }}
                       axisLine={false} tickLine={false} width={70}
                       tickFormatter={(v) => inr(v as number)} />
                <Tooltip
                  contentStyle={{ background: "#0b0f14", border: "1px solid rgba(255,255,255,.12)",
                                  borderRadius: 10, fontSize: 12 }}
                  formatter={(v) => [inr(v as number), "Net worth"]}
                />
                {opening != null && (
                  <ReferenceLine y={opening} strokeDasharray="4 4"
                                 stroke="rgba(255,255,255,.25)"
                                 label={{ value: "open", fontSize: 10,
                                          fill: "rgba(255,255,255,.4)", position: "right" }} />
                )}
                <Area type="monotone" dataKey="value" stroke={up ? "#34d399" : "#f87171"}
                      strokeWidth={2} fill="url(#nw)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* measured feasibility — answers "what interval is possible" with data */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
        <h2 className="font-medium">Refresh cadence — measured, not assumed</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div>
            <div className="text-xs text-white/45">MDO polls sharecfo every</div>
            <div className="text-lg font-semibold tabular-nums">
              {data ? `${Math.round(data.poll_seconds / 60)} min` : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-white/45">sharecfo actually updates every</div>
            <div className="text-lg font-semibold tabular-nums">
              {data?.observed_refresh?.median_seconds
                ? `${(data.observed_refresh.median_seconds / 60).toFixed(1)} min`
                : "measuring…"}
            </div>
          </div>
          <div>
            <div className="text-xs text-white/45">Distinct figures seen today</div>
            <div className="text-lg font-semibold tabular-nums">
              {data?.observed_refresh?.samples ?? 0}
            </div>
          </div>
        </div>
        <p className="mt-3 text-xs text-white/40 max-w-2xl">
          {data?.observed_refresh?.note ??
            "Once a few distinct broker figures have been stored, this reports the real ceiling."}
          {" "}Tune with <code className="text-white/60">NETWORTH_POLL_SECONDS</code> in{" "}
          <code className="text-white/60">.env</code>; polling faster than sharecfo updates
          only re-reads the same number.
        </p>
      </div>
    </div>
  )
}
