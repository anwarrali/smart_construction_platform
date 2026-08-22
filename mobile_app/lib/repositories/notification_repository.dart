import '../models/notification_item.dart';
import '../services/notification_service.dart';

class NotificationRepository {
  NotificationRepository(this._service);
  final NotificationService _service;

  Future<List<NotificationItem>> list({String? projectId, bool? unread}) =>
      _service.list(projectId: projectId, unread: unread);
  Future<void> markRead(String id) => _service.markRead(id);
  Future<void> markAllRead({String? projectId}) =>
      _service.markAllRead(projectId: projectId);

  /// One notification by id — how a tapped push resolves to a destination.
  Future<NotificationItem> byId(String id) => _service.byId(id);

  Future<void> registerDevice({
    required String token,
    required String platform,
    String? deviceId,
    String? deviceName,
    String? appVersion,
  }) => _service.registerDevice(
    token: token,
    platform: platform,
    deviceId: deviceId,
    deviceName: deviceName,
    appVersion: appVersion,
  );

  Future<void> unregisterDevice({String? token, String? deviceId}) =>
      _service.unregisterDevice(token: token, deviceId: deviceId);
}
