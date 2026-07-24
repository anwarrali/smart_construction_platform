class AppConfig {
  const AppConfig({
    required this.apiBaseUrl,
    this.appName = 'Construction Field',
  });

  final String apiBaseUrl;
  final String appName;

  factory AppConfig.fromEnvironment() => const AppConfig(
    apiBaseUrl: String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://127.0.0.1:8000/api/v1',
    ),
  );
}
