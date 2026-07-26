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
// restrict to WATCHED_GROUPS above.
const WATCH_MODE = (process.env.WA_WATCH_MODE || "all").toLowerCase()

function isWatchedName(name) {
  if (!name) return false
  if (WATCH_MODE === "all") return true
  const n = normName(name)
  return WATCHED_NORM.some(g => n.includes(g))
}

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

  // jid → group subject. Populated in bulk on connect; per-message lookups are
  // only a fallback. Failures are NOT cached — WhatsApp rate-limits metadata
  // calls during the post-pairing history flood, and a cached failure would
  // silently blackhole that group forever.
  const groupNameCache = {}

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
      console.log("WhatsApp connected")
      try {
        const groups = await sock.groupFetchAllParticipating()
        let watched = 0
        for (const [jid, meta] of Object.entries(groups)) {
          groupNameCache[jid] = meta.subject || ""
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
      await postToMDO("/api/whatsapp/status", { connected: true, message: "WhatsApp bridge connected" })
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
        await postToMDO("/api/whatsapp/status", { connected: false, message: "WhatsApp logged out — rescan QR" })
        setTimeout(startWA, 2000)
      }
    }
  })

  sock.ev.on("creds.update", saveCreds)

  // ── Message ingestion (live + history backfill) ────────────────────────────

  async function resolveGroupName(jid) {
    const cached = groupNameCache[jid]
    if (cached !== undefined) return cached
    try {
      const meta = await sock.groupMetadata(jid)
      groupNameCache[jid] = meta.subject || ""
      return groupNameCache[jid]
    } catch (e) {
      console.log(`groupMetadata failed for ${jid}: ${e.message} (will retry on next message)`)
      return null // deliberately not cached
    }
  }

  // Returns true if the message was forwarded to the backend.
  async function ingestMessage(msg, { skipFromMe = true } = {}) {
    if (!msg?.message) return false
    if (skipFromMe && msg.key?.fromMe) return false

    const jid = msg.key?.remoteJid || ""
    if (!jid.endsWith("@g.us")) return false // groups only

    const groupName = await resolveGroupName(jid)
    if (!groupName) return false
    if (!isWatchedName(groupName)) return false

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
    return true
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
  sock.ev.on("messaging-history.set", async ({ messages, isLatest, progress }) => {
    const recent = (messages || []).slice(-2000) // cap per chunk; chunks keep arriving
    console.log(`history sync: chunk of ${recent.length} messages (progress: ${progress ?? "?"}, latest: ${isLatest ?? "?"})`)
    let ingested = 0
    for (const msg of recent) {
      try {
        if (await ingestMessage(msg, { skipFromMe: false })) ingested++
      } catch (e) {
        console.log("history ingest error:", e.message)
      }
    }
    console.log(`history sync: forwarded ${ingested} messages to backend`)
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
  res.json({ connected: isConnected, watched_groups: WATCHED_GROUPS })
})

// Health check
app.get("/health", (req, res) => res.json({ ok: true }))

app.listen(PORT, () => {
  console.log(`WhatsApp bridge running on port ${PORT}`)
  startWA()
})
