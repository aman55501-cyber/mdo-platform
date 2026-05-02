import { db, killState, eq } from "@mdo/db";
import { logAction } from "../audit/logger.js";

// Returns true if this agent (or globally) is paused
export async function isPaused(agentId: string): Promise<boolean> {
  const [global, agent] = await Promise.all([
    db.query.killState.findFirst({ where: eq(killState.id, "global") }),
    db.query.killState.findFirst({ where: eq(killState.id, agentId) }),
  ]);
  return (global?.isPaused ?? false) || (agent?.isPaused ?? false);
}

export async function pauseAgent(agentId: string, by: string): Promise<void> {
  const now = new Date();
  await db
    .insert(killState)
    .values({ id: agentId, isPaused: true, pausedAt: now, pausedBy: by })
    .onConflictDoUpdate({
      target: killState.id,
      set: { isPaused: true, pausedAt: now, pausedBy: by, updatedAt: now },
    });

  await logAction({
    agentId,
    action: "kill_switch.paused",
    input: { by },
    output: { agentId },
  });
}

export async function resumeAgent(agentId: string, by: string): Promise<void> {
  const now = new Date();
  await db
    .insert(killState)
    .values({ id: agentId, isPaused: false, resumedAt: now, resumedBy: by })
    .onConflictDoUpdate({
      target: killState.id,
      set: { isPaused: false, resumedAt: now, resumedBy: by, updatedAt: now },
    });

  await logAction({
    agentId,
    action: "kill_switch.resumed",
    input: { by },
    output: { agentId },
  });
}

export async function pauseAll(by: string): Promise<void> {
  const now = new Date();
  await db
    .insert(killState)
    .values({ id: "global", isPaused: true, pausedAt: now, pausedBy: by })
    .onConflictDoUpdate({
      target: killState.id,
      set: { isPaused: true, pausedAt: now, pausedBy: by, updatedAt: now },
    });

  await logAction({
    agentId: "system",
    action: "kill_switch.paused_all",
    input: { by },
    output: {},
  });
}

export async function resumeAll(by: string): Promise<void> {
  const now = new Date();
  await db
    .insert(killState)
    .values({ id: "global", isPaused: false, resumedAt: now, resumedBy: by })
    .onConflictDoUpdate({
      target: killState.id,
      set: { isPaused: false, resumedAt: now, resumedBy: by, updatedAt: now },
    });

  await logAction({
    agentId: "system",
    action: "kill_switch.resumed_all",
    input: { by },
    output: {},
  });
}
