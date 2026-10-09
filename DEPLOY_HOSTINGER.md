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

Nothing to do: once §8's one-time command has run, the VPS pulls the working
branch itself every 10 minutes (`deploy_vps.sh --auto`). To force it by hand:

```bash
cd /docker/sharecfo/mdo-platform && sudo bash deploy_vps.sh
```

## 7a. Custom domains via the stack's own Caddy

Since the MDO and Shares CFO stacks were merged, **Caddy ships inside this
compose file** — there is no second proxy to join, and no
`docker network connect` step. Three hostnames route to three services
(see `Caddyfile`); set the ones you want in `.env` and Caddy fetches the
certificates itself.

1. **DNS (Hostinger hPanel → Domains → your domain → DNS)** — one `A` record
   per hostname you plan to use, each pointing at the VPS IP:
   - `cfo` → VPS IP (Shares CFO — the capital surface)
   - `mdo` → VPS IP (MDO app — the operating surface)
   - `api` → VPS IP (MDO backend API)
2. **Name them in `.env`:**
   ```
   DOMAIN=cfo.yourdomain.example
   MDO_DOMAIN=mdo.yourdomain.example
   MDO_API_DOMAIN=api.yourdomain.example
   ```
   `MDO_DOMAIN` / `MDO_API_DOMAIN` are optional — left blank they fall back to
   internal `.localhost` names and no certificate is requested, so you can add
   the MDO hostnames later without touching the Shares CFO one.
3. **Point the frontend at the HTTPS API** (browsers block an https page
   calling an http API) and reload:
   ```bash
   sed -i 's|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://api.yourdomain.example|' .env
   sed -i 's|^HDFC_REDIRECT_URL=.*|HDFC_REDIRECT_URL=https://api.yourdomain.example/api/hdfc/callback|' .env
   docker compose up -d --build frontend caddy
   ```
   Caddy issues the certificates automatically once DNS resolves.
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

## 8. The fleet (runs ON the VPS) — Chief of Staff edition

Every bot in `fleet.yaml` runs through `mdo_agent.py <bot-id>` inside the
backend container: same key, same database, same network. Every run files a
heartbeat even when clean, so a bot that stops is visible on the app's
**Fleet & Memory** page within one slot and the Chief of Staff sends a 💀 line.

**One SSH session, one command** (idempotent — safe to re-run any time):
```bash
cd /docker/sharecfo/mdo-platform && git fetch origin claude/chief-of-staff-bot-4i2jyz && git checkout claude/chief-of-staff-bot-4i2jyz && sudo bash deploy_vps.sh
```
It checks out the branch, fills any missing Chief of Staff variables in `.env`
from `.env.example` (never overwriting a value), runs the unit tests in a
throwaway container, rebuilds `backend` + the WhatsApp bridges, installs the
fleet crontab below as `/etc/cron.d/mdo-fleet`, removes the old per-user
`mdo_agent` cron lines, fires a test alert to WhatsApp, and prints a summary
with the three things only Aman can do. Run it from the repo; never pipe a
download into bash.

`--auto` is the self-update: cron runs `deploy_vps.sh --auto` every 10 minutes
and it deploys only when `origin/<branch>` is ahead of HEAD (tests first, no
cron rewrite), logging to `/var/log/mdo-deploy.log`. Every auto run — even
"up to date" — files a `deploy` heartbeat to `/api/agent/report`, so a silent
VPS shows up as a dead bot on the **Fleet & Memory** page.

To exercise a bot by hand:
```bash
cd /docker/sharecfo/mdo-platform
docker compose exec backend python mdo_agent.py daily-brief
docker compose exec backend python mdo_housekeeping.py --dry-run
docker compose exec backend python mdo_housekeeping.py --daily --dry-run
```
Expect `heartbeat filed: …` or `filed report N — {...}`.

