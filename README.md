# MDO Platform

One repository, one Docker stack, one `.env` — covering both halves of the system:

- **MDO** — the *operating* surface. Businesses, tenders, compliance, site ops,
  hotel numbers, WhatsApp intake, the Brain, the agents.
- **Shares CFO** — the *capital* surface. Live broker sessions, the consolidated
  book, analysis, and gated execution.

These were built as two separate projects on two separate stacks. They are now
merged: the MDO backend reaches Shares CFO at `http://sharescfo:8000` over the
compose network, so the old cross-stack bridge
(`docker network connect sharecfo_default …`) is gone.

---

## The tree

| Path | What it is |
|---|---|
| `mdo_server.py` | MDO backend — FastAPI, SQLite, the MCP endpoint, every `/api/*` route |
| `mdo_brain.py` | The LLM layer over MDO's data (Claude preferred, Grok as fallback) |
| `mdo_agent.py` | Autonomous checks registry — runs on cron, files reports into the app |
| `mdo-app/` | The MDO app — Next.js front end (also packaged for Electron) |
| `shares_cfo/` | Shares CFO service — brokers, analysis, execution, its own FastAPI app |
| `mobile/` | Shares CFO Android app (React Native, 5 tabs) |
| `vega/` | Legacy single-account trading engine — predates Shares CFO |
| `whatsapp_bridge/` | Baileys WhatsApp bridge (no Chromium); two instances, two phones |
| `vpn/` | Per-site OpenVPN sidecars — reach the hotel and Vedanta networks |
| `skills/` | Codified playbooks (Tier 1–5), loaded as prompts and read as SOPs |
| `handoff/` | Life OS and Business OS, extracted for their own projects |
| `docs/`, `*.md` | Vision, intel, the Life LLM map, deployment, plans |

## The docs that matter

| Document | Read it for |
|---|---|
| `MDO_VISION.md` | The principal, the businesses, the entities, the compliance flags |
| `LIFE_LLM_MAP.md` | The 7-layer architecture and the build roadmap |
| `MDO_INTEL.md` | The intelligence model — what gets watched and why |
| `DEPLOY_HOSTINGER.md` | Standing the whole stack up on the VPS, domains, HTTPS, cron |
| `shares_cfo/README.md` | The capital surface in detail |
| `shares_cfo/AGENT_CHARTER.md` | What an LLM agent may and may not do with the book |

---

## Running it

```bash
cp .env.example .env    # then fill it in — see the comments in that file
docker compose up -d --build
```

Nine services come up:

| Service | Role |
|---|---|
| `backend` | MDO API on `:8501` |
| `frontend` | MDO app on `:3000` |
| `sharescfo` | Shares CFO on `:8000` (internal; reached via Caddy or the backend) |
| `caddy` | TLS + hostname routing on `:80`/`:443` — see `Caddyfile` |
| `whatsapp`, `whatsapp2` | The two WhatsApp bridges |
| `vpn-hotel`, `vpn-vedanta` | Site VPN sidecars, tunnels confined to their containers |
| `autoheal` | Restarts any container that reports unhealthy |

State lives in named volumes (`mdo-data`, `sharescfo_state`, `wa-auth*`, …) and
survives rebuilds and `git pull` deploys.

## One `.env`, shared

Both halves read the same file, so key names are now global. Two consequences
worth knowing:

- `CFO_API_TOKEN` is the single shared secret — Shares CFO requires it, the MDO
  backend presents it. Defined once.
- `HDFC_BASE_URL` belongs to Shares CFO (the API host, `…/oapi/v1`). Legacy
  `vega` appends its own `/api/v1`, so it reads `VEGA_HDFC_BASE_URL` instead.

## Tests

```bash
python -m pytest tests/ -q
```
