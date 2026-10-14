import type { EngineInterface, Register } from 'claude-code'

type Check = {
  code: string
  title: string
  cadence: string
  domain?: string
  status: string
  blocker?: string
  last_run?: string | null
  last_result?: string
}

const H = 3600 * 1000
const D = 24 * H
// How long a check may go without reporting before it counts as dead.
const LIMIT: Record<string, number> = {
  hourly: 2 * H,
  daily: 36 * H,
  weekly: 9 * D,
  monthly: 35 * D,
  quarterly: 100 * D,
}

const IST_MS = 5.5 * H

function ist(ms: number): string {
  const d = new Date(ms + IST_MS).toISOString()
  return `${d.slice(8, 10)} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][Number(d.slice(5, 7)) - 1]} ${d.slice(11, 16)} IST`
}

// SQLite datetime('now') is UTC "YYYY-MM-DD HH:MM:SS".
function parseUtc(s: string | null | undefined): number | null {
  if (!s) return null
  const t = Date.parse(s.replace(' ', 'T') + 'Z')
  return Number.isNaN(t) ? null : t
}

export type Verdict = 'ok' | 'stale' | 'never' | 'blocked' | 'paused'

export function judge(c: Check, now: number): Verdict {
  if (c.status === 'blocked') return 'blocked'
  if (c.status === 'paused') return 'paused'
  const limit = LIMIT[c.cadence]
  if (limit === undefined) return 'ok' // annual etc.: not judged by age
  const t = parseUtc(c.last_run)
  if (t === null) return 'never'
  return now - t > limit ? 'stale' : 'ok'
}

export function summarise(checks: readonly Check[], now: number) {
  const by: Record<Verdict, Check[]> = { ok: [], stale: [], never: [], blocked: [], paused: [] }
  for (const c of checks) by[judge(c, now)].push(c)
  return by
}

export function line(checks: readonly Check[], now: number): string {
  const by = summarise(checks, now)
  const bad = by.stale.length + by.never.length
  const parts = [`${by.ok.length} ok`]
  if (by.stale.length) parts.push(`${by.stale.length} STALE`)
  if (by.never.length) parts.push(`${by.never.length} never ran`)
  if (by.blocked.length) parts.push(`${by.blocked.length} blocked`)
  return `${bad ? '!! ' : ''}MDO ${parts.join(' · ')} · checked ${ist(now).slice(3)}`
}

export function report(checks: readonly Check[], now: number): string {
  const by = summarise(checks, now)
  const row = (c: Check) => {
    const t = parseUtc(c.last_run)
    const when = t === null ? 'never' : ist(t)
    const res = (c.last_result ?? '').trim() || '(no result text)'
    return `  ${c.code} [${c.cadence}] last ${when}: ${res}`
  }
  const out = [line(checks, now), '']
  if (by.stale.length) out.push('STALE (silent too long):', ...by.stale.map(row), '')
  if (by.never.length) out.push('NEVER RAN:', ...by.never.map(row), '')
  if (by.blocked.length)
    out.push('BLOCKED:', ...by.blocked.map(c => `  ${c.code} [${c.cadence}] ${c.blocker ?? 'no reason recorded'}`), '')
  out.push(`ALIVE (${by.ok.length}):`, ...by.ok.map(row))
  return out.join('\n')
}

type Cfg = { base: string; token: string }

// Polls the registry, pins the status line, and returns the full report text.
async function poll($: EngineInterface, opt: Cfg): Promise<string> {
  // Settings win; otherwise the cloud environment's MDO_BASE_URL / MDO_AUTH_TOKEN.
  const cfg: Cfg = {
    base: opt.base || ((await $.env.get('MDO_BASE_URL')) ?? '').replace(/\/+$/, ''),
    token: opt.token || ((await $.env.get('MDO_AUTH_TOKEN')) ?? ''),
  }
  if (!cfg.base) {
    $.ui.status('MDO heartbeat: set baseUrl in /config')
    return 'mdo-heartbeat: set baseUrl (and token) in /config.'
  }
  const now = await $.clock.now()
  try {
    const res = await $.http.fetch(`${cfg.base}/api/checks`, cfg.token ? { headers: { 'x-mdo-key': cfg.token } } : {})
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const checks = (JSON.parse(res.text) as { checks: Check[] }).checks
    $.ui.status(line(checks, now))
    const by = summarise(checks, now)
    if (by.stale.length + by.never.length > 0) {
      $.ui.toast(`MDO: ${by.stale.length} stale, ${by.never.length} never ran. /runs`)
    }
    return report(checks, now)
  } catch (err) {
    // Unreachable is itself a finding: say so, never go quiet.
    $.ui.status(`!! MDO unreachable · ${ist(now).slice(3)}`)
    $.ui.toast('MDO backend unreachable. /runs')
    return `MDO UNREACHABLE at ${ist(now)}: ${String(err)}`
  }
}

export const register: Register = (on, options) => {
  const cfg: Cfg = {
    base: String(options.baseUrl ?? '').replace(/\/+$/, ''),
    token: String(options.token ?? ''),
  }
  const everyMs = Math.max(1, Number(options.pollMinutes ?? 10)) * 60 * 1000

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'runs', description: 'Every automation: last run, stale, never ran, blocked' })
    void poll($, cfg)
    $.clock.every(everyMs, () => void poll($, cfg))
    return next(e)
  })

  on('command.run', { command: 'runs' }, async $ => ({ text: await poll($, cfg) }))
}
