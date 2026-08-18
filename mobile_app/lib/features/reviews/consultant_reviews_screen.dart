import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/status_badge.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

class ConsultantReviewsScreen extends ConsumerStatefulWidget {
  const ConsultantReviewsScreen({super.key});

  @override
  ConsumerState<ConsultantReviewsScreen> createState() =>
      _ConsultantReviewsScreenState();
}

class _ConsultantReviewsScreenState
    extends ConsumerState<ConsultantReviewsScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return const [];
    final raw = await ref
        .read(apiClientProvider)
        .get<List<dynamic>>(ApiEndpoints.consultantReviews(project.id));
    return raw.whereType<Map<String, dynamic>>().toList();
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.reviewsPendingTitle)),
      body: project == null
          ? MessageView(
              icon: Icons.apartment_rounded,
              title: context.l10n.commonSelectProject,
              message: context.l10n.reviewsSelectProjectBody,
            )
          : FutureBuilder<List<Map<String, dynamic>>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return LoadingView(label: context.l10n.reviewsLoading);
                }
                if (snapshot.hasError) {
                  return MessageView(
                    icon: Icons.cloud_off_rounded,
                    title: context.l10n.commonUnavailable(
                      context.l10n.reviewsTitle,
                    ),
                    message: context.l10n.describeError(snapshot.error),
                    onAction: _refresh,
                  );
                }
                final items = snapshot.data ?? const [];
                if (items.isEmpty) {
                  return MessageView(
                    icon: Icons.fact_check_outlined,
                    title: context.l10n.reviewsEmptyTitle,
                    message: context.l10n.reviewsEmptyBody,
                  );
                }
                return RefreshIndicator(
                  onRefresh: _refresh,
                  child: ListView.separated(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.page,
                      AppSpacing.lg,
                      AppSpacing.page,
                      96 + MediaQuery.paddingOf(context).bottom,
                    ),
                    itemCount: items.length,
                    separatorBuilder: (_, __) =>
                        const SizedBox(height: AppSpacing.sm),
                    itemBuilder: (context, index) =>
                        _ReviewCard(item: items[index]),
                  ),
                );
              },
            ),
    );
  }
}

class _ReviewCard extends StatelessWidget {
  const _ReviewCard({required this.item});
  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final critical = item['isCritical'] == true;
    final overdue = item['isOverdue'] == true;
    final submitted = DateTime.tryParse('${item['submittedAt'] ?? ''}');
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.panel),
        onTap: () => context.push('/reviews/${item['id']}'),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: critical
                          ? AppColors.stateOverdueWash
                          : AppColors.muted,
                      borderRadius: BorderRadius.circular(AppRadius.panel),
                    ),
                    child: Icon(
                      critical
                          ? Icons.priority_high_rounded
                          : Icons.fact_check_outlined,
                      color: critical ? AppColors.destructive : AppColors.primary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${item['taskCode'] ?? ''} · '
                          '${item['taskTitle'] ?? context.l10n.reviewSubmissionFallback}',
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${context.l10n.disciplineLabel('${item['discipline'] ?? ''}')}'
                          ' · '
                          '${context.l10n.priorityLabel('${item['priority'] ?? ''}')}',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right_rounded),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 7,
                runSpacing: 7,
                children: [
                  StatusBadge('${item['reviewStatus'] ?? 'pending'}'),
                  if (critical)
                    _Tag(label: context.l10n.reviewCritical, danger: true),
                  if (overdue)
                    _Tag(label: context.l10n.reviewOverdue, danger: true),
                  if (item['isResubmission'] == true)
                    _Tag(
                      label: context.l10n.reviewAttempt(
                        context.formatInt(item['submissionNumber'] ?? 2),
                      ),
                    ),
                  _Tag(
                    label: context.l10n.reviewEvidenceCount(
                      (item['evidenceCount'] ?? 0) as int,
                    ),
                  ),
                ],
              ),
              if (submitted != null) ...[
                const SizedBox(height: 10),
                Text(
                  context.l10n.reviewSubmittedAt(
                    context.formatDateTime(submitted),
                  ),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label, this.danger = false});
  final String label;
  final bool danger;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
    decoration: BoxDecoration(
      color: danger ? AppColors.stateOverdueWash : AppColors.muted,
      borderRadius: BorderRadius.circular(30),
    ),
    child: Text(
      label,
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        color: danger ? AppColors.destructive : AppColors.mutedForeground,
      ),
    ),
  );
}


