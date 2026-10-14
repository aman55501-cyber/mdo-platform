import { test, expect } from 'claude-code/testing'

import { classify } from './register'

const allowed = ['mdo.example.com']

test('blocks outbound mail, money, filings, secrets, share lane', () => {
  expect(classify('mcp__Gmail__send_message', {}, allowed)).not.toBeNull()
  expect(classify('Bash', { command: 'curl -X POST https://api.razorpay.com/v1/payouts -d x=1' }, allowed)).not.toBeNull()
  expect(classify('Bash', { command: 'curl -X POST https://services.gst.gov.in/file -d x' }, allowed)).not.toBeNull()
  expect(classify('Bash', { command: 'cat BUSINESSES/vedanta_automation/.env' }, allowed)).not.toBeNull()
  expect(classify('Edit', { file_path: 'vega/strategy/risk.py', new_string: 'x' }, allowed)).not.toBeNull()
  expect(classify('Write', { file_path: 'a.py', content: 'k = "sk-ant-abcdefghijklmnopqrstuvwxyz"' }, allowed)).not.toBeNull()
})

test('lets normal work through', () => {
  expect(classify('Bash', { command: 'git status' }, allowed)).toBeNull()
  expect(classify('Bash', { command: 'curl -s https://mdo.example.com/api/checks' }, allowed)).toBeNull()
  expect(classify('Bash', { command: 'curl -X POST https://mdo.example.com/api/ops/tasks -d x' }, allowed)).toBeNull()
  expect(classify('Bash', { command: 'claude plugin validate x | grep -E "env|Validation"' }, allowed)).toBeNull()
  expect(classify('Bash', { command: 'printenv' }, allowed)).not.toBeNull()
  expect(classify('Edit', { file_path: 'vega/vedanta/bridge.py', new_string: 'x' }, allowed)).toBeNull()
  expect(classify('Read', { file_path: '.env.example' }, allowed)).toBeNull()
  expect(classify('mcp__Gmail__create_draft', {}, allowed)).toBeNull()
  expect(classify('Bash', { command: 'curl -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" -d chat_id=$TELEGRAM_CHAT_ID' }, allowed)).toBeNull()
})
