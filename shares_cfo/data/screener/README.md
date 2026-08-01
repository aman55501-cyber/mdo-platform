# Screener Premium drop-zone

Drop your Screener export here (`.xlsx` **or** `.csv`). The fundamentals provider
reads the **latest** file and OVERRIDES yfinance with `confidence=high`.

## How to export (Premium)

1. On screener.in, open a **Screen** (or your **Watchlist**).
2. Add the columns you want as thresholds: P/E, P/B, Debt to equity, Return on
   equity, Promoter holding %, Pledged percentage, Dividend yield.
3. Click **Export to Excel** — you get one `.xlsx` with one row per company.
4. Drop that file into this folder. Done — no conversion needed.

The reader matches on the **Name** / **Symbol** / **NSE Code** column.

## Column headers just work now

You don't have to match Screener's exact column names any more. The reader maps
headers in two passes: a deterministic table first, then — for any field it can't
place (e.g. your export says `ROE %` instead of `Return on equity`, or `Sub-Industry`
instead of `Industry`) — **Claude maps the leftover headers to fields**. It only ever
matches *header text*, never touches a data value, validates every header against your
real columns, and caches the result per export. Needs `ANTHROPIC_API_KEY` set; without
it you get the static mapping (set `CFO_SCREENER_LLM_MAP=0` to force static either way).

Check what mapped any time: `GET /fundamentals/screener/status` →
`fields_detected` (field → your header), `llm_mapped_fields` (what Claude rescued),
`fields_missing`. Add an **Industry** column to your export to light up the sub-sector
drill.
