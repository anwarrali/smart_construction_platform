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

/// One reviewed action, addressed by the identity the server assigned it.
///
/// Deliberately carries no index. An index is a position in a list, and the
/// pipeline has three lists (the model's suggestions, the server's drafts,
/// the execution results) that are only *usually* in the same order.
class VoiceDraftConfirmation {
  const VoiceDraftConfirmation({
    required this.draftId,
    this.targetId,
    this.payload,
  });

  final String draftId;
  final String? targetId;
  final Map<String, dynamic>? payload;
}

class VoiceActionDraftItem {
  VoiceActionDraftItem({
    required this.id,
    required this.sequence,
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

  /// The draft's own identifier — the only thing that identifies an action
  /// across the review/confirm/execute round trip. Positions must never be
  /// used: the server's draft list and the model's `suggestedActions` are two
  /// different lists, and binding one to the other by position is exactly
  /// what wrote a review payload onto a progress action.
  final String id;

  /// Position in the analysis's `suggestedActions`, supplied by the server.
  /// Used only to pair a draft with its human-readable reason.
  final int sequence;

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
        sequence: json['sequence'] as int? ?? 0,
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

  /// The question in one language — the one that was spoken.
  ///
  /// Both halves used to be shown, one under the other, which is a translation
  /// exercise rather than a conversation. The backend writes the naturally
  /// phrased question into the half matching the speaker's language and leaves
  /// the plain template in the other, so showing one is showing the good one.
  String questionFor(String languageCode) {
    final arabic = languageCode.startsWith('ar');
    final preferred = arabic ? questionAr : questionEn;
    return preferred.isNotEmpty ? preferred : (arabic ? questionEn : questionAr);
  }

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

/// A direct answer to a spoken question.
///
/// Present only when the backend decided the utterance was a question and could
/// answer it from project data. Its existence is what tells the UI to show a
/// sentence instead of a confirmation card: an answer proposes nothing, so
/// there is nothing to confirm or cancel.
class VoiceAnswer {
  const VoiceAnswer({
    required this.topic,
    required this.textEn,
    required this.textAr,
    this.text = '',
    this.language = '',
    this.data = const {},
  });

  final String topic;
  final String textEn;
  final String textAr;

  /// The sentence the backend actually composed for this question, already in
  /// the language the person spoke. Preferred over the two template fields,
  /// which remain as the fallback for an older backend or a provider outage.
  final String text;

  /// The language that sentence is written in — the language of the *speech*,
  /// not of the interface. Someone working with an English UI who asks a
  /// question in Arabic is answered in Arabic.
  final String language;
  final Map<String, dynamic> data;

  /// True when there is a sentence to show. A question the backend understood
  /// but could not pin to one task arrives with every text empty and a
  /// clarification alongside it.
  bool get hasText => text.isNotEmpty || textEn.isNotEmpty || textAr.isNotEmpty;

  /// What to display. `languageCode` is the interface language and is used only
  /// when the backend supplied no composed sentence of its own.
  String textFor(String languageCode) {
    if (text.isNotEmpty) return text;
    final arabic = (language.isNotEmpty ? language : languageCode).startsWith(
      'ar',
    );
    final preferred = arabic ? textAr : textEn;
    return preferred.isNotEmpty ? preferred : (arabic ? textEn : textAr);
  }

  factory VoiceAnswer.fromJson(Map<String, dynamic> json) => VoiceAnswer(
    topic: '${json['topic'] ?? ''}',
    textEn: '${json['textEn'] ?? ''}',
    textAr: '${json['textAr'] ?? ''}',
    text: '${json['text'] ?? ''}',
    language: '${json['language'] ?? ''}',
    data: Map<String, dynamic>.from(json['data'] as Map? ?? const {}),
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
    this.answer,
    this.route = 'ACTION',
    this.replyLanguage = '',
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
  final VoiceAnswer? answer;
  /// ANSWER | ACTION | COMMUNICATION | CLARIFICATION, decided by the backend
  /// router. The client renders from this rather than inferring intent from
  /// `status`, which is why the action-review card is no longer the universal
  /// voice result screen.
  final String route;

  /// The language the backend replied in, which is the language that was
  /// spoken. Empty from an older backend, in which case the interface language
  /// decides.
  final String replyLanguage;
  final List<Map<String, dynamic>> actionResults;
  final List<VoiceActionDraftItem> actionDrafts;
  final List<VoiceClarificationItem> clarifications;
  final int rowVersion;

  bool get completed =>
      status == 'COMPLETED' || status == 'READY_FOR_CONFIRMATION';

  bool get isAnswerRoute => route == 'ANSWER';
  bool get isClarificationRoute => route == 'CLARIFICATION';

  /// True when there is a mutation to review. The action-review card renders
  /// on this and nothing else, so a question or an unclassified utterance can
  /// never raise "Select a task / No safe executable action was suggested".
  bool get hasProposal => actionDrafts.isNotEmpty;

  /// True when every proposed action is fully specified.
  ///
  /// A half-specified proposal is not something a person can review — a card
  /// reading "Task: unknown, Progress: 50%" asks them to confirm a blank. While
  /// anything is outstanding the assistant asks about it in words instead, and
  /// the review card waits.
  bool get hasCompleteProposal =>
      actionDrafts.isNotEmpty &&
      actionDrafts.every((draft) => draft.missingFields.isEmpty);


  /// True when the reply is information rather than a proposal.
  ///
  /// An answered question also reaches COMPLETED — it is a terminal state —
  /// but it proposes nothing, so the screen shows the sentence and suppresses
  /// the confirmation card. `completed` deliberately keeps its original
  /// meaning of "terminal and reviewable"; deciding what to *render* belongs to
  /// the screen, not to this predicate.
  bool get answered => answer?.hasText == true;
  bool get needsClarification => status == 'NEEDS_CLARIFICATION';
  bool get failed => status == 'FAILED';

  /// True when the assistant is waiting on an answer it can still show.
  ///
  /// `needsClarification` alone is not that: once the question has been
  /// answered it stays in that status while the backend works out what the
  /// answer meant, and `clarifications` — which the parser trims to the
  /// *unanswered* ones — is empty. Gating the other cards on the status rather
  /// than on this is what left the screen with a question card that had gone,
  /// an answer card suppressed, and nothing in between.
  bool get isAsking => clarifications.isNotEmpty;

  /// True when there is nothing at all to render.
  ///
  /// Should never happen — the backend guarantees a question, a proposal or a
  /// sentence on every path — but a client that silently shows nothing is
  /// indistinguishable from a broken one, so the screen checks and says so.
  bool get hasNothingToShow =>
      !isAsking && !hasCompleteProposal && !answered && !failed;

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
    // The backend writes the answer into `structuredResult` rather than a
    // column of its own; it is derived output belonging to one analysis.
    answer:
        json['structuredResult'] is Map &&
            (json['structuredResult'] as Map)['answer'] is Map
        ? VoiceAnswer.fromJson(
            Map<String, dynamic>.from(
              (json['structuredResult'] as Map)['answer'] as Map,
            ),
          )
        : null,
    route:
        '${(json['providerMetadata'] as Map?)?['route'] ?? 'ACTION'}',
    replyLanguage:
        '${(json['providerMetadata'] as Map?)?['replyLanguage'] ?? ''}',
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
