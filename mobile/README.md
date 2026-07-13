# Shares CFO — Android app (Phase 2)

A 5-tab app. **Dashboard is live** (reads your `/portfolio`); the other four tabs are
honest placeholders that light up as their backends are built. Built with only core
React Native + Expo — **no navigation library**, so no dependency hell on first run.

```
mobile/
  App.tsx                 # 5-tab shell
  src/config.ts           # <-- EDIT: your PC's LAN IP + CFO_API_TOKEN
  src/api.ts              # read-only API client
  src/theme.ts            # styling + ₹ lakh/crore formatting
  src/components.tsx      # Card / Placeholder
  src/screens/            # Dashboard (live) + 4 placeholders
```

## Run it on your phone — step by step

Do this on your PC, with the backend server already running (`python -m shares_cfo.server`).

**1. Create a fresh Expo app** (gets the *current* SDK — we avoid stale pins on purpose):
```
npx create-expo-app@latest sharescfo --template blank-typescript
```

**2. Copy this app in.** Replace the generated `App.tsx` with `mobile/App.tsx`, and copy
the whole `mobile/src/` folder into `sharescfo/src/`. No extra `npx expo install` is
needed — this app uses only what the template already ships.

**3. Set your two values** in `sharescfo/src/config.ts`:
- `API_BASE` → your PC's LAN IP + `:8000`. Find it on your PC with `ipconfig` (use the
  IPv4 address, e.g. `http://192.168.1.23:8000`). **Not `localhost`** — the phone can't
  reach the PC's localhost.
- `CFO_API_TOKEN` → the exact same value as in your backend `.env`.

**4. Three things that otherwise waste an hour:**
- **Bind the server to all interfaces:** `python -m shares_cfo.server` already binds
  `0.0.0.0` — good. (Plain `uvicorn ... --host 0.0.0.0` if you run it manually.)
- **Windows Firewall:** allow inbound port `8000` on **Private** networks, or Windows
  silently blocks your phone.
- **Android blocks plain HTTP.** Easiest for LAN testing: in `sharescfo/app.json`, add
  under `"android"`:
  ```json
  "android": { "usesCleartextTraffic": true }
  ```
  (Or use Tailscale on both devices and point `API_BASE` at the `100.x.y.z` address.)

**5. Start it:**
```
cd sharescfo
npx expo start
```
Install **Expo Go** from the Play Store, scan the QR code. The app opens on your phone.

## What you should see
- **Dashboard:** your net worth, holdings, cash, sector-concentration bars, and a
  book-health strip. If the backend isn't reachable, it says so plainly (with what to
  check) instead of showing zeros.
- **Other tabs:** a short description of what's coming — no fake data.

> If Stage A isn't verified yet (probe not run), Dashboard will show the book as
> **degraded** with the reason — that's correct behaviour, not a bug.

## Not yet
- Live prices/analysis (needs EODHD), push notifications (needs the Alerts backend),
  and offline history (needs the Supabase sync layer). All planned; see the roadmap.
