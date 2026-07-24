import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/notification_item.dart';

class NotificationService {
  NotificationService(this._api);
  final ApiClient _api;

  Future<List<NotificationItem>> list({String? projectId, bool? unread}) async {
    final response = await _api.get<Map<String, dynamic>>(
      ApiEndpoints.notifications,
      query: {
        'limit': 100,
        if (projectId != null) 'project_id': projectId,
        if (unread != null) 'unread': unread,
      },
    );
    return (response['items'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(NotificationItem.fromJson)
        .toList();
  }

  Future<void> markRead(String id) =>
      _api.put<Object?>(ApiEndpoints.readNotification(id));

  Future<void> markAllRead({String? projectId}) => _api.put<Object?>(
    '/notifications/read-all',
    query: projectId == null ? null : {'project_id': projectId},
  );
}
