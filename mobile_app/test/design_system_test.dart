/// The Struct IQ design system on mobile.
///
/// These tests pin the things that made the app drift from the web in the
/// first place: a stale accent colour, a rounding scale from a different
/// design language, and status colours chosen per-screen. They assert
/// against the web token values directly, so if the web rebrands again the
/// failure lands here rather than in a screenshot review months later.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:construction_field/core/theme/app_colors.dart';
import 'package:construction_field/core/theme/app_radius.dart';
import 'package:construction_field/core/theme/app_theme.dart';
import 'package:construction_field/core/widgets/brand_mark.dart';
import 'package:construction_field/core/widgets/status_badge.dart';
import 'package:construction_field/models/chat_message.dart';
import 'package:construction_field/models/notification_item.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:construction_field/l10n/app_localizations.dart';

Widget _host(Widget child, {TextDirection direction = TextDirection.ltr}) =>
    MaterialApp(
      theme: AppTheme.light,
      // The shared widgets read their copy from the message catalogue now, so
      // the host has to be a localized app rather than a bare MaterialApp.
      locale: direction == TextDirection.rtl
          ? const Locale('ar')
          : const Locale('en'),
      localizationsDelegates: const [
        AppL10n.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en'), Locale('ar')],
      home: Directionality(
        textDirection: direction,
        child: Scaffold(body: Center(child: child)),
      ),
    );

void main() {
  group('brand tokens match the web', () {
    test('the accent is Verdant Data, not the retired bronze', () {
      // The pre-rebrand app used #DD922C. Anything in that hue range means
      // the stale palette has come back.
      expect(AppColors.brandAccent, const Color(0xFF4F8C5D));
      expect(AppColors.accent, const Color(0xFF447E52));
      expect(AppColors.accent.r, lessThan(AppColors.accent.g));
    });

    test('architectural navy is the brand ink', () {
      expect(AppColors.brandInk, const Color(0xFF0F2340));
    });

    test('focus is verdant, the same signal the web uses', () {
      expect(AppColors.ring, AppColors.accent);
    });

    test('radii are the web scale, not the old consumer rounding', () {
      expect(AppRadius.chip, 3);
      expect(AppRadius.control, 5);
      expect(AppRadius.panel, 8);
      expect(AppRadius.sheet, 12);
    });

    test('the semantic ramp has one hue per meaning', () {
      final ramp = {
        AppColors.stateVerified,
        AppColors.stateProgress,
        AppColors.stateReview,
        AppColors.stateOverdue,
        AppColors.stateBlocked,
        AppColors.stateIdle,
      };
      expect(ramp.length, 6, reason: 'two states must never share a colour');
    });
  });

  group('theme', () {
    testWidgets('primary is navy and the nav surface is the dark edge', (
      tester,
    ) async {
      await tester.pumpWidget(_host(const SizedBox()));
      final theme = Theme.of(tester.element(find.byType(Scaffold)));
      expect(theme.colorScheme.primary, AppColors.primary);
      expect(theme.appBarTheme.backgroundColor, AppColors.navSurface);
      expect(theme.scaffoldBackgroundColor, AppColors.background);
    });

    testWidgets('primary buttons clear the 48dp touch target', (tester) async {
      await tester.pumpWidget(
        _host(FilledButton(onPressed: () {}, child: const Text('Save'))),
      );
      expect(tester.getSize(find.byType(FilledButton)).height,
          greaterThanOrEqualTo(48));
    });
  });

  group('brand mark', () {
    testWidgets('renders at the requested size', (tester) async {
      await tester.pumpWidget(_host(const StructIQMark(size: 48)));
      expect(tester.getSize(find.byType(StructIQMark)), const Size(48, 48));
    });

    testWidgets('the wordmark splits Struct / IQ across ink and accent', (
      tester,
    ) async {
      await tester.pumpWidget(_host(const StructIQWordmark()));
      final span = tester.widget<Text>(find.byType(Text)).textSpan!
          as TextSpan;
      final parts = span.children!.cast<TextSpan>();
      expect(parts[0].text, 'Struct');
      expect(parts[0].style!.color, AppColors.brandInk);
      expect(parts[1].text, 'IQ');
      expect(parts[1].style!.color, AppColors.brandAccent);
    });

    testWidgets('the lockup stays left-to-right in Arabic', (tester) async {
      // The Latin wordmark is the brand in both locales; a mirrored lockup
      // would read as a different logo.
      await tester.pumpWidget(
        _host(const StructIQLogo(), direction: TextDirection.rtl),
      );
      final row = tester.widget<Row>(find.byType(Row).first);
      expect(row.textDirection, TextDirection.ltr);
    });
  });

  group('status badge', () {
    test('maps backend values onto the shared ramp', () {
      expect(StatusTone.of('approved'), StatusTone.verified);
      expect(StatusTone.of('in_progress'), StatusTone.progress);
      expect(StatusTone.of('overdue'), StatusTone.overdue);
      expect(StatusTone.of('blocked'), StatusTone.blocked);
    });

    // These four are the ones the web's own `statusVariant` table in
    // TaskCard.tsx pins down, and mobile was reading three of them
    // differently. Naming them here stops the two drifting apart again.
    test('agrees with the web task table', () {
      expect(StatusTone.of('todo'), StatusTone.idle);
      expect(StatusTone.of('under_review'), StatusTone.review); // warning
      expect(StatusTone.of('rework_required'), StatusTone.overdue); // danger
      expect(StatusTone.of('cancelled'), StatusTone.idle); // neutral
    });

    test('an unknown status is idle rather than an invented colour', () {
      expect(StatusTone.of('something_new'), StatusTone.idle);
      expect(StatusTone.of(null), StatusTone.idle);
    });

    // Task 6 moved the wording into the message catalogue, so the badge no
    // longer humanises the raw value — it translates it.
    testWidgets('shows the translated status, not the raw value', (
      tester,
    ) async {
      await tester.pumpWidget(_host(const StatusBadge('under_review')));
      expect(find.text('Under review'), findsOneWidget);
    });
  });

  group('notification priority', () {
    testWidgets('critical and important are badged', (tester) async {
      await tester.pumpWidget(_host(const PriorityBadge('CRITICAL')));
      expect(find.text('Critical'), findsOneWidget);

      await tester.pumpWidget(_host(const PriorityBadge('IMPORTANT')));
      expect(find.text('Important'), findsOneWidget);
    });

    testWidgets('normal and info are silent, so the loud ones stand out', (
      tester,
    ) async {
      await tester.pumpWidget(_host(const PriorityBadge('NORMAL')));
      expect(find.byType(Text), findsNothing);

      await tester.pumpWidget(_host(const PriorityBadge(null)));
      expect(find.byType(Text), findsNothing);
    });
  });

  group('notification model reads the smart-notification fields', () {
    test('priority, category and requiresAction come from the API', () {
      final item = NotificationItem.fromJson(const {
        'id': 'n1',
        'title': 'Task overdue',
        'message': 'Slab pour is overdue.',
        'type': 'task_overdue',
        'isRead': false,
        'priority': 'CRITICAL',
        'category': 'DEADLINE',
        'requiresAction': true,
      });
      expect(item.priority, 'CRITICAL');
      expect(item.category, 'DEADLINE');
      expect(item.requiresAction, isTrue);
      expect(item.isReminder, isFalse);
    });

    test('a reminder is recognised by its category', () {
      final item = NotificationItem.fromJson(const {
        'id': 'n2',
        'title': 'Response reminder',
        'message': 'Still waiting.',
        'type': 'system',
        'isRead': false,
        'category': 'REMINDERS',
      });
      expect(item.isReminder, isTrue);
    });

    test('rows predating these fields fall back to the server defaults', () {
      final item = NotificationItem.fromJson(const {
        'id': 'n3',
        'title': 'Old',
        'message': '',
        'type': 'system',
        'isRead': true,
      });
      expect(item.priority, 'NORMAL');
      expect(item.category, 'SYSTEM');
      expect(item.requiresAction, isFalse);
    });
  });

  group('message model carries forwarding and sharing context', () {
    test('a forward exposes the true original sender', () {
      final message = ChatMessage.fromJson(const {
        'id': 'm1',
        'conversationId': 'c1',
        'senderId': 'u2',
        'content': 'Can you review this?',
        'sender': {'id': 'u2', 'fullName': 'Civil Engineer Bilal'},
        'forwardedFromMessageId': 'm0',
        'forwardOrigin': {
          'messageId': 'm0',
          'content': 'Ceiling clashes with the cable tray.',
          'sender': {'id': 'u1', 'fullName': 'Architect Anwar'},
        },
      });
      expect(message.isForward, isTrue);
      // The origin is the root of the chain, not the person who forwarded it.
      expect(message.forwardOrigin!.sender.fullName, 'Architect Anwar');
      expect(message.sender.fullName, 'Civil Engineer Bilal');
    });

    test('an entity share names what was shared', () {
      final message = ChatMessage.fromJson(const {
        'id': 'm2',
        'conversationId': 'c1',
        'senderId': 'u1',
        'content': 'Shared Issue ...',
        'sender': {'id': 'u1', 'fullName': 'Architect Anwar'},
        'sharedEntityType': 'ISSUE',
        'sharedEntityId': 'i1',
      });
      expect(message.isEntityShare, isTrue);
      expect(message.sharedEntityType, 'ISSUE');
    });

    test('an ordinary message is neither', () {
      final message = ChatMessage.fromJson(const {
        'id': 'm3',
        'conversationId': 'c1',
        'senderId': 'u1',
        'content': 'Morning',
        'sender': {'id': 'u1', 'fullName': 'Someone'},
      });
      expect(message.isForward, isFalse);
      expect(message.isEntityShare, isFalse);
    });
  });

  group('Arabic / RTL', () {
    testWidgets('a directional badge lays out from the right in Arabic', (
      tester,
    ) async {
      await tester.pumpWidget(
        _host(
          const StatusBadge('approved', label: 'معتمد'),
          direction: TextDirection.rtl,
        ),
      );
      expect(find.text('معتمد'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Arabic text renders in the shared components', (
      tester,
    ) async {
      await tester.pumpWidget(
        _host(
          Column(
            children: const [
              StatusBadge('overdue', label: 'متأخر'),
              PriorityBadge('CRITICAL', criticalLabel: 'حرج'),
            ],
          ),
          direction: TextDirection.rtl,
        ),
      );
      expect(find.text('متأخر'), findsOneWidget);
      expect(find.text('حرج'), findsOneWidget);
    });
  });

  group('branding is applied everywhere, not per screen', () {
    test('no source file still carries the retired product name', () {
      // The login screen shipped its own hand-rolled "CONSTRUCTION FIELD"
      // lockup, which survived the first rename because the casing differed.
      // This walks the tree so a stray copy cannot come back unnoticed.
      final offenders = <String>[];
      for (final entity in Directory('lib').listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        final text = entity.readAsStringSync().toLowerCase();
        if (text.contains('construction field')) offenders.add(entity.path);
      }
      expect(offenders, isEmpty,
          reason: 'use the shared StructIQLogo lockup instead');
    });
  });

  group('priority styling renders rather than throwing', () {
    // Regression: the priority accent was first drawn as a non-uniform
    // `Border` on a decoration that also had a `borderRadius`. That
    // combination is invalid in Flutter and rendered every IMPORTANT and
    // CRITICAL notification as a blank box — visible only on a device,
    // because the analyzer and the model tests were both perfectly happy.
    for (final priority in ['CRITICAL', 'IMPORTANT', 'NORMAL']) {
      testWidgets('a $priority card paints without an exception', (
        tester,
      ) async {
        final accent = switch (priority) {
          'CRITICAL' => AppColors.stateOverdue,
          'IMPORTANT' => AppColors.stateReview,
          _ => null,
        };
        await tester.pumpWidget(
          _host(
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(AppRadius.panel),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (accent != null)
                    Container(width: 3, color: accent),
                  const Expanded(child: Text('Task overdue')),
                  PriorityBadge(priority),
                ],
              ),
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        expect(find.text('Task overdue'), findsOneWidget);
      });
    }
  });
}
