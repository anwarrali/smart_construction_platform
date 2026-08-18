import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/theme/app_theme.dart';
import '../l10n/app_localizations.dart';
import 'app_router.dart';
import 'locale_controller.dart';

class ConstructionFieldApp extends ConsumerWidget {
  const ConstructionFieldApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    // The product name is the brand in both languages and is not translated.
    title: 'Struct IQ',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light,
    // English and Arabic, the same pair the web ships. `AppL10n` carries the
    // app's own copy; the three Global* delegates cover the Material and
    // Cupertino widgets' built-in strings and the locale's text direction.
    localizationsDelegates: const [
      AppL10n.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: supportedLocales,
    // Null means "resolve from the device", which is what we want by
    // default; a stored preference wins when the user has set one.
    locale: ref.watch(localeControllerProvider).override,
    routerConfig: ref.watch(routerProvider),
  );
}
