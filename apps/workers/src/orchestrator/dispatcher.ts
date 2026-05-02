import type { Job } from "bullmq";
import type { AgentJob } from "./queue.js";
import { isPaused } from "../kill-switch/enforcer.js";
import { logAction } from "../audit/logger.js";
import { db, agentRuns, eq } from "@mdo/db";

type AgentModule = {
  run: (payload: unknown, ctx: { runId: string; isReplay: boolean }) => Promise<unknown>;
};

const agentModuleCache = new Map<string, AgentModule>();

async function loadAgent(agentId: string): Promise<AgentModule> {
  if (agentModuleCache.has(agentId)) return agentModuleCache.get(agentId)!;
  const mod = (await import(`../../../agents/${agentId}/index.js`)) as AgentModule;
  agentModuleCache.set(agentId, mod);
  return mod;
}

export async function dispatch(job: Job<AgentJob>): Promise<void> {
  const { agentId, runId, triggeredBy, payload } = job.data;

  if (await isPaused(agentId)) {
    console.log(`[dispatcher] ${agentId} is paused — skipping run ${runId}`);
    await logAction({ agentId, runId, action: "dispatch.skipped_paused" });
    return;
  }

  await db.insert(agentRuns).values({ id: runId as any, agentId, status: "running" });

  const t0 = Date.now();

  try {
    const mod = await loadAgent(agentId);
    const output = await mod.run(payload ?? {}, { runId, isReplay: false });
    const durationMs = Date.now() - t0;

    await db
      .update(agentRuns)
      .set({ status: "completed", completedAt: new Date(), durationMs })
      .where(eq(agentRuns.id, runId as any));

    await logAction({
      agentId,
      runId,
      action: "dispatch.completed",
      input: { triggeredBy },
      output: output as Record<string, unknown>,
      durationMs,
    });
  } catch (err) {
    const durationMs = Date.now() - t0;
    const errorMsg = err instanceof Error ? err.message : String(err);

    await db
      .update(agentRuns)
      .set({ status: "failed", completedAt: new Date(), durationMs, error: errorMsg })
      .where(eq(agentRuns.id, runId as any));

    await logAction({
      agentId,
      runId,
      action: "dispatch.failed",
      input: { triggeredBy },
      output: { error: errorMsg },
      durationMs,
    });

    throw err;
  }
}
