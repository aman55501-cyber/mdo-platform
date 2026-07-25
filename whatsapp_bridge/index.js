/**
 * MDO WhatsApp Bridge
 * Connects to WhatsApp Web via Baileys, listens to VWLR ops groups,
 * forwards messages to MDO backend via HTTP.
 */

const makeWASocket = require("@whiskeysockets/baileys").default
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys")
const express = require("express")
const QRCode  = require("qrcode")
const path    = require("path")
const fs      = require("fs")

const app  = express()
const PORT = process.env.PORT || 3001
const MDO_BACKEND = process.env.MDO_BACKEND_URL || "http://localhost:8501"

// Groups to monitor (partial name match — case insensitive)
const WATCHED_GROUPS = [
  "vedanta daily report",
  "vwlr rake status",
  "vwlr rake placement",
  "vwlr to apl raigarh",
  "vwlr-rkm group",
  "vwlr shifting",
]

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

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: true,
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
      console.log("WhatsApp connected")
      await postToMDO("/api/whatsapp/status", { connected: true, message: "WhatsApp bridge connected" })
    }

    if (connection === "close") {
      isConnected = false
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut
      console.log("WhatsApp disconnected. Reconnecting:", shouldReconnect)
      if (shouldReconnect) setTimeout(startWA, 5000)
      else {
        await postToMDO("/api/whatsapp/status", { connected: false, message: "WhatsApp logged out — rescan QR" })
      }
    }
  })

  sock.ev.on("creds.update", saveCreds)

  // ── Message ingestion (live + history backfill) ────────────────────────────
  const groupNameCache = {}

  async function resolveGroupName(jid) {
    if (groupNameCache[jid] !== undefined) return groupNameCache[jid]
    try {
      const meta = await sock.groupMetadata(jid)
      groupNameCache[jid] = meta.subject || ""
    } catch {
      groupNameCache[jid] = null // unknown — don't retry every message
    }
    return groupNameCache[jid]
  }

  async function ingestMessage(msg, { skipFromMe = true } = {}) {
    if (!msg?.message) return
    if (skipFromMe && msg.key?.fromMe) return

    const jid = msg.key?.remoteJid || ""
    if (!jid.endsWith("@g.us")) return // groups only

    const groupName = await resolveGroupName(jid)
    if (!groupName) return

    const isWatched = WATCHED_GROUPS.some(g =>
      groupName.toLowerCase().includes(g.toLowerCase())
    )
    if (!isWatched) return

    const text = (
      msg.message.conversation ||
      msg.message.extendedTextMessage?.text ||
      msg.message.imageMessage?.caption ||
      msg.message.documentMessage?.caption ||
      "[media]"
    )

    const sender = msg.pushName || msg.key.participant || "Unknown"
    const tsNum = Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000)
    const timestamp = new Date(tsNum * 1000).toISOString()

    console.log(`[${groupName}] ${sender}: ${String(text).slice(0, 80)}`)

    await postToMDO("/api/whatsapp/message", {
      group: groupName,
      sender,
      text: String(text),
      timestamp,
      jid,
    })
  }

  // Live messages
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return
    for (const msg of messages) {
      try { await ingestMessage(msg) } catch {}
    }
  })

  // History backfill — WhatsApp pushes recent chat history right after the QR
  // pairing. Ingest it so the Ops Feed is populated immediately, not empty.
  sock.ev.on("messaging-history.set", async ({ messages }) => {
    const recent = (messages || []).slice(-400) // newest chunk only
    console.log(`history sync: scanning ${recent.length} messages for watched groups`)
    for (const msg of recent) {
      try { await ingestMessage(msg, { skipFromMe: false }) } catch {}
    }
  })
}

// ── POST to MDO backend ───────────────────────────────────────────────────────

async function postToMDO(path, body) {
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
    })
    req.write(data)
    req.end()
  } catch (e) {
    // Silent fail — don't crash bridge on backend unavailability
  }
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
  res.json({ connected: isConnected, watched_groups: WATCHED_GROUPS })
})

// Health check
app.get("/health", (req, res) => res.json({ ok: true }))

app.listen(PORT, () => {
  console.log(`WhatsApp bridge running on port ${PORT}`)
  startWA()
})
