import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/l10n/l10n_labels.dart';
import '../../app/dependency_injection.dart';
import '../../core/network/network_exceptions.dart';
import '../../models/field_submission.dart';
import '../projects/project_context_view_model.dart';

const _directions = <String>[
  'FRONT', 'BACK', 'LEFT', 'RIGHT', 'TOP', 'DETAIL', 'OTHER',
];

class WorkerFieldSubmissionScreen extends ConsumerStatefulWidget {
  const WorkerFieldSubmissionScreen({
    super.key,
    required this.taskId,
    this.resubmissionOfId,
  });
  final String taskId;
  final String? resubmissionOfId;

  @override
  ConsumerState<WorkerFieldSubmissionScreen> createState() =>
      _WorkerFieldSubmissionScreenState();
}

class _WorkerFieldSubmissionScreenState
    extends ConsumerState<WorkerFieldSubmissionScreen> {
  final _note = TextEditingController();
  final _picker = ImagePicker();
  final List<XFile> _photos = [];
  final List<String?> _photoDirections = [];
  final Set<String> _selectedCategoryIds = {};
  List<PhotoCategory> _categories = [];
  bool _busy = false;
  Object? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadCategories());
  }

  Future<void> _loadCategories() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null) return;
    try {
      final values = await ref
          .read(fieldSubmissionRepositoryProvider)
          .categories(project.id);
      if (mounted) setState(() => _categories = values);
    } on NetworkException catch (error) {
      if (mounted) setState(() => _error = error);
    }
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _camera() async {
    final photo = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 88,
      maxWidth: 2200,
    );
    if (photo != null) setState(() { _photos.add(photo); _photoDirections.add(null); });
  }

  Future<void> _gallery() async {
    final photos = await _picker.pickMultiImage(
      imageQuality: 88,
      maxWidth: 2200,
    );
    if (photos.isNotEmpty) {
      setState(() {
        _photos.addAll(photos);
        _photoDirections.addAll(List<String?>.filled(photos.length, null));
      });
    }
  }

  Future<void> _submit() async {
    final project = ref.read(projectContextProvider).selected;
    if (project == null || (_note.text.trim().isEmpty && _photos.isEmpty)) return;
    setState(() { _busy = true; _error = null; });
    try {
      await ref.read(fieldSubmissionRepositoryProvider).create(
        projectId: project.id,
        taskId: widget.taskId,
        note: _note.text.trim(),
        photos: _photos,
        directions: _photoDirections,
        photoCategoryIds: List.generate(
          _photos.length,
          (_) => _selectedCategoryIds.toList(),
        ),
        resubmissionOfId: widget.resubmissionOfId,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(context.l10n.evidenceSent)),
        );
        context.pop(true);
      }
    } on NetworkException catch (error) {
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(widget.resubmissionOfId == null
          ? context.l10n.evidenceNewTitle
          : context.l10n.evidenceCorrectedTitle),
    ),
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            context.l10n.evidenceDocumentWork,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Text(context.l10n.evidenceVerifyHint),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              context.l10n.describeError(_error),
              style: const TextStyle(color: Colors.red),
            ),
          ],
          const SizedBox(height: 18),
          TextField(
            controller: _note,
            onChanged: (_) => setState(() {}),
            minLines: 3,
            maxLines: 6,
            decoration: InputDecoration(
              labelText: context.l10n.evidenceWhatWork,
              hintText: context.l10n.evidenceHint,
              alignLabelWithHint: true,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _busy ? null : _camera,
                  icon: const Icon(Icons.camera_alt),
                  label: Text(context.l10n.evidenceTakePhoto),
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _busy ? null : _gallery,
                  icon: const Icon(Icons.photo_library_outlined),
                  label: Text(context.l10n.evidenceAddPhotos),
                  style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (_categories.isNotEmpty) ...[
            Text(
              context.l10n.evidenceCategoryOptional,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              context.l10n.evidenceCategoryHint,
              style: const TextStyle(fontSize: 13),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: _categories.map((category) => FilterChip(
                label: Text(category.name),
                selected: _selectedCategoryIds.contains(category.id),
                onSelected: _busy ? null : (selected) => setState(() {
                  if (selected) {
                    _selectedCategoryIds.add(category.id);
                  } else {
                    _selectedCategoryIds.remove(category.id);
                  }
                }),
              )).toList(),
            ),
            const SizedBox(height: 14),
          ],
          ...List.generate(_photos.length, (index) => Card(
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: Image.file(
                      File(_photos[index].path),
                      width: 82,
                      height: 82,
                      fit: BoxFit.cover,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _photoDirections[index],
                      decoration: InputDecoration(
                        labelText: context.l10n.evidenceViewOptional,
                      ),
                      // The stored value stays the upper-case code.
                      items: _directions.map((value) => DropdownMenuItem(
                        value: value,
                        child: Text(context.l10n.photoViewLabel(value)),
                      )).toList(),
                      onChanged: (value) => setState(() => _photoDirections[index] = value),
                    ),
                  ),
                  IconButton(
                    tooltip: context.l10n.evidenceRemovePhoto,
                    onPressed: () => setState(() {
                      _photos.removeAt(index);
                      _photoDirections.removeAt(index);
                    }),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
            ),
          )),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy || (_note.text.trim().isEmpty && _photos.isEmpty)
                ? null : _submit,
            icon: _busy
                ? const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_upload_outlined),
            label: Text(_busy
                ? context.l10n.commonSubmitting
                : context.l10n.evidenceSubmit),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(58)),
          ),
        ],
      ),
    ),
  );
}
