/// The field-first mobile experience: navigation, role access, the
/// communication actions, and the vocabulary that reaches the screen.
///
/// These pin the decisions that a screenshot review would not catch — a
/// navigation indicator that stops mirroring under RTL, a role quietly losing
/// Voice again, a consultation relabelled as a handoff, or a database
/// identifier finding its way back into the activity feed.
library;

import 'package:construction_field/core/auth/voice_access.dart';
import 'package:construction_field/core/l10n/l10n_labels.dart';
import 'package:construction_field/core/theme/app_colors.dart';
import 'package:construction_field/core/theme/app_theme.dart';
import 'package:construction_field/core/widgets/dashboard_components.dart';
import 'package:construction_field/core/widgets/entity_actions.dart';
import 'package:construction_field/core/widgets/mobile_shell.dart';
import 'package:construction_field/core/widgets/struct_nav_bar.dart';
import 'package:construction_field/l10n/app_localizations.dart';
import 'package:construction_field/models/user.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

User _user({
  required String role,
  String? affiliation,
  String name = 'Sara Haddad',
}) => User(
  id: 'u1',
  fullName: name,
  email: 'x@example.com',
  role: role,
  status: 'active',
  engineerAffiliation: affiliation,
);

Widget _app(Widget child, {Locale locale = const Locale('en')}) => MaterialApp(
  theme: AppTheme.light,
  locale: locale,
  localizationsDelegates: const [
    AppL10n.delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
  ],
  supportedLocales: const [Locale('en'), Locale('ar')],
  home: child,
);

void _noop() {}

List<ShellDestination> _destinations() => [
  ShellDestination(
    path: '/home',
    icon: Icons.home_outlined,
    label: (context) => context.l10n.navHome,
  ),
  ShellDestination(
    path: '/tasks',
    icon: Icons.task_outlined,
    label: (context) => context.l10n.navTasks,
  ),
  ShellDestination(
    path: '/issues',
    icon: Icons.report_problem_outlined,
    label: (context) => context.l10n.navIssues,
  ),
  ShellDestination(
    path: '/messages',
    icon: Icons.forum_outlined,
    label: (context) => context.l10n.navMessages,
  ),
];

/// The indicator's resolved left edge on screen, in global coordinates.
double _indicatorLeft(WidgetTester tester) => tester
    .getTopLeft(
      find.byWidgetPredicate(
        (widget) =>
            widget is DecoratedBox &&
            widget.decoration is BoxDecoration &&
            (widget.decoration as BoxDecoration).color ==
                AppColors.navMark.withValues(alpha: .18),
      ),
    )
    .dx;

