import { db } from "./client.js";
import { sql } from "drizzle-orm";

const tableNames = [
  "agents",
  "alerts",
  "agent_actions",
  "agent_inputs_raw",
  "approvals",
  "kill_state",
  "events",
  "source_quarantine",
  "baselines",
  "agent_runs",
  "canary_deployments",
];

const rows = await db.execute(
  sql`SELECT tablename FROM pg_tables WHERE schemaname = 'public'`
);
const existing = rows.map((r: any) => r.tablename as string);
const missing = tableNames.filter((t) => !existing.includes(t));

const rlsRows = await db.execute(
  sql`SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true`
);
const rlsEnabled = rlsRows.map((r: any) => r.tablename as string);

const vectorRows = await db.execute(
  sql`SELECT extname FROM pg_extension WHERE extname = 'vector'`
);
const pgvectorReady = vectorRows.length > 0;

if (missing.length > 0) {
  console.error(`Missing tables: ${missing.join(", ")}`);
  process.exit(1);
}

console.log(
  `${tableNames.length} tables ✓, RLS enabled on ${rlsEnabled.length} table(s), pgvector ${pgvectorReady ? "ready ✓" : "NOT enabled — run: CREATE EXTENSION vector;"}`
);
process.exit(0);
