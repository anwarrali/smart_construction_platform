import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../l10n/l10n_labels.dart';
import '../../models/notification_item.dart';

/// How a notification is drawn, in one place.
///
/// The list and the detail screen were choosing independently, so a
/// notification that shouted in the list arrived on its own page as a generic
/// blue bell with no indication of priority at all. One table, used by both.
abstract final class NotificationVisuals {
  /// The icon and hue for a notification *type* — what it is about.
  static (IconData, Color) forType(String type) =>
      switch (type.toLowerCase()) {
        'task_assigned' ||
        'task_updated' ||
        'task_overdue' => (Icons.task_alt_rounded, AppColors.stateProgress),
        'review_submitted' ||
        'review_approved' => (
          Icons.fact_check_outlined,
          AppColors.stateVerified,
        ),
        'review_rejected' ||
        'rework_requested' => (Icons.replay_rounded, AppColors.stateReview),
        'issue_created' ||
        'issue_updated' => (
          Icons.report_problem_outlined,
          AppColors.destructive,
        ),
        'message' => (Icons.forum_outlined, AppColors.stateProgress),
        _ => (Icons.notifications_outlined, AppColors.primary),
      };

  /// The accent hue for a notification *priority* — how much it matters.
  ///
  /// Null for NORMAL and INFO, and that is the design: if every row carries a
  /// colour, none of them mean anything. Only the two priorities the Smart
  /// Notification system raises above ordinary get an accent, exactly as the
  /// web list does.
  static Color? forPriority(String? priority) =>
      switch (priority?.toUpperCase()) {
        'CRITICAL' => AppColors.stateOverdue,
        'IMPORTANT' => AppColors.stateReview,
        _ => null,
      };

  /// Critical is the only priority that also tints its ground. It is the
  /// difference between "read this next" and "something is wrong now", and a
  /// person scrolling a list under bright sun needs that to survive a glance.
  static bool isCritical(String? priority) =>
      priority?.toUpperCase() == 'CRITICAL';
}

/// The small "Reminder" marker used beside a priority badge.
///
/// Task 3's reminder and escalation notifications are ordinary notifications
/// with a flag; this says so without borrowing a priority colour it has not
/// earned.
class ReminderChip extends StatelessWidget {
  const ReminderChip({super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    decoration: BoxDecoration(
      color: AppColors.muted,
      borderRadius: BorderRadius.circular(AppRadius.chip),
    ),
    child: Text(
      context.l10n.notificationReminder,
      style: const TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.w700,
        color: AppColors.mutedForeground,
      ),
    ),
  );
}

/// Convenience for the two screens that render a notification.
extension NotificationPresentation on NotificationItem {
  (IconData, Color) get visual => NotificationVisuals.forType(type);
  Color? get accent => NotificationVisuals.forPriority(priority);
  bool get isCritical => NotificationVisuals.isCritical(priority);
}
