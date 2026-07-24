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
}
