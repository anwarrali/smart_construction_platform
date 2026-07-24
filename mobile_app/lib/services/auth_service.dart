import '../core/constants/api_endpoints.dart';
import '../core/network/api_client.dart';
import '../core/storage/secure_storage_service.dart';
import '../models/user.dart';

class AuthService {
  AuthService(this._api, this._storage);
  final ApiClient _api;
  final SecureStorageService _storage;

  Future<User> login(String identity, String password) async {
    final data = await _api.postForm<Map<String, dynamic>>(ApiEndpoints.login, {
      'username': identity.trim(),
      'password': password,
    });
    await _storage.saveTokens(
      data['access_token'] as String,
      data['refresh_token'] as String,
    );
    return currentUser();
  }

  Future<User> currentUser() async =>
      User.fromJson(await _api.get<Map<String, dynamic>>(ApiEndpoints.me));
  Future<bool> get hasToken async => await _storage.accessToken != null;

  Future<void> logout() async {
    try {
      await _api.post<Object?>(ApiEndpoints.logout);
    } finally {
      await _storage.clearTokens();
    }
  }
}
