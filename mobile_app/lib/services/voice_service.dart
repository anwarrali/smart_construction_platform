import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/voice_draft.dart';
import '../features/voice_command/voice_errors.dart';

/// The container the browser actually produced, and how to declare it.
///
/// The backend validates an upload three ways — extension, MIME type, and the
/// leading bytes — and rejects any recording where they disagree. On mobile all
/// three are known up front because the app chose the file name. On web the
/// *browser* chooses the container: Chrome honours `aacLc` and returns MP4,
/// Firefox supports no AAC container and falls back to its WebM default. So the
/// only safe declaration is one read back off the bytes themselves.
class RecordedAudioFormat {
  const RecordedAudioFormat(this.extension, this.mimeType);

  final String extension;
  final String mimeType;

  /// Mirrors the backend's `_matches_audio_signature` check, so a recording
  /// this method labels can never fail that check.
  static RecordedAudioFormat detect(Uint8List bytes) {
    bool matches(List<int> magic, [int offset = 0]) {
      if (bytes.length < offset + magic.length) return false;
      for (var index = 0; index < magic.length; index++) {
        if (bytes[offset + index] != magic[index]) return false;
      }
      return true;
    }

    // EBML header — WebM/Matroska.
    if (matches(const [0x1A, 0x45, 0xDF, 0xA3])) {
      return const RecordedAudioFormat('webm', 'audio/webm');
    }
    // 'ftyp' box at offset 4 — MP4/M4A.
    if (matches(const [0x66, 0x74, 0x79, 0x70], 4)) {
      return const RecordedAudioFormat('m4a', 'audio/mp4');
    }
    // 'RIFF' .... 'WAVE'
    if (matches(const [0x52, 0x49, 0x46, 0x46]) &&
        matches(const [0x57, 0x41, 0x56, 0x45], 8)) {
      return const RecordedAudioFormat('wav', 'audio/wav');
    }
    // 'ID3' tag, or an MPEG frame sync.
    if (matches(const [0x49, 0x44, 0x33]) ||
        (bytes.length >= 2 && bytes[0] == 0xFF && (bytes[1] & 0xE0) == 0xE0)) {
      return const RecordedAudioFormat('mp3', 'audio/mpeg');
    }
    // Unrecognised: claim WebM, the near-universal `MediaRecorder` default.
    // A wrong guess is rejected by the backend's signature check rather than
    // stored, which is the failure mode to prefer.
    return const RecordedAudioFormat('webm', 'audio/webm');
  }
}

/// Build the multipart audio part for whichever platform recorded it.
///
/// On web `source` is a `blob:` URL rather than a path, and
/// `MultipartFile.fromFile` is a hard `UnsupportedError` there —
/// `dio_web_adapter` replaces it with a thrower reading "MultipartFile is only
/// supported where dart:io is available." Reading the blob back over XHR (what
/// dio's browser adapter uses anyway) and sending bytes is the way across.
Future<MultipartFile> _recordedAudioPart(String source) async {
  if (!kIsWeb) {
    return MultipartFile.fromFile(
      source,
      filename: source.split(RegExp(r'[/\\]')).last,
      contentType: DioMediaType.parse('audio/mp4'),
    );
  }
  // A bare Dio: the blob is same-origin browser memory, so it needs none of
  // the API client's base URL, auth header, or interceptors.
  final response = await Dio().get<List<int>>(
    source,
    options: Options(responseType: ResponseType.bytes),
  );
  final bytes = Uint8List.fromList(response.data ?? const <int>[]);
  final format = RecordedAudioFormat.detect(bytes);
  return MultipartFile.fromBytes(
    bytes,
    filename: 'voice.${format.extension}',
    contentType: DioMediaType.parse(format.mimeType),
  );
}

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
    final form = FormData.fromMap({
      'project_id': projectId,
      if (taskId != null) 'task_id': taskId,
      'duration_seconds': duration.inSeconds,
      'idempotency_key': requestId,
      'audio': await _recordedAudioPart(filePath),
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
    final form = FormData.fromMap({
      'project_id': projectId,
      'audio': await _recordedAudioPart(filePath),
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
