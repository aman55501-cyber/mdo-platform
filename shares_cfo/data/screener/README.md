# Screener Premium drop-zone

Drop your Screener export here (`.xlsx` **or** `.csv`). The fundamentals provider
reads the **latest** file and OVERRIDES yfinance with `confidence=high`.

## How to export (Premium)

1. On screener.in, open a **Screen** (or your **Watchlist**).
2. Add the columns you want as thresholds: P/E, P/B, Debt to equity, Return on
   equity, Promoter holding %, Pledged percentage, Dividend yield.
3. Click **Export to Excel** — you get one `.xlsx` with one row per company.
4. Drop that file into this folder. Done — no conversion needed.

The reader matches on the **Name** / **Symbol** / **NSE Code** column. If your
export uses different header text, map it in
`shares_cfo/analysis/fundamentals.py` → `COLMAP`.
