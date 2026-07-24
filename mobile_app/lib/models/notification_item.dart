class NotificationItem {
  const NotificationItem({
    required this.id,
    required this.title,
    required this.message,
    required this.type,
    required this.createdAt,
    required this.isRead,
    this.projectId,
    this.taskId,
    this.relatedEntityType,
    this.relatedEntityId,
  });

  final String id;
  final String title;
  final String message;
  final String type;
  final DateTime createdAt;
  final bool isRead;
  final String? projectId;
  final String? taskId;
  final String? relatedEntityType;
  final String? relatedEntityId;

  NotificationItem copyWith({bool? isRead}) => NotificationItem(
    id: id,
    title: title,
    message: message,
    type: type,
    createdAt: createdAt,
    isRead: isRead ?? this.isRead,
    projectId: projectId,
    taskId: taskId,
    relatedEntityType: relatedEntityType,
    relatedEntityId: relatedEntityId,
  );

  factory NotificationItem.fromJson(Map<String, dynamic> json) =>
      NotificationItem(
        id: '${json['id']}',
        title: json['title'] as String? ?? 'Notification',
        message: json['message'] as String? ?? '',
        type: json['type'] as String? ?? 'system',
        createdAt:
            DateTime.tryParse(json['createdAt'] as String? ?? '') ??
            DateTime.now(),
        isRead: json['isRead'] as bool? ?? false,
        projectId: json['projectId']?.toString(),
        taskId: json['taskId']?.toString(),
        relatedEntityType: json['relatedEntityType'] as String?,
        relatedEntityId: json['relatedEntityId']?.toString(),
      );
}
