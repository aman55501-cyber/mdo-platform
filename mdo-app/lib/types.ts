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

// ── WhatsApp intelligence (Business Intel) ────────────────────────────

export type WaClassification = "business" | "personal" | "unclear"
export type WaSignalStatus = "open" | "done" | "dismissed"

export interface WaStats {
  chats: { business: number; personal: number; unclear: number }
  signals_open_by_kind: Record<string, number>
  msgs_7d: number
  last_pulse_at: string | null
}

export interface WaChat {
  jid: string
  account: string
  name: string
  kind: "group" | "dm"
  classification: WaClassification
  entity: string | null
  confidence: number | null
  reason: string | null
  decided_by: string | null
  last_seen: string | null
  msg_count: number
  participants: number | null
}

export interface WaSignal {
  id: number
  created_at: string
  entity: string | null
  chat_name: string | null
  kind: string
  counterparty: string | null
  amount: number | null
  currency: string | null
  due_date: string | null
  summary: string
  evidence_ids: number[]
  confidence: number | null
  status: WaSignalStatus
  owner: string | null
}

export interface WaRegisterItem {
  id: number
  category: string
  entity: string | null
  item: string
  value: number | string | null
  unit: string | null
  as_of: string | null
  source: string | null
  status: string | null
  notes: string | null
  updated_at: string | null
}

export interface WaRegisterInput {
  category: string
  entity: string
  item: string
  value: string | number | null
  unit: string
  as_of: string
  source: string
  notes: string
}

export interface WaPulseEfficiencyRow {
  chat: string
  sender: string
  median_reply_min: number | null
  unanswered_24h: number | null
}

export interface WaPulseNextStep {
  step: string
  owner: string | null
  eta: string | null
  cites: number[]
}

export interface WaPulseReport {
  sales_gap: unknown[]
  efficiency: WaPulseEfficiencyRow[]
  bottlenecks: unknown[]
  register_changes: unknown[]
  next_steps: WaPulseNextStep[]
}

export interface WaPulse {
  id: number
  period_start: string
  period_end: string
  summary: string
  report: Partial<WaPulseReport> | null
}

// ── Share buy/sell levels (levels-alert bot) ─────────────────────────────
export interface ShareLevel {
  id: number
  ticker: string
  exchange: string
  buy_level: number | null
  sell_level: number | null
  best_entry?: number | null
  note: string
  active: boolean
  source: string
  created_at: string
  updated_at: string
  ltp: number | null
  buy_distance_pct: number | null
  sell_distance_pct: number | null
  at_buy: boolean
  at_sell: boolean
  nearest_pct: number | null
  held_by?: { holder: string; qty: number | null }[]
  held_text?: string
  line: string
}

export interface LevelHit {
  ticker: string
  side: "buy" | "sell"
  level: number
  ltp: number
  hit_at: string
  trading_day: string
}

export interface LevelsResponse {
  levels: ShareLevel[]
  count: number
  active: number
  ltp_as_of: string | null
  hits_today: LevelHit[]
  market_open: boolean
  as_of: string
}

// ── Share Master (share-master-daily bot) ──────────────────────────
export interface PortfolioRow {
  snap_date: string
  account: string
  ticker: string
  company?: string
  qty: number | null
  avg_price: number | null
  ltp: number | null
  invested: number | null
  value: number | null
  pnl: number | null
  pnl_pct: number | null
  weight_pct: number | null
  buy_level?: number | null
  sell_level?: number | null
  flag: string
  source: string
}

export interface PortfolioAccountStatus {
  account: string
  ok: boolean
  reason: string
  note: string
  n: number
  snap_date: string | null
  fetched_at?: string | null
  source?: string
}

export interface MausajiCall {
  id: number
  call_date: string
  ticker: string
  action: "BUY" | "SELL" | "HOLD" | "AVOID"
  entry: number | null
  target: number | null
  stop: number | null
  timeframe: string
  quote: string
  message_id: number | null
  chat_name: string
  extracted_at: string
  ltp_at_call: number | null
  status: "open" | "hit_target" | "hit_stop" | "expired"
  last_ltp: number | null
  last_checked: string | null
}

