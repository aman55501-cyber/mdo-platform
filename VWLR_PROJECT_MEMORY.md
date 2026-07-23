# VWLR Tender Map — Project Memory

_Exported 2026-07-23. A handoff/reference snapshot: what this system is, how it's
built, its live state, and what's still open. Config IDs here are already public
in the committed code (no service keys)._

## 1. What it is
Mobile-first **coal-logistics tender intelligence** for **Vedanta Washery &
Logistic Solutions (VWLR)** — a coal **road-transport / rake-handling /
liaisoning** firm at VWLR Railway Siding, **Kharsia, Dist. Raigarh, Chhattisgarh**
(railway alpha code **VWLR**). It finds coal tenders, judges eligibility against
VWLR's profile, maps them, and runs the bid workflow.

Core "similar work" = **coal road transport + rake handling + liaisoning (RCR mode)**.

## 2. Stack & locations
- **Database:** Supabase (Postgres). Project id `sysicrpylpnzpcuvpvjc` ·
  URL `https://sysicrpylpnzpcuvpvjc.supabase.co`.
- **Repo:** `aman55501-cyber/mdo-platform` · working branch
  `claude/vwlr-tender-map-flutter-ah6zxy`.
- **Android app:** Flutter, in `vwlr_tender_map/`.
- **Web dashboard:** `vwlr-tender-map.html` (repo root) — install-free, fetches
  the DB live; "Add to Home Screen".
- **CI:** `.github/workflows/build-apk.yml` → builds APK → GitHub Release tag
  **`app-latest`**, asset **`app-release.apk`**
  (`https://github.com/aman55501-cyber/mdo-platform/releases/download/app-latest/app-release.apk`).
  `deploy-web.yml` → GitHub Pages (**NOT enabled** — enabling it gives
  `https://aman55501-cyber.github.io/mdo-platform/`, an auto-updating browser app,
  no reinstalls).

## 3. Database schema
- **`tenders`** — ref_no, title, authority, portal, value_inr, deadline
  (stored **end-of-day 23:59** so a tender stays live through its closing day),
  status (`tender_status` enum: live/bidding/won/lost/closed), relevance_score
  (90 RCR/washery · 80 rail-siding/rake · 72 power-plant · 62 other),
  relevance_reason, pdf_url, hearted, **pursued / bid_stage / bid_checklist**
  (Bid Desk), QR eligibility fields: qr_min_turnover_inr, qr_experience_mt,
  qr_experience_window_months, qr_experience_value_inr, qr_networth_inr,
  qr_networth_pct, qr_solvency_inr, emd_inr.
- **`locations`** — tender_id, role (`location_role`: mine/plant/siding/base),
  name, lat, lng, district, state. (Map markers + haul routes.)
- **`org_profile`** (id=1) — VWLR's profile (below).
- **Function** `public.close_expired_tenders()`.
- **pg_cron job `purge-expired-tenders`** — every 15 min, deletes tenders (and
  their locations) where `deadline < now()` or status not in (live,bidding).
  This is the authority for "only active tenders show" — server-side, silent,
  independent of any session or app version. (Confirmed running.)

## 4. VWLR profile (org_profile id=1) — verified against the user's books
- Avg annual turnover **₹112.15 Cr** (`1121539000`); FY22-23 128.55 / FY23-24
  121.98 / FY24-25 85.93 Cr.
- Net worth **₹96.55 Cr** (`965523000`, FY24-25). Paid-up capital **₹8.14 Cr**
  (`81424000`).
- Peak experience **21.95 lakh MT** (`2194654`) over **12 months** (client **RKM
  Powergen**); best single month 3.09 lakh MT; largest_work_order_mt 2194654.
  **largest_work_order_inr = NULL — still needed** (₹ value of the RKM contract).
- Bank solvency **₹79 Cr** (`790000000` = Yes Bank 49 + Kotak 30).
- PBG capacity **₹8 Cr** (`80000000`) — 5% PBG backs a contract of **~₹160 Cr**.
- MSME ✓, Class-I ✓, GeM-enlisted ✓, GST `22AAECV8176B1ZG`, not blacklisted.
- Base lat 21.9833 / lng 83.1; operating radius 300 km.
- Fleet (owned): **103 trailer/hywa, 11 poclain/clamshell, 10 loaders**.
- **Appetite:** value floor **₹250 Cr** (the "Big" filter). 22 preferred buyers:
  NTPC, NALCO, SECL, MCL, CSPGCL, Adani, Tata, JSW, Jindal/JPL, Vedanta, Hindalco,
  UltraTech, NUPPL, MPPGCL, Nabha, Mahagenco, JHABUA, Dhariwal, CSPDCL, APGENCO,
  PPGCL, CESC.

