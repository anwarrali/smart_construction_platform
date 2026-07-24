import '../models/project.dart';
import '../services/project_service.dart';

class ProjectRepository {
  ProjectRepository(this._service);
  final ProjectService _service;
  Future<List<Project>> listAssigned() => _service.listAssigned();
  Future<Map<String, dynamic>> dashboard(String id, {required String kind}) =>
      _service.dashboard(id, kind: kind);
  Future<Map<String, dynamic>> company() => _service.company();
}
