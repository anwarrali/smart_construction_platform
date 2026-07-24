import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../models/notification_item.dart';
import '../projects/project_context_view_model.dart';

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() =>
      _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  List<NotificationItem> _items = const [];
  bool _loading = true;
  bool _unreadOnly = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    final user = ref.read(sessionProvider).user;
    final project = ref.read(projectContextProvider).selected;
    try {
      final result = await ref
          .read(notificationRepositoryProvider)
          .list(
            projectId: user?.role == 'engineer' ? project?.id : null,
            unread: _unreadOnly ? true : null,
          );
      if (mounted) {
        setState(() {
          _items = result;
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
    final unreadCount = _items.where((item) => !item.isRead).length;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Notifications'),
            if (unreadCount > 0)
              Text(
                '$unreadCount unread',
                style: const TextStyle(
                  fontSize: 11,
                  color: Colors.white70,
                  fontWeight: FontWeight.w400,
                ),
              ),
          ],
        ),
        actions: [
          if (unreadCount > 0)
            TextButton(
              onPressed: _markAllRead,
              child: const Text(
                'Read all',
                style: TextStyle(color: Colors.white),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.page,
              AppSpacing.md,
              AppSpacing.page,
              AppSpacing.xs,
            ),
            child: Row(
              children: [
                Expanded(
                  child: _FilterButton(
                    label: 'All',
                    selected: !_unreadOnly,
                    onTap: () => _setFilter(false),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _FilterButton(
                    label: 'Unread',
                    selected: _unreadOnly,
                    onTap: () => _setFilter(true),
                  ),
                ),
              ],
            ),
          ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const LoadingView(label: 'Loading notifications');
    }
    if (_error != null) {
      return MessageView(
        icon: Icons.cloud_off_rounded,
        title: 'Notifications unavailable',
        message: _error!,
        onAction: _load,
      );
    }
    if (_items.isEmpty) {
      return MessageView(
        icon: Icons.notifications_none_rounded,
        title: _unreadOnly
            ? 'No unread notifications'
            : 'You are all caught up',
        message: _unreadOnly
            ? 'New unread notifications will appear here.'
            : 'Project updates and team activity will appear here.',
      );
    }

    final grouped = <String, List<NotificationItem>>{};
    for (final item in _items) {
      grouped.putIfAbsent(_dateLabel(item.createdAt), () => []).add(item);
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.page,
          AppSpacing.sm,
          AppSpacing.page,
          24 + MediaQuery.paddingOf(context).bottom,
        ),
        children: grouped.entries
            .expand(
              (entry) => [
                Padding(
                  padding: const EdgeInsets.only(top: 10, bottom: 8),
                  child: Text(
                    entry.key.toUpperCase(),
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      letterSpacing: .8,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ),
                ...entry.value.map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 9),
                    child: _NotificationCard(
                      item: item,
                      onTap: () => _open(item),
                    ),
                  ),
                ),
              ],
            )
            .toList(),
      ),
    );
  }

  void _setFilter(bool unread) {
    if (_unreadOnly == unread) return;
    setState(() => _unreadOnly = unread);
    _load();
  }

  Future<void> _open(NotificationItem item) async {
    var opened = item;
    if (!item.isRead) {
      try {
        await ref.read(notificationRepositoryProvider).markRead(item.id);
        opened = item.copyWith(isRead: true);
        if (mounted) {
          setState(
            () => _items = _items
                .map((value) => value.id == item.id ? opened : value)
                .toList(),
          );
        }
      } catch (_) {
        // Detail remains accessible even if marking read fails temporarily.
      }
    }
    if (mounted) context.push('/notifications/${item.id}', extra: opened);
  }

  Future<void> _markAllRead() async {
    final user = ref.read(sessionProvider).user;
    final project = ref.read(projectContextProvider).selected;
    try {
      await ref
          .read(notificationRepositoryProvider)
          .markAllRead(
            projectId: user?.role == 'engineer' ? project?.id : null,
          );
      if (mounted) {
        setState(
          () => _items = _items
              .map((item) => item.copyWith(isRead: true))
              .toList(),
        );
      }
    } on NetworkException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  String _dateLabel(DateTime date) {
    final now = DateTime.now();
    final value = DateTime(date.year, date.month, date.day);
    final today = DateTime(now.year, now.month, now.day);
    if (value == today) return 'Today';
    if (value == today.subtract(const Duration(days: 1))) return 'Yesterday';
    return DateFormat.yMMMd().format(date);
  }
}

class _FilterButton extends StatelessWidget {
  const _FilterButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });
  final String label;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => InkWell(
    borderRadius: BorderRadius.circular(AppRadius.medium),
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(vertical: 11),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: selected ? AppColors.navy : Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.medium),
        border: Border.all(color: selected ? AppColors.navy : AppColors.border),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: selected ? Colors.white : AppColors.textPrimary,
          fontWeight: FontWeight.w800,
        ),
      ),
    ),
  );
}

class _NotificationCard extends StatelessWidget {
  const _NotificationCard({required this.item, required this.onTap});
  final NotificationItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final (icon, tone) = _notificationVisual(item.type);
    return Material(
      color: item.isRead ? Colors.white : AppColors.infoSoft,
      borderRadius: BorderRadius.circular(AppRadius.large),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.large),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.large),
            border: Border.all(
              color: item.isRead
                  ? AppColors.border
                  : AppColors.info.withValues(alpha: .22),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: .1),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: Icon(icon, color: tone, size: 21),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ),
                        if (!item.isRead)
                          const Padding(
                            padding: EdgeInsets.only(left: 8),
                            child: CircleAvatar(
                              radius: 4,
                              backgroundColor: AppColors.info,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item.message,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 7),
                    Text(
                      DateFormat.MMMd().add_jm().format(item.createdAt),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              const Icon(
                Icons.chevron_right_rounded,
                color: AppColors.textSecondary,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

(IconData, Color) _notificationVisual(String type) =>
    switch (type.toLowerCase()) {
      'task_assigned' ||
      'task_updated' ||
      'task_overdue' => (Icons.task_alt_rounded, AppColors.info),
      'review_submitted' ||
      'review_approved' => (Icons.fact_check_outlined, AppColors.success),
      'review_rejected' ||
      'rework_requested' => (Icons.replay_rounded, AppColors.warning),
      'issue_created' ||
      'issue_updated' => (Icons.report_problem_outlined, AppColors.danger),
      'message' => (Icons.forum_outlined, AppColors.info),
      _ => (Icons.notifications_outlined, AppColors.navy),
    };
