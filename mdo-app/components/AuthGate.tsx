"use client"

// Access gate: if the backend requires a key (MDO_AUTH_TOKEN set), show a lock
// screen once per device. The key is stored in localStorage and attached to
// every API request via the fetch patch below.

import { useEffect, useState } from "react"
import { Lock } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"
const KEY_NAME = "mdo_key"

// Patch fetch once, at module load, so every page's API calls carry the key.
if (typeof window !== "undefined" && !(window as any).__mdoFetchPatched) {
  ;(window as any).__mdoFetchPatched = true
  const orig = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    try {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url
      if (url.startsWith(BASE)) {
        const key = localStorage.getItem(KEY_NAME)
        if (key) {
          const headers = new Headers(
            init.headers || (input instanceof Request ? input.headers : undefined)
          )
          headers.set("X-MDO-Key", key)
          init = { ...init, headers }
        }
      }
    } catch {}
    return orig(input as RequestInfo, init)
  }
}

export function getStoredKey(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(KEY_NAME)
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "open" | "locked">("checking")
  const [input, setInput] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    fetch(`${BASE}/api/status`, { cache: "no-store" })
      .then(r => setState(r.status === 401 ? "locked" : "open"))
      .catch(() => setState("open")) // backend down → let the offline banners handle it
  }, [])

  async function unlock() {
    const key = input.trim()
    if (!key) return
    try {
      const r = await fetch(`${BASE}/api/status`, {
        cache: "no-store",
        headers: { "X-MDO-Key": key },
      })
      if (r.ok) {
        localStorage.setItem(KEY_NAME, key)
        window.location.reload() // rerun every query + the live stream with the key
      } else {
        setError("Wrong key")
      }
    } catch {
      setError("Backend unreachable")
    }
  }

  if (state === "checking") return null
  if (state === "open") return <>{children}</>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "var(--bg)" }}>
      <div className="w-full max-w-xs px-6">
        <div className="flex items-center gap-2 mb-1">
          <Lock size={16} style={{ color: "var(--accent)" }} />
          <span style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 22, letterSpacing: "6px", color: "var(--accent)" }}>
            A M A N
          </span>
        </div>
        <p className="text-xs mb-4" style={{ color: "var(--text2)" }}>
          This system is private. Enter the access key.
        </p>
        <input
          type="password"
          autoFocus
          value={input}
          onChange={e => { setInput(e.target.value); setError("") }}
          onKeyDown={e => e.key === "Enter" && unlock()}
          placeholder="Access key"
          className="w-full px-3 py-2.5 rounded-lg text-sm border outline-none mb-2"
          style={{ background: "var(--bg2)", borderColor: error ? "var(--red)" : "var(--border)", color: "var(--text)" }}
        />
        {error && <p className="text-xs mb-2" style={{ color: "var(--red)" }}>{error}</p>}
        <button onClick={unlock}
          className="w-full py-2.5 rounded-lg text-sm font-medium"
          style={{ background: "var(--accent)", color: "#fff" }}>
          Unlock
        </button>
      </div>
    </div>
  )
}
