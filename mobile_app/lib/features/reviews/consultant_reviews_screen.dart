import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/status_badge.dart';
import '../projects/project_context_view_model.dart';

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
      appBar: AppBar(title: const Text('Pending Reviews')),
      body: project == null
          ? const MessageView(
              icon: Icons.apartment_rounded,
              title: 'Select a project',
              message: 'Choose a project before opening consultant reviews.',
            )
          : FutureBuilder<List<Map<String, dynamic>>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const LoadingView(label: 'Loading review submissions');
                }
                if (snapshot.hasError) {
                  return MessageView(
                    icon: Icons.cloud_off_rounded,
                    title: 'Reviews unavailable',
                    message: '${snapshot.error}',
                    onAction: _refresh,
                  );
                }
                final items = snapshot.data ?? const [];
                if (items.isEmpty) {
                  return const MessageView(
                    icon: Icons.fact_check_outlined,
                    title: 'Nothing waiting for review',
                    message:
                        'New submissions matching your discipline will appear here.',
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
        borderRadius: BorderRadius.circular(AppRadius.large),
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
                          ? AppColors.dangerSoft
                          : AppColors.surfaceMuted,
                      borderRadius: BorderRadius.circular(AppRadius.medium),
                    ),
                    child: Icon(
                      critical
                          ? Icons.priority_high_rounded
                          : Icons.fact_check_outlined,
                      color: critical ? AppColors.danger : AppColors.navy,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${item['taskCode'] ?? ''} · ${item['taskTitle'] ?? 'Review submission'}',
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${_label(item['discipline'])} · ${_label(item['priority'])}',
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
                  if (critical) const _Tag(label: 'Critical', danger: true),
                  if (overdue) const _Tag(label: 'Overdue', danger: true),
                  if (item['isResubmission'] == true)
                    _Tag(label: 'Attempt ${item['submissionNumber'] ?? 2}'),
                  _Tag(label: '${item['evidenceCount'] ?? 0} evidence'),
                ],
              ),
              if (submitted != null) ...[
                const SizedBox(height: 10),
                Text(
                  'Submitted ${DateFormat.MMMd().add_jm().format(submitted.toLocal())}',
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
      color: danger ? AppColors.dangerSoft : AppColors.surfaceMuted,
      borderRadius: BorderRadius.circular(30),
    ),
    child: Text(
      label,
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        color: danger ? AppColors.danger : AppColors.textSecondary,
      ),
    ),
  );
}

String _label(dynamic value) => '${value ?? '—'}'
    .replaceAll('_', ' ')
    .split(' ')
    .map(
      (word) =>
          word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}',
    )
    .join(' ');
