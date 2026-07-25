"use client"

import { useState, useRef, useEffect } from "react"
import { MessageSquare, Send, Loader2, User, Brain, Wrench } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type BrainMsg = {
  role: "user" | "assistant"
  content: string
  tools_used?: string[]
  provider?: string | null
}

const QUICK = [
  "Give me a full business snapshot",
  "Which tenders close this week?",
  "What should I bid for SECL, 20,000 MT via Bilaspur at ₹1,450 gate?",
  "Any compliance items overdue?",
  "How is Hotel ANS trending?",
  "Summarise today's site ops WhatsApp messages",
]

export default function BrainPage() {
  const [messages, setMessages] = useState<BrainMsg[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<{ active: string | null; tools: string[] } | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])
  useEffect(() => {
    fetch(`${BASE}/api/brain/status`, { cache: "no-store" })
      .then(r => r.json()).then(setStatus).catch(() => {})
  }, [])

  async function send(text: string) {
    const q = text.trim()
    if (!q || loading) return
    setInput("")
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
      setMessages(m => [...m, { role: "assistant", content: "Error — is the backend running?" }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <Brain size={20} style={{ color: "var(--accent2)" }} />
        <h1 className="text-2xl font-bold">MDO Brain</h1>
        <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          {status?.active
            ? `${status.active} · ${status.tools?.length ?? 0} live tools`
            : "no LLM key configured"}
        </span>
      </div>
      <p className="text-xs mb-4" style={{ color: "var(--text2)" }}>
        Answers are pulled from your live database — tenders, leads, compliance, hotel, pools,
        site ops feed — never invented.
      </p>

      {/* Quick prompts */}
      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {QUICK.map((q) => (
            <button key={q} onClick={() => send(q)}
              className="text-xs px-3 py-1.5 rounded-full border transition-colors text-left"
              style={{ borderColor: "var(--border)", background: "var(--bg2)", color: "var(--text2)" }}>
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            {m.role === "assistant" && (
              <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                style={{ background: "var(--bg3)", color: "var(--accent2)" }}>
                <Brain size={14} />
              </div>
            )}
            <div className="max-w-[80%]">
              <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap"
                style={{
                  background: m.role === "user" ? "var(--accent)" : "var(--bg2)",
                  color: m.role === "user" ? "#fff" : "var(--text)",
                  borderBottomRightRadius: m.role === "user" ? 4 : undefined,
                  borderBottomLeftRadius: m.role === "assistant" ? 4 : undefined,
                }}>
                {m.content}
              </div>
              {m.role === "assistant" && (m.tools_used?.length ?? 0) > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1.5 px-1">
                  {m.tools_used!.map((t, j) => (
                    <span key={j} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full"
                      style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                      <Wrench size={9} /> {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {m.role === "user" && (
              <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
                style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                <User size={14} />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: "var(--bg3)", color: "var(--accent2)" }}>
              <Brain size={14} />
            </div>
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl text-sm" style={{ background: "var(--bg2)", color: "var(--text2)" }}>
              <Loader2 size={14} className="animate-spin" /> Consulting live data…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="mt-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send(input))}
          placeholder="Ask about tenders, bids, compliance, hotel, portfolio, site ops…"
          className="flex-1 px-4 py-3 rounded-xl text-sm border outline-none"
          style={{ background: "var(--bg2)", borderColor: "var(--border)", color: "var(--text)" }}
        />
        <button onClick={() => send(input)} disabled={loading || !input.trim()}
          className="px-4 py-3 rounded-xl transition-colors"
          style={{ background: "var(--accent)", color: "#fff", opacity: loading || !input.trim() ? 0.5 : 1 }}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
