import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/constants/role_constants.dart';
import '../../core/widgets/async_views.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

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
      return Scaffold(
        body: MessageView(
          icon: Icons.apartment,
          title: context.l10n.commonSelectProject,
          message: context.l10n.collabSelectProjectBody,
        ),
      );
    }
    final canRequest = user.isOwner || user.isProjectManager || user.role == RoleConstants.admin;
    final canVisit = user.isSiteEngineer || user.isProjectManager || user.role == RoleConstants.admin;
    return Scaffold(
      appBar: AppBar(
        title: Text(context.l10n.collabMyActions),
        actions: [IconButton(onPressed: _reload, icon: const Icon(Icons.refresh))],
        bottom: TabBar(controller: _tabs, tabs: [
          Tab(text: context.l10n.collabTabActions),
          Tab(text: context.l10n.collabTabRequests),
          Tab(text: context.l10n.collabTabVisits),
        ]),
      ),
      body: TabBarView(controller: _tabs, children: [
        _ActionList(future: _actions),
        _RequestList(future: _requests, currentUserId: user.id, onAcknowledged: _reload),
        _VisitList(future: _visits),
      ]),
      floatingActionButton: AnimatedBuilder(
        animation: _tabs,
        builder: (_, __) {
          if (_tabs.index == 1 && canRequest) {
            return FloatingActionButton.extended(
              onPressed: _createRequest,
              icon: const Icon(Icons.add_comment_outlined),
              label: Text(context.l10n.collabNewRequest),
            );
          }
          if (_tabs.index == 2 && canVisit) {
            return FloatingActionButton.extended(
              onPressed: _createVisit,
              icon: const Icon(Icons.add_location_alt_outlined),
              label: Text(context.l10n.collabSchedule),
            );
          }
          return const SizedBox.shrink();
        },
      ),
    );
  }

  Future<void> _createRequest() async {
    final title = TextEditingController(); final description = TextEditingController();
    String discipline = 'general'; String priority = 'NORMAL';
    final accepted = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, builder: (context) => StatefulBuilder(builder: (context, setSheetState) => Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.viewInsetsOf(context).bottom + 20),
      child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(context.l10n.collabOwnerRequest, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        Text(context.l10n.collabRequestHint), const SizedBox(height: 16),
        TextField(controller: title, decoration: InputDecoration(labelText: context.l10n.commonTitle)),
        TextField(controller: description, maxLines: 4, decoration: InputDecoration(labelText: context.l10n.commonDescription)),
        DropdownButtonFormField(value: discipline, decoration: InputDecoration(labelText: context.l10n.commonDiscipline), items: const ['general', 'architectural', 'civil', 'electrical', 'mechanical'].map((x) => DropdownMenuItem(value: x, child: Text(context.l10n.disciplineLabel(x)))).toList(), onChanged: (x) => setSheetState(() => discipline = x!)),
        DropdownButtonFormField(value: priority, decoration: InputDecoration(labelText: context.l10n.commonPriority), items: const ['NORMAL', 'HIGH', 'CRITICAL'].map((x) => DropdownMenuItem(value: x, child: Text(context.l10n.priorityLabel(x)))).toList(), onChanged: (x) => setSheetState(() => priority = x!)),
        const SizedBox(height: 16), FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(context.l10n.collabSubmitForReview)),
      ])),
    )));
    if (accepted != true || title.text.trim().isEmpty || description.text.trim().isEmpty) return;
    final project = ref.read(projectContextProvider).selected!;
    try {
      await ref.read(apiClientProvider).post<Map<String, dynamic>>(ApiEndpoints.ownerRequests, data: {'projectId': project.id, 'title': title.text.trim(), 'description': description.text.trim(), 'category': 'GENERAL_REQUEST', 'discipline': discipline == 'general' ? null : discipline, 'priority': priority});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.collabRequestSubmitted)));
      _reload();
    } catch (error) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.describeError(error)))); }
  }

  Future<void> _createVisit() async {
    final title = TextEditingController(); final location = TextEditingController();
    var start = DateTime.now().add(const Duration(days: 1)); var end = DateTime.now().add(const Duration(days: 1, hours: 1));
    final accepted = await showModalBottomSheet<bool>(context: context, isScrollControlled: true, builder: (context) => StatefulBuilder(builder: (context, setSheetState) => Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.viewInsetsOf(context).bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(context.l10n.collabScheduleVisit, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
        TextField(controller: title, decoration: InputDecoration(labelText: context.l10n.commonTitle)),
        TextField(controller: location, decoration: InputDecoration(labelText: context.l10n.collabSiteLocation)),
        ListTile(title: Text(context.l10n.collabStart), subtitle: Text(context.formatDateTime(start)), trailing: const Icon(Icons.edit_calendar), onTap: () async { final value = await _pickDateTime(start); if (value != null) setSheetState(() { start = value; if (!end.isAfter(start)) end = start.add(const Duration(hours: 1)); }); }),
        ListTile(title: Text(context.l10n.collabEnd), subtitle: Text(context.formatDateTime(end)), trailing: const Icon(Icons.edit_calendar), onTap: () async { final value = await _pickDateTime(end); if (value != null) setSheetState(() => end = value); }),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(context.l10n.collabReviewAndSchedule)),
      ]),
    )));
    if (accepted != true || title.text.trim().isEmpty || !end.isAfter(start)) return;
    final project = ref.read(projectContextProvider).selected!;
    try {
      await ref.read(apiClientProvider).post<Map<String, dynamic>>(ApiEndpoints.siteVisits, data: {'projectId': project.id, 'title': title.text.trim(), 'scheduledStart': start.toUtc().toIso8601String(), 'scheduledEnd': end.toUtc().toIso8601String(), 'visitType': 'ROUTINE_INSPECTION', 'location': location.text.trim(), 'participantIds': []});
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.collabVisitScheduled)));
      _reload();
    } catch (error) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l10n.describeError(error)))); }
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
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: context.l10n.commonUnavailable(context.l10n.collabActionCenter), message: context.l10n.describeError(snapshot.error));
    final counts = snapshot.data?['counts'] as Map? ?? {};
    return RefreshIndicator(onRefresh: () async {}, child: ListView(padding: const EdgeInsets.all(16), children: [
      Text(context.l10n.collabWhatNeedsAttention, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
      const SizedBox(height: 12), ...counts.entries.map((entry) => Card(child: ListTile(title: Text(context.l10n.actionCountLabel('${entry.key}')), trailing: CircleAvatar(child: Text(context.formatInt(entry.value as num)))))),
      Card(child: ListTile(leading: const Icon(Icons.auto_awesome), title: Text(context.l10n.collabAiAdvisory), subtitle: Text(context.l10n.collabAiAdvisoryBody))),
    ]));
  });
}

