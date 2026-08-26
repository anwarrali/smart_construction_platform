import '../../l10n/app_localizations.dart';
import '../../core/l10n/l10n_labels.dart';

/// What actually happened when the user confirmed a set of voice actions.
///
/// This exists because the screen used to derive its result state from
/// "did the request come back without throwing", and then showed a green
/// verified shield reading "Action completed" — while the backend had
/// rejected every action and written nothing. A user went looking for a
/// notification on a colleague's account that was never sent.
///
/// Only the backend's own per-action `success` flag counts. Receiving a
/// response, having an analysis, or having proposed actions are all
/// explicitly *not* evidence of execution.
enum VoiceOutcome {
  /// Every confirmed action executed.
  success,

  /// Some executed, some did not.
  partial,

  /// Nothing executed.
  failure,

  /// There was nothing to execute — the note was understood but required no
  /// system change. Deliberately distinct from [success]: nothing happened,
  /// and pretending otherwise is the bug this file exists to prevent.
  nothing;

  static VoiceOutcome of(Iterable<VoiceActionOutcome> results) {
    final list = results.toList();
    if (list.isEmpty) return VoiceOutcome.nothing;
    final succeeded = list.where((item) => item.succeeded).length;
    if (succeeded == 0) return VoiceOutcome.failure;
    if (succeeded == list.length) return VoiceOutcome.success;
    return VoiceOutcome.partial;
  }

  /// Whether the affirmative (green, verified) treatment may be used.
  /// True only for [success] — never for partial, failure or nothing.
  bool get isAffirmative => this == VoiceOutcome.success;

  String title(AppL10n l10n) => switch (this) {
    VoiceOutcome.success => l10n.voiceOutcomeSuccessTitle,
    VoiceOutcome.partial => l10n.voiceOutcomePartialTitle,
    VoiceOutcome.failure => l10n.voiceOutcomeFailureTitle,
    VoiceOutcome.nothing => l10n.voiceOutcomeNothingTitle,
  };
}

/// One action's result, as reported by the backend.
class VoiceActionOutcome {
  const VoiceActionOutcome({
    required this.type,
    required this.succeeded,
    required this.status,
    required this.message,
    this.userMessage,
    this.errorCode,
  });

  /// The action type, e.g. `SUBMIT_TASK_FOR_REVIEW`.
  final String type;

  final bool succeeded;

  /// The backend's status token, e.g. `REJECTED`, `INVALID`.
  final String status;

  /// The backend's own English message. Never shown raw — see [reason].
  final String message;

  /// What the backend says to *the person*, already in the language they
  /// spoke: "ما عندك صلاحية تعمل هذا التعديل", "لمين بدك أبعت الرسالة؟". The
  /// server classifies the failure and phrases it — see
  /// `app/services/voice_action_errors.py` — because only the server knows
  /// which of a dozen rules refused, and the client used to flatten all of
  /// them into one "something went wrong".
  final String? userMessage;

  /// The stable classification behind [userMessage], for logs and analytics.
  /// Never displayed.
  final String? errorCode;

  factory VoiceActionOutcome.fromJson(Map<String, dynamic> json) =>
      VoiceActionOutcome(
        type: '${json['type'] ?? ''}',
        succeeded: json['success'] == true,
        status: '${json['status'] ?? ''}',
        message: '${json['message'] ?? ''}',
        userMessage: (json['userMessage'] as String?)?.trim().isEmpty ?? true
            ? null
            : json['userMessage'] as String?,
        errorCode: json['errorCode'] as String?,
      );

  /// The action's name in the user's language.
  String label(AppL10n l10n) => l10n.voiceIntentLabel(type);

  /// Why it failed, in the user's language.
  ///
  /// The server's explanation is preferred whenever there is one: it knows
  /// which rule refused and says so — "ما عندك صلاحية تعمل هذا التعديل",
  /// "لمين بدك أبعت الرسالة؟" — where this client can only tell that
  /// *something* refused. The old local classification stays as the fallback
  /// for an older backend, and the raw `message` is still never shown.
  String? reason(AppL10n l10n) {
    if (succeeded) return null;
    if (userMessage != null) return userMessage;
    final text = message.toLowerCase();
    if (text.contains('unsupported fields')) {
      return l10n.voiceOutcomeRejectedFields;
    }
    return l10n.voiceOutcomeGenericFailure;
  }

  /// What happened, for an action that did succeed.
  ///
  /// Only ever populated by the server after the operation returned, which is
  /// what keeps "تم إرسال الرسالة" from ever appearing for a message that was
  /// not sent.
  String? get outcomeText => succeeded ? userMessage : null;
}
