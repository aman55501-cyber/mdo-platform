# Shares CFO — Deploy on a VPS (always-on, HTTPS)

Runs the read-only dashboard 24/7 with automatic HTTPS. You provide a small Ubuntu
VPS and a free domain; the included `docker-compose.yml` + `Caddyfile` do the rest.

## What you need
- A VPS (Hetzner CX22 ~€4/mo, or DigitalOcean ~$6/mo) running **Ubuntu 24.04**.
- A free domain from **duckdns.org** (e.g. `amancfo.duckdns.org`) pointed at your VPS IP.
- A GitHub **personal access token** (read-only, this repo) to clone the private repo.

## Steps (run on the VPS over SSH)

**1. Create the VPS** in your provider's dashboard (Ubuntu 24.04, smallest size). Note its **public IP**.

**2. Point a free domain at it:** at duckdns.org, create a subdomain and set its IP to your VPS IP.

**3. SSH in** (from Windows PowerShell): `ssh root@<VPS-IP>`

**4. Install Docker:**
```
curl -fsSL https://get.docker.com | sh
```

**5. Get the code** (replace <TOKEN> with your GitHub token):
```
git clone https://<TOKEN>@github.com/aman55501-cyber/mdo-platform.git
cd mdo-platform
git checkout claude/shares-cfo-hdfc-setup-wrlqaj
```

**6. Create the `.env`** (never committed):
```
nano .env
```
Paste and fill in (use a long random CFO_API_TOKEN):
```
DOMAIN=amancfo.duckdns.org
HDFC_BASE_URL=https://developer.hdfcsec.com/oapi/v1
CFO_ACCOUNTS=HDFC1
HDFC_HDFC1_API_KEY=your_key
HDFC_HDFC1_API_SECRET=your_secret
CFO_API_TOKEN=your_long_random_string
```
Save (Ctrl+O, Enter, Ctrl+X).

**7. Start it:**
```
docker compose up -d --build
```
Caddy gets an HTTPS certificate automatically (give it ~30s).

**8. In the HDFC developer portal**, set the Redirect URL to:
```
https://amancfo.duckdns.org/hdfc/callback
```

## Daily use (from your phone, PC off)
- Log in each morning: `https://amancfo.duckdns.org/hdfc/login?key=HDFC1&token=<CFO_API_TOKEN>`
- Dashboard: `https://amancfo.duckdns.org/?token=<CFO_API_TOKEN>`

## Managing it
- Logs: `docker compose logs -f sharescfo`
- Update after a new push: `git pull && docker compose up -d --build`
- Restart: `docker compose restart`

## Security
- Read-only app; no order code exists. Access token stays in server memory.
- HTTPS everywhere (Caddy). Keep `CFO_API_TOKEN` secret and strong.
- Harden later: create a non-root user, enable a firewall (ufw allow 22,80,443), SSH keys.
