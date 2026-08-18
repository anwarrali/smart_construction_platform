import 'package:flutter/widgets.dart';

import '../../l10n/app_localizations.dart';
import '../../features/voice_command/voice_errors.dart';
import '../network/network_exceptions.dart';

/// Shorthand for the generated lookup, so screens read
/// `context.l10n.tasksTitle` rather than `AppL10n.of(context).tasksTitle`.
extension L10nContext on BuildContext {
  AppL10n get l10n => AppL10n.of(this);
}

/// Translations for values that arrive from the API as bare enum strings.
///
/// The generated `AppL10n` exposes static getters, not a map, so something
/// has to turn `"under_review"` into a sentence. Doing it once here is what
/// keeps the rule "no language conditionals in widgets" true: a screen asks
/// for `l10n.statusLabel(task.status)` and never knows which language it is
/// in. Unrecognised values fall back to the raw value with underscores
/// removed — the honest answer for a status the app has no wording for yet,
/// and the same thing the web's `defaultValue` does.
extension L10nLabels on AppL10n {
  String _humanise(String? value) =>
      (value ?? '').replaceAll('_', ' ').trim();

  /// Task, issue, project, review, design-change and site-report statuses.
  ///
  /// One table for all of them because the values do not collide and a
  /// caller should not have to know which entity a status came from.
  String statusLabel(String? value) =>
      switch (value?.toLowerCase().trim()) {
        'backlog' => statusBacklog,
        'todo' => statusTodo,
        'in_progress' => statusInProgress,
        'under_review' => statusUnderReview,
        'rework_required' => statusReworkRequired,
        'done' => statusDone,
        'blocked' => statusBlocked,
        'cancelled' => statusCancelled,
        'open' => statusOpen,
        'resolved' => statusResolved,
        'closed' => statusClosed,
        'pending' => statusPending,
        'in_review' => statusInReview,
        'approved' => statusApproved,
        'rejected' => statusRejected,
        'clarification_requested' => statusClarificationRequested,
        'draft' => statusDraft,
        'submitted' => statusSubmitted,
        'proposed' => statusProposed,
        'implemented' => statusImplemented,
        'planning' => statusPlanning,
        'active' => statusActive,
        'on_hold' => statusOnHold,
        'delayed' => statusDelayed,
        'completed' => statusCompleted,
        'verified' => statusVerified,
        'on_track' => statusOnTrack,
        'at_risk' => statusAtRisk,
        _ => _humanise(value),
      };

  /// Task/issue priority and severity, plus the notification priorities from
  /// the Smart Notification system.
  String priorityLabel(String? value) =>
      switch (value?.toLowerCase().trim()) {
        'low' => priorityLow,
        'medium' => priorityMedium,
        'high' => priorityHigh,
        'critical' => priorityCritical,
        'normal' => priorityNormal,
        'important' => priorityImportant,
        'info' => priorityInfo,
        _ => _humanise(value),
      };

  String disciplineLabel(String? value) =>
      switch (value?.toLowerCase().trim()) {
        'civil' => disciplineCivil,
        'architectural' || 'architecture' => disciplineArchitectural,
        'electrical' => disciplineElectrical,
        'mechanical' => disciplineMechanical,
        'structural' => disciplineStructural,
        'plumbing' => disciplinePlumbing,
        'hvac' || 'mechanical_hvac' => disciplineHvac,
        'fire_protection' => disciplineFireProtection,
        'general' => disciplineGeneral,
        'unclassified' => disciplineUnclassified,
        null || '' => disciplineUnassigned,
        _ => _humanise(value),
      };

  /// The voice flow's own failures.
  String describeVoiceFailure(VoiceFailure failure) => switch (failure) {
    VoiceFailure.microphonePermission => voiceMicPermissionRequired,
    VoiceFailure.recordBeforeTranscribing => voiceRecordBeforeTranscribe,
    VoiceFailure.recordBeforeAnalysis => voiceRecordBeforeAnalysis,
    VoiceFailure.nothingToRetry => voiceNoAnalysisRetry,
    VoiceFailure.nothingToConfirm => voiceNoAnalysisConfirm,
    VoiceFailure.nothingToClarify => voiceNoAnalysisClarify,
    VoiceFailure.actionUnavailable => voiceActionUnavailable,
  };

