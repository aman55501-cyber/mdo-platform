#!/usr/bin/env node
/**
 * WhatsApp bridge unit tests — no network, no node_modules.
 *
 * Baileys, express, qrcode and pino are stubbed through Module._load before
 * index.js is required, so this runs on a bare `node` (20+):
 *
 *     node whatsapp_bridge/test/run.js
 *
 * Covers: disconnect classification + reconnect backoff (incl. loggedOut auth
 * wipe and once-a-minute QR logging), queue retry / drop / overflow, the
 * watchdog, the status shape and the 503 "not paired" send response.
 */
"use strict"

const assert = require("assert")
const fs = require("fs")
const os = require("os")
const path = require("path")
const Module = require("module")

// ── Stubs ────────────────────────────────────────────────────────────────────

const DisconnectReason = {
  connectionClosed: 428, connectionLost: 408, connectionReplaced: 440, timedOut: 408,
  loggedOut: 401, badSession: 500, restartRequired: 515, multideviceMismatch: 411,
  forbidden: 403, unavailableService: 503,
}

const socks = []
function makeFakeSock() {
  const listeners = new Map()
  const processors = []
  const s = {
    user: { id: "917000000000:12@s.whatsapp.net" },
    ended: null,
    sent: [],
    queryImpl: () => Promise.resolve({ tag: "iq" }),
    ev: {
      on(ev, fn) { if (!listeners.has(ev)) listeners.set(ev, []); listeners.get(ev).push(fn) },
      process(fn) { processors.push(fn) },
      removeAllListeners() { listeners.clear(); processors.length = 0 },
      async emit(ev, data) {
        for (const p of processors) await p({ [ev]: data })
        for (const fn of listeners.get(ev) || []) await fn(data)
      },
    },
    end(err) { s.ended = (err && err.message) || "ended" },
    query(node) { return s.queryImpl(node) },
    sendMessage(jid, content) { s.sent.push({ jid, content }); return Promise.resolve({ key: { id: "X" } }) },
    groupFetchAllParticipating() { return Promise.resolve({}) },
    groupMetadata() { return Promise.reject(new Error("rate-overlimit")) },
  }
  socks.push(s)
  return s
}

let authCreds = { me: null }
const baileysStub = {
  default: (opts) => { baileysStub.lastOpts = opts; return makeFakeSock() },
  DisconnectReason,
  useMultiFileAuthState: async (dir) => ({ state: { creds: authCreds }, saveCreds() {} }),
  fetchLatestBaileysVersion: async () => ({ version: [2, 3000, 0], isLatest: true }),
  downloadMediaMessage: async () => Buffer.from("img"),
}

function makeExpressStub() {
  const routes = { GET: {}, POST: {} }
  const express = () => ({
    use() {},
    get(p, h) { routes.GET[p] = h },
    post(p, h) { routes.POST[p] = h },
    listen(port, cb) { cb && cb(); return { on() {} } },
  })
  express.json = () => (req, res, next) => next()
  express._routes = routes
  return express
}
const expressStub = makeExpressStub()

const STUBS = {
  "@whiskeysockets/baileys": baileysStub,
  "express": expressStub,
  "qrcode": { toDataURL: async (s) => "data:image/png;base64," + Buffer.from(s).toString("base64") },
  "pino": () => ({}),
}
const origLoad = Module._load
Module._load = function (request) {
  if (Object.prototype.hasOwnProperty.call(STUBS, request)) return STUBS[request]
  return origLoad.apply(this, arguments)
}

// ── Environment ──────────────────────────────────────────────────────────────

const AUTH_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "wa-bridge-test-"))
process.env.AUTH_DIR = AUTH_DIR
process.env.MDO_BACKEND_URL = "http://127.0.0.1:1"
process.env.WA_ACCOUNT = "9"
process.env.COS_INBOUND = "0"

// Capture logs
const logs = []
const realLog = console.log
console.log = (...a) => { logs.push(a.join(" ")) }
const logsMatching = re => logs.filter(l => re.test(l))

const B = require("../index.js")

// Fake timers: every T.setTimeout is recorded; `fire()` runs them.
const timers = []
let fakeNow = Date.now()
B.T.now = () => fakeNow
B.T.setTimeout = (fn, ms) => { const t = { fn, ms, id: timers.length + 1 }; timers.push(t); return t }
B.T.clearTimeout = (t) => { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1) }
function fire(pred = () => true) {
  const due = timers.filter(pred)
  for (const t of due) { B.T.clearTimeout(t); t.fn() }
  return due
}
const tick = () => new Promise(r => setImmediate(r))
async function settle(n = 5) { for (let i = 0; i < n; i++) await tick() }

