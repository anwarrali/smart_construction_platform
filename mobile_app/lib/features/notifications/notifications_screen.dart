import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/status_badge.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/notification_visuals.dart';
import '../../models/notification_item.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/l10n/notification_text.dart';

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
  Object? _error;

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
          _error = error;
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
            Text(context.l10n.notificationsTitle),
            if (unreadCount > 0)
              Text(
                context.l10n.notificationsUnreadCount(unreadCount),
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
              child: Text(
                context.l10n.notificationsReadAll,
                style: const TextStyle(color: Colors.white),
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
                    label: context.l10n.commonAll,
                    selected: !_unreadOnly,
                    onTap: () => _setFilter(false),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _FilterButton(
                    label: context.l10n.notificationsFilterUnread,
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
      return LoadingView(label: context.l10n.notificationsLoading);
    }
    if (_error != null) {
      return MessageView(
        icon: Icons.cloud_off_rounded,
        title: context.l10n.commonUnavailable(
          context.l10n.notificationsTitle,
        ),
        message: context.l10n.describeError(_error),
        onAction: _load,
      );
    }
    if (_items.isEmpty) {
      return MessageView(
        icon: Icons.notifications_none_rounded,
        title: _unreadOnly
            ? context.l10n.notificationsEmptyUnreadTitle
            : context.l10n.notificationsEmptyTitle,
        message: _unreadOnly
            ? context.l10n.notificationsEmptyUnreadBody
            : context.l10n.notificationsEmptyBody,
      );
    }

    final grouped = <String, List<NotificationItem>>{};
    for (final item in _items) {
      grouped.putIfAbsent(_dateLabel(context, item.createdAt), () => []).add(item);
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
                      color: AppColors.mutedForeground,
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
        ).showSnackBar(
          SnackBar(content: Text(context.l10n.describeError(error))),
        );
      }
    }
  }

  String _dateLabel(BuildContext context, DateTime date) {
    final now = DateTime.now();
    final value = DateTime(date.year, date.month, date.day);
    final today = DateTime(now.year, now.month, now.day);
    if (value == today) return context.l10n.commonToday;
    if (value == today.subtract(const Duration(days: 1))) {
      return context.l10n.commonYesterday;
    }
    return context.formatShortDate(date);
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
    borderRadius: BorderRadius.circular(AppRadius.panel),
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.symmetric(vertical: 11),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: selected ? AppColors.primary : Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.panel),
        border: Border.all(color: selected ? AppColors.primary : AppColors.border),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: selected ? Colors.white : AppColors.foreground,
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
    final (icon, tone) = item.visual;
    // The web list marks only IMPORTANT and CRITICAL with an accent edge and
    // a badge; everything else stays quiet so the loud ones actually stand
    // out. Mobile follows the same rule rather than colouring every row.
    final accentEdge = item.accent;
    return Material(
      // Critical is the one priority that also tints its ground, so it
      // survives a glance in bright sun. Everything else is distinguished
      // only by read/unread, which is what keeps the loud ones legible.
      color: item.isCritical
          ? AppColors.stateOverdueWash
          : item.isRead
          ? Colors.white
          : AppColors.stateProgressWash,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.panel),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.panel),
            // Uniform border only. A non-uniform `Border` combined with a
            // `borderRadius` is invalid in Flutter and silently rendered the
            // whole card blank — the priority accent is drawn as a strip
            // inside instead (see `_PriorityEdge` below).
            border: Border.all(
              color: item.isCritical
                  ? AppColors.stateOverdue.withValues(alpha: .35)
                  : item.isRead
                  ? AppColors.border
                  : AppColors.stateProgress.withValues(alpha: .22),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // The priority edge: a directional strip that mirrors under RTL
              // because it is the first child of a directional Row.
              //
              // Given an explicit height rather than `CrossAxisAlignment
              // .stretch`: stretch needs a bounded cross-axis extent, which a
              // Row inside a scrolling Column does not have, and asking for it
              // took the entire list down.
              if (accentEdge != null) ...[
                Container(
                  // Critical gets a heavier rule than important: the ramp has
                  // to be readable as a ramp, not just as "coloured".
                  width: item.isCritical ? 4 : 3,
                  height: 42,
                  decoration: BoxDecoration(
                    color: accentEdge,
                    borderRadius: BorderRadius.circular(AppRadius.chip),
                  ),
                ),
                const SizedBox(width: 10),
              ],
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
                            _titleOf(context, item),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontWeight: FontWeight.w800),
                          ),
                        ),
                        if (!item.isRead)
                          const Padding(
                            padding: EdgeInsetsDirectional.only(start: 8),
                            child: CircleAvatar(
                              radius: 4,
                              backgroundColor: AppColors.stateProgress,
                            ),
                          ),
                      ],
                    ),
                    if (accentEdge != null || item.isReminder)
                      Padding(
                        padding: const EdgeInsets.only(top: 5),
                        child: Wrap(
                          spacing: 6,
                          children: [
                            PriorityBadge(item.priority),
                            if (item.isReminder) const ReminderChip(),
                          ],
                        ),
                      ),
                    const SizedBox(height: 4),
                    Text(
                      context.l10n.notificationBody(item),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 7),
                    Text(
                      context.formatDateTime(item.createdAt),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              const Icon(
                Icons.chevron_right_rounded,
                color: AppColors.mutedForeground,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The notification's headline, translated when the server named it.
///
/// A notification that arrives with no `messageKey` at all still has the
/// server's English title; only a completely titleless row falls back to a
/// translated placeholder.
String _titleOf(BuildContext context, NotificationItem item) {
  final title = context.l10n.notificationTitle(item);
  return title.isEmpty ? context.l10n.notificationFallbackTitle : title;
}