class _RequestList extends ConsumerWidget {
  const _RequestList({required this.future, required this.currentUserId, required this.onAcknowledged});
  final Future<List<dynamic>>? future; final String currentUserId; final VoidCallback onAcknowledged;
  @override Widget build(BuildContext context, WidgetRef ref) => FutureBuilder<List<dynamic>>(future: future, builder: (_, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) return const LoadingView();
    final items = snapshot.data ?? const [];
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: context.l10n.commonUnavailable(context.l10n.collabRequestsTitle), message: context.l10n.describeError(snapshot.error));
    if (items.isEmpty) return MessageView(icon: Icons.mark_chat_read_outlined, title: context.l10n.collabNoRequests, message: context.l10n.collabNoRequestsBody);
    return ListView.builder(padding: const EdgeInsets.fromLTRB(12, 12, 12, 100), itemCount: items.length, itemBuilder: (_, index) {
      final item = items[index] as Map<String, dynamic>; final assigned = '${item['assignedToId']}' == currentUserId;
      return Card(child: ListTile(isThreeLine: true, title: Text('${item['title']}'), subtitle: Text('${item['description']}\n${context.l10n.statusLabel('${item['status']}')} · ${context.l10n.priorityLabel('${item['priority']}')}'), trailing: assigned && item['status'] == 'ASSIGNED' ? IconButton(tooltip: context.l10n.collabAcknowledge, icon: const Icon(Icons.done_all), onPressed: () async { await ref.read(apiClientProvider).patch<Map<String, dynamic>>(ApiEndpoints.ownerRequest('${item['id']}'), data: {'status': 'UNDER_REVIEW'}); onAcknowledged(); }) : null));
    });
  });
}

class _VisitList extends StatelessWidget {
  const _VisitList({required this.future}); final Future<List<dynamic>>? future;
  @override Widget build(BuildContext context) => FutureBuilder<List<dynamic>>(future: future, builder: (_, snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) return const LoadingView();
    final items = snapshot.data ?? const [];
    if (snapshot.hasError) return MessageView(icon: Icons.cloud_off, title: context.l10n.commonUnavailable(context.l10n.collabScheduleTitle), message: context.l10n.describeError(snapshot.error));
    if (items.isEmpty) return MessageView(icon: Icons.calendar_month_outlined, title: context.l10n.collabNoVisits, message: context.l10n.collabNoVisitsBody);
    return ListView.builder(padding: const EdgeInsets.fromLTRB(12, 12, 12, 100), itemCount: items.length, itemBuilder: (_, index) { final item = items[index] as Map<String, dynamic>; return Card(child: ListTile(leading: const Icon(Icons.engineering_outlined), title: Text('${item['title']}'), subtitle: Text('${context.formatDateTime(DateTime.parse('${item['scheduledStart']}'))}\n${context.l10n.visitTypeLabel('${item['visitType']}')} · ${item['location'] ?? context.l10n.collabProjectSite}'), isThreeLine: true, trailing: Text(context.l10n.statusLabel('${item['status']}')))); });
  });
}


