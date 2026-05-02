// Priority scoring — higher score = higher urgency in the queue
// Formula: severity weight + freshness bonus + business-hours multiplier

const SEVERITY_WEIGHTS: Record<string, number> = {
  critical: 100,
  high: 70,
  medium: 40,
  low: 15,
  info: 5,
};

const BUSINESS_HOURS_MULTIPLIER = 1.3; // 07:00–22:00 IST

export function computePriorityScore(
  severity: string,
  ageMs: number,
  metadata?: Record<string, unknown>
): number {
  const base = SEVERITY_WEIGHTS[severity] ?? 5;

  // Freshness: decays from 20 → 0 over 24 hours
  const freshness = Math.max(0, 20 - (ageMs / (24 * 60 * 60 * 1000)) * 20);

  // Business hours boost (IST = UTC+5:30)
  const istHour = (new Date().getUTCHours() + 5.5) % 24;
  const businessHours = istHour >= 7 && istHour <= 22;
  const multiplier = businessHours ? BUSINESS_HOURS_MULTIPLIER : 1.0;

  return Math.round((base + freshness) * multiplier);
}
