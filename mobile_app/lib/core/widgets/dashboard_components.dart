import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_shadows.dart';
import '../theme/app_spacing.dart';

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
        TextButton(onPressed: onAction, child: Text(actionLabel ?? 'View all')),
    ],
  );
}

class DashboardMetricCard extends StatelessWidget {
  const DashboardMetricCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    this.tone = AppColors.navy,
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
      borderRadius: BorderRadius.circular(AppRadius.large),
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
        color: AppColors.navy,
        borderRadius: BorderRadius.circular(AppRadius.large),
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
                  color: AppColors.bronze,
                ),
                Text(
                  '${progress.round()}%',
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
                  'Overall progress',
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 4),
                Text(
                  status.replaceAll('_', ' '),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Live project data',
                  style: TextStyle(color: AppColors.bronzeSoft, fontSize: 12),
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
      color: AppColors.navy,
      borderRadius: BorderRadius.circular(AppRadius.large),
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
                color: AppColors.bronze.withValues(alpha: .2),
                borderRadius: BorderRadius.circular(13),
              ),
              child: const Icon(
                Icons.auto_awesome_outlined,
                color: AppColors.bronze,
              ),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Smart Project Summary',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    'Executive project intelligence',
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
                state == SmartSummaryState.ready ? 'LIVE DATA' : 'AI READY',
                style: const TextStyle(
                  color: AppColors.bronzeSoft,
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
                : 'AI-generated insights will appear here when the summary service is connected. Current project metrics remain available below.',
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
                    ? 'Generated from current backend metrics · No external AI'
                    : 'Future integration placeholder · No fabricated insights',
                style: const TextStyle(color: Colors.white54, fontSize: 11),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}
