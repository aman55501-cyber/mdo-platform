/**
 * MDO WhatsApp Bridge
 * Connects to WhatsApp Web via Baileys and forwards EVERY chat on the account —
 * groups and 1:1 DMs, incoming and Aman's own replies — to the MDO backend via
 * HTTP. The backend classifies business vs personal and decides what to store;
 * the bridge only drops status/broadcast/newsletter traffic and unresolved LIDs.
 *
 * Built to run 1–2 months unattended on the VPS:
 *   • every Baileys disconnect reason is classified (see classifyDisconnect);
 *     reconnects use exponential backoff with a cap, the auth folder is wiped
 *     ONLY on a real logout (401 / 411), and "QR needed" is surfaced on
 *     /api/whatsapp/status and logged once a minute, not once a second;
 *   • a watchdog pings WhatsApp when no event has been seen for 15 min and
 *     restarts the socket if the ping fails;
 *   • posts to the backend go through a bounded queue (5000 msgs / 64 MB) with
 *     retry + backoff for 5xx / connection errors (backend restarting during a
 *     deploy) and a throttled "dropped N" log line when it overflows;
 *   • group / contact caches are LRU-bounded so a 10k+ history burst cannot
 *     grow the heap forever;
 *   • unhandledRejection / uncaughtException are logged, not fatal (a storm of
 *     them exits so Docker restarts the container cleanly).
 *
 * v2.2: voice notes / audio messages (audioMessage, ptt) of the chats that are
 * forwarded as text are downloaded (downloadMediaMessage) and handed to the
 * backend as multipart POST /api/wa/media (same X-MDO-Key) for the voice bot,
 * which transcribes them on the VPS with faster-whisper. The text row for the
 * same message is still forwarded as "[voice note Ns]" so chat activity counts.
 * Audio is forwarded for LIVE messages only — a history backfill would try to
 * download thousands of expired clips. WA_AUDIO_FORWARD=0 switches it off.
 *
 * Exports its internals when required as a module (test/run.js); only starts
 * listening when run directly.
 */

"use strict"

const baileys = require("@whiskeysockets/baileys")
const makeWASocket = baileys.default || baileys.makeWASocket
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion,
        downloadMediaMessage } = baileys
const express = require("express")
const QRCode  = require("qrcode")
const pino    = require("pino")
const path    = require("path")
const fs      = require("fs")
const http    = require("http")

const IS_MAIN = require.main === module
const VERSION = (() => { try { return require("./package.json").version } catch (e) { return "unknown" } })()

const app  = express()
const PORT = process.env.PORT || 3001
const MDO_BACKEND = process.env.MDO_BACKEND_URL || "http://localhost:8501"
const AUTH_DIR = process.env.AUTH_DIR || "/data/wa_auth"

// Which bridge this is: "1" (ops phone) or "2" (second phone). Sent on every
// forwarded message so the backend can tell the two accounts apart.
const WA_ACCOUNT = String(process.env.WA_ACCOUNT || "1")

const envInt = (k, d) => { const v = parseInt(process.env[k] || "", 10); return Number.isFinite(v) && v > 0 ? v : d }

// Groups to monitor (normalized partial name match — see isWatchedName).
// Rake count + daily dispatch quantity arrive inside "Vedanta Daily Report";
// the old "VWLR Rake Status" group no longer exists.
const WATCHED_GROUPS = [
  "vedanta daily report",
  "vwlr rake placement",
  "vwlr to apl raigarh",
  "vwlr-rkm group",
  "vwlr shifting",
  // Hotel ANS — the night report carries occupancy + daily numbers; the
  // backend parses them into hotel_daily automatically.
  "night report",
]

// Normalize before matching: lowercase, collapse punctuation/whitespace runs
// to single spaces — so "VWLR - RKM GROUP" matches "vwlr-rkm group".
const normName = s => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
const WATCHED_NORM = WATCHED_GROUPS.map(normName)

// Watch mode: "all" (default) ingests EVERY group on the account — reports
// from all firms, no per-business whitelist. Set WA_WATCH_MODE=list to
// restrict to WATCHED_GROUPS above. DMs are never filtered by this.
const WATCH_MODE = (process.env.WA_WATCH_MODE || "all").toLowerCase()

function isWatchedName(name) {
  if (!name) return false
  if (WATCH_MODE === "all") return true
  const n = normName(name)
  return WATCHED_NORM.some(g => n.includes(g))
}

// The backend's own CoS replies start with this; never echo them back.
const COS_PREFIX = "CoS ·"

// Voice notes → POST /api/wa/media (multipart). Off with WA_AUDIO_FORWARD=0.
// Clips over WA_AUDIO_MAX_BYTES (16 MB) are not downloaded; the text row still
// says "[voice note Ns]" so the chat is not silent.
const AUDIO_FORWARD = (process.env.WA_AUDIO_FORWARD || "1") !== "0"
const AUDIO_MAX_BYTES = envInt("WA_AUDIO_MAX_BYTES", 16 * 1024 * 1024)
let audioForwarded = 0

// Message kinds that carry no content (reactions, edits/deletes/ephemeral
// settings). Forwarding them would show up as fake "[media]" replies and skew
// response-time metrics.
const NON_CONTENT_KEYS = new Set(["protocolMessage", "reactionMessage"])

const bareNumber = jid => String(jid || "").split(":")[0].split("@")[0]

// Chief of Staff: direct messages to/from Aman. COS_INBOUND=1 turns this on.
const COS_INBOUND = (process.env.COS_INBOUND || "0") === "1"
const COS_ALLOWED = (process.env.COS_ALLOWED_NUMBERS || "").split(",").map(s => s.replace(/[^0-9]/g, "")).filter(Boolean)

app.use(express.json({ limit: "1mb" }))

// ── Timers / logging (injectable so the test can run without waiting) ────────

