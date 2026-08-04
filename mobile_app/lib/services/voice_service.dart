import 'package:dio/dio.dart';

import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/voice_draft.dart';

class VoiceProcessingService {
  VoiceProcessingService(this._api);
  final ApiClient _api;

  Future<VoiceAnalysis> createAnalysis({
    required String projectId,
    required String filePath,
    required Duration duration,
    required String requestId,
    String? taskId,
    ProgressCallback? onSendProgress,
  }) async {
    final filename = filePath.split(RegExp(r'[/\\]')).last;
    final form = FormData.fromMap({
      'project_id': projectId,
      if (taskId != null) 'task_id': taskId,
      'duration_seconds': duration.inSeconds,
      'idempotency_key': requestId,
      'audio': await MultipartFile.fromFile(
        filePath,
        filename: filename,
        contentType: DioMediaType.parse('audio/mp4'),
      ),
    });
    final data = await _api.upload<Map<String, dynamic>>(
      ApiEndpoints.voiceCommands,
      form,
      onSendProgress: onSendProgress,
      receiveTimeout: const Duration(seconds: 120),
    );
    return VoiceAnalysis.fromJson(data);
  }

  Future<Map<String, dynamic>> actionHistory(String projectId) =>
      _api.get<Map<String, dynamic>>(
        ApiEndpoints.aiActions,
        query: {'project_id': projectId, 'page_size': 50},
      );

  Future<Map<String, dynamic>> revertAction({
    required String actionId,
    required String requestId,
    required String reason,
  }) => _api.post<Map<String, dynamic>>(
    ApiEndpoints.revertAiAction(actionId),
    data: {'requestId': requestId, 'reason': reason},
  );

  Future<VoiceAnalysis> retryAnalysis(String analysisId) async {
    final data = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.retryVoiceAnalysis(analysisId),
    );
    return VoiceAnalysis.fromJson(data);
  }

  Future<List<Map<String, dynamic>>> confirmActions(
    String analysisId,
    List<Map<String, dynamic>> actions,
    VoiceAnalysis analysis,
  ) async {
    var current = analysis;
    final selectedIds = <String>[];
    for (final edit in actions) {
      final index = edit['actionIndex'] as int;
      if (index < 0 || index >= current.actionDrafts.length) {
        throw StateError('Voice action is no longer available.');
      }
      final draft = current.actionDrafts[index];
      selectedIds.add(draft.id);
      final data = await _api.put<Map<String, dynamic>>(
        ApiEndpoints.voiceDraft(analysisId, draft.id),
        data: {
          'targetId': edit['targetId'] ?? draft.targetEntityId,
          'payload': edit['payload'] ?? draft.extractedPayload,
          'selectedForExecution': true,
          'rowVersion': current.rowVersion,
        },
      );
      current = VoiceAnalysis.fromJson(data);
    }
    final confirmedData = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.confirmVoiceCommand(analysisId),
      data: {
        'selectedDraftIds': selectedIds,
        'rowVersion': current.rowVersion,
        'detailedConfirmation': current.actionDrafts.any(
          (draft) =>
              selectedIds.contains(draft.id) && draft.riskLevel == 'HIGH',
        ),
      },
    );
    current = VoiceAnalysis.fromJson(confirmedData);
    final executedData = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.executeVoiceCommand(analysisId),
      data: {'rowVersion': current.rowVersion},
    );
    current = VoiceAnalysis.fromJson(executedData);
    return current.actionResults;
  }

  Future<VoiceAnalysis> answerClarification({
    required VoiceAnalysis analysis,
    required String clarificationId,
    required String answer,
  }) async {
    final data = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.voiceClarifications(analysis.id),
      data: {'clarificationId': clarificationId, 'answerText': answer},
    );
    return VoiceAnalysis.fromJson(data);
  }

  Future<VoiceTranscription> transcribe({
    required String projectId,
    required String filePath,
    ProgressCallback? onSendProgress,
  }) async {
    final filename = filePath.split(RegExp(r'[/\\]')).last;
    final form = FormData.fromMap({
      'project_id': projectId,
      'audio': await MultipartFile.fromFile(
        filePath,
        filename: filename,
        contentType: DioMediaType.parse('audio/mp4'),
      ),
    });
    final data = await _api.upload<Map<String, dynamic>>(
      ApiEndpoints.aiTranscribe,
      form,
      onSendProgress: onSendProgress,
    );
    return VoiceTranscription(
      transcript: data['transcript'] as String? ?? '',
      language: data['language'] as String? ?? 'auto',
      model: data['model'] as String? ?? '',
    );
  }

  Future<VoiceIntentProposal> analyze({
    required String projectId,
    required String transcript,
  }) async {
    final data = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.aiAnalyzeCommand,
      data: {'projectId': projectId, 'transcript': transcript},
    );
    final action = data['proposedAction'] as Map<String, dynamic>? ?? const {};
    final validation = data['validation'] as Map<String, dynamic>? ?? const {};
    return VoiceIntentProposal(
      intentType: _intent('${action['actionType'] ?? 'unknown'}'),
      projectId: '${action['projectId'] ?? projectId}',
      taskId: action['taskId']?.toString(),
      confidence: (action['confidence'] as num?)?.toDouble(),
      requiresConfirmation: action['requiresConfirmation'] as bool? ?? true,
      detectedEntities: {
        if (action['taskReference'] != null)
          'taskReference': action['taskReference'],
        if (action['issueTitle'] != null) 'issueTitle': action['issueTitle'],
        if (action['requiresClarification'] == true)
          'requiresClarification': true,
      },
      proposedChanges: {
        if (action['progressPercentage'] != null)
          'progressPercentage': action['progressPercentage'],
        if (action['status'] != null) 'status': action['status'],
        if (action['description'] != null) 'description': action['description'],
      },
      warnings: (validation['warnings'] as List? ?? const [])
          .map((value) => '$value')
          .toList(),
      validationErrors: (validation['errors'] as List? ?? const [])
          .map((value) => '$value')
          .toList(),
    );
  }

  VoiceIntentType _intent(String value) => VoiceIntentType.values.firstWhere(
    (intent) => intent.value == value,
    orElse: () => VoiceIntentType.unknown,
  );
}
