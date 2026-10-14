import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Armed } from '../types'

const armed = atom({ plugin: 'mdo-guard', key: 'armed' } as const, null as Armed)

const GO_WINDOW_MS = 5 * 60 * 1000

// Tool names (MCP) that talk to other people, move money, sign, or file.
const OUTBOUND_TOOL =
  /^mcp__.*__(send_message|send_email|send_.+|reply|forward|share_file|share_document.*|post_.+comment|add_issue_comment|create_event|update_event|respond_to_event)$/i
const MONEY_TOOL = /^mcp__.*(pay|payment|payout|transfer|neft|rtgs|upi|razorpay)/i
const SIGN_TOOL = /^mcp__.*(esign|docusign|signature_request|sign_document)/i
const FILING_TOOL = /^mcp__.*(gstn|incometax|itr_|mca_|tds_file|file_return)/i

const FILING_HOST = /(gst\.gov\.in|incometax(gov)?\.gov\.in|mca\.gov\.in|tdscpc\.gov\.in|traces|epfindia|esic\.gov)/i
const MONEY_WORDS = /(razorpay|payu|cashfree|netbanking|\bneft\b|\brtgs\b|\bimps\b|\/payout|\/transfer\b)/i
const MESSAGE_HOST =
  /(graph\.facebook\.com|api\.twilio\.com|hooks\.slack\.com|discord(app)?\.com\/api\/webhooks|wa\.me|sendgrid|mailgun|smtp)/i
const POSTISH = /(-X\s*(POST|PUT|PATCH|DELETE)|--request\s*(POST|PUT|PATCH|DELETE)|\s-d\s|--data|\s-F\s|--form|--json|\bhttpie?\s+(post|put))/i
const HTTP_TOOL = /\b(curl|wget|http|https|xh)\b/

// Secret shapes: never into a file.
const SECRET_SHAPES =
  /(sk-ant-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{30,}|\b\d{8,10}:[A-Za-z0-9_-]{35}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----)/
const ENV_FILE = /(^|\/)\.env(\.(?!example)[A-Za-z0-9_-]+)?$/

// Share lane belongs to Grok. vega/vedanta is the tender side, not shares.
const SHARE_LANE = /(^|\/)(vega\/(?!vedanta\/)|levels\.yaml$|scripts\/(backtest|test_hdfc_auth)\.py$)/

type Input = Record<string, unknown>

function hostOf(url: string): string {
  const m = url.match(/^https?:\/\/([^/:?#]+)/i)
  return m ? m[1].toLowerCase() : ''
}

function urlsIn(command: string): string[] {
  return command.match(/https?:\/\/[^\s'"\\)]+/gi) ?? []
}

export function classify(tool: string, input: Input, allowed: readonly string[]): string | null {
  if (OUTBOUND_TOOL.test(tool)) return `outbound message or share via ${tool}`
  if (MONEY_TOOL.test(tool)) return `money move via ${tool}`
  if (SIGN_TOOL.test(tool)) return `signature via ${tool}`
  if (FILING_TOOL.test(tool)) return `regulator filing via ${tool}`

  if (tool === 'Read' || tool === 'Edit' || tool === 'Write' || tool === 'NotebookEdit') {
    const path = String(input.file_path ?? input.notebook_path ?? '')
    if (tool === 'Read' && ENV_FILE.test(path)) return `reading ${path} (secrets live in .env, never in chat)`
    if (tool !== 'Read' && ENV_FILE.test(path)) return `writing ${path} (edit secrets by hand)`
    if (tool !== 'Read' && SHARE_LANE.test(path)) return `share lane: Grok (${path})`
    if (tool !== 'Read') {
      const body = String(input.content ?? input.new_string ?? input.new_source ?? '')
      if (SECRET_SHAPES.test(body)) return `a secret-shaped value in ${path || 'the file'}`
    }
  }

  if (tool === 'Bash') {
    const cmd = String(input.command ?? '')

    if (/(^|[\s;&|])(cat|less|more|head|tail|grep|sed|awk|cp|scp|rsync|base64|xxd)\s[^|;&]*\.env(\s|$|["'])/.test(cmd) &&
        !/\.env\.example/.test(cmd)) return 'reading .env (secrets never printed)'
    if (/\bgit\s+add\b[^;&|]*\.env(\s|$)/.test(cmd) && !/\.env\.example/.test(cmd)) return 'staging .env'
    if (/\b(printenv|env)\b\s*($|[|;&])/.test(cmd) || /echo\s+["']?\$\{?[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|OTP)/.test(cmd))
      return 'printing environment secrets'
    if (SECRET_SHAPES.test(cmd)) return 'a secret-shaped value on the command line'

    if (/(^|[\s;&|])(sendmail|mailx?|msmtp|mutt)\s/.test(cmd)) return 'sending email from the shell'

    const urls = urlsIn(cmd)
    const callsHttp = HTTP_TOOL.test(cmd) && urls.length > 0
    if (callsHttp) {
      const writes = POSTISH.test(cmd)
      for (const u of urls) {
        const host = hostOf(u)
        // Aman's own digest bot: the chat id must come from the configured variable.
        if (/api\.telegram\.org\/bot[^/]+\/send/i.test(u)) {
          if (!/\$\{?TELEGRAM_CHAT_ID\}?/.test(cmd)) return 'Telegram message to a chat other than your own TELEGRAM_CHAT_ID'
          continue
        }
        if (FILING_HOST.test(host) && writes) return `regulator filing to ${host}`
        if (MESSAGE_HOST.test(u)) return `outbound message via ${host}`
        if (writes && MONEY_WORDS.test(u + ' ' + cmd)) return `money move via ${host}`
        if (writes && host !== 'localhost' && host !== '127.0.0.1' && !allowed.some(a => host === a || host.endsWith('.' + a)))
          return `write to third-party host ${host}`
      }
    }
  }
  return null
}

export const register: Register = (on, options) => {
  const allowed = [
    ...String(options.allowHosts ?? '').split(','),
    hostOf(String(options.baseUrl ?? '')),
  ].map(s => s.trim().toLowerCase()).filter(Boolean)

  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'go', description: 'Approve the ONE blocked action for the next 5 minutes' })
    await $.command.register({ name: 'hold', description: 'Cancel any pending /go' })
    $.ui.status('guard on')
    return next(e)
  })

  on('command.run', { command: 'go' }, async $ => {
    const until = (await $.clock.now()) + GO_WINDOW_MS
    await update($, armed, () => ({ until }))
    return { text: 'GO armed for ONE action, 5 minutes. Ask me to retry the blocked action now.' }
  })

  on('command.run', { command: 'hold' }, async $ => {
    await update($, armed, () => null)
    return { text: 'Cleared. Nothing is approved.' }
  })

  on('tool.call', async ($, e, next) => {
    const input = e as unknown as Input
    const reason = classify(String(e.tool), input, allowed)
    if (reason === null) return next(e)

    const now = await $.clock.now()
    const a = await read($, armed)
    if (a !== null && a.until > now) {
      await update($, armed, () => null)
      $.ui.toast(`guard: released one action (${reason})`)
      return next(e)
    }

    $.ui.toast(`guard blocked: ${reason}`)
    return {
      deny:
        `mdo-guard blocked: ${reason}. Aman's rule: money, signatures, regulator filings and outbound messages need his explicit click. ` +
        `Show him the exact draft, amount or filing, then he types /go (valid 5 min, one action). Do not retry before that.`,
    }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: 'mdo-guard: its check failed, so the action is held. Ask Aman to type /go after reviewing it.' },
  )
}
