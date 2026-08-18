import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/widgets/async_views.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/entity_actions.dart';
import '../../core/widgets/status_badge.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

/// The description line plus whatever state chips the record carries.
///
/// Kept as its own widget because every collection screen in the app renders
/// through [RemoteCollectionScreen], so this is the single place that decides
/// how a generic record advertises its state.
class _Subtitle extends StatelessWidget {
  const _Subtitle({required this.text, this.status, this.severity});

  final String text;
  final String? status;
  final String? severity;

  @override
  Widget build(BuildContext context) {
    final chips = <Widget>[
      if (status != null && status!.trim().isNotEmpty) StatusBadge(status!),
      // Severity only earns a chip when it says something the status does
      // not — a "low" severity next to an "open" status is just noise.
      if (severity != null &&
          const {'high', 'critical'}.contains(severity!.toLowerCase()))
        StatusBadge(
          severity!,
          compact: true,
          // Severity shares the ramp with statuses but not the vocabulary;
          // without this it fell through to the raw lowercase value.
          label: context.l10n.priorityLabel(severity),
        ),
    ];
    if (chips.isEmpty && text.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (text.isNotEmpty)
            Text(text, maxLines: 2, overflow: TextOverflow.ellipsis),
          if (chips.isNotEmpty) ...[
            if (text.isNotEmpty) const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: chips),
          ],
        ],
      ),
    );
  }
}

class RemoteCollectionScreen extends ConsumerStatefulWidget {
  const RemoteCollectionScreen({
    super.key,
    required this.title,
    required this.path,
    required this.emptyMessage,
    required this.icon,
    this.createRoute,
    this.entityType,
  });
  final String title;
  final String path;
  final String emptyMessage;
  final IconData icon;
  final String? createRoute;

  /// The shareable entity type these records are — ISSUE, SITE_REPORT,
  /// DESIGN_CHANGE, DOCUMENT. Supplying it turns on the contextual actions
  /// (Forward / Ask for Opinion / Share) for every row; leaving it null keeps
  /// the list read-only, which is right for collections the server does not
  /// accept as shareable.
  final String? entityType;
  @override
  ConsumerState<RemoteCollectionScreen> createState() =>
      _RemoteCollectionScreenState();
}

