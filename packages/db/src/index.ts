export { db } from "./client.js";
export * from "./schema.js";
// Re-export drizzle operators so consumers share a single drizzle-orm instance
export { eq, and, or, gte, lte, gt, lt, sql, asc, desc, inArray } from "drizzle-orm";
