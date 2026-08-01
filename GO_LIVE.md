# Go live — what Aman needs to do

Everything in this list is something I cannot do from here: it needs your VPS, your
secrets, your phone, or physical access to a site. Ordered so each step unlocks the
next. **Section A blocks everything else.**

Times are rough. Nothing here needs a developer.

---

## A. Deploy the merged stack — 20 min, blocks everything

The branch `claude/sharecfo-life-llm-merge-8www96` has both halves merged. Right now the
VPS is still running them as two stacks. Three things will collide if you just bring the
new one up, so do these in order.

### A1. Merge the two `.env` files into one

The old layout had two: `/docker/sharecfo/.env` (broker keys, `CFO_API_TOKEN`) and
`/docker/sharecfo/mdo-platform/.env` (MDO keys). The merged stack reads **one** file.

```bash
cd /docker/sharecfo/mdo-platform
cp .env .env.backup-$(date +%F)          # keep the old one
git fetch origin claude/sharecfo-life-llm-merge-8www96
git checkout claude/sharecfo-life-llm-merge-8www96
git pull origin claude/sharecfo-life-llm-merge-8www96
```

Now open `.env` and add everything from `/docker/sharecfo/.env` that isn't already
there — the `HDFC_*` keys, `ANGEL_*`, `CFO_ACCOUNTS`, and importantly **`CFO_API_TOKEN`**.

> ⚠️ `CFO_API_TOKEN` must be **one value** now. Shares CFO requires it and the MDO
> backend presents it. If the two old files had different values, pick the one from
> `/docker/sharecfo/.env` — that's the one the broker sessions were authenticated with.

`.env.example` documents every new key with comments. Diff it against yours to see
what's new: `diff <(grep -o '^[A-Z_]*' .env.example | sort -u) <(grep -o '^[A-Z_]*' .env | sort -u)`

### A2. Rescue the Shares CFO data volumes

**This one bites silently.** Docker prefixes volume names with the project directory.
The old stack's volumes are `sharecfo_sharescfo_state` etc.; the merged stack will create
fresh empty ones named `mdo-platform_sharescfo_*`. Your uploaded Screener Premium
exports, MProfit exports and snapshots would look like they vanished.

```bash
docker volume ls | grep sharescfo        # confirm the real old names first
```

For each of `state`, `screener`, `mprofit`:

```bash
docker run --rm \
  -v sharecfo_sharescfo_state:/from \
  -v mdo-platform_sharescfo_state:/to \
  alpine sh -c "cd /from && cp -a . /to"
```

(Substitute the actual old names from `docker volume ls`. Skip this only if you're happy
re-uploading the Screener and MProfit exports.)

### A3. Stop the old stack, start the merged one

Both stacks want ports 80 and 443 (Caddy) — the new one will fail to start otherwise.

```bash
cd /docker/sharecfo && docker compose down     # stops old caddy + sharescfo + autoheal
cd /docker/sharecfo/mdo-platform && docker compose up -d --build
docker compose ps                              # expect 9 services up
```

### A4. Prove it worked

```bash
curl -s localhost:8501/api/health
curl -s "localhost:8501/api/capital/summary" | head -c 300   # should NOT say "not configured"
curl -s localhost:8501/api/feed | head -c 200
```

If `/api/capital/summary` returns portfolio data, the bridge between the two halves is
live and the merge did its job.

---

### A5. The hostname is already decided for you

`srv1641037.hstgr.cloud` is registered at developer.hdfcsec.com as the HDFC redirect
(`https://srv1641037.hstgr.cloud/hdfc/callback`). That registration is the fixed point —
HDFC only ever calls back to the exact URL on file, so the Caddyfile now routes **one
hostname by path** to satisfy it:

| Path | Goes to | Why |
|---|---|---|
| `/api/*` | MDO backend | every MDO route lives under `/api` |
| `/mcp/*` | MDO backend | the Claude connector endpoint |
| `/hdfc/*` | **Shares CFO** | ← the registered OAuth callback must land here |
| `/*` | MDO app | the Decision Feed and every other page |

`.env.example` already carries the right values — `DOMAIN`, `MDO_APP_URL`,
`NEXT_PUBLIC_API_URL` and `HDFC_HDFC1_REDIRECT_URL` are all set to this hostname.
Copy them across when you merge your `.env` in A1.

Shares CFO's own terminal UI stays on `http://<VPS_IP>:8000` (now published) rather than
nested under a path — its pages link to absolute paths like `/portfolio` that would
collide with the MDO app.

> ⚠️ If you ever change the domain, change it at developer.hdfcsec.com **in the same
> sitting**. A stale redirect URL doesn't error — the login page just never completes,
> and the capital side goes quietly blind.

---

## B. Turn on phone push — 15 min, this is the whole point

The feed is built but silent until a channel is configured. **ntfy is the fastest** —
no bot, no account, no approval process.

1. Install the **ntfy** app (iOS/Android).
2. Invent a long random topic name — treat it like a password, anyone who knows it can
   read your alerts: `openssl rand -hex 16`
3. Subscribe to that topic in the app.
4. In `.env`:
   ```
   CFO_NTFY_TOPIC=<the random string>
   MDO_APP_URL=https://srv1641037.hstgr.cloud
   ALERT_WHATSAPP_TO=917000512030                # optional: WhatsApp self-message too
   ```
5. `docker compose up -d backend` then:
   ```bash
   curl -X POST localhost:8501/api/alerts/test
   ```
   Your phone should buzz. If it doesn't, nothing else in the feed will reach you.

