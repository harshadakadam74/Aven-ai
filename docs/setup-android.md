# Android setup

**Status: not built or run.** No Flutter SDK was available when this was written. Follow the steps in order; the first `flutter test` run will tell you quickly whether anything needs fixing.

Requirements: Flutter 3.22 or newer (Dart 3.3+), Android Studio or the Android SDK command-line tools, an emulator or a phone with USB debugging.

## 1. Generate the Android platform files

The repository contains the Dart code only. Create the `android/` folder once:

```powershell
cd apps\android
Copy-Item -Recurse lib ..\lib-backup     # safety copy
flutter create --platforms=android --project-name aven_ai .
Remove-Item test\widget_test.dart -ErrorAction SilentlyContinue   # generated sample test; it won't compile here
flutter pub get
```

If `flutter create` replaced anything in `lib\`, restore it from `..\lib-backup`.

## 2. Allow network access

Edit `android\app\src\main\AndroidManifest.xml`:

- Inside `<manifest>`, before `<application>`, add: `<uses-permission android:name="android.permission.INTERNET"/>`
- For **development over plain HTTP**, add `android:usesCleartextTraffic="true"` to the `<application>` tag. Remove it for any real release and use HTTPS.

## 3. Run the Dart tests and analyzer

```powershell
flutter test
flutter analyze
```

These tests have never been executed. If they fail, that is useful information, not a surprise.

## 4. Connect to the backend

Start the backend on your PC (`.\scripts\run-backend.ps1`).

**Emulator:** the server address is `http://10.0.2.2:8000` (the emulator's name for your PC's localhost; `127.0.0.1` inside the emulator is the emulator itself).

**Physical phone (recommended, keeps the server on localhost):**

```powershell
adb reverse tcp:8000 tcp:8000
```

Then use `http://127.0.0.1:8000` in the app.

**Physical phone over Wi-Fi (less safe):** set `AVEN_AI_HOST=0.0.0.0`, allow port 8000 in Windows Firewall for your private network, and use `http://<your PC's IPv4 from ipconfig>:8000`. Traffic is unencrypted HTTP, so anyone on that network can read your API key. Prefer `adb reverse` until Stage 7 adds pairing and HTTPS.

In the app: Settings, enter the address and the `AVEN_AI_API_KEY` from your `.env`, Save, Test connection.

## 5. Run and build

```powershell
flutter run                      # on the emulator or connected phone
flutter build apk --debug        # build\app\outputs\flutter-apk\app-debug.apk
```

Release builds need a signing key (`flutter build apk --release` after configuring `android\key.properties`). Never put API keys in the app; the user enters theirs in Settings and it is kept in Android secure storage.

## Current Android limits

- Chat needs the backend to be reachable; there is no offline engine on Android yet.
- Opening apps is intentionally not available from Android (the server refuses device actions from API callers).
- No microphone, speech, or wake word yet (Stages 2 and 3). Android background listening will need a foreground service with a visible notification.
