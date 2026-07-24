import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:image_picker/image_picker.dart';

import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/field_submission.dart';

class FieldSubmissionService {
  FieldSubmissionService(this._api);
  final ApiClient _api;

  Future<List<FieldSubmission>> mine(String projectId, {String? taskId}) async {
    final raw = await _api.get<List<dynamic>>(
      ApiEndpoints.myFieldSubmissions,
      query: {'project_id': projectId, if (taskId != null) 'task_id': taskId},
    );
    return raw.whereType<Map<String, dynamic>>().map(FieldSubmission.fromJson).toList();
  }

  Future<List<PhotoCategory>> categories(String projectId) async {
    final raw = await _api.get<List<dynamic>>(
      ApiEndpoints.photoCategories(projectId),
    );
    return raw
        .whereType<Map<String, dynamic>>()
        .map(PhotoCategory.fromJson)
        .where((category) => category.active)
        .toList();
  }

  Future<FieldSubmission> create({
    required String projectId,
    required String taskId,
    required String note,
    required List<XFile> photos,
    required List<String?> directions,
    required List<List<String>> photoCategoryIds,
    String? resubmissionOfId,
  }) async {
    final form = FormData();
    form.fields
      ..add(MapEntry('project_id', projectId))
      ..add(MapEntry('task_id', taskId))
      ..add(MapEntry('description', note))
      ..add(MapEntry('directions', jsonEncode(directions)))
      ..add(MapEntry('photo_category_ids', jsonEncode(photoCategoryIds)));
    if (resubmissionOfId != null) {
      form.fields.add(MapEntry('resubmission_of_id', resubmissionOfId));
    }
    for (final photo in photos) {
      form.files.add(MapEntry(
        'files',
        await MultipartFile.fromFile(photo.path, filename: photo.name),
      ));
    }
    return FieldSubmission.fromJson(
      await _api.upload<Map<String, dynamic>>(ApiEndpoints.fieldSubmissions, form),
    );
  }
}
