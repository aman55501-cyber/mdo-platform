import { test, expect } from 'claude-code/testing'

import { dueDays, headline, parse } from './register'

const NOW = Date.UTC(2026, 9, 14, 6, 0) // 14 Oct 2026

test('parses open and done rows', () => {
  const t = parse('- [ ] P1 | Sell vehicles | Tushar | this week | note\n- [x] P9 | Done thing | Aman | - | ok')
  expect(t.length).toBe(2)
  expect(t[0].done).toBe(false)
  expect(t[1].done).toBe(true)
})

test('due dates', () => {
  expect(dueDays('22 Oct 2026', NOW)).toBe(8)
  expect(dueDays('after Dussehra', NOW)).toBeNull()
  expect(dueDays('31 Dec 2026', NOW)).toBe(78)
})

test('headline', () => {
  const t = parse('- [ ] P2 | Sprinkling | UNASSIGNED | - | x\n- [ ] P8 | Expo | Claude | 22 Oct 2026 | y\n- [x] P0 | Done | Aman | - | z')
  const h = headline(t, NOW)
  expect(h).toContain('OPEN 2')
  expect(h).toContain('DONE 1 (33%)')
  expect(h).toContain('next due P8 in 8d')
  expect(h).toContain('1 unassigned')
})
