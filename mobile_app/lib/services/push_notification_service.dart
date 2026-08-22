import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../core/push/firebase_options.dart';

/// Everything that talks to Firebase Messaging on the device.
///
/// The boundary is deliberate: this class obtains permission and a token,
/// surfaces incoming messages as a stream of payloads, and knows nothing about
/// the API, the session, or where a notification should navigate. Those belong
/// to [PushController], which is where they can reuse the app's existing
/// networking and router instead of growing a second copy of either.
///
/// Everything degrades. An emulator without Play Services, a user who declines
/// the permission prompt, a build with no Firebase configuration — each leaves
/// [isAvailable] false and the rest of the app entirely unaffected, because
/// notifications are also readable in the notification screen.
class PushNotificationService {
  PushNotificationService();

  /// The Android channel notifications are posted to.
  ///
  /// Must match the backend's `PUSH_ANDROID_CHANNEL_ID`. Android 8 and later
  /// silently discard a notification whose channel does not exist on the
  /// device, which fails in the most confusing way possible: FCM reports
  /// success and nothing appears.
  static const androidChannelId = 'structiq_default';

  static const AndroidNotificationChannel _channel = AndroidNotificationChannel(
    androidChannelId,
    'Project notifications',
    description: 'Task assignments, reviews, reports and deadlines.',
    importance: Importance.high,
  );

  final _localNotifications = FlutterLocalNotificationsPlugin();
  final _messageController = StreamController<Map<String, String>>.broadcast();
  final _tapController = StreamController<Map<String, String>>.broadcast();

  FirebaseMessaging? _messaging;
  bool _available = false;

  /// True once Firebase initialized and permission was granted.
  bool get isAvailable => _available;

  /// Payloads arriving while the app is in the foreground.
  Stream<Map<String, String>> get onMessage => _messageController.stream;

  /// Payloads from a notification the user tapped, in any app state.
  Stream<Map<String, String>> get onNotificationTap => _tapController.stream;

  /// Initialize Firebase, ask for permission, and start listening.
  ///
  /// Returns false when push cannot work here, which is a normal outcome and
  /// never an error: the caller carries on and the app behaves as it did
  /// before push existed.
  Future<bool> initialize() async {
    try {
      final options = FirebasePushOptions.currentPlatformOrNull;
      // With no dart-defines, initialize bare so the native SDK reads
      // google-services.json / GoogleService-Info.plist instead.
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp(options: options);
      }
    } catch (error) {
      debugPrint('Push unavailable: Firebase could not initialize ($error)');
      return false;
    }

    final messaging = FirebaseMessaging.instance;
    _messaging = messaging;

    // Android 13+ and every iOS version require an explicit grant. Requested
    // here rather than at launch: this runs after sign-in, and a permission
    // prompt shown before the user knows what the app is gets denied — and a
    // denial cannot be reversed from code, only in system settings.
    final settings = await messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
    final granted =
        settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
    if (!granted) {
      debugPrint('Push unavailable: notification permission was not granted');
      return false;
    }

    await _configureLocalNotifications();

    // iOS shows foreground notifications itself once this is set; Android
    // never does, which is what _showLocalNotification below is for.
    await messaging.setForegroundNotificationPresentationOptions(
      alert: true,
      badge: true,
      sound: true,
    );

    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(
      (message) => _tapController.add(_payloadOf(message)),
    );

    // The app was launched *by* a notification tap from a terminated state.
    // This is the case that is easiest to forget and impossible to notice in
    // testing unless the app is fully closed first.
    final initialMessage = await messaging.getInitialMessage();
    if (initialMessage != null) {
      _tapController.add(_payloadOf(initialMessage));
    }

    _available = true;
    return true;
  }

  Future<void> _configureLocalNotifications() async {
    await _localNotifications.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(
          // Firebase Messaging already requested these; asking twice would
          // show the system prompt a second time.
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
      onDidReceiveNotificationResponse: (response) {
        final payload = response.payload;
        if (payload != null && payload.isNotEmpty) {
          _tapController.add(_decodePayload(payload));
        }
      },
    );

    await _localNotifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(_channel);
  }

  void _handleForegroundMessage(RemoteMessage message) {
    final payload = _payloadOf(message);
    // Let the UI react first — refreshing the notification list matters even
    // if the banner fails to render.
    _messageController.add(payload);
    unawaited(_showLocalNotification(message, payload));
  }

  /// Draw the banner ourselves while the app is open.
  ///
  /// Android deliberately suppresses FCM notifications in the foreground, on
  /// the theory that a visible app should update its own UI. That is right for
  /// a chat screen and wrong for a notification about a different project, so
  /// the banner is posted through the local plugin instead.
  Future<void> _showLocalNotification(
    RemoteMessage message,
    Map<String, String> payload,
  ) async {
    final notification = message.notification;
    final title = notification?.title ?? payload['title'];
    final body = notification?.body ?? payload['body'];
    if (title == null || title.isEmpty) return;

    await _localNotifications.show(
      // A stable id per subject, so a repeated notification about the same
      // thing replaces the previous banner rather than stacking.
      (payload['notificationId'] ?? title).hashCode,
      title,
      body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channel.id,
          _channel.name,
          channelDescription: _channel.description,
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: const DarwinNotificationDetails(),
      ),
      payload: _encodePayload(payload),
    );
  }

  /// The current registration token, or null when push is unavailable.
  Future<String?> currentToken() async {
    if (!_available) return null;
    try {
      return await _messaging?.getToken();
    } catch (error) {
      debugPrint('Could not read the FCM token: $error');
      return null;
    }
  }

  /// Tokens are rotated by FCM without warning; the backend must be told.
  ///
  /// A rotated token fails *silently* — FCM accepts the send and nothing
  /// arrives — so a missed refresh looks exactly like a notification that was
  /// never generated.
  Stream<String> get onTokenRefresh =>
      _messaging?.onTokenRefresh ?? const Stream<String>.empty();

  /// Delete the token on sign-out, so a shared device stops receiving the
  /// previous user's notifications.
  Future<void> deleteToken() async {
    try {
      await _messaging?.deleteToken();
    } catch (error) {
      debugPrint('Could not delete the FCM token: $error');
    }
  }

  Map<String, String> _payloadOf(RemoteMessage message) {
    final payload = <String, String>{
      for (final entry in message.data.entries)
        entry.key: '${entry.value}',
    };
    final notification = message.notification;
    if (notification != null) {
      payload.putIfAbsent('title', () => notification.title ?? '');
      payload.putIfAbsent('body', () => notification.body ?? '');
    }
    return payload;
  }

  // The local-notifications plugin carries a single string, so the payload is
  // flattened. Values are backend-generated ids and short labels; the
  // separators cannot occur in them.
  String _encodePayload(Map<String, String> payload) => payload.entries
      .map((entry) => '${entry.key}=${entry.value}')
      .join('&');

  Map<String, String> _decodePayload(String raw) {
    final result = <String, String>{};
    for (final pair in raw.split('&')) {
      final index = pair.indexOf('=');
      if (index > 0) {
        result[pair.substring(0, index)] = pair.substring(index + 1);
      }
    }
    return result;
  }

  void dispose() {
    _messageController.close();
    _tapController.close();
  }
}
