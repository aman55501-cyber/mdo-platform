# Web run harness

Runs the actual VWLR Tender Map app (the Flutter **web** build) headlessly and
drives every screen, on a machine where the real backend and Google's font /
CanvasKit CDNs are blocked. Used to verify the app end-to-end when the Android
APK can't be built and `*.supabase.co` is unreachable from the build host.

## What it proves

Launching the built app and driving it as a user confirmed, against the real
seed data served by the local mock:

- **Map** tab renders (legend, map-control FABs; map tile is a gray placeholder
  without a Maps key).
- **Tenders** list shows both tenders with correct status chips (NSPCL `CLOSED`,
  NALCO `LIVE`), values (₹9.31 Cr / ₹4.94 Cr), deadlines, hearts, and the
  All / Live / Watching / Eligible filters.
- **Detail** shows the eligibility verdict (NALCO → "No published PQC"), the
  facts table, Route & locations with per-site km, notes, the PDF button
  (disabled when `pdf_url` is null) and the status chips.
- **Dashboard** computes Live 1 / Eligible 1 / Pipeline ₹4.94 Cr, "No upcoming
  deadlines", and the pipeline counts.
- **Write-back**: tapping a heart issues `PATCH /rest/v1/tenders?id=eq.<uuid>`
  → `204`, then reloads; the change persists.
- All three reads hit PostgREST with the exact query strings the repository
  builds (`org_profile?select=*&id=eq.1`, `tenders?...order=deadline.asc.nullslast`,
  `locations?select=*`).

## How to run

```bash
cd vwlr_tender_map

# 1. Point the app at the local mock for the run (revert afterwards):
#    lib/config.dart -> supabaseUrl = 'http://127.0.0.1:54321'

# 2. Build web with CanvasKit bundled locally:
flutter build web --release --no-web-resources-cdn

# 3. Start the mock backend + a static server:
node tool/web_run/mock_supabase.js &                       # :54321
python3 -m http.server 8080 --directory build/web &        # :8080

# 4. Drive it (Playwright + the pre-installed Chromium):
PW="$(npm root -g)/playwright/index.mjs" \
PW_EXEC="/opt/pw-browsers/chromium-1194/chrome-linux/chrome" \
node tool/web_run/drive.mjs                                 # writes run_*.png

# 5. Restore lib/config.dart -> the real https://...supabase.co URL.
```

The `--no-web-resources-cdn` flag and the Roboto-font route in `drive.mjs` are
**only** needed on locked-down networks. On a real device/browser with normal
internet, CanvasKit and the font load from Google's CDN automatically and the
app works with no harness.
