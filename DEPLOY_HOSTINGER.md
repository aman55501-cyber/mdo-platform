# Deploying MDO on Hostinger — Step by Step

One VPS runs everything: FastAPI backend, Next.js frontend, SQLite on a
persistent Docker volume. This replaces Railway and fixes its three chronic
problems: **data resets** (no volume), **Whisper RAM** (Singhvi extractor),
and **Chromium** (WhatsApp bridge).

---

## 1. Get the VPS (one-time, ~10 min)

1. hostinger.com → **VPS** → pick a **KVM 2** plan (2 vCPU / 8 GB RAM)
   - KVM 1 (4 GB) runs the app fine; KVM 2 gives headroom for Whisper +
     the Chromium WhatsApp bridge — the two things Railway couldn't run.
2. During setup choose OS template: **Ubuntu 24.04 with Docker**
   (Hostinger has it under "OS with Control Panel / Applications").
   If you picked plain Ubuntu, install Docker later with:
   `curl -fsSL https://get.docker.com | sh`
3. Note the **VPS IP address** from the Hostinger dashboard.
4. Hostinger dashboard → your VPS → **Firewall**: allow TCP **22, 3000, 8501**
   (and 80/443 if you'll add a domain later).

## 2. Connect (laptop or phone)

- Laptop: `ssh root@YOUR_VPS_IP` (password is in the Hostinger dashboard)
- Phone / no terminal: Hostinger dashboard → VPS → **Browser terminal** —
  works fully from a phone.

## 3. Clone the repo (private — needs a GitHub token)

1. github.com → Settings → Developer settings → **Fine-grained tokens** →
   generate one scoped to `aman55501-cyber/mdo-platform`, Contents: Read.
2. On the VPS:
   ```bash
   git clone https://YOUR_TOKEN@github.com/aman55501-cyber/mdo-platform.git
   cd mdo-platform
   ```

## 4. Configure

```bash
cp .env.example .env
nano .env
```
Set at minimum:
- `NEXT_PUBLIC_API_URL=http://YOUR_VPS_IP:8501`  ← the browser talks to this
- `GROK_API_KEY=...` (copy the real value from the Railway dashboard env vars)
- `ANTHROPIC_API_KEY=...` — powers the MDO Brain with Claude (Grok is the
  fallback if you skip this; get a key at console.anthropic.com)
- `MDO_MCP_SECRET=...` — any long random string (`openssl rand -hex 16`).
  Enables the MCP server so the Claude app on your phone can talk to MDO.
- `HDFC_API_KEY=...` / `HDFC_API_SECRET=...`
- `HDFC_REDIRECT_URL=http://YOUR_VPS_IP:8501/api/hdfc/callback`
  (register this same URL in the HDFC developer portal — this was roadmap
  step "HDFC OAuth callback", now with a stable address)

## 5. Launch

```bash
docker compose up -d --build
```
First build takes ~3–5 min. Three services come up: backend, frontend, and
the WhatsApp bridge (Baileys — no Chromium). Then:
- **App: `http://YOUR_VPS_IP:3000`** ← bookmark on laptop, "Add to Home
  Screen" on phone
- Life LLM Map: `http://YOUR_VPS_IP:3000/lifemap`
- MDO Brain chat: `http://YOUR_VPS_IP:3000/grok`
- Backend health check: `http://YOUR_VPS_IP:8501/api/status`

### 5a. Connect WhatsApp (one-time QR scan)

Open **VWLR Ops Feed** in the app — a QR code appears. Scan it from
WhatsApp on +91 7000512030 (Linked devices → Link a device). The session
persists in the `wa-auth` volume; messages from the 6 VWLR site groups start
flowing into the Ops Feed and become Brain tools (`get_site_ops_feed`).

### 5b. Connect the Claude app to your business (MCP)

With `MDO_MCP_SECRET` set, your backend exposes an MCP server at:
```
http://YOUR_VPS_IP:8501/mcp/YOUR_SECRET/mcp
```
In the Claude app / claude.ai → Settings → Connectors → **Add custom
connector** → paste that URL. Claude (on your phone, anywhere) can then
query tenders, compliance, hotel numbers, site ops and file tasks — the same
18 tools the in-app Brain uses. Use HTTPS (step 7) before relying on it
daily, and rotate the secret if it ever leaks.

## 6. Updating after code changes

```bash
cd mdo-platform && git pull && docker compose up -d --build
```

## 7a. Custom domain via an EXISTING Caddy on the same VPS

If another compose stack on this VPS already runs Caddy on 80/443 (e.g.
sharecfo), route MDO through it instead of starting a second proxy:

1. **DNS (Hostinger hPanel → Domains → your domain → DNS):**
   - `A` record, name `@`, value = VPS IP
   - `A` record, name `api`, value = VPS IP
2. **Join Caddy to MDO's docker network** so it can reach the containers:
   ```bash
   docker network connect mdo-platform_default sharecfo-caddy-1
   ```
   (Re-run this if the Caddy container is ever recreated — or add the
   `mdo-platform_default` network to the Caddy service in that stack's
   compose file to make it permanent.)
3. **Append site blocks to that stack's Caddyfile** (find its path with
   `grep -B2 -A6 'caddy' /docker/sharecfo/docker-compose.yml` — look for the
   volume mounted at `/etc/caddy/Caddyfile`), e.g.:
   ```
   yourdomain.example {
       reverse_proxy frontend:3000
   }
   api.yourdomain.example {
       reverse_proxy backend:8501
   }
   ```
   `frontend` / `backend` resolve via the shared docker network. Then:
   ```bash
   docker restart sharecfo-caddy-1
   ```
   Caddy fetches HTTPS certificates automatically once DNS resolves.