const T = {
  setTimeout:   (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (t) => clearTimeout(t),
  now:          () => Date.now(),
}
const sleep = ms => new Promise(r => T.setTimeout(r, ms))
const nowIso = () => new Date(T.now()).toISOString()

function log(msg) { console.log(msg) }

// Log `msg` under `key` at most once per `everyMs` (default 60 s). Repeats in
// between are counted and reported with the next line.
const _logOnce = new Map()
function logOnce(key, msg, everyMs = 60000) {
  const now = T.now()
  const prev = _logOnce.get(key)
  if (prev && now - prev.at < everyMs) { prev.suppressed++; return false }
  const suffix = prev && prev.suppressed ? ` (+${prev.suppressed} similar in the last ${Math.round((now - prev.at) / 1000)}s)` : ""
  _logOnce.set(key, { at: now, suppressed: 0 })
  log(msg + suffix)
  return true
}

// ── Bounded caches ───────────────────────────────────────────────────────────
// History sync after pairing can deliver 10k+ messages and thousands of
// contacts; without a cap the two caches grow for as long as the process lives.

class LRU {
  constructor(max) { this.max = Math.max(1, max | 0); this.map = new Map() }
  get(k) {
    if (!this.map.has(k)) return undefined
    const v = this.map.get(k)
    this.map.delete(k); this.map.set(k, v)   // refresh recency
    return v
  }
  has(k) { return this.map.has(k) }
  set(k, v) {
    if (this.map.has(k)) this.map.delete(k)
    this.map.set(k, v)
    while (this.map.size > this.max) this.map.delete(this.map.keys().next().value)
    return this
  }
  clear() { this.map.clear() }
  get size() { return this.map.size }
}

// jid → { subject, participants: [jid, ...] }. Populated in bulk on connect;
// per-message lookups are only a fallback. Failures are NOT cached —
// WhatsApp rate-limits metadata calls during the post-pairing history flood,
// and a cached failure would silently blackhole that group forever.
const groupMetaCache = new LRU(envInt("WA_GROUP_CACHE_MAX", 2000))

// jid → display name, fed by contacts.upsert / contacts.update and by the
// pushName on incoming DMs. Used to name DM chats on Aman's own (fromMe)
// messages, where pushName is Aman himself, and to name group participants.
const contactNameCache = new LRU(envInt("WA_CONTACT_CACHE_MAX", 20000))

const MAX_PARTICIPANTS = 50
function rememberContact(c) {
  if (!c || !c.id) return
  const name = c.notify || c.name || c.verifiedName
  if (name) contactNameCache.set(c.id, String(name))
}
function rememberGroup(jid, meta) {
  if (!jid || !meta) return
  groupMetaCache.set(jid, {
    subject: meta.subject || "",
    participants: Array.isArray(meta.participants)
      ? meta.participants.slice(0, MAX_PARTICIPANTS).map(p => p && p.id).filter(Boolean)
      : [],
  })
}

// ── Connection state ─────────────────────────────────────────────────────────

const S = {
  startedAt: Date.now(),
  connection: "starting",   // starting | connecting | qr | open | close | reconnect-wait | relinking
  connected: false,
  paired: false,            // creds carry a linked device (creds.me) — false until the first QR scan
  qr: null,                 // latest QR as base64 PNG data URL
  qrPending: false,
  qrAnnounced: false,       // backend told once per (re)link that a QR is needed
  user: null,               // own bare number once connected
  lastEventAt: 0,
  lastConnectedAt: 0,
  lastDisconnect: null,     // { code, reason, message, at }
  reconnectAttempt: 0,
  reconnectTimer: null,
  nextReconnectAt: 0,
  stableTimer: null,
  badSessionStreak: 0,
  relinks: 0,
  starting: false,
  startFailures: 0,         // consecutive startWA() throws (auth state / socket creation)
  watchdogRestarts: 0,      // consecutive watchdog-forced restarts without reaching "open"
  gen: 0,                   // socket generation; events from an older socket are ignored
}
let sock = null

const RECONNECT_BASE_MS   = envInt("WA_RECONNECT_BASE_MS", 2000)
const RECONNECT_CAP_MS    = envInt("WA_RECONNECT_CAP_MS", 120000)
const STABLE_AFTER_MS     = envInt("WA_STABLE_AFTER_MS", 30000)
const WATCHDOG_IDLE_MS    = envInt("WA_WATCHDOG_IDLE_MS", 15 * 60 * 1000)
const WATCHDOG_TICK_MS    = envInt("WA_WATCHDOG_TICK_MS", 60 * 1000)
const PING_TIMEOUT_MS     = envInt("WA_PING_TIMEOUT_MS", 20000)
const SEND_TIMEOUT_MS     = envInt("WA_SEND_TIMEOUT_MS", 20000)
const WEDGE_START_FAILS   = envInt("WA_WEDGE_START_FAILURES", 5)
const WEDGE_WD_RESTARTS   = envInt("WA_WEDGE_WATCHDOG_RESTARTS", 3)

// Baileys' DisconnectReason, with the 6.7.x values as a fallback so the table
// below is complete even if a future release drops a name.
const DR = Object.assign({
  connectionClosed: 428, connectionLost: 408, connectionReplaced: 440, timedOut: 408,
  loggedOut: 401, badSession: 500, restartRequired: 515, multideviceMismatch: 411,
  forbidden: 403, unavailableService: 503,
}, DisconnectReason || {})

function touch() { S.lastEventAt = T.now() }

// Exponential backoff, capped. attempt 1 → base, 2 → 2×base, … ≤ cap.
function backoffMs(attempt, base = RECONNECT_BASE_MS, cap = RECONNECT_CAP_MS) {
  const n = Math.max(1, attempt | 0)
  return Math.min(cap, base * Math.pow(2, Math.min(n - 1, 30)))
}
const jitterMs = () => Math.floor(Math.random() * 1000)

// What to do for each disconnect status code.
//   relink    — the stored session is dead; wipe it and start fresh for a QR
//   reconnect — keep the session, reconnect after a delay
function classifyDisconnect(code) {
  switch (code) {
    case DR.loggedOut:           return { action: "relink",    reason: "loggedOut",           delayMs: 2000 }
    case DR.multideviceMismatch: return { action: "relink",    reason: "multideviceMismatch", delayMs: 2000 }
    case DR.restartRequired:     return { action: "reconnect", reason: "restartRequired",     delayMs: 500, immediate: true }
    case DR.connectionReplaced:  return { action: "reconnect", reason: "connectionReplaced",  minDelayMs: 30000 }
    case DR.forbidden:           return { action: "reconnect", reason: "forbidden",           minDelayMs: 10 * 60 * 1000 }
    case DR.badSession:          return { action: "reconnect", reason: "badSession",          relinkAfter: 3 }
    case DR.connectionClosed:    return { action: "reconnect", reason: "connectionClosed" }
    case DR.timedOut:            return { action: "reconnect", reason: "timedOut" }
    case DR.unavailableService:  return { action: "reconnect", reason: "unavailableService" }
    default:                     return { action: "reconnect", reason: code ? `code ${code}` : "unknown" }
  }
}

function clearTimer(name) {
  if (S[name]) { T.clearTimeout(S[name]); S[name] = null }
}

function scheduleReconnect(delayMs, why) {
  clearTimer("reconnectTimer")
  const delay = Math.max(0, delayMs | 0) + (delayMs > 0 ? jitterMs() : 0)
  S.connection = "reconnect-wait"
  S.nextReconnectAt = T.now() + delay
  log(`WhatsApp (account ${WA_ACCOUNT}): ${why} — reconnecting in ${Math.round(delay / 1000)}s (attempt ${S.reconnectAttempt})`)
  S.reconnectTimer = T.setTimeout(() => {
    S.reconnectTimer = null
    startWA().catch(e => log(`reconnect failed: ${e.message}`))
  }, delay)
  return delay
}

function safeEnd(s, why) {
  if (!s) return
  try { if (typeof s.end === "function") s.end(new Error(why)) } catch (e) { /* already closed */ }
  try { if (s.ev && typeof s.ev.removeAllListeners === "function") s.ev.removeAllListeners() } catch (e) { /* ignore */ }
}

function wipeAuth(dir) {
  try { fs.rmSync(dir, { recursive: true, force: true }); return true } catch (e) {
    log(`could not clear auth dir ${dir}: ${e.message}`)
    return false
  }
}

// Baileys closed the socket (or we did). Decide relink vs reconnect.
function onClose(lastDisconnect) {
  const err  = lastDisconnect && lastDisconnect.error
  const code = (err && err.output && err.output.statusCode) ?? (err && err.statusCode) ?? null
  const c = classifyDisconnect(code)
  S.connected = false
  S.qr = null
  S.qrPending = false
  S.connection = "close"
  S.lastDisconnect = { code, reason: c.reason, message: String((err && err.message) || "").slice(0, 200), at: nowIso() }
  clearTimer("stableTimer")

  if (c.reason === "badSession") S.badSessionStreak++; else S.badSessionStreak = 0

  let action = c.action
  if (c.relinkAfter && S.badSessionStreak >= c.relinkAfter) {
    log(`badSession ${S.badSessionStreak}× in a row — treating the stored session as dead`)
    action = "relink"
  }

  if (action === "relink") {
    // Device was unlinked from the phone (or the session is unrecoverable).
    // The stored session is dead — wipe it and restart so a FRESH QR is
    // generated for re-pairing. This is the ONLY path that touches AUTH_DIR.
    log(`WhatsApp logged out (${c.reason}) — clearing dead session, a fresh QR will follow`)
    wipeAuth(AUTH_DIR)
    S.paired = false
    S.qrAnnounced = false
    S.relinks++
    S.reconnectAttempt = 0
    S.badSessionStreak = 0
    S.connection = "relinking"
    postToMDO("/api/whatsapp/status", { connected: false, account: WA_ACCOUNT, qr_pending: true, message: "WhatsApp logged out — rescan QR" })
    return scheduleReconnect(c.delayMs || 2000, `relink after ${c.reason}`)
  }

  S.reconnectAttempt++
  let delay = c.immediate ? c.delayMs : backoffMs(S.reconnectAttempt)
  if (c.minDelayMs) delay = Math.max(delay, c.minDelayMs)
  if (c.reason === "connectionReplaced") {
    logOnce("replaced", "WhatsApp session was opened elsewhere (connectionReplaced) — is this account's bridge running twice?")
  }
  if (c.reason === "forbidden") {
    logOnce("forbidden", "WhatsApp refused the connection (403 forbidden — account blocked?). Retrying every 10 min.")
  }
  return scheduleReconnect(delay, `disconnected (${c.reason}${code ? ` ${code}` : ""})`)
}

// ── Start WhatsApp connection ─────────────────────────────────────────────────

async function startWA() {
  if (S.starting) return null
  S.starting = true
  clearTimer("reconnectTimer")
  const gen = ++S.gen
  const old = sock
  sock = null
  if (old) safeEnd(old, "superseded")

  let mySock
  try {
    if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true })

    // Multi-file auth state under AUTH_DIR (/data/wa_auth — the wa-auth docker
    // volume, so it survives image rebuilds). saveCreds is bound to
    // creds.update below; every key rotation lands on disk immediately.
    const { state: authState, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
    S.paired = !!(authState && authState.creds && authState.creds.me)

    let version
    try { ({ version } = await fetchLatestBaileysVersion()) } catch (e) {
      log(`fetchLatestBaileysVersion failed (${e.message}) — using the library default`)
    }

    S.connection = "connecting"
    mySock = makeWASocket({
      ...(version ? { version } : {}),
      auth: authState,
      // Ask the phone to push chat history after pairing — without this the
      // messaging-history.set event never fires and backfill is empty.
      syncFullHistory: true,
      // Do not announce the bridge as "online": a linked device that is online
      // stops the phone from showing WhatsApp notifications, and Aman is
      // reachable only by phone while the system runs unattended.
      markOnlineOnConnect: false,
      logger: pino({ level: "silent" }),
    })
    sock = mySock
    S.startFailures = 0
    mySock.ev.on("creds.update", saveCreds)
  } catch (e) {
    S.startFailures++
    S.starting = false
    log(`startWA failed (${S.startFailures}×): ${e.message}`)
    scheduleReconnect(backoffMs(S.startFailures), "start failed")
    return null
  }
  S.starting = false

  const live = () => gen === S.gen && sock === mySock

  // Every event batch from Baileys feeds the watchdog clock.
  if (typeof mySock.ev.process === "function") mySock.ev.process(() => { if (live()) touch() })
  else for (const ev of ["messages.upsert", "presence.update", "creds.update", "connection.update", "contacts.update", "chats.update"]) {
    mySock.ev.on(ev, () => { if (live()) touch() })
  }

  // QR code — show on MDO dashboard for scanning
  mySock.ev.on("connection.update", async (update) => {
    if (!live()) return
    try {
      const { connection, lastDisconnect, qr } = update

      if (qr) {
        S.qr = await QRCode.toDataURL(qr)
        S.qrPending = true
        S.connected = false
        S.connection = "qr"
        logOnce("qr", "QR needed — scan from the Ops Feed page (/api/whatsapp/qr)")
        if (!S.qrAnnounced) {
          S.qrAnnounced = true
          postToMDO("/api/whatsapp/status", { connected: false, account: WA_ACCOUNT, qr_pending: true, message: "WhatsApp bridge needs a QR scan" })
        }
      }

      if (connection === "connecting") S.connection = "connecting"

      if (connection === "open") {
        S.connected = true
        S.paired = true
        S.qr = null
        S.qrPending = false
        S.qrAnnounced = false
        S.connection = "open"
        S.lastConnectedAt = T.now()
        S.user = bareNumber(mySock.user && mySock.user.id) || null
        touch()
        // Backoff resets only once the connection has held for a while, so a
        // connect→drop→connect flap does not restart the ladder at 2 s.
        clearTimer("stableTimer")
        S.stableTimer = T.setTimeout(() => {
          S.stableTimer = null
          S.reconnectAttempt = 0
          S.badSessionStreak = 0
          S.watchdogRestarts = 0
        }, STABLE_AFTER_MS)
        log(`WhatsApp connected (account ${WA_ACCOUNT}, ${S.user || "?"})`)
        await primeGroups(mySock)
        postToMDO("/api/whatsapp/status", { connected: true, account: WA_ACCOUNT, message: "WhatsApp bridge connected" })
      }

      if (connection === "close") {
        if (!live()) return
        onClose(lastDisconnect)
      }
    } catch (e) {
      log(`connection.update handler error: ${e.message}`)
    }
  })

  // Contact names — arrive in bulk during history sync and trickle in live.
  mySock.ev.on("contacts.upsert", (contacts) => { for (const c of contacts || []) rememberContact(c) })
  mySock.ev.on("contacts.update", (contacts) => { for (const c of contacts || []) rememberContact(c) })

  // Live messages
  mySock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return
    for (const msg of messages || []) {
      try { await ingestMessage(mySock, msg) } catch (e) { log(`ingest error: ${e.message}`) }
    }
  })

  // History backfill — WhatsApp pushes recent chat history right after the QR
  // pairing. Ingest it so the Ops Feed is populated immediately, not empty.
  mySock.ev.on("messaging-history.set", async ({ messages, contacts, isLatest, progress }) => {
    try {
      for (const c of contacts || []) rememberContact(c)
      const recent = (messages || []).slice(-2000) // cap per chunk; chunks keep arriving
      log(`history sync: chunk of ${recent.length} messages (progress: ${progress ?? "?"}, latest: ${isLatest ?? "?"})`)
      const counts = { group: 0, dm: 0, cos: 0, skipped: 0 }
      for (const msg of recent) {
        try {
          const kind = await ingestMessage(mySock, msg, { skipFromMe: false, audio: false })
          if (kind) counts[kind] = (counts[kind] || 0) + 1
          else counts.skipped++
        } catch (e) {
          log(`history ingest error: ${e.message}`)
        }
      }
      await queueIdle()
      log(`history sync: forwarded ${counts.group + counts.dm} messages to backend (groups: ${counts.group}, dms: ${counts.dm}, cos: ${counts.cos}, skipped: ${counts.skipped}, dropped so far: ${Q.dropped})`)
    } catch (e) {
      log(`history handler error: ${e.message}`)
    }
  })

  return mySock
}