export interface ShareMasterSummary {
  as_of: string
  accounts: { account: string; n: number; invested: number; value: number; pnl: number; pnl_pct: number | null; flags: number; ok: boolean; note: string }[]
  total: { n: number; invested: number; value: number; pnl: number; pnl_pct: number | null }
  top_gainers: { account: string; ticker: string; pnl: number; pnl_pct: number }[]
  top_losers: { account: string; ticker: string; pnl: number; pnl_pct: number }[]
  calls: { open: number; hit_target: number; hit_stop: number; expired: number; total: number }
  levels: number
  flagged: number
  unverified: number
  stale_accounts: string[]
  positions: { accounts: { account: string; n: number; pl: number; premium_left: number; options: number; nearest_expiry: string | null; nearest_days: number | null }[]; n: number; pl: number; expiring_7d: number }
}

export interface SharePosition {
  account: string
  instrument: string
  side: "BUY" | "SELL"
  qty: number | null
  avg: number | null
  ltp: number | null
  pl: number | null
  product: string
  as_of: string
  source: string
  kind: "option" | "future" | "equity"
  expiry: string | null
  days_to_expiry: number | null
  premium_left: number | null
}

export interface ShareMasterResponse {
  as_of: string
  portfolio: { rows: PortfolioRow[]; accounts: PortfolioAccountStatus[]; snap_date: string | null }
  calls: MausajiCall[]
  levels: ShareLevel[]
  positions: SharePosition[]
  positions_source: string
  summary: ShareMasterSummary
  vault_file: string
  mausaji_chat: string
}

export interface PortfolioImportResult {
  holder: string
  stored: number
  uploaded_at: string
  count: number
  unverified: string[]
  skipped: { row: number; code?: string; reason: string }[]
  holdings: { ticker: string; hdfc_code: string; company: string; qty: number; avg_price: number | null; cmp: number | null; pnl_pct: number | null; ticker_verified: boolean }[]
}

// ── WhatsApp sweep (wa-sweep bot): Mausaji share lines, site-group bottlenecks, silence ──
export type WaSweepKind = "call" | "mention" | "bottleneck" | "silence"

export interface WaSweepFlag {
  id: number
  chat_jid: string
  chat_name: string
  account: string
  message_id: number | null
  sender: string
  kind: WaSweepKind
  ticker: string
  text: string
  detail: { tickers?: string[]; call?: Record<string, number | string | null>; words?: string[]; silent_hours?: number }
  msg_at: string
  day: string
  created_at: string
  status: "open" | "ack"
  pushed_at: string | null
  acked_at: string | null
}

export interface WaSweepFlagsResponse {
  flags: WaSweepFlag[]
  count: number
  open: number
  as_of: string
}

export interface WaSweepChat {
  jid: string
  name: string
  account: string
  kind: string
  mode: "mausaji" | "ops"
  priority: "high" | "normal" | "low"
  watermark: number
  last_push_at: string | null
  last_message_at: string | null
  msg_count: number
}

export interface WaSweepChatsResponse {
  chats: WaSweepChat[]
  count: number
  mausaji_chat: string
  mausaji_found: boolean
  watch_chats: string[]
  groups_regex: string
  idle_hours: number
  groups_seen: string[]
}

// ── Compliance (compliance-reminder bot): statutory calendar + 7-day reminders ──
export type ComplianceKind = "pvt_ltd" | "llp" | "partnership" | "proprietorship" | "individual"
export type ComplianceStage = "week" | "eve" | "day"

export interface ComplianceReminder {
  id: number
  entity_or_group: string
  item_id: string
  item: string
  due_date: string
  remind_on: string
  stage: ComplianceStage
  sent_at: string | null
  status: "queued" | "sent" | "done"
  done_at: string | null
}

