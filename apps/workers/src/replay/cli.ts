#!/usr/bin/env tsx
import "dotenv/config";
import { db, agentInputsRaw, agentActions, eq, and, gte, sql } from "@mdo/db";
import { randomUUID } from "crypto";
import { logAction } from "../audit/logger.js";

const args = process.argv.slice(2);
const agentFlag = args.indexOf("--agent");
const hoursFlag = args.indexOf("--hours");

if (agentFlag === -1) {
  console.error("Usage: pnpm replay --agent <name> --hours <n>");
  process.exit(1);
}

const agentId = args[agentFlag + 1];
const hours = hoursFlag !== -1 ? parseInt(args[hoursFlag + 1], 10) : 24;
const since = new Date(Date.now() - hours * 60 * 60 * 1000);

console.log(`Replaying ${agentId} — last ${hours}h (since ${since.toISOString()})`);

const inputs = await db.query.agentInputsRaw.findMany({
  where: and(
    eq(agentInputsRaw.agentId, agentId),
    gte(agentInputsRaw.capturedAt, since)
  ),
  orderBy: (t, { asc }) => [asc(t.capturedAt)],
});

if (inputs.length === 0) {
  console.log("No inputs found for that window.");
  process.exit(0);
}

console.log(`Found ${inputs.length} input(s). Running replay…`);

// Dynamically load the agent
let agentModule: { run: (payload: unknown, ctx: { runId: string; isReplay: boolean }) => Promise<unknown> };
try {
  agentModule = await import(`../../../agents/${agentId}/index.js`);
} catch {
  console.error(`Could not load agent: agents/${agentId}/index.ts`);
  process.exit(1);
}

let matched = 0;
let diffed = 0;

for (const input of inputs) {
  const replayRunId = randomUUID();
  const t0 = Date.now();

  const replayOutput = await agentModule.run(input.payload, {
    runId: replayRunId,
    isReplay: true,
  });

  const durationMs = Date.now() - t0;

  // Fetch original output for the same run
  const origActions = await db.query.agentActions.findMany({
    where: and(
      eq(agentActions.agentId, agentId),
      sql`${agentActions.runId}::text = ${input.runId}`
    ),
  });

  const origOutput = origActions[0]?.output ?? null;
  const replayJson = JSON.stringify(replayOutput);
  const origJson = JSON.stringify(origOutput);

  if (replayJson === origJson) {
    matched++;
  } else {
    diffed++;
    console.log(`\nDIFF for input ${input.id}:`);
    console.log("  original:", origJson?.slice(0, 200));
    console.log("  replay:  ", replayJson?.slice(0, 200));
  }

  await logAction({
    agentId,
    runId: replayRunId,
    action: "replay.run",
    input: { sourceRunId: input.runId, inputId: input.id },
    output: replayOutput as any,
    durationMs,
    isReplay: true,
  });
}

console.log(`\nReplay complete — ${matched} matched, ${diffed} diffed`);
process.exit(0);