async function primeGroups(s) {
  try {
    const groups = await s.groupFetchAllParticipating()
    let watched = 0
    for (const [jid, meta] of Object.entries(groups || {})) {
      rememberGroup(jid, meta)
      if (isWatchedName(meta.subject)) {
        watched++
        if (WATCH_MODE !== "all") log(`watching: ${meta.subject}`)
      }
    }
    log(`group cache primed: ${Object.keys(groups || {}).length} groups, ${watched} watched (mode: ${WATCH_MODE})`)
    if (WATCH_MODE !== "all") {
      if (watched < WATCHED_GROUPS.length) {
        const missed = Object.values(groups || {})
          .map(m => m.subject || "")
          .filter(n => n && !isWatchedName(n) && /vwlr|vedanta|rake|rkm|shifting|hotel|night|report|dsr|front office|kitchen/i.test(n))
        if (missed.length) log(`unmatched candidates: ${missed.join(" | ")}`)
      }
      if (watched === 0) log("WARNING: no groups matched WATCHED_GROUPS — check the names above against the list in index.js")
    }
  } catch (e) {
    log(`group prefetch failed (falling back to per-message lookups): ${e.message}`)
  }
}

// ── Watchdog ─────────────────────────────────────────────────────────────────
// Baileys has its own keepalive, but a half-dead websocket can sit "open"
// forever. If nothing (message, presence, keepalive) arrived for
// WATCHDOG_IDLE_MS we ping WhatsApp ourselves; a failed ping restarts the
// socket. A quiet account at night therefore costs one ping per 15 min, not a
// reconnect.

