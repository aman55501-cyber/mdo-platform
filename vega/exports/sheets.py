"""Google Sheets exporter — pushes VEGA portfolio data to MDO Live Sheet.

Target workbook: "AMAN — MDO LIVE"
Target tabs:
  - 5_Portfolio_Snapshot  → current positions + funds summary
  - 6_FO_Positions        → open F&O positions (NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY)
  - 4_Investments         → Aditi Investments closing balance + XIRR (daily append)

Setup:
  1. Create a Google Cloud service account with Sheets + Drive scope
  2. Share "AMAN — MDO LIVE" sheet with the service account email
  3. Set env vars:
       GOOGLE_SHEETS_CREDENTIALS_JSON = /path/to/service_account.json
       MDO_SHEET_ID = <the long ID from the Sheets URL>

Dependencies (optional — install when ready):
  pip install gspread google-auth

The module degrades gracefully if deps or credentials are missing.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from ..utils.logging import get_logger
from ..utils.time import now_ist

log = get_logger("sheets_exporter")

# Tab names — must match exactly what you create in MDO Live Sheet
TAB_PORTFOLIO_SNAPSHOT = "5_Portfolio_Snapshot"
TAB_FO_POSITIONS = "6_FO_Positions"
TAB_INVESTMENTS = "4_Investments"


class SheetsExporter:
    """Pushes VEGA data to the MDO Google Sheet."""

    def __init__(self) -> None:
        self._gc = None
        self._sheet = None
        self._sheet_id = os.getenv("MDO_SHEET_ID", "")
        self._creds_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
        self._available = False
        self._init()

    def _init(self) -> None:
        if not self._sheet_id or not self._creds_path:
            log.debug("sheets_exporter_disabled", reason="MDO_SHEET_ID or credentials not set")
            return
        try:
            import gspread
            from google.oauth2.service_account import Credentials
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(self._creds_path, scopes=scopes)
            self._gc = gspread.authorize(creds)
            self._sheet = self._gc.open_by_key(self._sheet_id)
            self._available = True
            log.info("sheets_exporter_ready", sheet_id=self._sheet_id[:12] + "...")
        except ImportError:
            log.debug("sheets_deps_missing", hint="pip install gspread google-auth")
        except Exception as exc:
            log.warning("sheets_init_failed", error=str(exc))

    @property
    def is_available(self) -> bool:
        return self._available

    def push_portfolio_snapshot(
        self,
        available: float,
        used_margin: float,
        total: float,
        positions: list[dict],
    ) -> bool:
        """Update tab 5_Portfolio_Snapshot with current portfolio state."""
        if not self._available:
            return False
        try:
            ws = self._sheet.worksheet(TAB_PORTFOLIO_SNAPSHOT)
            now = now_ist().strftime("%Y-%m-%d %H:%M")

            # Header row (overwrite A1:E1)
            ws.update("A1:E1", [["Updated", "Available (₹)", "Used Margin (₹)", "Total (₹)", "Positions"]])
            ws.update("A2:E2", [[now, available, used_margin, total, len(positions)]])

            # Positions table from row 4
            if positions:
                ws.update("A4:G4", [["Ticker", "Qty", "Avg Price", "LTP", "P&L", "Type", "Updated"]])
                rows = []
                for p in positions:
                    rows.append([
                        p.get("ticker", ""),
                        p.get("quantity", 0),
                        round(p.get("average_price", 0), 2),
                        round(p.get("last_price", 0), 2),
                        round(p.get("pnl", 0), 2),
                        p.get("product_type", ""),
                        now,
                    ])
                ws.update(f"A5:G{4 + len(rows)}", rows)

            log.info("sheets_snapshot_pushed", positions=len(positions))
            return True
        except Exception as exc:
            log.error("sheets_snapshot_failed", error=str(exc))
            return False

    def push_fo_positions(self, positions: list[dict]) -> bool:
        """Update tab 6_FO_Positions with open F&O positions."""
        if not self._available:
            return False
        try:
            ws = self._sheet.worksheet(TAB_FO_POSITIONS)
            now = now_ist().strftime("%Y-%m-%d %H:%M")

            fo_positions = [
                p for p in positions
                if any(
                    idx in p.get("ticker", "").upper()
                    for idx in ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY")
                )
                or p.get("product_type", "") in ("NRML", "MIS")
            ]

            ws.update("A1:H1", [["Updated", "Ticker", "Qty", "Avg Price", "LTP",
                                  "P&L", "Product", "Exchange"]])
            if fo_positions:
                rows = []
                for p in fo_positions:
                    rows.append([
                        now,
                        p.get("ticker", ""),
                        p.get("quantity", 0),
                        round(p.get("average_price", 0), 2),
                        round(p.get("last_price", 0), 2),
                        round(p.get("pnl", 0), 2),
                        p.get("product_type", ""),
                        p.get("exchange", "NSE"),
                    ])
                ws.update(f"A2:H{1 + len(rows)}", rows)
            else:
                ws.update("A2:H2", [[now, "No open F&O positions", "", "", "", "", "", ""]])

            log.info("sheets_fo_pushed", fo_count=len(fo_positions))
            return True
        except Exception as exc:
            log.error("sheets_fo_failed", error=str(exc))
            return False

    def append_investments_balance(self, available: float, total: float) -> bool:
        """Append a row to tab 4_Investments with today's Aditi Investments balance."""
        if not self._available:
            return False
        try:
            ws = self._sheet.worksheet(TAB_INVESTMENTS)
            today = now_ist().strftime("%Y-%m-%d")

            # Check if today's row already exists (avoid duplicates)
            existing = ws.col_values(1)
            if today in existing:
                log.debug("sheets_investments_already_logged", date=today)
                return True

            ws.append_row([today, "Aditi Investments", "HDFC Sec", available, total, "VEGA auto"])
            log.info("sheets_investments_appended", available=available)
            return True
        except Exception as exc:
            log.error("sheets_investments_failed", error=str(exc))
            return False
