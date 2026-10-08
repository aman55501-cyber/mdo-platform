# Shares CFO — Always-on on Railway

Runs the read-only dashboard 24/7 so your phone works even when your PC is off,
and (later) so scans/auto-refresh run overnight. Separate service from MDO; your
MDO deployment is not touched.

## How login works without a PC

There's no browser on a server, so instead of `hdfc_login.py` you use a **phone
login flow** built into the server:

1. Each morning you open **one link** on your phone:
   `https://<your-app>.up.railway.app/hdfc/login?key=HDFC1&token=<CFO_API_TOKEN>`
2. It sends you to HDFC's login → do your 2FA → approve.
3. HDFC redirects to `…/hdfc/callback`, the server exchanges the token and **arms
   itself** (token held in memory for the day). You see a green "logged in".
4. Open your dashboard: `https://<your-app>.up.railway.app/?token=<CFO_API_TOKEN>`.

Tokens are same-day, so you repeat step 1 once each morning. (If Railway restarts
the service mid-day, just re-open the login link.)

## One-time setup

1. **Set a strong `CFO_API_TOKEN`** — this server is on the public internet, so
   replace `qwerty22` with a long random string.

2. **In Railway** → New Service → Deploy from this repo → set:
   - Build: Dockerfile, path `Dockerfile.sharescfo`
   - Variables:
     ```
     HDFC_HDFC1_API_KEY     = <your key>
     HDFC_HDFC1_API_SECRET  = <your secret>
     HDFC_BASE_URL          = https://developer.hdfcsec.com/oapi/v1
     CFO_API_TOKEN          = <long random string>
     CFO_ACCOUNTS           = HDFC1
     ```
   Railway injects `PORT` automatically; the server binds it.

3. **In the HDFC developer portal**, change your app's **Redirect URL** to:
   `https://<your-app>.up.railway.app/hdfc/callback`
   (This is what lets the server capture the login instead of a Google page.)

4. Deploy. Then bookmark the two links (login + dashboard) on your phone.

## Security notes

- Everything is **read-only** — no order code exists in this package.
- The access token lives only in the server's memory, never in the response.
- `/portfolio`, `/health`, `/hdfc/login` all require `CFO_API_TOKEN`. Keep it secret.
- Railway serves HTTPS, so Android cleartext is no longer a concern.

## Not yet (future)
- Persisting snapshots (Supabase) so history survives restarts.
- Overnight scans + alerts once the analysis layer is wired to EODHD/Screener.
