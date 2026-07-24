import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/auth/permission_service.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/task.dart';
import '../field_evidence/worker_submissions_screen.dart';

class TaskDetailScreen extends ConsumerStatefulWidget {
  const TaskDetailScreen({super.key, required this.taskId});
  final String taskId;
  @override
  ConsumerState<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends ConsumerState<TaskDetailScreen> {
  late Future<ProjectTask> _task;
  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() => _task = ref.read(taskRepositoryProvider).get(widget.taskId);
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Task Details')),
    body: FutureBuilder<ProjectTask>(
      future: _task,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView();
        }
        if (snapshot.hasError || snapshot.data == null) {
          return MessageView(
            icon: Icons.cloud_off,
            title: 'Task unavailable',
            message: '${snapshot.error}',
            onAction: () => setState(_reload),
          );
        }
        final task = snapshot.data!;
        final user = ref.watch(sessionProvider).user!;
        final permission = const PermissionService();
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            task.name,
                            style: Theme.of(context).textTheme.headlineSmall
                                ?.copyWith(fontWeight: FontWeight.w800),
                          ),
                        ),
                        StatusBadge(task.status),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text('${task.code} • ${task.discipline ?? 'General'}'),
                    const SizedBox(height: 18),
                    LinearProgressIndicator(
                      value: task.progress / 100,
                      minHeight: 10,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    const SizedBox(height: 8),
                    Text('${task.progress.round()}% complete'),
                  ],
                ),
              ),
            ),
            if (task.hasIncompleteDependencies)
              Card(
                color: Colors.orange.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Cannot start yet',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 8),
                      ...task.dependencies
                          .where((d) => !d.isComplete)
                          .map(
                            (d) => Text(
                              '• ${d.name} (${d.status.replaceAll('_', ' ')})',
                            ),
                          ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 18),
            Text(
              'Quick actions',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: () => context.push('/tasks/${task.id}/discussion'),
              icon: const Icon(Icons.forum_outlined),
              label: const Text('Task Discussion'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(52),
              ),
            ),
            if (permission.canExecuteTask(user, task) || user.isWorker) ...[
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => context.push('/voice?taskId=${task.id}'),
                icon: const Icon(Icons.mic_none_rounded),
                label: const Text('AI Voice Field Update'),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                ),
              ),
            ],
            const SizedBox(height: 10),
            if (permission.canStartTask(user, task))
              FilledButton.icon(
                onPressed: () => _action(
                  () => ref.read(taskRepositoryProvider).start(task.id),
                ),
                icon: const Icon(Icons.play_arrow),
                label: const Text('Start Task'),
              ),
            if (permission.canExecuteTask(user, task)) ...[
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _progress(task),
                icon: const Icon(Icons.trending_up),
                label: const Text('Update Progress'),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _textAction(
                  'Add Comment',
                  (value) => ref
                      .read(taskRepositoryProvider)
                      .addComment(task.id, value),
                ),
                icon: const Icon(Icons.comment_outlined),
                label: const Text('Add Comment'),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _textAction(
                  'Submit for Review',
                  (value) => ref
                      .read(taskRepositoryProvider)
                      .submitReview(task.id, value),
                ),
                icon: const Icon(Icons.rate_review),
                label: const Text('Submit for Review'),
              ),
            ],
            if (user.isWorker) ...[
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () async {
                  final created = await context.push<bool>(
                    '/tasks/${task.id}/evidence/new',
                  );
                  if (created == true && mounted) setState(_reload);
                },
                icon: const Icon(Icons.add_a_photo_outlined),
                label: const Text('Create Field Update'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(56),
                ),
              ),
              const SizedBox(height: 22),
              Text(
                'My Evidence History',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              WorkerSubmissionsScreen(taskId: task.id, embedded: true),
            ],
            if (!permission.canExecuteTask(user, task) && user.isSiteEngineer)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text('You do not have permission to update this task.'),
              ),
          ],
        );
      },
    ),
  );

  Future<void> _action(Future<Object?> Function() action) async {
    try {
      await action();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Task updated.')));
        setState(_reload);
      }
    } on NetworkException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _progress(ProjectTask task) async {
    double value = task.progress;
    final note = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Update Progress'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('${value.round()}%'),
              Slider(
                value: value,
                min: 0,
                max: 100,
                divisions: 20,
                onChanged: (v) => setDialogState(() => value = v),
              ),
              TextField(
                controller: note,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Work note (optional)',
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Update'),
            ),
          ],
        ),
      ),
    );
    if (confirmed == true) {
      await _action(
        () => ref
            .read(taskRepositoryProvider)
            .updateProgress(
              task.id,
              value,
              note.text.trim().isEmpty ? null : note.text.trim(),
            ),
      );
    }
    note.dispose();
  }

  Future<void> _textAction(
    String title,
    Future<void> Function(String) action,
  ) async {
    final controller = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          maxLines: 4,
          decoration: const InputDecoration(labelText: 'Note'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirm'),
          ),
        ],
      ),
    );
    if (confirmed == true && controller.text.trim().isNotEmpty) {
      await _action(() => action(controller.text.trim()));
    }
    controller.dispose();
  }
}
