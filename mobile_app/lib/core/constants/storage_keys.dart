abstract final class StorageKeys {
  static const accessToken = 'mobile_access_token';
  static const refreshToken = 'mobile_refresh_token';
  static const selectedProject = 'selected_project_id';

  /// The user's explicit language choice: 'en', 'ar', or absent for
  /// "follow the device".
  static const locale = 'app_locale';

  /// A stable per-installation identifier for push registration.
  ///
  /// It lets the backend retire this installation's previous FCM token when
  /// one is rotated, instead of leaving a dead row behind on every refresh.
  /// Generated locally and containing nothing about the user.
  static const pushDeviceId = 'push_device_id';
}
