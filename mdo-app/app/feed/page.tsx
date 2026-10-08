"use client"

// The Decision Feed — the one place decisions arrive.
//
// Everything that needs Aman, from every domain, critical first. An item may carry a
// drafted action he approves with one tap. Money actions are refused by the backend as
// policy, so this page shows them as read-only and says why rather than offering a
// button that would fail.

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Inbox, AlertTriangle, Info, Bell, Check, X, ChevronRight,
  ShieldOff, Wifi, WifiOff, Loader2,
} from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

type FeedItem = {
  id: number
  key: string
  source: string
  domain: string
  severity: "critical" | "important" | "info"
  title: string
  body: string
  evidence: any[]
  action_type: string
  action_payload: Record<string, any>
  action_kind: "" | "internal" | "outward" | "money"
  status: string
  notify_policy: string
  notified_at: string | null
  decided_at: string | null
  result: string
  created_at: string
}
type Counts = { critical: number; important: number; info: number; pending_total: number }
type FeedResponse = {
  items: FeedItem[]
  counts: Counts
  actions: Record<string, string>
  money_actions_enabled: boolean
}
type Tunnel = { site: string; label: string; up: boolean; detail: string; proxy: string }

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { cache: "no-store", ...init })
  if (!r.ok) throw new Error(String(r.status))
  return r.json()
}

const SEV = {
  critical: { color: "var(--red)", icon: AlertTriangle, label: "Critical" },
  important: { color: "var(--amber)", icon: Bell, label: "Important" },
  info: { color: "var(--green)", icon: Info, label: "Info" },
} as const

