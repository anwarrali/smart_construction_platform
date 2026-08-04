class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.appName = 'Construction Field',
    this.aiDiagnosticsEnabled = false,
  });

  final String apiBaseUrl;
  final String appName;
  final bool aiDiagnosticsEnabled;

  factory AppConfig.fromEnvironment() => const AppConfig(
    apiBaseUrl: String.fromEnvironment(
      'API_BASE_URL',
      // 127.0.0.1 on a physical phone points back to the phone. This default
      // is the development machine's Wi-Fi address; deployments should always
      // override it with --dart-define=API_BASE_URL=https://api.example.com/api/v1.
      defaultValue: 'http://192.168.88.6:8000/api/v1',
    ),
    aiDiagnosticsEnabled: bool.fromEnvironment(
      'ENABLE_AI_DIAGNOSTICS',
      defaultValue: false,
    ),
  );
}
