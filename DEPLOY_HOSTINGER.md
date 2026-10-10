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
15 10   * * 1-5 $MDO python mdo_agent.py share-master-daily  >> /var/log/mdo-agent.log 2>&1   # 15:45 IST Mon-Fri: Share Master post-close refresh → vault finance/Share_Master.xlsx
15 3    * * 1-5 $MDO python mdo_agent.py share-master-daily  >> /var/log/mdo-agent.log 2>&1   # 08:45 IST Mon-Fri: Share Master pre-open refresh (Mausaji overnight calls)
*/15 3-10 * * 1-5 $MDO python mdo_agent.py wa-sweep mausaji >> /var/log/mdo-agent.log 2>&1   # every 15 min, 08:30–16:15 IST window Mon-Fri: Mausaji chat → share lines at once; option check self-checks market hours
*/30 2-16 * * *   $MDO python mdo_agent.py wa-sweep ops     >> /var/log/mdo-agent.log 2>&1   # every 30 min, 07:30–22:00 IST daily: site groups → bottleneck + silence flags
30 15   * * *   $MDO python mdo_agent.py wa-sweep daily   >> /var/log/mdo-agent.log 2>&1   # 21:00 IST: the day's totals + matched chat list to Aman
30 2    * * *   $MDO python mdo_agent.py compliance-reminder        >> /var/log/mdo-agent.log 2>&1   # 08:00 IST daily: statutory dates due in 7 days → one WhatsApp message (week before, day before, due day); heartbeat even when nothing is due
35 2    * * 1   $MDO python mdo_agent.py compliance-reminder weekly >> /var/log/mdo-agent.log 2>&1   # Mon 08:05 IST: "this week: …" compliance line, sent even when empty
30 1    * * *   $MDO python mdo_agent.py mail-reader         >> /var/log/mdo-agent.log 2>&1   # 07:00 IST: Gmail IMAP intake (statements, contract notes, tender results → vault); one WhatsApp line only when actionable
*/30 2-16 * * * $MDO python mdo_agent.py mail-reader         >> /var/log/mdo-agent.log 2>&1   # every 30 min 07:30–22:00 IST: same intake; heartbeat even when 0 new
0  17   * * *   $MDO python mdo_agent.py mail-reader         >> /var/log/mdo-agent.log 2>&1   # 22:30 IST: the day's last intake
0  13   * * *   $MDO python mdo_agent.py corp-actions        >> /var/log/mdo-agent.log 2>&1   # 18:30 IST daily: NSE announcements + corporate actions for every held/watched ticker → one push, NEW rows only; heartbeat even when 0 new
0  1,13 * * *   $MDO python mdo_agent.py tenders-direct      >> /var/log/mdo-agent.log 2>&1   # 06:30 + 18:30 IST: SECL / SECL e-tenders / Coal India / NTPC / CPP / MSTC listings → pipeline; one message only when NEW matches; heartbeat names every site
30-59/10 1 * * * $MDO python mdo_agent.py voice              >> /var/log/mdo-agent.log 2>&1   # 07:00–07:20 IST: WhatsApp voice notes → faster-whisper (CPU) → message store; heartbeat even at zero
*/10 2-15 * * *  $MDO python mdo_agent.py voice              >> /var/log/mdo-agent.log 2>&1   # every 10 min 07:30–21:20 IST: same
0-30/10 16 * * * $MDO python mdo_agent.py voice              >> /var/log/mdo-agent.log 2>&1   # 21:30–22:00 IST: the day's last transcription runs
30 1-16 * * *   $MDO python mdo_agent.py x-watch             >> /var/log/mdo-agent.log 2>&1   # hourly 07:00-22:00 IST: X/web watch via Grok
30 14   * * *   $MDO python mdo_agent.py hotel-daily         >> /var/log/mdo-agent.log 2>&1   # 20:00 IST: renovation + Guptasons contract tracker
10 */2  * * *   $MDO python mdo_agent.py wa-classifier       >> /var/log/mdo-agent.log 2>&1   # every 2h at :10
20 */6  * * *   $MDO python mdo_agent.py wa-intel            >> /var/log/mdo-agent.log 2>&1   # every 6h at :20
30 1    * * 0   $MDO python mdo_agent.py business-pulse      >> /var/log/mdo-agent.log 2>&1   # Sun 07:00 IST
*/30 *  * * *   $MDO python mdo_agent.py credit-guard        >> /var/log/mdo-agent.log 2>&1   # every 30 min: plan window + API cap → policy for every Claude session; one WhatsApp line per state change; heartbeat "credits fine" even when nothing happens
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

