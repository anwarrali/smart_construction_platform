import 'package:flutter_test/flutter_test.dart';
import 'package:construction_field/models/chat_message.dart';
import 'package:construction_field/models/notification_item.dart';
import 'package:construction_field/models/task.dart';
import 'package:construction_field/models/user.dart';
import 'package:construction_field/models/field_submission.dart';
import 'package:construction_field/models/voice_draft.dart';

void main() {
  test('task cannot start with incomplete dependency', () {
    final task = ProjectTask.fromJson({
      'id': 'task-1',
      'projectId': 'project-1',
      'taskCode': 'T-1',
      'name': 'Wiring',
      'status': 'todo',
      'priority': 'high',
      'progressPercentage': 0,
      'assigneeIds': ['user-1'],
      'dependencies': [
        {
          'dependsOnTaskId': 'task-0',
          'dependsOnTaskName': 'Walls',
          'dependsOnTaskStatus': 'in_progress',
        },
      ],
    });
    expect(task.canStart, isFalse);
    expect(task.hasIncompleteDependencies, isTrue);
  });

  test('the office role and disciplines are what the client reads', () {
    // The configurable model, as the server sends it. `orgRole` is the
    // office's own name for this person and `disciplines` is many-to-many —
    // an office that combines Mechanical and Electrical assigns both to one
    // engineer, which the retired single `discipline` could not express.
    final user = User.fromJson({
      'id': '1',
      'fullName': 'Field Engineer',
      'email': 'field@example.com',
      'role': 'engineer',
      'status': 'active',
      'orgRole': {
        'id': 'role-1',
        'code': 'site_engineer',
        'nameEn': 'Site Engineer',
        'isInternalOnly': true,
      },
      'disciplines': [
        {'id': 'd1', 'code': 'mechanical', 'nameEn': 'Mechanical'},
        {'id': 'd2', 'code': 'electrical', 'nameEn': 'Electrical'},
      ],
      'isInternal': true,
    });
    expect(user.orgRoleName, 'Site Engineer');
    expect(user.roleLabel, 'Site Engineer');
    expect(user.disciplines, ['mechanical', 'electrical']);
    expect(user.isInternal, isTrue);
  });

  test('an external participant is marked as one', () {
    final user = User.fromJson({
      'id': '2',
      'fullName': 'Contractor Rep',
      'email': 'rep@example.com',
      'role': 'engineer',
      'status': 'active',
      'orgRole': {
        'id': 'role-2',
        'code': 'contractor_representative',
        'nameEn': 'Main Contractor',
        'isInternalOnly': false,
      },
      'isInternal': false,
    });
    expect(user.isInternal, isFalse);
    expect(user.roleLabel, 'Main Contractor');
    expect(user.disciplines, isEmpty);
  });

  test('an account the backfill has not reached still renders', () {
    // No `orgRole`, so the retired enum is all there is. It must parse and
    // produce a label rather than throwing — the client cannot assume every
    // account has been migrated.
    final user = User.fromJson({
      'id': '3',
      'fullName': 'Legacy Account',
      'email': 'legacy@example.com',
      'role': 'project_manager',
      'status': 'active',
    });
    expect(user.orgRoleName, isNull);
    expect(user.roleLabel, 'project_manager');
    expect(user.isProjectManager, isTrue);
  });

  test('field submission preserves rejection and photo direction metadata', () {
    final submission = FieldSubmission.fromJson({
      'id': 'submission-1',
      'taskId': 'task-1',
      'status': 'REJECTED',
      'reviewComment': 'Add a rear view.',
      'createdAt': '2026-07-23T10:30:00Z',
      'photos': [
        {
          'id': 'photo-1',
          'direction': 'FRONT',
          'categories': [
            {
              'id': 'category-1',
              'name': 'Foundations',
              'code': 'FOUNDATIONS',
              'isSystem': true,
              'active': true,
            },
            {
              'id': 'category-2',
              'name': 'Concrete',
              'code': 'CONCRETE',
              'isSystem': true,
              'active': true,
            },
          ],
          'attachment': {
            'fileUrl': 'https://example.test/front.jpg',
            'originalFilename': 'front.jpg',
          },
        },
      ],
    });
    expect(submission.status, 'REJECTED');
    expect(submission.reviewComment, 'Add a rear view.');
    expect(submission.photos.single.direction, 'FRONT');
    expect(submission.photos.single.categories.length, 2);
    expect(submission.photos.single.categories.first.code, 'FOUNDATIONS');
  });

  test('notification preserves related navigation metadata', () {
    final notification = NotificationItem.fromJson({
      'id': 'notification-1',
      'title': 'Task updated',
      'message': 'Concrete inspection is ready.',
      'type': 'task_updated',
      'isRead': false,
      'taskId': 'task-1',
      'relatedEntityType': 'task',
      'relatedEntityId': 'task-1',
      'createdAt': '2026-07-19T10:30:00Z',
    });

    expect(notification.taskId, 'task-1');
    expect(notification.isRead, isFalse);
    expect(notification.copyWith(isRead: true).isRead, isTrue);
  });

  test('conversation message preserves sender and conversation context', () {
    final message = ChatMessage.fromJson({
      'id': 'message-1',
      'conversationId': 'conversation-1',
      'senderId': 'user-1',
      'content': 'Inspection is complete.',
      'createdAt': '2026-07-19T10:30:00Z',
      'sender': {
        'id': 'user-1',
        'fullName': 'Site Engineer',
        'email': 'site@example.com',
        'role': 'engineer',
        'status': 'active',
      },
    });

    expect(message.content, 'Inspection is complete.');
    expect(message.sender.fullName, 'Site Engineer');
    expect(message.conversationId, 'conversation-1');
  });

  test('conversation preserves per-user unread count and participants', () {
    final conversation = ProjectConversation.fromJson({
      'id': 'conversation-1',
      'projectId': 'project-1',
      'type': 'GROUP',
      'lastActivityAt': '2026-07-19T10:30:00Z',
      'unreadCount': 3,
      'participants': [
        {
          'userId': 'user-1',
          'user': {
            'id': 'user-1',
            'fullName': 'Site Engineer',
            'email': 'site@example.com',
            'role': 'engineer',
            'status': 'active',
          },
        },
      ],
    });
    expect(conversation.unreadCount, 3);
    expect(conversation.participants.single.user.fullName, 'Site Engineer');
  });

  test('voice analysis keeps AI suggestions separate from confirmation results', () {
    final analysis = VoiceAnalysis.fromJson({
      'id': 'analysis-1',
      'projectId': 'project-1',
      'status': 'COMPLETED',
      'confirmationStatus': 'PENDING',
      'retryCount': 0,
      'rawTranscript': 'خلصنا 60% من electrical rough-in',
      'structuredResult': {
        'summary': 'Electrical rough-in progress reported.',
        'detectedTask': {
          'taskId': 'task-1',
          'taskTitle': 'Electrical Floor 2',
          'confidence': .92,
        },
        'progress': {'mentioned': true, 'percentage': 60, 'confidence': .9},
        'discipline': {'value': 'electrical', 'confidence': .95},
        'location': {'text': 'Floor 2'},
        'workCompleted': ['Rough-in'],
        'problems': [],
        'materials': [],
        'suggestedActions': [
          {
            'type': 'UPDATE_TASK_PROGRESS',
            'reason': 'Progress explicitly mentioned',
            'targetId': 'task-1',
            'payload': {'progressPercentage': 60},
            'confidence': .9,
          },
        ],
      },
      'actionResults': [],
    });
    expect(analysis.completed, isTrue);
    expect(analysis.result!.suggestedActions.single.type, 'UPDATE_TASK_PROGRESS');
    expect(analysis.actionResults, isEmpty);
    expect(analysis.rawTranscript, contains('electrical'));
  });
}
