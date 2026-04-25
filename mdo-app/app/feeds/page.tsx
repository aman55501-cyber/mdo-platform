"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { FeedItem, FeedSource, FeedUrgency } from "@/lib/types"
import {
  Rss, ExternalLink, RefreshCw, TrendingUp, TrendingDown,
  Building2, Landmark, FileText, ShoppingCart, Calendar,
  IndianRupee, MapPin, Clock, ChevronDown, ChevronRight
} from "lucide-react"

// ── source config ─────────────────────────────────────────────────────────────
const SOURCE_META: Record<string, { label: string; color: string; bg: string; siteUrl: string; icon: typeof Rss }> = {
  singhvi:      { label: "Singhvi",      color: "#a78bfa", bg: "rgba(167,139,250,0.12)", siteUrl: "https://x.com/AnilSinghvi_",       icon: TrendingUp  },
  tender247:    { label: "Tender247",    color: "#38bdf8", bg: "rgba(56,189,248,0.12)",  siteUrl: "https://tender247.com",             icon: FileText    },
  gem:          { label: "GeM",          color: "#34d399", bg: "rgba(52,211,153,0.12)",  siteUrl: "https://gem.gov.in",                icon: ShoppingCart },
  nclt:         { label: "NCLT/IBBI",   color: "#fb923c", bg: "rgba(251,146,60,0.12)",  siteUrl: "https://ibbi.gov.in",               icon: Landmark    },
  bank_auction: { label: "Bank Auction", color: "#f87171", bg: "rgba(248,113,113,0.12)", siteUrl: "https://bankeauctions.com",          icon: Building2   },
  hdfc:         { label: "HDFC",         color: "#6366f1", bg: "rgba(99,102,241,0.12)",  siteUrl: "https://hdfcsky.hdfcsec.com",        icon: TrendingUp  },
}

const URGENCY_COLOR: Record<FeedUrgency, string> = {
  critical: "var(--red)",
  high:     "var(--amber)",
  medium:   "var(--cyan)",
  low:      "var(--text2)",
}

// ── helpers ───────────────────────────────────────────────────────────────────
function daysUntil(dateStr: string | null): string | null {
  if (!dateStr) return null
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr
  const days = Math.ceil((d.getTime() - Date.now()) / 86400000)
  if (days < 0) return "Overdue"
  if (days === 0) return "Today"
  if (days === 1) return "Tomorrow"
  return `${days}d left`
}

