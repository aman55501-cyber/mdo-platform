"use client"

import { useState, useRef, useEffect } from "react"
import { api } from "@/lib/api"
import { MessageSquare, Send, Loader2, User, Bot } from "lucide-react"
import type { GrokMessage } from "@/lib/types"

const QUICK = [
  "Morning briefing",
  "Vedanta tender update",
  "Nifty trend today",
  "RELIANCE sentiment",
  "Anil Singhvi latest calls",
  "ANS compliance status",
]

export default function GrokPage() {
  const [messages, setMessages] = useState<GrokMessage[]>([])
  const [input, setInput]       = useState("")
  const [loading, setLoading]   = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])

  async function send(text: string) {
    const q = text.trim()
    if (!q) return
    setInput("")
    const ts = new Date().toISOString()
    setMessages((m) => [...m, { role: "user", content: q, timestamp: ts }])
    setLoading(true)
    try {
      const { answer } = await api.grok.ask(q)
      setMessages((m) => [...m, { role: "assistant", content: answer, timestamp: new Date().toISOString() }])
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Error — is the backend running?", timestamp: new Date().toISOString() }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <MessageSquare size={20} style={{ color: "var(--accent2)" }} />
        <h1 className="text-2xl font-bold">Grok AI</h1>
        <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg3)", color: "var(--text2)" }}>
          x_search enabled
        </span>
      </div>

      {/* Quick prompts */}
      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {QUICK.map((q) => (
            <button key={q} onClick={() => send(q)}
              className="text-xs px-3 py-1.5 rounded-full border transition-colors"
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
                <Bot size={14} />
              </div>
            )}
            <div className="max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed"
              style={{
                background: m.role === "user" ? "var(--accent)" : "var(--bg2)",
                color: m.role === "user" ? "#fff" : "var(--text)",
                borderBottomRightRadius: m.role === "user" ? 4 : undefined,
                borderBottomLeftRadius: m.role === "assistant" ? 4 : undefined,
              }}>
              {m.content}
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
              <Bot size={14} />
            </div>
            <div className="flex items-center gap-2 px-4 py-3 rounded-2xl text-sm" style={{ background: "var(--bg2)", color: "var(--text2)" }}>
              <Loader2 size={14} className="animate-spin" /> Thinking…
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
          placeholder="Ask Grok anything about markets, Vedanta, compliance…"
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
