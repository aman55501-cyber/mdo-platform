import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Task, TaskView } from '../types'

const view = atom({ plugin: 'mdo-tasks', key: 'view' } as const, { tasks: [], error: '', at: 0 } as TaskView)
const expanded = atom({ plugin: 'mdo-tasks', key: 'expanded' } as const, false)

const ROW = /^- \[( |x)\] (P\d+) \|([^|]*)\|([^|]*)\|([^|]*)\|?(.*)$/
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
const DAY = 86400000
const IST = 5.5 * 3600000

export function parse(text: string): Task[] {
  const out: Task[] = []
  text.split('\n').forEach((raw, line) => {
    const m = raw.match(ROW)
    if (m) out.push({ line, done: m[1] === 'x', pri: m[2], title: m[3].trim(), owner: m[4].trim(), due: m[5].trim(), note: m[6].trim() })
  })
  return out
}

// "22 Oct 2026", "31 Dec 2026", "21 Oct": days from now (IST dates). null when no date in the text.
export function dueDays(due: string, nowMs: number): number | null {
  const m = due.toLowerCase().match(/(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*(?:\s+(\d{4}))?/)
  if (!m) return null
  const today = new Date(nowMs + IST)
  const year = m[3] ? Number(m[3]) : today.getUTCFullYear()
  const target = Date.UTC(year, MONTHS.indexOf(m[2]), Number(m[1]))
  const base = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
  return Math.round((target - base) / DAY)
}

export function stats(tasks: readonly Task[], nowMs: number) {
  const open = tasks.filter(t => !t.done)
  const done = tasks.length - open.length
  const dated = open
    .map(t => ({ t, d: dueDays(t.due, nowMs) }))
    .filter((x): x is { t: Task; d: number } => x.d !== null)
    .sort((a, b) => a.d - b.d)
  const overdue = dated.filter(x => x.d < 0)
  const unassigned = open.filter(t => /unassigned/i.test(t.owner))
  const byOwner = new Map<string, number>()
  for (const t of open) byOwner.set(t.owner.split('(')[0].trim() || '?', (byOwner.get(t.owner.split('(')[0].trim() || '?') ?? 0) + 1)
  const pct = tasks.length ? Math.round((100 * done) / tasks.length) : 0
  return { open, done, pct, dated, overdue, unassigned, byOwner }
}

export function headline(tasks: readonly Task[], nowMs: number): string {
  const s = stats(tasks, nowMs)
  const parts = [`OPEN ${s.open.length}`, `DONE ${s.done} (${s.pct}%)`]
  const next = s.dated.find(x => x.d >= 0)
  if (next) parts.push(`next due ${next.t.pri} in ${next.d}d`)
  if (s.overdue.length) parts.push(`${s.overdue.length} OVERDUE`)
  if (s.unassigned.length) parts.push(`${s.unassigned.length} unassigned`)
  return parts.join(' · ')
}

export function progressText(tasks: readonly Task[], nowMs: number): string {
  const s = stats(tasks, nowMs)
  const out = [headline(tasks, nowMs), '']
  if (s.overdue.length) out.push('OVERDUE:', ...s.overdue.map(x => `  ${x.t.pri} ${x.t.title} (${-x.d}d late, ${x.t.owner})`), '')
  const soon = s.dated.filter(x => x.d >= 0 && x.d <= 30)
  if (soon.length) out.push('DUE IN 30 DAYS:', ...soon.map(x => `  ${x.t.pri} in ${x.d}d: ${x.t.title} (${x.t.owner})`), '')
  if (s.unassigned.length) out.push('NO OWNER:', ...s.unassigned.map(t => `  ${t.pri} ${t.title}`), '')
  out.push('OPEN BY OWNER:', ...[...s.byOwner.entries()].sort((a, b) => b[1] - a[1]).map(([o, n]) => `  ${o}: ${n}`))
  const doneList = tasks.filter(t => t.done)
  if (doneList.length) out.push('', 'DONE:', ...doneList.map(t => `  ${t.pri} ${t.title}`))
  return out.join('\n')
}

async function load($: EngineInterface, path: string): Promise<void> {
  const at = await $.clock.now()
  try {
    const text = (await $.fs.read(path)) as string
    await update($, view, () => ({ tasks: parse(text), error: '', at }))
  } catch (err) {
    await update($, view, () => ({ tasks: [], error: `cannot read ${path}: ${String(err)}`, at }))
  }
}

async function tick($: EngineInterface, path: string, line: number): Promise<void> {
  const text = (await $.fs.read(path)) as string
  const rows = text.split('\n')
  if (!rows[line] || !rows[line].startsWith('- [ ] ')) return
  rows[line] = rows[line].replace('- [ ] ', '- [x] ')
  await $.fs.write(path, rows.join('\n'))
  await load($, path)
}

export const register: Register = (on, options) => {
  const path = String(options.file ?? 'WORKLIST.md')

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'tasks', description: 'Refresh and expand the open-tasks band' })
    await $.command.register({ name: 'progress', description: 'Progress: done %, overdue, due soon, by owner' })
    await load($, path)
    return next(e)
  })

  on('command.run', { command: 'tasks' }, async $ => {
    await load($, path)
    await update($, expanded, () => true)
    return { text: 'Open tasks refreshed.' }
  })

  on('command.run', { command: 'progress' }, async $ => {
    await load($, path)
    const v = await read($, view)
    return { text: v.error || progressText(v.tasks, v.at) }
  })

  // After every reply: re-read the file so the band is current.
  on('turn.complete', async ($, e, next) => {
    await load($, path)
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const open = await read($, expanded)

    if (v.error) {
      return (
        <Box>
          <Text color="red">OPEN: {v.error} </Text>
          <Button key="retry" label="Retry" onPress={() => load($, path)} />
        </Box>
      )
    }

    const todo = v.tasks.filter(t => !t.done)

    return (
      <Box flexDirection="column">
        <Box>
          <Text bold>{headline(v.tasks, v.at)} </Text>
          <Button key="toggle" label={open ? 'Collapse' : 'Expand'} onPress={() => update($, expanded, x => !x)} />
          <Button key="refresh" label="Refresh" onPress={() => load($, path)} />
        </Box>
        {open &&
          todo.slice(0, 18).map(t => {
            const d = dueDays(t.due, v.at)
            const tag = d === null ? '' : d < 0 ? ` · ${-d}d LATE` : ` · ${d}d left`
            return (
              <Box key={`t${t.line}`} flexDirection="column">
                <Box>
                  <Text>
                    {t.pri} {t.title} · {t.owner}
                    {tag}{' '}
                  </Text>
                  <Button key={`done${t.line}`} label="Done" onPress={() => tick($, path, t.line)} />
                </Box>
                {t.note && <Text dimColor>   {t.note}</Text>}
              </Box>
            )
          })}
      </Box>
    )
  })
}