// ── feed card ──────────────────────────────────────────────────────────────────
function FeedCard({ item }: { item: FeedItem }) {
  const [open, setOpen] = useState(false)
  const meta = SOURCE_META[item.source] || SOURCE_META.tender247
  const Icon = meta.icon
  const urgColor = URGENCY_COLOR[item.urgency]
  const due = daysUntil(item.due_date)
  const dueColor = due === "Overdue" || due === "Today" || due === "Tomorrow" ? "var(--red)" : due?.endsWith("d left") && parseInt(due) <= 3 ? "var(--amber)" : "var(--text2)"

  // Extra links for Singhvi calls
  const isStockCall = item.category === "stock_call"
  const m = item.metadata as Record<string, string | number | null>

  return (
    <div
      className="rounded-xl border overflow-hidden transition-all"
      style={{ background: "var(--bg2)", borderColor: urgColor + "50" }}
    >
      <div className="px-4 py-3">
        {/* Top row: source badge + urgency + title */}
        <div className="flex items-start gap-3">
          <div className="flex flex-col items-center gap-1 shrink-0 mt-0.5">
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
              style={{ background: meta.bg, color: meta.color }}>
              {meta.label}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="font-semibold text-sm leading-snug flex-1">{item.title}</div>
              <button onClick={() => setOpen(v => !v)} className="shrink-0 mt-0.5" style={{ color: "var(--text2)" }}>
                {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              </button>
            </div>
            <div className="text-xs mt-0.5 leading-relaxed" style={{ color: "var(--text2)" }}>{item.summary}</div>
          </div>
        </div>

        {/* Meta chips */}
        <div className="flex flex-wrap items-center gap-2 mt-2 ml-0">
          {item.urgency !== "low" && (
            <span className="text-xs px-1.5 py-0.5 rounded font-semibold uppercase"
              style={{ color: urgColor, background: urgColor + "18" }}>
              {item.urgency}
            </span>
          )}
          {item.amount && (
            <span className="flex items-center gap-1 text-xs" style={{ color: "var(--green)" }}>
              <IndianRupee size={10} />{item.amount}
            </span>
          )}
          {due && (
            <span className="flex items-center gap-1 text-xs" style={{ color: dueColor }}>
              <Calendar size={10} />{due}
            </span>
          )}
          {item.entity && (
            <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text2)" }}>
              <Building2 size={10} />{item.entity}
            </span>
          )}
          {(m.location as string) && (
            <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text2)" }}>
              <MapPin size={10} />{m.location as string}
            </span>
          )}
        </div>

        {/* Expanded detail */}
        {open && (
          <div className="mt-3 space-y-2">
            {isStockCall && (
              <div className="grid grid-cols-3 gap-2">
                {m.entry_price && <div className="px-3 py-2 rounded-lg text-xs" style={{ background: "var(--bg3)" }}>
                  <div style={{ color: "var(--text2)" }}>Entry</div>
                  <div className="font-bold">₹{Number(m.entry_price).toLocaleString("en-IN")}</div>
                </div>}
                {m.stop_loss && <div className="px-3 py-2 rounded-lg text-xs" style={{ background: "var(--bg3)" }}>
                  <div style={{ color: "var(--text2)" }}>Stop Loss</div>
                  <div className="font-bold" style={{ color: "var(--red)" }}>₹{Number(m.stop_loss).toLocaleString("en-IN")}</div>
                </div>}
                {m.target && <div className="px-3 py-2 rounded-lg text-xs" style={{ background: "var(--bg3)" }}>
                  <div style={{ color: "var(--text2)" }}>Target</div>
                  <div className="font-bold" style={{ color: "var(--green)" }}>₹{Number(m.target).toLocaleString("en-IN")}</div>
                </div>}
              </div>
            )}
            {m.case_no && <div className="text-xs" style={{ color: "var(--text2)" }}>Case: {m.case_no as string}</div>}
            {m.liquidator && <div className="text-xs" style={{ color: "var(--text2)" }}>Liquidator: {m.liquidator as string}</div>}
            {m.bid_id && <div className="text-xs" style={{ color: "var(--text2)" }}>Bid ID: {m.bid_id as string}</div>}
            {m.tender_id && <div className="text-xs" style={{ color: "var(--text2)" }}>Tender ID: {m.tender_id as string}</div>}
          </div>
        )}
      </div>

      {/* Action bar — direct links */}
      <div className="px-4 pb-3 flex flex-wrap gap-2">
        <a href={item.url} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium"
          style={{ background: meta.bg, color: meta.color }}>
          <ExternalLink size={11} />
          {isStockCall ? "NSE Quote" : item.category === "gem_bid" ? "View on GeM" : item.category === "npa_auction" ? "View Case" : "View Tender"}
        </a>

        {isStockCall && m.tradingview_url && (
          <a href={m.tradingview_url as string} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
            style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            <ExternalLink size={11} /> TradingView
          </a>
        )}
        {isStockCall && m.x_url && (
          <a href={m.x_url as string} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
            style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            <ExternalLink size={11} /> X post
          </a>
        )}
        {item.category === "npa_auction" && (
          <>
            <a href="https://ibbi.gov.in" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
              style={{ background: "var(--bg3)", color: "var(--text2)" }}>
              <ExternalLink size={11} /> IBBI
            </a>
            <a href="https://nclt.gov.in" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
              style={{ background: "var(--bg3)", color: "var(--text2)" }}>
              <ExternalLink size={11} /> NCLT
            </a>
          </>
        )}
        {item.category === "gem_bid" && (
          <a href="https://bidplus.gem.gov.in/all-bids" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
            style={{ background: "var(--bg3)", color: "var(--text2)" }}>
            <ExternalLink size={11} /> All GeM Bids
          </a>
        )}
      </div>
    </div>
  )
}

