// Minimal shared styling tokens. Dark-first (matches a trading app at a glance).
export const T = {
  bg: "#0d1117",
  card: "#161b22",
  cardAlt: "#1c2330",
  border: "#2a3038",
  text: "#e6edf3",
  textDim: "#8b949e",
  green: "#3fb950",
  red: "#f85149",
  amber: "#d29922",
  blue: "#58a6ff",
  radius: 14,
  pad: 16,
};

// Indian-format currency: ₹ with lakh/crore grouping for large sums.
export function formatINR(n: number, withSymbol = true): string {
  const sym = withSymbol ? "₹" : "";
  if (n === null || n === undefined || isNaN(n)) return `${sym}—`;
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e7) return `${sign}${sym}${(abs / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${sign}${sym}${(abs / 1e5).toFixed(2)} L`;
  // group with Indian thousands separators
  const s = Math.round(abs).toString();
  const last3 = s.slice(-3);
  const rest = s.slice(0, -3);
  const grouped = rest ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + last3 : last3;
  return `${sign}${sym}${grouped}`;
}

export function pct(fraction: number): string {
  if (fraction === null || fraction === undefined || isNaN(fraction)) return "—";
  return `${(fraction * 100).toFixed(1)}%`;
}

export function timeAgo(iso: string): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}
