/**
 * MDO WhatsApp Bridge
 * Connects to WhatsApp Web via Baileys and forwards EVERY chat on the account —
 * groups and 1:1 DMs, incoming and Aman's own replies — to the MDO backend via
 * HTTP. The backend classifies business vs personal and decides what to store;
 * the bridge only drops status/broadcast/newsletter traffic and unresolved LIDs.
 */

const makeWASocket = require("@whiskeysockets/baileys").default
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion,
        downloadMediaMessage } = require("@whiskeysockets/baileys")
const express = require("express")
const QRCode  = require("qrcode")
const pino    = require("pino")
const path    = require("path")
const fs      = require("fs")

const app  = express()
const PORT = process.env.PORT || 3001
const MDO_BACKEND = process.env.MDO_BACKEND_URL || "http://localhost:8501"

// Which bridge this is: "1" (ops phone) or "2" (second phone). Sent on every
// forwarded message so the backend can tell the two accounts apart.
const WA_ACCOUNT = String(process.env.WA_ACCOUNT || "1")

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

// Message kinds that carry no content (reactions, edits/deletes/ephemeral
// settings). Forwarding them would show up as fake "[media]" replies and skew
// response-time metrics.
const NON_CONTENT_KEYS = new Set(["protocolMessage", "reactionMessage"])

const bareNumber = jid => String(jid || "").split(":")[0].split("@")[0]

app.use(express.json())

let qrCodeData  = null   // latest QR as base64 PNG
let isConnected = false
let sock        = null

// ── Start WhatsApp connection ─────────────────────────────────────────────────

