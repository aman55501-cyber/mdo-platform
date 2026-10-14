import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Morning } from '../types'

const PANE = 'morning'
const view = atom({ plugin: 'mdo-morning', key: 'view' } as const, null as Morning | null)

type Check = { code: string; cadence: string; status: string; last_run?: string | null; last_result?: string; blocker?: string }

const H = 3600 * 1000
const LIMIT: Record<string, number> = { hourly: 2 * H, daily: 36 * H, weekly: 216 * H, monthly: 840 * H, quarterly: 2400 * H }

function age(c: Check, now: number): 'ok' | 'stale' | 'never' | 'blocked' | 'paused' {
  if (c.status === 'blocked') return 'blocked'
  if (c.status === 'paused') return 'paused'
  const limit = LIMIT[c.cadence]
  if (limit === undefined) return 'ok'
  if (!c.last_run) return 'never'
  const t = Date.parse(c.last_run.replace(' ', 'T') + 'Z')
  return Number.isNaN(t) || now - t > limit ? 'stale' : 'ok'
}

type Cfg = { base: string; headers: Record<string, string> }

async function getJson($: EngineInterface, cfg: Cfg, path: string): Promise<unknown> {
  const res = await $.http.fetch(`${cfg.base}${path}`, { headers: cfg.headers })
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return JSON.parse(res.text)
}

async function refresh($: EngineInterface, cfg: Cfg): Promise<void> {
  const now = await $.clock.now()
  const lines: string[] = []
  if (!cfg.base) {
    lines.push('Set baseUrl for mdo-morning in /config.')
  } else {
    try {
      const c = (await getJson($, cfg, '/api/checks')) as { checks: Check[] }
      const n = { ok: 0, stale: 0, never: 0, blocked: 0, paused: 0 }
      const bad: string[] = []
      for (const k of c.checks) {
        const v = age(k, now)
        n[v] += 1
        if (v === 'stale' || v === 'never') bad.push(`  ${v.toUpperCase()}  ${k.code} [${k.cadence}]`)
      }
      lines.push(`AUTOMATIONS  ${n.ok} ok · ${n.stale} stale · ${n.never} never ran · ${n.blocked} blocked`, ...bad, '')
    } catch (err) {
      lines.push(`AUTOMATIONS  UNREACHABLE: ${String(err)}`, '')
    }
    try {
      const b = (await getJson($, cfg, '/api/briefing/today/raw')) as {
        briefing: { content: string; generated_at?: string } | null
      }
      if (b.briefing) lines.push(`BRIEFING (${b.briefing.generated_at ?? 'today'})`, ...b.briefing.content.split('\n'))
      else lines.push('BRIEFING  none generated yet today')
    } catch (err) {
      lines.push(`BRIEFING  UNREACHABLE: ${String(err)}`)
    }
  }
  const hhmm = new Date(now + 5.5 * H).toISOString().slice(11, 16)
  await update($, view, () => ({ lines, at: `${hhmm} IST` }))
}

export const register: Register = (on, options) => {
  const cfg: Cfg = {
    base: String(options.baseUrl ?? '').replace(/\/+$/, ''),
    headers: options.token ? { 'x-mdo-key': String(options.token) } : {},
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'morning', description: 'Open the morning pane: briefing + automation heartbeat' })
    return next(e)
  })

  on('command.run', { command: 'morning' }, async $ => {
    await refresh($, cfg)
    await $.ui.open({ id: PANE, title: 'Morning' })
    return { text: 'Morning pane opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const room = Math.max(1, (e.viewport?.rows ?? 30) - 4)
    return (
      <Box flexDirection="column">
        <Box>
          <Text dimColor>{v ? `as of ${v.at}  ` : 'loading  '}</Text>
          <Button key="refresh" label="Refresh" onPress={() => refresh($, cfg)} />
        </Box>
        {(v?.lines ?? []).slice(0, room).map(l => (
          <Text>{l}</Text>
        ))}
      </Box>
    )
  })
}
