enum VoiceDraftStatus {
  idle,
  recording,
  paused,
  recorded,
  uploading,
  transcribing,
  ready,
  error,
}

class VoiceTranscription {
  const VoiceTranscription({
    required this.transcript,
    required this.language,
    required this.model,
  });

  final String transcript;
  final String language;
  final String model;
}

enum VoiceIntentType {
  updateTaskProgress('update_task_progress'),
  addTaskComment('add_task_comment'),
  addWorkUpdate('add_work_update'),
  reportBlocker('report_blocker'),
  createIssue('create_issue'),
  createSiteReportEntry('create_site_report_entry'),
  submitForReview('submit_for_review'),
  requestTaskSummary('request_task_summary'),
  unknown('unknown');

  const VoiceIntentType(this.value);
  final String value;
}

class VoiceDraft {
  const VoiceDraft({
    required this.id,
    required this.projectId,
    required this.status,
    required this.createdAt,
    this.localFilePath,
    this.taskId,
    this.transcription,
    this.duration = Duration.zero,
    this.uploadedAt,
  });
  final String id;
  final String? localFilePath;
  final Duration duration;
  final String projectId;
  final String? taskId;
  final String? transcription;
  final VoiceDraftStatus status;
  final DateTime createdAt;
  final DateTime? uploadedAt;
}

class VoiceIntentProposal {
  const VoiceIntentProposal({
    required this.intentType,
    required this.projectId,
    required this.detectedEntities,
    required this.proposedChanges,
    this.taskId,
    this.confidence,
    this.warnings = const [],
    this.validationErrors = const [],
    this.requiresConfirmation = true,
  });
  final VoiceIntentType intentType;
  final String projectId;
  final String? taskId;
  final Map<String, dynamic> detectedEntities;
  final Map<String, dynamic> proposedChanges;
  final double? confidence;
  final List<String> warnings;
  final List<String> validationErrors;
  final bool requiresConfirmation;
}

class VoiceSuggestedAction {
  VoiceSuggestedAction({
    required this.type,
    required this.reason,
    required this.confidence,
    required this.payload,
    this.targetId,
  });

  final String type;
  final String reason;
  final double confidence;
  final String? targetId;
  final Map<String, dynamic> payload;

  factory VoiceSuggestedAction.fromJson(Map<String, dynamic> json) =>
      VoiceSuggestedAction(
        type: '${json['type'] ?? ''}',
        reason: '${json['reason'] ?? ''}',
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        targetId: json['targetId']?.toString(),
        payload: Map<String, dynamic>.from(json['payload'] as Map? ?? const {}),
      );
}

class VoiceActionDraftItem {
  VoiceActionDraftItem({
    required this.id,
    required this.actionType,
    required this.extractedPayload,
    required this.confidence,
    this.targetEntityId,
    this.userEditedPayload,
    this.missingFields = const [],
    this.warnings = const [],
    this.riskLevel = 'LOW',
    this.requiredEvidence = const [],
  });

  final String id;
  final String actionType;
  final String? targetEntityId;
  final Map<String, dynamic> extractedPayload;
  final Map<String, dynamic>? userEditedPayload;
  final double confidence;
  final List<String> missingFields;
  final List<String> warnings;
  final String riskLevel;
  final List<String> requiredEvidence;

  factory VoiceActionDraftItem.fromJson(Map<String, dynamic> json) =>
      VoiceActionDraftItem(
        id: '${json['id']}',
        actionType: '${json['actionType'] ?? ''}',
        targetEntityId: json['targetEntityId']?.toString(),
        extractedPayload: Map<String, dynamic>.from(
          json['extractedPayload'] as Map? ?? const {},
        ),
        userEditedPayload: json['userEditedPayload'] is Map
            ? Map<String, dynamic>.from(json['userEditedPayload'] as Map)
            : null,
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
        missingFields: (json['missingFields'] as List? ?? const [])
            .map((value) => '$value')
            .toList(),
        warnings: (json['warnings'] as List? ?? const [])
            .map((value) => '$value')
            .toList(),
        riskLevel: '${json['riskLevel'] ?? 'LOW'}',
        requiredEvidence: (json['requiredEvidence'] as List? ?? const [])
            .map((value) => '$value')
            .toList(),
      );
}

class VoiceClarificationItem {
  VoiceClarificationItem({
    required this.id,
    required this.questionAr,
    required this.questionEn,
    required this.expectedAnswerType,
    this.options = const [],
  });
  final String id;
  final String questionAr;
  final String questionEn;
  final String expectedAnswerType;
  final List<Map<String, dynamic>> options;