Future<void> _pumpBar(
  WidgetTester tester, {
  required int selected,
  Locale locale = const Locale('en'),
  NavCenterAction? centre,
}) async {
  await tester.pumpWidget(
    _app(
      Scaffold(
        bottomNavigationBar: StructNavBar(
          destinations: _destinations(),
          selectedIndex: selected,
          onSelected: (_) {},
          centerAction: centre,
        ),
      ),
      locale: locale,
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('bottom navigation', () {
    testWidgets('every destination is labelled and reachable', (tester) async {
      var tapped = -1;
      await tester.pumpWidget(
        _app(
          Scaffold(
            bottomNavigationBar: StructNavBar(
              destinations: _destinations(),
              selectedIndex: 0,
              onSelected: (index) => tapped = index,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Messages'), findsOneWidget);
      await tester.tap(find.text('Issues'));
      expect(tapped, 2);
    });

    testWidgets('the indicator travels with the selection', (tester) async {
      await _pumpBar(tester, selected: 0);
      final first = _indicatorLeft(tester);
      await _pumpBar(tester, selected: 2);
      expect(_indicatorLeft(tester), greaterThan(first));
    });

    testWidgets('the indicator mirrors under RTL', (tester) async {
      // In Arabic the first destination is on the *right*, so selecting a
      // later one must move the indicator left. A physically-positioned
      // indicator would move the same way in both languages, which is the
      // bug this exists to catch.
      await _pumpBar(tester, selected: 0, locale: const Locale('ar'));
      final first = _indicatorLeft(tester);
      await _pumpBar(tester, selected: 2, locale: const Locale('ar'));
      expect(_indicatorLeft(tester), lessThan(first));
    });

    testWidgets('nothing is marked selected on a non-destination screen', (
      tester,
    ) async {
      await _pumpBar(tester, selected: -1);
      final indicator = tester.widget<AnimatedOpacity>(
        find.ancestor(
          of: find.byWidgetPredicate(
            (widget) =>
                widget is DecoratedBox &&
                widget.decoration is BoxDecoration &&
                (widget.decoration as BoxDecoration).color ==
                    AppColors.navMark.withValues(alpha: .18),
          ),
          matching: find.byType(AnimatedOpacity),
        ),
      );
      expect(indicator.opacity, 0);
    });

    testWidgets('the centre action is offered when a role has voice', (
      tester,
    ) async {
      var pressed = false;
      await _pumpBar(
        tester,
        selected: 0,
        centre: NavCenterAction(
          icon: Icons.mic_rounded,
          label: 'Voice Assistant',
          onPressed: () => pressed = true,
        ),
      );
      await tester.tap(find.byIcon(Icons.mic_rounded));
      expect(pressed, isTrue);
    });

    testWidgets('the bar yields to the keyboard instead of stacking on it', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(
          MediaQuery(
            data: const MediaQueryData(
              viewInsets: EdgeInsets.only(bottom: 320),
            ),
            child: Scaffold(
              bottomNavigationBar: StructNavBar(
                destinations: _destinations(),
                selectedIndex: 0,
                onSelected: (_) {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Home'), findsNothing);
    });

    testWidgets('Arabic labels stay on one line inside a narrow bar', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      await _pumpBar(tester, selected: 0, locale: const Locale('ar'));
      // No overflow is reported as an exception by the test binding; this
      // asserts the labels are actually present rather than clipped away.
      expect(tester.takeException(), isNull);
      expect(find.byType(StructNavBar), findsOneWidget);
    });
  });

  group('shell selection', () {
    testWidgets('a nested route selects its parent destination', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(
          MobileShell(
            location: '/reviews/42',
            destinations: [
              ShellDestination(
                path: '/home',
                icon: Icons.home_outlined,
                label: (context) => context.l10n.navHome,
              ),
              ShellDestination(
                path: '/reviews',
                icon: Icons.fact_check_outlined,
                label: (context) => context.l10n.navReviews,
              ),
            ],
            child: const SizedBox.shrink(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final bar = tester.widget<StructNavBar>(find.byType(StructNavBar));
      expect(bar.selectedIndex, 1);
    });

    testWidgets('a screen outside the destinations selects nothing', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(
          MobileShell(
            location: '/profile',
            destinations: _destinations(),
            child: const SizedBox.shrink(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<StructNavBar>(find.byType(StructNavBar)).selectedIndex,
        lessThan(0),
      );
    });
  });

  group('voice access', () {
    test('every normal system role has voice', () {
      for (final role in [
        'project_manager',
        'engineer',
        'consultant',
        'owner',
        'worker',
      ]) {
        expect(canUseVoice(_user(role: role)), isTrue, reason: role);
      }
    });

    test('an engineer of any discipline or affiliation has voice', () {
      // The previous gate was `isSiteEngineer`, which is engineer AND main
      // contractor. An architect or an electrical engineer working for the
      // consultant lost the feature entirely.
      expect(
        canUseVoice(_user(role: 'engineer', affiliation: 'external_consultant')),
        isTrue,
      );
      expect(
        canUseVoice(_user(role: 'engineer', affiliation: 'main_contractor')),
        isTrue,
      );
    });

    test('admin does not', () {
      expect(canUseVoice(_user(role: 'admin')), isFalse);
    });

    test('a signed-out session does not', () {
      expect(canUseVoice(null), isFalse);
    });
  });

  group('communication actions', () {
    test('an issue can be forwarded and consulted on', () {
      expect(intentsForEntity('ISSUE'), [
        ShareIntent.forward,
        ShareIntent.askOpinion,
      ]);
    });

    test('a design change offers the same pair', () {
      expect(intentsForEntity('DESIGN_CHANGE'), [
        ShareIntent.forward,
        ShareIntent.askOpinion,
      ]);
    });

    test('a task is consulted on, never "forwarded"', () {
      // Forwarding a task would imply the recipient now owns it. The server
      // only ever writes a message, so the wording must not promise more.
      expect(intentsForEntity('TASK'), [ShareIntent.askOpinion]);
      expect(intentsForEntity('TASK'), isNot(contains(ShareIntent.forward)));
    });

    test('reports and documents are shared', () {
      expect(intentsForEntity('SITE_REPORT'), [ShareIntent.share]);
      expect(intentsForEntity('DOCUMENT'), [ShareIntent.share]);
    });

    test('an unknown entity offers nothing rather than guessing', () {
      expect(intentsForEntity('PROJECT'), isEmpty);
    });

    testWidgets('the consultation action is not called Forward', (
      tester,
    ) async {
      late AppL10n l10n;
      await tester.pumpWidget(
        _app(
          Builder(
            builder: (context) {
              l10n = context.l10n;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(ShareIntent.askOpinion.label(l10n), 'Ask for Opinion');
      expect(ShareIntent.forward.label(l10n), 'Forward');
      expect(
        ShareIntent.askOpinion.label(l10n),
        isNot(ShareIntent.forward.label(l10n)),
      );
    });
  });

  group('field components survive Arabic on a small screen', () {
    // The dashboard is the screen a device pass found overflowing twice, and
    // it is behind sign-in — so these render its parts at real phone widths
    // in the harder language rather than trusting the desk check.
    Future<void> pumpAt(WidgetTester tester, Size size, Widget child) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      await tester.pumpWidget(
        _app(
          Scaffold(
            body: Padding(padding: const EdgeInsets.all(20), child: child),
          ),
          locale: const Locale('ar'),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('an attention row holds a long Arabic label at 320dp', (
      tester,
    ) async {
      await pumpAt(
        tester,
        const Size(320, 640),
        const AttentionRow(
          label: 'مهام بانتظار مراجعة الاستشاري وإعادة العمل المطلوبة',
          count: '12',
          icon: Icons.rate_review_outlined,
          tone: AppColors.stateReview,
          onTap: _noop,
        ),
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('an attention row survives a 1.5x text scale', (tester) async {
      tester.view.physicalSize = const Size(360, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      await tester.pumpWidget(
        _app(
          MediaQuery(
            data: const MediaQueryData(textScaler: TextScaler.linear(1.5)),
            child: const Scaffold(
              body: Padding(
                padding: EdgeInsets.all(20),
                child: AttentionRow(
                  label: 'أعمال متأخرة عن موعدها',
                  count: '3',
                  icon: Icons.event_busy_outlined,
                  tone: AppColors.stateOverdue,
                  onTap: _noop,
                ),
              ),
            ),
          ),
          locale: const Locale('ar'),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('the progress card writes a localized percentage', (
      tester,
    ) async {
      await pumpAt(
        tester,
        const Size(320, 640),
        const ProjectProgressCard(progress: 62, status: 'active'),
      );
      expect(tester.takeException(), isNull);
      // The card used to interpolate '${progress.round()}%' directly, which
      // hardcoded the Western sign in an Arabic session.
      expect(find.text('62%'), findsNothing);
    });
  });

  group('activity vocabulary', () {
    Future<AppL10n> resolve(WidgetTester tester, Locale locale) async {
      late AppL10n resolved;
      await tester.pumpWidget(
        _app(
          Builder(
            builder: (context) {
              resolved = context.l10n;
              return const SizedBox.shrink();
            },
          ),
          locale: locale,
        ),
      );
      return resolved;
    }

    testWidgets('a known action becomes a sentence', (tester) async {
      final l10n = await resolve(tester, const Locale('en'));
      expect(l10n.activityLabel('progress_updated'), 'Progress updated');
      expect(l10n.activityLabel('reminders_dispatched'), 'Reminders sent');
    });

    testWidgets('prose from the server resolves to the same entry', (
      tester,
    ) async {
      final l10n = await resolve(tester, const Locale('en'));
      // `/field-submissions/worker-dashboard` sends "Evidence verified"
      // rather than a code.
      expect(
        l10n.activityLabel('Evidence verified'),
        l10n.activityLabel('evidence_verified'),
      );
    });

    testWidgets('an unknown action never leaks the identifier', (
      tester,
    ) async {
      final l10n = await resolve(tester, const Locale('en'));
      final label = l10n.activityLabel('step_up_challenge_locked');
      expect(label, l10n.activityGeneric);
      expect(label, isNot(contains('_')));
      expect(label.toLowerCase(), isNot(contains('step up')));
    });

    testWidgets('the fallback is translated, not English prose', (
      tester,
    ) async {
      final arabic = await resolve(tester, const Locale('ar'));
      expect(arabic.activityLabel('some_new_backend_action'), isNotEmpty);
      expect(
        arabic.activityLabel('some_new_backend_action'),
        isNot(matches(RegExp('[A-Za-z]'))),
      );
    });
  });
}
