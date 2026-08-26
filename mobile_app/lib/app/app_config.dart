class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.appName = 'Struct IQ',
    this.aiDiagnosticsEnabled = false,
  });

  final String apiBaseUrl;
  final String appName;
  final bool aiDiagnosticsEnabled;

  factory AppConfig.fromEnvironment() => const AppConfig(
    apiBaseUrl: String.fromEnvironment(
      'API_BASE_URL',
      // The development machine's Wi-Fi address. 127.0.0.1 would point a
      // physical phone back at itself, and 10.0.2.2 only means anything to
      // the Android emulator, so a LAN address is the only default that can
      // work on a real device.
      //
      // It is also **DHCP-assigned and will go stale**: this value was
      // .88.6, then .88.5, and is now .88.2 — each move broke every build in
      // between with a generic "cannot reach the server" that looks exactly
      // like a rejected password. If sign-in fails to connect, the login
      // screen prints the address it tried; compare it with `ipconfig`
      // before suspecting anything else.
      //
      // Rather than editing this line again, prefer passing the current
      // address at build time, which leaves the checked-in default alone:
      //   flutter run --dart-define=API_BASE_URL=http://<your-ip>:8000/api/v1
      //
      //   defaultValue: 'http://192.168.88.2:8000/api/v1',
      // Deployments must override it the same way:
      //   --dart-define=API_BASE_URL=https://api.example.com/api/v1
      defaultValue: 'http://127.0.0.1:8000/api/v1',
    ),
    aiDiagnosticsEnabled: bool.fromEnvironment(
      'ENABLE_AI_DIAGNOSTICS',
      defaultValue: false,
    ),
  );
}
