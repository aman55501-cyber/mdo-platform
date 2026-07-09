# VWLR Tender Map — build notes

Flutter Android app for Vedanta Washery & Logistic Solutions (railway code
VWLR, Kharsia, Chhattisgarh). Backend is a live, seeded Supabase project
(`sysicrpylpnzpcuvpvjc`, region ap-south-1) — see `lib/config.dart`.

## Status

| Acceptance criterion | State |
|---|---|
| `flutter analyze` = 0 errors | ✅ Passing (Flutter 3.44.5, Dart 3.12.2). Only info-level deprecation lints remain (`anonKey`, `withOpacity`). |
| `flutter build apk --release` succeeds | ⛔ Blocked in the current environment — see below. |
| App reads live Supabase data, 3 tabs + detail work | ✅ **Verified by running the web build** headlessly against the real seed data — Map, Tenders (+ filters/hearts), Detail (eligibility, facts, locations, status chips), Dashboard, and heart/status write-back (`PATCH → 204`) all work. See `tool/web_run/`. |
| Deadline notifications schedule without error | Code complete (`lib/services/notifications.dart`); guarded with `kIsWeb` so the web build doesn't crash (the plugin has no web implementation). |

## Why the APK build is blocked here

This build ran inside a Claude Code sandbox whose outbound network policy
**denies `dl.google.com` (HTTP 403 at the egress proxy).** The entire Android
build toolchain lives behind that host:

- **Android SDK** command-line tools, platform-tools, build-tools, and
  `platforms;android-NN` are served only from
  `https://dl.google.com/android/repository/...`.
- **Android Gradle Plugin** and its dependencies resolve from Google's Maven
  (`google()` repo), which is `maven.google.com` → 301 →
  `https://dl.google.com/dl/android/maven2/...` — same blocked host.

`pub.dev`, `storage.googleapis.com`, Maven Central, and the Gradle
distribution hosts are reachable, so `flutter pub get` and `flutter analyze`
work; only the Google-hosted Android artifacts are unreachable.

Per the sandbox proxy policy, policy denials must not be routed around
(mirrors, etc.). Allowlisting the host is the correct fix.

## Runnable *today* without the Android toolchain: Flutter web

The **same Dart codebase builds for the web**, whose engine assets come from
`storage.googleapis.com` (allowed) rather than `dl.google.com`:

```bash
flutter build web --release --no-web-resources-cdn
# -> build/web/  (static site; open index.html via any web server)
# --no-web-resources-cdn bundles CanvasKit under canvaskit/ instead of loading
# it from gstatic.com, so the app also works on locked-down/offline hosts.
```

To verify it without a device, `tool/web_run/` runs the built app headlessly
against a local mock of the Supabase API seeded with the real rows, and drives
every screen (see that folder's README).

This succeeds in the sandbox. Serve `build/web/` on any static host (GitHub
Pages, Netlify, `python3 -m http.server`, etc.) and open it on a phone or
laptop — where `*.supabase.co` is reachable over the public internet, so the
app loads live tender data, and the list / dashboard / detail / eligibility /
heart+status write-back all work. The Map tab needs a "Maps JavaScript API"
browser key pasted into `web/index.html` (placeholder is wired in); without it
only the map tile stays blank.

> Note: inside the Claude Code sandbox both `dl.google.com` **and**
> `*.supabase.co` are denied by the egress policy, so the app can't be
> exercised end-to-end *here* — but it runs anywhere with normal internet.

## How to finish the Android build (either after allowlisting, or on a normal machine)

1. Ensure network access to `dl.google.com` and `maven.google.com`
   (in Claude Code on the web: choose/adjust the environment's network policy).
2. Install the Android SDK (Android Studio, or command-line tools) and set
   `ANDROID_HOME`. Accept licenses: `flutter doctor --android-licenses`.
3. From this directory:
   ```bash
   flutter pub get
   flutter analyze          # already 0 errors
   flutter build apk --release
   # -> build/app/outputs/flutter-apk/app-release.apk
   ```

The Gradle config is already prepared: `minSdk` ≥ 21, core-library
desugaring enabled, and `desugar_jdk_libs:2.1.4` added
(`android/app/build.gradle.kts`).

## Google Maps key (needed only for map tiles)

`PASTE_YOUR_GOOGLE_MAPS_ANDROID_KEY` is still a placeholder in two files:
- `lib/config.dart`
- `android/app/src/main/AndroidManifest.xml`

The app compiles and runs without it; only the Map tab's tiles stay blank
until a real "Maps SDK for Android" key is pasted into both.

## Reminder about eligibility data

The eligibility engine (`lib/services/eligibility.dart`) compares each
tender's published PQC against the `org_profile` row. That row currently holds
**placeholder financials.** Update it with VWLR's real avg. turnover, net
worth, paid-up capital, and past experience (MT) so the "Eligible" verdicts
are accurate.
