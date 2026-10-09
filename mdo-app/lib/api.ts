import type {
  Status, Position, Holding, Funds, PnlStats,
  WatchlistItem, IntelItem, Urgency, IntelCategory,
  Tender, Lead, BidResult, GrokMessage,
  FeedItem, FeedsResponse,
  WaStats, WaChat, WaSignal, WaRegisterItem, WaRegisterInput, WaPulse,
  WaClassification, WaSignalStatus,
  LevelsResponse,
  ShareMasterResponse, PortfolioImportResult,
  WaSweepFlagsResponse, WaSweepChatsResponse, WaSweepChat,
  ComplianceUpcomingResponse, ComplianceEntitiesResponse, ComplianceEntity,
  MailRecentResponse, MailStatsResponse,
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

  // ── WhatsApp intelligence (Business Intel) ────────────────────────
  wa: {
    stats: () => get<WaStats>("/api/wa/stats"),
    chats: (classification?: WaClassification) =>
      get<{ chats: WaChat[] }>(`/api/wa/chats${classification ? "?classification=" + classification : ""}`).then(r => r.chats ?? []),
    classify: (body: { jid: string; classification: "business" | "personal"; entity: string }) =>
      post<{ ok: boolean }>("/api/wa/chats/classify", { ...body, decided_by: "aman" }),
    signals: (params?: { status?: WaSignalStatus; entity?: string; kind?: string; limit?: number }) => {
      const q = new URLSearchParams()
      q.set("status", params?.status ?? "open")
      if (params?.entity) q.set("entity", params.entity)
      if (params?.kind)   q.set("kind", params.kind)
      q.set("limit", String(params?.limit ?? 200))
      return get<{ signals: WaSignal[] }>(`/api/wa/signals?${q}`).then(r => r.signals ?? [])
    },
    setSignalStatus: (id: number, status: WaSignalStatus) =>
      post<{ ok: boolean }>(`/api/wa/signals/${id}/status`, { status }),
    register: (category?: string) =>
      get<{ items: WaRegisterItem[] }>(`/api/wa/register${category ? "?category=" + encodeURIComponent(category) : ""}`).then(r => r.items ?? []),
    addRegister: (item: WaRegisterInput) => post<{ ok: boolean; id: number }>("/api/wa/register", item),
    pulseLatest: () => get<{ pulse: WaPulse | null }>("/api/wa/pulse/latest").then(r => r.pulse ?? null),
  },

  // ── Share buy/sell levels (levels-alert bot) ──────────────────────
  levels: {
    list:     () => get<LevelsResponse>("/api/levels"),
    snapshot: () => get<{ text: string; ltp_as_of: string | null; count: number; hits_today: number }>("/api/levels/snapshot"),
    set:      (item: { ticker: string; buy_level?: number | null; sell_level?: number | null; note?: string; active?: boolean }) =>
      post<LevelsResponse & { upserted: string[] }>("/api/levels", item),
    remove:   (ticker: string) =>
      fetch(`${BASE}/api/levels/${encodeURIComponent(ticker)}`, { method: "DELETE" }).then(r => {
        if (!r.ok) throw new Error(`API /api/levels/${ticker} → ${r.status}`)
        return r.json() as Promise<LevelsResponse & { deleted: string }>
      }),
  },

  // ── WhatsApp sweep (wa-sweep bot): open flags + ack, the watched chats ──
  waSweep: {
    flags:       (status: "open" | "ack" | "" = "open") => get<WaSweepFlagsResponse>(`/api/wa/sweep/flags?status=${status}`),
    ack:         (id: number) => post<{ ok: boolean; id: number; status: string }>(`/api/wa/sweep/flags/${id}/ack`, {}),
    chats:       () => get<WaSweepChatsResponse>("/api/wa/sweep/chats"),
    setPriority: (jid: string, priority: WaSweepChat["priority"]) =>
      post<{ ok: boolean; jid: string; priority: string }>(`/api/wa/sweep/chats/${encodeURIComponent(jid)}/priority`, { priority }),
  },

  // ── Compliance (compliance-reminder bot): statutory calendar, next 30 days, entity list ──
  complianceCalendar: {
    upcoming:  (days = 30) => get<ComplianceUpcomingResponse>(`/api/compliance/upcoming?days=${days}`),
    entities:  () => get<ComplianceEntitiesResponse>("/api/compliance/entities"),
    upsertEntities: (items: Partial<ComplianceEntity>[]) =>
      post<{ upserted: string[]; entities: ComplianceEntity[] }>("/api/compliance/entities", items),
    done:      (id: number) => post<{ ok: boolean; id: number; status: string }>(`/api/compliance/reminders/${id}/done`, {}),
  },

  // ── Mail (mail-reader bot): 7-day counts by category, the actionable rows, ack ──
  mail: {
    stats:  (days = 7) => get<MailStatsResponse>(`/api/mail/stats?days=${days}`),
    recent: (days = 7, category = "") =>
      get<MailRecentResponse>(`/api/mail/recent?days=${days}${category ? `&category=${encodeURIComponent(category)}` : ""}`),
    ack:    (id: number) => post<{ ok: boolean; id: number; status: string }>(`/api/mail/${id}/ack`, {}),
  },

  // ── Share Master (share-master-daily bot): one workbook, Portfolio · Mausaji Calls · Levels ──
  shareMaster: {
    get:     () => get<ShareMasterResponse>("/api/share-master"),
    xlsxUrl: `${BASE}/api/share-master/xlsx`,
    // fetch (not a plain link) so the X-MDO-Key header the AuthGate adds rides along; the blob becomes the download
    download: async (): Promise<string> => {
      const res = await fetch(`${BASE}/api/share-master/xlsx`, { cache: "no-store" })
      if (!res.ok) throw new Error(`API /api/share-master/xlsx → ${res.status}`)
      const disp = res.headers.get("content-disposition") || ""
      const name = /filename="?([^";]+)"?/.exec(disp)?.[1] || "Share_Master.xlsx"
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement("a")
      a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10_000)
      return name
    },
    refresh: () => post<ShareMasterResponse & { stored: number; outcomes: Record<string, number>; vault: { saved: boolean; path: string; error?: string } }>("/api/share-master/refresh", {}),
    importPortfolio: (holder: string, csv: string, dryRun = false) =>
      post<PortfolioImportResult & { dry_run?: boolean }>("/api/share-master/portfolio/import", { holder, csv, dry_run: dryRun }),
  },
}
