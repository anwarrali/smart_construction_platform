import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../l10n/l10n_labels.dart';

/// One semantic ramp, six hues, one meaning each — identical to the web.
///
/// The web tokens are explicit that this ramp replaced a scatter of colours
/// that carried no consistent meaning from one module to the next. Mobile
/// resolves the same vocabulary here, in one place, so a status cannot come
/// out green on one screen and blue on another.
enum StatusTone {
  /// approved · signed off · on plan
  verified(AppColors.stateVerified, AppColors.stateVerifiedWash),

  /// under way · information
  progress(AppColors.stateProgress, AppColors.stateProgressWash),

  /// at risk · awaiting a decision
  review(AppColors.stateReview, AppColors.stateReviewWash),

  /// delayed · critical · past date
  overdue(AppColors.stateOverdue, AppColors.stateOverdueWash),

  /// held by something else
  blocked(AppColors.stateBlocked, AppColors.stateBlockedWash),

  /// not started · inactive
  idle(AppColors.stateIdle, AppColors.stateIdleWash);

  const StatusTone(this.ink, this.wash);
  final Color ink;
  final Color wash;

  /// Maps a backend status/severity string onto the ramp.
  ///
  /// The values are the ones the API actually emits across tasks, issues,
  /// site reports and design changes. Anything unrecognised resolves to
  /// [idle] rather than inventing a colour.
  static StatusTone of(String? value) => switch (value?.toLowerCase().trim()) {
    'done' ||
    'approved' ||
    'verified' ||
    'resolved' ||
    'completed' ||
    'active' ||
    'implemented' => StatusTone.verified,

    'in_progress' ||
    'submitted' ||
    'proposed' ||
    'low' ||
    'info' ||
    'normal' => StatusTone.progress,

    // `under_review` is warning on the web (`statusVariant` in
    // `TaskCard.tsx`), not info: the work is parked awaiting somebody's
    // decision, which is exactly what this hue means.
    'under_review' ||
    'pending' ||
    'at_risk' ||
    'medium' ||
    'high' ||
    'important' ||
    'needs_clarification' => StatusTone.review,

    // `rework_required` is the rejected outcome under another name, so it
    // takes the same hue as `rejected` — the web calls both danger.
    'overdue' ||
    'delayed' ||
    'rejected' ||
    'rework_required' ||
    'critical' => StatusTone.overdue,

    'blocked' || 'on_hold' => StatusTone.blocked,

    // Cancelled is inactive, not failed; the web calls it neutral.
    'cancelled' => StatusTone.idle,

    _ => StatusTone.idle,
  };
}

/// A compact status chip.
///
/// Tight radius and a wash ground, matching the web's chip: this is a label,
/// not a pill — the rounded-pill treatment the app used before belonged to a
/// different (consumer) visual language.
class StatusBadge extends StatelessWidget {
  const StatusBadge(this.value, {super.key, this.compact = false, this.label});

  /// The raw backend value, used both to pick the tone and (by default) as
  /// the visible text.
  final String value;

  /// Overrides the visible text. Almost nothing needs this: by default the
  /// badge translates [value] through the shared status vocabulary, so a
  /// status reads the same wherever it appears.
  final String? label;

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final tone = StatusTone.of(value);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 6 : 8,
        vertical: compact ? 3 : 4,
      ),
      decoration: BoxDecoration(
        color: tone.wash,
        borderRadius: BorderRadius.circular(AppRadius.chip),
        border: Border.all(color: tone.ink.withValues(alpha: 0.22)),
      ),
      child: Text(
        label ?? context.l10n.statusLabel(value),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          color: tone.ink,
          fontSize: compact ? 10.5 : 11.5,
          fontWeight: FontWeight.w600,
          height: 1.2,
        ),
      ),
    );
  }
}

/// The notification priority indicator from the Smart Notification system.
///
/// Only IMPORTANT and CRITICAL get a visible badge. Marking every ordinary
/// notification "Normal" would make the list noisier rather than clearer —
/// the point of the badge is that something stands out from the ordinary.
/// This mirrors exactly what the web notification list does.
class PriorityBadge extends StatelessWidget {
  const PriorityBadge(this.priority, {super.key, this.importantLabel, this.criticalLabel});

  final String? priority;
  final String? importantLabel;
  final String? criticalLabel;

  @override
  Widget build(BuildContext context) {
    final value = priority?.toUpperCase();
    final (tone, text) = switch (value) {
      'CRITICAL' => (
        StatusTone.overdue,
        criticalLabel ?? context.l10n.priorityCritical,
      ),
      'IMPORTANT' => (
        StatusTone.review,
        importantLabel ?? context.l10n.priorityImportant,
      ),
      _ => (null, ''),
    };
    if (tone == null) return const SizedBox.shrink();
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: tone.wash,
        borderRadius: BorderRadius.circular(AppRadius.chip),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: tone.ink,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          height: 1.2,
        ),
      ),
    );
  }
}
