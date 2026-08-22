import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// Firebase configuration, supplied at build time rather than checked in.
///
/// The usual `flutterfire configure` writes a generated `firebase_options.dart`
/// containing a specific project's identifiers. That file is fine to commit —
/// these are public client identifiers, not credentials — but it hardcodes one
/// Firebase project, so a staging build cannot point anywhere else without
/// editing source. This reads the same values from `--dart-define` instead.
///
/// **Both configuration paths work, and neither requires editing this file.**
///
///  * Supply `--dart-define=FIREBASE_*` values and these options are used.
///  * Supply none, and [currentPlatformOrNull] returns null — the caller then
///    initializes Firebase bare, which makes the native SDK read
///    `android/app/google-services.json` or `ios/Runner/GoogleService-Info.plist`.
///    That is the path most Firebase documentation describes, and both files
///    are git-ignored.
///
/// If neither is configured, push is simply unavailable and the app runs
/// normally — notifications still arrive in the notification screen.
abstract final class FirebasePushOptions {
  static const _apiKey = String.fromEnvironment('FIREBASE_API_KEY');
  static const _appIdAndroid = String.fromEnvironment('FIREBASE_APP_ID_ANDROID');
  static const _appIdIos = String.fromEnvironment('FIREBASE_APP_ID_IOS');
  static const _messagingSenderId = String.fromEnvironment(
    'FIREBASE_MESSAGING_SENDER_ID',
  );
  static const _projectId = String.fromEnvironment('FIREBASE_PROJECT_ID');
  static const _storageBucket = String.fromEnvironment('FIREBASE_STORAGE_BUCKET');
  static const _iosBundleId = String.fromEnvironment('FIREBASE_IOS_BUNDLE_ID');

  /// Options for this platform, or null to fall back to the native config file.
  static FirebaseOptions? get currentPlatformOrNull {
    if (_apiKey.isEmpty || _projectId.isEmpty || _messagingSenderId.isEmpty) {
      return null;
    }
    final appId = switch (defaultTargetPlatform) {
      TargetPlatform.android => _appIdAndroid,
      TargetPlatform.iOS => _appIdIos,
      // Only Android and iOS are shipped for this app; the web build of the
      // platform is the React application, which has its own Firebase setup.
      _ => '',
    };
    if (appId.isEmpty) return null;

    return FirebaseOptions(
      apiKey: _apiKey,
      appId: appId,
      messagingSenderId: _messagingSenderId,
      projectId: _projectId,
      storageBucket: _storageBucket.isEmpty ? null : _storageBucket,
      iosBundleId: _iosBundleId.isEmpty ? null : _iosBundleId,
    );
  }
}
