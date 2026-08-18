/// A notification from the Smart Notification system.
///
/// `priority`, `category` and `requiresAction` come from the backend's
/// notification model (Task 3). They are read here rather than recomputed:
/// the server decides how loud a notification is, and mobile only presents
/// that decision — a second opinion on the client would drift from the web.
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
    this.priority = 'NORMAL',
    this.category = 'SYSTEM',
    this.requiresAction = false,
    this.messageKey,
    this.messageParams = const {},
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

  /// INFO | NORMAL | IMPORTANT | CRITICAL.
  final String priority;

  /// DIRECT | WORKFLOW | REMINDERS | DEADLINE | SYSTEM.
  final String category;

  final bool requiresAction;

  /// The structured message identifier, e.g. `taskDeadline.OVERDUE`.
  ///
  /// This is what makes a notification translatable: the server names the
  /// sentence and supplies its parameters, and each client renders it in the
  /// reader's own language. `title`/`message` remain the server's rendered
  /// English and are the fallback when no key was sent.
  final String? messageKey;

  /// Parameters for [messageKey] — task names, project names, reviewer
  /// names. Project data, so never translated, only interpolated.
  final Map<String, dynamic> messageParams;

  /// True when this notification is a chase rather than a first telling.
  bool get isReminder => category.toUpperCase() == 'REMINDERS';

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
    priority: priority,
    category: category,
    requiresAction: requiresAction,
    messageKey: messageKey,
    messageParams: messageParams,
  );

  factory NotificationItem.fromJson(Map<String, dynamic> json) =>
      NotificationItem(
        id: '${json['id']}',
        // An untitled notification is not expected; when it happens the
        // screen substitutes a translated placeholder rather than this
        // model inventing copy it cannot localize.
        title: json['title'] as String? ?? '',
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
        // Older rows predate these fields, so each falls back to the value
        // the server itself defaults to rather than to null.
        priority: json['priority'] as String? ?? 'NORMAL',
        category: json['category'] as String? ?? 'SYSTEM',
        requiresAction: json['requiresAction'] as bool? ?? false,
        messageKey: json['messageKey'] as String?,
        messageParams: switch (json['messageParamsJson']) {
          final Map<String, dynamic> params => params,
          _ => const {},
        },
      );
}
