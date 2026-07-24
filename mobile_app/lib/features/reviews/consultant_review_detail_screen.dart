import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/status_badge.dart';
import '../projects/project_context_view_model.dart';

enum _ReviewAction { approve, reject, clarification }

class ConsultantReviewDetailScreen extends ConsumerStatefulWidget {
  const ConsultantReviewDetailScreen({super.key, required this.reviewId});
  final String reviewId;

  @override
  ConsumerState<ConsultantReviewDetailScreen> createState() =>
      _ConsultantReviewDetailScreenState();
}

class _ConsultantReviewDetailScreenState
    extends ConsumerState<ConsultantReviewDetailScreen> {
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) {
      setState(() {
        _loading = false;
        _error = 'Select a project first.';
      });
      return;
    }
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final data = await ref
          .read(apiClientProvider)
          .get<Map<String, dynamic>>(
            ApiEndpoints.consultantReview(project.id, widget.reviewId),
          );
      if (mounted) {
        setState(() {
          _data = data;
          _loading = false;
        });
      }
    } on NetworkException catch (error) {
      if (mounted) {
        setState(() {
          _error = error.message;
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final review = data?['review'] as Map<String, dynamic>?;
    final task = data?['task'] as Map<String, dynamic>?;
    return Scaffold(
      appBar: AppBar(title: const Text('Review Submission')),
      body: _loading
          ? const LoadingView(label: 'Loading submission and evidence')
          : _error != null || data == null || review == null || task == null
          ? MessageView(
              icon: Icons.error_outline_rounded,
              title: 'Unable to open review',
              message: _error ?? 'Review submission not found.',
              onAction: _load,
            )
          : _content(data, review, task),
    );
  }

  Widget _content(
    Map<String, dynamic> data,
    Map<String, dynamic> review,
    Map<String, dynamic> task,
  ) {
    final status = '${review['reviewStatus'] ?? 'pending'}';
    final canDecide = status == 'pending' || status == 'in_review';
    final evidence = (data['submissionEvidence'] as List? ?? const []);
    final dependencies = (data['dependencies'] as List? ?? const []);
    final dependents = (data['dependents'] as List? ?? const []);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.page,
          AppSpacing.lg,
          AppSpacing.page,
          32 + MediaQuery.paddingOf(context).bottom,
        ),
        children: [
          Text(
            '${task['taskCode'] ?? ''} · ${task['title'] ?? 'Task review'}',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              StatusBadge(status),
              if (review['isCritical'] == true) const StatusBadge('critical'),
              if (review['isOverdue'] == true) const StatusBadge('overdue'),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          _InfoCard(
            title: 'Task and submission',
            children: [
              _InfoRow(
                label: 'Project',
                value: '${task['projectName'] ?? '—'}',
              ),
              _InfoRow(label: 'Discipline', value: _title(task['discipline'])),
              _InfoRow(label: 'Priority', value: _title(task['priority'])),
              _InfoRow(
                label: 'Progress',
                value: '${task['progressPercentage'] ?? 0}%',
              ),
              _InfoRow(
                label: 'Submission',
                value: '#${review['submissionNumber'] ?? 1}',
              ),
              if ('${review['completionNote'] ?? ''}'.trim().isNotEmpty)
                _InfoRow(
                  label: 'Completion note',
                  value: '${review['completionNote']}',
                ),
              if ('${task['description'] ?? ''}'.trim().isNotEmpty)
                _InfoRow(label: 'Description', value: '${task['description']}'),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          _InfoCard(
            title: 'Submitted evidence (${evidence.length})',
            children: evidence.isEmpty
                ? const [Text('No evidence was attached to this submission.')]
                : evidence
                      .whereType<Map>()
                      .map(
                        (item) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.attach_file_rounded),
                          title: Text('${item['filename'] ?? 'Attachment'}'),
                          subtitle: Text(
                            '${item['mimeType'] ?? item['mime_type'] ?? ''}',
                          ),
                        ),
                      )
                      .toList(),
          ),
          const SizedBox(height: AppSpacing.md),
          _InfoCard(
            title: 'Dependency impact',
            children: [
              Text('${dependencies.length} predecessors'),
              const SizedBox(height: 6),
              Text('${dependents.length} dependent tasks'),
              if (review['blocksDependentWork'] == true) ...[
                const SizedBox(height: 9),
                const Text(
                  'Approval is currently gating downstream work.',
                  style: TextStyle(
                    color: AppColors.warning,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ],
          ),
          if (canDecide) ...[
            const SizedBox(height: AppSpacing.xl),
            if (status == 'pending')
              OutlinedButton.icon(
                onPressed: _busy
                    ? null
                    : () => _startReview('${review['taskId']}'),
                icon: const Icon(Icons.play_arrow_rounded),
                label: const Text('Start Review'),
              ),
            const SizedBox(height: 10),
            FilledButton.icon(
              onPressed: _busy
                  ? null
                  : () => _showAction(
                      _ReviewAction.approve,
                      '${review['taskId']}',
                    ),
              icon: const Icon(Icons.check_circle_outline_rounded),
              label: const Text('Approve Submission'),
              style: FilledButton.styleFrom(backgroundColor: AppColors.success),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () => _showAction(
                      _ReviewAction.clarification,
                      '${review['taskId']}',
                    ),
              icon: const Icon(Icons.help_outline_rounded),
              label: const Text('Request Clarification'),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _busy
                  ? null
                  : () => _showAction(
                      _ReviewAction.reject,
                      '${review['taskId']}',
                    ),
              icon: const Icon(Icons.replay_rounded),
              label: const Text('Request Rework'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.danger,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _startReview(String taskId) async {
    await _execute(
      () => ref
          .read(apiClientProvider)
          .put<Object?>(ApiEndpoints.startReview(taskId)),
      'Review started.',
    );
  }

  Future<void> _showAction(_ReviewAction action, String taskId) async {
    final comments = TextEditingController();
    final reason = TextEditingController();
    final corrections = TextEditingController();
    final submitted = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(switch (action) {
          _ReviewAction.approve => 'Approve Submission',
          _ReviewAction.reject => 'Request Rework',
          _ReviewAction.clarification => 'Request Clarification',
        }),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (action == _ReviewAction.approve)
                const Text(
                  'Approval marks this task complete and may unlock dependent work.',
                ),
              if (action == _ReviewAction.reject) ...[
                TextField(
                  controller: reason,
                  decoration: const InputDecoration(
                    labelText: 'Rejection reason *',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: corrections,
                  minLines: 2,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    labelText: 'Required corrections *',
                  ),
                ),
                const SizedBox(height: 12),
              ],
              TextField(
                controller: comments,
                minLines: 3,
                maxLines: 5,
                decoration: InputDecoration(
                  labelText: action == _ReviewAction.clarification
                      ? 'Clarification question *'
                      : action == _ReviewAction.reject
                      ? 'Review comments *'
                      : 'Review note (optional)',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (action == _ReviewAction.reject &&
                  (reason.text.trim().isEmpty ||
                      corrections.text.trim().isEmpty ||
                      comments.text.trim().isEmpty)) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  const SnackBar(
                    content: Text('Complete all required fields.'),
                  ),
                );
                return;
              }
              if (action == _ReviewAction.clarification &&
                  comments.text.trim().length < 3) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  const SnackBar(
                    content: Text('Enter a clarification question.'),
                  ),
                );
                return;
              }
              Navigator.pop(dialogContext, true);
            },
            child: Text(action == _ReviewAction.approve ? 'Approve' : 'Submit'),
          ),
        ],
      ),
    );
    if (submitted != true || !mounted) {
      comments.dispose();
      reason.dispose();
      corrections.dispose();
      return;
    }
    final api = ref.read(apiClientProvider);
    switch (action) {
      case _ReviewAction.approve:
        await _execute(
          () => api.put<Object?>(
            ApiEndpoints.approveTask(taskId),
            data: {'comments': comments.text.trim()},
          ),
          'Submission approved successfully.',
        );
      case _ReviewAction.reject:
        await _execute(
          () => api.put<Object?>(
            ApiEndpoints.rejectTask(taskId),
            data: {
              'comments': comments.text.trim(),
              'rejectionReason': reason.text.trim(),
              'requiredCorrections': corrections.text.trim(),
            },
          ),
          'Rework request recorded.',
        );
      case _ReviewAction.clarification:
        await _execute(
          () => api.put<Object?>(
            ApiEndpoints.requestClarification(taskId),
            data: {'question': comments.text.trim()},
          ),
          'Clarification requested.',
        );
    }
    comments.dispose();
    reason.dispose();
    corrections.dispose();
  }

  Future<void> _execute(
    Future<Object?> Function() action,
    String success,
  ) async {
    setState(() => _busy = true);
    try {
      await action();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(success), backgroundColor: AppColors.success),
      );
      await _load();
    } on NetworkException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(error.message),
            backgroundColor: AppColors.danger,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.title, required this.children});
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.md),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(AppRadius.large),
      border: Border.all(color: AppColors.border),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        ...children,
      ],
    ),
  );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 112,
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.textSecondary,
              fontWeight: FontWeight.w700,
              fontSize: 12,
            ),
          ),
        ),
        Expanded(child: Text(value)),
      ],
    ),
  );
}

String _title(dynamic value) => '${value ?? '—'}'
    .replaceAll('_', ' ')
    .split(' ')
    .map(
      (word) =>
          word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}',
    )
    .join(' ');
