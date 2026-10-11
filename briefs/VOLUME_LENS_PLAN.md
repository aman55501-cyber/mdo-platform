# Volume lens — using volume in daily trading and investing (plan, 2026-10-11)
**Why it directly helps you:** price tells you *where*, volume tells you *whether anyone means it*. Your rules (never book a loss, patient, >80% conviction)
are exactly where volume earns its place: it separates a real breakout from noise, and a quiet pullback (sellers exhausted) from a heavy sell-off (sellers in control).

## Six readings, all computed after the close for your 128 level-shares and 331 holdings (no new subscription)
| # | Reading | Rule of thumb | How you use it |
|---|---|---|---|
| 1 | **Relative volume (RVOL)** = today's volume ÷ 20-day average | ≥ 2× = unusual; ≤ 0.6× = quiet | Anything else you see today is only as trustworthy as its RVOL |
| 2 | **Price + volume pair** | up > 2% on RVOL ≥ 2 = strength; down > 2% on RVOL ≥ 2 = distribution | A held share falling on heavy volume is a *protection* alert, even before it hits a level |
| 3 | **Buy-zone quality** | price at your buy level on RVOL ≤ 0.8 = no sellers left; on RVOL ≥ 2 = still being dumped, wait | Turns "at buy" from a price fact into a patience-friendly call |
| 4 | **Delivery %** (share of volume actually taken delivery) | rising delivery % with a flat price = accumulation | Investing lens: who is holding, not trading |
| 5 | **Breakout confirmation** | close above the 20/50-day high on RVOL ≥ 1.5 | Avoids false breakouts |
| 6 | **Bulk / block deals** | named buyers and sellers of large lots | Signals worth a look on any share you hold or watch |
Daily output: ONE WhatsApp section ("Volume · 5 things that changed today") sorted by what matters for *your* holdings and levels, and a Morning-page card. Holder column on every line (Directive 18).

## Data sources — what I can verify vs not yet
| Need | Source | Status |
|---|---|---|
| Daily OHLC + volume, 20+ days | Yahoo chart API (already used for prices on the server) | works today |
| Delivery % and full bhavcopy | NSE `sec_bhavdata_full_<DDMMYYYY>.csv` on the archives host | **unverified from our server**; NSE's API host answers 403 ([probe 2026-10-11]); testing the archive host now with `/api/market-sources/probe` |
| Bulk / block deals | NSE `content/equities/bulk.csv` and `block.csv` on the archives host ([community code](https://huggingface.co/spaces/eshan6704/backend/commit/31b0f5f7ed4ff1401984dab69de3dcac88a5ce3e)); NSE's page shows only 50 rows and points to the CSV ([NSE](https://www.nseindia.com/report-detail/display-bulk-and-block-deals)) | testing |
| Same data through your broker | Angel One SmartAPI: historical candles with volume, LTP; HDFC Securities API: quotes. Neither lists bulk deals or corporate announcements. | needs your keys (A30 for HDFC) |
If the archive host is also blocked, fallbacks in order: BSE's equivalent files, then Yahoo-only (readings 1, 2, 3, 5 work with no NSE at all; 4 and 6 need NSE/BSE).

## Build order (each step reports every run, even when empty)
1. Readings 1, 2, 3, 5 from Yahoo, post-close (16:30 IST) — zero cost, no blocked source. 2. Add 4 and 6 when a source is confirmed. 3. Morning card + the section in the evening summary. 4. Paper-track "would the volume rule have helped?" on the algo's first 7–15 days of proposals (feeds your standing-limit decision).
