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
}
