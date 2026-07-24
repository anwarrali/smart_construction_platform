import 'package:image_picker/image_picker.dart';

import '../models/field_submission.dart';
import '../services/field_submission_service.dart';

class FieldSubmissionRepository {
  FieldSubmissionRepository(this._service);
  final FieldSubmissionService _service;

  Future<List<FieldSubmission>> mine(String projectId, {String? taskId}) =>
      _service.mine(projectId, taskId: taskId);

  Future<List<PhotoCategory>> categories(String projectId) =>
      _service.categories(projectId);

  Future<FieldSubmission> create({
    required String projectId,
    required String taskId,
    required String note,
    required List<XFile> photos,
    required List<String?> directions,
    required List<List<String>> photoCategoryIds,
    String? resubmissionOfId,
  }) => _service.create(
    projectId: projectId,
    taskId: taskId,
    note: note,
    photos: photos,
    directions: directions,
    photoCategoryIds: photoCategoryIds,
    resubmissionOfId: resubmissionOfId,
  );
}
