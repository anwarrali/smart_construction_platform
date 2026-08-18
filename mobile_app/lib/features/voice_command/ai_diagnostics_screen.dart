import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

import '../../app/dependency_injection.dart';
import '../../core/l10n/l10n_labels.dart';

class AiDiagnosticsScreen extends ConsumerStatefulWidget {
  const AiDiagnosticsScreen({super.key});

  @override
  ConsumerState<AiDiagnosticsScreen> createState() => _AiDiagnosticsScreenState();
}

class _AiDiagnosticsScreenState extends ConsumerState<AiDiagnosticsScreen> {
  bool _running = false;
  Map<String, _DiagnosticResult> _results = const {};

  @override
  void initState() {
    super.initState();
    Future.microtask(_run);
  }

  Future<void> _run() async {
    setState(() => _running = true);
    final config = ref.read(configProvider);
    final api = ref.read(apiClientProvider);
    final recorder = AudioRecorder();
    final results = <String, _DiagnosticResult>{};
    final uri = Uri.tryParse(config.apiBaseUrl);
    final loopback = uri == null || {'localhost', '127.0.0.1', '10.0.2.2'}.contains(uri.host);
    results['Physical-device API URL'] = _DiagnosticResult(
      !loopback,
      loopback ? 'The configured URL is not suitable for a physical phone.' : config.apiBaseUrl,
    );
    results['Release transport'] = _DiagnosticResult(
      uri?.scheme == 'https' || kDebugMode,
      uri?.scheme == 'https' ? 'HTTPS is configured.' : 'HTTP is allowed only by the debug Android manifest.',
    );
    try {
      final health = await api.get<Map<String, dynamic>>('/health');
      results['API reachable'] = _DiagnosticResult(
        health['status'] == 'healthy',
        'Backend responded: ${health['status'] ?? 'unknown'}',
      );
    } catch (error) {
      results['API reachable'] = _DiagnosticResult(false, '$error');
    }
    try {
      await api.get<Map<String, dynamic>>('/auth/me');
      results['Authentication valid'] = const _DiagnosticResult(true, 'Authenticated profile request succeeded.');
    } catch (error) {
      results['Authentication valid'] = _DiagnosticResult(false, '$error');
    }
    try {
      final permitted = await recorder.hasPermission();
      results['Microphone permission'] = _DiagnosticResult(
        permitted,
        permitted ? 'Android reports microphone access is granted.' : 'Permission is not granted. Open the voice screen to request it.',
      );
    } catch (error) {
      results['Microphone permission'] = _DiagnosticResult(false, '$error');
    } finally {
      await recorder.dispose();
    }
    results['Recording format'] = const _DiagnosticResult(true, 'AAC-LC in an M4A container; uploaded as audio/mp4.');
    results['Voice timeout'] = const _DiagnosticResult(true, 'Upload/analysis receive timeout is 120 seconds.');
    if (mounted) {
      setState(() {
        _results = results;
        _running = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final enabled = ref.watch(configProvider).aiDiagnosticsEnabled;
    if (!enabled) {
      return Scaffold(
        body: Center(child: Text(context.l10n.diagnosticsDisabled)),
      );
    }
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.diagnosticsTitle)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(context.l10n.diagnosticsBody),
          const SizedBox(height: 16),
          if (_running) const LinearProgressIndicator(),
          ..._results.entries.map(
            (entry) => Card(
              child: ListTile(
                leading: Icon(
                  entry.value.passed ? Icons.check_circle : Icons.error,
                  color: entry.value.passed ? Colors.green : Colors.red,
                ),
                title: Text(entry.key),
                subtitle: Text(entry.value.detail),
              ),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _running ? null : _run,
            icon: const Icon(Icons.refresh),
            label: Text(context.l10n.diagnosticsRerun),
          ),
        ],
      ),
    );
  }
}

class _DiagnosticResult {
  const _DiagnosticResult(this.passed, this.detail);
  final bool passed;
  final String detail;
}