export interface ComplianceUpcomingItem {
  item_id: string
  item: string
  label: string
  due: string                       // ISO date
  cadence: string
  source: string
  extendable: boolean
  payment: boolean
  group: string
  targets: string[]                 // entity names, or the one group label
  level: "entity" | "group"
  days_left: number
  stage: ComplianceStage | null
  reminders: ComplianceReminder[]
  done_for: string[]
  done: boolean
}

export interface ComplianceUpcomingResponse {
  as_of: string
  today: string
  days: number
  items: ComplianceUpcomingItem[]
  entities_loaded: boolean
  entity_count: number
  level: "entity" | "group"
  footer: string
  note: string
}

export interface ComplianceEntity {
  id: number
  name: string
  kind: ComplianceKind
  gst_registered: boolean
  gst_qrmp: boolean
  tds_deductor: boolean
  audit_case: boolean
  pf_esi: boolean
  active: boolean
  source: string
  notes: string
}

export interface ComplianceEntitiesResponse {
  entities: ComplianceEntity[]
  kinds: ComplianceKind[]
  loaded: boolean
  note: string
}

// ── Mail (mail-reader bot): IMAP intake of statements, contract notes and tender results ──
export type MailCategory = "broker-statement" | "contract-note" | "exchange-balance" | "bank-statement" | "tender-result"
  | "grok-tender"
  | "mf-transaction" | "insurance" | "evoting" | "other"
export type MailStatus = "new" | "seen" | "ack"

export interface MailMessage {
  id: number
  uid: number
  message_id: string
  from_addr: string
  sender: string                    // short label (SIB, HDFC Sec, Angel One, bidsnrfp …)
  subject: string
  received_at: string | null        // ISO UTC
  category: MailCategory
  entity_hint: string               // exact name matches only, "" when none
  attachment_names: string[]
  attachment_locked: boolean        // encrypted PDF — stored, never opened
  stored_path: string               // relative to the vault, "" when nothing stored
  summary: string
  status: MailStatus
  actionable: boolean
  pushed_at: string | null
  acked_at: string | null
}

export interface MailRecentResponse {
  items: MailMessage[]
  count: number
  days: number
  category: string
  status: string
  as_of: string
}

export interface MailStatsResponse {
  days: number
  as_of: string
  total: number
  locked: number
  by_category: Record<string, { count: number; locked: number; actionable: number; new: number }>
  categories: MailCategory[]
  actionable: MailMessage[]         // the last 10 actionable rows, newest first
  configured: boolean
  host: string
  mailbox: string
  state: { last_uid: number; last_run_at: string | null; last_line: string; runs: number }
  note: string
}

// ── Corporate actions (corp-actions bot): NSE announcements + corporate actions for every held/watched ticker ──
export type CorpActionKind = "results" | "dividend" | "buyback" | "bonus" | "split" | "rights" | "agm" | "board_meeting" | "record_date" | "other"

export interface CorpAction {
  id: number
  ticker: string
  kind: CorpActionKind
  subject: string
  ex_date: string                   // ISO date or ""
  record_date: string               // ISO date or ""
  announced_at: string              // ISO datetime (IST)
  url: string
  source: "announcement" | "action"
  company: string
  pushed_at: string | null
  created_at: string
  date: string                      // ex_date || record_date || announced day
  held_by: { holder: string; qty: number | null }[]   // Directive 18
  held_text: string                 // "Ashok 3000, Aman 500" or "nobody"
}

export interface CorpActionsRun {
  id: number
  ran_at: string
  tickers: number
  new: number
  failed: number
  nse_ok: number
  line: string
  pushed: number
}

export interface CorpActionsUpcomingResponse {
  as_of: string
  today: string
  days: number
  items: CorpAction[]
  last_run: CorpActionsRun | null
  tickers_watched: number
}

// ── Tenders direct (tenders-direct bot): public tender listings read from the buyers' own pages ──
export type TenderDirectSource = "secl" | "secl-etender" | "coalindia" | "ntpc" | "eprocure" | "mstc"

