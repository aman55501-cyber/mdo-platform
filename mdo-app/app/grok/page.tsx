"use client"

import { useState, useRef, useEffect } from "react"
import { Send, Wrench, Sparkles, User } from "lucide-react"
import { Markdown } from "@/lib/markdown"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type BrainMsg = {
  role: "user" | "assistant"
  content: string
  tools_used?: string[]
  provider?: string | null
}

const QUICK = [
  { title: "Business snapshot",   q: "Give me a full business snapshot",                                        hint: "Across all entities" },
  { title: "Today's priorities",  q: "What needs my attention today? Classify 🔴🟡🟢.",                          hint: "Ranked by urgency" },
  { title: "Tender radar",        q: "Which tenders close this week?",                                          hint: "Pipeline + deadlines" },
  { title: "Bid calculator",      q: "What should I bid for SECL, 20,000 MT via Bilaspur at ₹1,450 gate?",     hint: "Landed cost + margin" },
  { title: "Compliance check",    q: "Any compliance items overdue?",                                           hint: "Filings across 26 units" },
  { title: "Site ops digest",     q: "Summarise today's site ops WhatsApp messages",                            hint: "From the VWLR groups" },
]

const THINKING = [
  "Consulting live business data…",
  "Reading tenders & pipeline…",
  "Checking compliance calendar…",
  "Scanning site ops feed…",
  "Cross-checking the numbers…",
]

function greeting() {
  const istHour = (new Date().getUTCHours() + 5.5) % 24
  if (istHour < 5)  return "Working late, Aman"
  if (istHour < 12) return "Good morning, Aman"
  if (istHour < 17) return "Good afternoon, Aman"
  return "Good evening, Aman"
}

export default function BrainPage() {
  const [messages, setMessages] = useState<BrainMsg[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [thinkIdx, setThinkIdx] = useState(0)
  const [status, setStatus] = useState<{ active: string | null; tools: string[] } | null>(null)
  const [unreachable, setUnreachable] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages, loading])
  useEffect(() => {
    fetch(`${BASE}/api/brain/status`, { cache: "no-store" })
      .then(r => r.json()).then(s => { setStatus(s); setUnreachable(false) })
      .catch(() => setUnreachable(true))
  }, [])
  useEffect(() => {
    if (!loading) return
    const id = setInterval(() => setThinkIdx(i => (i + 1) % THINKING.length), 2200)
    return () => clearInterval(id)
  }, [loading])

  async function send(text: string) {
    const q = text.trim()
    if (!q || loading) return
    setInput("")
    setThinkIdx(0)
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: "user", content: q }])
    setLoading(true)
    try {
      const r = await fetch(`${BASE}/api/brain/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history }),
      })
      const data = await r.json()
      setMessages(m => [...m, {
        role: "assistant",
        content: data.answer || "(no answer)",
        tools_used: data.tools_used || [],
        provider: data.provider,
      }])
    } catch {
      setMessages(m => [...m, { role: "assistant", content: "The backend didn't respond — check the connection." }])
    } finally {
      setLoading(false)
    }
  }

  const empty = messages.length === 0

  return (
    <div className="flex flex-col mx-auto w-full max-w-3xl"
      style={{ height: "calc(100vh - 86px)", minHeight: 420 }}>

      {/* status strip */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={15} style={{ color: "var(--accent2)" }} />
          <span className="text-sm font-semibold">MDO Brain</span>
        </div>
        <span className="text-[10px] px-2.5 py-1 rounded-full"
          style={{
            background: unreachable ? "rgba(248,113,113,0.12)" : "rgba(143,140,255,0.08)",
            color: unreachable ? "var(--red)" : "var(--text2)",
            border: `1px solid ${unreachable ? "rgba(248,113,113,0.3)" : "var(--glass-brd)"}`,
          }}>
          {unreachable
            ? "backend unreachable"
            : status?.active
              ? `${status.active} · ${status.tools?.length ?? 0} live tools`
              : status ? "no LLM key configured" : "connecting…"}
        </span>
      </div>

      {/* conversation / hero */}
      <div className="flex-1 overflow-y-auto pr-1">
        {empty ? (
          <div className="h-full flex flex-col items-center justify-center text-center fade-up">
            <div className="brain-orb mb-6" style={{ width: 88, height: 88, opacity: 0.9 }} />
            <h1 className="grad-text mb-2"
              style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 34, fontWeight: 400 }}>
              {greeting()}
            </h1>
            <p className="text-xs mb-8 max-w-sm" style={{ color: "var(--text2)" }}>
              Ask anything about the business. Every answer is pulled from your live
              data — tenders, compliance, pools, hotel, site ops — never invented.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-xl">
              {QUICK.map(({ title, q, hint }) => (
                <button key={title} onClick={() => send(q)}
                  className="glass card-hover text-left px-4 py-3 rounded-xl"
                  style={{ cursor: "pointer" }}>
                  <div className="text-[13px] font-medium" style={{ color: "var(--text)" }}>{title}</div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--text2)" }}>{hint}</div>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-5 py-2">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 fade-up ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" && (
                  <div className="brain-orb shrink-0 mt-1" style={{ width: 28, height: 28 }} />
                )}
                <div className="max-w-[85%]">
                  {m.role === "user" ? (
                    <div className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
                      style={{ background: "rgba(109,106,248,0.16)", border: "1px solid rgba(109,106,248,0.25)", color: "var(--text)", borderBottomRightRadius: 6 }}>
                      {m.content}
                    </div>
                  ) : (
                    <div className="rounded-2xl px-4 py-3"
                      style={{ background: "var(--bg2)", border: "1px solid var(--border)", borderBottomLeftRadius: 6 }}>
                      <Markdown text={m.content} />
                      {(m.tools_used?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-3 pt-2.5" style={{ borderTop: "1px solid var(--border)" }}>
                          {m.tools_used!.map((t, j) => (
                            <span key={j} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full"
                              style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                              <Wrench size={9} /> {t}
                            </span>
                          ))}
                          {m.provider && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full ml-auto"
                              style={{ background: "rgba(143,140,255,0.08)", color: "var(--accent2)" }}>
                              {m.provider}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {m.role === "user" && (
                  <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-1"
                    style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                    <User size={13} />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex gap-3 fade-up">
                <div className="brain-orb shrink-0" style={{ width: 28, height: 28 }} />
                <div className="px-4 py-3 rounded-2xl text-sm thinking-text"
                  style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
                  {THINKING[thinkIdx]}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {/* input */}
      <div className="glass mt-3 shrink-0 flex items-center gap-2 rounded-2xl px-2 py-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send(input))}
          placeholder="Ask about tenders, bids, compliance, hotel, portfolio, site ops…"
          className="flex-1 px-3 py-2.5 bg-transparent text-sm outline-none border-none"
          style={{ color: "var(--text)", boxShadow: "none" }}
        />
        <button onClick={() => send(input)} disabled={loading || !input.trim()}
          aria-label="Send"
          className="flex items-center justify-center rounded-xl transition-all active:scale-95"
          style={{
            width: 40, height: 40,
            background: input.trim() && !loading ? "var(--accent-grad)" : "var(--bg3)",
            color: input.trim() && !loading ? "#fff" : "var(--text2)",
            border: "none", cursor: input.trim() && !loading ? "pointer" : "default",
          }}>
          <Send size={15} />
        </button>
      </div>
    </div>
  )
}
