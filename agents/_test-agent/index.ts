import { db, alerts, agentRuns } from "@mdo/db";
import { eq } from "drizzle-orm";
import { recordInput } from "../../apps/workers/src/replay/recorder.js";
import { computePriorityScore } from "../../apps/workers/src/orchestrator/priority.js";

export interface RunContext {
  runId: string;
  isReplay: boolean;
}

export interface AgentOutput {
  alertId: string;
  message: string;
  priorityScore: number;
}

export async function run(
  payload: unknown,
  ctx: RunContext
): Promise<AgentOutput> {
  // Record raw input before doing anything — enables replay
  await recordInput("test-agent", ctx.runId, payload);

  const message = "Hello, AMAN — Phase 0 alert";
  const priorityScore = computePriorityScore("info", 0);

  const [alert] = await db
    .insert(alerts)
    .values({
      agentId: "test-agent",
      title: "Phase 0 Hello World",
      body: message,
      severity: "info",
      status: "pending",
      priorityScore,
      metadata: { runId: ctx.runId, isReplay: ctx.isReplay },
    })
    .returning({ id: alerts.id });

  // Update run alert count
  await db
    .update(agentRuns)
    .set({ alertsEmitted: 1 })
    .where(eq(agentRuns.id, ctx.runId as any));

  console.log(`[test-agent] Alert emitted: ${alert.id} (score=${priorityScore})`);

  return { alertId: alert.id, message, priorityScore };
}
