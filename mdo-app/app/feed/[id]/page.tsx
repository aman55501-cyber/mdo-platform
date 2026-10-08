"use client"

// Where a push notification lands. One item, its evidence, its drafted action, and the
// two buttons — so the tap from the phone goes straight to the decision rather than to
// a list he then has to search.

import { useState, use } from "react"
import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import {
  ArrowLeft, AlertTriangle, Info, Bell, Check, X, ShieldOff, Loader2,
} from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type AuditRow = { id: number; event: string; detail: string; at: string }
type FeedItem = {
  id: number; key: string; source: string; domain: string
  severity: "critical" | "important" | "info"
  title: string; body: string; evidence: any[]
  action_type: string; action_payload: Record<string, any>
  action_kind: "" | "internal" | "outward" | "money"
  status: string; result: string; created_at: string; decided_at: string | null
  audit: AuditRow[]
}

const SEV = {
  critical: { color: "var(--red)", icon: AlertTriangle, label: "Critical" },
  important: { color: "var(--amber)", icon: Bell, label: "Important" },
  info: { color: "var(--green)", icon: Info, label: "Info" },
} as const

const DECIDED = ["approved", "rejected", "executed", "failed", "refused", "expired"]

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { cache: "no-store", ...init })
  if (!r.ok) throw new Error(String(r.status))
  return r.json()
}

export default function FeedItemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState("")

  const { data: item, isLoading, refetch } = useQuery({
    queryKey: ["feed-item", id],
    queryFn: () => apiFetch<FeedItem>(`${BASE}/api/feed/${id}`),
  })

  async function decide(decision: "approve" | "reject") {
    setBusy(true)
    setNote("")
    try {
      const out = await apiFetch<any>(`${BASE}/api/feed/${id}/${decision}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      const o = out?.outcome
      setNote(
        o === "executed" ? "Done — action executed."
        : o === "refused" ? `Refused: ${out.reason}`
        : o === "failed" ? `Failed: ${out.error ?? out.result}`
        : o === "already_decided" ? "Already handled."
        : o === "rejected" ? "Dismissed."
        : "Acknowledged."
      )
      await refetch()
    } catch (e: any) {
      setNote(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  if (isLoading) return <div style={{ padding: 24, opacity: 0.6 }}>Loading…</div>
  if (!item) return (
    <div style={{ padding: 24 }}>
      <p>That item no longer exists.</p>
      <Link href="/feed">← Back to the feed</Link>
    </div>
  )

  const sev = SEV[item.severity] ?? SEV.info
  const Icon = sev.icon
  const money = item.action_kind === "money"
  const settled = DECIDED.includes(item.status)

  return (
    <div style={{ padding: 20, maxWidth: 720, margin: "0 auto" }}>
      <Link href="/feed" style={{
        display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13,
        opacity: 0.7, marginBottom: 16,
      }}>
        <ArrowLeft size={14} /> Decision Feed
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Icon size={20} color={sev.color} />
        <h1 style={{ fontSize: 20, margin: 0 }}>{item.title}</h1>
      </div>
      <div style={{ marginTop: 6, fontSize: 12, opacity: 0.6, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <span>{sev.label}</span><span>{item.domain}</span>
        {item.source && <span>via {item.source}</span>}
        <span>status: {item.status}</span>
      </div>

      {item.body && <p style={{ marginTop: 16, fontSize: 14 }}>{item.body}</p>}

      {item.evidence?.length > 0 && (
        <section style={{ marginTop: 16 }}>
          <h2 style={{ fontSize: 13, opacity: 0.7, marginBottom: 6 }}>What this is based on</h2>
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", opacity: 0.85 }}>
            {JSON.stringify(item.evidence, null, 2)}
          </pre>
        </section>
      )}

      {item.action_type && (
        <section style={{
          marginTop: 16, padding: 14, borderRadius: 8,
          border: `1px solid ${money ? "var(--red)" : "var(--border)"}`,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            {money && <ShieldOff size={14} color="var(--red)" />}
            <strong>Proposed action</strong>
            <code style={{ fontSize: 12 }}>{item.action_type}</code>
            <span style={{ opacity: 0.6, fontSize: 12 }}>({item.action_kind})</span>
          </div>
          {item.action_kind === "outward" && (
            <p style={{ fontSize: 12, opacity: 0.85, marginBottom: 0 }}>
              This reaches a real person. Read the exact content before approving.
            </p>
          )}
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {JSON.stringify(item.action_payload, null, 2)}
          </pre>
          {money && (
            <p style={{ fontSize: 12, color: "var(--red)", marginBottom: 0 }}>
              Money actions never execute from an approval tap.
            </p>
          )}
        </section>
      )}

      {note && (
        <div style={{
          marginTop: 16, padding: "8px 12px", borderRadius: 6, fontSize: 13,
          border: "1px solid var(--border)",
        }}>{note}</div>
      )}

      {!settled && (
        <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
          <button onClick={() => decide("approve")} disabled={busy || money}
            style={{
              display: "flex", alignItems: "center", gap: 6, padding: "9px 18px",
              borderRadius: 6, border: "1px solid var(--border)", fontSize: 14,
              cursor: busy || money ? "not-allowed" : "pointer",
              opacity: money ? 0.45 : 1,
              background: money ? "transparent" : "var(--green)",
              color: money ? "inherit" : "#fff",
            }}>
            {busy ? <Loader2 size={15} /> : <Check size={15} />}
            {item.action_type && !money ? "Approve & run" : "Acknowledge"}
          </button>
          <button onClick={() => decide("reject")} disabled={busy}
            style={{
              display: "flex", alignItems: "center", gap: 6, padding: "9px 18px",
              borderRadius: 6, border: "1px solid var(--border)", fontSize: 14,
              cursor: busy ? "not-allowed" : "pointer", background: "transparent",
            }}>
            <X size={15} /> Dismiss
          </button>
        </div>
      )}

      {settled && item.result && (
        <p style={{ marginTop: 18, fontSize: 13, opacity: 0.8 }}>
          <strong>Result:</strong> {item.result}
        </p>
      )}

      {item.audit?.length > 0 && (
        <section style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 13, opacity: 0.7, marginBottom: 6 }}>Trail</h2>
          <ul style={{ fontSize: 12, opacity: 0.75, paddingLeft: 18, margin: 0 }}>
            {item.audit.map(a => (
              <li key={a.id}>{a.at} — <strong>{a.event}</strong>{a.detail ? ` — ${a.detail}` : ""}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
