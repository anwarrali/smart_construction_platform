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
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

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
  Object? _error;

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
          _error = error;
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
      appBar: AppBar(title: Text(context.l10n.reviewSubmissionTitle)),
      body: _loading
          ? LoadingView(label: context.l10n.reviewLoadingSubmission)
          : _error != null || data == null || review == null || task == null
          ? MessageView(
              icon: Icons.error_outline_rounded,
              title: context.l10n.reviewUnableToOpen,
              message: _error != null
                  ? context.l10n.describeError(_error)
                  : context.l10n.reviewNotFound,
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
            '${task['taskCode'] ?? ''} · '
            '${task['title'] ?? context.l10n.reviewTaskReview}',
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
            title: context.l10n.reviewTaskAndSubmission,
            children: [
              _InfoRow(
                label: context.l10n.commonProject,
                value: '${task['projectName'] ?? '—'}',
              ),
              _InfoRow(
                label: context.l10n.commonDiscipline,
                value: context.l10n.disciplineLabel(
                  '${task['discipline'] ?? ''}',
                ),
              ),
              _InfoRow(
                label: context.l10n.commonPriority,
                value: context.l10n.priorityLabel('${task['priority'] ?? ''}'),
              ),
              _InfoRow(
                label: context.l10n.commonProgress,
                value: context.formatPercent(
                  (task['progressPercentage'] ?? 0) as num,
                ),
              ),
              _InfoRow(
                label: context.l10n.reviewSubmission,
                value: '#${review['submissionNumber'] ?? 1}',
              ),
              if ('${review['completionNote'] ?? ''}'.trim().isNotEmpty)
                _InfoRow(
                  label: context.l10n.reviewCompletionNote,
                  value: '${review['completionNote']}',
                ),
              if ('${task['description'] ?? ''}'.trim().isNotEmpty)
                _InfoRow(
                  label: context.l10n.commonDescription,
                  value: '${task['description']}',
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          _InfoCard(
            title: context.l10n.reviewSubmittedEvidence(evidence.length),
            children: evidence.isEmpty
                ? [Text(context.l10n.reviewNoEvidence)]
                : evidence
                      .whereType<Map>()
                      .map(
                        (item) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.attach_file_rounded),
                          title: Text(
                            '${item['filename'] ?? context.l10n.reviewAttachment}',
                          ),
                          subtitle: Text(
                            '${item['mimeType'] ?? item['mime_type'] ?? ''}',
                          ),
                        ),
                      )
                      .toList(),
          ),
          const SizedBox(height: AppSpacing.md),
          _InfoCard(
            title: context.l10n.reviewDependencyImpact,
            children: [
              Text(context.l10n.reviewPredecessors(dependencies.length)),
              const SizedBox(height: 6),
              Text(context.l10n.reviewDependentTasks(dependents.length)),
              if (review['blocksDependentWork'] == true) ...[
                const SizedBox(height: 9),
                Text(
                  context.l10n.reviewGatingWork,
                  style: const TextStyle(
                    color: AppColors.stateReview,
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
                label: Text(context.l10n.reviewStart),
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
              label: Text(context.l10n.reviewApproveSubmission),
              style: FilledButton.styleFrom(backgroundColor: AppColors.stateVerified),
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
              label: Text(context.l10n.reviewRequestClarification),
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
              label: Text(context.l10n.reviewRequestRework),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.destructive,
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
      context.l10n.reviewStarted,
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
          _ReviewAction.approve => context.l10n.reviewApproveSubmission,
          _ReviewAction.reject => context.l10n.reviewRequestRework,
          _ReviewAction.clarification =>
            context.l10n.reviewRequestClarification,
        }),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (action == _ReviewAction.approve)
                Text(context.l10n.reviewApprovalHint),
              if (action == _ReviewAction.reject) ...[
                TextField(
                  controller: reason,
                  decoration: InputDecoration(
                    labelText: context.l10n.reviewRejectionReasonRequired,
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: corrections,
                  minLines: 2,
                  maxLines: 4,
                  decoration: InputDecoration(
                    labelText: context.l10n.reviewRequiredCorrections,
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
            child: Text(context.l10n.commonCancel),
          ),
          FilledButton(
            onPressed: () {
              if (action == _ReviewAction.reject &&
                  (reason.text.trim().isEmpty ||
                      corrections.text.trim().isEmpty ||
                      comments.text.trim().isEmpty)) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  SnackBar(
                    content: Text(
                      context.l10n.validationCompleteRequiredFields,
                    ),
                  ),
                );
                return;
              }
              if (action == _ReviewAction.clarification &&
                  comments.text.trim().length < 3) {
                ScaffoldMessenger.of(dialogContext).showSnackBar(
                  SnackBar(
                    content: Text(
                      context.l10n.validationEnterClarificationQuestion,
                    ),
                  ),
                );
                return;
              }
              Navigator.pop(dialogContext, true);
            },
            child: Text(action == _ReviewAction.approve
                ? context.l10n.commonApprove
                : context.l10n.commonSubmit),
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
          context.l10n.reviewApproved,
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
          context.l10n.reviewReworkRecorded,
        );
      case _ReviewAction.clarification:
        await _execute(
          () => api.put<Object?>(
            ApiEndpoints.requestClarification(taskId),
            data: {'question': comments.text.trim()},
          ),
          context.l10n.reviewClarificationRequested,
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
        SnackBar(content: Text(success), backgroundColor: AppColors.stateVerified),
      );
      await _load();
    } on NetworkException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(context.l10n.describeError(error)),
            backgroundColor: AppColors.destructive,
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
      borderRadius: BorderRadius.circular(AppRadius.panel),
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
              color: AppColors.mutedForeground,
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
