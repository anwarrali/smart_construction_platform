import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/l10n/l10n_labels.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/widgets/async_views.dart';
import '../../models/field_submission.dart';
import '../projects/project_context_view_model.dart';

class WorkerSubmissionsScreen extends ConsumerWidget {
  const WorkerSubmissionsScreen({super.key, this.taskId, this.embedded = false});
  final String? taskId;
  final bool embedded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final project = ref.watch(projectContextProvider).selected;
    if (project == null) {
      return MessageView(
        icon: Icons.apartment,
        title: context.l10n.commonNoProjectSelected,
        message: context.l10n.commonSelectProjectFirst,
      );
    }
    final content = FutureBuilder<List<FieldSubmission>>(
      future: ref.read(fieldSubmissionRepositoryProvider).mine(project.id, taskId: taskId),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return LoadingView(label: context.l10n.evidenceLoading);
        }
        if (snapshot.hasError) {
          return MessageView(
            icon: Icons.cloud_off,
            title: context.l10n.commonUnavailable(
              context.l10n.evidenceTitle,
            ),
            message: context.l10n.describeError(snapshot.error),
          );
        }
        final items = snapshot.data ?? const [];
        if (items.isEmpty) {
          return Padding(
            padding: const EdgeInsets.all(20),
            child: Text(context.l10n.evidenceEmpty),
          );
        }
        return ListView.separated(
          shrinkWrap: embedded,
          physics: embedded ? const NeverScrollableScrollPhysics() : null,
          padding: const EdgeInsets.all(16),
          itemCount: items.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (context, index) => _SubmissionCard(item: items[index]),
        );
      },
    );
    return embedded ? content : Scaffold(
      appBar: AppBar(title: Text(context.l10n.evidenceMyTitle)),
      body: content,
    );
  }
}

class _SubmissionCard extends StatelessWidget {
  const _SubmissionCard({required this.item});
  final FieldSubmission item;

  @override
  Widget build(BuildContext context) {
    final rejected = item.status == 'REJECTED';
    final verified = item.status == 'VERIFIED';
    final color = verified ? Colors.green : rejected ? Colors.red : Colors.orange;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text(
                  DateFormat.yMMMd().add_jm().format(item.createdAt),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                )),
                Chip(
                  label: Text(context.l10n.statusLabel(item.status)),
                  backgroundColor: color.withValues(alpha: .12),
                  labelStyle: TextStyle(color: color, fontWeight: FontWeight.w700),
                ),
              ],
            ),
            if ((item.description ?? '').isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(item.description!),
            ],
            const SizedBox(height: 8),
            Text(context.l10n.evidencePhotoCount(item.photos.length)),
            if ((item.reviewComment ?? '').isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                color: color.withValues(alpha: .08),
                child: Text(item.reviewComment!),
              ),
            ],
            if (rejected) ...[
              const SizedBox(height: 10),
              FilledButton.icon(
                onPressed: () => context.push(
                  '/tasks/${item.taskId}/evidence/new?resubmission=${item.id}',
                ),
                icon: const Icon(Icons.refresh),
                label: Text(context.l10n.evidenceSubmitCorrected),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