  /// The intents the voice analyser can propose. Unknown intents are
  /// humanised rather than hidden: a new server-side intent should still be
  /// legible while its translation is being added.
  String voiceIntentLabel(String intent) => switch (intent.toUpperCase()) {
    'UPDATE_TASK_PROGRESS' => voiceIntentUpdateProgress,
    'REPORT_ISSUE' => voiceIntentReportIssue,
    'SEND_MESSAGE' => voiceIntentSendMessage,
    'SUBMIT_SITE_REPORT' => voiceIntentSubmitReport,
    'REQUEST_CLARIFICATION' => voiceIntentRequestClarification,
    _ => _humanise(intent),
  };

  /// The action-centre counters, keyed by the field names
  /// `GET /collaboration/my-action-center` returns.
  String actionCountLabel(String key) => switch (key) {
    'needsMyResponse' => collabNeedsMyResponse,
    'ownerRequests' => collabOwnerRequests,
    'requiresActionNotifications' => collabRequiresActionNotifications,
    'upcomingSiteVisits' => collabUpcomingSiteVisits,
    'aiAlertsRequiringReview' => collabAiAlertsRequiringReview,
    'tasksUnderReview' => collabTasksUnderReview,
    _ => _humanise(key),
  };

  String visitTypeLabel(String? value) => switch (value?.toUpperCase()) {
    'ROUTINE_INSPECTION' => collabVisitTypeRoutine,
    'QUALITY_AUDIT' => collabVisitTypeQuality,
    'SAFETY_INSPECTION' => collabVisitTypeSafety,
    'PROGRESS_REVIEW' => collabVisitTypeProgress,
    _ => _humanise(value),
  };

  /// Which face of the work a field photo shows. Like the issue categories,
  /// the stored value is the upper-case code and only the display changes.
  String photoViewLabel(String value) => switch (value.toUpperCase()) {
    'FRONT' => viewFront,
    'BACK' => viewBack,
    'LEFT' => viewLeft,
    'RIGHT' => viewRight,
    'TOP' => viewTop,
    'DETAIL' => viewDetail,
    'OTHER' => viewOther,
    _ => value.toLowerCase(),
  };

