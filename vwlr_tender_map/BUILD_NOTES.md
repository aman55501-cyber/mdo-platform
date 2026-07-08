# VWLR Tender Map — build notes

Flutter app for Vedanta Washery & Logistic Solutions (VWLR, Kharsia, Chhattisgarh).
Reads a live Supabase backend; shows tenders on a Google Map, a filterable list,
tender detail with an eligibility verdict, and a dashboard. Schedules local
deadline reminders.

## Status

| Acceptance criterion | Result |
|---|---|
| `flutter analyze` = 0 errors | ✅ **No issues found** (0 errors / 0 warnings / 0 infos) |
| `flutter build apk --release` succeeds | ⛔ **Blocked by this environment's network policy** — see below |
| Reads live Supabase data, 3 tabs + detail | ✅ code complete (verified statically; runtime needs the APK) |
| Deadline notifications schedule | ✅ code complete (adapted to installed plugin API) |

The Dart/Flutter side is **complete and analyzer-clean**. The only thing missing
is the final Android/Gradle compile, which cannot finish here because Google's
Android Maven repository is unreachable from this sandbox.

## What blocks the APK build (and how to fix it)

The Android Gradle Plugin (`com.android.tools.build:gradle`) and all `androidx.*`
libraries are published **only** on Google's Maven repository, served from
`dl.google.com/dl/android/maven2/`. In this environment that host — and every
mirror of it — is denied by the egress network policy:

```
dl.google.com            -> 403 (CONNECT rejected by policy)
maven.google.com         -> 301 redirect to dl.google.com (blocked)
maven.aliyun.com (mirror)-> blocked
repo.huaweicloud.com     -> blocked
Maven Central            -> 404 (androidx/AGP are not hosted there)
plugins.gradle.org/m2    -> redirects to Maven Central (404)
```

Because androidx/AGP have no reachable source, Gradle fails at dependency
resolution before any compilation. This is a **network-policy** limitation, not a
code problem.

### Fix — pick one

1. **Re-run in an environment with open egress** (recommended). Allow
   `dl.google.com` (and `maven.google.com`) in the environment's network policy,
   then run `flutter build apk --release`. With that host reachable the standard
   toolchain resolves everything. See
   https://code.claude.com/docs/en/claude-code-on-the-web (network policies).

2. **Build on any machine with normal internet** (the project is complete):
   ```bash
   cd vwlr_tender_map
   flutter pub get
   flutter build apk --release
   # -> build/app/outputs/flutter-apk/app-release.apk
   ```

## Toolchain notes

The **committed project is stock and portable** — it uses the standard
Flutter 3.24.5 Android config (Gradle 8.3 wrapper via `services.gradle.org`,
AGP 8.1.0, Kotlin 1.8.22) plus the spec's real requirements:
compileSdk 34 / minSdk 21 / Java 17 and core-library desugaring
(`desugar_jdk_libs:2.1.2`) for `flutter_local_notifications`. On any machine
with normal internet, `flutter pub get && flutter build apk --release` just works.

During this sandbox session the following temporary workarounds were used to get
as far as possible against the firewall (they were **not** committed, to keep the
project portable):

- **Flutter pinned to 3.24.5** (Dart 3.5). The container had no Flutter; the
  latest stable (3.44) pulls AGP 9 / compileSdk 36, which the mid-2024 plugins in
  `pubspec.yaml` predate. 3.24.5 matches those plugin versions. *(This pin is
  worth keeping — it is why the plugin versions resolve cleanly.)*
- **Gradle distribution** served from a local file, because `services.gradle.org`
  redirects to a GitHub release asset that the policy blocks.
- **AGP 8.7.3 / Kotlin 2.1.0** to match that local Gradle.
- **Android SDK skeleton**: `dl.google.com` blocks `sdkmanager`, so a minimal SDK
  was assembled (platform-34 `android.jar` + synthesized metadata + license
  hashes). With open egress, install the real SDK normally:
  `sdkmanager "platforms;android-34" "build-tools;34.0.0"`.

## Configuration you still need to set

- **Google Maps Android key** (`PASTE_YOUR_GOOGLE_MAPS_ANDROID_KEY`) in
  `lib/config.dart` **and** `android/app/src/main/AndroidManifest.xml`. The app
  compiles and runs without it; only the map tiles stay blank until it's added.
- **Eligibility financials**: `org_profile` in Supabase uses placeholder
  turnover / net worth / experience. Update that row with VWLR's real figures so
  the eligibility verdict is accurate.

## API adaptation made

`flutter_local_notifications` (installed 17.x) requires
`uiLocalNotificationDateInterpretation` on `zonedSchedule`; it was added in
`lib/services/notifications.dart`.
