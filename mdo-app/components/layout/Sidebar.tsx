"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState, useEffect } from "react"
import {
  LayoutDashboard, Brain, TrendingUp, MessageSquare, ShieldAlert,
  Wifi, WifiOff, Building2, Rss, CheckSquare, Landmark, ExternalLink, Sun
} from "lucide-react"
import { useLiveStore } from "@/lib/store"

const NAV_SECTIONS = [
  {
    label: "Command",
    items: [
      { href: "/",           icon: LayoutDashboard, label: "Dashboard"        },
      { href: "/feeds",      icon: Rss,             label: "Live Feeds"       },
      { href: "/intel",      icon: Brain,           label: "Intel Centre"     },
    ]
  },
  {
    label: "Sales",
    items: [
      { href: "/vwlr",       icon: Building2,       label: "VWLR — Washery"  },
    ]
  },
  {
    label: "Operations",
    items: [
      { href: "/ops",        icon: CheckSquare,     label: "Task Board"       },
      { href: "/entities",   icon: Landmark,        label: "Entities (26)"    },
      { href: "/compliance", icon: ShieldAlert,     label: "Compliance"       },
      { href: "/hotel",      icon: Building2,       label: "Hotel ANS"        },
    ]
  },
  {
    label: "Capital",
    items: [
      { href: "/morning",    icon: Sun,             label: "Morning Setup"    },
      { href: "/aditi",      icon: TrendingUp,      label: "Aditi Investments"},
    ]
  },
  {
    label: "AI",
    items: [
      { href: "/grok",       icon: MessageSquare,   label: "Grok AI"          },
    ]
  },
]

const QUICK_LINKS = [
  { label: "NSE",        url: "https://www.nseindia.com"    },
  { label: "HDFC SKY",  url: "https://hdfcsky.hdfcsec.com" },
  { label: "Tender247", url: "https://tender247.com"       },
  { label: "GeM",       url: "https://gem.gov.in"          },
  { label: "IBBI",      url: "https://ibbi.gov.in"         },
  { label: "NCLT",      url: "https://nclt.gov.in"         },
  { label: "MCA",       url: "https://www.mca.gov.in"      },
  { label: "GST",       url: "https://www.gst.gov.in"      },
]

function ISTClock() {
  const [time, setTime] = useState("")
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      // IST = UTC + 5:30
      const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000))
      setTime(ist.toISOString().substring(11, 19))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
      IST {time}
    </span>
  )
}

export function Sidebar() {
  const path      = usePathname()
  const connected = useLiveStore((s) => s.connected)

  return (
    <aside
      className="flex flex-col shrink-0 overflow-y-auto"
      style={{
        width: 220,
        background: "var(--bg2)",
        borderRight: "1px solid var(--border)",
      }}
    >
      {/* Brand header */}
      <div
        className="px-5 py-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <div
          style={{
            fontFamily: "'Cormorant Garamond', Georgia, serif",
            fontWeight: 300,
            fontSize: 22,
            letterSpacing: "8px",
            color: "var(--accent)",
            lineHeight: 1.2,
          }}
        >
          A M A N
        </div>
        <div
          style={{
            fontSize: 10,
            color: "var(--text2)",
            marginTop: 4,
            letterSpacing: "0.04em",
          }}
        >
          Raigarh · CG
        </div>
      </div>

      {/* Nav sections */}
      <nav className="flex-1 py-2 px-2">
        {NAV_SECTIONS.map(({ label, items }) => (
          <div key={label} className="mb-3">
            <div
              className="px-3 py-1 uppercase tracking-wider"
              style={{
                color: "var(--text2)",
                fontSize: 9,
                fontWeight: 500,
                opacity: 0.4,
                letterSpacing: "0.12em",
              }}
            >
              {label}
            </div>
            {items.map(({ href, icon: Icon, label: lbl }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href)
              return (
                <Link
                  key={href}
                  href={href}
                  className="flex items-center gap-3 px-3 py-2 rounded text-sm font-medium transition-colors"
                  style={{
                    background: active ? "var(--bg3)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text2)",
                  }}
                  onMouseEnter={(e) => {
                    if (!active) (e.currentTarget as HTMLElement).style.background = "#6366f115"
                  }}
                  onMouseLeave={(e) => {
                    if (!active) (e.currentTarget as HTMLElement).style.background = "transparent"
                  }}
                >
                  <Icon size={14} strokeWidth={1.5} />
                  {lbl}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      {/* Quick external links / Portals */}
      <div
        className="px-3 py-3 shrink-0"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div
          className="uppercase tracking-wider px-1 mb-2"
          style={{
            color: "var(--text2)",
            fontSize: 9,
            fontWeight: 500,
            opacity: 0.4,
            letterSpacing: "0.12em",
          }}
        >
          Portals
        </div>
        <div className="grid grid-cols-2 gap-1">
          {QUICK_LINKS.map(({ label, url }) => (
            <a
              key={label}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 px-2 py-1.5 rounded text-xs transition-colors"
              style={{ color: "var(--text2)", background: "transparent" }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = "#6366f115"
                ;(e.currentTarget as HTMLElement).style.color = "var(--accent)"
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = "transparent"
                ;(e.currentTarget as HTMLElement).style.color = "var(--text2)"
              }}
            >
              <ExternalLink size={9} style={{ flexShrink: 0 }} />
              {label}
            </a>
          ))}
        </div>
      </div>

      {/* IST clock */}
      <div
        className="px-4 py-2 shrink-0"
        style={{
          borderTop: "1px solid var(--border)",
          color: "var(--text2)",
        }}
      >
        <ISTClock />
      </div>

      {/* Live connection status */}
      <div
        className="px-4 py-2 text-xs flex items-center gap-2 shrink-0"
        style={{ borderTop: "1px solid var(--border)", color: "var(--text2)" }}
      >
        {connected ? (
          <>
            <Wifi size={12} style={{ color: "var(--accent)" }} />
            Backend live
          </>
        ) : (
          <>
            <WifiOff size={12} style={{ color: "var(--red)" }} />
            Run: python mdo_server.py
          </>
        )}
      </div>
    </aside>
  )
}
