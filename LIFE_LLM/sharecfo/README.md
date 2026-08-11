# sharecfo — the Capital Organ

**Role in the Life LLM:** holds live authenticated broker sessions for all four
accounts, and answers questions about money that is actually in the market. It is one
organ among several — not the container of the system.

---

## What it is

A separate stack on the same Hostinger VPS, with its own containers and its own
network (`sharecfo_default`). It maintains logged-in sessions for:

| Holder | Broker | Account |
|---|---|---|
| Aman | HDFC Securities | #4016900 (personal) |
| Sudha | HDFC Securities | — |
| Ashok | HDFC Securities | — |
| Aditi Investments (firm) | AngelOne | #A1504046 |

## How the Life LLM reads it

MDO does **not** build a second broker auth path. It reads sharecfo over the shared
Docker network through a narrow, token-gated contract:

```
mdo_server.py  _cfo_get(path)
   → GET {CFO_API_URL}{path}?token={CFO_API_TOKEN}
   → /portfolio · /exposure · /positions/live
   → surfaced as GET /api/capital/summary
```

Joined once with:

```bash
docker network connect sharecfo_default mdo-platform-backend-1
```

**Contract rules** — these are load-bearing, do not break them:

- **Read-only.** MDO never places an order through sharecfo. Execution, when it
  happens, goes through the HDFC InvestRight path with its own OTP.
- **Staleness is reported, never hidden.** `_stale_hours()` compares `as_of` against
  now; over 24h raises an 🟡 flag saying sharecfo may not be refreshing. A stale number
  presented as live is worse than no number.
- **Degrades to a note, never to a fabricated value.** If the bridge is down,
  `/api/capital/summary` returns `{"connected": false, "error": ...}` and the agent
  reports the outage.
- **The network join must survive.** Adding networks to `mdo-platform-backend-1` (the
  VPN sidecars do this) must not drop `sharecfo_default`. Verify with
  `docker inspect mdo-platform-backend-1` before and after any compose change.

## What it covers, and what it does not

sharecfo sees **the liquid book only** — Pool B. It does not see property, unlisted
equity, plant, receivables, or any liability. Net worth is *not* what sharecfo reports;
that is `holdings_value`. The `networth_rollup` check exists precisely to stop those
two being confused, and stays blocked until Pools C and D are sized.

---

## Runbook — invert the directory hierarchy on the VPS

**The problem.** The deploy tree currently reads `/docker/sharecfo/mdo-platform`. The
capital organ is the parent directory of the entire life system. Every path in
`DEPLOY_HOSTINGER.md`, `mdo_agent.py`'s cron lines and the VPN plan repeats this, so
every human and every future agent reads it as "MDO is a part of sharecfo" — the exact
inverse of the truth.

**The target.**

```
/docker/life-llm/
├── mdo-platform/     # this repo — body, senses, reflexes, memory
└── sharecfo/         # the capital organ
```

**Do this in one sitting, not in pieces.** Roughly 15 minutes, one deploy window.

```bash
# 0. Snapshot first — this is the only step that protects you
docker compose -f /docker/sharecfo/mdo-platform/docker-compose.yml ps
docker run --rm -v mdo-data:/d -v /root:/backup alpine \
  tar czf /backup/mdo-data-$(date +%F).tar.gz -C /d .
cp /docker/sharecfo/mdo-platform/.env /root/mdo-env-$(date +%F).bak

# 1. Stop both stacks (order matters — MDO depends on sharecfo, not the reverse)
cd /docker/sharecfo/mdo-platform && docker compose down
cd /docker/sharecfo               && docker compose down

# 2. Move. Named volumes are not path-bound, so the database moves with nothing to do.
mkdir -p /docker/life-llm
mv /docker/sharecfo/mdo-platform /docker/life-llm/mdo-platform
mv /docker/sharecfo              /docker/life-llm/sharecfo

# 3. Bring sharecfo up FIRST so its network exists before MDO joins it
cd /docker/life-llm/sharecfo && docker compose up -d

# 4. Then MDO
cd /docker/life-llm/mdo-platform && docker compose up -d --build

# 5. Re-join the network — the join is on the container, so a recreated
#    container loses it. This is the step people forget.
docker network connect sharecfo_default mdo-platform-backend-1

# 6. Verify the capital organ answers before you call it done
curl -s -H "X-MDO-Key: $MDO_AUTH_TOKEN" \
  http://localhost:8501/api/capital/summary | head -c 400
#    Expect "connected": true and a recent as_of. If "connected": false,
#    step 5 did not take — check `docker inspect mdo-platform-backend-1`.
```

**Then update the two places that hardcode the old path:**

```bash
crontab -e     # all four mdo_agent.py lines: /docker/sharecfo/... → /docker/life-llm/...
```

and in this repo, `DEPLOY_HOSTINGER.md` and `mdo_agent.py`'s docstring. Leave those
edits until *after* the move succeeds — if you have to roll back, the docs should still
describe reality.

**Rollback:** `mv` the two directories back and re-run steps 3–5. Nothing in the
database is path-dependent, because SQLite lives in the named volume `mdo-data`, not in
the project directory.

**Two things that could bite:**

- If sharecfo's compose file uses `name:` or relies on its directory name for the
  project name, the network could come up as `life-llm_default` instead of
  `sharecfo_default`. Check with `docker network ls` after step 3 and, if the name
  changed, either set `name: sharecfo` in its compose file or update `CFO_API_URL` and
  the connect command to match.
- If either `.env` contains an absolute path to the other stack, grep for
  `/docker/sharecfo` in both before starting.
