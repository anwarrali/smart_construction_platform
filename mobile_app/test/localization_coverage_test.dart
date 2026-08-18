import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Static checks over the message catalogue and the sources that use it.
///
/// These run without a widget tree because they are about the *resources*:
/// a missing Arabic key, a duplicated key, or a screen that quietly went back
/// to a hardcoded English sentence are all things that would otherwise only
/// show up when somebody switches the app to Arabic and reads every screen.
void main() {
  final enFile = File('lib/l10n/app_en.arb');
  final arFile = File('lib/l10n/app_ar.arb');

  late Map<String, dynamic> en;
  late Map<String, dynamic> ar;

  setUpAll(() {
    en = jsonDecode(enFile.readAsStringSync()) as Map<String, dynamic>;
    ar = jsonDecode(arFile.readAsStringSync()) as Map<String, dynamic>;
  });

  Iterable<String> messageKeys(Map<String, dynamic> arb) =>
      arb.keys.where((key) => !key.startsWith('@'));

  group('message catalogue', () {
    test('both resources exist and declare their locale', () {
      expect(enFile.existsSync(), isTrue);
      expect(arFile.existsSync(), isTrue);
      expect(en['@@locale'], 'en');
      expect(ar['@@locale'], 'ar');
    });

    test('every English key has an Arabic translation', () {
      final missing = messageKeys(en).where((key) => !ar.containsKey(key));
      expect(
        missing,
        isEmpty,
        reason: 'Arabic is missing: ${missing.join(', ')}',
      );
    });

    test('Arabic has no keys English does not', () {
      final extra = messageKeys(ar).where((key) => !en.containsKey(key));
      expect(
        extra,
        isEmpty,
        reason: 'Arabic has orphans: ${extra.join(', ')}',
      );
    });

    test('no translation is empty or whitespace', () {
      for (final arb in [en, ar]) {
        for (final key in messageKeys(arb)) {
          expect(
            '${arb[key]}'.trim(),
            isNotEmpty,
            reason: '$key is blank in ${arb['@@locale']}',
          );
        }
      }
    });

    test('every message carries a description for translators', () {
      for (final key in messageKeys(en)) {
        final meta = en['@$key'];
        expect(meta, isNotNull, reason: '$key has no @$key metadata');
        expect(
          '${(meta as Map)['description'] ?? ''}'.trim(),
          isNotEmpty,
          reason: '$key has no description',
        );
      }
    });

    test('placeholders match between the two languages', () {
      final placeholder = RegExp(r'\{(\w+)\}');
      for (final key in messageKeys(en)) {
        Set<String> names(Object? value) => placeholder
            .allMatches('$value')
            .map((match) => match.group(1)!)
            .toSet();
        expect(
          names(ar[key]),
          names(en[key]),
          // A placeholder dropped in translation renders as a literal
          // "{name}" or throws, so this is worth failing the build over.
          reason: '$key uses different placeholders in Arabic',
        );
      }
    });

    test('a key is never declared twice', () {
      // jsonDecode silently keeps the last duplicate, so the raw text is the
      // only place a duplicate is visible.
      for (final file in [enFile, arFile]) {
        // Exactly two spaces of indent: the top level of the document. The
        // `description`/`placeholders` fields inside an `@key` object are
        // nested deeper and legitimately repeat.
        final declared = RegExp(r'^  "(\w+)"\s*:', multiLine: true)
            .allMatches(file.readAsStringSync())
            .map((match) => match.group(1)!)
            .toList();
        final seen = <String>{};
        final duplicated = declared.where((key) => !seen.add(key)).toList();
        expect(
          duplicated,
          isEmpty,
          reason: '${file.path} declares twice: ${duplicated.join(', ')}',
        );
      }
    });

    test('the generated Dart is in step with the resources', () {
      // If this fails, `flutter gen-l10n` has not been run since the ARB
      // changed and the app would build against a stale catalogue.
      //
      // The identifiers are collected once into a set rather than running a
      // `\bkey\b` regex per key over the whole generated file. That form was
      // 550 scans of a 3,400-line source and took upwards of twenty minutes
      // on its own — most of the suite's runtime, for a check that is a set
      // membership test. A test nobody can afford to run is not a check.
      final generated = File('lib/l10n/app_localizations.dart');
      expect(generated.existsSync(), isTrue);
      final declared = RegExp(r'\b\w+\b')
          .allMatches(generated.readAsStringSync())
          .map((match) => match.group(0)!)
          .toSet();
      final missing = messageKeys(en)
          .where((key) => !declared.contains(key))
          .toList();
      expect(
        missing,
        isEmpty,
        reason: 'Not generated: ${missing.take(5).join(', ')}',
      );
    });
  });

  group('no hardcoded user-facing English', () {
    // Widget constructors whose string argument reaches the screen. This is
    // the list that decides what counts as "user-facing"; a new widget with a
    // visible string parameter belongs here.
    final visible = RegExp(
      r"""(?:Text|SelectableText|Tooltip)\(\s*'([^']{2,})'"""
      r"""|(?:label|labelText|hintText|helperText|title|subtitle|message|"""
      r"""tooltip|semanticsLabel|emptyMessage|actionLabel)\s*:\s*'([^']{2,})'"""
      // A default behind `??` reaches the screen exactly as often as a
      // literal argument does, and this is how `'Retry'` and `'View all'`
      // survived every previous pass: `Text(actionLabel ?? 'Retry')` does
      // not start with `Text('`.
      r"""|\?\?\s*'([^']{2,})'""",
    );

    // Strings that are not prose: identifiers, routes, formats, and the
    // handful of brand and technical tokens that are the same in every
    // language.
    bool isProse(String value) {
      // An interpolated string is project data being formatted, not a
      // sentence the app authored: '${task.code} · ${task.name}' is a task's
      // own identifiers, and translating it would be translating content.
      if (value.contains(r'$')) return false;
      if (RegExp(r'^[a-z0-9_.]+$').hasMatch(value)) return false;
      if (RegExp(r'^[A-Z0-9_]+$').hasMatch(value)) return false;
      if (value.startsWith('/') || value.startsWith('http')) return false;
      if (RegExp(r'^[\W\d\s]+$').hasMatch(value)) return false;
      const allowed = {'Struct', 'IQ', 'Struct IQ', 'name@company.com'};
      if (allowed.contains(value)) return false;
      // Arabic counts as prose too. The rule is "no hardcoded copy", not "no
      // hardcoded English" — the voice clarification card shipped four
      // Arabic literals that this test could not see, so an English session
      // was shown an Arabic heading, label, hint and button.
      if (RegExp(r'[؀-ۿ]{2}').hasMatch(value)) return true;
      // Needs two consecutive letters somewhere to be a word at all.
      return RegExp(r'[A-Za-z]{2}').hasMatch(value);
    }

    test('no widget carries a physical left/right edge assumption', () {
      // Arabic is a first-class locale, so a physical inset or alignment is a
      // layout bug waiting for the language switch: `EdgeInsets.only(right:)`
      // put the gap on the wrong side of every dashboard tile, and a
      // `fromLTRB` header inset let the project name run under the back
      // button. The directional forms mirror on their own.
      final physical = RegExp(
        r'EdgeInsets\.only\(\s*(?:left|right)\s*:'
        r'|Alignment\.(?:centerLeft|centerRight|topLeft|topRight'
        r'|bottomLeft|bottomRight)'
        r'|Positioned\(\s*(?:left|right)\s*:',
      );
      final offenders = <String>[];
      for (final entity in Directory('lib').listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        if (entity.path.replaceAll(r'\', '/').contains('lib/l10n/')) continue;
        final lines = entity.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          if (lines[i].trimLeft().startsWith('//')) continue;
          if (physical.hasMatch(lines[i])) {
            offenders.add('${entity.path}:${i + 1}: ${lines[i].trim()}');
          }
        }
      }
      expect(
        offenders,
        isEmpty,
        reason:
            'These would lay out wrongly in Arabic; use the Directional '
            'form:\n${offenders.join('\n')}',
      );
    });

    test('every visible string in lib/ comes from the catalogue', () {
      final offenders = <String>[];
      for (final entity in Directory('lib').listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        // The generated localizations legitimately contain every English
        // sentence in the app.
        if (entity.path.replaceAll(r'\', '/').contains('lib/l10n/')) continue;

        final lines = entity.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (line.trimLeft().startsWith('//')) continue;
          for (final match in visible.allMatches(line)) {
            final value =
                match.group(1) ?? match.group(2) ?? match.group(3)!;
            if (!isProse(value)) continue;
            offenders.add('${entity.path}:${i + 1}: "$value"');
          }
        }
      }
      expect(
        offenders,
        isEmpty,
        reason:
            'These strings would stay English in an Arabic session:\n'
            '${offenders.join('\n')}',
      );
    });

    test('no widget switches on the locale to pick its own words', () {
      // The rule from the task brief: language conditionals belong in the
      // catalogue, not scattered through widgets.
      final conditional = RegExp(
        r"""languageCode\s*==\s*'(?:ar|en)'\s*\?\s*'""",
      );
      final offenders = <String>[];
      for (final entity in Directory('lib').listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        final lines = entity.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          if (conditional.hasMatch(lines[i])) {
            offenders.add('${entity.path}:${i + 1}');
          }
        }
      }
      expect(offenders, isEmpty, reason: offenders.join('\n'));
    });
  });
}
