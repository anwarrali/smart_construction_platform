/// Voice action execution: identity, and telling the truth about the result.
///
/// These reproduce a real production failure. A contractor engineer recorded
/// one note that produced two actions — `UPDATE_TASK_PROGRESS` and
/// `SUBMIT_TASK_FOR_REVIEW`. The review action is the one that reaches the
/// consultant. What actually happened:
///
///   * the review action's payload was written onto the progress draft,
///   * the progress action was then rejected for carrying the *other*
///     action's fields,
///   * the review action was never selected, so the consultant was never
///     notified,
///   * and the app displayed a green "Action completed".
///
/// The cause was positional identity: the confirm call took an index into the
/// model's `suggestedActions` and used it to subscript the server's
/// `actionDrafts` — a different list, ordered by a column that is identical
/// for every draft of one analysis and could therefore come back in a
/// different order once a row had been rewritten.
library;

import 'package:construction_field/core/network/api_client.dart';
import 'package:construction_field/features/voice_command/voice_outcome.dart';
import 'package:construction_field/models/voice_draft.dart';
import 'package:construction_field/services/voice_service.dart';
import 'package:construction_field/l10n/app_localizations.dart';
import 'package:construction_field/core/l10n/l10n_labels.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

/// Records every call and answers with canned analysis payloads.
///
/// Critically, it can return the draft list in a **different order** on each
/// response — which is exactly what the real server did, and what no test
/// previously exercised.
class _FakeApi implements ApiClient {
  _FakeApi({
    required this.drafts,
    this.reverseAfterFirstPut = false,
  });

  final List<Map<String, dynamic>> drafts;
  final bool reverseAfterFirstPut;

  final List<String> putPaths = <String>[];
  final List<Map<String, dynamic>> putBodies = <Map<String, dynamic>>[];
  List<String> confirmedDraftIds = const [];
  bool detailedConfirmation = false;
  int _puts = 0;

  Map<String, dynamic> _analysis() {
    final ordered = reverseAfterFirstPut && _puts > 0
        ? drafts.reversed.toList()
        : drafts;
    return {
      'id': 'analysis-1',
      'projectId': 'project-1',
      'status': 'READY_FOR_CONFIRMATION',
      'confirmationStatus': 'PENDING',
      'retryCount': 0,
      'rowVersion': 1 + _puts,
      'actionDrafts': ordered,
      'actionResults': const <Map<String, dynamic>>[],
    };
  }

  @override
  Future<T> put<T>(String path, {Object? data, Map<String, dynamic>? query}) async {
    putPaths.add(path);
    putBodies.add(Map<String, dynamic>.from(data! as Map));
    _puts++;
    return _analysis() as T;
  }

  @override
  Future<T> post<T>(String path, {Object? data}) async {
    final body = Map<String, dynamic>.from(data! as Map);
    if (path.endsWith('/confirm')) {
      confirmedDraftIds = List<String>.from(
        body['selectedDraftIds'] as List? ?? const [],
      );
      detailedConfirmation = body['detailedConfirmation'] == true;
    }
    return _analysis() as T;
  }

  @override
  Future<T> get<T>(String path, {Map<String, dynamic>? query}) async =>
      _analysis() as T;

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw UnimplementedError('${invocation.memberName}');
}

Map<String, dynamic> _draft({
  required String id,
  required int sequence,
  required String type,
  required Map<String, dynamic> payload,
  String risk = 'LOW',
}) => {
  'id': id,
  'sequence': sequence,
  'actionType': type,
  'targetEntityId': 'task-1',
  'extractedPayload': payload,
  'confidence': 0.98,
  'missingFields': <String>[],
  'warnings': <String>[],
  'riskLevel': risk,
  'requiredEvidence': <String>[],
};

/// The exact pair of actions from the production failure.
List<Map<String, dynamic>> _productionDrafts() => [
  _draft(
    id: 'draft-progress',
    sequence: 0,
    type: 'UPDATE_TASK_PROGRESS',
    payload: {'progressPercentage': 100.0, 'note': 'تم صب القواعد'},
  ),
  _draft(
    id: 'draft-review',
    sequence: 1,
    type: 'SUBMIT_TASK_FOR_REVIEW',
    risk: 'HIGH',
    payload: {'completionNote': 'بانتظار مراجعة الاستشاري'},
  ),
];

VoiceAnalysis _analysisFrom(List<Map<String, dynamic>> drafts) =>
    VoiceAnalysis.fromJson({
      'id': 'analysis-1',
      'projectId': 'project-1',
      'status': 'READY_FOR_CONFIRMATION',
      'confirmationStatus': 'PENDING',
      'retryCount': 0,
      'rowVersion': 1,
      'actionDrafts': drafts,
    });

