import '../models/chat_message.dart';
import '../services/message_service.dart';

class MessageRepository {
  MessageRepository(this._service);
  final MessageService _service;
  Future<RecipientOptions> recipientOptions(String projectId) =>
      _service.recipientOptions(projectId);
  Future<List<ProjectConversation>> conversations(String projectId) =>
      _service.conversations(projectId);
  Future<ProjectConversation> conversation(String id) =>
      _service.conversation(id);
  Future<ProjectConversation?> context(String projectId, String type, String id) =>
      _service.context(projectId, type, id);
  Future<ProjectConversation> create({
    required String projectId, required List<String> recipientIds,
    String? groupCode, String? title, required String content,
  }) => _service.create(
    projectId: projectId, recipientIds: recipientIds,
    groupCode: groupCode, title: title, content: content,
  );
  Future<ProjectConversation> announce({
    required String projectId, required String groupCode,
    required String content, String? title,
  }) => _service.announce(
    projectId: projectId, groupCode: groupCode,
    content: content, title: title,
  );
  Future<ProjectConversation> createContext({
    required String projectId, required String type,
    required String contextId, required String content,
  }) => _service.createContext(
    projectId: projectId, type: type,
    contextId: contextId, content: content,
  );
  Future<ProjectConversation> forward({
    required String messageId, required List<String> recipientIds,
    String? groupCode, String? note, String? title,
  }) => _service.forward(
    messageId: messageId, recipientIds: recipientIds,
    groupCode: groupCode, note: note, title: title,
  );
  Future<ProjectConversation> shareEntity({
    required String entityType, required String entityId,
    required List<String> recipientIds,
    String? groupCode, String? note, String? title,
  }) => _service.shareEntity(
    entityType: entityType, entityId: entityId, recipientIds: recipientIds,
    groupCode: groupCode, note: note, title: title,
  );
  Future<ChatMessage> send(String conversationId, String content) =>
      _service.send(conversationId, content);
  Future<void> markRead(String conversationId) => _service.markRead(conversationId);
}
