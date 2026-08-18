import '../../l10n/app_localizations.dart';
import '../../models/notification_item.dart';

/// Renders a notification's title and body in the active language.
///
/// The Smart Notification system (Task 3) stores a `messageKey` and a
/// parameter map alongside the pre-rendered English `title`/`message`. The
/// web resolves `notification.<messageKey>.title` against its own catalogue;
/// this does exactly the same against the ARB, so a notification reads
/// identically on both clients and no second notification system exists.
///
/// Anything the backend sends without a `messageKey` — or with a key this
/// build does not know — falls back to the server's own text. That text is
/// English, and it is shown as-is rather than guessed at: inventing a
/// client-side translation for a string whose structure we do not know is
/// exactly the unreliable logic Phase 13 rules out. New keys are added here
/// and to the ARB together.
extension NotificationText on AppL10n {
  String notificationTitle(NotificationItem item) {
    final params = item.messageParams;
    return switch (item.messageKey) {
      'taskDeadline.DUE_TOMORROW' => notifTaskDueTomorrowTitle,
      'taskDeadline.DUE_TODAY' => notifTaskDueTodayTitle,
      'taskDeadline.OVERDUE' ||
      'taskDeadline.OVERDUE_SEVERAL' ||
      'taskDeadline.OVERDUE_WEEK' => notifTaskOverdueTitle,
      'siteReport.awaitingVerification' => notifSiteReportAwaitingTitle,
      'siteReport.verified' => notifSiteReportVerifiedTitle,
      'siteReport.rejected' => notifSiteReportRejectedTitle,
      'reminder.waiting' => notifReminderWaitingTitle(_p(params, 'label')),
      'reminder.escalation' =>
        notifReminderEscalationTitle(_p(params, 'label')),
      'stepUp.codeRequested' => notifStepUpRequestedTitle,
      _ => item.title,
    };
  }

  String notificationBody(NotificationItem item) {
    final params = item.messageParams;
    return switch (item.messageKey) {
      'taskDeadline.DUE_TOMORROW' =>
        notifTaskDueTomorrowBody(_p(params, 'name')),
      'taskDeadline.DUE_TODAY' => notifTaskDueTodayBody(_p(params, 'name')),
      'taskDeadline.OVERDUE' => notifTaskOverdueBody(_p(params, 'name')),
      'taskDeadline.OVERDUE_SEVERAL' =>
        notifTaskOverdueSeveralBody(_p(params, 'name')),
      'taskDeadline.OVERDUE_WEEK' =>
        notifTaskOverdueWeekBody(_p(params, 'name')),
      'siteReport.awaitingVerification' =>
        notifSiteReportAwaitingBody(_p(params, 'project')),
      'siteReport.verified' => notifSiteReportVerifiedBody(
        _p(params, 'date'),
        _p(params, 'reviewer'),
      ),
      'siteReport.rejected' => notifSiteReportRejectedBody(
        _p(params, 'date'),
        _p(params, 'reviewer'),
        _p(params, 'reason'),
      ),
      'reminder.waiting' => notifReminderWaitingBody(
        _p(params, 'target'),
        _p(params, 'sequence'),
      ),
      'reminder.escalation' =>
        notifReminderEscalationBody(_p(params, 'target')),
      'stepUp.codeRequested' =>
        notifStepUpRequestedBody(_p(params, 'action')),
      _ => item.message,
    };
  }

  /// Parameter values are project data — task names, project names, reviewer
  /// names, rejection reasons — and are interpolated exactly as the server
  /// sent them. They are never translated.
  static String _p(Map<String, dynamic> params, String name) =>
      params[name]?.toString() ?? '';
}