## 5. App (5 tabs)
1. **Map** — per-tender colour shade + role symbols (⛰ mine · 🏭 plant · 🚆 siding
   · 🏠 base), small name labels, mine→plant haul lines, base radius. Live tenders
   only. Google Maps Android key baked in; R8/minify disabled (fixed a launch crash).
   Markers generated at runtime (canvas → BitmapDescriptor.bytes).
2. **Tenders** — list with filters (Relevant / Live / Big ₹250Cr+ / Saved / All);
   preferred buyers float to top; BG-shortfall flag.
3. **Eligibility** — judges each tender vs profile → **✅ Eligible / 🔍 Needs review
   / (hidden) Not eligible**, with a per-criterion breakdown. Net-worth test fixed
   to compare vs absolute or % of **contract value** (never % of paid-up capital).
   Soft checks (BG capacity, registrations) flag but don't disqualify.
4. **Bid Desk** — "Pursue this bid" (on tender detail) moves a tender here with a
   stage tracker (Interested→Preparing→Submitted→Won/Lost) and a 7-step checklist
   (download doc · PQ pack · EMD · 5% PBG vs capacity · pre-bid · submit · result)
   with the tender's numbers filled in; progress persists to the DB.
5. **Dashboard** — stats + VWLR bid-prep profile panel.

Delivery caveat: each app change needs a **manual APK reinstall** (latest builds
often show 0 downloads → improvements don't reach the phone until reinstalled).
Enabling GitHub Pages removes this friction.

## 6. Data pipeline
- **Source:** Tender247 email alerts from `admin@bidsnrfp.com` → Gmail
  (`aman.55501@gmail.com`), subjects "N New Tender/s".
- **Ingest:** read digests → extract coal-logistics-relevant → insert into
  `tenders` + geocoded `locations`; dedupe on ref_no.
- **Daily sync** (Routine `trig_01HdHtpD1r8D2cfrjUpHdHk5`, cron `30 2 * * *` =
  08:00 IST) — **currently PAUSED** (enabled=false) at user request; ingest-only
  (no deletes — pg_cron handles cleanup). Resume by re-enabling it or say
  "resume sync". "add new tenders" pulls the latest inbox digests on demand.
- **Health monitor** — ~6h self-scheduled check (DB up, counts, purge) still armed.
- **Eligibility auto-extraction: DISABLED.** This environment's egress policy
  returns **403** for the tender portals (coalindiatenders.nic.in, mahagenco.in,
  scclmines.com, nalcoindia.com, gem.gov.in, dvc.gov.in, secl-cil.in, …) and
  general web — so NITs can't be fetched to read PQC. To fill eligibility
  thresholds: **paste the eligibility clause / upload the NIT PDF**, or open the
  environment's network policy.

## 7. Current state (2026-07-23)
- **28 active tenders**, 0 expired/closed (DB self-cleans via pg_cron).
- Web dashboard hardened: removed the stale `SNAPSHOT` demo fallback + added an
  active-only render gate → expired/closed can never show.

## 8. Open items / next steps
1. **Largest work-order ₹ value** (RKM contract) → activates the similar-work-value
   eligibility check.
2. **Enable GitHub Pages** (repo Settings → Pages → Source: "GitHub Actions") →
   auto-updating browser app, ends the reinstall friction.
3. **Paste PQC/eligibility clauses** for tenders being pursued → real ✅/❌ verdicts.
4. Optional: auto-refresh in the app (currently refreshes on cold-start / ⟳ only).

## 9. Handy commands
```sql
-- active tenders
select ref_no, authority, title, value_inr, deadline, relevance_score
from tenders where status in ('live','bidding') order by deadline;
-- purge job health
select * from cron.job where jobname='purge-expired-tenders';
select status, return_message, start_time from cron.job_run_details
  order by start_time desc limit 5;
-- set a tender's eligibility (example)
update tenders set qr_min_turnover_inr=<rupees>, qr_experience_mt=<mt>,
  qr_experience_window_months=<mo> where ref_no='T247-...';
```