4. **Rebuild the frontend against the HTTPS API** (browsers block an https
   page calling an http API):
   ```bash
   cd /docker/sharecfo/mdo-platform
   sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://api.yourdomain.example|' .env
   sed -i 's|^HDFC_REDIRECT_URL=.*|HDFC_REDIRECT_URL=https://api.yourdomain.example/api/hdfc/callback|' .env
   docker compose up -d --build frontend
   ```
5. New addresses: app `https://yourdomain.example`, MCP connector
   `https://api.yourdomain.example/mcp/<MDO_MCP_SECRET>/mcp`. You can then
   close ports 3000/8501 in the firewall if you want domain-only access.

## 7b. Domain + HTTPS from scratch (no existing proxy) (~15 min)

1. Point a domain/subdomain A-record at the VPS IP (Hostinger DNS panel):
   `mdo.yourdomain.com` → VPS IP, `api.yourdomain.com` → VPS IP
2. Install Caddy on the VPS (`apt install caddy`) with this `/etc/caddy/Caddyfile`:
   ```
   mdo.yourdomain.com { reverse_proxy localhost:3000 }
   api.yourdomain.com { reverse_proxy localhost:8501 }
   ```
3. `systemctl reload caddy` — automatic HTTPS certificates included.
4. Rebuild frontend with the new API URL:
   set `NEXT_PUBLIC_API_URL=https://api.yourdomain.com` in `.env`, then
   `docker compose up -d --build frontend`. Update `HDFC_REDIRECT_URL` too.

## 8. Autonomous agents (run ON the VPS)

`mdo_agent.py` runs the checks registry on a cadence and files reports into the
app. It lives inside the backend container — same key, same database, same
network as everything else, so there is no cloud-session auth to fail silently.

Test it by hand first:
```bash
cd /docker/sharecfo/mdo-platform
docker compose exec backend python mdo_agent.py daily
```
Expect: `filed report N — {...} — intel items: M`. Findings appear in the app's
Intel Centre immediately.

Then schedule it with host cron (`crontab -e`):
```
24 * * * * cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py hourly >> /var/log/mdo-agent.log 2>&1
27 1 * * * cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py daily  >> /var/log/mdo-agent.log 2>&1
```
(01:27 UTC = 06:57 IST — the brief is waiting when you wake up.)

Behaviour: the hourly run files a report **only** when a finding crosses a
threshold — silence is the healthy state. The daily run always files. Checks
whose `run_window` excludes the current time (e.g. market checks at night) are
skipped; checks marked `blocked` are reported as gaps, never guessed at.

Model: set `MDO_AGENT_MODEL` in `.env` to change it (default `claude-sonnet-5`;
use `claude-opus-5` for deeper strategy work at higher cost).

Watch it: `tail -f /var/log/mdo-agent.log`

## Data safety

- SQLite lives in the Docker volume `mdo-data` — it survives rebuilds,
  restarts, and `git pull` deployments.
- Backup (run occasionally, or cron it):
  ```bash
  docker compose cp backend:/data/vega_data.db ./backup-$(date +%F).db
  ```

## What this unlocks next (from the roadmap)

- **Singhvi extractor live test** — the VPS has the RAM Whisper needs
- **WhatsApp bridge revival** — Chromium fits now; `whatsapp_bridge/` can run
  as another compose service
- **Stable HDFC callback URL** — no more moving-target OAuth registration
