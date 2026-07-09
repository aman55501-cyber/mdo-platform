# VWLR Tender Map — backend pipeline (Supabase)

Daily auto-population of coal-transport tenders, relevance filtering, de-dup,
document links, and auto-close of expired tenders. All objects below are
deployed on the live project `sysicrpylpnzpcuvpvjc` (tracked in Supabase
migration history); this folder documents them and holds the Gmail ingester.

## Data flow

```
Tender247 alert emails (Gmail)
        │   supabase/tender247/Tender247Ingest.gs  (daily Google Apps Script)
        ▼
public.ingest_tender247_batch(secret, items)      ← secret-gated RPC (anon-callable)
        │   inserts into
        ▼
public.tender_candidates  (staging)
        │   public.ingest_candidates()
        ▼
public.tenders            ← relevant only, de-duped by (source_api, source_uid),
                            pdf_url = tender document link
```

Two `pg_cron` jobs run daily:
- `vwlr-tender247-ingest` (01:00 UTC) → `fetch_tender247()` (for a future direct
  API; currently disabled and no-ops — the Gmail Apps Script is the live source).
- `vwlr-close-expired` (19:00 UTC) → `close_expired_tenders()` flips Live/Bidding
  tenders past their deadline to Closed.

## Relevance filter — `score_tender_relevance(text, state)`

Gate: text must mention **coal / lignite / washery** AND a **transport / handling**
scope (transport, haul, loading, unloading, siding, tipper, conveyor, RCR, …).
Bonuses: washery scope (+10), in-region (+25) — Chhattisgarh / Odisha / Jharkhand /
MP / WB or VWLR's coalfield towns. Score 0 ⇒ rejected with a reason. Verified on
the real feed: Central Coalfields "handling, transport… coal extraction" → 75
(published); biomass-pellet and coal-*supply* tenders → 0 (filtered out).

## Objects

| Object | Purpose |
|---|---|
| `tenders.source_api/source_uid/relevance_score/relevance_reason/ingested_at` | provenance + de-dup key (`pdf_url` holds the doc link) |
| `tender_candidates` | raw landing table for incoming tenders |
| `score_tender_relevance()` | relevance score + reason |
| `ingest_candidates()` | filter → de-dup → upsert into `tenders` (preserves user status/hearted) |
| `close_expired_tenders()` | daily hygiene |
| `ingest_config` + Vault `tender247_api_key` | config for the (optional) direct-API fetch |
| `fetch_tender247()` | direct-API adapter (disabled until an API is configured) |
| `ingest_tender247_batch(secret, items)` | endpoint the Gmail Apps Script calls |

## Enable the daily Gmail feed

See the header of `tender247/Tender247Ingest.gs`: paste into script.google.com,
run once to authorize, add a daily time-driven trigger. It labels processed
emails `Tender247-Ingested` and is idempotent (re-runs are safe — upsert by
Tender247 id).

> The `ingest_secret` in the script gates writes to your own staging table only
> (low sensitivity). Rotate any time with
> `update public.ingest_config set ingest_secret = encode(extensions.gen_random_bytes(18),'hex') where id=1;`
> and update the script.