function withTimeout(p, ms, label) {
  let t
  const timeout = new Promise((_, rej) => { t = setTimeout(() => rej(Object.assign(new Error(label || "timeout"), { timeout: true })), ms); if (t.unref) t.unref() })
  return Promise.race([p, timeout]).finally(() => clearTimeout(t))
}

async function pingSocket(s, timeoutMs = PING_TIMEOUT_MS) {
  if (!s || typeof s.query !== "function") return false
  try {
    await withTimeout(
      s.query({ tag: "iq", attrs: { to: "s.whatsapp.net", type: "get", xmlns: "w:p" }, content: [{ tag: "ping", attrs: {} }] }, timeoutMs),
      timeoutMs + 1000, "ping timeout")
    return true
  } catch (e) { return false }
}

async function watchdogTick(now = T.now()) {
  const idle = now - (S.lastEventAt || S.startedAt)
  if (S.connected) {
    if (idle < WATCHDOG_IDLE_MS) return "ok"
    if (await pingSocket(sock)) { touch(); return "pinged" }
    log(`watchdog: no event for ${Math.round(idle / 60000)} min and ping failed — restarting the socket`)
    S.watchdogRestarts++
    S.connected = false
    S.gen++                              // the old socket's close event is now stale
    safeEnd(sock, "watchdog")
    S.reconnectAttempt++
    scheduleReconnect(2000, "watchdog restart")
    return "restarted"
  }
  // Not connected: a reconnect is scheduled or in progress — nothing to do.
  if (S.reconnectTimer || S.starting) return "waiting"
  // Baileys refreshes the QR every ~20-60 s, so even an unpaired bridge emits
  // events. No event at all for 15 min means the socket is stuck connecting.
  if (idle < WATCHDOG_IDLE_MS) return "ok"
  log(`watchdog: not connected and no event for ${Math.round(idle / 60000)} min — restarting the socket`)
  S.watchdogRestarts++
  S.gen++
  safeEnd(sock, "watchdog")
  S.reconnectAttempt++
  scheduleReconnect(2000, "watchdog restart (stuck connecting)")
  return "restarted"
}

