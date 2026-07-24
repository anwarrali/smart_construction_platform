import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/task_card.dart';
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
      return const MessageView(
        icon: Icons.apartment,
        title: 'No project selected',
        message: 'Select a project first.',
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(user.isSiteEngineer || user.isWorker ? 'My Tasks' : 'Project Tasks'),
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
            return const LoadingView(label: 'Loading tasks');
          }
          if (snapshot.hasError) {
            return MessageView(
              icon: Icons.cloud_off,
              title: 'Tasks unavailable',
              message: '${snapshot.error}',
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
                        value: '${allTasks.length}',
                        label: 'Total',
                        tone: AppColors.navy,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _TaskSummary(
                        value:
                            '${allTasks.where((task) => task.isOverdue).length}',
                        label: 'Overdue',
                        tone: AppColors.danger,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: _TaskSummary(
                        value:
                            '${allTasks.where((task) => task.status == 'blocked').length}',
                        label: 'Blocked',
                        tone: AppColors.warning,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(
                height: 60,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.page,
                    vertical: 10,
                  ),
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
                              padding: const EdgeInsets.only(right: 8),
                              child: FilterChip(
                                label: Text(_filterLabel(value)),
                                selected: _filter == value,
                                showCheckmark: true,
                                checkmarkColor: Colors.white,
                                backgroundColor: Colors.white,
                                selectedColor: AppColors.navy,
                                side: BorderSide(
                                  color: _filter == value
                                      ? AppColors.navy
                                      : AppColors.border,
                                ),
                                labelStyle: TextStyle(
                                  color: _filter == value
                                      ? Colors.white
                                      : AppColors.textPrimary,
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
                    ? const MessageView(
                        icon: Icons.task_alt,
                        title: 'No matching tasks',
                        message: 'There are no assigned tasks in this view.',
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

  String _filterLabel(String value) => switch (value) {
    'all' => 'All',
    'todo' => 'To do',
    'in_progress' => 'In progress',
    'under_review' => 'Under review',
    'rework_required' => 'Rework',
    _ => '${value[0].toUpperCase()}${value.substring(1)}',
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
              color: AppColors.textSecondary,
            ),
          ),
        ),
      ],
    ),
  );
}