function fakeRes() {
  const r = { code: 200, body: null, statusMessage: "", status(c) { r.code = c; return r }, json(b) { r.body = b; return r } }
  return r
}
const GET  = (p, req = {}) => { const r = fakeRes(); expressStub._routes.GET[p](req, r); return r }
const POST = async (p, body) => { const r = fakeRes(); await expressStub._routes.POST[p]({ body }, r); return r }

const boom = code => ({ error: { message: `code ${code}`, output: { statusCode: code } } })
const currentSock = () => socks[socks.length - 1]

let passed = 0
async function test(name, fn) {
  try { await fn(); passed++; realLog(`  ok   ${name}`) }
  catch (e) { realLog(`  FAIL ${name}\n       ${e.stack}`); process.exitCode = 1 }
}

// ── Tests ────────────────────────────────────────────────────────────────────

;(async () => {
  realLog("whatsapp_bridge tests")

  await test("classifyDisconnect covers every Baileys reason", () => {
    const c = B.classifyDisconnect
    assert.strictEqual(c(401).action, "relink")
    assert.strictEqual(c(411).action, "relink")
    assert.strictEqual(c(515).reason, "restartRequired"); assert.ok(c(515).immediate)
    assert.strictEqual(c(440).reason, "connectionReplaced"); assert.ok(c(440).minDelayMs >= 30000)
    assert.strictEqual(c(403).reason, "forbidden"); assert.ok(c(403).minDelayMs >= 600000)
    assert.strictEqual(c(500).reason, "badSession"); assert.strictEqual(c(500).relinkAfter, 3)
    assert.strictEqual(c(428).action, "reconnect")
    assert.strictEqual(c(408).action, "reconnect")
    assert.strictEqual(c(503).action, "reconnect")
    assert.strictEqual(c(undefined).action, "reconnect")
    assert.strictEqual(c(999).action, "reconnect")
  })

  await test("backoffMs doubles and caps", () => {
    assert.deepStrictEqual([1, 2, 3, 4, 5, 6, 7, 8].map(a => B.backoffMs(a)), [2000, 4000, 8000, 16000, 32000, 64000, 120000, 120000])
    assert.strictEqual(B.backoffMs(50), 120000)
    assert.strictEqual(B.backoffMs(3, 1000, 30000), 4000)
  })

  await test("LRU is bounded and refreshes on get", () => {
    const l = new B.LRU(3)
    l.set("a", 1); l.set("b", 2); l.set("c", 3)
    l.get("a")                 // a is now most recent
    l.set("d", 4)              // evicts b
    assert.strictEqual(l.size, 3)
    assert.strictEqual(l.has("b"), false)
    assert.strictEqual(l.get("a"), 1)
    for (let i = 0; i < 10000; i++) l.set("k" + i, i)
    assert.strictEqual(l.size, 3)
  })

  await test("startWA creates a socket, binds creds.update and ignores stale sockets", async () => {
    await B.startWA()
    const s0 = currentSock()
    assert.ok(s0, "socket created")
    assert.strictEqual(baileysStub.lastOpts.markOnlineOnConnect, false)
    assert.strictEqual(B.S.paired, false)
    assert.strictEqual(B.S.connection, "connecting")
    await s0.ev.emit("connection.update", { connection: "open" })
    assert.strictEqual(B.S.connected, true)
    assert.strictEqual(B.S.user, "917000000000")
    assert.ok(B.S.lastEventAt > 0, "event touched the watchdog clock")
    const stable = timers.find(t => t.ms === 30000)
    assert.ok(stable, "stability timer armed on open")
  })

  await test("reconnect backoff grows per close and resets after a stable open", async () => {
    let s = currentSock()
    const delays = []
    for (const code of [428, 408, 503, 428]) {
      await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(code) })
      assert.strictEqual(B.S.connected, false)
      const t = timers.find(t => B.S.reconnectTimer === t)
      assert.ok(t, "reconnect timer scheduled")
      delays.push(t.ms)
      fire(x => x === t)           // run the reconnect now
      await settle()
      s = currentSock()
    }
    assert.ok(delays[0] >= 2000 && delays[0] < 3000, `attempt 1 ≈ 2s (${delays[0]})`)
    assert.ok(delays[1] >= 4000 && delays[1] < 5000, `attempt 2 ≈ 4s (${delays[1]})`)
    assert.ok(delays[2] >= 8000 && delays[2] < 9000, `attempt 3 ≈ 8s (${delays[2]})`)
    assert.ok(delays[3] >= 16000 && delays[3] < 17000, `attempt 4 ≈ 16s (${delays[3]})`)
    assert.strictEqual(B.S.reconnectAttempt, 4)
    assert.strictEqual(B.S.lastDisconnect.code, 428)
    // open + stable → ladder resets
    await s.ev.emit("connection.update", { connection: "open" })
    fire(t => t.ms === 30000)
    assert.strictEqual(B.S.reconnectAttempt, 0)
    const st = GET("/api/whatsapp/status").body
    assert.strictEqual(st.reconnect_attempts, 0)
  })

  await test("restartRequired reconnects immediately; connectionReplaced waits ≥30s", async () => {
    let s = currentSock()
    await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(515) })
    let t = B.S.reconnectTimer
    assert.ok(t.ms >= 500 && t.ms < 1500, `515 → ~0.5s (${t.ms})`)
    fire(x => x === t); await settle(); s = currentSock()
    await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(440) })
    t = B.S.reconnectTimer
    assert.ok(t.ms >= 30000 && t.ms < 31000, `440 → ≥30s (${t.ms})`)
    assert.ok(logsMatching(/opened elsewhere/).length >= 1)
    fire(x => x === t); await settle()
  })

  await test("loggedOut wipes the auth dir exactly once, then a QR is surfaced and logged once a minute", async () => {
    fs.writeFileSync(path.join(AUTH_DIR, "creds.json"), "{}")
    let s = currentSock()
    await s.ev.emit("connection.update", { connection: "open" })
    assert.strictEqual(B.S.paired, true)
    await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(401) })
    assert.strictEqual(fs.existsSync(path.join(AUTH_DIR, "creds.json")), false, "auth dir wiped on loggedOut")
    assert.strictEqual(B.S.paired, false)
    assert.strictEqual(B.S.relinks, 1)
    assert.strictEqual(B.S.reconnectAttempt, 0, "relink does not count as a backoff attempt")
    const t = B.S.reconnectTimer
    assert.ok(t.ms >= 2000 && t.ms < 3000)
    fire(x => x === t); await settle()
    s = currentSock()
    assert.ok(fs.existsSync(AUTH_DIR), "auth dir recreated for the fresh session")
    // a flood of QR refreshes → one log line per minute
    logs.length = 0
    for (let i = 0; i < 30; i++) await s.ev.emit("connection.update", { qr: "qr-" + i })
    assert.strictEqual(logsMatching(/QR needed/).length, 1, "QR logged once, not 30 times")
    fakeNow += 61 * 1000
    await s.ev.emit("connection.update", { qr: "qr-later" })
    const later = logsMatching(/QR needed/)
    assert.strictEqual(later.length, 2)
    assert.ok(/\+29 similar/.test(later[1]), "suppressed count reported")
    const st = GET("/api/whatsapp/status")
    assert.strictEqual(st.code, 200, "unpaired bridge is still healthy")
    assert.strictEqual(st.body.qr_pending, true)
    assert.strictEqual(st.body.connected, false)
    assert.ok(/QR/.test(st.body.message))
    const qr = GET("/api/whatsapp/qr").body
    assert.ok(qr.qr && qr.qr.startsWith("data:image/png"))
    // non-relink closes never touch the auth dir
    fs.writeFileSync(path.join(AUTH_DIR, "creds.json"), "{}")
    await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(428) })
    assert.ok(fs.existsSync(path.join(AUTH_DIR, "creds.json")), "428 leaves the session alone")
    fire(x => x === B.S.reconnectTimer); await settle()
  })

  await test("badSession relinks only after 3 in a row", async () => {
    let s = currentSock()
    for (let i = 1; i <= 3; i++) {
      fs.writeFileSync(path.join(AUTH_DIR, "creds.json"), "{}")
      await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(500) })
      const wiped = !fs.existsSync(path.join(AUTH_DIR, "creds.json"))
      assert.strictEqual(wiped, i === 3, `badSession #${i} wiped=${wiped}`)
      fire(x => x === B.S.reconnectTimer); await settle(); s = currentSock()
    }
    assert.strictEqual(B.S.relinks, 2)
  })

  await test("send returns 503 with a readable reason while unpaired / reconnecting", async () => {
    const s = currentSock()
    B.S.paired = false; B.S.connected = false; B.S.qrPending = true
    let r = await POST("/api/whatsapp/send", { to: "917000512030", text: "hi" })
    assert.strictEqual(r.code, 503)
    assert.strictEqual(r.body.sent, false)
    assert.strictEqual(r.body.ok, false)
    assert.strictEqual(r.body.reason, "not paired — scan QR")
    assert.strictEqual(r.statusMessage, "not paired - scan QR", "ASCII reason phrase for urllib's HTTPError")
    B.S.paired = true; B.S.qrPending = false
    r = await POST("/api/whatsapp/send", { to: "917000512030", text: "hi" })
    assert.strictEqual(r.code, 503)
    assert.strictEqual(r.body.reason, "bridge reconnecting — retry shortly")
    r = await POST("/api/whatsapp/send", { to: "", text: "" })
    assert.strictEqual(r.code, 400); assert.strictEqual(r.body.sent, false)
    // connected → delivered
    await s.ev.emit("connection.update", { connection: "open" })
    r = await POST("/api/whatsapp/send", { to: "+91 70005 12030", text: "alert" })
    assert.strictEqual(r.code, 200)
    assert.deepStrictEqual(r.body, { ok: true, sent: true, jid: "917000512030@s.whatsapp.net" })
    assert.strictEqual(s.sent[0].jid, "917000512030@s.whatsapp.net")
  })

  await test("status endpoint carries the required shape and keeps the old fields", () => {
    const r = GET("/api/whatsapp/status")
    assert.strictEqual(r.code, 200)
    const st = r.body
    for (const k of ["connected", "account", "qr_pending", "last_event_at", "queued", "dropped", "uptime_s", "version",
                     "watch_mode", "watched_groups", "state", "paired", "message", "last_disconnect", "reconnect_attempts", "wedged", "forwarded", "caches"]) {
      assert.ok(k in st, `status has ${k}`)
    }
    assert.strictEqual(st.account, "9")
    assert.strictEqual(typeof st.uptime_s, "number")
    assert.strictEqual(typeof st.queued, "number")
    assert.strictEqual(typeof st.dropped, "number")
    assert.ok(typeof st.version === "string" && st.version !== "unknown")
    assert.ok(Array.isArray(st.watched_groups))
    assert.ok(/^\d{4}-\d\d-\d\dT/.test(st.last_event_at))
    assert.strictEqual(st.wedged, false)
    const h = GET("/healthz"); assert.strictEqual(h.code, 200); assert.strictEqual(h.body.ok, true)
  })

  await test("queue: 5xx / ECONNREFUSED retried with backoff, then delivered", async () => {
    const calls = []
    let n = 0
    B.setTransport(async (p, data) => { calls.push(p); n++; return n <= 3 ? (n === 1 ? { status: 0, error: "connect ECONNREFUSED" } : { status: 503 }) : { status: 200 } })
    const before = B.Q.delivered
    const seen = new Set(timers)
    const p = B.queuePost("/api/whatsapp/message", { text: "x" })
    await p                                   // accepted (slot was free)
    await settle()
    for (let i = 0; i < 3; i++) {             // three retry sleeps
      const t = timers.find(t => !seen.has(t))
      assert.ok(t, "retry sleep scheduled")
      const expected = B.backoffMs(i + 1, 1000, 30000)
      assert.ok(t.ms >= expected && t.ms < expected + 1000, `retry ${i + 1} delay ${t.ms} ≈ ${expected}`)
      fire(x => x === t); await settle()
    }
    await B.queueIdle()
    assert.strictEqual(calls.length, 4)
    assert.strictEqual(B.Q.delivered, before + 1)
    assert.strictEqual(B.Q.retries >= 3, true)
    assert.ok(logsMatching(/retrying \(attempt 1\/10/).length >= 1)
  })

  await test("queue: backend down for good → dropped after max attempts, counted and logged once", async () => {
    B.setTransport(async () => ({ status: 0, error: "connect ECONNREFUSED 127.0.0.1:8501" }))
    const dropped0 = B.Q.dropped
    logs.length = 0
    fakeNow += 11000                          // past the 10 s drop-log throttle
    const seen = new Set(timers)
    await B.queuePost("/api/whatsapp/message", { text: "y" })
    for (let i = 0; i < B.QCFG.maxAttempts + 2; i++) { await settle(); fire(t => !seen.has(t)) }
    await B.queueIdle()
    assert.strictEqual(B.Q.dropped, dropped0 + 1)
    const dl = logsMatching(/^dropped 1 message\(s\) — backend unreachable after 10 attempts/)
    assert.strictEqual(dl.length, 1, "one dropped-count line")
    assert.ok(/dropped in total since start/.test(dl[0]))
  })

  await test("queue: 4xx is rejected, never retried", async () => {
    let n = 0
    B.setTransport(async () => { n++; return { status: 401 } })
    const rej0 = B.Q.rejected
    await B.queuePost("/api/whatsapp/message", { text: "z" })
    await B.queueIdle()
    assert.strictEqual(n, 1)
    assert.strictEqual(B.Q.rejected, rej0 + 1)
    assert.ok(logsMatching(/MDO_AUTH_TOKEN missing/).length >= 1)
  })

  await test("queue: bounded buffer drops the oldest, resolves every caller, logs a dropped line", async () => {
    const saved = { maxQueue: B.QCFG.maxQueue, maxInFlight: B.QCFG.maxInFlight }
    B.QCFG.maxQueue = 10
    B.QCFG.maxInFlight = 1
    let release
    const gate = new Promise(r => { release = r })
    B.setTransport(async () => { await gate; return { status: 200 } })
    const dropped0 = B.Q.dropped
    logs.length = 0
    fakeNow += 11000                          // past the 10 s drop-log throttle
    const accepted = []
    for (let i = 0; i < 16; i++) accepted.push(B.queuePost("/api/whatsapp/message", { i }))
    // 1 in flight, 10 pending, 5 dropped (oldest)
    assert.strictEqual(B.Q.inFlight, 1)
    assert.strictEqual(B.Q.pending.length, 10)
    assert.strictEqual(B.Q.dropped, dropped0 + 5)
    assert.deepStrictEqual(B.Q.pending.map(j => JSON.parse(j.data).i), [6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    assert.ok(B.Q.bytes > 0)
    assert.strictEqual(logsMatching(/queue full/).length, 1, "throttled to one line")
    const st = GET("/api/whatsapp/status").body
    assert.strictEqual(st.queued, 10); assert.strictEqual(st.in_flight, 1)
    release()
    await Promise.all(accepted)            // dropped callers were resolved too
    await B.queueIdle()
    assert.strictEqual(B.Q.pending.length, 0)
    assert.strictEqual(B.Q.bytes, 0)
    Object.assign(B.QCFG, saved)
    B.setTransport(async () => ({ status: 200 }))
  })

  await test("queue: byte budget caps image-heavy bursts", async () => {
    const saved = { maxBytes: B.QCFG.maxBytes, maxInFlight: B.QCFG.maxInFlight }
    B.QCFG.maxBytes = 5000
    B.QCFG.maxInFlight = 1
    let release
    const gate = new Promise(r => { release = r })
    B.setTransport(async () => { await gate; return { status: 200 } })
    const dropped0 = B.Q.dropped
    const ps = []
    for (let i = 0; i < 6; i++) ps.push(B.queuePost("/api/whatsapp/message", { i, image_b64: "A".repeat(1500) }))
    assert.ok(B.Q.bytes <= 5000, `bytes ${B.Q.bytes} within budget`)
    assert.ok(B.Q.dropped > dropped0)
    release(); await Promise.all(ps); await B.queueIdle()
    Object.assign(B.QCFG, saved)
  })

  await test("ingest: a message is forwarded with the expected body; CoS prefix is never echoed", async () => {
    const posted = []
    B.setTransport(async (p, data) => { posted.push({ p, body: JSON.parse(data) }); return { status: 200 } })
    const s = currentSock()
    await s.ev.emit("connection.update", { connection: "open" })
    await s.ev.emit("messages.upsert", { type: "notify", messages: [
      { key: { remoteJid: "918888888888@s.whatsapp.net", fromMe: false, id: "M1" }, pushName: "Ravi", messageTimestamp: 1760000000, message: { conversation: "rake placed" } },
      { key: { remoteJid: "918888888888@s.whatsapp.net", fromMe: true, id: "M2" }, message: { conversation: "CoS · reply" } },
      { key: { remoteJid: "status@broadcast", id: "M3" }, message: { conversation: "status" } },
      { key: { remoteJid: "918888888888@s.whatsapp.net", id: "M4" }, message: { reactionMessage: {} } },
      { key: { remoteJid: "120363@g.us", id: "M5" }, message: { conversation: "group, metadata fails → retried later" } },
    ] })
    await B.queueIdle()
    const msgs = posted.filter(x => x.p === "/api/whatsapp/message")
    assert.strictEqual(msgs.length, 1, "exactly one message forwarded")
    assert.ok(posted.some(x => x.p === "/api/whatsapp/status" && x.body.connected === true), "connected status pinged to backend")
    const b = msgs[0].body
    assert.strictEqual(b.account, "9"); assert.strictEqual(b.group, "Ravi"); assert.strictEqual(b.sender, "Ravi")
    assert.strictEqual(b.text, "rake placed"); assert.strictEqual(b.chat_kind, "dm"); assert.strictEqual(b.from_me, 0)
    assert.strictEqual(b.wa_msg_id, "M1"); assert.strictEqual(b.timestamp, "2025-10-09T08:53:20.000Z")
    assert.strictEqual(B.contactNameCache.get("918888888888@s.whatsapp.net"), "Ravi")
    assert.strictEqual(B.groupMetaCache.has("120363@g.us"), false, "metadata failure not cached")
  })

  await test("watchdog: quiet socket is pinged, dead socket is restarted, idle unpaired socket left alone while a reconnect is pending", async () => {
    const s = currentSock()
    await s.ev.emit("connection.update", { connection: "open" })
    assert.strictEqual(await B.watchdogTick(fakeNow), "ok")
    fakeNow += 16 * 60 * 1000
    s.queryImpl = () => Promise.resolve({})
    assert.strictEqual(await B.watchdogTick(fakeNow), "pinged")
    assert.strictEqual(B.S.lastEventAt, fakeNow)
    assert.strictEqual(s.ended, null)
    fakeNow += 16 * 60 * 1000
    s.queryImpl = () => Promise.reject(new Error("timed out"))
    assert.strictEqual(await B.watchdogTick(fakeNow), "restarted")
    assert.strictEqual(s.ended, "watchdog")
    assert.strictEqual(B.S.connected, false)
    assert.strictEqual(B.S.watchdogRestarts, 1)
    assert.ok(B.S.reconnectTimer && B.S.reconnectTimer.ms >= 2000)
    // the old socket's late close event is stale and must not double-schedule
    const before = B.S.reconnectTimer
    await s.ev.emit("connection.update", { connection: "close", lastDisconnect: boom(428) })
    assert.strictEqual(B.S.reconnectTimer, before)
    assert.strictEqual(await B.watchdogTick(fakeNow), "waiting")
    fire(x => x === before); await settle()
    const s2 = currentSock()
    assert.notStrictEqual(s2, s)
    await s2.ev.emit("connection.update", { connection: "open" })
    fire(t => t.ms === 30000)
    assert.strictEqual(B.S.watchdogRestarts, 0, "reset after a stable open")
    assert.strictEqual(B.isWedged(), false)
  })

  await test("wedged only after repeated start failures; status then returns 503", async () => {
    B.S.startFailures = 5
    const r = GET("/api/whatsapp/status")
    assert.strictEqual(r.code, 503); assert.strictEqual(r.body.wedged, true)
    assert.strictEqual(GET("/healthz").code, 503)
    B.S.startFailures = 0
    assert.strictEqual(GET("/api/whatsapp/status").code, 200)
  })

  await test("asciiReason strips non-ASCII for the HTTP reason phrase", () => {
    assert.strictEqual(B.asciiReason("not paired — scan QR"), "not paired - scan QR")
    assert.strictEqual(B.asciiReason("a\nb\tc"), "a-b-c", "control chars never reach the reason phrase")
  })

  // ── done ──
  console.log = realLog
  try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }) } catch (e) { /* ignore */ }
  realLog(`\n${passed} passed${process.exitCode ? ", some FAILED" : ""}`)
  process.exit(process.exitCode || 0)
})().catch(e => { console.log = realLog; realLog("harness error", e); process.exit(1) })