The fleet crontab. **This block is the source `deploy_vps.sh` copies** into
`/etc/cron.d/mdo-fleet` (it expands `$MDO`, adds the `root` user field, and
appends its own `--auto` line). Edit it here, then re-run the script. Times are
UTC on the host; IST in the comments. Each line = one bot: when it wakes,
what it runs, where it logs.
```
# MDO fleet — one line per bot (fleet.yaml). Log: /var/log/mdo-agent.log
MDO=cd /docker/sharecfo/mdo-platform && docker compose exec -T backend
24 *    * * *   $MDO python mdo_agent.py ops-hourly          >> /var/log/mdo-agent.log 2>&1   # every hour
27 1    * * *   $MDO python mdo_agent.py daily-brief         >> /var/log/mdo-agent.log 2>&1   # 06:57 IST
0  2    * * *   $MDO python mdo_agent.py compliance-sentinel >> /var/log/mdo-agent.log 2>&1   # 07:30 IST
30 2    * * *   $MDO python mdo_agent.py tender-go-no-go     >> /var/log/mdo-agent.log 2>&1   # 08:00 IST
35 3-10 * * 1-5 $MDO python mdo_agent.py capital-watcher     >> /var/log/mdo-agent.log 2>&1   # 09:05-15:35 IST Mon-Fri
*/15 3-10 * * 1-5 $MDO python mdo_agent.py levels-alert >> /var/log/mdo-agent.log 2>&1   # every 15 min, 08:30–15:45 IST window; bot self-checks market hours
35 2    * * 1-5 $MDO python mdo_agent.py singhvi             >> /var/log/mdo-agent.log 2>&1   # 08:05 IST Mon-Fri: Singhvi calls → Morning Setup proposals
30 1-16 * * *   $MDO python mdo_agent.py x-watch             >> /var/log/mdo-agent.log 2>&1   # hourly 07:00-22:00 IST: X/web watch via Grok
30 14   * * *   $MDO python mdo_agent.py hotel-daily         >> /var/log/mdo-agent.log 2>&1   # 20:00 IST: renovation + Guptasons contract tracker
10 */2  * * *   $MDO python mdo_agent.py wa-classifier       >> /var/log/mdo-agent.log 2>&1   # every 2h at :10
20 */6  * * *   $MDO python mdo_agent.py wa-intel            >> /var/log/mdo-agent.log 2>&1   # every 6h at :20
30 1    * * 0   $MDO python mdo_agent.py business-pulse      >> /var/log/mdo-agent.log 2>&1   # Sun 07:00 IST
30 21   * * *   $MDO python mdo_housekeeping.py --daily      >> /var/log/mdo-agent.log 2>&1   # 03:00 IST daily: DB snapshots (§10)
30 21   * * 6   $MDO python mdo_housekeeping.py              >> /var/log/mdo-agent.log 2>&1   # Sun 03:00 IST: purge + weekly bundle
0  22   * * 6   savelog -n -c 8 /var/log/mdo-agent.log                                        # keep 8 weeks of log
```
(`$MDO` is shorthand for this document only; the script writes every line
with the full `cd … && docker compose exec -T backend` spelled out, so the
installed file has no cron variables.)

Budget: `SPEND_CAP_INR_MONTH` in `.env`. At 90% the bots drop to Haiku; at
100% they file "paused: budget" and stop. Both are reported, never silent.
Model per bot: `fleet.yaml` (`model:`), not `.env`.

Two-way WhatsApp (the Chief of Staff answers in the chat you write in):
- `COS_CHANNEL=alert` (today): self-message via the ops bridge. Type in your
  own "message yourself" chat; replies start with `CoS ·`.
- `COS_CHANNEL=baileys`: a dedicated number on its own bridge container
  (copy the `whatsapp` service in docker-compose.yml, name it `whatsapp-cos`,
  own volume, scan its QR once). Set `COS_WA_BRIDGE_URL`, `COS_WHATSAPP_TO`.
- `COS_CHANNEL=meta`: Meta WhatsApp Cloud API. Set `META_*` in `.env`, point
  the webhook at `https://api.<domain>/api/cos/meta-webhook` with
  `META_VERIFY_TOKEN`.
Either way `COS_ALLOWED_NUMBERS` lists who may talk to it.

Watch it: `tail -f /var/log/mdo-agent.log` · app: **Fleet & Memory** page.

## 9. The vault — Aman's private files, off the laptop

`/data/vault/{memory,finance}` inside the `mdo-data` Docker volume. Never in the
repo, never in a public path. Reached only through `/api/vault/list|get|put`
with `X-Vault-Token` (`VAULT_TOKEN` in `.env`, separate from the app key), over
the HTTPS domain. No delete over HTTP. Every access lands in `vault_audit`.
Writes are atomic and keep a `.prev` copy. Every Sunday housekeeping folds the
vault into the weekly AES-256 bundle (`/data/backups/weekly-YYYYMMDD.tar.enc`,
passphrase `VAULT_BACKUP_PASSPHRASE`) together with the database snapshots —
see §10. (Bundles made before 2026-10-09 are the older
`archive/vault-YYYY-MM-DD.tar.gz.enc` files; they are left in place.)

One-time import from the laptop (PowerShell, then SSH):
```
scp -r "C:\Users\Owner\Desktop\BUSINESSES\_memory"  root@<VPS>:/docker/sharecfo/mdo-platform/vault-import/memory
scp -r "C:\Users\Owner\claude master\finance"        root@<VPS>:/docker/sharecfo/mdo-platform/vault-import/finance
ssh root@<VPS> "cd /docker/sharecfo/mdo-platform && sudo bash vault_import.sh"
```
The two Sunday Routines (memory sync, finance update) read and write through
the vault API from then on, laptop off. After their first clean run, rename the
laptop folders `*.OLD`: memory points at one place, never two.

## 10. Records & backups — the VPS as system of record

Everything the business remembers lives in one Docker volume, `mdo-data`,
mounted at `/data` in the backend container. It survives rebuilds, restarts
and every `git pull`. What it holds, and who keeps it tidy:

| Path (in `mdo-data`) | What | Written by |
|---|---|---|
| `/data/vega_data.db` | the MDO database: ledger, tasks, intel, reports, chats, vault audit | backend |
| `/data/vedanta_crm.db` | Vedanta CRM (when present) | backend |
| `/data/vault/{memory,finance}` | Aman's private files (§9) | Routines via `/api/vault/*` |
| `/data/archive/*.jsonl.gz` | rows housekeeping trimmed from the database, by month | housekeeping (weekly) |
| `/data/backups/<name>-YYYYMMDD.db.gz` | daily SQLite snapshots, integrity-checked | housekeeping `--daily` |
| `/data/backups/weekly-YYYYMMDD.tar.enc` | **the off-site file**: vault + latest snapshots, AES-256 | housekeeping (weekly) |

The daily snapshot uses the SQLite online-backup API (consistent while the
backend writes), runs `PRAGMA integrity_check` on the copy, and only then
prunes older snapshots. The weekly bundle is `openssl enc -aes-256-cbc -pbkdf2`
with `VAULT_BACKUP_PASSPHRASE` from `.env`; **without the passphrase there is
no bundle** and housekeeping says so in its heartbeat every Sunday. Keep a copy
of the passphrase off the VPS.

### Retention

| Record | Kept | Where |
|---|---|---|
| daily DB snapshots | 14 | `/data/backups/` |
| weekly bundle (vault + DB) | 8 locally **+ every week in Google Drive › "MDO Backups"** | `/data/backups/` + Drive (bot `backup-offsite`) |
| `agent_reports` | 60 days, then `archive/reports-YYYY-MM.jsonl.gz` | database → archive |
| `whatsapp_messages` (unflagged) | 90 days, then `archive/whatsapp-YYYY-MM.jsonl.gz` | database → archive |
| Docker logs | 30 MB per service (json-file, 10 MB × 3) | host, `docker compose logs` |
| `/var/log/mdo-agent.log` | 8 weeks (`savelog`, §8) | host |
| `vault_audit` rows | never trimmed | database |

Never trimmed: the Objectives sheet, `agenda.yaml`, `COS_LOG.md`, open intel,
open tasks, open jobs, the checks registry, `bot_memory`, the last 20 turns of
any chat (Directive 12).

### Off-site door

`GET /api/vault/backup/list` → `[{name, bytes, created}]` and
`GET /api/vault/backup/latest` → the newest `weekly-*.tar.enc` as a download
(404 with a plain reason when there is none). Same `X-Vault-Token` as §9, every
call lands in `vault_audit`. Only `.enc` files are ever served from here — never
a raw `.db`, a snapshot or a vault file. The `backup-offsite` bot
(`fleet.yaml`, a Claude Routine, Sun 08:00 IST) fetches it and drops it in the
Drive folder **MDO Backups**; it never decrypts. Fetch it by hand:
```bash
curl -fsS -H "X-Vault-Token: $VAULT_TOKEN" -o latest.tar.enc https://api.<domain>/api/vault/backup/latest
```

### Restore in 5 commands

On any machine with `openssl`, `tar` and `sqlite3` (`apt install sqlite3`),
with the bundle in the current directory (from `/data/backups/` on the VPS, or
the Drive copy):
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:VAULT_BACKUP_PASSPHRASE -in weekly-20261011.tar.enc -out weekly.tar   # 1. decrypt
tar -xf weekly.tar                                                              # 2. unpack → db/*.db.gz + vault/{memory,finance}
gunzip -c db/vega-20261011.db.gz > vega_data.db                                 # 3. the database (repeat for vedanta-*.db.gz)
sqlite3 vega_data.db "PRAGMA integrity_check;"                                  # 4. must print: ok
docker compose stop backend && docker compose cp vega_data.db backend:/data/vega_data.db && docker compose cp vault backend:/data/vault && docker compose start backend   # 5. put it back
```
Step 5 runs on the VPS in the repo directory; copy `vega_data.db` and `vault/`
there first (`scp`). A fresh VPS needs §3–§5 first, then step 5.

### Logs, ports and the host

- **Docker logs** are capped in `docker-compose.yml` (`x-logging`, applied to
  every service); nothing can fill the disk from a chatty container.
- **Shares CFO on port 8000 is bound to `127.0.0.1` only.** Caddy proxies
  `/hdfc/*` (the HDFC OAuth callback) to it over the compose network, so the
  broker flow is unchanged. The terminal UI is reached through an SSH tunnel:
  ```bash
  ssh -L 8000:127.0.0.1:8000 root@<VPS>     # then open http://localhost:8000
  ```
- **`vps_harden.sh`** (run once as root, safe to re-run): ufw 22/80/443 (asks
  before enabling), fail2ban sshd jail, security-only unattended-upgrades
  with no auto-reboot, journald capped at 500 MB, prunes dangling Docker
  images older than 7 days, prints a one-screen summary. It never edits
  `sshd_config` or disables password auth. Note: Docker-published ports
  bypass ufw, so the Hostinger panel firewall (§1) remains the place to
  close 3000/8501 once the domain is live.
- **Disk**: housekeeping files 🔴 at <15% free (daily) / <20% (weekly).

## What this unlocks next (from the roadmap)

- **Singhvi extractor live test** — the VPS has the RAM Whisper needs
- **WhatsApp bridge revival** — Chromium fits now; `whatsapp_bridge/` can run
  as another compose service
- **Stable HDFC callback URL** — no more moving-target OAuth registration