## 8a. External watchdog — the one alarm that fires when the fleet itself is dead

Every bot heartbeats, and the Chief of Staff sends a 💀 line when one stops — but
when the VPS, Docker, cron or the backend is down, nothing on the VPS can say so.
`GET /api/health/public` is the only unauthenticated read in the backend
(`mdo_health.py`; the auth middleware exempts it, Caddy already proxies `/api/*`).
It answers `200 {"ok":true,"last_heartbeat_age_min":N,"bridges":{"wa1":"connected"|"down","wa2":…}}`
only when the newest fleet heartbeat (`cos_runs` — every bot run and every
`deploy_vps.sh --auto` files one, so it is at most ~10 min old on a live VPS) is
younger than 45 minutes AND the database opens; otherwise `503` with the reason.
Nothing else is in the reply: no bot names, no summaries, no tokens. A bridge
showing `down` does not fail the check — pairing is the app's business.

**UptimeRobot (free) — Aman's one-time setup (~3 min):**
1. https://uptimerobot.com → sign up with aman.55501@gmail.com, install the
   UptimeRobot app on the phone (push alerts, free).
2. **Add New Monitor**: type **HTTP(s) – Keyword**, friendly name `MDO fleet`,
   URL `https://amanagrawal.cloud/api/health/public`, keyword `"ok":true`
   (with the quotes), alert when keyword **does not exist**, monitoring
   interval **5 minutes**, timeout 30 s.
