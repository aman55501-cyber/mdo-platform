"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Newspaper, RefreshCw, TrendingUp, TrendingDown, Minus, ExternalLink, Bell } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...opts })
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

const TICKERS = [
  "RELIANCE","HDFCBANK","COALINDIA","NTPC","JSPL",
  "SAIL","HAL","TATAMOTORS","MSTC","NALCO",
  "VEDL","ADANIPOWER","JSWENERGY","IRCON","RITES"
]

function sentimentColor(s: string) {
  if (s === "bullish" || s === "positive") return "var(--green)"
  if (s === "bearish" || s === "negative") return "var(--red)"
  return "var(--amber)"
}

function SentimentIcon({ s }: { s: string }) {
  if (s === "bullish" || s === "positive") return <TrendingUp size={11} style={{ color: "var(--green)" }} />
  if (s === "bearish" || s === "negative") return <TrendingDown size={11} style={{ color: "var(--red)" }} />
  return <Minus size={11} style={{ color: "var(--amber)" }} />
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function NewsPage() {
  const qc = useQueryClient()
  const [activeTicker, setActiveTicker] = useState<string>("ALL")
  const [refreshing, setRefreshing] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["portfolio-news", activeTicker],
    queryFn: () => {
      const param = activeTicker !== "ALL" ? `?tickers=${activeTicker}` : ""
      return apiFetch<{ items: any[]; count: number }>(`/api/news/portfolio${param}`)
    },
    refetchInterval: 60_000,
  })

  const markRead = useMutation({
    mutationFn: (id: number) => apiFetch(`/api/news/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio-news"] }),
  })

  const refresh = async () => {
    setRefreshing(true)
    try {
      const r = await apiFetch<{ new_items: number }>("/api/news/portfolio/refresh", { method: "POST" })
      qc.invalidateQueries({ queryKey: ["portfolio-news"] })
    } finally {
      setRefreshing(false)
    }
  }

  const items = data?.items || []
  const unread = items.filter(i => !i.read).length

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Newspaper size={20} style={{ color: "var(--accent2)" }} />
          <div>
            <h1 className="text-2xl font-bold">Portfolio News</h1>
            <div style={{ fontSize: 12, color: "var(--text2)" }}>
              Real-time news for your holdings — {unread} unread
            </div>
          </div>
        </div>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium"
          style={{ background: "var(--bg2)", border: "1px solid var(--border)", color: "var(--text2)" }}
        >
          <RefreshCw size={13} style={{ animation: refreshing ? "spin 1s linear infinite" : "none" }} />
          {refreshing ? "Fetching…" : "Refresh"}
        </button>
      </div>

      {/* Ticker filter */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {["ALL", ...TICKERS].map(t => (
          <button
            key={t}
            onClick={() => setActiveTicker(t)}
            className="px-2.5 py-1 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: activeTicker === t ? "var(--accent)" : "var(--bg2)",
              color: activeTicker === t ? "#fff" : "var(--text2)",
              border: `1px solid ${activeTicker === t ? "var(--accent)" : "var(--border)"}`,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* News items */}
      {isLoading && (
        <div className="text-center py-12 text-sm" style={{ color: "var(--text2)" }}>Loading…</div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="rounded-xl p-10 text-center" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
          <Bell size={32} style={{ color: "var(--text2)", margin: "0 auto 12px" }} />
          <div className="font-semibold mb-1">No news yet</div>
          <div className="text-sm" style={{ color: "var(--text2)" }}>Click Refresh to fetch latest news for your portfolio</div>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 rounded-lg text-sm font-semibold"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            Fetch Now
          </button>
        </div>
      )}

      <div className="space-y-2">
        {items.map((item: any) => (
          <div
            key={item.id}
            className="rounded-xl p-4 flex items-start gap-3 cursor-pointer transition-all"
            style={{
              background: item.read ? "var(--bg2)" : "var(--bg3)",
              border: `1px solid ${item.read ? "var(--border)" : "var(--accent)"}`,
              opacity: item.read ? 0.7 : 1,
            }}
            onClick={() => {
              if (!item.read) markRead.mutate(item.id)
              if (item.url) window.open(item.url, "_blank")
            }}
          >
            {/* Ticker badge */}
            <div
              className="shrink-0 px-2 py-1 rounded-lg text-xs font-bold"
              style={{ background: "var(--bg)", color: "var(--accent2)", border: "1px solid var(--border)", minWidth: 72, textAlign: "center" }}
            >
              {item.ticker}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div
                  className="text-sm font-medium leading-snug"
                  style={{ color: item.read ? "var(--text2)" : "var(--text)" }}
                >
                  {item.headline}
                </div>
                <ExternalLink size={11} style={{ color: "var(--text2)", flexShrink: 0, marginTop: 2 }} />
              </div>
              <div className="flex items-center gap-3 mt-1.5">
                <div className="flex items-center gap-1">
                  <SentimentIcon s={item.sentiment} />
                  <span style={{ fontSize: 11, color: sentimentColor(item.sentiment) }}>
                    {item.sentiment}
                  </span>
                </div>
                <span style={{ fontSize: 11, color: "var(--text2)" }}>{item.source}</span>
                <span style={{ fontSize: 11, color: "var(--text2)" }}>{timeAgo(item.fetched_at)}</span>
                {!item.read && (
                  <span className="px-1.5 py-0.5 rounded text-xs font-bold"
                    style={{ background: "var(--accent)", color: "#fff" }}>NEW</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}