// The process is "wedged" only when restarting the socket in-process stopped
// helping: socket creation keeps throwing, or the watchdog has forced several
// restarts without ever reaching "open". Then the compose healthcheck fails
// and autoheal restarts the container. Being unpaired is NOT wedged.
function isWedged() {
  return S.startFailures >= WEDGE_START_FAILS || S.watchdogRestarts >= WEDGE_WD_RESTARTS
}

// ── Message ingestion (live + history backfill) ──────────────────────────────

async function resolveGroupName(s, jid) {
  const cached = groupMetaCache.get(jid)
  if (cached !== undefined) return cached.subject
  try {
    const meta = await s.groupMetadata(jid)
    rememberGroup(jid, meta)
    return (groupMetaCache.get(jid) || {}).subject || ""
  } catch (e) {
    logOnce(`groupMetadata:${jid}`, `groupMetadata failed for ${jid}: ${e.message} (will retry on next message)`)
    return null // deliberately not cached
  }
}

// Up to 50 participant names (cached contact name, else bare number) — only
// when the metadata cache actually has them; never a metadata call here.
function groupParticipants(jid) {
  const meta = groupMetaCache.get(jid)
  const ids = meta && meta.participants
  if (!ids || !ids.length) return null
  return ids.slice(0, MAX_PARTICIPANTS).map(id => contactNameCache.get(id) || bareNumber(id))
}

// "group" | "dm" | null. Drops status@broadcast, @broadcast, @newsletter and
// anything else we cannot route. A @lid chat is accepted only when Baileys
// hands us the resolved phone-number jid alongside it.
function classifyChat(key) {
  let jid = (key && key.remoteJid) || ""
  if (jid.endsWith("@lid")) {
    const alt = (key && (key.remoteJidAlt || key.senderPn)) || ""
    if (!alt.endsWith("@s.whatsapp.net")) return { kind: null, jid }
    jid = alt
  }
  if (jid.endsWith("@g.us")) return { kind: "group", jid }
  if (jid.endsWith("@s.whatsapp.net")) return { kind: "dm", jid }
  return { kind: null, jid } // status@broadcast, *@broadcast, *@newsletter, unknown
}

// ── Chief of Staff: direct messages to/from Aman ──────────────────────────
// Two shapes work:
//   • a dedicated CoS number running this bridge: Aman's DMs arrive !fromMe
//     from a number in COS_ALLOWED_NUMBERS;
//   • Aman's own number (this bridge = his phone): he types in the
//     "message yourself" chat, which arrives fromMe with remoteJid = own jid.
// The backend's replies start with "CoS ·" and are skipped here, so a
// self-chat never loops.
function ownNumber(s) { return bareNumber(s && s.user && s.user.id) }

async function routeDirectMessage(s, msg) {
  if (!COS_INBOUND || !msg || !msg.message) return false
  const jid = (msg.key && msg.key.remoteJid) || ""
  if (!jid.endsWith("@s.whatsapp.net")) return false
  const number = jid.split("@")[0]
  const fromMe = !!(msg.key && msg.key.fromMe)
  const selfChat = fromMe && number === ownNumber(s)
  if (!selfChat && (fromMe || (COS_ALLOWED.length && !COS_ALLOWED.includes(number)))) return false
  const text = msg.message.conversation || (msg.message.extendedTextMessage && msg.message.extendedTextMessage.text) || ""
  if (!text || text.startsWith(COS_PREFIX)) return false
  log(`[CoS inbound] ${number}: ${text.slice(0, 80)}`)
  // Through the retrying queue: Aman's instruction must survive a backend deploy.
  await queuePost("/api/cos/inbound", { from: number, text, channel: "baileys", message_id: (msg.key && msg.key.id) || "" })
  return true
}

