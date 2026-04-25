// ── API response types ────────────────────────────────────────────────

export interface Status {
  time: string
  market: "OPEN" | "PRE-MARKET" | "CLOSED"
  broker_authenticated: boolean
  active_positions: number
  watchlist: string[]
}

export interface Position {
  ticker: string
  side: "BUY" | "SELL"
  quantity: number
  entry_price: number
  ltp: number
  pnl: number
  pnl_pct: number
  stop_loss?: number
  target?: number
}

export interface Holding {
  ticker: string
  quantity: number
  average_price: number
  ltp: number
  current_value: number
  pnl: number
  pnl_pct: number
}

export interface Funds {
  available: number
  used_margin: number
  total: number
}

export interface PnlStats {
  total_pnl: number
  realized_pnl: number
  unrealized_pnl: number
  trades_today: number
  win_rate: number
  best_trade?: string
  worst_trade?: string
}

export interface WatchlistItem {
  ticker: string
  ltp: number | null
  sentiment_score: number | null
  sentiment_confidence: number | null
  sentiment_summary?: string
}

// ── Intel Centre ──────────────────────────────────────────────────────

export type Urgency = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
export type IntelCategory = "trading" | "vwlr" | "compliance" | "wealth" | "market"
export type IntelStatus = "open" | "acknowledged" | "resolved" | "snoozed"

export interface IntelItem {
  id: number
  category: IntelCategory
  source: string
  urgency: Urgency
  entity: string
  title: string
  body: string
  due_date?: string
  status: IntelStatus
  created_at: string
  updated_at: string
}

// ── VWLR ─────────────────────────────────────────────────────────────

export interface Tender {
  id: number
  tender_id: string
  title: string
  buyer: string
  volume: number
  unit: string
  due_date?: string
  status: string
  eligibility_score: number
  url?: string
  location?: string
}

export interface Lead {
  id: number
  company: string
  contact_person: string
  phone: string
  location: string
  distance_km: number
  potential_volume: string
  status: string
  priority: "High" | "Medium" | "Low"
  tender_score: number
  next_followup?: string
  notes?: string
}

export interface BidResult {
  buyer: string
  volume_mt: number
  route: string
  gate_price: number
  fois_freight: number
  landed_cost: number
  volume_discount_pct: number
  suggested_bid: number
  margin_pct: number
  total_revenue: number
  total_margin: number
}

// ── Grok ─────────────────────────────────────────────────────────────

export interface GrokMessage {
  role: "user" | "assistant"
  content: string
  timestamp: string
}

// ── External Feeds ────────────────────────────────────────────────────

export type FeedSource = "tender247" | "gem" | "nclt" | "bank_auction" | "singhvi"
export type FeedCategory = "tender" | "gem_bid" | "npa_auction" | "stock_call"
export type FeedUrgency = "critical" | "high" | "medium" | "low"

export interface FeedItem {
  id: string
  source: FeedSource
  category: FeedCategory
  title: string
  summary: string
  url: string
  urgency: FeedUrgency
  amount: string | null
  due_date: string | null
  entity: string | null
  fetched_at: string
  metadata: Record<string, unknown>
}

export interface FeedsResponse {
  items: FeedItem[]
  count: number
  sources?: Record<string, number>
}

// ── SSE events ────────────────────────────────────────────────────────

export interface MarketEvent {
  type: "market"
  ticker: string
  ltp: number
  timestamp: string
}

export interface SentimentEvent {
  type: "sentiment"
  ticker: string
  score: number
  confidence: number
  summary: string
}

export interface SignalEvent {
  type: "signal"
  id: string
  ticker: string
  action: string
  entry_price: number
  target_price: number
  stop_loss: number
  quantity: number
  rationale: string
}

export type LiveEvent = MarketEvent | SentimentEvent | SignalEvent
