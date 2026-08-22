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

  /// One notification by id, for resolving a tapped push into a destination.
  ///
  /// A tap gives the app only an id; the screen to open is derived from the
  /// notification's project and entity. Scoped to the caller on the server.
  Future<NotificationItem> byId(String id) async {
    final response = await _api.get<Map<String, dynamic>>(
      ApiEndpoints.notification(id),
    );
    return NotificationItem.fromJson(response);
  }

  /// Register this device for push. Safe to call on every app start.
  Future<void> registerDevice({
    required String token,
    required String platform,
    String? deviceId,
    String? deviceName,
    String? appVersion,
  }) => _api.post<Object?>(
    ApiEndpoints.notificationDevices,
    data: {
      'token': token,
      'platform': platform,
      if (deviceId != null) 'deviceId': deviceId,
      if (deviceName != null) 'deviceName': deviceName,
      if (appVersion != null) 'appVersion': appVersion,
    },
  );

  /// Retire this device on sign-out, so the next user of the handset is not
  /// reached with the previous user's notifications.
  Future<void> unregisterDevice({String? token, String? deviceId}) =>
      _api.delete<Object?>(
        ApiEndpoints.notificationDevices,
        data: {
          if (token != null) 'token': token,
          if (deviceId != null) 'deviceId': deviceId,
        },
      );
}
