import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_spacing.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_labels.dart';

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
      appBar: AppBar(title: Text(context.l10n.issueReport)),
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
                project?.name ?? context.l10n.commonNoProjectSelected,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: AppSpacing.lg),
              TextFormField(
                controller: _title,
                textInputAction: TextInputAction.next,
                decoration: InputDecoration(
                  labelText: context.l10n.issueTitleLabel,
                  prefixIcon: const Icon(Icons.report_problem_outlined),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? context.l10n.validationEnterIssueTitle
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),
              TextFormField(
                controller: _description,
                minLines: 4,
                maxLines: 7,
                decoration: InputDecoration(
                  labelText: context.l10n.commonDescription,
                  alignLabelWithHint: true,
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? context.l10n.validationDescribeIssue
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                value: _category,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: context.l10n.commonCategory,
                  prefixIcon: const Icon(Icons.category_outlined),
                ),
                // The item *values* stay the English strings the API already
                // stores; only the visible text is translated.
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
                            child: Text(
                              context.l10n.issueCategoryLabel(value),
                            ),
                          ),
                        )
                        .toList(),
                onChanged: (value) =>
                    setState(() => _category = value ?? _category),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                value: _severity,
                decoration: InputDecoration(
                  labelText: context.l10n.issueSeverity,
                  prefixIcon: const Icon(Icons.priority_high_rounded),
                ),
                items: const ['low', 'medium', 'high', 'critical']
                    .map(
                      (value) => DropdownMenuItem(
                        value: value,
                        child: Text(context.l10n.priorityLabel(value)),
                      ),
                    )
                    .toList(),
                onChanged: (value) =>
                    setState(() => _severity = value ?? _severity),
              ),
              const SizedBox(height: AppSpacing.sm),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(context.l10n.issueAffectsSchedule),
                subtitle: Text(context.l10n.issueAffectsScheduleBody),
                value: _affectsSchedule,
                onChanged: (value) => setState(() => _affectsSchedule = value),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton.icon(
                onPressed: project == null || _submitting ? null : _submit,
                icon: const Icon(Icons.send_rounded),
                label: Text(
                  _submitting
                      ? context.l10n.commonSubmitting
                      : context.l10n.issueSubmit,
                ),
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
          SnackBar(content: Text(context.l10n.issueReported)),
        );
        Navigator.pop(context, true);
      }
    } on NetworkException catch (error) {
      if (mounted) {
        setState(() => _submitting = false);
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(
          SnackBar(content: Text(context.l10n.describeError(error))),
        );
      }
    }
  }
}
