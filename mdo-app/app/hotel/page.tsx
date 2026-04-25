"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Hotel,
  UtensilsCrossed,
  ShoppingBag,
  ExternalLink,
  BedDouble,
  IndianRupee,
  TrendingUp,
  BarChart2,
  StickyNote,
  Save,
  RefreshCw,
  Wifi,
  AlertCircle,
  ChevronRight,
} from "lucide-react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts"

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8501"
const TOTAL_ROOMS = 30

// ── API helpers ───────────────────────────────────────────────────────────────

async function fetchHotelDaily(days = 7) {
  const r = await fetch(`${BASE}/api/hotel/daily?days=${days}`, { cache: "no-store" })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json() as Promise<{
    records: Array<{
      date: string
      occupied: number
      rate: number
      fnb_revenue: number
      occupancy_pct: number
    }>
  }>
}

async function postHotelDaily(payload: {
  date: string
  occupied: number
  rate: number
  fnb_revenue: number
}) {
  const r = await fetch(`${BASE}/api/hotel/daily`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}

async function postOpsTask(task: object) {
  const r = await fetch(`${BASE}/api/ops/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(task),
  })
  return r.json()
}

// ── helpers ───────────────────────────────────────────────────────────────────

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" })
}

function fmtINR(n: number) {
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`
  return `₹${n.toLocaleString("en-IN")}`
}

// ── Portal Card ───────────────────────────────────────────────────────────────

interface PortalCardProps {
  name: string
  description: string
  url: string
  Icon: React.ElementType
  iconColor: string
}

function PortalCard({ name, description, url, Icon, iconColor }: PortalCardProps) {
  return (
    <div
      className="rounded-xl border flex flex-col gap-3 p-5"
      style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "var(--bg3)" }}
        >
          <Icon size={20} style={{ color: iconColor }} />
        </div>
        <div>
          <div className="font-semibold text-sm">{name}</div>
          <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
            {description}
          </div>
        </div>
      </div>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-auto flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold border transition-colors"
        style={{ borderColor: "var(--border)", color: "var(--accent2)", background: "var(--bg3)" }}
      >
        Open Portal
        <ChevronRight size={12} />
      </a>
    </div>
  )
}

// ── Metric Stat ───────────────────────────────────────────────────────────────

function MetricStat({
  label,
  value,
  sub,
  color,
}: {
  label: string
  value: string
  sub?: string
  color?: string
}) {
  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: "var(--bg3)", borderColor: "var(--border)" }}
    >
      <div className="text-xs mb-1" style={{ color: "var(--text2)" }}>
        {label}
      </div>
      <div className="text-xl font-bold" style={{ color: color || "var(--text)" }}>
        {value}
      </div>
      {sub && (
        <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
          {sub}
        </div>
      )}
    </div>
  )
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs"
      style={{ background: "var(--bg2)", borderColor: "var(--border)", color: "var(--text)" }}
    >
      <div style={{ color: "var(--text2)" }}>{label}</div>
      <div className="font-semibold mt-0.5">
        {payload[0]?.value?.toFixed(0)}% occupancy
      </div>
    </div>
  )
}

// ── OTA Status Card ───────────────────────────────────────────────────────────

