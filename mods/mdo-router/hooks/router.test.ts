import { test, expect } from 'claude-code/testing'

import { forced, pick } from './register'

const models = { base: 'sonnet', heavy: 'opus' }

test('routes by label', () => {
  expect(pick('quick', models).model).toBe('sonnet')
  expect(pick('quick', models).effort).toBe('low')
  expect(pick('build', models).effort).toBe('high')
  expect(pick('judgement', models).model).toBe('opus')
})

test('force prefix', () => {
  expect(forced('!opus review this contract')).toBe('opus')
  expect(forced('review this contract')).toBeNull()
})
