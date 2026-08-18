import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../app/dependency_injection.dart';
import '../../core/constants/api_endpoints.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_spacing.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

class CreateSiteReportScreen extends ConsumerStatefulWidget {
  const CreateSiteReportScreen({super.key});

  @override
  ConsumerState<CreateSiteReportScreen> createState() =>
      _CreateSiteReportScreenState();
}

class _CreateSiteReportScreenState
    extends ConsumerState<CreateSiteReportScreen> {
  final _formKey = GlobalKey<FormState>();
  final _summary = TextEditingController();
  final _weather = TextEditingController();
  final _workers = TextEditingController();
  final _equipment = TextEditingController();
  final _completed = TextEditingController();
  final _delays = TextEditingController();
  DateTime _date = DateTime.now();
  bool _submitting = false;

  @override
  void dispose() {
    for (final controller in [
      _summary,
      _weather,
      _workers,
      _equipment,
      _completed,
      _delays,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final project = ref.watch(projectContextProvider).selected;
    return Scaffold(
      appBar: AppBar(title: Text(context.l10n.siteReportCreate)),
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
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.calendar_today_outlined),
                title: Text(context.l10n.siteReportDate),
                subtitle: Text(context.formatShortDate(_date)),
                trailing: const Icon(Icons.edit_calendar_outlined),
                onTap: _selectDate,
              ),
              const SizedBox(height: AppSpacing.sm),
              TextFormField(
                controller: _summary,
                minLines: 4,
                maxLines: 8,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportWorkSummary,
                  alignLabelWithHint: true,
                  prefixIcon: const Padding(
                    padding: EdgeInsets.only(bottom: 75),
                    child: Icon(Icons.description_outlined),
                  ),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? context.l10n.validationAddReportSummary
                    : null,
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _completed,
                minLines: 2,
                maxLines: 5,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportWorkCompleted,
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _weather,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportWeather,
                  prefixIcon: const Icon(Icons.cloud_outlined),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _workers,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportWorkersCount,
                  prefixIcon: const Icon(Icons.groups_outlined),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _equipment,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportEquipment,
                  prefixIcon: const Icon(
                    Icons.precision_manufacturing_outlined,
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _delays,
                minLines: 2,
                maxLines: 5,
                decoration: InputDecoration(
                  labelText: context.l10n.siteReportDelays,
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              OutlinedButton.icon(
                onPressed: project == null || _submitting
                    ? null
                    : () => _submit('draft'),
                icon: const Icon(Icons.save_outlined),
                label: Text(context.l10n.commonSaveDraft),
              ),
              const SizedBox(height: AppSpacing.sm),
              FilledButton.icon(
                onPressed: project == null || _submitting
                    ? null
                    : () => _submit('submitted'),
                icon: const Icon(Icons.send_rounded),
                label: Text(
                  _submitting
                      ? context.l10n.commonSubmitting
                      : context.l10n.siteReportSubmit,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _selectDate() async {
    final value = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime.now().subtract(const Duration(days: 30)),
      lastDate: DateTime.now(),
    );
    if (value != null) setState(() => _date = value);
  }

  Future<void> _submit(String status) async {
    if (!_formKey.currentState!.validate()) return;
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return;
    final workers = int.tryParse(_workers.text.trim());
    setState(() => _submitting = true);
    try {
      final data = FormData.fromMap({
        'project_id': project.id,
        'report_date': DateFormat('yyyy-MM-dd').format(_date),
        'content': _summary.text.trim(),
        'review_status': status,
        if (_weather.text.trim().isNotEmpty)
          'weather_conditions': _weather.text.trim(),
        if (workers != null) 'workers_count': workers,
        if (_equipment.text.trim().isNotEmpty)
          'equipment': _equipment.text.trim(),
        if (_completed.text.trim().isNotEmpty)
          'work_completed': _completed.text.trim(),
        if (_delays.text.trim().isNotEmpty) 'delays': _delays.text.trim(),
      });
      await ref
          .read(apiClientProvider)
          .upload<Map<String, dynamic>>(ApiEndpoints.submitSiteReport, data);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              status == 'draft'
                  ? context.l10n.siteReportDraftSaved
                  : context.l10n.siteReportSubmitted,
            ),
          ),
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
