import cron from "node-cron";
import { randomUUID } from "crypto";
import { db, agents, eq } from "@mdo/db";
import { enqueueAgent } from "../orchestrator/queue.js";
import { computePriorityScore } from "../orchestrator/priority.js";
import { logAction } from "../audit/logger.js";

// Validate cron expressions and register one cron task per active agent
export async function startScheduler(): Promise<void> {
  const activeAgents = await db.query.agents.findMany({
    where: eq(agents.status, "active"),
  });

  for (const agent of activeAgents) {
    if (!agent.cronExpression) continue;

    const expr = agent.cronExpression;

    if (!cron.validate(expr)) {
      console.error(`[scheduler] Invalid cron for ${agent.id}: "${expr}"`);
      continue;
    }

    cron.schedule(expr, async () => {
      const runId = randomUUID();
      console.log(`[scheduler] Triggering ${agent.id} — run ${runId}`);

      const priority = computePriorityScore("info", 0);

      await enqueueAgent(
        { agentId: agent.id, runId, triggeredBy: "cron" },
        priority
      );

      await db
        .update(agents)
        .set({ lastRun: new Date() })
        .where(eq(agents.id, agent.id));

      await logAction({
        agentId: agent.id,
        runId,
        action: "scheduler.triggered",
        input: { cronExpression: expr },
      });
    });

    console.log(`[scheduler] Registered ${agent.id} with cron "${expr}"`);
  }

  console.log(`[scheduler] Started — ${activeAgents.length} agent(s) scheduled`);
}
