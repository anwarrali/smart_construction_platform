import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/storage/preferences_service.dart';
import 'dependency_injection.dart';

/// The languages the app ships. Adding one here and an `app_<code>.arb`
/// beside the others is the whole change — nothing else enumerates locales.
const supportedLocales = <Locale>[Locale('en'), Locale('ar')];

/// The active language, and whether the user chose it.
///
/// A null [override] means "follow the device", which is the default: a phone
/// set to Arabic gets an Arabic app on first launch. The override exists
/// because the web has a language switch too, and a bilingual site team
/// routinely wants the app in the other language from the phone.
class LocaleState {
  const LocaleState({this.override});

  final Locale? override;

  bool get followsDevice => override == null;
}

/// A build-time language override, for verifying the app in a language the
/// device cannot be set to.
///
/// Every task requires the app to be checked in both English and Arabic on a
/// real device, and a production Android image will not let `adb` change the
/// system locale — so the only ways to see the Arabic layout were to sign in
/// first and use the in-app switch, or to hand-edit `app.dart` before each
/// build. Neither is a check anyone runs twice, which is how an Arabic-only
/// overflow reaches a release.
///
/// Empty unless somebody passes it, so a shipped build behaves exactly as
/// before: the device decides, and the user's own preference wins over that.
const _localeOverride = String.fromEnvironment('APP_LOCALE');

class LocaleController extends StateNotifier<LocaleState> {
  LocaleController(this._preferences)
    : super(LocaleState(override: _read(_preferences)));

  final PreferencesService _preferences;

  static Locale? _read(PreferencesService preferences) {
    final code = _localeOverride.isNotEmpty
        ? _localeOverride
        : preferences.localeCode;
    if (code == null || code.isEmpty) return null;
    // A stored code that is no longer supported resolves to "follow the
    // device" rather than to a locale with no translations.
    return supportedLocales.firstWhere(
      (locale) => locale.languageCode == code,
      orElse: () => const Locale('en'),
    );
  }

  Future<void> select(Locale? locale) async {
    await _preferences.setLocaleCode(locale?.languageCode);
    state = LocaleState(override: locale);
  }
}

final localeControllerProvider =
    StateNotifierProvider<LocaleController, LocaleState>(
      (ref) => LocaleController(ref.watch(preferencesProvider)),
    );
