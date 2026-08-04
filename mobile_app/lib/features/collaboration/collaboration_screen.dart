import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/constants/role_constants.dart';
import '../../core/widgets/async_views.dart';
import '../projects/project_context_view_model.dart';

class CollaborationScreen extends ConsumerStatefulWidget {
  const CollaborationScreen({super.key});

  @override
  ConsumerState<CollaborationScreen> createState() => _CollaborationScreenState();
}

class _CollaborationScreenState extends ConsumerState<CollaborationScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  Future<List<dynamic>>? _requests;
  Future<List<dynamic>>? _visits;
  Future<Map<String, dynamic>>? _actions;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 3, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _reload());
  }

  @override
  void dispose() { _tabs.dispose(); super.dispose(); }

  void _reload() {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return;
    final api = ref.read(apiClientProvider);
    setState(() {
      _requests = api.get<List<dynamic>>(ApiEndpoints.ownerRequests, query: {'project_id': project.id});
      _visits = api.get<List<dynamic>>(ApiEndpoints.siteVisits, query: {'project_id': project.id});
      _actions = api.get<Map<String, dynamic>>(ApiEndpoints.myActionCenter, query: {'project_id': project.id});
    });
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    final user = ref.watch(sessionProvider).user;
    if (project == null || user == null) {
      return const Scaffold(body: MessageView(icon: Icons.apartment, title: 'Select a project', message: 'Choose a project to see accountable actions.'));
    }
    final canRequest = user.isOwner || user.isProjectManager || user.role == RoleConstants.admin;
    final canVisit = user.isSiteEngineer || user.isProjectManager || user.role == RoleConstants.admin;
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Actions'),
        actions: [IconButton(onPressed: _reload, icon: const Icon(Icons.refresh))],
        bottom: TabBar(controller: _tabs, tabs: const [Tab(text: 'Actions'), Tab(text: 'Requests'), Tab(text: 'Visits')]),
      ),
      body: TabBarView(controller: _tabs, children: [
        _ActionList(future: _actions),
        _RequestList(future: _requests, currentUserId: user.id, onAcknowledged: _reload),
        _VisitList(future: _visits),
      ]),
      floatingActionButton: AnimatedBuilder(
        animation: _tabs,
        builder: (_, __) {
          if (_tabs.index == 1 && canRequest) return FloatingActionButton.extended(onPressed: _createRequest, icon: const Icon(Icons.add_comment_outlined), label: const Text('New request'));
          if (_tabs.index == 2 && canVisit) return FloatingActionButton.extended(onPressed: _createVisit, icon: const Icon(Icons.add_location_alt_outlined), label: const Text('Schedule'));
          return const SizedBox.shrink();
        },
      ),
    );
  }

  Future<void> _createRequest() async {
    final title = TextEditingController(); final description = TextEditingController();
    String discipline = 'general'; String priority = 'NORMAL';
    final accepted = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, builder: (context) => StatefulBuilder(builder: (context, setSheetState) => Padding(
      padding: EdgeInsets.only(left: 20, right: 20, top: 20, bottom: MediaQuery.viewInsetsOf(context).bottom + 20),
      child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Client / Owner Request', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        const Text('This request does not modify the official design.'), const SizedBox(height: 16),
        TextField(controller: title, decoration: const InputDecoration(labelText: 'Title')),
        TextField(controller: description, maxLines: 4, decoration: const InputDecoration(labelText: 'Description')),
        DropdownButtonFormField(value: discipline, decoration: const InputDecoration(labelText: 'Discipline'), items: const ['general', 'architectural', 'civil', 'electrical', 'mechanical'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), onChanged: (x) => setSheetState(() => discipline = x!)),
        DropdownButtonFormField(value: priority, decoration: const InputDecoration(labelText: 'Priority'), items: const ['NORMAL', 'HIGH', 'CRITICAL'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), onChanged: (x) => setSheetState(() => priority = x!)),
        const SizedBox(height: 16), FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Submit for engineering review')),
      ])),
    )));
    if (accepted != true || title.text.trim().isEmpty || description.text.trim().isEmpty) return;
    final project = ref.read(projectContextProvider).selected!;
    try {
      await ref.read(apiClientProvider).post<Map<String, dynamic>>(ApiEndpoints.ownerRequests, data: {'projectId': project.id, 'title': title.text.trim(), 'description': description.text.trim(), 'category': 'GENERAL_REQUEST', 'discipline': discipline == 'general' ? null : discipline, 'priority': priority});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Request submitted for human engineering review.')));
      _reload();
    } catch (error) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error'))); }
  }

  Future<void> _createVisit() async {
    final title = TextEditingController(); final location = TextEditingController();
    var start = DateTime.now().add(const Duration(days: 1)); var end = DateTime.now().add(const Duration(days: 1, hours: 1));
    final accepted = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, builder: (context) => StatefulBuilder(builder: (context, setSheetState) => Padding(
      padding: EdgeInsets.only(left: 20, right: 20, top: 20, bottom: MediaQuery.viewInsetsOf(context).bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Text('Schedule site visit', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        TextField(controller: title, decoration: const InputDecoration(labelText: 'Title')),
        TextField(controller: location, decoration: const InputDecoration(labelText: 'Site / location')),
        ListTile(title: const Text('Start'), subtitle: Text(DateFormat.yMMMd().add_jm().format(start)), trailing: const Icon(Icons.edit_calendar), onTap: () async { final value = await _pickDateTime(start); if (value != null) setSheetState(() { start = value; if (!end.isAfter(start)) end = start.add(const Duration(hours: 1)); }); }),
        ListTile(title: const Text('End'), subtitle: Text(DateFormat.yMMMd().add_jm().format(end)), trailing: const Icon(Icons.edit_calendar), onTap: () async { final value = await _pickDateTime(end); if (value != null) setSheetState(() => end = value); }),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Review and schedule')),
      ]),
    )));
    if (accepted != true || title.text.trim().isEmpty || !end.isAfter(start)) return;
    final project = ref.read(projectContextProvider).selected!;
    try {
      await ref.read(apiClientProvider).post<Map<String, dynamic>>(ApiEndpoints.siteVisits, data: {'projectId': project.id, 'title': title.text.trim(), 'scheduledStart': start.toUtc().toIso8601String(), 'scheduledEnd': end.toUtc().toIso8601String(), 'visitType': 'ROUTINE_INSPECTION', 'location': location.text.trim(), 'participantIds': []});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Site visit scheduled.')));
      _reload();
    } catch (error) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$error'))); }
  }

  Future<DateTime?> _pickDateTime(DateTime initial) async {
    final date = await showDatePicker(context: context, firstDate: DateTime.now().subtract(const Duration(days: 1)), lastDate: DateTime.now().add(const Duration(days: 730)), initialDate: initial);
    if (date == null || !mounted) return null;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(initial));
    return time == null ? null : DateTime(date.year, date.month, date.day, time.hour, time.minute);
  }
}

