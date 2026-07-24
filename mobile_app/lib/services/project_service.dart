import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/project.dart';

class ProjectService {
  ProjectService(this._api);
  final ApiClient _api;
  Future<List<Project>> listAssigned() async {
    final response = await _api.get<Map<String, dynamic>>(
      ApiEndpoints.projects,
      query: {'limit': 100},
    );
    return (response['data'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(Project.fromJson)
        .toList();
  }

  Future<Map<String, dynamic>> dashboard(String id, {required String kind}) {
    final path = switch (kind) {
      'engineer' => ApiEndpoints.engineerDashboard(id),
      'consultant' => ApiEndpoints.consultantDashboard(id),
      'owner' => ApiEndpoints.ownerDashboard(id),
      'worker' => '${ApiEndpoints.workerDashboard}?project_id=$id',
      _ => ApiEndpoints.projectDashboard(id),
    };
    return _api.get<Map<String, dynamic>>(path);
  }

  Future<Map<String, dynamic>> company() =>
      _api.get<Map<String, dynamic>>(ApiEndpoints.company);
}
