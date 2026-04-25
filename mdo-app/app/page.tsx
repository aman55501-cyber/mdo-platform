"use client"

import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

// ── types ─────────────────────────────────────────────────────────────────────
interface BriefingResponse {
  bullets: string[]
  generated_at: string
}

interface IndexQuote {
  label: string
  value: number
  change: number
  changePct: number
}

interface IndicesResponse {
  nifty50: IndexQuote
  banknifty: IndexQuote
  usdinr: IndexQuote
  nasdaq: IndexQuote
  dowjones: IndexQuote
}

interface StockQuote {
  ticker: string
  cmp: number
  changePct: number
  high52w: number
  low52w: number
}

interface WatchlistItem {
  ticker: string
  name: string
  cmp: number
  changePct: number
  high52w: number
  low52w: number
  context: string
  stale?: boolean
}

// ── fetchers ──────────────────────────────────────────────────────────────────
async function fetchBriefing(): Promise<BriefingResponse> {
  const res = await fetch(`${BASE}/api/briefing/today`)
  if (!res.ok) throw new Error("No briefing")
  return res.json()
}

async function generateBriefing(): Promise<BriefingResponse> {
  const res = await fetch(`${BASE}/api/briefing/generate`, { method: "POST" })
  if (!res.ok) throw new Error("Generate failed")
  return res.json()
}

async function fetchIndices(): Promise<IndicesResponse> {
  const res = await fetch(`${BASE}/api/market/indices`)
  if (!res.ok) throw new Error("Indices failed")
  return res.json()
}

async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const res = await fetch(`${BASE}/api/market/watchlist`)
  if (!res.ok) throw new Error("Watchlist failed")
  return res.json()
}

async function fetchQuote(ticker: string): Promise<StockQuote> {
  const res = await fetch(`${BASE}/api/market/quote/${ticker}`)
  if (!res.ok) throw new Error(`Quote failed for ${ticker}`)
  return res.json()
}

// ── helpers ───────────────────────────────────────────────────────────────────
function fmtNum(n: number | undefined | null, dec = 2): string {
  if (n == null || isNaN(n)) return "—"
  return n.toLocaleString("en-IN", { minimumFractionDigits: dec, maximumFractionDigits: dec })
}

function isMarketOpen(): boolean {
  const now = new Date()
  // Convert to IST (UTC+5:30)
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }))
  const day = ist.getDay() // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false
  const h = ist.getHours()
  const m = ist.getMinutes()
  const mins = h * 60 + m
  return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
}

function todayLabel(): string {
  return new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  })
}

// ── skeleton pulse ────────────────────────────────────────────────────────────
function Skeleton({ w = "100%", h = 14 }: { w?: string; h?: number }) {
  return (
    <div
      className="skeleton-pulse"
      style={{
        width: w,
        height: h,
        borderRadius: 4,
        background: "var(--bg3)",
      }}
    />
  )
}

// ── change badge ──────────────────────────────────────────────────────────────
function Change({ pct, small }: { pct: number | undefined | null; small?: boolean }) {
  if (pct == null || isNaN(pct)) return <span style={{ color: "var(--text2)" }}>—</span>
  const up = pct >= 0
  return (
    <span
      style={{
        color: up ? "var(--green)" : "var(--red)",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: small ? 11 : 13,
        fontWeight: 600,
      }}
    >
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
    </span>
  )
}

// ── 52W range bar ─────────────────────────────────────────────────────────────
function RangeBar({ cmp, low, high }: { cmp: number; low: number; high: number }) {
  const pct = high > low ? Math.max(0, Math.min(100, ((cmp - low) / (high - low)) * 100)) : 50
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <div
        style={{
          width: "100%",
          height: 4,
          background: "var(--bg3)",
          borderRadius: 2,
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            height: "100%",
            width: `${pct}%`,
            background: "var(--accent)",
            borderRadius: 2,
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ color: "var(--text2)", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
          {fmtNum(low)}
        </span>
        <span style={{ color: "var(--text2)", fontSize: 10, fontFamily: "'JetBrains Mono', monospace" }}>
          {fmtNum(high)}
        </span>
      </div>
    </div>
  )
}

// ── tooltip ───────────────────────────────────────────────────────────────────
function Tooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false)
  return (
    <span
      style={{ position: "relative", display: "inline-block", cursor: "help" }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 14,
          height: 14,
          borderRadius: "50%",
          border: "1px solid var(--border)",
          color: "var(--text2)",
          fontSize: 9,
          fontWeight: 700,
          lineHeight: 1,
          marginLeft: 4,
          userSelect: "none",
        }}
      >
        ?
      </span>
      {show && (
        <span
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: "50%",
            transform: "translateX(-50%)",
            background: "var(--bg3)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: "6px 10px",
            fontSize: 11,
            color: "var(--text)",
            whiteSpace: "nowrap",
            zIndex: 100,
            lineHeight: 1.5,
            boxShadow: "0 4px 16px rgba(0,0,0,0.6)",
          }}
        >
          {text}
        </span>
      )}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 1: MORNING BRIEFING
