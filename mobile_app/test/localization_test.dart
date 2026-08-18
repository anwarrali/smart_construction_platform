import 'package:construction_field/core/l10n/l10n_formats.dart';
import 'package:construction_field/core/l10n/l10n_labels.dart';
import 'package:construction_field/core/l10n/notification_text.dart';
import 'package:construction_field/core/network/network_exceptions.dart';
import 'package:construction_field/core/widgets/status_badge.dart';
import 'package:construction_field/l10n/app_localizations.dart';
import 'package:construction_field/models/notification_item.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

/// Renders [child] under a real localized app in [locale].
Widget _app(Locale locale, Widget child) => MaterialApp(
  locale: locale,
  localizationsDelegates: const [
    AppL10n.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  supportedLocales: const [Locale('en'), Locale('ar')],
  home: Scaffold(body: child),
);

/// Resolves [AppL10n] the way a screen does, so the tests exercise the same
/// path the app uses rather than instantiating the class directly.
Future<AppL10n> _l10n(WidgetTester tester, Locale locale) async {
  late AppL10n resolved;
  await tester.pumpWidget(
    _app(
      locale,
      Builder(
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
  group('locale resolution', () {
    testWidgets('English loads', (tester) async {
      final l10n = await _l10n(tester, const Locale('en'));
      expect(l10n.localeName, 'en');
      expect(l10n.navTasks, 'Tasks');
    });

    testWidgets('Arabic loads', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.localeName, 'ar');
      expect(l10n.navTasks, 'المهام');
    });

    testWidgets('Arabic gives the tree a right-to-left direction', (
      tester,
    ) async {
      late TextDirection direction;
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Builder(
            builder: (context) {
              direction = Directionality.of(context);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(direction, TextDirection.rtl);
    });

    testWidgets('an unsupported device locale falls back to English', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('fr'));
      expect(l10n.localeName, 'en');
    });
  });

  group('product terminology matches the web', () {
    // These are the terms the web's own ar/translation.json fixes. Pinning
    // them here is what stops the two products drifting into two different
    // Arabic vocabularies for the same workflow.
    const arabic = {
      'under_review': 'قيد المراجعة',
      'rework_required': 'تتطلب إعادة عمل',
      'blocked': 'متوقفة',
      'approved': 'معتمد',
      'rejected': 'مرفوض',
      'in_progress': 'قيد التنفيذ',
    };

    testWidgets('statuses use the web wording', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      arabic.forEach((value, expected) {
        expect(l10n.statusLabel(value), expected, reason: value);
      });
    });

    testWidgets('roles use the web wording', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.roleLabel('project_manager'), 'مدير المشروع');
      expect(l10n.roleLabel('consultant'), 'الاستشاري');
      expect(l10n.roleLabel('engineer'), 'مهندس');
    });

    testWidgets('priorities use the web wording', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.priorityLabel('critical'), 'حرجة');
      expect(l10n.priorityLabel('high'), 'عالية');
      expect(l10n.priorityLabel('important'), 'مهم');
    });

    testWidgets('an unknown status is humanised, not blank', (tester) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.statusLabel('some_new_state'), 'some new state');
      expect(l10n.statusLabel(null), '');
    });
  });

  group('user-generated content is never translated', () {
    testWidgets('a forwarded quote keeps the sender name verbatim', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      final line = l10n.communicationForwardedFrom('Sara Al-Rashid');
      expect(line, contains('Sara Al-Rashid'));
      // The label around the name is Arabic…
      expect(line, contains('مُعاد توجيهها'));
    });

    testWidgets('notification parameters are interpolated as sent', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      final item = NotificationItem(
        id: '1',
        title: 'Task overdue',
        message: 'Basement waterproofing is overdue.',
        type: 'task_overdue',
        createdAt: DateTime(2026, 8, 16),
        isRead: false,
        messageKey: 'taskDeadline.OVERDUE',
        messageParams: const {'name': 'Basement waterproofing'},
      );
      expect(l10n.notificationTitle(item), 'مهمة متأخرة');
      // The task's own name survives untranslated inside the Arabic body.
      expect(
        l10n.notificationBody(item),
        contains('Basement waterproofing'),
      );
    });
  });

  group('notifications stay compatible with the Task 3 contract', () {
    testWidgets('a notification with no messageKey shows the server text', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      final item = NotificationItem(
        id: '2',
        title: 'Something the server named',
        message: 'Body the server wrote',
        type: 'system',
        createdAt: DateTime(2026, 8, 16),
        isRead: false,
      );
      expect(l10n.notificationTitle(item), 'Something the server named');
      expect(l10n.notificationBody(item), 'Body the server wrote');
    });

    testWidgets('an unknown messageKey falls back rather than blanking', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      final item = NotificationItem(
        id: '3',
        title: 'Future notification',
        message: 'From a newer backend',
        type: 'system',
        createdAt: DateTime(2026, 8, 16),
        isRead: false,
        messageKey: 'somethingAdded.LATER',
        messageParams: const {'name': 'X'},
      );
      expect(l10n.notificationTitle(item), 'Future notification');
      expect(l10n.notificationBody(item), 'From a newer backend');
    });
  });

  group('errors are translated, not passed through', () {
    testWidgets('a known status code becomes a translated sentence', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      const error = NetworkException(
        'You do not have permission to do this',
        statusCode: 403,
        failure: NetworkFailure.badResponse,
      );
      expect(l10n.describeError(error), 'لا تملك صلاحية تنفيذ هذا الإجراء.');
    });

    testWidgets('an unknown failure gets the generic translated sentence', (
      tester,
    ) async {
      final l10n = await _l10n(tester, const Locale('ar'));
      const error = NetworkException(
        'Some internal server detail',
        statusCode: 500,
        failure: NetworkFailure.badResponse,
      );
      expect(l10n.describeError(error), l10n.errorGeneric);
      // The server's English prose is not what the user sees.
      expect(l10n.describeError(error), isNot(contains('internal')));
    });

    testWidgets('sign-in failures have their own wording', (tester) async {
      final l10n = await _l10n(tester, const Locale('en'));
      const error = NetworkException(
        null,
        statusCode: 401,
        failure: NetworkFailure.badResponse,
      );
      expect(l10n.describeLoginError(error), l10n.loginInvalidCredentials);
      expect(l10n.describeError(error), l10n.errorUnauthorized);
    });
  });

  group('dates and numbers follow the locale', () {
    // Renamed from "in its own digits": that was never what the formatter
    // did, and the assertion below only passed because the Arabic percent
    // *sign* (U+066A) differs. The policy is one numbering system —
    // Western — with the locale's own sign, so the test now says that and
    // checks the digits too.
    testWidgets('Arabic formats a percentage with the locale sign', (
      tester,
    ) async {
      late String english;
      late String arabic;
      await tester.pumpWidget(
        _app(
          const Locale('en'),
          Builder(
            builder: (context) {
              english = context.formatPercent(62);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Builder(
            builder: (context) {
              arabic = context.formatPercent(62);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(english, '62%');
      expect(arabic, isNot('62%'));
      expect(arabic, isNotEmpty);
      // Same rule as dates: no Arabic-Indic digits anywhere, so a card can
      // never show "٦٢٪" beside "17 أغسطس".
      expect(arabic, isNot(matches(RegExp('[٠-٩]'))));
      expect(arabic, contains('62'));
    });

    testWidgets('Arabic counts use the same digits as Arabic dates', (
      tester,
    ) async {
      late String arabic;
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Builder(
            builder: (context) {
              arabic = context.formatInt(1234);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      // `formatInt` used to return Arabic-Indic digits while every date on
      // the same screen was already forced to Western ones.
      expect(arabic, isNot(matches(RegExp('[٠-٩]'))));
      expect(arabic, contains('234'));
    });

    testWidgets('Arabic dates use Western digits, matching the web', (
      tester,
    ) async {
      // intl renders Arabic dates with Arabic-Indic digits but Arabic
      // numbers with Western ones, which put two numbering systems on one
      // screen. The formatter pins Western digits; this keeps it pinned.
      late String arabic;
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Builder(
            builder: (context) {
              arabic = context.formatShortDate(DateTime(2026, 8, 17));
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(arabic, contains('17'));
      expect(arabic, isNot(matches(RegExp('[٠-٩]'))));
    });

    testWidgets('counts that read wrong at one are pluralised', (
      tester,
    ) async {
      final en = await _l10n(tester, const Locale('en'));
      expect(en.projectsOpenIssues(1), '1 open issue');
      expect(en.projectsOpenIssues(3), '3 open issues');
      final ar = await _l10n(tester, const Locale('ar'));
      // Arabic has singular, dual and few forms; none of them is the
      // English-style "{count} + plural noun".
      expect(ar.projectsOpenIssues(1), isNot(contains('1')));
      expect(ar.projectsOpenIssues(2), isNot(ar.projectsOpenIssues(3)));
    });

    testWidgets('the two locales format the same date differently', (
      tester,
    ) async {
      final date = DateTime(2026, 8, 17);
      late String english;
      late String arabic;
      await tester.pumpWidget(
        _app(
          const Locale('en'),
          Builder(
            builder: (context) {
              english = context.formatShortDate(date);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Builder(
            builder: (context) {
              arabic = context.formatShortDate(date);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(english, 'Aug 17');
      expect(arabic, isNot(english));
    });
  });

  group('values from the API resolve through the right vocabulary', () {
    testWidgets('a severity is a priority word, not a status word', (
      tester,
    ) async {
      // The severity chip used to be routed through `statusLabel`, which has
      // no severity entries, so "critical" fell through untranslated.
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.priorityLabel('critical'), 'حرجة');
      expect(l10n.statusLabel('critical'), isNot('حرجة'));
    });

    testWidgets('a project status is translated, not humanised', (
      tester,
    ) async {
      // The progress ring used to print the raw value ("active").
      final l10n = await _l10n(tester, const Locale('ar'));
      expect(l10n.statusLabel('active'), 'قيد التنفيذ');
    });
  });

  group('representative screens render in both languages', () {
    testWidgets('a status badge shows Arabic wording under RTL', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(const Locale('ar'), const StatusBadge('under_review')),
      );
      expect(find.text('قيد المراجعة'), findsOneWidget);
    });

    testWidgets('the same badge shows English under LTR', (tester) async {
      await tester.pumpWidget(
        _app(const Locale('en'), const StatusBadge('under_review')),
      );
      expect(find.text('Under review'), findsOneWidget);
    });

    testWidgets('a long Arabic label does not overflow a narrow button', (
      tester,
    ) async {
      // The longest action label in the app, in the language that renders it
      // longest, inside a phone-width button.
      await tester.pumpWidget(
        _app(
          const Locale('ar'),
          Center(
            child: SizedBox(
              width: 200,
              child: Builder(
                builder: (context) => FilledButton(
                  onPressed: () {},
                  child: Text(
                    context.l10n.collabSubmitForReview,
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('Arabic survives a 1.5x accessibility text scale', (
      tester,
    ) async {
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(1.5)),
          child: _app(
            const Locale('ar'),
            Center(
              child: SizedBox(
                width: 220,
                child: Builder(
                  builder: (context) => Text(context.l10n.evidenceVerifyHint),
                ),
              ),
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
    });
  });
}
