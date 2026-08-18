import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/async_views.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

class IfcModelsScreen extends ConsumerStatefulWidget {
  const IfcModelsScreen({super.key});

  @override
  ConsumerState<IfcModelsScreen> createState() => _IfcModelsScreenState();
}

class _IfcModelsScreenState extends ConsumerState<IfcModelsScreen> {
  Future<List<_IfcGroup>>? _future;
  String? _projectId;

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    if (project == null) {
      return Scaffold(
        body: MessageView(
          icon: Icons.apartment,
          title: context.l10n.commonSelectProject,
          message: context.l10n.ifcSelectProjectBody,
        ),
      );
    }
    if (_projectId != project.id || _future == null) {
      _projectId = project.id;
      _future = _load(project.id);
    }
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.ifcTitle)),
      body: FutureBuilder<List<_IfcGroup>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return LoadingView(label: context.l10n.ifcLoading);
          }
          if (snapshot.hasError) {
            return MessageView(
              icon: Icons.cloud_off,
              title: context.l10n.commonUnavailable(
                context.l10n.ifcModelsTitle,
              ),
              message: context.l10n.describeError(snapshot.error),
              onAction: () => setState(() => _future = _load(project.id)),
            );
          }
          final groups = snapshot.data ?? const [];
          if (groups.isEmpty) {
            return MessageView(
              icon: Icons.view_in_ar_outlined,
              title: context.l10n.ifcEmptyTitle,
              message: context.l10n.ifcEmptyBody,
            );
          }
          return RefreshIndicator(
            onRefresh: () async { setState(() => _future = _load(project.id)); await _future; },
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(project.name, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(
                  context.l10n.ifcReadOnlyHint,
                  style: const TextStyle(color: AppColors.mutedForeground),
                ),
                const SizedBox(height: 16),
                ...groups.map((group) => Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ExpansionTile(
                    leading: const CircleAvatar(child: Icon(Icons.account_tree_outlined)),
                    title: Text(group.name, style: const TextStyle(fontWeight: FontWeight.w700)),
                    subtitle: Text(group.discipline == null
                        ? context.l10n.ifcFederatedModel
                        : context.l10n.disciplineLabel(group.discipline)),
                    children: group.versions.isEmpty
                        ? [ListTile(title: Text(context.l10n.ifcNoVersions))]
                        : group.versions.map((version) => ListTile(
                            leading: Icon(version.ready ? Icons.check_circle : version.failed ? Icons.error : Icons.sync, color: version.ready ? AppColors.stateVerified : version.failed ? AppColors.destructive : AppColors.stateProgress),
                            title: Text(context.l10n.ifcVersionLine(
                              context.formatInt(version.number),
                              version.title,
                            )),
                            // The IFC schema name (e.g. IFC4) is a format
                            // identifier and stays as the file declares it.
                            subtitle: Text(
                              '${context.l10n.statusLabel(version.status)} · '
                              '${context.l10n.ifcElementCount(version.entityCount)}'
                              '${version.schema == null ? '' : ' · ${version.schema}'}',
                            ),
                            trailing: version.active
                                ? Chip(label: Text(context.l10n.ifcActive))
                                : null,
                          )).toList(),
                  ),
                )),
              ],
            ),
          );
        },
      ),
    );
  }

  Future<List<_IfcGroup>> _load(String projectId) async {
    final api = ref.read(apiClientProvider);
    final raw = await api.get<List<dynamic>>(ApiEndpoints.ifcModels(projectId));
    return Future.wait(raw.map((value) async {
      final map = Map<String, dynamic>.from(value as Map);
      final versions = await api.get<List<dynamic>>(ApiEndpoints.ifcVersions(projectId, '${map['id']}'));
      return _IfcGroup('${map['name']}', map['discipline'] as String?, versions.map((item) => _IfcVersion.fromJson(Map<String, dynamic>.from(item as Map))).toList());
    }));
  }
}

class _IfcGroup {
  const _IfcGroup(this.name, this.discipline, this.versions);
  final String name;
  final String? discipline;
  final List<_IfcVersion> versions;
}

class _IfcVersion {
  const _IfcVersion(this.number, this.title, this.status, this.entityCount, this.schema, this.active);
  factory _IfcVersion.fromJson(Map<String, dynamic> value) => _IfcVersion(value['versionNumber'] as int? ?? 0, '${value['title'] ?? ''}', '${value['processingStatus'] ?? 'UPLOADED'}', value['entityCount'] as int? ?? 0, value['ifcSchema'] as String?, value['isActive'] as bool? ?? false);
  final int number;
  final String title;
  final String status;
  final int entityCount;
  final String? schema;
  final bool active;
  bool get ready => status == 'READY' || status == 'READY_WITH_WARNINGS';
  bool get failed => status == 'FAILED';
}
