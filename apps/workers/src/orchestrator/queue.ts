import { Queue, Worker, Job } from "bullmq";

export interface AgentJob {
  agentId: string;
  runId: string;
  triggeredBy: "cron" | "manual" | "replay";
  payload?: unknown;
}

function redisConnection(): Record<string, unknown> {
  const url = process.env.REDIS_URL;
  if (!url) throw new Error("REDIS_URL is required");
  // BullMQ accepts a plain connection string via `connection` ioredis options
  return { lazyConnect: true, ...parseRedisUrl(url) };
}

function parseRedisUrl(url: string): Record<string, unknown> {
  const u = new URL(url);
  return {
    host: u.hostname,
    port: u.port ? parseInt(u.port) : 6379,
    password: u.password || undefined,
    username: u.username || undefined,
    tls: u.protocol === "rediss:" ? {} : undefined,
  };
}

export const agentQueue = new Queue<AgentJob>("agent-jobs", {
  connection: redisConnection(),
  defaultJobOptions: {
    attempts: 3,
    backoff: { type: "exponential", delay: 2000 },
    removeOnComplete: { count: 500 },
    removeOnFail: { count: 200 },
  },
});

export async function enqueueAgent(job: AgentJob, priority: number = 5): Promise<void> {
  await agentQueue.add(job.agentId, job, { priority: Math.max(1, 100 - priority) });
}

export function createAgentWorker(
  processor: (job: Job<AgentJob>) => Promise<void>,
  concurrency = 5
): Worker<AgentJob> {
  return new Worker<AgentJob>("agent-jobs", processor, {
    connection: redisConnection(),
    concurrency,
  });
}
