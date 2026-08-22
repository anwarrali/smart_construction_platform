import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'firebase_options.dart';

/// Handles a push that arrives while the app is backgrounded or terminated.
///
/// This runs in a **separate isolate** with none of the app's state: no
/// providers, no router, no session, no `ApiClient`. That is why it does
/// almost nothing. Anything it tried to touch in the running app would not
/// exist, and network calls from here are unreliable because the isolate can
/// be killed the moment it returns.
///
/// The notification itself still appears: the backend sends a `notification`
/// block, so Android and iOS render it from the system tray without any Dart
/// code running at all. This handler exists so that a *data-only* message does
/// not crash the isolate, and so Firebase is initialized if one arrives.
///
/// It must be a top-level function annotated `@pragma('vm:entry-point')`, or
/// tree-shaking removes it from release builds and background messages fail
/// only in production — the worst possible place to discover it.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: FirebasePushOptions.currentPlatformOrNull,
      );
    }
  } catch (error) {
    debugPrint('Background push: Firebase could not initialize ($error)');
    return;
  }
  debugPrint('Background push received: ${message.messageId}');
}
