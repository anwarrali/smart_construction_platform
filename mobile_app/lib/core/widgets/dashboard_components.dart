import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_shadows.dart';
import '../theme/app_spacing.dart';
import '../theme/app_theme.dart';
import '../l10n/l10n_formats.dart';
import '../l10n/l10n_labels.dart';

class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  });
  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.end,
    children: [
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            if (subtitle != null) ...[
              const SizedBox(height: 3),
              Text(subtitle!, style: Theme.of(context).textTheme.bodySmall),
            ],
          ],
        ),
      ),
      if (onAction != null)
        TextButton(
          onPressed: onAction,
          child: Text(actionLabel ?? context.l10n.commonViewAll),
        ),
    ],
  );
}

/// One line of the "Today" list: a thing that needs a person, how many of
/// them there are, and where to go to deal with it.
///
/// This replaced a six-cell grid of metric squares. The grid gave equal
/// weight to "6 overdue" and "0 blocked", so the screen looked identical
/// whether the project was on fire or completely clear — a person had to read
/// six numbers to find that out. A list that only carries what is non-zero,
/// worst first, answers the field question in one glance and disappears
/// entirely when there is nothing to answer.
class AttentionRow extends StatelessWidget {
  const AttentionRow({
    super.key,
    required this.label,
    required this.count,
    required this.icon,
    required this.tone,
    required this.onTap,
  });

  final String label;
  final String count;
  final IconData icon;
  final Color tone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: AppColors.card,
    borderRadius: BorderRadius.circular(AppRadius.panel),
    child: InkWell(
      borderRadius: BorderRadius.circular(AppRadius.panel),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: 10,
        ),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppRadius.panel),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: tone.withValues(alpha: .1),
                borderRadius: BorderRadius.circular(AppRadius.control),
              ),
              child: Icon(icon, color: tone, size: 20),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            const SizedBox(width: AppSpacing.xs),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
              decoration: BoxDecoration(
                color: tone.withValues(alpha: .12),
                borderRadius: BorderRadius.circular(AppRadius.chip),
              ),
              child: Text(
                count,
                style: AppTheme.measured.copyWith(
                  color: tone,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const Icon(
              Icons.chevron_right_rounded,
              color: AppColors.mutedForeground,
            ),
          ],
        ),
      ),
    ),
  );
}

class DashboardMetricCard extends StatelessWidget {
  const DashboardMetricCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.tone = AppColors.primary,
    this.background = Colors.white,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color tone;
  final Color background;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.md),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      border: Border.all(color: AppColors.border),
      boxShadow: AppShadows.card,
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 38,
          height: 38,
          decoration: BoxDecoration(
            color: tone.withValues(alpha: .1),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: tone, size: 21),
        ),
        const Spacer(),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 2),
        Text(
          label,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(
            context,
          ).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
        ),
      ],
    ),
  );
}

class ProjectProgressCard extends StatelessWidget {
  const ProjectProgressCard({
    super.key,
    required this.progress,
    required this.status,
  });
  final double progress;
  final String status;

  @override
  Widget build(BuildContext context) {
    final normalized = progress.clamp(0, 100) / 100;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.circular(AppRadius.panel),
        boxShadow: AppShadows.elevated,
      ),
      child: Row(
        children: [
          SizedBox.square(
            dimension: 78,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: normalized,
                  strokeWidth: 8,
                  backgroundColor: Colors.white.withValues(alpha: .12),
                  color: AppColors.accent,
                ),
                Text(
                  // Was '${progress.round()}%', which hardcoded the Western
                  // percent sign and bypassed the app's number policy.
                  context.formatPercent(progress),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.dashboardOverallProgress,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 4),
                Text(
                  context.l10n.statusLabel(status),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  context.l10n.dashboardLiveProjectData,
                  style: const TextStyle(
                    color: AppColors.accentWash,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

enum SmartSummaryState { ready, loading, unavailable }

class SmartSummaryCard extends StatelessWidget {
  const SmartSummaryCard({
    super.key,
    required this.state,
    this.summary,
    this.lastUpdated,
  });

  final SmartSummaryState state;
  final String? summary;
  final DateTime? lastUpdated;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.lg),
    decoration: BoxDecoration(
      color: AppColors.primary,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      boxShadow: AppShadows.elevated,
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: AppColors.accent.withValues(alpha: .2),
                borderRadius: BorderRadius.circular(13),
              ),
              child: const Icon(
                Icons.auto_awesome_outlined,
                color: AppColors.accent,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.dashboardSummaryTitle,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    context.l10n.dashboardSummarySubtitle,
                    style: TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .1),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                // These two were hardcoded English literals even though the
                // catalogue already carried both keys.
                state == SmartSummaryState.ready
                    ? context.l10n.dashboardLiveData
                    : context.l10n.dashboardAiReady,
                style: const TextStyle(
                  color: AppColors.accentWash,
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (state == SmartSummaryState.loading)
          ...List.generate(
            3,
            (index) => Container(
              height: 10,
              margin: const EdgeInsets.only(bottom: 9),
              width: index == 2 ? 180 : double.infinity,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .11),
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          )
        else
          Text(
            state == SmartSummaryState.ready && summary != null
                ? summary!
                : context.l10n.dashboardAiPlaceholder,
            style: const TextStyle(color: Colors.white, height: 1.5),
          ),
        const SizedBox(height: AppSpacing.md),
        Row(
          children: [
            Icon(
              state == SmartSummaryState.ready
                  ? Icons.verified_outlined
                  : Icons.hub_outlined,
              color: Colors.white54,
              size: 15,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                state == SmartSummaryState.ready
                    ? context.l10n.dashboardGeneratedFrom
                    : context.l10n.dashboardFutureIntegration,
                style: const TextStyle(color: Colors.white54, fontSize: 11),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}
