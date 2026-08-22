import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/app.dart';
import 'app/dependency_injection.dart';
import 'core/push/background_handler.dart';
import 'core/push/firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Firebase and the background handler are registered here, before the app
  // starts, because both must exist before any message can arrive — a push
  // that lands while the app is terminated has no other opportunity to be
  // handled. Wrapped in try/catch so a build with no Firebase configuration
  // still launches: push is an enhancement, and every notification remains
  // readable in the notification screen without it.
  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: FirebasePushOptions.currentPlatformOrNull,
      );
    }
    FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  } catch (error) {
    debugPrint('Push notifications unavailable: $error');
  }

  final dependencies = await AppDependencies.create();
  runApp(
    ProviderScope(
      overrides: dependencies.overrides,
      child: const ConstructionFieldApp(),
    ),
  );
}
