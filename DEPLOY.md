# MDO Platform — Deployment Runbook

## Prerequisites

- Node 20+
- pnpm (`npm install -g pnpm`)
- Supabase project `gogtdnlknbmhdvunpeqo` already provisioned (ap-south-1)
- Redis service on Railway (see step below)

---

## 1. Local setup

```bash
git clone <repo-url> mdo-platform
cd mdo-platform
pnpm install
```

Create `apps/workers/.env`:

```
DATABASE_URL=<supabase-connection-string>
REDIS_URL=<railway-redis-url>
```

---

## 2. Get DATABASE_URL

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard) → project `gogtdnlknbmhdvunpeqo`
2. Settings → Database → Connection string
3. Use **Transaction mode (port 6543)** for connection pooling (recommended for serverless/workers), or direct on port 5432 for long-lived processes
4. Copy the URI — it looks like `postgresql://postgres.[ref]:[password]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres`
5. Paste as `DATABASE_URL` in `apps/workers/.env`

---

## 3. Get REDIS_URL

1. Go to [railway.app](https://railway.app) → New Project → Add a service → Redis
2. Once provisioned, open the Redis service → Variables tab
3. Copy `REDIS_URL` (format: `redis://default:<password>@<host>:<port>`)
4. Paste as `REDIS_URL` in `apps/workers/.env`

---

## 4. Database setup (first deploy only)

```bash
# Apply all pending Drizzle migrations to Supabase
pnpm db:migrate

# Seed agents + kill_state rows
pnpm db:seed

# Confirm all 11 tables exist with RLS + pgvector
pnpm db:check
```

> If pgvector is missing, run `CREATE EXTENSION vector;` in the Supabase SQL editor before migrating.

---

## 5. Run locally

```bash
# Start orchestrator (scheduler + BullMQ worker)
pnpm workers:dev

# In a second terminal — replay last 24h of inputs for the test agent
pnpm replay --agent _test-agent --hours 24
```

---

## 6. Deploy to Railway

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select this repo; set **Root Directory** to `/`
3. Under **Settings → Build**:
   - Build command: `pnpm install && pnpm --filter @mdo/workers build`
   - Start command: `node apps/workers/dist/index.js`
4. Under **Variables**, add:
   - `DATABASE_URL` — same value as local
   - `REDIS_URL` — same value as local
5. Deploy. Railway streams build logs; watch for `Workers started` in the deploy log.

---

## 7. Verification

```bash
# From local machine after deploy
pnpm db:check          # All 11 tables present
```

Then in the Supabase dashboard:

1. Open project `gogtdnlknbmhdvunpeqo` → Table Editor → `agent_runs`
2. Wait ~5 minutes — the scheduler fires the `_test-agent` on its cron interval
3. Confirm new rows appear with `status = 'completed'`

If rows are missing after 10 minutes, check Railway deploy logs for connection errors against `DATABASE_URL` or `REDIS_URL`.
