"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState, useEffect } from "react"
import {
  LayoutDashboard, Brain, TrendingUp, MessageSquare, ShieldAlert,
  Building2, Rss, CheckSquare, Landmark, ExternalLink, Sun, Network,
  Menu, X, Sparkles, FileText, Wallet,
} from "lucide-react"
import { useLiveStore } from "@/lib/store"
import { NextStepsMini } from "@/components/RemainingSteps"

const NAV_SECTIONS = [
  {
    label: "Command",
    items: [
      { href: "/",           icon: LayoutDashboard, label: "Dashboard"        },
      { href: "/lifemap",    icon: Network,         label: "Life LLM Map"     },
      { href: "/briefing",   icon: ShieldAlert,     label: "Daily Briefing"   },
      { href: "/reports",    icon: FileText,        label: "Agent Reports"    },
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
      { href: "/ops-feed",   icon: MessageSquare,   label: "VWLR Ops Feed"   },
      { href: "/entities",   icon: Landmark,        label: "Entities (26)"    },
      { href: "/compliance", icon: ShieldAlert,     label: "Compliance"       },
      { href: "/hotel",      icon: Building2,       label: "Hotel ANS"        },
    ]
  },
  {
    label: "Capital",
    items: [
      { href: "/networth",   icon: Wallet,          label: "Live Net Worth"   },
      { href: "/morning",    icon: Sun,             label: "Morning Setup"    },
      { href: "/aditi",      icon: TrendingUp,      label: "Aditi Investments"},
    ]
  },
  {
    label: "Intelligence",
    items: [
      { href: "/news",       icon: Rss,             label: "Portfolio News"   },
      { href: "/grok",       icon: Sparkles,        label: "MDO Brain"        },
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

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="brain-orb shrink-0" style={{ width: 26, height: 26 }} />
      <div>
        <div className="grad-text"
          style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", fontWeight: 400, fontSize: 19, letterSpacing: "7px", lineHeight: 1.15 }}>
          AMAN
        </div>
        <div style={{ fontSize: 9, color: "var(--text2)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
          Decision Office
        </div>
      </div>
    </div>
  )
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const path      = usePathname()
  const connected = useLiveStore((s) => s.connected)

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-4 shrink-0" style={{ borderBottom: "1px solid var(--border)" }}>
        <Brand />
      </div>

      <nav className="flex-1 overflow-y-auto py-3 px-2.5">
        {NAV_SECTIONS.map(({ label, items }) => (
          <div key={label} className="mb-4">
            <div className="px-3 pb-1.5 uppercase"
              style={{ color: "var(--text2)", fontSize: 9, fontWeight: 600, opacity: 0.45, letterSpacing: "0.14em" }}>
              {label}
            </div>
            {items.map(({ href, icon: Icon, label: lbl }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href)
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onNavigate}
                  className="relative flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all"
                  style={{
                    background: active ? "rgba(109,106,248,0.12)" : "transparent",
                    color: active ? "var(--accent2)" : "var(--text2)",
                    marginBottom: 1,
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      const el = e.currentTarget as HTMLElement
                      el.style.background = "rgba(143,140,255,0.06)"
                      el.style.color = "var(--text)"
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      const el = e.currentTarget as HTMLElement
                      el.style.background = "transparent"
                      el.style.color = "var(--text2)"
                    }
                  }}
                >
                  {active && (
                    <span aria-hidden style={{
                      position: "absolute", left: 0, top: "22%", bottom: "22%", width: 2.5,
                      borderRadius: 4, background: "var(--accent-grad)",
                    }} />
                  )}
                  <Icon size={14} strokeWidth={1.8} />
                  {lbl}
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      <NextStepsMini />

      <div className="px-3 py-3 shrink-0" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="uppercase px-1 mb-2"
          style={{ color: "var(--text2)", fontSize: 9, fontWeight: 600, opacity: 0.45, letterSpacing: "0.14em" }}>
          Portals
        </div>
        <div className="grid grid-cols-2 gap-1">
          {QUICK_LINKS.map(({ label, url }) => (
            <a key={label} href={url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] transition-colors"
              style={{ color: "var(--text2)" }}
              onMouseEnter={(e) => {
                const el = e.currentTarget as HTMLElement
                el.style.background = "rgba(143,140,255,0.07)"
                el.style.color = "var(--accent2)"
              }}
              onMouseLeave={(e) => {
                const el = e.currentTarget as HTMLElement
                el.style.background = "transparent"
                el.style.color = "var(--text2)"
              }}>
              <ExternalLink size={9} style={{ flexShrink: 0 }} />
              {label}
            </a>
          ))}
        </div>
      </div>

      <div className="px-4 py-2.5 shrink-0 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--border)", color: "var(--text2)" }}>
        <ISTClock />
        <span className="flex items-center gap-1.5 text-[10px] font-semibold" style={{ letterSpacing: "0.08em" }}>
          <span className={connected ? "live-dot" : ""} style={{
            width: 7, height: 7, borderRadius: 9999,
            background: connected ? "var(--green)" : "var(--red)", display: "inline-block",
          }} />
          <span style={{ color: connected ? "var(--green)" : "var(--red)" }}>
            {connected ? "LIVE" : "OFFLINE"}
          </span>
        </span>
      </div>
    </div>
  )
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const path = usePathname()
  useEffect(() => { setMobileOpen(false) }, [path])

  return (
    <>
      {/* Desktop rail */}
      <aside className="hidden md:flex flex-col shrink-0"
        style={{ width: 224, background: "rgba(10,12,20,0.75)", borderRight: "1px solid var(--border)", backdropFilter: "blur(14px)" }}>
        <SidebarBody />
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-40 glass flex items-center justify-between px-4"
        style={{ height: 54 }}>
        <Brand />
        <button onClick={() => setMobileOpen(true)} aria-label="Open menu"
          style={{ color: "var(--text)", background: "none", border: "none", padding: 8, cursor: "pointer" }}>
          <Menu size={20} />
        </button>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50"
          style={{ background: "rgba(4,5,9,0.6)", backdropFilter: "blur(4px)" }}
          onMouseDown={e => { if (e.target === e.currentTarget) setMobileOpen(false) }}>
          <aside className="absolute left-0 top-0 bottom-0 flex flex-col"
            style={{ width: 264, background: "#0b0d15", borderRight: "1px solid var(--border)", boxShadow: "8px 0 40px rgba(0,0,0,0.5)" }}>
            <button onClick={() => setMobileOpen(false)} aria-label="Close menu"
              className="absolute z-10"
              style={{ top: 12, right: 12, color: "var(--text2)", background: "none", border: "none", padding: 6, cursor: "pointer" }}>
              <X size={18} />
            </button>
            <SidebarBody onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
    </>
  )
}
