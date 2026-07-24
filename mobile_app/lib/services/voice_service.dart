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
    String? taskId,
    ProgressCallback? onSendProgress,
  }) async {
    final filename = filePath.split(RegExp(r'[/\\]')).last;
    final form = FormData.fromMap({
      'project_id': projectId,
      if (taskId != null) 'task_id': taskId,
      'duration_seconds': duration.inSeconds,
      'audio': await MultipartFile.fromFile(
        filePath,
        filename: filename,
        contentType: DioMediaType.parse('audio/mp4'),
      ),
    });
    final data = await _api.upload<Map<String, dynamic>>(
      ApiEndpoints.voiceAnalyses,
      form,
      onSendProgress: onSendProgress,
    );
    return VoiceAnalysis.fromJson(data);
  }

  Future<VoiceAnalysis> retryAnalysis(String analysisId) async {
    final data = await _api.post<Map<String, dynamic>>(
      ApiEndpoints.retryVoiceAnalysis(analysisId),
    );
    return VoiceAnalysis.fromJson(data);
  }

  Future<List<Map<String, dynamic>>> confirmActions(
    String analysisId,
    List<Map<String, dynamic>> actions,
  ) async {
    final data = await _api.post<List<dynamic>>(
      ApiEndpoints.confirmVoiceAnalysis(analysisId),
      data: {'actions': actions},
    );
    return data
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList();
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
