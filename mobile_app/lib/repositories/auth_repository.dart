import '../models/user.dart';
import '../services/auth_service.dart';

abstract interface class AuthRepository {
  Future<User> login(String identity, String password);
  Future<User?> restoreSession();
  Future<void> logout();
}

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(this._service);
  final AuthService _service;
  @override
  Future<User> login(String identity, String password) =>
      _service.login(identity, password);
  @override
  Future<User?> restoreSession() async =>
      await _service.hasToken ? _service.currentUser() : null;
  @override
  Future<void> logout() => _service.logout();
}