class _RemoteCollectionScreenState
    extends ConsumerState<RemoteCollectionScreen> {
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(widget.title)),
    floatingActionButton: widget.createRoute == null
        ? null
        : FloatingActionButton.extended(
            onPressed: () async {
              await context.push(widget.createRoute!);
              if (mounted) setState(() {});
            },
            icon: const Icon(Icons.add_rounded),
            label: Text(context.l10n.commonCreate),
          ),
    body: FutureBuilder<dynamic>(
      future: ref.read(apiClientProvider).get<dynamic>(widget.path),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const LoadingView();
        }
        if (snapshot.hasError) {
          return MessageView(
            icon: Icons.cloud_off,
            title: context.l10n.commonUnavailable(widget.title),
            message: context.l10n.describeError(snapshot.error),
            onAction: () => setState(() {}),
          );
        }
        final raw = snapshot.data;
        final List items = raw is List
            ? raw
            : raw is Map
            ? (raw['items'] as List? ?? raw['data'] as List? ?? const [])
            : const [];
        if (items.isEmpty) {
          return MessageView(
            icon: widget.icon,
            title: context.l10n.commonNothingHereYet,
            message: widget.emptyMessage,
          );
        }
        return RefreshIndicator(
          onRefresh: () async => setState(() {}),
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.page,
              AppSpacing.lg,
              AppSpacing.page,
              104,
            ),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 10),
            itemBuilder: (context, index) {
              final item = items[index] is Map ? items[index] as Map : const {};
              final title =
                  item['title'] ??
                  item['name'] ??
                  item['subject'] ??
                  item['content'] ??
                  item['message'] ??
                  widget.title;
              // Status used to be a *fallback* for the subtitle text, so an
              // issue with a description showed no state at all. It is a
              // separate signal and gets the ramp chip instead.
              final subtitle =
                  item['description'] ??
                  item['summary'] ??
                  item['createdAt'] ??
                  '';
              final status = item['status']?.toString();
              final severity = item['severity']?.toString();
              final id = item['id']?.toString();
              final shareable =
                  widget.entityType != null &&
                  id != null &&
                  id.isNotEmpty &&
                  intentsForEntity(widget.entityType!).isNotEmpty;
              return Card(
                child: ListTile(
                  onTap: () => _showDetails(item, '$title'),
                  onLongPress: shareable
                      ? () => showEntityActions(
                          context: context,
                          entityType: widget.entityType!,
                          entityId: id,
                          entityTitle: '$title',
                        )
                      : null,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  leading: Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: AppColors.muted,
                      borderRadius: BorderRadius.circular(AppRadius.panel),
                    ),
                    child: Icon(widget.icon, color: AppColors.primary, size: 21),
                  ),
                  title: Text(
                    '$title',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: _Subtitle(
                    text: '$subtitle',
                    status: status,
                    severity: severity,
                  ),
                  trailing: shareable
                      ? IconButton(
                          tooltip: context.l10n.commonMoreActions,
                          icon: const Icon(
                            Icons.more_vert_rounded,
                            color: AppColors.mutedForeground,
                          ),
                          onPressed: () => showEntityActions(
                            context: context,
                            entityType: widget.entityType!,
                            entityId: id,
                            entityTitle: '$title',
                          ),
                        )
                      : const Icon(
                          Icons.chevron_right_rounded,
                          color: AppColors.mutedForeground,
                        ),
                ),
              );
            },
          ),
        );
      },
    ),
  );

  /// The record's detail, at mobile altitude.
  ///
  /// This used to enumerate every scalar field the API returned and label each
  /// one with its own JSON key uppercased — so a site manager was shown
  /// `PROJECT ID`, `IS ACTIVE`, `2026-08-17T09:14:22.481Z` and a bare
  /// `under_review`. That is a debugging view, not a product.
  ///
  /// Now it shows what a person on site actually needs — what it is, what
  /// state it is in, how urgent, when — every value passed through the
  /// localization layer, and nothing else. Full detail is the web's job, and
  /// the actions that *are* useful from a phone sit at the bottom of the
  /// sheet where they can be reached one-handed.
  void _showDetails(Map item, String title) {
    final id = item['id']?.toString();
    final shareable =
        widget.entityType != null &&
        id != null &&
        id.isNotEmpty &&
        intentsForEntity(widget.entityType!).isNotEmpty;
    final description =
        '${item['description'] ?? item['summary'] ?? item['notes'] ?? ''}'
            .trim();

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      useSafeArea: true,
      builder: (sheetContext) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .55,
        minChildSize: .3,
        maxChildSize: .9,
        builder: (sheetContext, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.page,
            0,
            AppSpacing.page,
            AppSpacing.xl,
          ),
          children: [
            Text(title, style: Theme.of(sheetContext).textTheme.headlineSmall),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if ('${item['status'] ?? ''}'.trim().isNotEmpty)
                  StatusBadge('${item['status']}'),
                if ('${item['severity'] ?? item['priority'] ?? ''}'
                    .trim()
                    .isNotEmpty)
                  StatusBadge(
                    '${item['severity'] ?? item['priority']}',
                    label: sheetContext.l10n.priorityLabel(
                      '${item['severity'] ?? item['priority']}',
                    ),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            Text(
              description.isEmpty
                  ? sheetContext.l10n.commonNoDescription
                  : description,
              style: Theme.of(sheetContext).textTheme.bodyLarge,
            ),
            const SizedBox(height: AppSpacing.lg),
            _MetaRow(
              label: sheetContext.l10n.commonCreated,
              value: _date(sheetContext, item['createdAt'] ?? item['reportDate']),
            ),
            _MetaRow(
              label: sheetContext.l10n.commonDue,
              value: _date(sheetContext, item['dueDate'] ?? item['targetDate']),
            ),
            _MetaRow(
              label: sheetContext.l10n.commonDiscipline,
              value: item['discipline'] == null
                  ? null
                  : sheetContext.l10n.disciplineLabel('${item['discipline']}'),
            ),
            if (shareable) ...[
              const SizedBox(height: AppSpacing.lg),
              for (final intent in intentsForEntity(widget.entityType!))
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: OutlinedButton.icon(
                    onPressed: () {
                      Navigator.pop(sheetContext);
                      showShareSheet(
                        context: context,
                        intent: intent,
                        entityType: widget.entityType,
                        entityId: id,
                      );
                    },
                    icon: Icon(intent.icon),
                    label: Text(intent.label(sheetContext.l10n)),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }

  /// Formats an API date, or returns null so the row is omitted entirely
  /// rather than showing an empty label or a raw ISO string.
  String? _date(BuildContext context, Object? value) {
    final parsed = DateTime.tryParse('${value ?? ''}');
    return parsed == null ? null : context.formatShortDate(parsed);
  }
}

/// One metadata line, dropped when it has no value.
class _MetaRow extends StatelessWidget {
  const _MetaRow({required this.label, required this.value});
  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    if (value == null || value!.trim().isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 110,
            child: Text(
              label,
              style: const TextStyle(
                color: AppColors.mutedForeground,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          Expanded(child: Text(value!)),
        ],
      ),
    );
  }
}
