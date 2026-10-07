"use client"

import { useQuery } from "@tanstack/react-query"
import { Bot, Database, HardDrive, IndianRupee, Skull, CheckCircle2, Clock, Brain, ListChecks } from "lucide-react"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"

async function getJSON(path: string) {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store" })
  if (!r.ok) throw new Error(`${path} → ${r.status}`)
  return r.json()
}

function ago(iso?: string | null) {
  if (!iso) return "never"
  const t = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").getTime()
  const m = Math.round((Date.now() - t) / 60000)
  if (m < 1) return "just now"
  if (m < 60) return `${m}m ago`
  if (m < 48 * 60) return `${Math.round(m / 60)}h ago`
  return `${Math.round(m / 1440)}d ago`
}
function until(iso?: string | null) {
  if (!iso) return "—"
  const m = Math.round((new Date(iso).getTime() - Date.now()) / 60000)
  if (m < 0) return `${Math.abs(m)}m late`
  if (m < 60) return `in ${m}m`
  return `in ${Math.round(m / 60)}h`
}
const STATUS_COLOR: Record<string, string> = {
  clean: "var(--green)", reported: "var(--cyan)", error: "var(--red)", paused: "var(--amber)",
  warning: "var(--amber)", disabled: "var(--text2)", never: "var(--text2)",
}

function Card({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--card)" }}>
      <div className="flex items-center gap-2 mb-3 text-sm font-semibold"><Icon size={15} />{title}</div>
      {children}
    </div>
  )
}