  factory VoiceClarificationItem.fromJson(Map<String, dynamic> json) =>
      VoiceClarificationItem(
        id: '${json['id']}',
        questionAr: '${json['questionAr'] ?? ''}',
        questionEn: '${json['questionEn'] ?? ''}',
        expectedAnswerType: '${json['expectedAnswerType'] ?? 'TEXT'}',
        options: (json['options'] as List? ?? const [])
            .map((value) => Map<String, dynamic>.from(value as Map))
            .toList(),
      );
}

class ConstructionVoiceResult {
  ConstructionVoiceResult({
    required this.summary,
    required this.detectedTask,
    required this.progress,
    required this.discipline,
    required this.location,
    required this.workCompleted,
    required this.problems,
    required this.materials,
    required this.suggestedActions,
  });

  final String summary;
  final Map<String, dynamic> detectedTask;
  final Map<String, dynamic> progress;
  final Map<String, dynamic> discipline;
  final Map<String, dynamic> location;
  final List<String> workCompleted;
  final List<Map<String, dynamic>> problems;
  final List<Map<String, dynamic>> materials;
  final List<VoiceSuggestedAction> suggestedActions;

  factory ConstructionVoiceResult.fromJson(
    Map<String, dynamic> json,
  ) => ConstructionVoiceResult(
    summary: '${json['summary'] ?? ''}',
    detectedTask: Map<String, dynamic>.from(
      json['detectedTask'] as Map? ?? const {},
    ),
    progress: Map<String, dynamic>.from(json['progress'] as Map? ?? const {}),
    discipline: Map<String, dynamic>.from(
      json['discipline'] as Map? ?? const {},
    ),
    location: Map<String, dynamic>.from(json['location'] as Map? ?? const {}),
    workCompleted: (json['workCompleted'] as List? ?? const [])
        .map((value) => '$value')
        .toList(),
    problems: (json['problems'] as List? ?? const [])
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList(),
    materials: (json['materials'] as List? ?? const [])
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList(),
    suggestedActions: (json['suggestedActions'] as List? ?? const [])
        .map(
          (value) => VoiceSuggestedAction.fromJson(
            Map<String, dynamic>.from(value as Map),
          ),
        )
        .toList(),
  );
}

class VoiceAnalysis {
  VoiceAnalysis({
    required this.id,
    required this.projectId,
    required this.status,
    required this.confirmationStatus,
    required this.retryCount,
    this.taskId,
    this.fieldSubmissionId,
    this.rawTranscript,
    this.detectedLanguage,
    this.errorDetail,
    this.result,
    this.actionResults = const [],
    this.actionDrafts = const [],
    this.clarifications = const [],
    this.rowVersion = 1,
  });

  final String id;
  final String projectId;
  final String? taskId;
  final String? fieldSubmissionId;
  final String status;
  final String confirmationStatus;
  final int retryCount;
  final String? rawTranscript;
  final String? detectedLanguage;
  final String? errorDetail;
  final ConstructionVoiceResult? result;
  final List<Map<String, dynamic>> actionResults;
  final List<VoiceActionDraftItem> actionDrafts;
  final List<VoiceClarificationItem> clarifications;
  final int rowVersion;

  bool get completed =>
      status == 'COMPLETED' || status == 'READY_FOR_CONFIRMATION';
  bool get needsClarification => status == 'NEEDS_CLARIFICATION';
  bool get failed => status == 'FAILED';

  factory VoiceAnalysis.fromJson(Map<String, dynamic> json) => VoiceAnalysis(
    id: '${json['id']}',
    projectId: '${json['projectId']}',
    taskId: json['taskId']?.toString(),
    fieldSubmissionId: json['fieldSubmissionId']?.toString(),
    status: '${json['status'] ?? ''}',
    confirmationStatus: '${json['confirmationStatus'] ?? 'PENDING'}',
    retryCount: json['retryCount'] as int? ?? 0,
    rowVersion: json['rowVersion'] as int? ?? 1,
    rawTranscript: json['rawTranscript'] as String?,
    detectedLanguage: json['detectedLanguage'] as String?,
    errorDetail: json['errorDetail'] as String?,
    result: json['structuredResult'] is Map
        ? ConstructionVoiceResult.fromJson(
            Map<String, dynamic>.from(json['structuredResult'] as Map),
          )
        : null,
    actionResults: (json['actionResults'] as List? ?? const [])
        .map((value) => Map<String, dynamic>.from(value as Map))
        .toList(),
    actionDrafts: (json['actionDrafts'] as List? ?? const [])
        .map(
          (value) => VoiceActionDraftItem.fromJson(
            Map<String, dynamic>.from(value as Map),
          ),
        )
        .toList(),
    clarifications: (json['clarifications'] as List? ?? const [])
        .where((value) => (value as Map)['answerText'] == null)
        .map(
          (value) => VoiceClarificationItem.fromJson(
            Map<String, dynamic>.from(value as Map),
          ),
        )
        .toList(),
  );
}
