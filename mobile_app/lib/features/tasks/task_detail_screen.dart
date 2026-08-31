import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/auth/permission_service.dart';
import '../../core/auth/session_manager.dart';
import '../../core/auth/voice_access.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/entity_actions.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/task.dart';
import '../field_evidence/field_submissions_screen.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/auth/capabilities.dart';

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
    appBar: AppBar(title: Text(context.l10n.taskDetailTitle)),
    body: FutureBuilder<ProjectTask>(
      future: _task,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView();
        }
        if (snapshot.hasError || snapshot.data == null) {
          return MessageView(
            icon: Icons.cloud_off,
            title: context.l10n.commonUnavailable(context.l10n.taskTitle),
            message: context.l10n.describeError(snapshot.error),
            onAction: () => setState(_reload),
          );
        }
        final task = snapshot.data!;
        final user = ref.watch(sessionProvider).user!;
        final permission = const PermissionService();
        // Resolved for this project: the same person can be office staff
        // on one and a contractor's representative on another.
        final capabilities = capabilitiesOf(ref, projectId: task.projectId);
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
                    Text(
                      '${task.code} • '
                      '${context.l10n.disciplineLabel(task.discipline)}',
                    ),
                    const SizedBox(height: 18),
                    LinearProgressIndicator(
                      value: task.progress / 100,
                      minHeight: 10,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      context.l10n.taskPercentComplete(
                        context.formatInt(task.progress.round()),
                      ),
                    ),
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
                      Text(
                        context.l10n.taskCannotStartYet,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 8),
                      ...task.dependencies
                          .where((d) => !d.isComplete)
                          .map(
                            (d) => Text(
                              context.l10n.taskDependencyLine(
                                d.name.trim().isEmpty
                                    ? context.l10n.taskDependencyUnnamed
                                    : d.name,
                                context.l10n.statusLabel(d.status),
                              ),
                            ),
                          ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 18),
            Text(
              context.l10n.taskQuickActions,
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: () => context.push('/tasks/${task.id}/discussion'),
              icon: const Icon(Icons.forum_outlined),
              label: Text(context.l10n.taskDiscussion),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(52),
              ),
            ),
            // Consultation, not handoff: asking a colleague to advise on a
            // task creates a message and changes nothing about who owns it.
            // Deliberately never labelled "Forward" — see `ShareIntent`.
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: () => showShareSheet(
                context: context,
                intent: ShareIntent.askOpinion,
                entityType: 'TASK',
                entityId: task.id,
              ),
              icon: const Icon(Icons.help_outline_rounded),
              label: Text(context.l10n.shareAskOpinion),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(52),
              ),
            ),
            // Voice was gated on `canExecuteTask || isWorker`, which took it
            // away from Project Managers, Consultants, Owners and every
            // engineer not affiliated to the main contractor. It is a general
            // interaction layer for every role but Admin.
            if (canUseVoice(capabilities)) ...[
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => context.push('/voice?taskId=${task.id}'),
                icon: const Icon(Icons.mic_none_rounded),
                label: Text(context.l10n.taskVoiceUpdate),
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                ),
              ),
            ],
            const SizedBox(height: 10),
            if (permission.canStartTask(capabilities, user, task))
              FilledButton.icon(
                onPressed: () => _action(
                  () => ref.read(taskRepositoryProvider).start(task.id),
                ),
                icon: const Icon(Icons.play_arrow),
                label: Text(context.l10n.taskStart),
              ),
            if (permission.canExecuteTask(capabilities, user, task)) ...[
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _progress(task),
                icon: const Icon(Icons.trending_up),
                label: Text(context.l10n.taskUpdateProgress),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _textAction(
                  context.l10n.taskAddComment,
                  (value) => ref
                      .read(taskRepositoryProvider)
                      .addComment(task.id, value),
                ),
                icon: const Icon(Icons.comment_outlined),
                label: Text(context.l10n.taskAddComment),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _textAction(
                  context.l10n.taskSubmitForReview,
                  (value) => ref
                      .read(taskRepositoryProvider)
                      .submitReview(task.id, value),
                ),
                icon: const Icon(Icons.rate_review),
                label: Text(context.l10n.taskSubmitForReview),
              ),
            ],
            // Filing field evidence follows `field_evidence.submit` — the
            // same code the server checks — rather than a job title. A
            // Site Engineer normally holds it; so may anyone else the
            // office decided should.
            if (permission.canSubmitFieldEvidence(capabilities)) ...[
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: () async {
                  final created = await context.push<bool>(
                    '/tasks/${task.id}/evidence/new',
                  );
                  if (created == true && mounted) setState(_reload);
                },
                icon: const Icon(Icons.add_a_photo_outlined),
                label: Text(context.l10n.taskCreateFieldUpdate),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(56),
                ),
              ),
              const SizedBox(height: 22),
              Text(
                context.l10n.taskEvidenceHistory,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              FieldSubmissionsScreen(taskId: task.id, embedded: true),
            ],
            if (!permission.canExecuteTask(capabilities, user, task)
                && permission.canSubmitFieldEvidence(capabilities))
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(context.l10n.taskNoPermission),
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
        ).showSnackBar(
          SnackBar(content: Text(context.l10n.taskUpdated)),
        );
        setState(_reload);
      }
    } on NetworkException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(
          SnackBar(content: Text(context.l10n.describeError(e))),
        );
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
          title: Text(context.l10n.taskUpdateProgress),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(context.formatPercent(value)),
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
                decoration: InputDecoration(
                  labelText: context.l10n.taskWorkNote,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text(context.l10n.commonCancel),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(context.l10n.commonUpdate),
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
          decoration: InputDecoration(labelText: context.l10n.commonNote),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(context.l10n.commonCancel),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(context.l10n.commonConfirm),
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