export interface TenderDirect {
  id: number
  source: TenderDirectSource
  tender_id: string                 // the site's reference, else "h:<hash>"
  title: string
  org: string
  published: string                 // ISO date or ""
  due: string                       // ISO date or ""
  value_text: string                // as the page wrote it, "" when unstated
  url: string
  matched: boolean
  keywords: string[]                // the TENDERS_KEYWORDS words that matched
  category: string                  // Coal washing | RCR | Coal transport | Loading | Mining services | Other | ""
  first_seen: string
  last_seen: string
  pushed_at: string | null
  pipeline_posted: boolean
}

export interface TenderDirectSiteState {
  label: string
  url: string
  ok: boolean
  status: number
  rows: number
  matched: number
  new: number
  reason: string                    // "blocked (HTTP 403 — …)", "timeout after 25s", "" when fine
}

export interface TenderDirectRun {
  id: number
  ran_at: string
  sites_ok: number
  sites_failed: number
  pages: number
  rows: number
  matched: number
  new: number
  pushed: number
  line: string
  sites: Record<string, TenderDirectSiteState>
}

export interface TendersDirectUpcomingResponse {
  items: TenderDirect[]             // matched, due inside the window, by due date
  undated: TenderDirect[]           // matched rows the page gave no closing date for
  count: number
  days: number
  as_of: string
  from: string
  until: string
  state: TenderDirectRun | null
  keywords: string[]
  min_value_cr: number
  sites: { key: TenderDirectSource; label: string; url: string }[]
}

export interface TendersDirectStatsResponse {
  as_of: string
  total: number
  matched: number
  by_source: Record<string, { label: string; url: string; rows: number; matched: number }>
  keywords: string[]
  min_value_cr: number
  runs: number
  state: TenderDirectRun | null
}

// ── Voice notes (voice bot): WhatsApp audio transcribed on the VPS with faster-whisper ──
export type VoiceStatus = "pending" | "done" | "failed"

export interface VoiceMedia {
  id: number
  message_id: string
  account: string
  chat_jid: string
  chat_name: string
  chat_kind: "group" | "dm"
  sender: string
  from_me: boolean
  received_at: string | null        // ISO UTC
  mimetype: string
  path: string                      // relative to the voice dir: <date>/<message_id>.ogg
  bytes: number
  duration: number                  // seconds, as the bridge reported
  transcript: string
  language: string                  // Whisper's detected language, "" until done
  status: VoiceStatus
  error: string                     // "no speech detected", a decode error, ""
  seconds: number                   // processing time
  attempts: number
  store_msg_id: number | null       // whatsapp_messages.id of the transcript row
  created_at: string
  done_at: string | null
}

export interface VoiceRun {
  id: number
  ran_at: string
  transcribed: number
  pending: number
  failed: number
  model: string
  avg_s: number
  line: string
}

export interface VoiceStatsResponse {
  as_of: string
  installed: boolean                // faster-whisper importable in the backend image
  model: string
  counts: Record<VoiceStatus, number>
  last_24h: number
  transcripts: VoiceMedia[]         // the last 20 done rows, newest first
  state: VoiceRun | null
  voice_dir: string
  model_dir: string
}

export interface VoiceRecentResponse {
  items: VoiceMedia[]
  count: number
  status: string
  as_of: string
}

// ── credit-guard (GET /api/credits) ──
export interface CreditsStatus {
  as_of: string
  plan_state: "ok" | "tight" | "blocked" | "overage" | "unknown"
  plan: { at: string; session: string; status: string; limit_type: string; resets_at: number | null; overage: number } | null
  api: {
    month: string; month_to_date_inr: number; calls: number; cap_inr: number | null; pct_of_cap: number | null
    forecast_inr: number; mode: "normal" | "economy" | "paused"; mode_reason: string
    by_bot: { bot: string; model: string; inr: number; calls: number }[]
  }
  policy: { state: string; workers: "yes" | "no"; max_workers: number; models: { read: string; build: string; hard: string; cos: string }; fleet_api_mode: string }
  line: string
  last_run: { at: string; status: string; line: string } | null
}
