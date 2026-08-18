import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/task_card.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../models/task.dart';
import '../projects/project_context_view_model.dart';

class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});
  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends ConsumerState<TasksScreen> {
  String _filter = 'all';
  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    final user = ref.watch(sessionProvider).user!;
    if (project == null) {
      return MessageView(
        icon: Icons.apartment,
        title: context.l10n.commonNoProjectSelected,
        message: context.l10n.commonSelectProjectFirst,
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              user.isSiteEngineer || user.isWorker
                  ? context.l10n.tasksMyTasks
                  : context.l10n.tasksProjectTasks,
            ),
            Text(
              project.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                color: Colors.white70,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
      body: FutureBuilder<List<ProjectTask>>(
        future: ref
            .read(taskRepositoryProvider)
            .list(project.id, assignedOnly: user.isSiteEngineer || user.isWorker),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return LoadingView(label: context.l10n.tasksLoading);
          }
          if (snapshot.hasError) {
            return MessageView(
              icon: Icons.cloud_off,
              title: context.l10n.commonUnavailable(context.l10n.tasksTitle),
              message: context.l10n.describeError(snapshot.error),
              onAction: () => setState(() {}),
            );
          }
          var tasks = snapshot.data ?? const [];
          if (_filter != 'all') {
            tasks = tasks
                .where(
                  (task) =>
                      task.status == _filter ||
                      (_filter == 'overdue' && task.isOverdue),
                )
                .toList();
          }
          final allTasks = snapshot.data ?? const <ProjectTask>[];
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.page,
                  AppSpacing.md,
                  AppSpacing.page,
                  4,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: _TaskSummary(
                        value: context.formatInt(allTasks.length),
                        label: context.l10n.tasksTotal,
                        tone: AppColors.primary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _TaskSummary(
                        value: context.formatInt(
                          allTasks.where((task) => task.isOverdue).length,
                        ),
                        label: context.l10n.tasksOverdue,
                        tone: AppColors.destructive,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _TaskSummary(
                        value: context.formatInt(
                          allTasks
                              .where((task) => task.status == 'blocked')
                              .length,
                        ),
                        label: context.l10n.tasksBlocked,
                        tone: AppColors.stateReview,
                      ),
                    ),
                  ],
                ),
              ),
              // Was a fixed 60dp box around a horizontal ListView, which
              // clipped the chips as soon as a translated label or an
              // accessibility text scale made them taller — the same class of
              // failure as the fixed-height dashboard header. A scroll view
              // wrapping a Row sizes to its content instead.
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.page,
                  vertical: 10,
                ),
                child: Row(
                  children:
                      [
                            'all',
                            'backlog',
                            'todo',
                            'in_progress',
                            'under_review',
                            'rework_required',
                            'blocked',
                            'done',
                            'cancelled',
                            'overdue',
                          ]
                          .map(
                            (value) => Padding(
                              // Directional: the gap follows the reading
                              // order, so the chips do not bunch up in Arabic.
                              padding: const EdgeInsetsDirectional.only(end: 8),
                              child: FilterChip(
                                label: Text(_filterLabel(context, value)),
                                selected: _filter == value,
                                showCheckmark: true,
                                checkmarkColor: Colors.white,
                                backgroundColor: Colors.white,
                                selectedColor: AppColors.primary,
                                side: BorderSide(
                                  color: _filter == value
                                      ? AppColors.primary
                                      : AppColors.border,
                                ),
                                labelStyle: TextStyle(
                                  color: _filter == value
                                      ? Colors.white
                                      : AppColors.foreground,
                                  fontWeight: _filter == value
                                      ? FontWeight.w800
                                      : FontWeight.w600,
                                ),
                                onSelected: (_) =>
                                    setState(() => _filter = value),
                              ),
                            ),
                          )
                          .toList(),
                ),
              ),
              Expanded(
                child: tasks.isEmpty
                    ? MessageView(
                        icon: Icons.task_alt,
                        title: context.l10n.tasksNoMatching,
                        message: context.l10n.tasksNoAssigned,
                      )
                    : RefreshIndicator(
                        onRefresh: () async => setState(() {}),
                        child: ListView.separated(
                          padding: const EdgeInsets.fromLTRB(
                            AppSpacing.page,
                            4,
                            AppSpacing.page,
                            104,
                          ),
                          itemCount: tasks.length,
                          separatorBuilder: (_, __) =>
                              const SizedBox(height: 12),
                          itemBuilder: (_, i) => TaskCard(
                            task: tasks[i],
                            onTap: () => context.push('/tasks/${tasks[i].id}'),
                          ),
                        ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }

  /// Filter chips are narrow, so `rework_required` gets a short form; every
  /// other value uses the shared status vocabulary rather than a second one.
  String _filterLabel(BuildContext context, String value) => switch (value) {
    'all' => context.l10n.commonAll,
    'rework_required' => context.l10n.tasksFilterRework,
    _ => context.l10n.statusLabel(value),
  };
}

class _TaskSummary extends StatelessWidget {
  const _TaskSummary({
    required this.value,
    required this.label,
    required this.tone,
  });
  final String value;
  final String label;
  final Color tone;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 11),
    decoration: BoxDecoration(
      color: tone.withValues(alpha: .08),
      borderRadius: BorderRadius.circular(14),
    ),
    child: Row(
      children: [
        Text(
          value,
          style: TextStyle(
            color: tone,
            fontWeight: FontWeight.w800,
            fontSize: 18,
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w700,
              color: AppColors.mutedForeground,
            ),
          ),
        ),
      ],
    ),
  );
}
