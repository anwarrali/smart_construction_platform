import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../app/dependency_injection.dart';
import '../../core/widgets/async_views.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';

class RemoteCollectionScreen extends ConsumerStatefulWidget {
  const RemoteCollectionScreen({
    super.key,
    required this.title,
    required this.path,
    required this.emptyMessage,
    required this.icon,
    this.createRoute,
  });
  final String title;
  final String path;
  final String emptyMessage;
  final IconData icon;
  final String? createRoute;
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
            label: const Text('Create'),
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
            title: '${widget.title} unavailable',
            message: '${snapshot.error}',
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
            title: 'Nothing here yet',
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
                  '${widget.title} item';
              final subtitle =
                  item['description'] ??
                  item['summary'] ??
                  item['status'] ??
                  item['createdAt'] ??
                  '';
              return Card(
                child: ListTile(
                  onTap: () => _showDetails(item, '$title'),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 8,
                  ),
                  leading: Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: AppColors.surfaceMuted,
                      borderRadius: BorderRadius.circular(AppRadius.medium),
                    ),
                    child: Icon(widget.icon, color: AppColors.navy, size: 21),
                  ),
                  title: Text(
                    '$title',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  subtitle: '$subtitle'.isEmpty
                      ? null
                      : Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            '$subtitle',
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                  trailing: const Icon(
                    Icons.chevron_right_rounded,
                    color: AppColors.textSecondary,
                  ),
                ),
              );
            },
          ),
        );
      },
    ),
  );

  void _showDetails(Map item, String title) {
    final visible = item.entries.where((entry) {
      final value = entry.value;
      return value != null &&
          value.toString().trim().isNotEmpty &&
          value is! Map &&
          value is! List;
    }).toList();
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: DraggableScrollableSheet(
          expand: false,
          initialChildSize: .62,
          minChildSize: .35,
          maxChildSize: .9,
          builder: (context, controller) => ListView(
            controller: controller,
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.page,
              0,
              AppSpacing.page,
              AppSpacing.xl,
            ),
            children: [
              Text(title, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: AppSpacing.lg),
              ...visible.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _fieldLabel('${entry.key}'),
                        style: const TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text('${entry.value}'),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _fieldLabel(String value) {
    final spaced = value.replaceAllMapped(
      RegExp(r'([a-z])([A-Z])'),
      (match) => '${match.group(1)} ${match.group(2)}',
    );
    return spaced.replaceAll('_', ' ').toUpperCase();
  }
}
