import 'user.dart';

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.senderId,
    required this.content,
    required this.sender,
    required this.createdAt,
  });
  final String id;
  final String conversationId;
  final String senderId;
  final String content;
  final User sender;
  final DateTime createdAt;

  factory ChatMessage.fromJson(Map<String, dynamic> json) => ChatMessage(
    id: '${json['id']}',
    conversationId: '${json['conversationId']}',
    senderId: '${json['senderId']}',
    content: json['content'] as String? ?? '',
    sender: User.fromJson(json['sender'] as Map<String, dynamic>? ?? const {}),
    createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ?? DateTime.now(),
  );
}

class ConversationParticipant {
  const ConversationParticipant({required this.userId, required this.user});
  final String userId;
  final User user;
  factory ConversationParticipant.fromJson(Map<String, dynamic> json) =>
      ConversationParticipant(
        userId: '${json['userId']}',
        user: User.fromJson(json['user'] as Map<String, dynamic>? ?? const {}),
      );
}

class ProjectConversation {
  const ProjectConversation({
    required this.id,
    required this.projectId,
    required this.type,
    required this.lastActivityAt,
    required this.participants,
    required this.unreadCount,
    this.title,
    this.contextType,
    this.contextId,
    this.lastMessage,
    this.messages = const [],
  });
  final String id;
  final String projectId;
  final String type;
  final String? title;
  final String? contextType;
  final String? contextId;
  final DateTime lastActivityAt;
  final List<ConversationParticipant> participants;
  final int unreadCount;
  final ChatMessage? lastMessage;
  final List<ChatMessage> messages;

  factory ProjectConversation.fromJson(Map<String, dynamic> json) =>
      ProjectConversation(
        id: '${json['id']}',
        projectId: '${json['projectId']}',
        type: json['type'] as String? ?? 'DIRECT',
        title: json['title'] as String?,
        contextType: json['contextType'] as String?,
        contextId: json['contextId'] == null ? null : '${json['contextId']}',
        lastActivityAt: DateTime.tryParse(json['lastActivityAt'] as String? ?? '') ?? DateTime.now(),
        participants: (json['participants'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ConversationParticipant.fromJson)
            .toList(),
        unreadCount: json['unreadCount'] as int? ?? 0,
        lastMessage: json['lastMessage'] is Map<String, dynamic>
            ? ChatMessage.fromJson(json['lastMessage'] as Map<String, dynamic>)
            : null,
        messages: (json['messages'] as List? ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(ChatMessage.fromJson)
            .toList(),
      );
}

class RecipientGroup {
  const RecipientGroup({required this.code, required this.label, required this.recipientCount});
  final String code;
  final String label;
  final int recipientCount;
  factory RecipientGroup.fromJson(Map<String, dynamic> json) => RecipientGroup(
    code: json['code'] as String? ?? '',
    label: json['label'] as String? ?? '',
    recipientCount: json['recipientCount'] as int? ?? 0,
  );
}

class RecipientOptions {
  const RecipientOptions({required this.users, required this.groups});
  final List<User> users;
  final List<RecipientGroup> groups;
  factory RecipientOptions.fromJson(Map<String, dynamic> json) => RecipientOptions(
    users: (json['users'] as List? ?? const [])
        .whereType<Map<String, dynamic>>().map(User.fromJson).toList(),
    groups: (json['groups'] as List? ?? const [])
        .whereType<Map<String, dynamic>>().map(RecipientGroup.fromJson).toList(),
  );
}