async function startWA() {
  const AUTH_DIR = process.env.AUTH_DIR || "/data/wa_auth"
  if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true })

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  // jid → { subject, participants: [jid, ...] }. Populated in bulk on connect;
  // per-message lookups are only a fallback. Failures are NOT cached —
  // WhatsApp rate-limits metadata calls during the post-pairing history flood,
  // and a cached failure would silently blackhole that group forever.
  const groupMetaCache = {}

  // jid → display name, fed by contacts.upsert / contacts.update and by the
  // pushName on incoming DMs. Used to name DM chats on Aman's own (fromMe)
  // messages, where pushName is Aman himself, and to name group participants.
  const contactNameCache = {}
  function rememberContact(c) {
    if (!c || !c.id) return
    const name = c.notify || c.name || c.verifiedName
    if (name) contactNameCache[c.id] = String(name)
  }
  function rememberGroup(jid, meta) {
    if (!jid || !meta) return
    groupMetaCache[jid] = {
      subject: meta.subject || "",
      participants: Array.isArray(meta.participants) ? meta.participants.map(p => p.id).filter(Boolean) : [],
    }
  }

  sock = makeWASocket({
    version,
    auth: state,
    // Ask the phone to push chat history after pairing — without this the
    // messaging-history.set event never fires and backfill is empty.
    syncFullHistory: true,
    logger: require("pino")({ level: "silent" }),
  })

  // QR code — show on MDO dashboard for scanning
  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update

    if (qr) {
      qrCodeData  = await QRCode.toDataURL(qr)
      isConnected = false
      console.log("QR ready — scan from MDO dashboard /api/whatsapp/qr")
    }

    if (connection === "open") {
      isConnected = true
      qrCodeData  = null
      console.log(`WhatsApp connected (account ${WA_ACCOUNT})`)
      try {
        const groups = await sock.groupFetchAllParticipating()
        let watched = 0
        for (const [jid, meta] of Object.entries(groups)) {
          rememberGroup(jid, meta)
          if (isWatchedName(meta.subject)) {
            watched++
            if (WATCH_MODE !== "all") console.log(`watching: ${meta.subject}`)
          }
        }
        console.log(`group cache primed: ${Object.keys(groups).length} groups, ${watched} watched (mode: ${WATCH_MODE})`)
        if (WATCH_MODE !== "all") {
          if (watched < WATCHED_GROUPS.length) {
            const missed = Object.values(groups)
              .map(m => m.subject || "")
              .filter(n => n && !isWatchedName(n) && /vwlr|vedanta|rake|rkm|shifting|hotel|night|report|dsr|front office|kitchen/i.test(n))
            if (missed.length) console.log(`unmatched candidates: ${missed.join(" | ")}`)
          }
          if (watched === 0) {
            console.log("WARNING: no groups matched WATCHED_GROUPS — check the names above against the list in index.js")
          }
        }
      } catch (e) {
        console.log("group prefetch failed (falling back to per-message lookups):", e.message)
      }
      await postToMDO("/api/whatsapp/status", { connected: true, account: WA_ACCOUNT, message: "WhatsApp bridge connected" })
    }

    if (connection === "close") {
      isConnected = false
      const loggedOut = lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut
      if (!loggedOut) {
        console.log("WhatsApp disconnected — reconnecting in 5s")
        setTimeout(startWA, 5000)
      } else {
        // Device was unlinked from the phone. The stored session is dead —
        // wipe it and restart so a FRESH QR is generated for re-pairing.
        console.log("WhatsApp logged out — clearing dead session, generating fresh QR")
        try { fs.rmSync(AUTH_DIR, { recursive: true, force: true }) } catch (e) {
          console.log("could not clear auth dir:", e.message)
        }
        await postToMDO("/api/whatsapp/status", { connected: false, account: WA_ACCOUNT, message: "WhatsApp logged out — rescan QR" })
        setTimeout(startWA, 2000)
      }
    }
  })

  sock.ev.on("creds.update", saveCreds)

  // Contact names — arrive in bulk during history sync and trickle in live.
  sock.ev.on("contacts.upsert", (contacts) => { for (const c of contacts || []) rememberContact(c) })
  sock.ev.on("contacts.update", (contacts) => { for (const c of contacts || []) rememberContact(c) })

  // ── Message ingestion (live + history backfill) ────────────────────────────

  async function resolveGroupName(jid) {
    const cached = groupMetaCache[jid]
    if (cached !== undefined) return cached.subject
    try {
      const meta = await sock.groupMetadata(jid)
      rememberGroup(jid, meta)
      return groupMetaCache[jid].subject
    } catch (e) {
      console.log(`groupMetadata failed for ${jid}: ${e.message} (will retry on next message)`)
      return null // deliberately not cached
    }
  }

  // Up to 50 participant names (cached contact name, else bare number) — only
  // when the metadata cache actually has them; never a metadata call here.
  function groupParticipants(jid) {
    const ids = groupMetaCache[jid]?.participants
    if (!ids || !ids.length) return null
    return ids.slice(0, 50).map(id => contactNameCache[id] || bareNumber(id))
  }

  // "group" | "dm" | null. Drops status@broadcast, @broadcast, @newsletter and
  // anything else we cannot route. A @lid chat is accepted only when Baileys
  // hands us the resolved phone-number jid alongside it.
  function classifyChat(key) {
    let jid = key?.remoteJid || ""
    if (jid.endsWith("@lid")) {
      const alt = key?.remoteJidAlt || key?.senderPn || ""
      if (!alt.endsWith("@s.whatsapp.net")) return { kind: null, jid }
      jid = alt
    }
    if (jid.endsWith("@g.us")) return { kind: "group", jid }
    if (jid.endsWith("@s.whatsapp.net")) return { kind: "dm", jid }
    return { kind: null, jid } // status@broadcast, *@broadcast, *@newsletter, unknown
  }

  // ── Chief of Staff: direct messages to/from Aman ──────────────────────────
  // COS_INBOUND=1 turns this on. Two shapes work:
  //   • a dedicated CoS number running this bridge: Aman's DMs arrive !fromMe
  //     from a number in COS_ALLOWED_NUMBERS;
  //   • Aman's own number (this bridge = his phone): he types in the
  //     "message yourself" chat, which arrives fromMe with remoteJid = own jid.
  // The backend's replies start with "CoS ·" and are skipped here, so a
  // self-chat never loops.
  const COS_INBOUND = (process.env.COS_INBOUND || "0") === "1"
  const COS_ALLOWED = (process.env.COS_ALLOWED_NUMBERS || "").split(",").map(s => s.replace(/[^0-9]/g, "")).filter(Boolean)
  function ownNumber() { return String(sock?.user?.id || "").split(":")[0].split("@")[0] }

  async function routeDirectMessage(msg) {
    if (!COS_INBOUND || !msg?.message) return false
    const jid = msg.key?.remoteJid || ""
    if (!jid.endsWith("@s.whatsapp.net")) return false
    const number = jid.split("@")[0]
    const fromMe = !!msg.key?.fromMe
    const selfChat = fromMe && number === ownNumber()
    if (!selfChat && (fromMe || (COS_ALLOWED.length && !COS_ALLOWED.includes(number)))) return false
    const text = msg.message.conversation || msg.message.extendedTextMessage?.text || ""
    if (!text || text.startsWith(COS_PREFIX)) return false
    console.log(`[CoS inbound] ${number}: ${text.slice(0, 80)}`)
    await postToMDO("/api/cos/inbound", { from: number, text, channel: "baileys", message_id: msg.key?.id || "" })
    return true
  }

  // Returns the chat kind ("group" | "dm") if the message was forwarded to the
  // backend, else null. `skipFromMe` is kept for callers but defaults to false:
  // Aman's own replies are needed for response-time metrics.
  async function ingestMessage(msg, { skipFromMe = false } = {}) {
    if (!msg?.message) return null
    if (await routeDirectMessage(msg)) return "cos"
    const fromMe = !!msg.key?.fromMe
    if (skipFromMe && fromMe) return null

    const { kind, jid } = classifyChat(msg.key)
    if (!kind) return null

    // Unwrap ephemeral / view-once envelopes so the content checks below see
    // the real node; otherwise everything inside them reads as "[media]".
    const m = msg.message.ephemeralMessage?.message
      || msg.message.viewOnceMessage?.message
      || msg.message.viewOnceMessageV2?.message
      || msg.message
    const contentKeys = Object.keys(m).filter(k => k !== "messageContextInfo" && k !== "senderKeyDistributionMessage")
    if (!contentKeys.length || contentKeys.every(k => NON_CONTENT_KEYS.has(k))) return null

    const text = (
      m.conversation ||
      m.extendedTextMessage?.text ||
      m.imageMessage?.caption ||
      m.videoMessage?.caption ||
      m.documentMessage?.caption ||
      "[media]"
    )
    // Never echo the backend's own CoS replies back to it (they arrive fromMe
    // on a self-chat bridge, !fromMe when a dedicated CoS number sent them).
    if (String(text).startsWith(COS_PREFIX)) return null

    // ── Chat display name ──
    let chatName
    if (kind === "group") {
      chatName = await resolveGroupName(jid)
      if (!chatName) return null
      if (!isWatchedName(chatName)) return null
    } else {
      const number = bareNumber(jid)
      if (!fromMe && msg.pushName) contactNameCache[jid] = msg.pushName
      chatName = (!fromMe && msg.pushName) || contactNameCache[jid] || number
    }

    // ── Sender ──
    let sender
    if (fromMe) {
      sender = "me"
    } else if (kind === "group") {
      const pJid = msg.key.participantAlt || msg.key.participant || ""
      sender = msg.pushName || contactNameCache[pJid] || bareNumber(pJid) || "Unknown"
    } else {
      sender = msg.pushName || contactNameCache[jid] || bareNumber(jid)
    }

    // Images carry the numbers that matter here — weighbridge slips, dispatch
    // tallies, hotel sales registers. For GROUPS download and hand them to the
    // backend, which decides whether to run vision extraction. DMs: caption or
    // "[media]" only — no download.
    let image_b64 = null, image_mime = null
    if (kind === "group") {
      const imgNode = m.imageMessage
        || (String(m.documentMessage?.mimetype || "").startsWith("image/") ? m.documentMessage : null)
      if (imgNode && (imgNode.fileLength || 0) <= 8 * 1024 * 1024) {
        try {
          const buf = await downloadMediaMessage(msg, "buffer", {}, { logger: pino({ level: "silent" }) })
          if (buf && buf.length) {
            image_b64 = buf.toString("base64")
            image_mime = imgNode.mimetype || "image/jpeg"
          }
        } catch (e) {
          console.log("image download failed:", e.message)
        }
      }
    }

    const tsNum = Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000)
    const timestamp = new Date(tsNum * 1000).toISOString()

    const tag = kind === "dm" ? `[dm:${chatName}]` : `[${chatName}]`
    console.log(`${tag} ${sender}: ${String(text).slice(0, 80)}`)

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
      wa_msg_id: msg.key?.id || "",
      ...(participants ? { participants } : {}),
      ...(image_b64 ? { image_b64, image_mime } : {}),
    })
    forwardedTotal++
    if (forwardedTotal % 500 === 0) console.log(`forwarded ${forwardedTotal} messages so far (account ${WA_ACCOUNT})`)
    return kind
  }

  // Live messages
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return
    for (const msg of messages) {
      try { await ingestMessage(msg) } catch (e) { console.log("ingest error:", e.message) }
    }
  })

  // History backfill — WhatsApp pushes recent chat history right after the QR
  // pairing. Ingest it so the Ops Feed is populated immediately, not empty.
  sock.ev.on("messaging-history.set", async ({ messages, contacts, isLatest, progress }) => {
    for (const c of contacts || []) rememberContact(c)
    const recent = (messages || []).slice(-2000) // cap per chunk; chunks keep arriving
    console.log(`history sync: chunk of ${recent.length} messages (progress: ${progress ?? "?"}, latest: ${isLatest ?? "?"})`)
    const counts = { group: 0, dm: 0, cos: 0, skipped: 0 }
    for (const msg of recent) {
      try {
        const kind = await ingestMessage(msg, { skipFromMe: false })
        if (kind) counts[kind] = (counts[kind] || 0) + 1
        else counts.skipped++
      } catch (e) {
        console.log("history ingest error:", e.message)
      }
    }
    await queueIdle()
    console.log(`history sync: forwarded ${counts.group + counts.dm} messages to backend (groups: ${counts.group}, dms: ${counts.dm}, cos: ${counts.cos}, skipped: ${counts.skipped})`)
  })
}

