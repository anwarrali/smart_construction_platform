# Construction Field mobile app

## Connecting a phone to the backend

The phone cannot use `127.0.0.1` or `localhost` to reach a backend running on a development computer. Those addresses point to the phone itself.

The current development default is:

```text
http://192.168.88.6:8000/api/v1
```

The backend must listen on `0.0.0.0:8000`, and the phone and computer must be connected to the same Wi-Fi network. Before building, verify `http://192.168.88.6:8000/health` in the phone browser.

For another network or a deployed HTTPS server, always override the URL at build time:

```powershell
flutter run --dart-define=API_BASE_URL=http://YOUR_COMPUTER_LAN_IP:8000/api/v1
flutter build apk --release --dart-define=API_BASE_URL=https://YOUR_API_HOST/api/v1
```

For a development-only readiness screen, add
`--dart-define=ENABLE_AI_DIAGNOSTICS=true` and open
`/dev/ai-diagnostics`. It checks the API, authenticated session, microphone
permission, audio format, and timeout. It does not fake recording, upload,
transcription, or AI success. Leave the flag unset in production builds.

Find the computer's Wi-Fi IPv4 address with `ipconfig`. If the browser cannot open `/health`, allow inbound TCP port 8000 in Windows Firewall for private networks. Do not use an HTTP LAN URL for production releases; use HTTPS.

## Flutter Mobile Docker Tools

Optional reproducible Flutter analysis, tests, and Android builds are available through the repository's `mobile-tools` Docker Compose profile. The mobile application is not a runtime container and is excluded from normal Compose startup. See the root [README](../README.md#flutter-mobile-docker-tools) for commands, caches, artifacts, signing, CI guidance, and iOS limitations.