// ═══════════════════════════════════════════════════════════════════════════════
function MorningBriefing() {
  const qc = useQueryClient()

  const { data, isLoading, isError } = useQuery<BriefingResponse>({
    queryKey: ["briefing-today"],
    queryFn: fetchBriefing,
    refetchInterval: 60_000,
    retry: 1,
  })

  const mutation = useMutation({
    mutationFn: generateBriefing,
    onSuccess: (newData) => {
      qc.setQueryData(["briefing-today"], newData)
    },
  })

  const noBriefing = isError || (!isLoading && (!data || !data.bullets?.length))

  return (
    <div
      style={{
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span
          style={{
            fontFamily: "'Cormorant Garamond', serif",
            fontWeight: 300,
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase" as const,
            color: "var(--accent)",
          }}
        >
          Morning Briefing
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ color: "var(--text2)", fontSize: 11 }}>{todayLabel()}</span>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 12px",
              background: mutation.isPending ? "var(--bg3)" : "transparent",
              border: "1px solid var(--accent)",
              borderRadius: 4,
              color: "var(--accent)",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.05em",
              cursor: mutation.isPending ? "default" : "pointer",
              opacity: mutation.isPending ? 0.7 : 1,
              transition: "background 0.15s",
            }}
          >
            {mutation.isPending ? (
              <>
                <span className="spin-icon">⟳</span> Generating…
              </>
            ) : (
              <>⟳ Regenerate</>
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: "14px 16px" }}>
        {isLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[100, 85, 90, 75, 95].map((w, i) => (
              <Skeleton key={i} w={`${w}%`} h={15} />
            ))}
          </div>
        ) : noBriefing ? (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div style={{ color: "var(--text2)", fontSize: 13, marginBottom: 14 }}>
              No briefing generated for today yet.
            </div>
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              style={{
                padding: "8px 22px",
                background: "var(--accent)",
                border: "none",
                borderRadius: 4,
                color: "#080808",
                fontWeight: 700,
                fontSize: 13,
                cursor: mutation.isPending ? "default" : "pointer",
                letterSpacing: "0.04em",
              }}
            >
              {mutation.isPending ? "Generating…" : "Generate Today's Briefing"}
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            {(data?.bullets ?? []).map((raw, i) => {
              // Bullets may be full strings like "MARKETS: Nifty flat..." or raw text
              const colonIdx = raw.indexOf(":")
              const hasCategory = colonIdx > 0 && colonIdx < 15
              const category = hasCategory ? raw.slice(0, colonIdx).trim().toUpperCase() : null
              const rest = hasCategory ? raw.slice(colonIdx + 1).trim() : raw.trim()
              return (
                <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13, lineHeight: 1.55 }}>
                  <span style={{ color: "var(--accent)", marginTop: 1, flexShrink: 0 }}>•</span>
                  <span>
                    {category && (
                      <span
                        style={{
                          color: "var(--accent)",
                          fontWeight: 700,
                          fontSize: 11,
                          letterSpacing: "0.08em",
                          marginRight: 6,
                          textTransform: "uppercase" as const,
                        }}
                      >
                        {category}:
                      </span>
                    )}
                    <span style={{ color: "var(--text)" }}>{rest}</span>
                  </span>
                </div>
              )
            })}
          </div>
        )}
        {mutation.isError && (
          <div style={{ color: "var(--red)", fontSize: 11, marginTop: 8 }}>
            Generation failed — please try again.
          </div>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 2: MARKET INDICES BAR
// ═══════════════════════════════════════════════════════════════════════════════
function MarketIndicesBar() {
  const [live, setLive] = useState(isMarketOpen())

  useEffect(() => {
    const t = setInterval(() => setLive(isMarketOpen()), 60_000)
    return () => clearInterval(t)
  }, [])

  const { data, isLoading } = useQuery<IndicesResponse>({
    queryKey: ["indices"],
    queryFn: fetchIndices,
    refetchInterval: 300_000,
    retry: 1,
  })

  const indices: { key: keyof IndicesResponse; label: string; prefix?: string }[] = [
    { key: "nifty50", label: "NIFTY 50" },
    { key: "banknifty", label: "BANKNIFTY" },
    { key: "usdinr", label: "USD/INR", prefix: "₹" },
    { key: "nasdaq", label: "NASDAQ" },
    { key: "dowjones", label: "DOW JONES" },
  ]

  return (
    <div
      style={{
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        gap: 0,
      }}
    >
      <div style={{ display: "flex", flex: 1, gap: 4, flexWrap: "wrap" as const }}>
        {indices.map(({ key, label, prefix }, i) => {
          const q = data?.[key]
          return (
            <div
              key={key}
              style={{
                flex: "1 1 0",
                minWidth: 120,
                padding: "6px 12px",
                borderRight: i < indices.length - 1 ? "1px solid var(--border)" : "none",
              }}
            >
              <div style={{ color: "var(--text2)", fontSize: 10, letterSpacing: "0.07em", marginBottom: 3 }}>
                {label}
              </div>
              {isLoading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <Skeleton w="70%" h={18} />
                  <Skeleton w="50%" h={12} />
                </div>
              ) : (
                <>
                  <div
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 700,
                      fontSize: 15,
                      color: "var(--text)",
                    }}
                  >
                    {q ? `${prefix ?? ""}${fmtNum(q.value)}` : "—"}
                  </div>
                  <Change pct={q?.changePct} small />
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* Market hours indicator */}
      <div
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: 7,
          paddingLeft: 18,
          borderLeft: "1px solid var(--border)",
          marginLeft: 8,
        }}
      >
        {live ? (
          <>
            <span className="pulse-dot" />
            <span style={{ color: "var(--green)", fontSize: 11, fontWeight: 700, letterSpacing: "0.08em" }}>
              LIVE
            </span>
          </>
        ) : (
          <>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--text2)",
                display: "inline-block",
              }}
            />
            <span style={{ color: "var(--text2)", fontSize: 11, fontWeight: 600, letterSpacing: "0.08em" }}>
              CLOSED
            </span>
          </>
        )}
        <div style={{ fontSize: 9, color: "var(--text2)", lineHeight: 1.3, textAlign: "center" as const }}>
          09:15–15:30
          <br />
          IST
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 3: COAL SECTOR PULSE
// ═══════════════════════════════════════════════════════════════════════════════
const COAL_TOOLTIPS: Record<string, string> = {
  "COAL INDIA": "Sector anchor — also VWLR's main indirect customer",
  NTPC: "CG plants at Sipat/Korba — capex = new rake contracts for VWLR",
  "NEWCASTLE COAL": "Global benchmark — when it rises, Indian plants rely more on domestic coal → VWLR volumes up",
  "NCI INDIA": "India domestic coal index — directly sets coal trading margins",
  "USD/INR": "Affects imported coal parity price and Coal India competitiveness",
}

function CoalCard({
  label,
  sublabel,
  value,
  change,
  changePct,
  note,
  isLoading: loading,
  stale,
}: {
  label: string
  sublabel?: string
  value: string
  change?: string
  changePct?: number | null
  note?: string
  isLoading?: boolean
  stale?: boolean
}) {
  return (
    <div
      style={{
        flex: "1 1 0",
        minWidth: 140,
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "12px 14px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 6,
        }}
      >
        <span
          style={{
            color: "var(--accent)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.1em",
            textTransform: "uppercase" as const,
          }}
        >
          {label}
        </span>
        <Tooltip text={COAL_TOOLTIPS[label] ?? ""} />
      </div>
      {sublabel && (
        <div style={{ color: "var(--text2)", fontSize: 10, marginBottom: 6 }}>{sublabel}</div>
      )}
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          <Skeleton w="80%" h={22} />
          <Skeleton w="50%" h={13} />
        </div>
      ) : (
        <>
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 700,
              fontSize: 18,
              color: stale ? "var(--text2)" : "var(--text)",
              lineHeight: 1.2,
            }}
          >
            {value}
            {stale && (
              <span style={{ fontSize: 9, color: "var(--text2)", marginLeft: 4, fontWeight: 400 }}>cached</span>
            )}
          </div>
          {(change || changePct != null) && (
            <div style={{ marginTop: 5 }}>
              {changePct != null ? (
                <Change pct={changePct} small />
              ) : (
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: 11,
                    color: change?.startsWith("+") ? "var(--green)" : change?.startsWith("-") ? "var(--red)" : "var(--text2)",
                  }}
                >
                  {change}
                </span>
              )}
            </div>
          )}
          {note && (
            <div style={{ color: "var(--text2)", fontSize: 10, marginTop: 5, fontStyle: "italic" }}>{note}</div>
          )}
        </>
      )}
    </div>
  )
}