// ── Backpressure: bounded POST queue ─────────────────────────────────────────
// History sync arrives in bursts of thousands. queuePost() resolves when the
// job has been HANDED to the HTTP layer (a slot was free), so a caller that
// awaits it is throttled to MAX_IN_FLIGHT concurrent requests without having
// to wait for each response. queueIdle() resolves once everything has drained.

const MAX_IN_FLIGHT = 4
const postQueue = { pending: [], inFlight: 0, idleWaiters: [] }
let forwardedTotal = 0

function queuePost(path, body) {
  return new Promise((accepted) => {
    postQueue.pending.push({ path, body, accepted })
    pumpQueue()
  })
}

function pumpQueue() {
  while (postQueue.inFlight < MAX_IN_FLIGHT && postQueue.pending.length) {
    const job = postQueue.pending.shift()
    postQueue.inFlight++
    job.accepted()
    postToMDO(job.path, job.body).then(() => {
      postQueue.inFlight--
      pumpQueue()
      if (!postQueue.inFlight && !postQueue.pending.length) {
        postQueue.idleWaiters.splice(0).forEach(r => r())
      }
    })
  }
}

function queueIdle() {
  return new Promise((resolve) => {
    if (!postQueue.inFlight && !postQueue.pending.length) return resolve()
    postQueue.idleWaiters.push(resolve)
  })
}

