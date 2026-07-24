import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/widgets/async_views.dart';
import '../../models/chat_message.dart';
import '../projects/project_context_view_model.dart';

class MessagesScreen extends ConsumerStatefulWidget {
  const MessagesScreen({super.key});
  @override
  ConsumerState<MessagesScreen> createState() => _MessagesScreenState();
}

class _MessagesScreenState extends ConsumerState<MessagesScreen> {
  List<ProjectConversation> _items = const [];
  RecipientOptions _options = const RecipientOptions(users: [], groups: []);
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future.microtask(_load);
  }

  Future<void> _load() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) {
      if (mounted) setState(() { _loading = false; _error = 'Select a project first.'; });
      return;
    }
    if (mounted) setState(() { _loading = true; _error = null; });
    try {
      final results = await Future.wait([
        ref.read(messageRepositoryProvider).conversations(project.id),
        ref.read(messageRepositoryProvider).recipientOptions(project.id),
      ]);
      if (mounted) {
        setState(() {
          _items = results[0] as List<ProjectConversation>;
          _options = results[1] as RecipientOptions;
          _loading = false;
        });
      }
    } on NetworkException catch (error) {
      if (mounted) setState(() { _error = error.message; _loading = false; });
    }
  }

  String _title(ProjectConversation item, String? currentUserId) {
    if (item.title?.isNotEmpty == true) return item.title!;
    final names = item.participants
        .where((participant) => participant.userId != currentUserId)
        .map((participant) => participant.user.fullName)
        .join(', ');
    return names.isEmpty ? 'Project discussion' : names;
  }

  Future<void> _compose() async {
    final project = ref.read(projectContextProvider).selected;
    final user = ref.read(sessionProvider).user;
    if (project == null) return;
    final selected = <String>{};
    var groupCode = '';
    var useGroup = false;
    var announcement = false;
    final title = TextEditingController();
    final content = TextEditingController();
    final created = await showModalBottomSheet<ProjectConversation>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) => Padding(
          padding: EdgeInsets.fromLTRB(
            16, 16, 16, 16 + MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('New Project Conversation',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
                if (user?.isProjectManager == true || user?.role == 'admin')
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Project/team announcement'),
                    value: announcement,
                    onChanged: (value) => setSheetState(() {
                      announcement = value;
                      useGroup = value;
                      if (value) groupCode = 'ALL_PROJECT_MEMBERS';
                    }),
                  ),
                if (_options.groups.isNotEmpty && !announcement)
                  SegmentedButton<bool>(
                    segments: const [
                      ButtonSegment(value: false, label: Text('People')),
                      ButtonSegment(value: true, label: Text('Team / Group')),
                    ],
                    selected: {useGroup},
                    onSelectionChanged: (value) =>
                        setSheetState(() => useGroup = value.first),
                  ),
                const SizedBox(height: 12),
                if (useGroup)
                  DropdownButtonFormField<String>(
                    value: groupCode.isEmpty ? null : groupCode,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Recipient group'),
                    items: _options.groups.map((group) => DropdownMenuItem(
                      value: group.code,
                      child: Text('${group.label} (${group.recipientCount})',
                          overflow: TextOverflow.ellipsis),
                    )).toList(),
                    onChanged: (value) => setSheetState(() => groupCode = value ?? ''),
                  )
                else
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 230),
                    child: ListView(
                      shrinkWrap: true,
                      children: _options.users.map((recipient) => CheckboxListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        value: selected.contains(recipient.id),
                        title: Text(recipient.fullName, overflow: TextOverflow.ellipsis),
                        subtitle: Text(recipient.role.replaceAll('_', ' ')),
                        onChanged: (checked) => setSheetState(() {
                          if (checked == true) {
                            selected.add(recipient.id);
                          } else {
                            selected.remove(recipient.id);
                          }
                        }),
                      )).toList(),
                    ),
                  ),
                const SizedBox(height: 10),
                TextField(controller: title, decoration: const InputDecoration(labelText: 'Title (optional)')),
                const SizedBox(height: 10),
                TextField(
                  controller: content, minLines: 3, maxLines: 6,
                  decoration: const InputDecoration(labelText: 'Message'),
                ),
                const SizedBox(height: 14),
                FilledButton(
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                  onPressed: () async {
                    if (content.text.trim().isEmpty ||
                        (useGroup ? groupCode.isEmpty : selected.isEmpty)) {
                      return;
                    }
                    try {
                      final result = announcement
                          ? await ref.read(messageRepositoryProvider).announce(
                              projectId: project.id, groupCode: groupCode,
                              content: content.text.trim(),
                              title: title.text.trim().isEmpty ? null : title.text.trim(),
                            )
                          : await ref.read(messageRepositoryProvider).create(
                              projectId: project.id,
                              recipientIds: selected.toList(),
                              groupCode: useGroup ? groupCode : null,
                              title: title.text.trim().isEmpty ? null : title.text.trim(),
                              content: content.text.trim(),
                            );
                      if (context.mounted) Navigator.pop(context, result);
                    } on NetworkException catch (error) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(error.message)),
                        );
                      }
                    }
                  },
                  child: const Text('Send'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    title.dispose();
    content.dispose();
    if (created != null && mounted) {
      await _load();
      if (mounted) context.push('/messages/${created.id}', extra: created);
    }
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    final currentUserId = ref.watch(sessionProvider).user?.id;
    return Scaffold(
      appBar: AppBar(title: Text(project == null ? 'Messages' : 'Messages · ${project.name}',
          overflow: TextOverflow.ellipsis)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _compose, icon: const Icon(Icons.edit_outlined),
        label: const Text('New'),
      ),
      body: _loading
          ? const LoadingView(label: 'Loading conversations')
          : _error != null
              ? MessageView(icon: Icons.cloud_off, title: 'Messages unavailable',
                  message: _error!, onAction: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _items.isEmpty
                      ? ListView(children: const [
                          SizedBox(height: 180),
                          Center(child: Text('No project conversations yet.')),
                        ])
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(12, 12, 12, 100),
                          itemCount: _items.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 8),
                          itemBuilder: (context, index) {
                            final item = _items[index];
                            return Card(
                              child: ListTile(
                                onTap: () async {
                                  await context.push('/messages/${item.id}', extra: item);
                                  _load();
                                },
                                leading: CircleAvatar(child: Icon(
                                  item.type == 'PROJECT_CHANNEL'
                                      ? Icons.campaign_outlined
                                      : item.type == 'GROUP'
                                          ? Icons.groups_outlined
                                          : Icons.person_outline,
                                )),
                                title: Text(_title(item, currentUserId),
                                    maxLines: 1, overflow: TextOverflow.ellipsis),
                                subtitle: Text(item.lastMessage?.content ?? 'No messages',
                                    maxLines: 2, overflow: TextOverflow.ellipsis),
                                trailing: item.unreadCount > 0
                                    ? Badge(label: Text('${item.unreadCount}'))
                                    : const Icon(Icons.chevron_right),
                              ),
                            );
                          },
                        ),
                ),
    );
  }
}
