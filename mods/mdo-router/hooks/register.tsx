import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Route } from '../types'

const route = atom({ plugin: 'mdo-router', key: 'route' } as const, null as Route | null)
const isOn = atom({ plugin: 'mdo-router', key: 'isOn' } as const, true)

export const LABELS = ['quick', 'routine', 'build', 'judgement'] as const
export type Label = (typeof LABELS)[number]

// Switching model re-bills the cached prefix, so heavy -> default waits for 2 calm turns.
export const CALM_TURNS = 2

export function pick(label: Label, models: { base: string; heavy: string }): Omit<Route, 'calm'> {
  switch (label) {
    case 'quick':
      return { model: models.base, effort: 'low', why: 'quick answer' }
    case 'routine':
      return { model: models.base, effort: 'medium', why: 'routine work' }
    case 'build':
      return { model: models.base, effort: 'high', why: 'multi-step build' }
    case 'judgement':
      return { model: models.heavy, effort: 'high', why: 'high-stakes judgement' }
  }
}

export function forced(text: string): string | null {
  const m = text.match(/^\s*!(opus|sonnet|haiku)\b/i)
  return m ? m[1].toLowerCase() : null
}

const GUIDE =
  'quick = a lookup, rewording, short factual answer. routine = normal analysis, drafting, summarising, small edits. ' +
  'build = multi-file code or long agentic work. judgement = contracts, legal, structural safety, capital allocation, ' +
  'tax or compliance exposure, anything above Rs 25 lakh, strategy with irreversible consequences.'

export const register: Register = (on, options) => {
  const models = { base: String(options.defaultModel ?? 'sonnet'), heavy: String(options.heavyModel ?? 'opus') }

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'route', description: 'on | off | status: automatic model and effort routing' })
    return next(e)
  })

  on('command.run', { command: 'route' }, async ($, e) => {
    const arg = String((e as unknown as { args?: string }).args ?? '').trim().toLowerCase()
    if (arg === 'on' || arg === 'off') await update($, isOn, () => arg === 'on')
    const r = await read($, route)
    const on_ = await read($, isOn)
    return { text: `Routing ${on_ ? 'ON' : 'OFF'}. Last: ${r ? `${r.model} / ${r.effort} (${r.why})` : 'none yet'}. Prefix a prompt with !opus, !sonnet or !haiku to force one turn.` }
  })

  on('turn.start', async ($, e, next) => {
    if (!(await read($, isOn))) return next(e)
    const text = e.text ?? ''
    const prev = await read($, route)
    const f = forced(text)
    let want: Omit<Route, 'calm'>
    if (f) {
      want = { model: f, effort: 'high', why: `forced !${f}` }
    } else {
      let label: Label = 'routine'
      try {
        const guess = await $.model.classify(`${GUIDE}\n\nTask: ${text.slice(0, 1500)}`, LABELS)
        if (guess) label = guess as Label
      } catch {
        label = 'routine' // classifier failed: stay on the default, never block the turn
      }
      want = pick(label, models)
    }
    // Hysteresis: stepping down from heavy needs CALM_TURNS calm turns in a row.
    let next_: Route = { ...want, calm: 0 }
    if (prev && prev.model === models.heavy && want.model !== models.heavy && !f) {
      next_ = prev.calm + 1 >= CALM_TURNS ? { ...want, calm: 0 } : { ...prev, calm: prev.calm + 1 }
    }
    await update($, route, () => next_)
    $.ui.status(`route: ${next_.model} / ${next_.effort} · ${next_.why}`)
    return next(e)
  })

  on('turn.step', async function* ($, e, next) {
    const r = await read($, route)
    if (e.agentId || !r || !(await read($, isOn))) return yield* next(e)
    return yield* next({ ...e, model: r.model, effort: r.effort })
  })
}