// ── POST to MDO backend ───────────────────────────────────────────────────────

function postToMDO(path, body) {
  return new Promise((resolve) => {
    try {
      const http = require("http")
      const url  = new URL(MDO_BACKEND + path)
      const data = JSON.stringify(body)
      const req  = http.request({
        hostname: url.hostname,
        port: url.port || 80,
        path: url.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(data),
          // backend access key (when MDO_AUTH_TOKEN protection is enabled)
          "X-MDO-Key": process.env.MDO_AUTH_TOKEN || "",
        },
      }, (res) => {
        if (res.statusCode >= 300) {
          const hint = res.statusCode === 401
            ? " — MDO_AUTH_TOKEN missing/wrong in the whatsapp container (docker compose up -d after .env edits)"
            : ""
          console.log(`POST ${path} -> ${res.statusCode}${hint}`)
        }
        res.resume()
        res.on("end", resolve)
        res.on("error", resolve)
      })
      req.on("error", (e) => {
        console.log(`POST ${path} failed: ${e.message}`)
        resolve()
      })
      req.write(data)
      req.end()
    } catch (e) {
      console.log(`POST ${path} error: ${e.message}`)
      resolve()
    }
  })
}

// ── Express API ───────────────────────────────────────────────────────────────

// QR code for scanning
app.get("/api/whatsapp/qr", (req, res) => {
  if (isConnected) {
    return res.json({ connected: true, qr: null })
  }
  if (!qrCodeData) {
    return res.json({ connected: false, qr: null, message: "Starting up, check back in 10 seconds" })
  }
  res.json({ connected: false, qr: qrCodeData })
})

// Connection status
app.get("/api/whatsapp/status", (req, res) => {
  res.json({ connected: isConnected, account: WA_ACCOUNT, watch_mode: WATCH_MODE, watched_groups: WATCHED_GROUPS })
})

// Send a message (used by the backend to push 🔴 alerts to Aman's phone).
// `to` may be a bare number (917000512030), a full jid, or a group jid.
app.post("/api/whatsapp/send", async (req, res) => {
  const { to, text } = req.body || {}
  if (!to || !text) return res.status(400).json({ ok: false, error: "to and text required" })
  if (!isConnected || !sock) return res.status(503).json({ ok: false, error: "WhatsApp not connected" })
  const jid = String(to).includes("@")
    ? String(to)
    : String(to).replace(/[^0-9]/g, "") + "@s.whatsapp.net"
  try {
    await sock.sendMessage(jid, { text: String(text).slice(0, 4000) })
    console.log(`sent alert -> ${jid} (${String(text).length} chars)`)
    res.json({ ok: true, jid })
  } catch (e) {
    console.log("send failed:", e.message)
    res.status(500).json({ ok: false, error: e.message })
  }
})

// Health check
app.get("/health", (req, res) => res.json({ ok: true }))

app.listen(PORT, () => {
  console.log(`WhatsApp bridge running on port ${PORT} (account ${WA_ACCOUNT})`)
  startWA()
})
