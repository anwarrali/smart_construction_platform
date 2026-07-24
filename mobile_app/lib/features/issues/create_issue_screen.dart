import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_spacing.dart';
import '../projects/project_context_view_model.dart';

class CreateIssueScreen extends ConsumerStatefulWidget {
  const CreateIssueScreen({super.key});

  @override
  ConsumerState<CreateIssueScreen> createState() => _CreateIssueScreenState();
}

class _CreateIssueScreenState extends ConsumerState<CreateIssueScreen> {
  final _formKey = GlobalKey<FormState>();
  final _title = TextEditingController();
  final _description = TextEditingController();
  String _category = 'Other';
  String _severity = 'medium';
  bool _affectsSchedule = false;
  bool _submitting = false;

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    return Scaffold(
      appBar: AppBar(title: const Text('Report Issue')),
      body: SafeArea(
        top: false,
        child: Form(
          key: _formKey,
          child: ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: EdgeInsets.fromLTRB(
              AppSpacing.page,
              AppSpacing.lg,
              AppSpacing.page,
              AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
            ),
            children: [
              Text(
                project?.name ?? 'No project selected',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: AppSpacing.lg),
              TextFormField(
                controller: _title,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Issue title',
                  prefixIcon: Icon(Icons.report_problem_outlined),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Enter an issue title.'
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _description,
                minLines: 4,
                maxLines: 7,
                decoration: const InputDecoration(
                  labelText: 'Description',
                  alignLabelWithHint: true,
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Describe the issue.'
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                value: _category,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Category',
                  prefixIcon: Icon(Icons.category_outlined),
                ),
                items:
                    const [
                          'Material unavailable',
                          'Previous task incomplete',
                          'Drawing unavailable',
                          'Equipment unavailable',
                          'Labor shortage',
                          'Site access issue',
                          'Consultant clarification required',
                          'Technical conflict',
                          'Safety restriction',
                          'Other',
                        ]
                        .map(
                          (value) => DropdownMenuItem(
                            value: value,
                            child: Text(value),
                          ),
                        )
                        .toList(),
                onChanged: (value) =>
                    setState(() => _category = value ?? _category),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                value: _severity,
                decoration: const InputDecoration(
                  labelText: 'Severity',
                  prefixIcon: Icon(Icons.priority_high_rounded),
                ),
                items: const ['low', 'medium', 'high', 'critical']
                    .map(
                      (value) => DropdownMenuItem(
                        value: value,
                        child: Text(
                          '${value[0].toUpperCase()}${value.substring(1)}',
                        ),
                      ),
                    )
                    .toList(),
                onChanged: (value) =>
                    setState(() => _severity = value ?? _severity),
              ),
              const SizedBox(height: AppSpacing.sm),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Affects project schedule'),
                subtitle: const Text('Flag this issue for schedule attention.'),
                value: _affectsSchedule,
                onChanged: (value) => setState(() => _affectsSchedule = value),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton.icon(
                onPressed: project == null || _submitting ? null : _submit,
                icon: const Icon(Icons.send_rounded),
                label: Text(_submitting ? 'Submitting…' : 'Submit Issue'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return;
    setState(() => _submitting = true);
    try {
      await ref
          .read(apiClientProvider)
          .post<Map<String, dynamic>>(
            ApiEndpoints.createIssue,
            data: {
              'projectId': project.id,
              'title': _title.text.trim(),
              'description': _description.text.trim(),
              'category': _category,
              'severity': _severity,
              'affectsSchedule': _affectsSchedule,
            },
          );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Issue reported successfully.')),
        );
        Navigator.pop(context, true);
      }
    } on NetworkException catch (error) {
      if (mounted) {
        setState(() => _submitting = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }
}
