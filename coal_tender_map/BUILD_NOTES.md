# Coal Tender Map — native Android (Kotlin + Jetpack Compose)

Native app for Vedanta Washery & Logistic Solutions (VWLR, Kharsia, Chhattisgarh).
Coal-transport tenders on a Google Map (mine → plant), pickup-from-HQ and haul
distances, auto eligibility verdict vs the firm profile, and a generated NIT view.
Backend is the LIVE Supabase project `vwlr-tender-map` (do not recreate).

## Status
- ✅ Complete Android Studio project, all files per the spec (13 Kotlin sources +
  Gradle wiring + manifest + launcher icon).
- ⛔ **APK not built in this sandbox** — same network-policy block as the Flutter
  build: Google's Maven host `dl.google.com` (AGP, all of androidx/Compose, Google
  Maps Compose) is firewalled here and has no reachable mirror. A native Compose app
  depends on it even more heavily than Flutter, and there is no offline analyzer for
  Kotlin+Compose either. Maven Central (Supabase-kt, Ktor, kotlinx) IS reachable.

## Build it (any machine with normal internet)
Option A — Android Studio: File → Open → this folder → let it sync → Run.
Option B — command line:
```bash
export ANDROID_HOME=/path/to/Android/Sdk   # or set sdk.dir in local.properties
./gradlew assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease      # app/build/outputs/apk/release/app-release.apk
```
The Android SDK must have `platforms;android-34` and `build-tools;34.0.x` installed
(Android Studio prompts for these automatically).

## Versions pinned (mutually compatible, mid-2024 era)
AGP 8.5.2 · Kotlin 2.0.0 (android + serialization + compose-compiler plugins) ·
Gradle 8.9 (wrapper) · compileSdk/target 34, minSdk 24 · Compose BOM 2024.09.00 ·
maps-compose 6.1.0 / play-services-maps 19.0.0 · Supabase BOM 2.6.0 + postgrest-kt ·
Ktor 2.3.12 · kotlinx-serialization-json 1.7.1.

## Known drift to watch on first sync (adapt, don't delete features)
- **supabase-kt Postgrest** (`data/Repository.kt`): the `select { order(...) }` and
  `update(map) { filter { eq(...) } }` DSL shifted across 2.x. If the resolved BOM
  rejects it, switch to the typed builder (e.g. `update({ set("hearted", v) }) { filter { eq("id", id) } }`)
  — keep the same behaviour (list tenders + locations, update hearted/status by id).
- If Supabase returns `numeric` columns as JSON strings and `Double` decode throws,
  make those model fields `String?` and parse, or install a lenient Json — don't drop fields.
- `Surface(onClick = …)` uses `@OptIn(ExperimentalMaterial3Api::class)` (already added
  at the top of MapScreen.kt / DetailSheet.kt).

## Still yours to do
1. **Google Maps key** — replace `PASTE_YOUR_GOOGLE_MAPS_ANDROID_KEY` in
   `app/src/main/AndroidManifest.xml`. App builds/runs with the placeholder; only map
   tiles are blank until the key is added. (`Config.kt` stays as-is.)
2. **Real financials** — fill your true turnover / net worth / paid-up capital /
   experience into the `org_profile` row (Supabase) so the eligibility verdict is
   accurate. A questionnaire for this already exists.
