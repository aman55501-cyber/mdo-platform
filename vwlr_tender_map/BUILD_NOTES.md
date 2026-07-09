# VWLR Tender Map — build notes

Flutter Android app for Vedanta Washery & Logistic Solutions (railway code
VWLR, Kharsia, Chhattisgarh). Backend is a live, seeded Supabase project
(`sysicrpylpnzpcuvpvjc`, region ap-south-1) — see `lib/config.dart`.

## Status

| Acceptance criterion | State |
|---|---|
| `flutter analyze` = 0 errors | ✅ Passing (Flutter 3.44.5, Dart 3.12.2). Only info-level deprecation lints remain (`anonKey`, `withOpacity`). |
| `flutter build apk --release` succeeds | ⛔ Blocked in the current environment — see below. |
| App reads live Supabase data, 3 tabs + detail work | Code complete; runtime verification needs an emulator/device (blocked with the build). |
| Deadline notifications schedule without error | Code complete (`lib/services/notifications.dart`). |

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

## How to finish the build (either after allowlisting, or on a normal machine)

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
