import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../models/chat_message.dart';

class MessageService {
  MessageService(this._api);
  final ApiClient _api;

  Future<RecipientOptions> recipientOptions(String projectId) async =>
      RecipientOptions.fromJson(await _api.get<Map<String, dynamic>>(
        ApiEndpoints.messageRecipientOptions,
        query: {'project_id': projectId},
      ));

  Future<List<ProjectConversation>> conversations(String projectId) async {
    final response = await _api.get<Map<String, dynamic>>(
      ApiEndpoints.messageConversations,
      query: {'project_id': projectId, 'page_size': 100},
    );
    return (response['items'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(ProjectConversation.fromJson).toList();
  }

  Future<ProjectConversation> conversation(String id) async =>
      ProjectConversation.fromJson(await _api.get<Map<String, dynamic>>(
        ApiEndpoints.conversation(id),
      ));

  Future<ProjectConversation?> context(
    String projectId, String type, String contextId,
  ) async {
    final response = await _api.get<dynamic>(
      ApiEndpoints.messageContext(type, contextId),
      query: {'project_id': projectId},
    );
    return response is Map<String, dynamic>
        ? ProjectConversation.fromJson(response) : null;
  }

  Future<ProjectConversation> create({
    required String projectId,
    required List<String> recipientIds,
    String? groupCode,
    String? title,
    required String content,
  }) async => ProjectConversation.fromJson(
    await _api.post<Map<String, dynamic>>(
      ApiEndpoints.messageConversations,
      data: {
        'projectId': projectId,
        'recipientIds': recipientIds,
        if (groupCode != null) 'groupCode': groupCode,
        if (title != null) 'title': title,
        'content': content,
      },
    ),
  );

  Future<ProjectConversation> announce({
    required String projectId,
    required String groupCode,
    required String content,
    String? title,
  }) async => ProjectConversation.fromJson(
    await _api.post<Map<String, dynamic>>(
      ApiEndpoints.messageAnnouncements,
      data: {
        'projectId': projectId, 'groupCode': groupCode,
        'content': content, if (title != null) 'title': title,
      },
    ),
  );

  Future<ProjectConversation> createContext({
    required String projectId,
    required String type,
    required String contextId,
    required String content,
  }) async => ProjectConversation.fromJson(
    await _api.post<Map<String, dynamic>>(
      ApiEndpoints.messageContext(type, contextId),
      data: {
        'projectId': projectId, 'contextType': type,
        'contextId': contextId, 'content': content,
      },
    ),
  );

  Future<ChatMessage> send(String conversationId, String content) async =>
      ChatMessage.fromJson(await _api.post<Map<String, dynamic>>(
        ApiEndpoints.conversationMessages(conversationId),
        data: {'content': content},
      ));

  Future<void> markRead(String conversationId) async {
    await _api.put<Map<String, dynamic>>(
      ApiEndpoints.conversationRead(conversationId),
    );
  }
}