6. End-to-end test — publish a fake finding with a drafted action and approve it:
   ```bash
   curl -s -X POST localhost:8501/api/feed/publish -H 'Content-Type: application/json' -d '{
     "key":"test.golive","title":"Test finding","severity":"critical","domain":"vwlr",
     "body":"If you can tap this and it files a task, the whole loop works.",
     "action_type":"add_task",
     "action_payload":{"title":"Delete me — go-live test","priority":"low"}}'
   ```
   Your phone buzzes → tap the link → it opens `/feed/<id>` → tap **Approve & run** →
   the task appears on your Task Board. That's the product working.

> `MDO_APP_URL` is already the hostname HDFC calls back to, so it is public and
> reachable from your phone the moment Caddy has a certificate for it.

---

## C. Site data over the VPNs — needs you at/near the sites

This is the part I built blind and the part that needs you most. The tunnels, the proxy,
the read layer, the health checks and the alerting are all done and tested. What's
missing is knowledge that only exists inside those two buildings.

### C1. Put the two `.ovpn` profiles on the VPS

They are **not in the repo** — `.gitignore` excludes them because they contain private
keys (verified: `git ls-files vpn/` shows only `.gitkeep` files). Copy them from wherever
you keep them:

```bash
scp hotel.ovpn   root@<VPS_IP>:/docker/sharecfo/mdo-platform/vpn/hotel/client.ovpn
scp vedanta.ovpn root@<VPS_IP>:/docker/sharecfo/mdo-platform/vpn/vedanta/client.ovpn
docker compose up -d vpn-hotel vpn-vedanta
docker compose logs vpn-hotel | tail -20     # look for "Initialization Sequence Completed"
```

### C2. Discover what's actually on those networks

Nobody has done this yet — `docs/PLAN_VPN_SITE_ACCESS.md` names it as its Phase 3 and it
hasn't run. I refuse to guess site addresses, which is why `site_sources.json` is empty.

Once a tunnel is up, from the VPS:

```bash
# what subnet did the site push us?
docker compose exec vpn-hotel ip route

# scan it for web-speaking hosts (nmap is already in the image)
docker compose exec vpn-hotel nmap -p 80,443,8080,8000,3000 --open -oG - 10.0.0.0/24
```

**Paste that output to me** and I'll write the source config and any parsing needed.

### C3. Tell me what software runs at each site

The scan gives me addresses; it doesn't tell me what's behind them. Far more useful:

- **Hotel ANS** — what runs the front desk? A PMS (which one)? Is Staah the only
  inventory system, or is there an on-site server? Is there a POS for F&B?
- **VWLR / Vedanta** — what's on the weighbridge? Does it write to a PC with software
  (which), or only print slips? Is there a plant SCADA/DCS with a web page? Anything
  tracking rakes or dispatch?

With names I can write real parsers instead of generic JSON-path extraction — and in
some cases go straight at a database rather than scraping a page.

### C4. Set the tunnel probes

Pick any URL inside each LAN that reliably answers (the gateway's own login page is
usually fine) and set:

```
HOTEL_PROBE_URL=http://10.0.0.1/
VEDANTA_PROBE_URL=http://10.1.0.1/
```

Without these I can only tell you the sidecar is alive, not that the tunnel is actually
carrying traffic — a meaningful difference at 3am.

---

## D. Decisions and facts only you have

Answer whichever you can; each unblocks something specific.

| # | What I need | Why it matters |
|---|---|---|
| D1 | Are the four broker accounts authenticated **today**? | If HDFC tokens are stale the capital half of the feed is empty. Daily browser-2FA via `scripts/hdfc_login.py` |
| D2 | Did the HDFC OAuth callback URL ever get registered to the VPS domain? | It's still an open roadmap task in your own DB. Blocks live execution permanently until done |
| D3 | Is the Staah token sorted? | Named as blocked in `LIFE_LLM_MAP.md` Phase 2 — it's the difference between live hotel occupancy and manual entry |
| D4 | Should the daily digest land at a fixed time (e.g. 06:57 IST with the brief)? | Right now `important` items batch but only push on demand |
| D5 | Who else should see the feed — a COO, Jahnavi, the CA? | Changes auth from one key to per-person tokens. Cheap now, expensive later |
| D6 | Are the cooldowns right? (critical 3h, important 12h, info 24h) | I picked these with no evidence. Live for a week then tell me if it's too chatty or too quiet |
| D7 | Was the Apr-25 "drop Telegram" decision about the whole interface, or just trade confirms? | If just confirms, reviving the built inline-keyboard loop saves you the round trip into the app |

---

## E. What I do once you've done each

| You do | I then build |
|---|---|
| A (deploy) | Nothing needed — it just works |
| B (push channel) | Digest scheduling at your chosen hour (D4) |
| C1 (profiles) | Nothing — tunnels self-connect |
| C2 + C3 (scan + software names) | Real site source config and parsers; hotel occupancy and Vedanta dispatch flowing into the feed with provenance |
| D5 (who else) | Per-person tokens and a shared/private split on feed items |
| D7 (Telegram verdict) | Either leave it, or wire the approve buttons back on |

Plus, whenever you want it and independent of the above: retiring the second push path
(`shares_cfo/proactive.py` still alerts on its own channel), and folding the Shares CFO
terminal UI into the Next.js app so there is genuinely one front door.

---

## The short version

If you only do three things this week:

1. **A3** — bring up the merged stack (and don't skip A2, or your Screener data looks lost).
2. **B** — set `CFO_NTFY_TOPIC` + `MDO_APP_URL`, then run the go-live test in B6.
3. **C1** — drop the two `.ovpn` files in, then send me the `nmap` output from C2.