// ── source summary bar ─────────────────────────────────────────────────────────
function SourceBar({ sources, active, setActive }: {
  sources: Record<string, number>
  active: string
  setActive: (s: string) => void
}) {
  const all = [
    { key: "all",      label: "All",           color: "var(--text2)"  },
    { key: "singhvi",  label: "📈 Singhvi",     color: "#a78bfa"       },
    { key: "tender247",label: "📋 Tender247",   color: "#38bdf8"       },
    { key: "gem",      label: "🏛 GeM",         color: "#34d399"       },
    { key: "nclt",     label: "⚖️ NPA/NCLT",   color: "#fb923c"       },
    { key: "bank_auction", label: "🏦 Auctions", color: "#f87171"     },
  ]
  return (
    <div className="flex flex-wrap gap-2">
      {all.map(({ key, label, color }) => {
        const count = key === "all" ? Object.values(sources).reduce((a, b) => a + b, 0) : (sources[key] ?? 0)
        return (
          <button key={key} onClick={() => setActive(key)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors"
            style={{
              borderColor: active === key ? color : "var(--border)",
              background: active === key ? color + "18" : "var(--bg2)",
              color: active === key ? color : "var(--text2)",
            }}>
            {label}
            {count > 0 && <span className="text-xs opacity-70">({count})</span>}
          </button>
        )
      })}
    </div>
  )
}

// ── quick links ────────────────────────────────────────────────────────────────
const QUICK_LINKS = [
  { label: "Tender247",          url: "https://tender247.com",                          color: "#38bdf8" },
  { label: "GeM Bids",           url: "https://bidplus.gem.gov.in/all-bids",            color: "#34d399" },
  { label: "IBBI Liquidations",  url: "https://ibbi.gov.in/home/public-announcement",   color: "#fb923c" },
  { label: "NCLT Cases",         url: "https://nclt.gov.in",                            color: "#fb923c" },
  { label: "Bank e-Auctions",    url: "https://bankeauctions.com",                      color: "#f87171" },
  { label: "SARFAESI Auctions",  url: "https://sarfaesi.com",                           color: "#f87171" },
  { label: "AnilSinghvi X",      url: "https://x.com/AnilSinghvi_",                    color: "#a78bfa" },
  { label: "NSE India",          url: "https://www.nseindia.com",                       color: "#6366f1" },
  { label: "HDFC SKY",           url: "https://hdfcsky.hdfcsec.com",                   color: "#6366f1" },
]

// ── main ──────────────────────────────────────────────────────────────────────
export default function FeedsPage() {
  const [activeSource, setActiveSource] = useState("all")
  const qc = useQueryClient()

  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["feeds_all"],
    queryFn: api.feeds.all,
    refetchInterval: 5 * 60_000,  // refresh every 5 min
    staleTime: 4 * 60_000,
  })

  const refresh = useMutation({
    mutationFn: api.feeds.singhviRefresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feeds_all"] }),
  })

  const items = data?.items ?? []
  const sources = data?.sources ?? {}

  const filtered = activeSource === "all"
    ? items
    : items.filter(i => i.source === activeSource)

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    : null

  return (
    <div className="space-y-5 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Rss size={20} style={{ color: "var(--accent2)" }} />
          <h1 className="text-2xl font-bold">Live Feeds</h1>
          {items.length > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
              {items.length} items
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastUpdated && (
            <span className="text-xs flex items-center gap-1" style={{ color: "var(--text2)" }}>
              <Clock size={11} /> {lastUpdated}
            </span>
          )}
          <button
            onClick={() => { qc.invalidateQueries({ queryKey: ["feeds_all"] }); refresh.mutate() }}
            disabled={isLoading || refresh.isPending}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border"
            style={{ borderColor: "var(--border)", background: "var(--bg2)", color: "var(--text2)" }}>
            <RefreshCw size={12} className={isLoading || refresh.isPending ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Quick links */}
      <div className="rounded-xl border p-3" style={{ background: "var(--bg2)", borderColor: "var(--border)" }}>
        <div className="text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: "var(--text2)" }}>Quick Links</div>
        <div className="flex flex-wrap gap-2">
          {QUICK_LINKS.map(({ label, url, color }) => (
            <a key={label} href={url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border transition-colors"
              style={{ borderColor: color + "40", color, background: color + "10" }}>
              <ExternalLink size={10} /> {label}
            </a>
          ))}
        </div>
      </div>

      {/* Source filter */}
      <SourceBar sources={sources} active={activeSource} setActive={setActiveSource} />

      {/* Feed items */}
      {isLoading && (
        <div className="text-center py-16">
          <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: "var(--text2)" }} />
          <div className="text-sm" style={{ color: "var(--text2)" }}>Fetching from Tender247, GeM, IBBI, Singhvi…</div>
          <div className="text-xs mt-1" style={{ color: "var(--text2)" }}>This may take 20–30 seconds (Grok web search)</div>
        </div>
      )}

      {isError && (
        <div className="rounded-xl border p-6 text-center" style={{ background: "var(--bg2)", borderColor: "var(--red)" }}>
          <div className="text-sm font-medium" style={{ color: "var(--red)" }}>Backend not connected</div>
          <div className="text-xs mt-1" style={{ color: "var(--text2)" }}>
            Run: <code className="px-1.5 py-0.5 rounded" style={{ background: "var(--bg3)" }}>python mdo_server.py</code> from misc/vega/
          </div>
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="text-center py-12 text-sm" style={{ color: "var(--text2)" }}>No items found</div>
      )}

      <div className="space-y-3">
        {filtered.map(item => <FeedCard key={item.id} item={item} />)}
      </div>
    </div>
  )
}
