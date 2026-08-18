import 'package:flutter/material.dart';

import '../../models/task.dart';
import '../l10n/l10n_formats.dart';
import '../l10n/l10n_labels.dart';
import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_shadows.dart';
import '../theme/app_spacing.dart';
import 'status_badge.dart';

class TaskCard extends StatelessWidget {
  const TaskCard({super.key, required this.task, required this.onTap});
  final ProjectTask task;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final priorityTone = switch (task.priority) {
      'critical' => AppColors.destructive,
      'high' => AppColors.stateReview,
      'low' => AppColors.stateVerified,
      _ => AppColors.stateProgress,
    };
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.panel),
        border: Border.all(
          color: task.isOverdue
              ? AppColors.destructive.withValues(alpha: .26)
              : AppColors.border,
        ),
        boxShadow: AppShadows.card,
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.panel),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 4,
                    height: 44,
                    decoration: BoxDecoration(
                      color: priorityTone,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                  const SizedBox(width: 11),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          task.name,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${task.code}  ·  '
                          '${context.l10n.disciplineLabel(task.discipline)}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  StatusBadge(task.status, compact: true),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Text(
                    context.l10n.commonProgress,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const Spacer(),
                  Text(
                    context.formatPercent(task.progress),
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.primary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 7),
              LinearProgressIndicator(
                value: task.progress.clamp(0, 100) / 100,
                minHeight: 7,
                borderRadius: BorderRadius.circular(10),
              ),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _MetaPill(
                    icon: Icons.flag_outlined,
                    label: context.l10n.priorityLabel(task.priority),
                    color: priorityTone,
                  ),
                  if (task.dueDate != null)
                    _MetaPill(
                      icon: task.isOverdue
                          ? Icons.event_busy_outlined
                          : Icons.event_outlined,
                      label: task.isOverdue
                          ? context.l10n.taskDaysOverdue(task.daysOverdue)
                          : context.l10n.taskDueOn(
                              context.formatShortDate(task.dueDate!),
                            ),
                      color: task.isOverdue
                          ? AppColors.destructive
                          : AppColors.mutedForeground,
                    ),
                  if (task.hasIncompleteDependencies)
                    _MetaPill(
                      icon: Icons.link_off_rounded,
                      label: context.l10n.taskDependencyBlocked,
                      color: AppColors.stateReview,
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetaPill extends StatelessWidget {
  const _MetaPill({
    required this.icon,
    required this.label,
    required this.color,
  });
  final IconData icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .08),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 4),
        Text(
          label.replaceAll('_', ' '),
          style: TextStyle(
            color: color,
            fontSize: 10,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}
