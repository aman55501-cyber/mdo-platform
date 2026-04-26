const express = require("express")
const { Client, LocalAuth } = require("whatsapp-web.js")
const qrcode = require("qrcode")
const fetch = require("node-fetch")

const app = express()
app.use(express.json())
app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "*")
  res.header("Access-Control-Allow-Headers", "Content-Type")
  next()
})

const MDO_BACKEND = process.env.MDO_BACKEND_URL || "http://localhost:8501"
const PORT = process.env.PORT || 3001

// Target groups to monitor
const TARGET_GROUPS = [
  "Vedanta Daily Report",
  "VWLR Rake status",
  "VWLR Rake Placement",
  "VWLR to APL Raigarh",
  "VWLR-RKM Group",
  "VWLR Shifting",
]

let currentQR = null
let isConnected = false
let clientReady = false

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "/data/wa-session" }),
  puppeteer: {
    executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium",
    args: [
      "--no-sandbox", "--disable-setuid-sandbox",
      "--disable-dev-shm-usage", "--disable-gpu",
      "--no-first-run", "--no-zygote", "--single-process",
    ],
  },
})

client.on("qr", async (qr) => {
  console.log("QR received")
  isConnected = false
  try {
    currentQR = await qrcode.toDataURL(qr)
  } catch (e) {
    currentQR = qr
  }
})

client.on("ready", () => {
  console.log("WhatsApp connected")
  isConnected = true
  clientReady = true
  currentQR = null
})

client.on("disconnected", () => {
  console.log("WhatsApp disconnected")
  isConnected = false
  clientReady = false
})

client.on("message", async (msg) => {
  try {
    const chat = await msg.getChat()
    const groupName = chat.name || ""

    // Only process messages from target groups
    const isTarget = TARGET_GROUPS.some(g =>
      groupName.toLowerCase().includes(g.toLowerCase())
    )
    if (!isTarget) return

    const contact = await msg.getContact()
    const senderName = contact.pushname || contact.name || msg.from

    const payload = {
      group: groupName,
      sender: senderName,
      message: msg.body,
      timestamp: new Date(msg.timestamp * 1000).toISOString(),
      type: msg.type,
    }

    console.log(`[${groupName}] ${senderName}: ${msg.body.slice(0, 80)}`)

    // Forward to MDO backend
    await fetch(`${MDO_BACKEND}/api/whatsapp/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(e => console.error("MDO forward error:", e.message))

  } catch (e) {
    console.error("Message handler error:", e.message)
  }
})

// Initialize WhatsApp client
client.initialize().catch(e => console.error("Init error:", e))

// API Routes
app.get("/api/whatsapp/qr", (req, res) => {
  res.json({
    connected: isConnected,
    ready: clientReady,
    qr: isConnected ? null : currentQR,
  })
})

app.get("/health", (req, res) => {
  res.json({ ok: true, connected: isConnected, ready: clientReady })
})

app.listen(PORT, () => {
  console.log(`WhatsApp bridge running on port ${PORT}`)
  console.log(`MDO backend: ${MDO_BACKEND}`)
})