// Returns the chat kind ("group" | "dm" | "cos") if the message was forwarded
// to the backend, else null. `skipFromMe` is kept for callers but defaults to
// false: Aman's own replies are needed for response-time metrics.
async function ingestMessage(s, msg, { skipFromMe = false, audio = true } = {}) {
  if (!msg || !msg.message) return null
  if (await routeDirectMessage(s, msg)) return "cos"
  const fromMe = !!(msg.key && msg.key.fromMe)
  if (skipFromMe && fromMe) return null

  const { kind, jid } = classifyChat(msg.key)
  if (!kind) return null

  // Unwrap ephemeral / view-once envelopes so the content checks below see
  // the real node; otherwise everything inside them reads as "[media]".
  const m = (msg.message.ephemeralMessage && msg.message.ephemeralMessage.message)
    || (msg.message.viewOnceMessage && msg.message.viewOnceMessage.message)
    || (msg.message.viewOnceMessageV2 && msg.message.viewOnceMessageV2.message)
    || msg.message
  const contentKeys = Object.keys(m).filter(k => k !== "messageContextInfo" && k !== "senderKeyDistributionMessage")
  if (!contentKeys.length || contentKeys.every(k => NON_CONTENT_KEYS.has(k))) return null

  const text = (
    m.conversation ||
    (m.extendedTextMessage && m.extendedTextMessage.text) ||
    (m.imageMessage && m.imageMessage.caption) ||
    (m.videoMessage && m.videoMessage.caption) ||
    (m.documentMessage && m.documentMessage.caption) ||
    (m.audioMessage && `[voice note ${Number(m.audioMessage.seconds) || 0}s]`) ||
    "[media]"
  )
  // Never echo the backend's own CoS replies back to it (they arrive fromMe
  // on a self-chat bridge, !fromMe when a dedicated CoS number sent them).
  if (String(text).startsWith(COS_PREFIX)) return null

  // ── Chat display name ──
  let chatName
  if (kind === "group") {
    chatName = await resolveGroupName(s, jid)
    if (!chatName) return null
    if (!isWatchedName(chatName)) return null
  } else {
    const number = bareNumber(jid)
    if (!fromMe && msg.pushName) contactNameCache.set(jid, msg.pushName)
    chatName = (!fromMe && msg.pushName) || contactNameCache.get(jid) || number
  }

  // ── Sender ──
  let sender
  if (fromMe) {
    sender = "me"
  } else if (kind === "group") {
    const pJid = msg.key.participantAlt || msg.key.participant || ""
    sender = msg.pushName || contactNameCache.get(pJid) || bareNumber(pJid) || "Unknown"
  } else {
    sender = msg.pushName || contactNameCache.get(jid) || bareNumber(jid)
  }

  // Images carry the numbers that matter here — weighbridge slips, dispatch
  // tallies, hotel sales registers. For GROUPS download and hand them to the
  // backend, which decides whether to run vision extraction. DMs: caption or
  // "[media]" only — no download.
  let image_b64 = null, image_mime = null
  if (kind === "group") {
    const imgNode = m.imageMessage
      || (String((m.documentMessage && m.documentMessage.mimetype) || "").startsWith("image/") ? m.documentMessage : null)
    if (imgNode && (Number(imgNode.fileLength) || 0) <= 8 * 1024 * 1024) {
      try {
        const buf = await downloadMediaMessage(msg, "buffer", {}, { logger: pino({ level: "silent" }) })
        if (buf && buf.length) {
          image_b64 = buf.toString("base64")
          image_mime = imgNode.mimetype || "image/jpeg"
        }
      } catch (e) {
        logOnce("imgdl", `image download failed: ${e.message}`)
      }
    }
  }

  // Voice notes / audio (groups AND DMs — the Mausaji chat is a DM; the backend's
  // personal-chat gate decides what is kept). Live messages only (see header).
  let audioClip = null
  const audioNode = m.audioMessage
  if (audioNode && audio && AUDIO_FORWARD) {
    const len = Number(audioNode.fileLength) || 0
    if (len > AUDIO_MAX_BYTES) {
      logOnce("audiobig", `voice note skipped: ${Math.round(len / 1048576)} MB over WA_AUDIO_MAX_BYTES`)
    } else {
      try {
        const buf = await downloadMediaMessage(msg, "buffer", {}, { logger: pino({ level: "silent" }) })
        if (buf && buf.length) {
          audioClip = {
            buf,
            mimetype: audioNode.mimetype || "audio/ogg; codecs=opus",
            seconds: Number(audioNode.seconds) || 0,
            ptt: !!audioNode.ptt,
          }
        }
      } catch (e) {
        logOnce("audiodl", `voice note download failed: ${e.message}`)
      }
    }
  }

  const tsNum = Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000)
  const timestamp = new Date(tsNum * 1000).toISOString()

  const tag = kind === "dm" ? `[dm:${chatName}]` : `[${chatName}]`
  log(`${tag} ${sender}: ${String(text).slice(0, 80)}`)

  const participants = kind === "group" ? groupParticipants(jid) : null

  await queuePost("/api/whatsapp/message", {
    account: WA_ACCOUNT,
    group: chatName,          // chat display name — for DMs too
    sender,
    text: String(text),
    timestamp,
    jid,
    chat_jid: jid,
    chat_kind: kind,
    from_me: fromMe ? 1 : 0,
    wa_msg_id: (msg.key && msg.key.id) || "",
    ...(participants ? { participants } : {}),
    ...(image_b64 ? { image_b64, image_mime } : {}),
  })
  forwardedTotal++
  if (forwardedTotal % 500 === 0) log(`forwarded ${forwardedTotal} messages so far (account ${WA_ACCOUNT})`)

  if (audioClip) {
    const msgId = (msg.key && msg.key.id) || ""
    const ext = /mpeg|mp3/i.test(audioClip.mimetype) ? "mp3" : (/mp4|m4a|aac/i.test(audioClip.mimetype) ? "m4a" : "ogg")
    await queuePost("/api/wa/media", multipartBody({
      account: WA_ACCOUNT,
      chat_jid: jid,
      chat_name: chatName,
      sender,
      message_id: msgId,
      mimetype: audioClip.mimetype,
      duration_seconds: String(audioClip.seconds),
      ptt: audioClip.ptt ? "1" : "0",
      timestamp,
      from_me: fromMe ? "1" : "0",
      chat_kind: kind,
    }, { name: "file", filename: `${msgId || "voice"}.${ext}`, mimetype: audioClip.mimetype, buffer: audioClip.buf }))
    audioForwarded++
    log(`${tag} ${sender}: voice note ${audioClip.seconds}s (${Math.round(audioClip.buf.length / 1024)} KB) → /api/wa/media`)
  }
  return kind
}

// multipart/form-data body for queuePost(): plain string fields + one file.
// Built up front so the retrying queue can resend the same bytes.
function multipartBody(fields, file) {
  const boundary = "----MDOBridge" + Date.now().toString(16) + Math.random().toString(16).slice(2)
  const parts = []
  for (const [k, v] of Object.entries(fields || {})) {
    if (v === undefined || v === null) continue
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${String(v)}\r\n`))
  }
  if (file && file.buffer) {
    const fname = String(file.filename || "file").replace(/["\r\n]/g, "_")
    parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${file.name || "file"}"; filename="${fname}"\r\nContent-Type: ${file.mimetype || "application/octet-stream"}\r\n\r\n`))
    parts.push(file.buffer)
    parts.push(Buffer.from("\r\n"))
  }
  parts.push(Buffer.from(`--${boundary}--\r\n`))
  return { __multipart: true, data: Buffer.concat(parts), contentType: `multipart/form-data; boundary=${boundary}` }
}

// ── Backpressure: bounded POST queue with retry ──────────────────────────────
// History sync arrives in bursts of thousands. queuePost() resolves when the
// job has been HANDED to the HTTP layer (a slot was free) or dropped, so a
// caller that awaits it is throttled to MAX_IN_FLIGHT concurrent requests
// without having to wait for each response. queueIdle() resolves once
// everything has drained.
//
// The buffer is bounded (WA_QUEUE_MAX messages / WA_QUEUE_MAX_BYTES); when it
// overflows the OLDEST job is dropped and counted. A job whose POST fails with
// a 5xx / 408 / 429 or a connection error (backend restarting during a deploy)
// is retried in its slot with exponential backoff up to WA_POST_MAX_ATTEMPTS,
// then dropped and counted. A 4xx is never retried (counted as rejected).

const Q = {
  pending: [], inFlight: 0, idleWaiters: [], bytes: 0,
  delivered: 0, dropped: 0, rejected: 0, retries: 0,
  lastDropLogAt: 0, droppedSinceLog: 0,
}
const QCFG = {
  maxInFlight: envInt("WA_QUEUE_IN_FLIGHT", 4),
  maxQueue:    envInt("WA_QUEUE_MAX", 5000),
  maxBytes:    envInt("WA_QUEUE_MAX_BYTES", 64 * 1024 * 1024),
  maxAttempts: envInt("WA_POST_MAX_ATTEMPTS", 10),
  retryBaseMs: envInt("WA_POST_RETRY_BASE_MS", 1000),
  retryCapMs:  envInt("WA_POST_RETRY_CAP_MS", 30000),
  postTimeoutMs: envInt("WA_POST_TIMEOUT_MS", 60000),
}
let forwardedTotal = 0

