import "dotenv/config";
import { startScheduler } from "./scheduler/index.js";
import { createAgentWorker } from "./orchestrator/queue.js";
import { dispatch } from "./orchestrator/dispatcher.js";

console.log("MDO Orchestrator starting…");

// Launch the BullMQ worker that processes enqueued agent jobs
const worker = createAgentWorker(dispatch, 5);

worker.on("completed", (job) => {
  console.log(`[worker] Job ${job.id} (${job.data.agentId}) completed`);
});

worker.on("failed", (job, err) => {
  console.error(`[worker] Job ${job?.id} (${job?.data.agentId}) failed: ${err.message}`);
});

// Seed and then start the cron scheduler
await startScheduler();

console.log("MDO Orchestrator ready.");

// Graceful shutdown
process.on("SIGTERM", async () => {
  console.log("Shutting down…");
  await worker.close();
  process.exit(0);
});
