import {
  pgTable,
  text,
  timestamp,
  boolean,
  integer,
  real,
  jsonb,
  uuid,
  varchar,
  pgEnum,
  index,
  vector,
} from "drizzle-orm/pg-core";

export const agentStatusEnum = pgEnum("agent_status", [
  "active",
  "paused",
  "error",
  "retired",
]);

export const alertSeverityEnum = pgEnum("alert_severity", [
  "critical",
  "high",
  "medium",
  "low",
  "info",
]);

export const alertStatusEnum = pgEnum("alert_status", [
  "pending",
  "delivered",
  "acknowledged",
  "dismissed",
  "failed",
]);

export const approvalStatusEnum = pgEnum("approval_status", [
  "pending",
  "approved",
  "rejected",
  "expired",
]);

// Core agent registry — one row per agent
export const agents = pgTable("agents", {
  id: varchar("id", { length: 64 }).primaryKey(),
  name: text("name").notNull(),
  description: text("description"),
  status: agentStatusEnum("status").notNull().default("active"),
  cronExpression: text("cron_expression"),
  nextRun: timestamp("next_run", { withTimezone: true }),
  lastRun: timestamp("last_run", { withTimezone: true }),
  version: integer("version").notNull().default(1),
  config: jsonb("config").default({}),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Alerts emitted by agents — delivered via WhatsApp/email/dashboard
export const alerts = pgTable(
  "alerts",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agentId: varchar("agent_id", { length: 64 })
      .notNull()
      .references(() => agents.id),
    title: text("title").notNull(),
    body: text("body").notNull(),
    severity: alertSeverityEnum("severity").notNull().default("info"),
    status: alertStatusEnum("status").notNull().default("pending"),
    priorityScore: real("priority_score").notNull().default(0),
    metadata: jsonb("metadata").default({}),
    // populated after embedding pipeline runs
    bodyEmbedding: vector("body_embedding", { dimensions: 1024 }),
    deliveredAt: timestamp("delivered_at", { withTimezone: true }),
    acknowledgedAt: timestamp("acknowledged_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("alerts_agent_id_idx").on(t.agentId), index("alerts_created_at_idx").on(t.createdAt)]
);

// Audit trail — every action taken by the orchestrator or an agent
export const agentActions = pgTable(
  "agent_actions",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agentId: varchar("agent_id", { length: 64 })
      .notNull()
      .references(() => agents.id),
    runId: uuid("run_id"),
    action: text("action").notNull(),
    input: jsonb("input").default({}),
    output: jsonb("output").default({}),
    durationMs: integer("duration_ms"),
    costUsd: real("cost_usd"),
    isReplay: boolean("is_replay").notNull().default(false),
    outputEmbedding: vector("output_embedding", { dimensions: 1024 }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("agent_actions_agent_id_idx").on(t.agentId),
    index("agent_actions_run_id_idx").on(t.runId),
  ]
);

// Every raw input stored before processing — enables replay
export const agentInputsRaw = pgTable(
  "agent_inputs_raw",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agentId: varchar("agent_id", { length: 64 })
      .notNull()
      .references(() => agents.id),
    runId: uuid("run_id").notNull(),
    payload: jsonb("payload").notNull(),
    sourceHash: text("source_hash"),
    capturedAt: timestamp("captured_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("agent_inputs_raw_agent_id_idx").on(t.agentId),
    index("agent_inputs_raw_run_id_idx").on(t.runId),
  ]
);

// Human approval requests — used for high-stakes agent actions
export const approvals = pgTable("approvals", {
  id: uuid("id").primaryKey().defaultRandom(),
  agentId: varchar("agent_id", { length: 64 })
    .notNull()
    .references(() => agents.id),
  actionId: uuid("action_id").references(() => agentActions.id),
  description: text("description").notNull(),
  status: approvalStatusEnum("status").notNull().default("pending"),
  requestedAt: timestamp("requested_at", { withTimezone: true }).notNull().defaultNow(),
  respondedAt: timestamp("responded_at", { withTimezone: true }),
  respondedBy: text("responded_by"),
  expiresAt: timestamp("expires_at", { withTimezone: true }),
});

// Per-agent and global kill switch state
export const killState = pgTable("kill_state", {
  id: varchar("id", { length: 64 }).primaryKey(),
  isPaused: boolean("is_paused").notNull().default(false),
  pausedAt: timestamp("paused_at", { withTimezone: true }),
  pausedBy: text("paused_by"),
  resumedAt: timestamp("resumed_at", { withTimezone: true }),
  resumedBy: text("resumed_by"),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
});

// Generic system events log — infra events, deployments, errors
export const events = pgTable(
  "events",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    type: text("type").notNull(),
    source: text("source").notNull(),
    payload: jsonb("payload").default({}),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("events_type_idx").on(t.type), index("events_created_at_idx").on(t.createdAt)]
);

// Quarantine list — sources flagged as unreliable
export const sourceQuarantine = pgTable("source_quarantine", {
  id: uuid("id").primaryKey().defaultRandom(),
  sourceId: text("source_id").notNull().unique(),
  reason: text("reason").notNull(),
  flaggedAt: timestamp("flagged_at", { withTimezone: true }).notNull().defaultNow(),
  flaggedBy: text("flagged_by"),
  resolvedAt: timestamp("resolved_at", { withTimezone: true }),
});

// Statistical baselines per agent metric — used for anomaly detection
export const baselines = pgTable("baselines", {
  id: uuid("id").primaryKey().defaultRandom(),
  agentId: varchar("agent_id", { length: 64 })
    .notNull()
    .references(() => agents.id),
  metric: text("metric").notNull(),
  mean: real("mean"),
  stddev: real("stddev"),
  p50: real("p50"),
  p95: real("p95"),
  sampleCount: integer("sample_count").notNull().default(0),
  computedAt: timestamp("computed_at", { withTimezone: true }).notNull().defaultNow(),
});

// One record per agent execution run — cost, duration, outcome
export const agentRuns = pgTable(
  "agent_runs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    agentId: varchar("agent_id", { length: 64 })
      .notNull()
      .references(() => agents.id),
    version: integer("version").notNull().default(1),
    status: text("status").notNull().default("running"),
    startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
    completedAt: timestamp("completed_at", { withTimezone: true }),
    durationMs: integer("duration_ms"),
    totalCostUsd: real("total_cost_usd"),
    anthropicTokensIn: integer("anthropic_tokens_in"),
    anthropicTokensOut: integer("anthropic_tokens_out"),
    alertsEmitted: integer("alerts_emitted").notNull().default(0),
    isReplay: boolean("is_replay").notNull().default(false),
    error: text("error"),
  },
  (t) => [index("agent_runs_agent_id_idx").on(t.agentId), index("agent_runs_started_at_idx").on(t.startedAt)]
);

// Canary deployment tracking — run two agent versions in parallel
export const canaryDeployments = pgTable("canary_deployments", {
  id: uuid("id").primaryKey().defaultRandom(),
  agentId: varchar("agent_id", { length: 64 })
    .notNull()
    .references(() => agents.id),
  v1Version: integer("v1_version").notNull(),
  v2Version: integer("v2_version").notNull(),
  trafficSplitPct: integer("traffic_split_pct").notNull().default(10),
  status: text("status").notNull().default("active"),
  startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
  completedAt: timestamp("completed_at", { withTimezone: true }),
  winnerVersion: integer("winner_version"),
  metrics: jsonb("metrics").default({}),
});