export default function FleetPage() {
  const fleet = useQuery({ queryKey: ["fleet"], queryFn: () => getJSON("/api/fleet"), refetchInterval: 60000 })
  const spend = useQuery({ queryKey: ["spend"], queryFn: () => getJSON("/api/spend"), refetchInterval: 60000 })
  const memory = useQuery({ queryKey: ["cos-memory"], queryFn: () => getJSON("/api/cos/memory"), refetchInterval: 120000 })
  const jobs = useQuery({ queryKey: ["cos-jobs"], queryFn: () => getJSON("/api/cos/jobs?status=open"), refetchInterval: 60000 })

  const f = fleet.data, s = spend.data, m = memory.data
  const dead: string[] = f?.dead || []

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2"><Bot size={20} /> Fleet &amp; Memory</h1>
          <div className="text-xs" style={{ color: "var(--text2)" }}>
            Every bot, every run. A missing report is a finding, not silence.
          </div>
        </div>
        {f && (
          <div className="flex items-center gap-2 text-sm font-semibold"
            style={{ color: dead.length ? "var(--red)" : "var(--green)" }}>
            {dead.length ? <Skull size={16} /> : <CheckCircle2 size={16} />}
            {f.alive}/{f.total} reported · {dead.length ? `${dead.join(", ")} dead` : "all alive"}
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        <Card title="Spend this month" icon={IndianRupee}>
          {s ? (
            <>
              <div className="text-2xl font-bold">₹{Number(s.month_to_date_inr).toLocaleString("en-IN")}
                <span className="text-sm font-normal" style={{ color: "var(--text2)" }}> of {s.cap_inr ? `₹${Number(s.cap_inr).toLocaleString("en-IN")}` : "no cap set"}</span>
              </div>
              <div className="h-2 rounded mt-2" style={{ background: "var(--border)" }}>
                <div className="h-2 rounded" style={{ width: `${Math.min(100, s.pct_of_cap || 0)}%`,
                  background: s.mode === "paused" ? "var(--red)" : s.mode === "economy" ? "var(--amber)" : "var(--green)" }} />
              </div>
              <div className="text-xs mt-1" style={{ color: "var(--text2)" }}>mode: {s.mode} · {s.calls} calls</div>
            </>
          ) : "…"}
        </Card>
        <Card title="Needs you" icon={ListChecks}>
          {jobs.data ? (jobs.data.jobs.length === 0 ? <div className="text-sm" style={{ color: "var(--text2)" }}>Nothing waiting on you.</div> :
            <ul className="space-y-1 text-sm">
              {jobs.data.jobs.slice(0, 6).map((j: any) => (
                <li key={j.id}><span className="font-mono" style={{ color: "var(--amber)" }}>#{j.id}</span> {j.title}
                  <span className="text-xs" style={{ color: "var(--text2)" }}> · {j.kind}{j.eta ? ` · ETA ${j.eta}` : ""}</span></li>
              ))}
            </ul>) : "…"}
        </Card>
        <Card title="Storage" icon={HardDrive}>
          {m ? (
            <div className="text-sm space-y-1">
              <div>Database: <b>{m.db_bytes ? (m.db_bytes / 1048576).toFixed(1) : "?"} MB</b></div>
              <div>Disk free: <b style={{ color: m.disk && m.disk.pct_free < 20 ? "var(--red)" : "inherit" }}>
                {m.disk ? `${m.disk.pct_free}% (${m.disk.free_mb.toLocaleString("en-IN")} MB)` : "?"}</b></div>
              <div>Archives: <b>{m.archives?.length ?? 0}</b> files · purge weekly, never the sheet or open items</div>
            </div>
          ) : "…"}
        </Card>
      </div>

      <Card title="Bots" icon={Bot}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs" style={{ color: "var(--text2)" }}>
                <th className="py-1 pr-3">Bot</th><th className="pr-3">Cadence</th><th className="pr-3">Model</th>
                <th className="pr-3">Last run</th><th className="pr-3">Status</th><th className="pr-3">Next due</th><th className="pr-3">₹ MTD</th>
              </tr>
            </thead>
            <tbody>
              {(f?.bots || []).map((b: any) => (
                <tr key={b.id} className="border-t" style={{ borderColor: "var(--border)", opacity: b.enabled ? 1 : 0.45 }}>
                  <td className="py-2 pr-3">
                    <div className="font-medium flex items-center gap-1">{b.missed && <Skull size={13} style={{ color: "var(--red)" }} />}{b.id}</div>
                    <div className="text-xs" style={{ color: "var(--text2)" }}>{b.name !== b.id ? b.name : b.runs_on}</div>
                  </td>
                  <td className="pr-3 text-xs">{b.cadence}</td>
                  <td className="pr-3 text-xs font-mono">{b.model}</td>
                  <td className="pr-3 text-xs"><Clock size={11} className="inline mr-1" />{ago(b.last_run)}</td>
                  <td className="pr-3">
                    <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                      style={{ color: STATUS_COLOR[b.last_status] || "var(--text2)", background: (STATUS_COLOR[b.last_status] || "#94a3b8") + "18" }}>
                      {b.enabled ? b.last_status : "off"}
                    </span>
                    {b.last_summary && <div className="text-xs mt-0.5 max-w-xs truncate" style={{ color: "var(--text2)" }} title={b.last_summary}>{b.last_summary}</div>}
                  </td>
                  <td className="pr-3 text-xs" style={{ color: b.missed ? "var(--red)" : "inherit" }}>{b.enabled ? until(b.next_due) : "—"}</td>
                  <td className="pr-3 text-xs">₹{Number(b.spend_inr_mtd || 0).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {f?.gaps?.length ? (
          <div className="mt-3 text-xs" style={{ color: "var(--text2)" }}>
            <b>Known gaps:</b> {f.gaps.map((g: string, i: number) => <div key={i}>• {g}</div>)}
          </div>
        ) : null}
      </Card>

      <Card title="Memory — what the agent remembers, and where" icon={Brain}>
        {m ? (
          <div className="grid md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs font-semibold mb-1" style={{ color: "var(--text2)" }}>WHERE</div>
              <ul className="space-y-1 text-xs">
                {Object.entries(m.where || {}).map(([k, v]) => <li key={k}><b>{k}</b>: {String(v)}</li>)}
              </ul>
              <div className="text-xs font-semibold mt-3 mb-1" style={{ color: "var(--text2)" }}>OBJECTIVES (mirror)</div>
              {m.agenda?.objectives?.length ? (
                <ul className="space-y-1 text-xs">{m.agenda.objectives.map((o: any, i: number) => <li key={i}>• {o.title || JSON.stringify(o)}</li>)}</ul>
              ) : <div className="text-xs" style={{ color: "var(--amber)" }}>No confirmed objectives yet — edit the Objectives sheet.</div>}
              <div className="text-xs mt-1" style={{ color: "var(--text2)" }}>source: {m.agenda?.source || "—"} · synced {m.agenda?.synced_at ? ago(m.agenda.synced_at) : "never"}</div>
            </div>
            <div>
              <div className="text-xs font-semibold mb-1" style={{ color: "var(--text2)" }}>ROWS</div>
              <ul className="text-xs space-y-0.5">
                {Object.entries(m.rows || {}).map(([k, v]) => <li key={k}><Database size={10} className="inline mr-1" />{k}: {v === null ? "—" : Number(v).toLocaleString("en-IN")}</li>)}
                <li><Database size={10} className="inline mr-1" />runs logged: {m.runs_logged}</li>
              </ul>
              <div className="text-xs font-semibold mt-3 mb-1" style={{ color: "var(--text2)" }}>CHATS REMEMBERED</div>
              {m.chats?.length ? <ul className="text-xs">{m.chats.map((c: any) => <li key={c.chat_id}>{c.chat_id}: {c.turns} turns · last {ago(c.last)}</li>)}</ul>
                : <div className="text-xs" style={{ color: "var(--text2)" }}>none yet</div>}
              <div className="text-xs font-semibold mt-3 mb-1" style={{ color: "var(--text2)" }}>BOT MEMORY</div>
              {m.bot_memory?.length ? (
                <ul className="text-xs space-y-0.5">{m.bot_memory.map((b: any, i: number) => (
                  <li key={i}><b>{b.bot}</b> · {b.key}: {b.value} <span style={{ color: b.status === "proposed" ? "var(--amber)" : "var(--text2)" }}>[{b.status}]</span></li>
                ))}</ul>
              ) : <div className="text-xs" style={{ color: "var(--text2)" }}>empty — bots propose facts; you approve them by reply</div>}
            </div>
          </div>
        ) : "…"}
      </Card>
    </div>
  )
}
