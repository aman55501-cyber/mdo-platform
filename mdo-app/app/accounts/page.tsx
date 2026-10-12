"use client"

// /accounts — broker logins. One page for: which accounts are connected, add an HDFC or Angel One account, log in each day.
// Aman, chat 2026-10-12: "rebuild frontend especially login page so I can put Cowork on it".
// Built for a person or for Cowork: every field has a visible label, a stable id and an aria-label; secret fields are type=password and
// say so; nothing here ever shows a key after it is sent. Cowork must stop at every password field ("your turn").

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, Circle, KeyRound, LogIn, RefreshCw, ShieldCheck } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

interface Account { key: string; label: string; broker: string; client_code?: string; logged_in: boolean; needs_setup?: boolean; source?: string }
interface AccountsData { accounts: Account[]; error: string }

const card: React.CSSProperties = { background: "var(--bg2)", border: "1px solid var(--border)", borderRadius: 14, padding: 14, marginBottom: 12 }
const h: React.CSSProperties = { fontSize: 11, color: "var(--text2)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }
const btn: React.CSSProperties = { minHeight: 44, minWidth: 44, borderRadius: 10, border: "1px solid var(--border2)", background: "var(--bg)", color: "var(--text)", padding: "0 14px", fontSize: 14, cursor: "pointer" }
const input: React.CSSProperties = { width: "100%", minHeight: 44, borderRadius: 10, border: "1px solid var(--border2)", background: "var(--bg)", color: "var(--text)", padding: "0 12px", fontSize: 15, boxSizing: "border-box" }
const label: React.CSSProperties = { display: "block", fontSize: 13, color: "var(--text2)", margin: "10px 0 4px" }

type Broker = "hdfc" | "angel"
const FIELDS: Record<Broker, { id: string; text: string; secret: boolean; hint: string }[]> = {
  hdfc: [
    { id: "api_key", text: "API key", secret: true, hint: "From the HDFC Securities developer portal" },
    { id: "api_secret", text: "API secret", secret: true, hint: "Shown once at the same place" },
    { id: "client_code", text: "Client code", secret: false, hint: "Optional, helps label the account" },
  ],
  angel: [
    { id: "api_key", text: "API key", secret: true, hint: "Angel One SmartAPI key" },
    { id: "client_code", text: "Client code", secret: false, hint: "Your Angel One client ID" },
    { id: "totp_secret", text: "Authenticator (TOTP) secret", secret: true, hint: "The text secret shown when the authenticator was set up, not a 6-digit code" },
    { id: "mpin", text: "MPIN", secret: true, hint: "Your Angel One PIN" },
  ],
}

export default function AccountsPage() {
  const qc = useQueryClient()
  const q = useQuery<AccountsData>({
    queryKey: ["broker-accounts"],
    queryFn: async () => { const r = await fetch(`${BASE}/api/broker/accounts`, { cache: "no-store" }); if (!r.ok) throw new Error(`accounts ${r.status}`); return r.json() },
    refetchInterval: 60000,
  })
  const [broker, setBroker] = useState<Broker>("hdfc")
  const [name, setName] = useState("")
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const prefix = broker === "hdfc" ? "HDFC" : "ANGEL"
  const accounts = q.data?.accounts ?? []
  const suggestion = (() => {
    for (let i = 1; i <= 9; i++) { const k = `${prefix}${i}`; if (!accounts.some(a => a.key === k && !a.needs_setup)) return k }
    return `${prefix}1`
  })()

  async function connect() {
    const account = (name || suggestion).trim().toUpperCase()
    setBusy(true); setMsg(null)
    try {
      const r = await fetch(`${BASE}/api/broker/accounts/add`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ account, ...vals }) })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j.detail || `error ${r.status}`)
      setMsg({ ok: true, text: `${j.account} connected. ${j.next || ""}` })
      setVals({}); setName("")                                   // the keys leave the page the moment they are sent
      qc.invalidateQueries({ queryKey: ["broker-accounts"] })
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message })
    } finally { setBusy(false) }
  }

  async function login(key: string) {
    setMsg(null)
    try {
      const r = await fetch(`${BASE}/api/broker/hdfc-login-url?key=${encodeURIComponent(key)}`, { cache: "no-store" })
      const j = await r.json()
      if (!r.ok) throw new Error(j.detail || `error ${r.status}`)
      window.location.href = j.url
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }) }
  }

  const inCount = accounts.filter(a => a.logged_in).length
  return (
    <div style={{ maxWidth: 560, margin: "0 auto", padding: "16px" }} data-page="broker-accounts">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, margin: 0 }}>Broker accounts</h1>
          <div style={{ fontSize: 13, color: "var(--text2)" }}>{inCount} of {accounts.length} logged in today</div>
        </div>
        <button style={btn} onClick={() => qc.invalidateQueries({ queryKey: ["broker-accounts"] })} aria-label="Refresh accounts"><RefreshCw size={16} /></button>
      </div>

      {q.error && <div style={{ ...card, borderColor: "var(--red)", color: "var(--red)" }}>Could not load accounts: {(q.error as Error).message}</div>}
      {q.data?.error && <div style={{ ...card, borderColor: "var(--red)", color: "var(--red)" }}>Shares CFO did not answer: {q.data.error}</div>}

      <div style={card} data-section="accounts">
        <div style={h}><ShieldCheck size={14} /> Accounts</div>
        {accounts.length === 0 && <div style={{ fontSize: 14 }}>No accounts yet. Add one below.</div>}
        {accounts.map(a => (
          <div key={a.key} data-account={a.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--border)" }}>
            <div>
              <div style={{ fontSize: 15 }}>{a.label || a.key} <span style={{ color: "var(--text2)", fontSize: 12 }}>{a.key} · {a.broker}{a.client_code ? ` · ${a.client_code}` : ""}</span></div>
              <div style={{ fontSize: 13, color: a.needs_setup ? "var(--red)" : a.logged_in ? "var(--green)" : "var(--text2)", display: "flex", alignItems: "center", gap: 5 }}>
                {a.logged_in ? <CheckCircle2 size={13} /> : <Circle size={13} />}
                {a.needs_setup ? "needs keys" : a.logged_in ? "logged in today" : "not logged in"}
              </div>
            </div>
            {!a.needs_setup && a.broker === "hdfc" && !a.logged_in && (
              <button style={btn} onClick={() => login(a.key)} aria-label={`Log in ${a.key}`}><LogIn size={15} style={{ marginRight: 6, verticalAlign: "middle" }} />Log in</button>
            )}
            {!a.needs_setup && a.broker === "angel" && !a.logged_in && <span style={{ fontSize: 12, color: "var(--text2)" }}>logs in by itself</span>}
          </div>
        ))}
        <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 8 }}>HDFC asks for a fresh code from your phone every day. I never see or store that code.</div>
      </div>

      <form style={card} data-section="add-account" onSubmit={e => { e.preventDefault(); connect() }} autoComplete="off">
        <div style={h}><KeyRound size={14} /> Add an account</div>
        <div role="radiogroup" aria-label="Broker" style={{ display: "flex", gap: 8 }}>
          {(["hdfc", "angel"] as Broker[]).map(b => (
            <button type="button" key={b} role="radio" aria-checked={broker === b} style={{ ...btn, flex: 1, borderColor: broker === b ? "var(--accent2)" : "var(--border2)" }}
              onClick={() => { setBroker(b); setVals({}) }}>{b === "hdfc" ? "HDFC Securities" : "Angel One"}</button>
          ))}
        </div>
        <label htmlFor="account_name" style={label}>Account name</label>
        <input id="account_name" name="account_name" aria-label="Account name" style={input} value={name} placeholder={suggestion}
          onChange={e => setName(e.target.value.toUpperCase())} autoCapitalize="characters" />
        <div style={{ fontSize: 12, color: "var(--text2)" }}>Starts with {prefix}. Leave empty to use {suggestion}.</div>
        {FIELDS[broker].map(f => (
          <div key={f.id}>
            <label htmlFor={f.id} style={label}>{f.text}{f.secret ? " (secret: type it yourself)" : ""}</label>
            <input id={f.id} name={f.id} aria-label={f.text} data-secret={f.secret ? "true" : "false"} type={f.secret ? "password" : "text"}
              autoComplete="off" autoCorrect="off" spellCheck={false} style={input} value={vals[f.id] ?? ""} onChange={e => setVals({ ...vals, [f.id]: e.target.value })} />
            <div style={{ fontSize: 12, color: "var(--text2)" }}>{f.hint}</div>
          </div>
        ))}
        <button type="submit" disabled={busy} style={{ ...btn, width: "100%", marginTop: 14, borderColor: "var(--accent2)" }} aria-label="Connect account">{busy ? "Connecting…" : "Connect"}</button>
        {msg && <div role="status" style={{ marginTop: 10, fontSize: 14, color: msg.ok ? "var(--green)" : "var(--red)" }}>{msg.text}</div>}
        <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 10 }}>
          Keys go straight to your server and are never shown again. Do not paste them in chat, email or WhatsApp.
        </div>
      </form>
    </div>
  )
}