  /// Audit-log actions, as they appear in a project's activity feed.
  ///
  /// The feed carries the raw action identifier — `progress_updated`,
  /// `reminders_dispatched`, `site_report_verified` — and a device pass caught
  /// those being shown to a site manager verbatim. Humanising the underscores
  /// was not a fix: `reminders dispatched` is still a database word.
  ///
  /// The backend defines roughly a hundred actions, most of them
  /// administrative and none of them ever seen by a field user. This table
  /// covers the ones that actually reach a project feed; **anything else
  /// resolves to a translated generic sentence rather than to the identifier**,
  /// which is the whole point — a person must never be shown an internal name.
  /// The actor and the timestamp beside it carry the specifics.
  String activityLabel(String? value) {
    // Some endpoints send an already-prose action ("Evidence verified")
    // rather than a code, so normalise both shapes into one key.
    final key = (value ?? '')
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'\s+'), '_');
    return switch (key) {
      'task_created' || 'created_from_ifc_suggestion' ||
      'task_created_from_ai_insight' => activityTaskCreated,
      'task_started' => activityTaskStarted,
      'task_resumed' => activityTaskResumed,
      'progress_updated' => activityProgressUpdated,
      'submitted' => activitySubmitted,
      'approved' => activityApproved,
      'review_started' => activityReviewStarted,
      'rework_requested' => activityReworkRequested,
      'rework_started' => activityReworkStarted,
      'clarification_requested' => activityClarificationRequested,
      'clarification_responded' => activityClarificationResponded,
      'comment_added' => activityCommentAdded,
      'work_update_added' => activityWorkUpdateAdded,
      'blocker_reported' => activityBlockerReported,
      'document_uploaded' => activityDocumentUploaded,
      'attachment_uploaded' => activityAttachmentUploaded,
      'site_report_verified' => activitySiteReportVerified,
      'site_visit_scheduled' => activitySiteVisitScheduled,
      'owner_request_submitted' => activityOwnerRequestSubmitted,
      'schedule_recalculated' ||
      'critical_path_calculated' => activityScheduleRecalculated,
      'reminders_dispatched' => activityRemindersDispatched,
      'project_member_assigned' => activityMemberAssigned,
      'ifc_version_uploaded' ||
      'ifc_version_activated' => activityModelVersionUploaded,
      'voice_command_executed' ||
      'ai_voice_actions_confirmed' ||
      'voice_evidence_uploaded' => activityVoiceUpdate,
      'evidence_verified' ||
      'field_submission_verified_and_update_applied' =>
        activityEvidenceVerified,
      'evidence_rejected' => activityEvidenceRejected,
      'evidence_submitted' => activityEvidenceSubmitted,
      'created' => activityCreated,
      'updated' => activityUpdated,
      _ => activityGeneric,
    };
  }

  String roleLabel(String? value) => switch (value?.toLowerCase().trim()) {
    'admin' => roleAdmin,
    'owner' => roleOwner,
    'project_manager' => roleProjectManager,
    'engineer' => roleEngineer,
    'consultant' => roleConsultant,
    'worker' => roleWorker,
    _ => _humanise(value),
  };

  /// The five entity types Task 2.1 can share into a conversation.
  String entityLabel(String? value) => switch (value?.toUpperCase().trim()) {
    'ISSUE' => entityIssue,
    'TASK' => entityTask,
    'SITE_REPORT' => entitySiteReport,
    'DESIGN_CHANGE' => entityDesignChange,
    'DOCUMENT' => entityDocument,
    _ => _humanise(value),
  };

  /// Issue categories are keyed by their **English text**, because that text
  /// is the value the API already stores. Translating the display without
  /// touching the stored value is the whole point: an issue raised in an
  /// Arabic session must be indistinguishable, in the database, from one
  /// raised in English.
  String issueCategoryLabel(String value) => switch (value) {
    'Material unavailable' => issueCategoryMaterialUnavailable,
    'Previous task incomplete' => issueCategoryPreviousTaskIncomplete,
    'Drawing unavailable' => issueCategoryDrawingUnavailable,
    'Equipment unavailable' => issueCategoryEquipmentUnavailable,
    'Labor shortage' => issueCategoryLaborShortage,
    'Site access issue' => issueCategorySiteAccess,
    'Consultant clarification required' =>
      issueCategoryConsultantClarification,
    'Technical conflict' => issueCategoryTechnicalConflict,
    'Safety restriction' => issueCategorySafetyRestriction,
    'Other' => issueCategoryOther,
    _ => value,
  };

  /// Turns a thrown error into a sentence the user can act on.
  ///
  /// The server's own `detail` text is deliberately ignored: it is English
  /// prose generated by the backend, so showing it would put untranslated
  /// English in an Arabic UI. Known status codes get a translated sentence
  /// and anything else gets the generic one — Phase 15's rule, and the
  /// reason `NetworkException` keeps `statusCode` as structured data.
  String describeError(Object? error) {
    if (error is VoiceException) return describeVoiceFailure(error.failure);
    if (error is! NetworkException) return errorGeneric;
    return switch (error.failure) {
      NetworkFailure.offline => errorNetwork,
      NetworkFailure.timeout => errorTimeout,
      _ => switch (error.statusCode) {
        401 => errorUnauthorized,
        403 => errorForbidden,
        404 => errorNotFound,
        409 => errorConflict,
        422 => errorValidation,
        _ => errorGeneric,
      },
    };
  }

  /// Sign-in failures, which need their own wording.
  ///
  /// The generic 401 sentence ("You are not signed in") is true but useless
  /// on the sign-in screen itself, and the throttle response is worth saying
  /// out loud so a user who has been locked out knows to wait.
  String describeLoginError(Object? error) {
    if (error is! NetworkException) return errorGeneric;
    return switch (error.failure) {
      NetworkFailure.offline => errorNetwork,
      NetworkFailure.timeout => errorTimeout,
      _ => switch (error.statusCode) {
        401 => loginInvalidCredentials,
        403 => loginAccountDeactivated,
        429 => loginTooManyAttempts,
        _ => errorGeneric,
      },
    };
  }
}