class _ActionList extends StatelessWidget {
  const _ActionList({required this.future}); final Future<Map<String, dynamic>>? future;
  @override Widget build(BuildContext context) => FutureBuilder<Map<String, dynamic>>(future: future, builder: (_, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) return const LoadingView();
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: 'Action center unavailable', message: '${snapshot.error}');
    final counts = snapshot.data?['counts'] as Map? ?? {};
    return RefreshIndicator(onRefresh: () async {}, child: ListView(padding: const EdgeInsets.all(16), children: [
      const Text('What needs my attention right now?', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      const SizedBox(height: 12), ...counts.entries.map((entry) => Card(child: ListTile(title: Text(_label('${entry.key}')), trailing: CircleAvatar(child: Text('${entry.value}'))))),
      const Card(child: ListTile(leading: Icon(Icons.auto_awesome), title: Text('AI is advisory'), subtitle: Text('AI alerts require human review and retain their project sources.'))),
    ]));
  });
}

class _RequestList extends ConsumerWidget {
  const _RequestList({required this.future, required this.currentUserId, required this.onAcknowledged});
  final Future<List<dynamic>>? future; final String currentUserId; final VoidCallback onAcknowledged;
  @override Widget build(BuildContext context, WidgetRef ref) => FutureBuilder<List<dynamic>>(future: future, builder: (_, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) return const LoadingView();
    final items = snapshot.data ?? const [];
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: 'Requests unavailable', message: '${snapshot.error}');
    if (items.isEmpty) return const MessageView(icon: Icons.mark_chat_read_outlined, title: 'No active owner requests', message: 'New client requests and engineering responses will appear here.');
    return ListView.builder(padding: const EdgeInsets.fromLTRB(12, 12, 12, 100), itemCount: items.length, itemBuilder: (_, index) {
      final item = items[index] as Map<String, dynamic>; final assigned = '${item['assignedToId']}' == currentUserId;
      return Card(child: ListTile(isThreeLine: true, title: Text('${item['title']}'), subtitle: Text('${item['description']}\n${_label('${item['status']}')} · ${_label('${item['priority']}')}'), trailing: assigned && item['status'] == 'ASSIGNED' ? IconButton(tooltip: 'Acknowledge action', icon: const Icon(Icons.done_all), onPressed: () async { await ref.read(apiClientProvider).patch<Map<String, dynamic>>(ApiEndpoints.ownerRequest('${item['id']}'), data: {'status': 'UNDER_REVIEW'}); onAcknowledged(); }) : null));
    });
  });
}

class _VisitList extends StatelessWidget {
  const _VisitList({required this.future}); final Future<List<dynamic>>? future;
  @override Widget build(BuildContext context) => FutureBuilder<List<dynamic>>(future: future, builder: (_, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) return const LoadingView();
    final items = snapshot.data ?? const [];
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: 'Schedule unavailable', message: '${snapshot.error}');
    if (items.isEmpty) return const MessageView(icon: Icons.calendar_month_outlined, title: 'No site visits scheduled', message: 'Visits across assigned projects will appear here.');
    return ListView.builder(padding: const EdgeInsets.fromLTRB(12, 12, 12, 100), itemCount: items.length, itemBuilder: (_, index) { final item = items[index] as Map<String, dynamic>; return Card(child: ListTile(leading: const Icon(Icons.engineering_outlined), title: Text('${item['title']}'), subtitle: Text('${DateFormat.yMMMd().add_jm().format(DateTime.parse('${item['scheduledStart']}').toLocal())}\n${_label('${item['visitType']}')} · ${item['location'] ?? 'Project site'}'), isThreeLine: true, trailing: Text(_label('${item['status']}')))); });
  });
}

String _label(String value) => value.replaceAll('_', ' ').toLowerCase().split(' ').map((part) => part.isEmpty ? part : '${part[0].toUpperCase()}${part.substring(1)}').join(' ');
