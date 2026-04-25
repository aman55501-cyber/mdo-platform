"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { MessageSquare, Wifi, WifiOff, RefreshCw, QrCode } from "lucide-react"

const BASE     = process.env.NEXT_PUBLIC_API_URL  || "http://localhost:8501"
const WA_BRIDGE = process.env.NEXT_PUBLIC_WA_URL  || ""

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" })
  if (!res.ok) throw new Error(res.status.toString())
  return res.json()
}

const GROUP_COLORS: Record<string, string> = {
  "vedanta": "#f59e0b",
  "rake status": "#6366f1",
  "rake placement": "#06b6d4",
  "apl raigarh": "#22c55e",
  "rkm": "#ef4444",
  "shifting": "#8b5cf6",
}

function groupColor(name: string) {
  const lower = name.toLowerCase()
  for (const [key, color] of Object.entries(GROUP_COLORS)) {
    if (lower.includes(key)) return color
  }
  return "var(--accent2)"
}

function timeAgo(ts: string) {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function OpsFeedPage() {
  const [activeGroup, setActiveGroup] = useState("ALL")
  const [showQR, setShowQR] = useState(false)

  const { data: groupsData } = useQuery({
    queryKey: ["wa-groups"],
    queryFn: () => apiFetch<{ groups: any[] }>(`${BASE}/api/whatsapp/groups`),
    refetchInterval: 30_000,
  })

  const { data: msgsData, isLoading, refetch } = useQuery({
    queryKey: ["wa-messages", activeGroup],
    queryFn: () => {
      const g = activeGroup !== "ALL" ? `?group=${encodeURIComponent(activeGroup)}` : ""
      return apiFetch<{ messages: any[]; count: number }>(`${BASE}/api/whatsapp/messages${g}`)
    },
    refetchInterval: 15_000,
  })

  const { data: qrData } = useQuery({
    queryKey: ["wa-qr"],
    queryFn: () => WA_BRIDGE
      ? apiFetch<{ connected: boolean; qr: string | null }>(`${WA_BRIDGE}/api/whatsapp/qr`)
      : Promise.resolve({ connected: false, qr: null }),
    refetchInterval: 10_000,
    enabled: showQR || true,
  })

  const groups  = groupsData?.groups || []
  const messages = msgsData?.messages || []
  const connected = qrData?.connected || false

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto" }}>

      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <MessageSquare size={20} style={{ color: "var(--accent2)" }} />
          <div>
            <h1 className="text-2xl font-bold">VWLR Ops Feed</h1>
            <div style={{ fontSize: 12, color: "var(--text2)" }}>
              Live from your WhatsApp site groups
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
            style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            {connected
              ? <><Wifi size={12} style={{ color: "var(--green)" }} /><span style={{ fontSize: 12, color: "var(--green)" }}>Connected</span></>
              : <><WifiOff size={12} style={{ color: "var(--red)" }} /><span style={{ fontSize: 12, color: "var(--red)" }}>Not connected</span></>
            }
          </div>
          {!connected && (
            <button onClick={() => setShowQR(v => !v)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium"
              style={{ background: "var(--accent)", color: "#fff" }}>
              <QrCode size={13} /> Scan QR
            </button>
          )}
          <button onClick={() => refetch()} style={{ color: "var(--text2)" }}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* QR scan panel */}
      {showQR && !connected && (
        <div className="rounded-xl p-6 mb-6 text-center" style={{ background: "var(--bg2)", border: "1px solid var(--accent)" }}>
          <div className="font-semibold mb-2">Scan with WhatsApp on +917000512030</div>
          <div style={{ fontSize: 12, color: "var(--text2)", marginBottom: 16 }}>
            Open WhatsApp → Settings → Linked Devices → Link a Device → scan this QR
          </div>
          {qrData?.qr ? (
            <img src={qrData.qr} alt="WhatsApp QR" style={{ width: 220, height: 220, margin: "0 auto", borderRadius: 12 }} />
          ) : (
            <div style={{ width: 220, height: 220, margin: "0 auto", background: "var(--bg3)", borderRadius: 12,
              display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text2)", fontSize: 13 }}>
              {WA_BRIDGE ? "Loading QR…" : "Deploy WhatsApp bridge first"}
            </div>
          )}
          <div style={{ fontSize: 11, color: "var(--text2)", marginTop: 12 }}>
            QR refreshes every 20 seconds. Once scanned, this panel closes automatically.
          </div>
        </div>
      )}

      {/* Group tabs */}
      {groups.length > 0 && (
        <div className="flex gap-2 mb-5 flex-wrap">
          <button onClick={() => setActiveGroup("ALL")}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{
              background: activeGroup === "ALL" ? "var(--accent)" : "var(--bg2)",
              color: activeGroup === "ALL" ? "#fff" : "var(--text2)",
              border: `1px solid ${activeGroup === "ALL" ? "var(--accent)" : "var(--border)"}`,
            }}>
            All Groups
          </button>
          {groups.map((g: any) => (
            <button key={g.group_name} onClick={() => setActiveGroup(g.group_name)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5"
              style={{
                background: activeGroup === g.group_name ? groupColor(g.group_name) + "22" : "var(--bg2)",
                color: activeGroup === g.group_name ? groupColor(g.group_name) : "var(--text2)",
                border: `1px solid ${activeGroup === g.group_name ? groupColor(g.group_name) : "var(--border)"}`,
              }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: groupColor(g.group_name), flexShrink: 0 }} />
              {g.group_name}
              <span style={{ fontSize: 10, opacity: 0.7 }}>({g.msg_count})</span>
            </button>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && messages.length === 0 && (
        <div className="rounded-xl p-10 text-center" style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
          <MessageSquare size={32} style={{ color: "var(--text2)", margin: "0 auto 12px" }} />
          <div className="font-semibold mb-2">No messages yet</div>
          <div style={{ fontSize: 13, color: "var(--text2)", maxWidth: 380, margin: "0 auto" }}>
            Scan the QR code above to link your WhatsApp (+917000512030).
            Messages from your 6 VWLR groups will appear here in real time.
          </div>
        </div>
      )}

      {/* Message feed */}
      <div className="space-y-2">
        {messages.map((msg: any) => (
          <div key={msg.id} className="rounded-xl p-3 flex gap-3"
            style={{ background: "var(--bg2)", border: "1px solid var(--border)" }}>
            <div style={{ width: 3, borderRadius: 3, background: groupColor(msg.group_name), flexShrink: 0 }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <span style={{ fontSize: 11, fontWeight: 700, color: groupColor(msg.group_name) }}>
                    {msg.group_name}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text2)" }}>· {msg.sender}</span>
                </div>
                <span style={{ fontSize: 11, color: "var(--text2)", flexShrink: 0 }}>
                  {timeAgo(msg.timestamp || msg.created_at)}
                </span>
              </div>
              <div style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>
                {msg.text}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