3. **Alert contacts**: the e-mail (aman.55501@gmail.com) and the mobile app
   push (Aman's phone, logged into the app). Both on.
4. Save. The first check runs within 5 min; "Up" means the fleet heartbeat is
   fresh. Test it once: `docker compose stop backend` on the VPS → the alert
   should arrive within 10 min → `docker compose start backend`.

The CoS does not get this alert — that is the point: it reaches Aman's phone
through a service that does not live on the VPS.

## 8b. Calendar on your phone — the MDO feed, no OAuth

`GET /api/calendar.ics?token=<CALENDAR_TOKEN>` (`mdo_calendar.py`) is an
iCalendar feed computed on request — no bot, no table: every compliance due
date in the next 365 days (`<item> — <entity or group>`, alarms 7 days and 1
day before), every option/future expiry in Share Master positions, the NIFTY
option alert as a note on its expiry, and the Las Vegas trip (10–12 Nov 2026,
dates only, from `briefs/TRIP_LAS_VEGAS_2026-11.md`). The token is its own
door: `CALENDAR_TOKEN` in `.env`, separate from the app key, generated by
`bash deploy_vps.sh` when empty and printed on its summary line
`calendar feed  : https://<domain>/api/calendar.ics?token=…`. Empty token =
the feed answers 403 to everyone.

**Google Calendar (phone or web), one-time:** on calendar.google.com (web —
subscribing is not offered in the phone app) → left column **Other calendars**
→ **+** → **From URL** → paste the feed URL from the deploy summary → **Add
calendar**. It then appears on the phone's Google Calendar under that account;
Google refreshes a URL feed every 12–24 h. iPhone Calendar: Settings → Calendar
→ Accounts → Add Account → Other → **Add Subscribed Calendar** → same URL.
To rotate the token: blank `CALENDAR_TOKEN=` in `.env`, re-run
`bash deploy_vps.sh`, re-subscribe with the new URL.

## 8c. Voice notes and the direct tender feed — what the deploy must do once

Both bots are rule-based and cost nothing per run; both need `bash deploy_vps.sh`
once (it renders the four new cron lines above, rebuilds the backend image and
restarts the bridge containers):

- **voice** (`mdo_voice.py`, bot `voice`, every 10 min 07:00–22:00 IST). The
  bridges (`whatsapp_bridge` v2.2) forward audio / voice messages as multipart
  `POST /api/wa/media` with the same `X-MDO-Key`; the backend keeps the clip in
  the data volume at `/data/voice/<date>/<message_id>.ogg` and the bot
  transcribes it with faster-whisper (CPU, int8) — `faster-whisper` is already
  in `requirements_server.txt` and `ffmpeg` already in the Dockerfile apt line
  (both were there for the Singhvi capture), so the image does not grow. The
  model (`VOICE_MODEL=small`, ~460 MB) is downloaded ONCE on the first run into
  `/data/whisper-models` (the `mdo-data` volume) — the first heartbeat of the
  day it happens may take a few minutes. A slow VPS: set `VOICE_MODEL=base`.
  Check: `docker compose exec backend python mdo_agent.py voice` → `heartbeat
  filed: clean — voice: 0 transcribed, 0 pending, …`; the bridge log shows
  `voice note 12s (… KB) → /api/wa/media` when one arrives.
- **tenders-direct** (`mdo_tenders_direct.py`, bot `tenders-direct`, 06:30 and
  18:30 IST). Public pages only, no login: the heartbeat names every site, so a
  portal that blocks the VPS shows as `eprocure: blocked (HTTP 403 …)` and one
  whose layout changed as `0 rows (layout?): secl`. Keywords and the value
  floor live in `.env` (`TENDERS_KEYWORDS`, `TENDERS_MIN_VALUE_CR`); a site can
  be switched off with `TENDERS_SITES_OFF=mstc`. Check: `docker compose exec
  backend python mdo_agent.py tenders-direct`.

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

## Share Master — loading the family holdings (one-time, and after every new export)

The holdings files are never in the repo or the image. Aman uploads an HDFC portfolio CSV or an
Angel One "DP Transaction Cum Holding" PDF through the Share Master card, or the CoS transcribes
them into `pf/*.json` on the VPS host (`/docker/sharecfo/mdo-platform/pf/`, mode 600, root only).

```bash
# HDFC CSV (holder = whose account), Angel One DP statement PDF (broker=angel is implied by .pdf)
curl -sS -H "X-MDO-Key: $MDO_AUTH_TOKEN" -F holder=Aditi -F file=@Aditi_portfolio.csv http://127.0.0.1:8501/api/share-master/portfolio/import
curl -sS -H "X-MDO-Key: $MDO_AUTH_TOKEN" -F "holder=Aditi Investments" -F broker=angel -F file=@DP_statement.pdf http://127.0.0.1:8501/api/share-master/portfolio/import

# pf/*.json (HDFC-derived, Angel-derived, positions_*.json) piped from the host into the container, then one refresh:
cd /docker/sharecfo/mdo-platform && for f in pf/*.json; do docker compose exec -T -e DOC="$(cat "$f")" -e DOC_NAME="$f" backend python tools/import_share_master.py --stdin; done; docker compose exec -T backend python tools/import_share_master.py --refresh
```

Each file prints one line with the HTTP status; `--refresh` prices the whole book once and saves
`finance/Share_Master.xlsx` to the vault. Tickers resolve from the NSE list (`EQUITY_L.csv`, cached 7
days in the data volume; ISIN column for Angel rows, company name for HDFC codes) — anything the
list does not know is stored as given and flagged "unverified ticker", never guessed. The image
has `poppler-utils` (pdftotext) and `pypdf` for the PDF.
