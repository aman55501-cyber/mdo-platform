// Thin API client for the Shares CFO backend. Read-only — it only ever GETs.
import { CONFIG } from "./config";

async function getJSON<T>(path: string): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const url = `${CONFIG.API_BASE}${path}${sep}token=${encodeURIComponent(CONFIG.CFO_API_TOKEN)}`;
  const res = await fetch(url, {
    headers: { "X-CFO-Token": CONFIG.CFO_API_TOKEN },
  });
  if (!res.ok) {
    throw new Error(`Server returned HTTP ${res.status}. Is the backend running and the IP/token correct?`);
  }
  return (await res.json()) as T;
}

// ---- response shapes (match shares_cfo/server.py) ----
export interface SectorRow { sector: string; value: number; pct: number; }
export interface HoldingRow {
  ticker: string; exchange: string; quantity: number;
  average_price: number; last_price: number; pnl: number;
  sector: string; market_value: number;
  day_change: number; day_change_pct: number;
  isin: string; security_id: string;
}
export interface PositionRow {
  ticker: string; exchange: string; product_type: string;
  quantity: number; average_price: number; last_price: number;
  pnl: number; day_pnl: number;
}
export interface DegradedAccount { creds_key: string; reason: string; }
export interface AccountRow {
  creds_key: string; client_code: string; label: string;
  ok: boolean; status: string; reason: string; fetched_at: string;
  holdings: HoldingRow[]; holdings_value: number;
  positions: PositionRow[];
  funds: { available: number; used_margin: number; total: number; cash: number; ledger_balance: number };
}
export interface Portfolio {
  as_of: string;
  complete: boolean;
  net_worth: number;
  holdings_value: number;
  invested_value: number;
  unrealised_pnl: number;
  unrealised_pnl_pct: number;
  cash: number;
  day_change: number;
  day_change_pct: number;
  positions_pnl: number;
  sector_concentration: SectorRow[];
  unmapped_sectors: string[];
  book_health: {
    accounts: number; fresh: number; degraded: number;
    degraded_accounts: DegradedAccount[];
  };
  accounts: AccountRow[];
}

export const getPortfolio = () => getJSON<Portfolio>("/portfolio");