function noteDrop(why) {
  Q.droppedSinceLog++
  const now = T.now()
  if (now - Q.lastDropLogAt < 10000) return
  log(`dropped ${Q.droppedSinceLog} message(s) — ${why}; ${Q.dropped} dropped in total since start (account ${WA_ACCOUNT})`)
  Q.lastDropLogAt = now
  Q.droppedSinceLog = 0
}

function queuePost(path, body) {
  return new Promise((accepted) => {
    const multipart = !!(body && body.__multipart)
    const data = multipart ? body.data : (typeof body === "string" ? body : JSON.stringify(body))
    const contentType = multipart ? body.contentType : "application/json"
    const job = { path, data, contentType, bytes: Buffer.byteLength(data), accepted, attempts: 0 }
    Q.pending.push(job)
    Q.bytes += job.bytes
    while (Q.pending.length > QCFG.maxQueue || (Q.bytes > QCFG.maxBytes && Q.pending.length > 1)) {
      const old = Q.pending.shift()
      Q.bytes -= old.bytes
      Q.dropped++
      noteDrop(`queue full (${QCFG.maxQueue} msgs / ${Math.round(QCFG.maxBytes / 1048576)} MB)`)
      old.accepted()            // never leave a caller hanging on a dropped job
    }
    pumpQueue()
  })
}

function pumpQueue() {
  while (Q.inFlight < QCFG.maxInFlight && Q.pending.length) {
    const job = Q.pending.shift()
    Q.bytes -= job.bytes
    Q.inFlight++
    job.accepted()
    deliver(job).catch(e => log(`deliver error: ${e.message}`)).then(() => {
      Q.inFlight--
      pumpQueue()
      if (!Q.inFlight && !Q.pending.length) Q.idleWaiters.splice(0).forEach(r => r())
    })
  }
}

function queueIdle() {
  return new Promise((resolve) => {
    if (!Q.inFlight && !Q.pending.length) return resolve()
    Q.idleWaiters.push(resolve)
  })
}

const isRetriable = r => !r || r.status === 0 || r.status >= 500 || r.status === 408 || r.status === 429

async function deliver(job) {
  for (;;) {
    job.attempts++
    let r
    try { r = await transport(job.path, job.data, job.contentType) } catch (e) { r = { status: 0, error: e.message } }
    if (r && r.status >= 200 && r.status < 300) { Q.delivered++; return true }
    const what = r && r.status ? `HTTP ${r.status}` : `${(r && r.error) || "no response"}`
    if (!isRetriable(r)) {
      Q.rejected++
      const hint = r.status === 401
        ? " — MDO_AUTH_TOKEN missing/wrong in the whatsapp container (docker compose up -d after .env edits)"
        : ""
      logOnce(`post-rejected:${job.path}:${r.status}`, `POST ${job.path} -> ${what}${hint} (not retried)`)
      return false
    }
    if (job.attempts >= QCFG.maxAttempts) {
      Q.dropped++
      noteDrop(`backend unreachable after ${job.attempts} attempts (${what}) on ${job.path}`)
      return false
    }
    Q.retries++
    const delay = backoffMs(job.attempts, QCFG.retryBaseMs, QCFG.retryCapMs) + jitterMs()
    logOnce(`post-retry:${job.path}`, `POST ${job.path} -> ${what}; retrying (attempt ${job.attempts}/${QCFG.maxAttempts}, next in ${Math.round(delay / 1000)}s, queued ${Q.pending.length})`, 30000)
    await sleep(delay)
  }
}

// ── POST to MDO backend ───────────────────────────────────────────────────────
// transport(path, body, contentType) → { status, error? }. body is a JSON string
// (default content type application/json) or a multipart Buffer with its
// boundary content type. Never rejects. Replaced by the test harness.

function httpTransport(path, data, contentType) {
  return new Promise((resolve) => {
    let done = false
    const finish = (r) => { if (!done) { done = true; resolve(r) } }
    try {
      const url = new URL(MDO_BACKEND + path)
      const req = http.request({
        hostname: url.hostname,
        port: url.port || 80,
        path: url.pathname,
        method: "POST",
        timeout: QCFG.postTimeoutMs,
        headers: {
          "Content-Type": contentType || "application/json",
          "Content-Length": Buffer.byteLength(data),
          // backend access key (when MDO_AUTH_TOKEN protection is enabled)
          "X-MDO-Key": process.env.MDO_AUTH_TOKEN || "",
        },
      }, (res) => {
        res.resume()
        res.on("end", () => finish({ status: res.statusCode }))
        res.on("error", (e) => finish({ status: 0, error: e.message }))
      })
      req.on("timeout", () => req.destroy(new Error(`timeout after ${QCFG.postTimeoutMs}ms`)))
      req.on("error", (e) => finish({ status: 0, error: e.message }))
      req.write(data)
      req.end()
    } catch (e) {
      finish({ status: 0, error: e.message })
    }
  })
}
let transport = httpTransport
function setTransport(fn) { transport = fn || httpTransport }

// One attempt, no retry — for status pings. Never rejects.
async function postToMDO(path, body) {
  try {
    const r = await transport(path, JSON.stringify(body))
    if (!r || !(r.status >= 200 && r.status < 300)) {
      logOnce(`post:${path}`, `POST ${path} -> ${r && r.status ? r.status : (r && r.error) || "no response"}`)
    }
    return r
  } catch (e) {
    log(`POST ${path} error: ${e.message}`)
    return { status: 0, error: e.message }
  }
}

// ── Status ───────────────────────────────────────────────────────────────────

function humanMessage() {
  if (S.connected) return "connected"
  if (S.qrPending) return "QR needed — scan from the Ops Feed page"
  if (!S.paired) return "not paired — waiting for a QR"
  if (S.reconnectTimer) return `reconnecting in ${Math.max(0, Math.round((S.nextReconnectAt - T.now()) / 1000))}s`
  return S.connection
}

