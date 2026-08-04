# Construction Platform Software Project

The default Docker workflow starts PostgreSQL, the FastAPI backend, and the web frontend:

```bash
docker compose up --build
```

The native Flutter application is developed normally from `mobile_app` with `flutter pub get` and `flutter run`. Docker is optional for repeatable checks and Android artifact builds.

## Flutter Mobile Docker Tools

The Flutter client is an Android/iOS application, not a permanent server. It is excluded from the default Compose workflow and never starts, builds, runs tests, or launches an emulator with `docker compose up --build`.

The optional `mobile-tools` profile uses Flutter 3.32.2 with Dart 3.8.1, matching the project metadata and SDK constraint. It provides Linux-based Flutter, Android SDK, Pub, and Gradle tooling suitable for local validation and future CI.

If antivirus or a corporate proxy replaces HTTPS certificates, keep TLS verification enabled and pass its public root CA as a temporary BuildKit secret (never commit it):

```powershell
docker build --secret id=additional_ca,src=C:\path\to\root-ca.crt -f mobile_app/Dockerfile.ci -t constructionplatformsoftwareproject-flutter-tools mobile_app
```

On a normal network, use the Compose build command below; no CA secret is needed.

### Commands

Run these commands from the repository root:

```bash
# Verify the container SDK
docker compose --profile mobile-tools run --rm flutter-tools flutter --version

# Install dependencies
docker compose --profile mobile-tools run --rm flutter-tools flutter pub get

# Static analysis
docker compose --profile mobile-tools run --rm flutter-tools flutter analyze

# Tests
docker compose --profile mobile-tools run --rm flutter-tools flutter test

# Combined dependency, analysis, and test validation (mobile-check)
docker compose --profile mobile-tools run --rm flutter-tools sh tool/mobile-check.sh

# Android release APK
docker compose --profile mobile-tools run --rm flutter-tools \
  flutter build apk --release --dart-define=API_BASE_URL=https://YOUR_API_HOST/api/v1

# Android release App Bundle
docker compose --profile mobile-tools run --rm flutter-tools \
  flutter build appbundle --release --dart-define=API_BASE_URL=https://YOUR_API_HOST/api/v1
```

Build the tools image explicitly when required:

```bash
docker compose --profile mobile-tools build flutter-tools
```

The application directory is bind-mounted into the container, so generated artifacts remain on the host:

- APK: `mobile_app/build/app/outputs/flutter-apk/app-release.apk`
- App Bundle: `mobile_app/build/app/outputs/bundle/release/app-release.aab`

Named volumes retain Pub and Gradle downloads between runs. Container-specific `.dart_tool` and `android/.gradle` data is isolated from the host toolchain. Docker is not required for regular Android Studio, VS Code, or `flutter run` development.

### API environments

The application already reads `API_BASE_URL` through `--dart-define`. Choose a URL reachable from the device:

- Android emulator: normally `http://10.0.2.2:8000/api/v1` for a backend on the development computer.
- Physical device: use the computer's LAN address; `localhost` refers to the phone itself.
- Staging and production: use a publicly reachable HTTPS API URL.

The Compose hostname `backend` works only between containers on the Compose network. An installed mobile application cannot use it. See [mobile_app/README.md](mobile_app/README.md) for physical-device networking notes.

### Android signing

The current project falls back to Android's debug signing configuration for local release-mode builds. Such artifacts are not suitable for Google Play. A Play release requires a privately managed upload keystore and a signed `.aab`.

Optional CI signing is supported without storing credentials in the repository. Set these environment variables in the CI secret store:

```text
ANDROID_KEYSTORE_PATH
ANDROID_KEYSTORE_PASSWORD
ANDROID_KEY_ALIAS
ANDROID_KEY_PASSWORD
```

Mount the keystore read-only at the container path referenced by `ANDROID_KEYSTORE_PATH`. Do not place a keystore, passwords, or aliases in Dockerfiles, Compose files, Git, or build logs. No signing file is mounted by default.

### Code generation and CI

The current `pubspec.yaml` does not use `build_runner`, Freezed, JSON serialization generators, Injectable, Retrofit generators, Drift, or Riverpod Generator, so no code-generation command is required. If a generator is added later, add its declared project command to CI rather than installing undeclared generator packages.

A future CI pipeline can use the same profile for dependency installation, static analysis, tests, `flutter build appbundle`, and artifact collection. This setup does not publish to Google Play or the App Store.

### iOS limitation

The Linux tools image can analyze and test shared Dart code and build Android artifacts. It cannot create a valid App Store iOS release because Xcode is only available on macOS. Run `flutter build ipa` on a macOS development machine or macOS CI runner for iOS releases; no simulator or Xcode emulation is attempted in Docker.