function OTACard({ name, direct = false }: { name: string; direct?: boolean }) {
  return (
    <div
      className="rounded-xl border flex items-center justify-between px-4 py-3"
      style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
    >
      <div className="flex items-center gap-2.5">
        <div
          className="w-2 h-2 rounded-full"
          style={{ background: direct ? "var(--accent)" : "var(--green)" }}
        />
        <span className="text-sm font-medium">{name}</span>
      </div>
      <div className="flex items-center gap-1.5">
        {direct ? (
          <span className="text-xs px-2 py-0.5 rounded-full"
            style={{ background: "rgba(99,102,241,0.15)", color: "var(--accent2)" }}>
            Direct
          </span>
        ) : (
          <span className="flex items-center gap-1 text-xs" style={{ color: "var(--text2)" }}>
            <Wifi size={10} />
            Sync via Staah
          </span>
        )}
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function HotelANSPage() {
  const qc = useQueryClient()
  const today = todayISO()

  // form state
  const [form, setForm] = useState({
    occupied: "",
    rate: "",
    fnb_revenue: "",
  })
  const [note, setNote] = useState("")
  const [noteSaved, setNoteSaved] = useState(false)
  const [formSaved, setFormSaved] = useState(false)

  // fetch 7-day history
  const {
    data,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["hotel_daily"],
    queryFn: () => fetchHotelDaily(7),
    retry: 1,
  })

  const records = data?.records ?? []
  const todayRecord = records.find((r) => r.date === today)

  // derived metrics from today or form
  const occupiedNum = todayRecord?.occupied ?? (form.occupied ? Number(form.occupied) : null)
  const rateNum = todayRecord?.rate ?? (form.rate ? Number(form.rate) : null)
  const fnbNum = todayRecord?.fnb_revenue ?? (form.fnb_revenue ? Number(form.fnb_revenue) : null)
  const occupancyPct =
    occupiedNum != null ? ((occupiedNum / TOTAL_ROOMS) * 100).toFixed(1) : null
  const roomRevenue = occupiedNum != null && rateNum != null ? occupiedNum * rateNum : null
  const revPAR =
    roomRevenue != null ? (roomRevenue / TOTAL_ROOMS).toFixed(0) : null

  // chart data
  const chartData = records.map((r) => ({
    date: fmtDate(r.date),
    pct: r.occupancy_pct ?? (r.occupied / TOTAL_ROOMS) * 100,
  }))

  // mutations
  const mutSave = useMutation({
    mutationFn: postHotelDaily,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["hotel_daily"] })
      setFormSaved(true)
      setTimeout(() => setFormSaved(false), 2500)
    },
  })

  const mutNote = useMutation({
    mutationFn: postOpsTask,
    onSuccess: () => {
      setNote("")
      setNoteSaved(true)
      setTimeout(() => setNoteSaved(false), 2500)
    },
  })

  const handleSaveNumbers = useCallback(() => {
    if (!form.occupied || !form.rate) return
    mutSave.mutate({
      date: today,
      occupied: Number(form.occupied),
      rate: Number(form.rate),
      fnb_revenue: Number(form.fnb_revenue) || 0,
    })
  }, [form, today, mutSave])

  const handleSaveNote = useCallback(() => {
    if (!note.trim()) return
    mutNote.mutate({
      title: note.trim().slice(0, 80),
      description: note.trim(),
      category: "hotel",
      entity: "Hotel ANS",
      priority: "medium",
      assigned_to: "Aman",
    })
  }, [note, mutNote])

  const inputStyle = {
    background: "var(--bg3)",
    borderColor: "var(--border)",
    color: "var(--text)",
    border: "1px solid var(--border)",
  }

  return (
    <div className="space-y-6 max-w-5xl">

      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "var(--bg3)", border: "1px solid var(--border)" }}
          >
            <Hotel size={20} style={{ color: "var(--accent2)" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold leading-tight">Hotel ANS</h1>
            <div className="text-xs mt-0.5" style={{ color: "var(--text2)" }}>
              Raigarh, CG — Property Management
            </div>
          </div>
        </div>

        {/* Occupancy badge */}
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-xl border"
          style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
        >
          <BedDouble size={15} style={{ color: "var(--cyan)" }} />
          <div className="text-sm">
            {occupancyPct != null ? (
              <>
                <span className="font-bold" style={{ color: "var(--cyan)" }}>
                  {occupancyPct}%
                </span>
                <span style={{ color: "var(--text2)" }} className="ml-1.5 text-xs">
                  occupancy today
                </span>
              </>
            ) : (
              <span style={{ color: "var(--text2)" }} className="text-xs">
                Enter today's numbers below
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Quick Access Portals ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <ExternalLink size={14} style={{ color: "var(--accent2)" }} />
          <span className="font-semibold text-sm">Quick Access Portals</span>
        </div>
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}
        >
          <PortalCard
            name="Staah"
            description="Room inventory & OTA sync"
            url="https://www.staah.com/login"
            Icon={Hotel}
            iconColor="var(--accent2)"
          />
          <PortalCard
            name="Swiggy Partner"
            description="Food delivery orders"
            url="https://partner.swiggy.com"
            Icon={UtensilsCrossed}
            iconColor="var(--amber)"
          />
          <PortalCard
            name="Zomato Partner"
            description="Restaurant dashboard"
            url="https://www.zomato.com/partners"
            Icon={ShoppingBag}
            iconColor="var(--red)"
          />
        </div>
      </div>

      {/* ── Occupancy Tracker ── */}
      <div
        className="rounded-xl border"
        style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
      >
        <div
          className="px-5 py-3.5 border-b flex items-center gap-2"
          style={{ borderColor: "var(--border)" }}
        >
          <BarChart2 size={15} style={{ color: "var(--accent2)" }} />
          <span className="font-semibold text-sm">Occupancy Tracker</span>
          <span className="ml-auto text-xs" style={{ color: "var(--text2)" }}>
            {new Date().toLocaleDateString("en-IN", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </span>
        </div>

        <div className="p-5 space-y-5">
          {/* API offline notice */}
          {isError && (
            <div
              className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg border"
              style={{
                background: "rgba(245,158,11,0.08)",
                borderColor: "rgba(245,158,11,0.3)",
                color: "var(--amber)",
              }}
            >
              <AlertCircle size={13} />
              Backend not yet configured — data saved locally when API comes online
            </div>
          )}

          {/* Input row */}
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}
          >
            {/* Total rooms — read-only */}
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>
                Total Rooms
              </label>
              <div
                className="px-3 py-2 rounded-lg text-sm font-semibold border"
                style={{ ...inputStyle, color: "var(--text2)", opacity: 0.6 }}
              >
                30
              </div>
            </div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>
                Occupied
              </label>
              <input
                type="number"
                min={0}
                max={30}
                placeholder={todayRecord?.occupied?.toString() ?? "0"}
                value={form.occupied}
                onChange={(e) => setForm((f) => ({ ...f, occupied: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                style={inputStyle}
              />
            </div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>
                Rate / Room (₹)
              </label>
              <input
                type="number"
                min={0}
                placeholder={todayRecord?.rate?.toString() ?? "2500"}
                value={form.rate}
                onChange={(e) => setForm((f) => ({ ...f, rate: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                style={inputStyle}
              />
            </div>

            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--text2)" }}>
                F&B Revenue (₹)
              </label>
              <input
                type="number"
                min={0}
                placeholder={todayRecord?.fnb_revenue?.toString() ?? "0"}
                value={form.fnb_revenue}
                onChange={(e) => setForm((f) => ({ ...f, fnb_revenue: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                style={inputStyle}
              />
            </div>
          </div>

          {/* Save button */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveNumbers}
              disabled={!form.occupied || !form.rate || mutSave.isPending}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-opacity disabled:opacity-40"
              style={{ background: "var(--accent)", color: "#fff" }}
            >
              {mutSave.isPending ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <Save size={13} />
              )}
              Save Today's Numbers
            </button>
            {formSaved && (
              <span className="text-xs" style={{ color: "var(--green)" }}>
                Saved successfully
              </span>
            )}
            {mutSave.isError && (
              <span className="text-xs" style={{ color: "var(--red)" }}>
                Save failed — check API
              </span>
            )}
          </div>

          {/* Key metrics */}
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}
          >
            <MetricStat
              label="Occupancy %"
              value={occupancyPct != null ? `${occupancyPct}%` : "—"}
              sub={occupiedNum != null ? `${occupiedNum} / ${TOTAL_ROOMS} rooms` : undefined}
              color={
                occupancyPct != null
                  ? Number(occupancyPct) >= 70
                    ? "var(--green)"
                    : Number(occupancyPct) >= 40
                    ? "var(--amber)"
                    : "var(--red)"
                  : undefined
              }
            />
            <MetricStat
              label="Room Revenue Today"
              value={roomRevenue != null ? fmtINR(roomRevenue) : "—"}
              sub={rateNum != null ? `@ ₹${rateNum.toLocaleString("en-IN")}/room` : undefined}
              color="var(--cyan)"
            />
            <MetricStat
              label="F&B Revenue"
              value={fnbNum != null ? fmtINR(fnbNum) : "—"}
              color="var(--accent2)"
            />
            <MetricStat
              label="RevPAR"
              value={revPAR != null ? `₹${Number(revPAR).toLocaleString("en-IN")}` : "—"}
              sub="Room revenue / 30 rooms"
              color="var(--text)"
            />
          </div>

          {/* 7-day bar chart */}
          {chartData.length > 0 ? (
            <div>
              <div className="text-xs mb-2 font-medium" style={{ color: "var(--text2)" }}>
                Last {chartData.length} days — Occupancy %
              </div>
              <ResponsiveContainer width="100%" height={120}>
                <BarChart data={chartData} barCategoryGap="30%">
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: "var(--text2)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: "var(--text2)" }}
                    axisLine={false}
                    tickLine={false}
                    width={28}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="pct" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={
                          entry.pct >= 70
                            ? "var(--green)"
                            : entry.pct >= 40
                            ? "var(--amber)"
                            : "var(--accent)"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : isLoading ? (
            <div className="text-xs py-4 text-center" style={{ color: "var(--text2)" }}>
              Loading history…
            </div>
          ) : (
            <div
              className="text-xs py-6 text-center rounded-lg border"
              style={{ color: "var(--text2)", borderColor: "var(--border)", background: "var(--bg3)" }}
            >
              No history yet — start entering daily numbers above
            </div>
          )}
        </div>
      </div>

      {/* ── OTA Status ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <TrendingUp size={14} style={{ color: "var(--accent2)" }} />
          <span className="font-semibold text-sm">OTA & Distribution Channels</span>
        </div>
        <div
          className="grid gap-2"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
        >
          <OTACard name="Booking.com" />
          <OTACard name="MakeMyTrip" />
          <OTACard name="Goibibo" />
          <OTACard name="OYO" />
          <OTACard name="Direct Bookings" direct />
        </div>
        <div className="mt-2 text-xs" style={{ color: "var(--text2)" }}>
          OTA inventory synced via Staah channel manager — open Staah portal above to manage rates &amp; availability.
        </div>
      </div>

      {/* ── Recent Notes ── */}
      <div
        className="rounded-xl border"
        style={{ background: "var(--bg2)", borderColor: "var(--border)" }}
      >
        <div
          className="px-5 py-3.5 border-b flex items-center gap-2"
          style={{ borderColor: "var(--border)" }}
        >
          <StickyNote size={15} style={{ color: "var(--accent2)" }} />
          <span className="font-semibold text-sm">Ops Notes</span>
          <span className="ml-auto text-xs" style={{ color: "var(--text2)" }}>
            Saved as hotel tasks in Operations
          </span>
        </div>

        <div className="p-5 space-y-3">
          <textarea
            rows={3}
            placeholder="e.g. AC in room 12 broken, Swiggy order spike this weekend, Water supply issue floor 2…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full px-3 py-2.5 rounded-lg text-sm border outline-none resize-none"
            style={{ ...inputStyle, fontFamily: "inherit", lineHeight: 1.6 }}
          />
          <div className="flex items-center gap-3">
            <button
              onClick={handleSaveNote}
              disabled={!note.trim() || mutNote.isPending}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-opacity disabled:opacity-40"
              style={{ background: "var(--bg3)", color: "var(--text)", border: "1px solid var(--border)" }}
            >
              {mutNote.isPending ? (
                <RefreshCw size={13} className="animate-spin" />
              ) : (
                <Save size={13} />
              )}
              Save as Ops Task
            </button>
            {noteSaved && (
              <span className="text-xs" style={{ color: "var(--green)" }}>
                Task added to Operations
              </span>
            )}
            {mutNote.isError && (
              <span className="text-xs" style={{ color: "var(--red)" }}>
                Save failed
              </span>
            )}
          </div>
          <div className="text-xs" style={{ color: "var(--text2)" }}>
            Notes are saved to the Ops task board under the "hotel" category and can be managed in the Operations page.
          </div>
        </div>
      </div>

    </div>
  )
}
