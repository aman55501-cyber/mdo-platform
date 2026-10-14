import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Task, TaskView } from '../types'

const view = atom({ plugin: 'mdo-tasks', key: 'view' } as const, { tasks: [], error: '' } as TaskView)
const expanded = atom({ plugin: 'mdo-tasks', key: 'expanded' } as const, false)

const ROW = /^- \[ \] (P\d+) \|([^|]*)\|([^|]*)\|([^|]*)\|?(.*)$/

export function parse(text: string): Task[] {
  const out: Task[] = []
  text.split('\n').forEach((raw, line) => {
    const m = raw.match(ROW)
    if (m) out.push({ line, pri: m[1], title: m[2].trim(), owner: m[3].trim(), due: m[4].trim(), note: m[5].trim() })
  })
  return out
}

async function load($: EngineInterface, path: string): Promise<void> {
  try {
    const text = (await $.fs.read(path)) as string
    await update($, view, () => ({ tasks: parse(text), error: '' }))
  } catch (err) {
    await update($, view, () => ({ tasks: [], error: `cannot read ${path}: ${String(err)}` }))
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
    await load($, path)
    return next(e)
  })

  on('command.run', { command: 'tasks' }, async $ => {
    await load($, path)
    await update($, expanded, () => true)
    return { text: 'Open tasks refreshed.' }
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

    const p1 = v.tasks.filter(t => t.pri === 'P1').length
    const head = `OPEN ${v.tasks.length} incomplete${p1 ? ` · ${p1} at P1` : ''}`

    return (
      <Box flexDirection="column">
        <Box>
          <Text bold>{head} </Text>
          <Button key="toggle" label={open ? 'Collapse' : 'Expand'} onPress={() => update($, expanded, x => !x)} />
          <Button key="refresh" label="Refresh" onPress={() => load($, path)} />
        </Box>
        {open &&
          v.tasks.slice(0, 15).map(t => (
            <Box key={`t${t.line}`} flexDirection="column">
              <Box>
                <Text>
                  {t.pri} {t.title} · {t.owner}
                  {t.due && t.due !== '-' ? ` · due ${t.due}` : ''}{' '}
                </Text>
                <Button key={`done${t.line}`} label="Done" onPress={() => tick($, path, t.line)} />
              </Box>
              {t.note && <Text dimColor>   {t.note}</Text>}
            </Box>
          ))}
      </Box>
    )
  })
}
