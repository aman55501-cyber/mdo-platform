"use client"

// Global "Ask MDO" layer: ⌘K / Ctrl+K anywhere (or the floating orb button)
// opens a command-palette-style overlay that talks to the MDO Brain without
// leaving the current page.

import { useEffect, useRef, useState, useCallback } from "react"
import { Sparkles, X, Wrench, CornerDownLeft } from "lucide-react"
import { Markdown } from "@/lib/markdown"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

const THINKING = [
  "Consulting live business data…",
  "Reading tenders & pipeline…",
  "Checking compliance calendar…",
  "Scanning site ops feed…",
  "Cross-checking the numbers…",
]

const SUGGESTIONS = [
  "Full business snapshot",
  "What needs my attention today?",
  "Tenders closing this week",
  "Overdue compliance items",
]

type Exchange = {
  q: string
  a?: string
  tools?: string[]
  provider?: string | null
  error?: boolean
}

export function BrainDock() {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [thinkIdx, setThinkIdx] = useState(0)
  const [items, setItems] = useState<Exchange[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // hotkey: ⌘K / Ctrl+K toggles, Esc closes
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(o => !o)
      } else if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 60)
  }, [open])

  useEffect(() => {
    if (!loading) return
    const id = setInterval(() => setThinkIdx(i => (i + 1) % THINKING.length), 2200)
    return () => clearInterval(id)
  }, [loading])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [items, loading])

  const ask = useCallback(async (text: string) => {
    const q = text.trim()
    if (!q || loading) return
    setInput("")
    setThinkIdx(0)
    const history = items.flatMap(it =>
      it.a && !it.error
        ? [{ role: "user", content: it.q }, { role: "assistant", content: it.a }]
        : []
    )
    setItems(list => [...list, { q }])
    setLoading(true)
    try {
      const r = await fetch(`${BASE}/api/brain/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history }),
      })
      const data = await r.json()
      setItems(list => {
        const next = [...list]
        next[next.length - 1] = {
          q,
          a: data.answer || "(no answer)",
          tools: data.tools_used || [],
          provider: data.provider,
        }
        return next
      })
    } catch {
      setItems(list => {
        const next = [...list]
        next[next.length - 1] = { q, a: "The backend didn't respond — check the connection.", error: true }
        return next
      })
    } finally {
      setLoading(false)
    }
  }, [items, loading])

  return (
    <>
      {/* Floating orb button */}
      <button
        onClick={() => setOpen(true)}
        aria-label="Ask MDO Brain (Ctrl+K)"
        className="fixed z-40 flex items-center justify-center card-hover"
        style={{
          right: 18, bottom: 18, width: 48, height: 48, borderRadius: 9999,
          background: "var(--accent-grad)", color: "#fff", border: "none",
          boxShadow: "0 6px 24px rgba(109,106,248,0.45)", cursor: "pointer",
        }}
      >
        <Sparkles size={20} />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center px-3 pt-[8vh] sm:pt-[12vh]"
          style={{ background: "rgba(4,5,9,0.6)", backdropFilter: "blur(6px)" }}
          onMouseDown={e => { if (e.target === e.currentTarget) setOpen(false) }}
        >
          <div className="glass fade-up w-full max-w-2xl rounded-2xl overflow-hidden flex flex-col"
            style={{ maxHeight: "72vh", boxShadow: "0 24px 80px rgba(0,0,0,0.6)" }}>

            {/* input row */}
            <div className="flex items-center gap-3 px-4 py-3.5"
              style={{ borderBottom: items.length || loading ? "1px solid var(--border)" : "none" }}>
              <Sparkles size={17} style={{ color: "var(--accent2)", flexShrink: 0 }} />
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && ask(input)}
                placeholder="Ask MDO anything — tenders, cash, compliance, site ops…"
                className="flex-1 bg-transparent text-sm outline-none border-none"
                style={{ color: "var(--text)", boxShadow: "none" }}
              />
              <kbd className="hidden sm:flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded"
                style={{ background: "var(--bg3)", color: "var(--text2)", border: "1px solid var(--border)" }}>
                <CornerDownLeft size={9} /> send
              </kbd>
              <button onClick={() => setOpen(false)} aria-label="Close"
                style={{ color: "var(--text2)", background: "none", border: "none", cursor: "pointer" }}>
                <X size={16} />
              </button>
            </div>

            {/* suggestions (empty state) */}
            {items.length === 0 && !loading && (
              <div className="px-4 py-3 flex flex-wrap gap-2">
                {SUGGESTIONS.map(s => (
                  <button key={s} onClick={() => ask(s)}
                    className="text-xs px-3 py-1.5 rounded-full transition-colors"
                    style={{ background: "var(--bg3)", color: "var(--text2)", border: "1px solid var(--border)", cursor: "pointer" }}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* conversation */}
            {(items.length > 0 || loading) && (
              <div ref={scrollRef} className="overflow-y-auto px-4 py-4 flex flex-col gap-4">
                {items.map((it, i) => (
                  <div key={i} className="fade-up">
                    <div className="text-xs mb-1.5 font-medium" style={{ color: "var(--accent2)" }}>{it.q}</div>
                    {it.a === undefined ? (
                      <div className="text-sm thinking-text">{THINKING[thinkIdx]}</div>
                    ) : (
                      <>
                        <div style={{ color: it.error ? "var(--red)" : "var(--text)" }}>
                          <Markdown text={it.a} />
                        </div>
                        {(it.tools?.length ?? 0) > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {it.tools!.map((t, j) => (
                              <span key={j} className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full"
                                style={{ background: "var(--bg3)", color: "var(--text2)" }}>
                                <Wrench size={9} /> {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* footer */}
            <div className="px-4 py-2 text-[10px] flex items-center justify-between"
              style={{ borderTop: "1px solid var(--border)", color: "var(--text2)" }}>
              <span>Answers come only from your live database — never invented.</span>
              <a href="/grok" style={{ color: "var(--accent2)" }}>Open MDO Brain →</a>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
