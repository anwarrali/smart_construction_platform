import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../models/notification_item.dart';

class NotificationDetailScreen extends StatelessWidget {
  const NotificationDetailScreen({super.key, required this.notification});
  final NotificationItem? notification;

  @override
  Widget build(BuildContext context) {
    final item = notification;
    if (item == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Notification')),
        body: const Center(
          child: Text(
            'This notification must be opened from the notification list.',
          ),
        ),
      );
    }
    final destination = _destination(item);
    return Scaffold(
      appBar: AppBar(title: const Text('Notification Details')),
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
            Container(
              width: 58,
              height: 58,
              decoration: BoxDecoration(
                color: AppColors.infoSoft,
                borderRadius: BorderRadius.circular(AppRadius.large),
              ),
              child: const Icon(
                Icons.notifications_active_outlined,
                color: AppColors.info,
                size: 29,
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            Text(item.title, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Text(
              DateFormat.yMMMd().add_jm().format(item.createdAt),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: AppSpacing.xl),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Text(
                  item.message,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            if (destination != null)
              FilledButton.icon(
                onPressed: () => context.go(destination),
                icon: const Icon(Icons.open_in_new_rounded),
                label: Text(_destinationLabel(item)),
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

  String _destinationLabel(NotificationItem item) {
    final type = (item.relatedEntityType ?? item.type).toLowerCase();
    if (item.taskId != null) return 'Open Task';
    if (type.contains('message')) return 'Open Messages';
    if (type.contains('issue')) return 'Open Issues';
    if (type.contains('review')) return 'Open Reviews';
    if (type.contains('report')) return 'Open Reports';
    return 'Open Project';
  }
}
