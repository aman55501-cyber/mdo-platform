import { db, agentInputsRaw } from "@mdo/db";
import { createHash } from "crypto";

export async function recordInput(
  agentId: string,
  runId: string,
  payload: unknown
): Promise<void> {
  const json = JSON.stringify(payload);
  const sourceHash = createHash("sha256").update(json).digest("hex");

  await db.insert(agentInputsRaw).values({
    agentId,
    runId: runId as any,
    payload: payload as any,
    sourceHash,
  });
}
