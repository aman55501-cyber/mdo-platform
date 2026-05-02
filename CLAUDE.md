# MDO Platform — CLAUDE.md

## Architecture overview

Monorepo managed with pnpm workspaces + Turborepo.

```
mdo-platform/
├── apps/
│   ├── workers/        # TypeScript orchestrator — BullMQ, cron, dispatch
│   └── (web future)    # Next.js dashboard (Phase 1)
├── packages/
│   └── db/             # Drizzle ORM schema + migrations for Supabase
├── agents/
│   └── _test-agent/    # Phase 0 hello-world agent (proves pipeline)
└── mdo-app/            # Existing Next.js frontend (pre-orchestrator)
```

## Key rules

1. **Every agent action is audited.** Call `logAction()` from `apps/workers/src/audit/logger.ts` before returning from any agent execution path.
2. **Kill switch is checked first.** Call `isPaused(agentId)` from `enforcer.ts` before running any agent logic. Never bypass this.
3. **All raw inputs are recorded before processing.** Call `recordInput()` from `replay/recorder.ts` at the top of every agent `run()` function.
4. **Never commit secrets.** All credentials go in `.env` (git-ignored). Use `.env.example` for templates.
5. **Drizzle migrations only.** Never edit tables directly in Supabase Dashboard. Always go through `pnpm db:generate` → `pnpm db:migrate`.

## Environment variables required

| Variable | Where | Description |
|---|---|---|
| `DATABASE_URL` | `apps/workers/.env` | Supabase PostgreSQL connection string |
| `REDIS_URL` | `apps/workers/.env` | Railway Redis connection string |

## Common commands

```bash
# Install all workspace deps
pnpm install

# Start orchestrator workers in dev mode (requires DATABASE_URL + REDIS_URL)
pnpm workers:dev

# Generate a Drizzle migration after schema changes
pnpm db:generate

# Apply pending migrations to Supabase
pnpm db:migrate

# Seed the database (inserts test-agent + kill_state rows)
pnpm db:seed

# Verify all 11 tables exist with RLS + pgvector
pnpm db:check

# Replay an agent's last 24h of inputs
pnpm replay --agent _test-agent --hours 24

# Typecheck the workers package
pnpm --filter @mdo/workers typecheck
```

## Database (Supabase)

- Project ID: `gogtdnlknbmhdvunpeqo`
- Region: `ap-south-1`
- 11 core tables: `agents`, `alerts`, `agent_actions`, `agent_inputs_raw`, `approvals`, `kill_state`, `events`, `source_quarantine`, `baselines`, `agent_runs`, `canary_deployments`
- pgvector extension required (`CREATE EXTENSION vector;` in Supabase SQL editor before first migration)
- Realtime enabled on: `alerts`, `approvals`, `kill_state`

## Adding a new agent

1. Create `agents/<agent-id>/index.ts` with an exported `run(payload, ctx)` function
2. Insert a row in the `agents` table (via seed or migration)
3. Insert a row in `kill_state` with `id = '<agent-id>'`
4. The scheduler picks it up automatically on next workers restart

## Phase 0 delivery

Branch: `claude/orchestrator-skeleton-setup-bsM0V`

Components delivered:
- Drizzle schema (11 tables) in `packages/db/src/schema.ts`
- Scheduler (`apps/workers/src/scheduler/`) — node-cron, reads `agents` table
- BullMQ queue + worker (`apps/workers/src/orchestrator/queue.ts`)
- Priority scoring (`apps/workers/src/orchestrator/priority.ts`)
- Dispatcher (`apps/workers/src/orchestrator/dispatcher.ts`)
- Audit logger (`apps/workers/src/audit/logger.ts`)
- Kill-switch enforcer (`apps/workers/src/kill-switch/enforcer.ts`)
- Replay recorder + CLI (`apps/workers/src/replay/`)
- Test agent (`agents/_test-agent/index.ts`)
