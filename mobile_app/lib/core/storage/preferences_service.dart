import 'package:shared_preferences/shared_preferences.dart';
import '../constants/storage_keys.dart';

class PreferencesService {
  PreferencesService(this._preferences);
  final SharedPreferences _preferences;

  String? get selectedProjectId =>
      _preferences.getString(StorageKeys.selectedProject);
  Future<void> selectProject(String id) =>
      _preferences.setString(StorageKeys.selectedProject, id);
  Future<void> clearProject() =>
      _preferences.remove(StorageKeys.selectedProject);

  /// The stored language override, or null when the app should follow the
  /// device. Null is the default so a phone set to Arabic gets an Arabic app
  /// on first launch without the user configuring anything.
  String? get localeCode => _preferences.getString(StorageKeys.locale);

  Future<void> setLocaleCode(String? code) => code == null
      ? _preferences.remove(StorageKeys.locale)
      : _preferences.setString(StorageKeys.locale, code);
}