Map<String, dynamic> _result(String type, bool success, {String message = ''}) =>
    {
      'type': type,
      'success': success,
      'status': success ? 'EXECUTED' : 'REJECTED',
      'message': message,
    };

Future<AppL10n> _l10n(WidgetTester tester, Locale locale) async {
  late AppL10n resolved;
  await tester.pumpWidget(
    MaterialApp(
      locale: locale,
      localizationsDelegates: const [
        AppL10n.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en'), Locale('ar')],
      home: Builder(
        builder: (context) {
          resolved = context.l10n;
          return const SizedBox.shrink();
        },
      ),
    ),
  );
  return resolved;
}

void main() {
  group('action identity survives the confirm round trip', () {
    test('each draft receives its own payload, addressed by id', () async {
      final drafts = _productionDrafts();
      final api = _FakeApi(drafts: drafts);
      final analysis = _analysisFrom(drafts);

      await VoiceProcessingService(api).confirmActions(
        'analysis-1',
        [
          VoiceDraftConfirmation(
            draftId: 'draft-progress',
            payload: const {'progressPercentage': 100.0},
          ),
          VoiceDraftConfirmation(
            draftId: 'draft-review',
            payload: const {'completionNote': 'ready'},
          ),
        ],
        analysis,
      );

      expect(api.putPaths[0], contains('draft-progress'));
      expect(api.putPaths[1], contains('draft-review'));
      expect(api.putBodies[0]['payload'], {'progressPercentage': 100.0});
      expect(api.putBodies[1]['payload'], {'completionNote': 'ready'});
    });

    test(
      'a reordered draft list mid-flow cannot misroute a payload',
      () async {
        // This is the production bug. The server returned the drafts in a
        // different order after the first PUT, because they were ordered by a
        // timestamp identical for both. Positional addressing then wrote the
        // review payload onto the progress draft.
        final drafts = _productionDrafts();
        final api = _FakeApi(drafts: drafts, reverseAfterFirstPut: true);

        await VoiceProcessingService(api).confirmActions(
          'analysis-1',
          [
            VoiceDraftConfirmation(
              draftId: 'draft-progress',
              payload: const {'progressPercentage': 100.0},
            ),
            VoiceDraftConfirmation(
              draftId: 'draft-review',
              payload: const {'completionNote': 'ready'},
            ),
          ],
          _analysisFrom(drafts),
        );

        // The second PUT must still address the review draft even though the
        // list it came back in was reversed.
        expect(api.putPaths[1], contains('draft-review'));
        expect(
          api.putBodies[1]['payload'],
          containsPair('completionNote', 'ready'),
          reason: 'the review payload must never land on the progress draft',
        );
        expect(api.putBodies[1]['payload'].containsKey('progressPercentage'),
            isFalse);
      },
    );

    test('every selected action is confirmed, none silently dropped', () async {
      final drafts = _productionDrafts();
      final api = _FakeApi(drafts: drafts, reverseAfterFirstPut: true);

      await VoiceProcessingService(api).confirmActions(
        'analysis-1',
        const [
          VoiceDraftConfirmation(draftId: 'draft-progress'),
          VoiceDraftConfirmation(draftId: 'draft-review'),
        ],
        _analysisFrom(drafts),
      );

      // In the production failure the review draft was never selected and so
      // was marked REMOVED — the consultant heard nothing.
      expect(api.confirmedDraftIds, ['draft-progress', 'draft-review']);
    });

    test('a high-risk selection is still declared after a reorder', () async {
      final drafts = _productionDrafts();
      final api = _FakeApi(drafts: drafts, reverseAfterFirstPut: true);
      await VoiceProcessingService(api).confirmActions(
        'analysis-1',
        const [VoiceDraftConfirmation(draftId: 'draft-review')],
        _analysisFrom(drafts),
      );
      expect(api.detailedConfirmation, isTrue);
    });

    test('an unknown draft id is refused before anything is mutated', () async {
      final drafts = _productionDrafts();
      final api = _FakeApi(drafts: drafts);
      await expectLater(
        VoiceProcessingService(api).confirmActions(
          'analysis-1',
          const [VoiceDraftConfirmation(draftId: 'draft-that-vanished')],
          _analysisFrom(drafts),
        ),
        throwsA(isA<Exception>()),
      );
      expect(api.putPaths, isEmpty);
    });
  });

  group('outcome semantics', () {
    // Cases A-E from the brief.
    test('Case A — two valid actions both succeed', () {
      final results = [
        VoiceActionOutcome.fromJson(_result('UPDATE_TASK_PROGRESS', true)),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', true)),
      ];
      expect(VoiceOutcome.of(results), VoiceOutcome.success);
      expect(VoiceOutcome.of(results).isAffirmative, isTrue);
    });

    test('Case B — first fails, second succeeds', () {
      final results = [
        VoiceActionOutcome.fromJson(_result('UPDATE_TASK_PROGRESS', false)),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', true)),
      ];
      expect(VoiceOutcome.of(results), VoiceOutcome.partial);
      expect(VoiceOutcome.of(results).isAffirmative, isFalse);
    });

    test('Case C — first succeeds, second fails', () {
      final results = [
        VoiceActionOutcome.fromJson(_result('UPDATE_TASK_PROGRESS', true)),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', false)),
      ];
      expect(VoiceOutcome.of(results), VoiceOutcome.partial);
      expect(VoiceOutcome.of(results).isAffirmative, isFalse);
    });

    test('Case D — both fail, exactly the production case', () {
      final results = [
        VoiceActionOutcome.fromJson(
          _result(
            'UPDATE_TASK_PROGRESS',
            false,
            message:
                'Unsupported fields for UPDATE_TASK_PROGRESS: completionNote,'
                ' location, recipientRoles, sourceDiscipline, subject',
          ),
        ),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', false)),
      ];
      expect(VoiceOutcome.of(results), VoiceOutcome.failure);
      expect(
        VoiceOutcome.of(results).isAffirmative,
        isFalse,
        reason: 'this is the case that used to show a green success shield',
      );
    });

    test('Case E — three actions, mixed', () {
      final results = [
        VoiceActionOutcome.fromJson(_result('UPDATE_TASK_PROGRESS', true)),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', false)),
        VoiceActionOutcome.fromJson(_result('ADD_TASK_NOTE', true)),
      ];
      expect(VoiceOutcome.of(results), VoiceOutcome.partial);
    });

    test('no results at all is "nothing", never success', () {
      expect(VoiceOutcome.of(const []), VoiceOutcome.nothing);
      expect(VoiceOutcome.of(const []).isAffirmative, isFalse);
    });

    test('success requires every action, not merely one', () {
      final results = [
        VoiceActionOutcome.fromJson(_result('UPDATE_TASK_PROGRESS', true)),
        VoiceActionOutcome.fromJson(_result('SUBMIT_TASK_FOR_REVIEW', false)),
      ];
      expect(
        results.any((item) => item.succeeded),
        isTrue,
        reason: 'guards against reverting to an any() based success test',
      );
      expect(VoiceOutcome.of(results).isAffirmative, isFalse);
    });
  });

  group('failure explanations are localized, never raw backend text', () {
    testWidgets('a field rejection becomes an actionable sentence', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('en'));
      final outcome = VoiceActionOutcome.fromJson(
        _result(
          'UPDATE_TASK_PROGRESS',
          false,
          message:
              'Unsupported fields for UPDATE_TASK_PROGRESS: completionNote,'
              ' location. Allowed fields: correctionConfirmed, note,'
              ' progressPercentage.',
        ),
      );
      final reason = outcome.reason(l10n)!;
      expect(reason, l10n.voiceOutcomeRejectedFields);
      // Internal field names must not reach a site engineer.
      expect(reason, isNot(contains('recipientRoles')));
      expect(reason, isNot(contains('Unsupported')));
    });

    testWidgets('Arabic gets Arabic, not the English server message', (
      tester,
    ) async {
      final arabic = await _l10n(tester, const Locale('ar'));
      final outcome = VoiceActionOutcome.fromJson(
        _result('SUBMIT_TASK_FOR_REVIEW', false, message: 'Task not found'),
      );
      final reason = outcome.reason(arabic)!;
      expect(reason, isNotEmpty);
      expect(reason, isNot(matches(RegExp('[A-Za-z]'))));
    });

    testWidgets('a successful action has no failure reason', (tester) async {
      final l10n = await _l10n(tester, const Locale('en'));
      final outcome = VoiceActionOutcome.fromJson(
        _result('UPDATE_TASK_PROGRESS', true),
      );
      expect(outcome.reason(l10n), isNull);
    });

    testWidgets('every outcome has a distinct localized title', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      final titles = VoiceOutcome.values.map((value) => value.title(l10n));
      expect(titles.toSet().length, VoiceOutcome.values.length);
      expect(
        VoiceOutcome.failure.title(l10n),
        isNot(VoiceOutcome.success.title(l10n)),
      );
    });
  });
}
