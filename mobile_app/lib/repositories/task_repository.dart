import '../models/task.dart';
import '../services/task_service.dart';

class TaskRepository {
  TaskRepository(this._service);
  final TaskService _service;
  Future<List<ProjectTask>> list(
    String projectId, {
    required bool assignedOnly,
  }) => _service.list(projectId, assignedOnly: assignedOnly);
  Future<ProjectTask> get(String id) => _service.get(id);
  Future<ProjectTask> start(String id) => _service.start(id);
  Future<ProjectTask> updateProgress(String id, double value, String? note) =>
      _service.updateProgress(id, value, note);
  Future<void> addComment(String id, String content) =>
      _service.addComment(id, content);
  Future<void> submitReview(String id, String? note) =>
      _service.submitReview(id, note);
}
