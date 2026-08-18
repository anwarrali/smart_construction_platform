import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/notification_visuals.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/notification_item.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/l10n/notification_text.dart';

class NotificationDetailScreen extends StatelessWidget {
  const NotificationDetailScreen({super.key, required this.notification});
  final NotificationItem? notification;

  @override
  Widget build(BuildContext context) {
    final item = notification;
    if (item == null) {
      return Scaffold(
        appBar: AppBar(title: Text(context.l10n.notificationFallbackTitle)),
        body: Center(
          child: Text(context.l10n.notificationDetailMustOpen),
        ),
      );
    }
    final destination = _destination(item);
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.notificationDetailTitle)),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.page,
            AppSpacing.xl,
            AppSpacing.page,
            AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
          ),
          children: [
            // The detail used to show one generic blue bell for everything, so
            // a critical escalation and a routine task update were
            // indistinguishable once opened. Type picks the icon, priority
            // picks the accent — the same two decisions the list makes.
            Builder(
              builder: (context) {
                final (icon, tone) = item.visual;
                final accent = item.accent ?? tone;
                return Container(
                  width: 58,
                  height: 58,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: .1),
                    borderRadius: BorderRadius.circular(AppRadius.panel),
                  ),
                  child: Icon(icon, color: accent, size: 29),
                );
              },
            ),
            const SizedBox(height: AppSpacing.lg),
            if (item.accent != null || item.isReminder)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    PriorityBadge(item.priority),
                    if (item.isReminder) const ReminderChip(),
                  ],
                ),
              ),
            Text(
              context.l10n.notificationTitle(item),
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(
              context.formatDateTime(item.createdAt),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.xl),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Text(
                  context.l10n.notificationBody(item),
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            if (destination != null)
              FilledButton.icon(
                onPressed: () => context.go(destination),
                icon: const Icon(Icons.open_in_new_rounded),
                label: Text(_destinationLabel(context, item)),
              ),
          ],
        ),
      ),
    );
  }

  String? _destination(NotificationItem item) {
    if (item.taskId != null) return '/tasks/${item.taskId}';
    final type = (item.relatedEntityType ?? item.type).toLowerCase();
    if (type.contains('message')) return '/messages';
    if (type.contains('issue')) return '/issues';
    if (type.contains('review')) return '/reviews';
    if (type.contains('report')) return '/reports';
    if (item.projectId != null || type.contains('project')) return '/home';
    return null;
  }

  String _destinationLabel(BuildContext context, NotificationItem item) {
    final type = (item.relatedEntityType ?? item.type).toLowerCase();
    if (item.taskId != null) return context.l10n.notificationOpenTask;
    if (type.contains('message')) return context.l10n.notificationOpenMessages;
    if (type.contains('issue')) return context.l10n.notificationOpenIssues;
    if (type.contains('review')) return context.l10n.notificationOpenReviews;
    if (type.contains('report')) return context.l10n.notificationOpenReports;
    return context.l10n.notificationOpenProject;
  }
}
