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
  });

  /// The action type, e.g. `SUBMIT_TASK_FOR_REVIEW`.
  final String type;

  final bool succeeded;

  /// The backend's status token, e.g. `REJECTED`, `INVALID`.
  final String status;

  /// The backend's own English message. Never shown raw — see [reason].
  final String message;

  factory VoiceActionOutcome.fromJson(Map<String, dynamic> json) =>
      VoiceActionOutcome(
        type: '${json['type'] ?? ''}',
        succeeded: json['success'] == true,
        status: '${json['status'] ?? ''}',
        message: '${json['message'] ?? ''}',
      );

  /// The action's name in the user's language.
  String label(AppL10n l10n) => l10n.voiceIntentLabel(type);

  /// Why it failed, in the user's language.
  ///
  /// The backend's `message` is English prose written for developers (and
  /// sometimes names internal field names), so it is classified rather than
  /// printed. A recognised class gets a sentence a site engineer can act on;
  /// anything else gets the generic one. Raw backend text and stack traces
  /// never reach the screen.
  String? reason(AppL10n l10n) {
    if (succeeded) return null;
    final text = message.toLowerCase();
    if (text.contains('unsupported fields')) {
      return l10n.voiceOutcomeRejectedFields;
    }
    return l10n.voiceOutcomeGenericFailure;
  }
}
