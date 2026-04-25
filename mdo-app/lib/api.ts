import type {
  Status, Position, Holding, Funds, PnlStats,
  WatchlistItem, IntelItem, Urgency, IntelCategory,
  Tender, Lead, BidResult, GrokMessage,
  FeedItem, FeedsResponse
} from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`)
  return res.json()
}

// ── Trading ───────────────────────────────────────────────────────────
export const api = {
  status:    () => get<Status>("/api/status"),
  positions: () => get<{ positions: Position[] }>("/api/positions").then(r => r.positions),
  holdings:  () => get<{ holdings: Holding[] }>("/api/holdings").then(r => r.holdings),
  funds:     () => get<Funds>("/api/funds"),
  pnl:       () => get<PnlStats>("/api/pnl"),
  watchlist: () => get<{ watchlist: WatchlistItem[] }>("/api/watchlist").then(r => r.watchlist),
  sentiment: (ticker: string) => get<{ score: number; summary: string; confidence: number }>(`/api/sentiment/${ticker}`),
  health:    () => get<Record<string, boolean>>("/api/health"),

  // ── Intel Centre ─────────────────────────────────────────────────
  intel: {
    list: (params?: { urgency?: Urgency; category?: IntelCategory; status?: string }) => {
      const q = new URLSearchParams()
      if (params?.urgency)  q.set("urgency", params.urgency)
      if (params?.category) q.set("category", params.category)
      if (params?.status)   q.set("status", params.status)
      return get<{ items: IntelItem[] }>(`/api/intel?${q}`).then(r => r.items)
    },
    add: (item: { category: IntelCategory; title: string; body: string; urgency: Urgency; entity?: string; due_date?: string }) =>
      post<IntelItem>("/api/intel", item),
    resolve: (id: number) => post<IntelItem>(`/api/intel/${id}/resolve`, {}),
    acknowledge: (id: number) => post<IntelItem>(`/api/intel/${id}/acknowledge`, {}),
    snooze: (id: number, days: number) => post<IntelItem>(`/api/intel/${id}/snooze`, { days }),
  },

  // ── VWLR ─────────────────────────────────────────────────────────
  vwlr: {
    tenders: (params?: { buyer?: string; hot?: boolean }) => {
      const q = new URLSearchParams()
      if (params?.buyer) q.set("buyer", params.buyer)
      if (params?.hot)   q.set("hot", "true")
      return get<{ tenders: Tender[] }>(`/api/vwlr/tenders?${q}`).then(r => r.tenders)
    },
    leads: (priority?: string) => {
      const q = priority ? `?priority=${priority}` : ""
      return get<{ leads: Lead[] }>(`/api/vwlr/leads${q}`).then(r => r.leads)
    },
    followups: () => get<{ leads: Lead[] }>("/api/vwlr/followups").then(r => r.leads),
    bid: (buyer: string, volume: number, route: string, gate_price: number) =>
      get<BidResult>(`/api/vwlr/bid?buyer=${buyer}&volume=${volume}&route=${route}&gate_price=${gate_price}`),
  },

  // ── Grok ─────────────────────────────────────────────────────────
  grok: {
    ask: (question: string) => post<{ answer: string }>("/api/grok/ask", { question }),
  },

  // ── Live Trading Signals ──────────────────────────────────────────
  trading: {
    signals:  (status?: string) => get<{ signals: any[] }>(`/api/trading/signals${status ? "?status=" + status : ""}`).then(r => r.signals),
    confirm:  (id: number)      => post<any>(`/api/trading/signals/${id}/confirm`, {}),
    reject:   (id: number)      => post<any>(`/api/trading/signals/${id}/reject`, {}),
    add:      (sig: object)     => post<any>("/api/trading/signals", sig),
  },

  // ── Aditi Pools ───────────────────────────────────────────────────
  aditi: {
    pools: () => get<{ pools: any[] }>("/api/aditi/pools").then(r => r.pools),
    updatePool: (code: string, body: object) =>
      fetch(`${BASE}/api/aditi/pools/${code}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()),
  },

  // ── Entities ──────────────────────────────────────────────────────
  entities: {
    list:   (type?: string) => get<{ entities: any[] }>(`/api/entities${type ? "?type=" + type : ""}`),
    update: (id: number, body: object) =>
      fetch(`${BASE}/api/entities/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()),
  },

  // ── Compliance ────────────────────────────────────────────────────
  compliance: {
    filings: (entity?: string, status?: string) => {
      const q = new URLSearchParams()
      if (entity) q.set("entity", entity)
      if (status) q.set("status", status)
      return get<{ filings: any[] }>(`/api/compliance/filings?${q}`)
    },
    updateFiling: (id: number, body: object) =>
      fetch(`${BASE}/api/compliance/filings/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json()),
  },

  // ── Live Feeds ────────────────────────────────────────────────────
  feeds: {
    all:            () => get<FeedsResponse>("/api/feeds/all"),
    tenders:        () => get<{ items: FeedItem[]; count: number }>("/api/feeds/tenders"),
    gem:            () => get<{ items: FeedItem[]; count: number }>("/api/feeds/gem"),
    npa:            () => get<{ items: FeedItem[]; count: number }>("/api/feeds/npa"),
    singhvi:        () => get<{ calls: FeedItem[]; count: number }>("/api/singhvi"),
    singhviRefresh: () => post<{ calls: FeedItem[]; count: number; refreshed: boolean }>("/api/singhvi/refresh", {}),
  },

  // ── Market data ───────────────────────────────────────────────────
  market: {
    watchlist: () => get<{ watchlist: any[] }>("/api/market/watchlist"),
    indices:   () => get<{ indices: any[] }>("/api/market/indices"),
    quote:     (symbol: string) => get<any>(`/api/market/quote/${symbol}`),
  },

  // ── Morning Briefing ──────────────────────────────────────────────
  briefing: {
    today:    () => get<{ briefing: any; fresh: boolean }>("/api/briefing/today"),
    generate: () => post<{ briefing: any; error: string | null }>("/api/briefing/generate", {}),
  },
}