function ago(ts: string) {
  if (!ts) return ""
  const t = new Date(ts.replace(" ", "T")).getTime()
  const mins = Math.floor((Date.now() - t) / 60000)
  if (mins < 60) return `${Math.max(mins, 0)}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
  return `${Math.floor(mins / 1440)}d ago`
}

// What approving this item will actually do, in plain words. An outward action reaches
// a real person, so its full text is shown before the tap — never summarised away.
function ActionPreview({ item }: { item: FeedItem }) {
  if (!item.action_type) return null
  const money = item.action_kind === "money"
  const outward = item.action_kind === "outward"
  return (
    <div style={{
      marginTop: 12, padding: 12, borderRadius: 8,
      border: `1px solid ${money ? "var(--red)" : "var(--border)"}`,
      background: "var(--bg-subtle)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, opacity: 0.8 }}>
        {money ? <ShieldOff size={14} /> : <ChevronRight size={14} />}
        <strong>Proposed action</strong>
        <code style={{ fontSize: 11 }}>{item.action_type}</code>
        <span style={{ opacity: 0.6 }}>({item.action_kind || "unknown"})</span>
      </div>

      {outward && (
        <div style={{ marginTop: 8, fontSize: 12, opacity: 0.85 }}>
          This reaches a real person. The exact message is below — read it before approving.
        </div>
      )}

      <pre style={{
        marginTop: 8, marginBottom: 0, fontSize: 12, whiteSpace: "pre-wrap",
        wordBreak: "break-word", opacity: 0.9,
      }}>
        {JSON.stringify(item.action_payload, null, 2)}
      </pre>

      {money && (
        <div style={{ marginTop: 8, fontSize: 12, color: "var(--red)" }}>
          Money actions never execute from an approval tap. This item is informational —
          act through the capital surface deliberately.
        </div>
      )}
    </div>
  )
}

function ItemCard({ item, onDecide, busy }: {
  item: FeedItem
  onDecide: (id: number, decision: "approve" | "reject") => void
  busy: number | null
}) {
  const [open, setOpen] = useState(false)
  const sev = SEV[item.severity] ?? SEV.info
  const Icon = sev.icon
  const isBusy = busy === item.id
  const money = item.action_kind === "money"

  return (
    <div style={{
      border: "1px solid var(--border)", borderLeft: `3px solid ${sev.color}`,
      borderRadius: 8, padding: 14, marginBottom: 10, background: "var(--bg-card)",
    }}>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: "pointer" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Icon size={16} color={sev.color} />
          <strong style={{ fontSize: 15 }}>{item.title}</strong>
        </div>
        <div style={{ marginTop: 4, fontSize: 12, opacity: 0.6, display: "flex", gap: 10, flexWrap: "wrap" }}>
          <span>{item.domain}</span>
          {item.source && <span>via {item.source}</span>}
          <span>{ago(item.created_at)}</span>
          {item.notified_at && <span>pushed</span>}
        </div>
      </div>

      {(open || item.severity === "critical") && (
        <>
          {item.body && (
            <p style={{ marginTop: 10, marginBottom: 0, fontSize: 13, opacity: 0.9 }}>{item.body}</p>
          )}

          {item.evidence?.length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary style={{ fontSize: 12, opacity: 0.7, cursor: "pointer" }}>
                What this is based on
              </summary>
              <pre style={{ fontSize: 11, whiteSpace: "pre-wrap", opacity: 0.8 }}>
                {JSON.stringify(item.evidence, null, 2)}
              </pre>
            </details>
          )}

          <ActionPreview item={item} />

          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              onClick={() => onDecide(item.id, "approve")}
              disabled={isBusy || money}
              title={money ? "Money actions cannot be approved here" : undefined}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "7px 14px",
                borderRadius: 6, border: "1px solid var(--border)", fontSize: 13,
                cursor: isBusy || money ? "not-allowed" : "pointer",
                opacity: money ? 0.45 : 1,
                background: money ? "transparent" : "var(--green)",
                color: money ? "inherit" : "#fff",
              }}>
              {isBusy ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
              {item.action_type && !money ? "Approve & run" : "Acknowledge"}
            </button>
            <button
              onClick={() => onDecide(item.id, "reject")}
              disabled={isBusy}
              style={{
                display: "flex", alignItems: "center", gap: 6, padding: "7px 14px",
                borderRadius: 6, border: "1px solid var(--border)", fontSize: 13,
                cursor: isBusy ? "not-allowed" : "pointer", background: "transparent",
              }}>
              <X size={14} /> Dismiss
            </button>
          </div>
        </>
      )}
    </div>
  )
}

export default function FeedPage() {
  const qc = useQueryClient()
  const [busy, setBusy] = useState<number | null>(null)
  const [note, setNote] = useState<string>("")

  const { data, isLoading } = useQuery({
    queryKey: ["decision-feed"],
    queryFn: () => apiFetch<FeedResponse>(`${BASE}/api/feed`),
    refetchInterval: 30_000,
  })

  // Site links matter here: a dead tunnel means site numbers are missing, not merely
  // stale, and the feed should say so rather than look complete.
  const { data: sites } = useQuery({
    queryKey: ["site-links"],
    queryFn: () => apiFetch<{ tunnels: { sites: Tunnel[] } }>(`${BASE}/api/sites`),
    refetchInterval: 120_000,
  })

  async function onDecide(id: number, decision: "approve" | "reject") {
    setBusy(id)
    setNote("")
    try {
      const out = await apiFetch<any>(`${BASE}/api/feed/${id}/${decision}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      })
      const outcome = out?.outcome ?? "done"
      setNote(
        outcome === "executed" ? "Done — action executed."
        : outcome === "refused" ? `Refused: ${out.reason ?? "policy"}`
        : outcome === "failed" ? `Failed: ${out.error ?? out.result}`
        : outcome === "already_decided" ? "Already handled."
        : outcome === "rejected" ? "Dismissed."
        : "Acknowledged."
      )
      await qc.invalidateQueries({ queryKey: ["decision-feed"] })
    } catch (e: any) {
      setNote(`Error: ${e.message}`)
    } finally {
      setBusy(null)
    }
  }

  const items = data?.items ?? []
  const counts = data?.counts
  const downSites = (sites?.tunnels?.sites ?? []).filter(s => !s.up)

  return (
    <div style={{ padding: 20, maxWidth: 860, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <Inbox size={22} />
        <h1 style={{ fontSize: 22, margin: 0 }}>Decision Feed</h1>
      </div>
      <p style={{ fontSize: 13, opacity: 0.7, marginTop: 0 }}>
        Everything waiting on you, across capital and business. Critical first.
      </p>

      {counts && (
        <div style={{ display: "flex", gap: 14, margin: "14px 0", fontSize: 13, flexWrap: "wrap" }}>
          {(["critical", "important", "info"] as const).map(s => (
            <span key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{
                width: 8, height: 8, borderRadius: 4, background: SEV[s].color,
                display: "inline-block",
              }} />
              {counts[s]} {SEV[s].label.toLowerCase()}
            </span>
          ))}
        </div>
      )}

      {/* A dead site link is itself a finding — surface it at the top of the feed. */}
      {downSites.length > 0 && (
        <div style={{
          border: "1px solid var(--amber)", borderRadius: 8, padding: 12,
          marginBottom: 14, fontSize: 13,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <WifiOff size={15} color="var(--amber)" />
            <strong>Site link down</strong>
          </div>
          {downSites.map(s => (
            <div key={s.site} style={{ marginTop: 6, opacity: 0.85 }}>
              {s.label} — readings from this site are missing, not stale. {s.detail}
            </div>
          ))}
        </div>
      )}
      {downSites.length === 0 && sites && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12,
                      opacity: 0.6, marginBottom: 14 }}>
          <Wifi size={13} /> Both site links up
        </div>
      )}

      {note && (
        <div style={{
          padding: "8px 12px", borderRadius: 6, marginBottom: 12, fontSize: 13,
          border: "1px solid var(--border)",
        }}>{note}</div>
      )}

      {isLoading && <p style={{ opacity: 0.6 }}>Loading…</p>}

      {!isLoading && items.length === 0 && (
        <div style={{
          textAlign: "center", padding: "48px 20px", border: "1px dashed var(--border)",
          borderRadius: 10, opacity: 0.75,
        }}>
          <Check size={28} style={{ opacity: 0.5 }} />
          <p style={{ marginBottom: 4, marginTop: 10, fontSize: 15 }}>Nothing needs you.</p>
          <p style={{ margin: 0, fontSize: 13, opacity: 0.7 }}>
            The agents are watching. Anything critical will reach your phone.
          </p>
        </div>
      )}

      {items.map(it => (
        <ItemCard key={it.id} item={it} onDecide={onDecide} busy={busy} />
      ))}

      {data && !data.money_actions_enabled && items.some(i => i.action_kind === "money") && (
        <p style={{ fontSize: 12, opacity: 0.6, marginTop: 16 }}>
          Money actions are disabled by policy and cannot be approved from this screen.
        </p>
      )}
    </div>
  )
}
