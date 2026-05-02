import { db, agentActions } from "@mdo/db";

export interface ActionLogEntry {
  agentId: string;
  runId?: string;
  action: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  durationMs?: number;
  costUsd?: number;
  isReplay?: boolean;
}

export async function logAction(entry: ActionLogEntry): Promise<string> {
  const [row] = await db
    .insert(agentActions)
    .values({
      agentId: entry.agentId,
      runId: entry.runId ? (entry.runId as any) : undefined,
      action: entry.action,
      input: entry.input ?? {},
      output: entry.output ?? {},
      durationMs: entry.durationMs,
      costUsd: entry.costUsd,
      isReplay: entry.isReplay ?? false,
    })
    .returning({ id: agentActions.id });

  return row.id;
}
