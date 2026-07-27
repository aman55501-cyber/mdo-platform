"use client"

// Access gate: if the backend requires a key (MDO_AUTH_TOKEN set), show a lock
// screen once per device. The key is stored in localStorage and attached to
// every API request via the fetch patch below.

import { useEffect, useState } from "react"
import { Lock, Eye, EyeOff } from "lucide-react"

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
  const [show, setShow] = useState(false)

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
      } else if (r.status === 401) {
        setError("Wrong key")
      } else {
        setError(`Server error ${r.status} — key not the problem; check the backend/proxy`)
      }
    } catch {
      setError("Backend unreachable")
    }
  }

  if (state === "checking") return null
  if (state === "open") return <>{children}</>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden"
      style={{ background: "var(--bg)" }}>
      {/* ambient orb */}
      <div className="brain-orb" aria-hidden
        style={{ position: "absolute", left: "50%", top: "38%", width: 380, height: 380, opacity: 0.16 }} />

      <div className={`glass fade-up w-full max-w-sm mx-4 px-8 py-9 rounded-3xl ${error ? "shake" : ""}`}
        style={{ boxShadow: "0 30px 90px rgba(0,0,0,0.55)" }}>
        <div className="flex flex-col items-center text-center mb-7">
          <div className="brain-orb mb-5" style={{ width: 52, height: 52 }} />
          <span className="grad-text"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontSize: 30, letterSpacing: "10px", fontWeight: 400, paddingLeft: 10 }}>
            AMAN
          </span>
          <p className="text-xs mt-2" style={{ color: "var(--text2)", letterSpacing: "0.04em" }}>
            Management Decision Office
          </p>
        </div>

        <div className="relative mb-3">
          <input
            type={show ? "text" : "password"}
            name="mdo-access-key"
            autoComplete="new-password"
            autoFocus
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={input}
            onChange={e => { setInput(e.target.value); setError("") }}
            onKeyDown={e => e.key === "Enter" && unlock()}
            placeholder="Access key"
            className="w-full px-4 py-3 pr-11 rounded-xl text-sm border outline-none"
            style={{ background: "rgba(7,8,13,0.6)", borderColor: error ? "var(--red)" : "var(--border)", color: "var(--text)" }}
          />
          <button
            type="button"
            onClick={() => setShow(s => !s)}
            aria-label={show ? "Hide access key" : "Show access key"}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1"
            style={{ color: "var(--text2)", background: "none", border: "none", cursor: "pointer" }}
          >
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        {error && <p className="text-xs mb-3" style={{ color: "var(--red)" }}>{error}</p>}
        <button onClick={unlock}
          className="w-full py-3 rounded-xl text-sm font-semibold transition-transform active:scale-[0.98]"
          style={{ background: "var(--accent-grad)", color: "#fff", border: "none", cursor: "pointer", boxShadow: "0 6px 24px rgba(109,106,248,0.35)" }}>
          <span className="inline-flex items-center gap-2 justify-center"><Lock size={13} /> Unlock</span>
        </button>
        <p className="text-[10px] text-center mt-5" style={{ color: "var(--text2)", opacity: 0.6 }}>
          Private system · encrypted · Raigarh CG
        </p>
      </div>
    </div>
  )
}
