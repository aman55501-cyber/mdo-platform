import { db } from "./client.js";
import { agents, killState } from "./schema.js";

console.log("Seeding database…");

await db
  .insert(agents)
  .values({
    id: "test-agent",
    name: "Test Agent",
    description: "Phase 0 hello-world agent — proves end-to-end pipeline",
    status: "active",
    cronExpression: "*/5 * * * *",
    version: 1,
    config: { message: "Hello, AMAN — Phase 0 alert" },
  })
  .onConflictDoNothing();

// Global kill switch — starts unpaused
await db
  .insert(killState)
  .values({ id: "global", isPaused: false })
  .onConflictDoNothing();

// Per-agent kill switch
await db
  .insert(killState)
  .values({ id: "test-agent", isPaused: false })
  .onConflictDoNothing();

console.log("Seed complete.");
process.exit(0);
