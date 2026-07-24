import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/task.dart';

class TaskService {
  TaskService(this._api);
  final ApiClient _api;
  Future<List<ProjectTask>> list(
    String projectId, {
    required bool assignedOnly,
  }) async {
    final raw = await _api.get<List<dynamic>>(
      assignedOnly
          ? ApiEndpoints.myTasks
          : ApiEndpoints.projectTasks(projectId),
      query: assignedOnly ? {'project_id': projectId} : null,
    );
    return raw
        .whereType<Map<String, dynamic>>()
        .map(ProjectTask.fromJson)
        .toList();
  }

  Future<ProjectTask> get(String id) async => ProjectTask.fromJson(
    await _api.get<Map<String, dynamic>>(ApiEndpoints.task(id)),
  );
  Future<ProjectTask> start(String id) async => ProjectTask.fromJson(
    await _api.put<Map<String, dynamic>>(ApiEndpoints.startTask(id)),
  );
  Future<ProjectTask> updateProgress(
    String id,
    double value,
    String? note,
  ) async => ProjectTask.fromJson(
    await _api.put<Map<String, dynamic>>(
      ApiEndpoints.progress(id),
      data: {'progressPercentage': value, 'note': note},
    ),
  );
  Future<void> addComment(String id, String content) =>
      _api.post<Object?>(ApiEndpoints.comments(id), data: {'content': content});
  Future<void> submitReview(String id, String? note) => _api.put<Object?>(
    ApiEndpoints.submitReview(id),
    data: {'completionNote': note},
  );
}
