# Voice notes and your phone — setup (2026-10-11)

## A. Your phone: make WhatsApp the constant channel (5 minutes, once)
1. Save the CoS number as a contact named "CoS". Open the chat, pin it to the top.
2. Chat info → Notifications: custom tone ON, "Use high priority notifications" ON.
3. Android: Settings → Apps → WhatsApp → Battery → Unrestricted. Settings → Notifications → Do Not Disturb → allow WhatsApp "CoS". iPhone: Focus → allow "CoS" contact; Settings → Notifications → WhatsApp → Time Sensitive ON.
4. Keep "Message yourself" as the second channel: it works for typing commands (confirmed 2026-10-11) but WhatsApp may not ping you for messages from your own account, so the *alerts* must come from the CoS contact, not your own chat. If a line from the CoS ever shows only in "Message yourself" and does not ping, tell me and I switch the sender.
5. Reply grammar (the CoS understands these): `ok 14` / `no 14` · `plan washery: pour slab C2 @Ramesh; fix shuttering` · `done 3,4` · `miss 5 material by Ramesh` · `today`. Anything else is a question for the CoS brain (Sonnet).
6. You will receive: 07:30 objectives + plan, 19:30 planned-vs-actual, instant 🔴 lines, and an instant line whenever an agent is stuck with the roadblock named.

## B. Voice notes into the system — options and my pick
| Option | Cost | Hindi/Hinglish accuracy | Effort | Verdict |
|---|---|---|---|---|
| faster-whisper **small** on the VPS (live now) | ₹0 | fair; weaker on Hindi names and site terms | none | fine for English-heavy notes |
| faster-whisper **medium** on the VPS | ₹0; ~2–3 GB RAM, 2–3× slower, a ~1.5 GB model download | clearly better on Hindi/Hinglish | one setting (`VOICE_MODEL=medium`) | **my pick** |
| faster-whisper **large-v3** on the VPS | ₹0; ~6 GB RAM, slow on CPU | best | risks the 8 GB box | only if medium disappoints |
| Cloud speech API (OpenAI / Google) | per-minute fee | good | new key, data leaves the VPS | skip unless the VPS cannot cope |
Plan: switch to `medium`, test on 5 of your real voice notes (send them to the CoS chat, mix of Hindi and English, with site terms), compare against what you meant, keep the winner. The transcripts then flow into the same WhatsApp-intel path as typed messages (the sweep, the daily plan, the objectives), tagged `[voice transcript]`.
**What I need:** 5 sample voice notes, and who sends voice notes today (you, site heads, Mausaji)?
