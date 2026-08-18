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
      // .88.6, the router later moved the machine to .88.5, and every build
      // in between failed on the phone with a generic "cannot reach the
      // server" that looks exactly like a rejected password. If sign-in
      // fails to connect, the login screen now prints the address it tried —
      // compare it with `ipconfig` before suspecting anything else.
      //
      // Deployments must override this:
      //   --dart-define=API_BASE_URL=https://api.example.com/api/v1
      defaultValue: 'http://192.168.88.5:8000/api/v1',
    ),
    aiDiagnosticsEnabled: bool.fromEnvironment(
      'ENABLE_AI_DIAGNOSTICS',
      defaultValue: false,
    ),
  );
}
