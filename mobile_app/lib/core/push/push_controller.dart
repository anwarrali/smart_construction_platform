import 'dart:async';
import 'dart:io' show Platform;
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../app/app_router.dart';
import '../../repositories/notification_repository.dart';
import '../../services/push_notification_service.dart';
import '../auth/session_manager.dart';
import '../storage/preferences_service.dart';

/// Connects device push to the rest of the app.
///
/// Everything here is glue, on purpose. Registration uses the existing
/// [NotificationRepository] and therefore the existing authenticated
/// [ApiClient]; navigation uses the existing `go_router`. There is no second
/// networking stack, no second auth handling, and no second notion of what a
/// notification means — the server decides all of that.
///
/// The lifecycle it owns is small but easy to get wrong:
///
///   sign in   -> ask permission, get token, register it with the backend
///   token
///   rotates   -> re-register (a rotated token fails *silently* otherwise)
///   sign out  -> unregister server-side, then delete the token locally
///
/// The sign-out order matters: unregistering needs a valid access token, and
/// after the session ends there is none.
/// This app's route for a backend entity reference, or null if it has none.
///
/// Top-level and public so it can be tested without a Firebase instance, a
/// router or a session — the mapping from "what the notification is about" to
/// "which screen" is the part most likely to drift as screens are added, and
/// it is pure.
///
/// Only entities the mobile app actually has a screen for appear here.
/// Anything else returns null and the caller falls back to the notification
/// detail screen, rather than pushing a route that would render an error.
String? routeForEntity(String? entityType, String? entityId) {
  if (entityType == null || entityId == null || entityId.isEmpty) return null;
  return switch (entityType.toUpperCase()) {
    'TASK' => '/tasks/$entityId',
    'ISSUE' => '/issues',
    'SITE_REPORT' => '/reports',
    'DESIGN_CHANGE' => '/design-changes',
    'FIELD_SUBMISSION' => '/evidence',
    'OWNER_REQUEST' || 'SITE_VISIT' => '/actions',
    _ => null,
  };
}

class PushController {
  PushController(this._ref, this._service, this._repository, this._preferences);

  final Ref _ref;
  final PushNotificationService _service;
  final NotificationRepository _repository;
  final PreferencesService _preferences;

  final _subscriptions = <StreamSubscription<Object?>>[];
  bool _started = false;
  String? _registeredToken;

  /// Fires when a push arrives in the foreground, so an open notification
  /// list can refresh itself.
  final _foregroundNotifier = ValueNotifier<int>(0);
  ValueListenable<int> get foregroundMessages => _foregroundNotifier;

  /// Begin push for the signed-in user. Safe to call more than once.
  Future<void> start() async {
    if (_started) return;
    _started = true;

    final available = await _service.initialize();
    if (!available) {
      // A perfectly normal outcome: no Play Services, permission declined, or
      // no Firebase configuration in this build. Notifications remain readable
      // in the notification screen, so nothing is broken and nothing is said.
      _started = false;
      return;
    }

    final token = await _service.currentToken();
    if (token != null) await _registerToken(token);

    _subscriptions.add(
      _service.onTokenRefresh.listen((refreshed) {
        unawaited(_registerToken(refreshed));
      }),
    );
    _subscriptions.add(
      _service.onMessage.listen((_) => _foregroundNotifier.value++),
    );
    _subscriptions.add(_service.onNotificationTap.listen(_openNotification));
  }

  /// Retire this device. Called before the session ends.
  Future<void> stop() async {
    for (final subscription in _subscriptions) {
      await subscription.cancel();
    }
    _subscriptions.clear();

    final deviceId = _preferences.pushDeviceId;
    if (_registeredToken != null || deviceId != null) {
      try {
        await _repository.unregisterDevice(
          token: _registeredToken,
          deviceId: deviceId,
        );
      } catch (error) {
        // The server may already have retired it, or the phone may be on a
        // site with no signal. Signing out must not depend on the network.
        debugPrint('Could not unregister the push device: $error');
      }
    }
    await _service.deleteToken();
    _registeredToken = null;
    _started = false;
  }

  Future<void> _registerToken(String token) async {
    if (token == _registeredToken) return;
    try {
      await _repository.registerDevice(
        token: token,
        platform: Platform.isIOS ? 'ios' : 'android',
        deviceId: await _deviceId(),
        deviceName: _deviceName(),
      );
      _registeredToken = token;
    } catch (error) {
      // Leave `_registeredToken` unset so the next refresh or app start tries
      // again. Failing to register costs push, never the app.
      debugPrint('Could not register this device for push: $error');
    }
  }

  /// A stable identifier for this installation, created once and kept.
  ///
  /// It is what lets the backend retire this phone's *previous* token when FCM
  /// rotates one, instead of accumulating dead rows. Generated locally and
  /// containing nothing about the user or the hardware.
  Future<String> _deviceId() async {
    final existing = _preferences.pushDeviceId;
    if (existing != null && existing.isNotEmpty) return existing;
    final random = Random.secure();
    final id = List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
    await _preferences.setPushDeviceId(id);
    return id;
  }

  String _deviceName() => Platform.isIOS ? 'iOS device' : 'Android device';

  /// Open the screen a tapped notification is about.
  ///
  /// The payload names the subject; the destination is this app's own route
  /// for it. The server deliberately does not send a path — the web app's
  /// routes are role-prefixed and the mobile app's are not, so a server-chosen
  /// URL could only be wrong for one of them.
  Future<void> _openNotification(Map<String, String> payload) async {
    final router = _ref.read(routerProvider);

    final entityType = payload['entityType'];
    final entityId = payload['entityId'] ?? payload['taskId'];
    final notificationId = payload['notificationId'];

    final direct = routeForEntity(entityType, entityId);
    if (direct != null) {
      router.push(direct);
      return;
    }

    // No usable subject in the payload — fall back to the notification itself,
    // which is always a truthful destination. Fetching it also lets a
    // data-only push (one with no entity fields) still land somewhere useful.
    if (notificationId == null) {
      router.push('/notifications');
      return;
    }
    try {
      final notification = await _repository.byId(notificationId);
      final resolved = routeForEntity(
        notification.relatedEntityType,
        notification.relatedEntityId ?? notification.taskId,
      );
      router.push(resolved ?? '/notifications/$notificationId', extra: notification);
    } catch (error) {
      debugPrint('Could not resolve the tapped notification: $error');
      router.push('/notifications');
    }
  }

  void dispose() {
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    _foregroundNotifier.dispose();
    _service.dispose();
  }
}

final pushServiceProvider = Provider<PushNotificationService>((ref) {
  final service = PushNotificationService();
  ref.onDispose(service.dispose);
  return service;
});

final pushControllerProvider = Provider<PushController>((ref) {
  final controller = PushController(
    ref,
    ref.read(pushServiceProvider),
    ref.read(notificationRepositoryProvider),
    ref.read(preferencesProvider),
  );
  ref.onDispose(controller.dispose);
  return controller;
});

/// Starts and stops push in step with the session.
///
/// Watched once, from the app shell. Push must not begin before sign-in: the
/// registration call needs an access token, and an unauthenticated permission
/// prompt is the fastest route to a permanent denial.
final pushLifecycleProvider = Provider<void>((ref) {
  final status = ref.watch(sessionProvider.select((state) => state.status));
  final controller = ref.read(pushControllerProvider);
  if (status == SessionStatus.authenticated) {
    unawaited(controller.start());
  }
  return;
});