function CoalSectorPulse() {
  const { data: coalData, isLoading: coalLoading } = useQuery<StockQuote>({
    queryKey: ["quote", "COALINDIA.NS"],
    queryFn: () => fetchQuote("COALINDIA.NS"),
    refetchInterval: 300_000,
    retry: 1,
  })

  const { data: ntpcData, isLoading: ntpcLoading } = useQuery<StockQuote>({
    queryKey: ["quote", "NTPC.NS"],
    queryFn: () => fetchQuote("NTPC.NS"),
    refetchInterval: 300_000,
    retry: 1,
  })

  const { data: indices } = useQuery<IndicesResponse>({
    queryKey: ["indices"],
    queryFn: fetchIndices,
    refetchInterval: 300_000,
    retry: 1,
  })

  return (
    <div>
      <div
        style={{
          fontFamily: "'Cormorant Garamond', serif",
          fontWeight: 300,
          fontSize: 11,
          letterSpacing: "0.14em",
          textTransform: "uppercase" as const,
          color: "var(--accent)",
          marginBottom: 8,
        }}
      >
        Coal Sector Pulse
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const }}>
        <CoalCard
          label="COAL INDIA"
          sublabel="NSE: COALINDIA"
          value={coalData?.cmp ? `₹${fmtNum(coalData.cmp)}` : "—"}
          changePct={coalData?.changePct}
          isLoading={coalLoading}
          stale={!coalLoading && !coalData?.cmp}
        />
        <CoalCard
          label="NTPC"
          sublabel="NSE: NTPC"
          value={ntpcData?.cmp ? `₹${fmtNum(ntpcData.cmp)}` : "—"}
          changePct={ntpcData?.changePct}
          isLoading={ntpcLoading}
          stale={!ntpcLoading && !ntpcData?.cmp}
        />
        <CoalCard
          label="NEWCASTLE COAL"
          sublabel="ICE Benchmark"
          value="$133.40 /MT"
          change="+1.1%"
          note="1M: +8.1%"
        />
        <CoalCard
          label="NCI INDIA"
          sublabel="Updated: Mar 2026"
          value="INDEX 142.3"
          note="Ministry of Coal"
        />
        <CoalCard
          label="USD/INR"
          sublabel="Spot Rate"
          value={indices?.usdinr?.value ? `₹${fmtNum(indices.usdinr.value, 2)}` : "—"}
          changePct={indices?.usdinr?.changePct}
        />
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECTION 4: WATCHLIST TABLE
// ═══════════════════════════════════════════════════════════════════════════════
function WatchlistTable() {
  const { data, isLoading } = useQuery<WatchlistItem[]>({
    queryKey: ["watchlist"],
    queryFn: fetchWatchlist,
    refetchInterval: 300_000,
    retry: 1,
  })

  return (
    <div
      style={{
        background: "var(--bg2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span
          style={{
            fontFamily: "'Cormorant Garamond', serif",
            fontWeight: 300,
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase" as const,
            color: "var(--accent)",
          }}
        >
          Watchlist
        </span>
        <span style={{ color: "var(--text2)", fontSize: 10 }}>Refreshes every 5 min</span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              {["Stock", "CMP", "Day %", "52W Range", "Context"].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "8px 16px",
                    textAlign: h === "CMP" || h === "Day %" ? "right" : "left",
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: "0.08em",
                    color: "var(--text2)",
                    textTransform: "uppercase" as const,
                    whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    {[1, 2, 3, 4, 5].map((c) => (
                      <td key={c} style={{ padding: "12px 16px" }}>
                        <Skeleton w={c === 4 ? "100%" : c === 5 ? "90%" : "60%"} h={14} />
                      </td>
                    ))}
                  </tr>
                ))
              : (data ?? []).map((item) => {
                  const cmp = item.cmp || 0
                  const stale = cmp === 0
                  return (
                    <tr
                      key={item.ticker}
                      style={{
                        borderBottom: "1px solid var(--border)",
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={(e) =>
                        ((e.currentTarget as HTMLTableRowElement).style.background = "var(--bg3)")
                      }
                      onMouseLeave={(e) =>
                        ((e.currentTarget as HTMLTableRowElement).style.background = "transparent")
                      }
                    >
                      {/* Stock */}
                      <td style={{ padding: "10px 16px", whiteSpace: "nowrap" }}>
                        <div
                          style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontWeight: 700,
                            fontSize: 13,
                            color: "var(--text)",
                          }}
                        >
                          {item.ticker}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--text2)", marginTop: 1 }}>{item.name}</div>
                      </td>

                      {/* CMP */}
                      <td style={{ padding: "10px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                        <span
                          style={{
                            fontFamily: "'JetBrains Mono', monospace",
                            fontWeight: 700,
                            fontSize: 14,
                            color: stale ? "var(--text2)" : "var(--text)",
                          }}
                        >
                          {stale ? "—" : `₹${fmtNum(cmp)}`}
                          {stale && item.cmp > 0 && (
                            <span style={{ fontSize: 9, color: "var(--text2)", marginLeft: 4 }}>cached</span>
                          )}
                        </span>
                      </td>

                      {/* Day % */}
                      <td style={{ padding: "10px 16px", textAlign: "right", whiteSpace: "nowrap" }}>
                        <Change pct={stale ? null : item.changePct} />
                      </td>

                      {/* 52W Range */}
                      <td style={{ padding: "10px 16px", minWidth: 140 }}>
                        {item.high52w && item.low52w && cmp > 0 ? (
                          <RangeBar cmp={cmp} low={item.low52w} high={item.high52w} />
                        ) : (
                          <span style={{ color: "var(--text2)", fontSize: 12 }}>—</span>
                        )}
                      </td>

                      {/* Context */}
                      <td style={{ padding: "10px 16px" }}>
                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text2)",
                            fontStyle: "italic",
                            lineHeight: 1.45,
                          }}
                        >
                          {item.context || "—"}
                        </span>
                      </td>
                    </tr>
                  )
                })}
            {!isLoading && (!data || data.length === 0) && (
              <tr>
                <td colSpan={5} style={{ padding: "28px 16px", textAlign: "center", color: "var(--text2)", fontSize: 13 }}>
                  No watchlist items
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROOT DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════
export default function Dashboard() {
  return (
    <>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        .skeleton-pulse {
          animation: pulse 1.5s ease-in-out infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin-icon {
          display: inline-block;
          animation: spin 0.9s linear infinite;
        }
        @keyframes pulse-dot {
          0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5); }
          50% { box-shadow: 0 0 0 5px rgba(34, 197, 94, 0); }
        }
        .pulse-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--green);
          animation: pulse-dot 1.4s ease-in-out infinite;
        }
      `}</style>

      <div style={{ maxWidth: 1280, display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Page title bar */}
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
          <h1
            style={{
              fontFamily: "'Cormorant Garamond', serif",
              fontWeight: 300,
              fontSize: 22,
              letterSpacing: "0.06em",
              color: "var(--text)",
              margin: 0,
            }}
          >
            AMAN{" "}
            <span style={{ color: "var(--accent)", fontSize: 13, letterSpacing: "0.16em", fontWeight: 400 }}>
              / OVERVIEW
            </span>
          </h1>
          <span style={{ color: "var(--text2)", fontSize: 11 }}>{todayLabel()}</span>
        </div>

        {/* S1: Morning Briefing */}
        <MorningBriefing />

        {/* S2: Market Indices */}
        <MarketIndicesBar />

        {/* S3: Coal Sector Pulse */}
        <CoalSectorPulse />

        {/* S4: Watchlist */}
        <WatchlistTable />
      </div>
    </>
  )
}