function buildStatus() {
  const now = T.now()
  return {
    // existing fields — the backend / dashboard already know these
    connected: S.connected,
    account: WA_ACCOUNT,
    watch_mode: WATCH_MODE,
    watched_groups: WATCHED_GROUPS,
    // new fields
    state: S.connection,
    paired: S.paired,
    qr_pending: !!S.qrPending,
    user: S.user,
    message: humanMessage(),
    last_event_at: S.lastEventAt ? new Date(S.lastEventAt).toISOString() : null,
    last_connected_at: S.lastConnectedAt ? new Date(S.lastConnectedAt).toISOString() : null,
    last_disconnect: S.lastDisconnect,
    reconnect_attempts: S.reconnectAttempt,
    next_reconnect_in_s: S.reconnectTimer ? Math.max(0, Math.round((S.nextReconnectAt - now) / 1000)) : null,
    relinks: S.relinks,
    watchdog_restarts: S.watchdogRestarts,
    wedged: isWedged(),
    queued: Q.pending.length,
    in_flight: Q.inFlight,
    queued_bytes: Q.bytes,
    delivered: Q.delivered,
    dropped: Q.dropped,
    rejected: Q.rejected,
    retries: Q.retries,
    forwarded: forwardedTotal,
    audio_forwarded: audioForwarded,
    audio_forward: AUDIO_FORWARD,
    caches: { groups: groupMetaCache.size, contacts: contactNameCache.size },
    uptime_s: Math.floor((now - S.startedAt) / 1000),
    version: VERSION,
    pid: process.pid,
  }
}

// HTTP reason phrases must be ASCII; urllib on the backend shows this string
// as "HTTP Error 503: <phrase>", which is all it reads from an error response.
const asciiReason = s => String(s).replace(/[^\x20-\x7e]+/g, "-").replace(/\s+/g, " ").trim().slice(0, 80)

// ── Express API ───────────────────────────────────────────────────────────────

// QR code for scanning
app.get("/api/whatsapp/qr", (req, res) => {
  if (S.connected) return res.json({ connected: true, qr: null, qr_pending: false })
  if (!S.qr) return res.json({ connected: false, qr: null, qr_pending: false, message: `${humanMessage()} — check back in 10 seconds` })
  res.json({ connected: false, qr: S.qr, qr_pending: true })
})

// Connection status. 200 whenever the process is alive — an unpaired bridge
// waiting for a QR is healthy. 503 only when wedged (see isWedged), which is
// the compose healthcheck's cue to let autoheal restart the container.
app.get("/api/whatsapp/status", (req, res) => {
  const st = buildStatus()
  if (st.wedged) res.statusMessage = "bridge wedged"
  res.status(st.wedged ? 503 : 200).json(st)
})

// Send a message (used by the backend to push 🔴 alerts to Aman's phone).
// `to` may be a bare number (917000512030), a full jid, or a group jid.
app.post("/api/whatsapp/send", async (req, res) => {
  const { to, text } = req.body || {}
  if (!to || !text) return res.status(400).json({ ok: false, sent: false, error: "to and text required", reason: "to and text required" })
  if (!S.connected || !sock) {
    const reason = !S.paired || S.qrPending ? "not paired — scan QR" : "bridge reconnecting — retry shortly"
    res.statusMessage = asciiReason(reason)
    return res.status(503).json({ ok: false, sent: false, error: reason, reason, qr_pending: !!S.qrPending, state: S.connection })
  }
  const jid = String(to).includes("@")
    ? String(to)
    : String(to).replace(/[^0-9]/g, "") + "@s.whatsapp.net"
  try {
    await withTimeout(sock.sendMessage(jid, { text: String(text).slice(0, 4000) }), SEND_TIMEOUT_MS, "send timed out")
    log(`sent alert -> ${jid} (${String(text).length} chars)`)
    res.json({ ok: true, sent: true, jid })
  } catch (e) {
    log(`send failed: ${e.message}`)
    res.statusMessage = asciiReason(e.message)
    res.status(e.timeout ? 504 : 500).json({ ok: false, sent: false, error: e.message, reason: e.message })
  }
})

// Health check (liveness; same wedged rule as /api/whatsapp/status)
const health = (req, res) => {
  const wedged = isWedged()
  res.status(wedged ? 503 : 200).json({ ok: !wedged, connected: S.connected, qr_pending: !!S.qrPending, uptime_s: Math.floor((T.now() - S.startedAt) / 1000) })
}
app.get("/health", health)
app.get("/healthz", health)

// ── Process-level safety ─────────────────────────────────────────────────────

function installProcessGuards() {
  const storm = []
  process.on("unhandledRejection", (r) => {
    log(`unhandledRejection (kept alive): ${(r && r.stack) || r}`)
  })
  process.on("uncaughtException", (e) => {
    log(`uncaughtException (kept alive): ${(e && e.stack) || e}`)
    const now = Date.now()
    while (storm.length && now - storm[0] > 60000) storm.shift()
    storm.push(now)
    if (storm.length >= 20) {
      log("20 uncaught exceptions within 60s — exiting so Docker restarts the bridge cleanly")
      process.exit(1)
    }
  })
  const shutdown = (sig) => {
    log(`${sig} — shutting down (queued ${Q.pending.length}, in flight ${Q.inFlight})`)
    try { safeEnd(sock, sig) } catch (e) { /* ignore */ }
    setTimeout(() => process.exit(0), 500).unref()
  }
  process.on("SIGTERM", () => shutdown("SIGTERM"))
  process.on("SIGINT", () => shutdown("SIGINT"))
}

if (IS_MAIN) {
  installProcessGuards()
  const server = app.listen(PORT, () => {
    log(`WhatsApp bridge v${VERSION} running on port ${PORT} (account ${WA_ACCOUNT}, auth ${AUTH_DIR})`)
    startWA().catch(e => log(`startWA error: ${e.message}`))
    const wd = setInterval(() => { watchdogTick().catch(e => log(`watchdog error: ${e.message}`)) }, WATCHDOG_TICK_MS)
    if (wd.unref) wd.unref()
  })
  server.on("error", (e) => {
    log(`HTTP server error: ${e.message} — exiting so Docker restarts the bridge`)
    process.exit(1)
  })
}

module.exports = {
  app, startWA, watchdogTick, buildStatus, isWedged,
  classifyDisconnect, backoffMs, onClose, scheduleReconnect,
  queuePost, queueIdle, postToMDO, setTransport, multipartBody, ingestMessage,
  LRU, logOnce, asciiReason,
  S, Q, QCFG, T, DR, WA_ACCOUNT, AUTH_DIR,
  groupMetaCache, contactNameCache,
  getSock: () => sock,
}
