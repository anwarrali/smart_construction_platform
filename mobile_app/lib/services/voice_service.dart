import 'package:dio/dio.dart';

import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/voice_draft.dart';
import '../features/voice_command/voice_errors.dart';

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

  /// Confirms and executes the chosen actions.
  ///
  /// Every action is addressed by its **draft id**. The previous version took
  /// a positional `actionIndex` into `result.suggestedActions` and used it to
  /// subscript `analysis.actionDrafts` — two different lists — and it
  /// reassigned `current` from each PUT response inside the loop, so the
  /// second iteration indexed a freshly deserialized list. The server ordered
  /// that list by `created_at`, which is identical for every draft of one
  /// analysis, so the order was a tie that Postgres could return differently
  /// once a row had been rewritten.
  ///
  /// The observed result: a `SUBMIT_TASK_FOR_REVIEW` payload was written onto
  /// the `UPDATE_TASK_PROGRESS` draft, which was then rejected for carrying
  /// the other action's fields, while the review draft was never selected and
  /// the consultant was never notified.
  ///
  /// Ids are resolved from the analysis the user actually reviewed, before
  /// anything is mutated, so no later response can change what they refer to.
  Future<List<Map<String, dynamic>>> confirmActions(
    String analysisId,
    List<VoiceDraftConfirmation> actions,
    VoiceAnalysis analysis,
  ) async {
    if (actions.isEmpty) {
      throw const VoiceException(VoiceFailure.nothingToConfirm);
    }
    final known = {for (final draft in analysis.actionDrafts) draft.id: draft};
    // Resolved up front and never recomputed.
    final selectedIds = [for (final action in actions) action.draftId];
    if (selectedIds.any((id) => !known.containsKey(id))) {
      throw const VoiceException(VoiceFailure.actionUnavailable);
    }

    var current = analysis;
    for (final action in actions) {
      final draft = known[action.draftId]!;
      final data = await _api.put<Map<String, dynamic>>(
        // The id, not a position — this is the whole fix.
        ApiEndpoints.voiceDraft(analysisId, draft.id),
        data: {
          'targetId': action.targetId ?? draft.targetEntityId,
          'payload': action.payload ?? draft.extractedPayload,
          'selectedForExecution': true,
          // Only the optimistic-concurrency token is carried forward from
          // the response; the draft list from it is deliberately not used
          // for addressing anything.
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
        // Resolved from the reviewed analysis, so a high-risk action cannot
        // be silently dropped from this check by a reordered response.
        'detailedConfirmation': selectedIds.any(
          (id) => known[id]!.riskLevel == 'HIGH',
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
