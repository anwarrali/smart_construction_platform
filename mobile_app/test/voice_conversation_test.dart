import 'package:flutter_test/flutter_test.dart';
import 'package:construction_field/models/voice_draft.dart';

/// What the voice screen is allowed to show, and when.
///
/// Three rules, each one a thing the screen used to get wrong:
///
///  * The reply is shown in the language it was *spoken* in, not the language
///    the app happens to be set to.
///  * A half-specified proposal is never offered for review. "Task: unknown,
///    Progress: 50%" is not something a person can confirm.
///  * A question is asked once, in one language, rather than stacked in two.
void main() {
  Map<String, dynamic> analysisJson({
    Map<String, dynamic>? answer,
    List<Map<String, dynamic>> drafts = const [],
    String replyLanguage = 'ar',
    String status = 'NEEDS_CLARIFICATION',
  }) => {
    'id': 'analysis-1',
    'projectId': 'project-1',
    'status': status,
    'confirmationStatus': 'PENDING',
    'retryCount': 0,
    'rowVersion': 1,
    'providerMetadata': {'route': 'ACTION', 'replyLanguage': replyLanguage},
    'structuredResult': {
      'summary': 'spoken content',
      if (answer != null) 'answer': answer,
    },
    'actionDrafts': drafts,
    'clarifications': const [],
  };

  Map<String, dynamic> draftJson({List<String> missing = const []}) => {
    'id': 'draft-1',
    'sequence': 0,
    'actionType': 'UPDATE_TASK_PROGRESS',
    'extractedPayload': {'progressPercentage': 50},
    'confidence': 0.8,
    'missingFields': missing,
  };

  group('the reply follows the speaker', () {
    test('a composed sentence is preferred over the templates', () {
      final answer = VoiceAnswer.fromJson({
        'topic': 'PROJECT_PROGRESS',
        'text': 'المشروع منجز حوالي 45% لهلأ.',
        'language': 'ar',
        'textEn': 'The project is at 45% overall.',
        'textAr': 'المشروع منجز بنسبة 45% إجمالاً.',
      });
      // Even in an English interface: the question was asked in Arabic.
      expect(answer.textFor('en'), 'المشروع منجز حوالي 45% لهلأ.');
      expect(answer.hasText, isTrue);
    });

    test('an older backend without a composed sentence still answers', () {
      final answer = VoiceAnswer.fromJson({
        'topic': 'PROJECT_PROGRESS',
        'textEn': 'The project is at 45% overall.',
        'textAr': 'المشروع منجز بنسبة 45% إجمالاً.',
      });
      expect(answer.textFor('ar'), 'المشروع منجز بنسبة 45% إجمالاً.');
      expect(answer.textFor('en'), 'The project is at 45% overall.');
    });

    test('the analysis carries the language it was answered in', () {
      final analysis = VoiceAnalysis.fromJson(analysisJson());
      expect(analysis.replyLanguage, 'ar');
    });
  });

  group('review waits for a complete proposal', () {
    test('a draft missing its task is not reviewable', () {
      final analysis = VoiceAnalysis.fromJson(
        analysisJson(drafts: [draftJson(missing: const ['target.taskId'])]),
      );
      expect(analysis.hasProposal, isTrue);
      expect(analysis.hasCompleteProposal, isFalse);
    });

    test('a fully specified draft is reviewable', () {
      final analysis = VoiceAnalysis.fromJson(
        analysisJson(
          drafts: [draftJson()],
          status: 'READY_FOR_CONFIRMATION',
        ),
      );
      expect(analysis.hasCompleteProposal, isTrue);
    });
  });

  group('nothing a person says is met with an empty screen', () {
    // The reported bug: the assistant asks "ما فهمت قصدك", the engineer
    // answers, and the screen goes blank. The command comes back still in
    // NEEDS_CLARIFICATION, its only clarification now answered — so the
    // question card is gone — while the answer card was gated on that same
    // status and stayed hidden.
    test('an answered clarification no longer hides the reply', () {
      final analysis = VoiceAnalysis.fromJson(
        analysisJson(
          answer: {
            'topic': 'CLARIFICATION',
            'text': 'تمام، فهمت إن المواد الكهربائية تأخرت. بأي مهمة؟',
            'language': 'ar',
          },
          // Every clarification answered: the parser keeps only unanswered
          // ones, so this arrives empty.
          status: 'NEEDS_CLARIFICATION',
        ),
      );
      expect(analysis.isAsking, isFalse);
      expect(analysis.answered, isTrue);
      expect(analysis.hasNothingToShow, isFalse);
    });

    test('a question still on screen keeps the reply out of the way', () {
      final analysis = VoiceAnalysis.fromJson({
        ...analysisJson(
          answer: {'topic': 'CLARIFICATION', 'text': 'أي مهمة تقصد؟', 'language': 'ar'},
        ),
        'clarifications': [
          {
            'id': 'clar-1',
            'questionAr': 'أي مهمة تقصد؟',
            'questionEn': 'Which task do you mean?',
            'expectedAnswerType': 'TASK_SELECTION',
          },
        ],
      });
      expect(analysis.isAsking, isTrue);
      expect(analysis.hasNothingToShow, isFalse);
    });

    test('a command with no question, no proposal and no reply is caught', () {
      final analysis = VoiceAnalysis.fromJson(analysisJson());
      expect(analysis.isAsking, isFalse);
      expect(analysis.answered, isFalse);
      expect(analysis.hasCompleteProposal, isFalse);
      // The screen shows its last-resort line rather than nothing at all.
      expect(analysis.hasNothingToShow, isTrue);
    });

    test('a failed command is not treated as an empty one', () {
      final analysis = VoiceAnalysis.fromJson(analysisJson(status: 'FAILED'));
      expect(analysis.failed, isTrue);
      expect(analysis.hasNothingToShow, isFalse);
    });
  });

  group('a question is asked once', () {
    test('the spoken language decides which wording is shown', () {
      final question = VoiceClarificationItem.fromJson({
        'id': 'clar-1',
        'questionAr': 'تمام، فهمت إن التقدم صار 50%. أي مهمة تقصد؟',
        'questionEn': 'Which task do you mean?',
        'expectedAnswerType': 'TASK_SELECTION',
      });
      expect(question.questionFor('ar'), startsWith('تمام'));
      expect(question.questionFor('en'), 'Which task do you mean?');
    });

    test('a missing half falls back rather than showing nothing', () {
      final question = VoiceClarificationItem.fromJson({
        'id': 'clar-2',
        'questionAr': 'شو المشكلة اللي بدك تسجلها؟',
        'questionEn': '',
        'expectedAnswerType': 'TEXT',
      });
      expect(question.questionFor('en'), 'شو المشكلة اللي بدك تسجلها؟');
    });
  });
}
