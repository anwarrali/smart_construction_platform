import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../models/user.dart';
import '../network/network_exceptions.dart';

enum SessionStatus { checking, authenticating, authenticated, unauthenticated }

class SessionState {
  const SessionState({required this.status, this.user, this.error});
  final SessionStatus status;
  final User? user;
  /// The failure that ended the last sign-in attempt, kept as the exception
  /// rather than a rendered sentence so the screen can translate it.
  final Object? error;
}

final sessionProvider = StateNotifierProvider<SessionManager, SessionState>((
  ref,
) {
  return SessionManager(ref.read(authRepositoryProvider))..restore();
});

class SessionManager extends StateNotifier<SessionState> {
  SessionManager(this._repository)
    : super(const SessionState(status: SessionStatus.checking));
  final dynamic _repository;

  Future<void> restore() async {
    state = const SessionState(status: SessionStatus.checking);
    try {
      final user = await _repository.restoreSession() as User?;
      state = SessionState(
        status: user == null
            ? SessionStatus.unauthenticated
            : SessionStatus.authenticated,
        user: user,
      );
    } catch (_) {
      state = const SessionState(status: SessionStatus.unauthenticated);
    }
  }

  Future<bool> login(String identity, String password) async {
    state = const SessionState(status: SessionStatus.authenticating);
    try {
      final user = await _repository.login(identity, password) as User;
      state = SessionState(status: SessionStatus.authenticated, user: user);
      return true;
    } on NetworkException catch (error) {
      state = SessionState(
        status: SessionStatus.unauthenticated,
        error: error,
      );
      return false;
    }
  }

  Future<void> logout() async {
    try {
      await _repository.logout();
    } finally {
      // Logging out locally must not depend on the server being reachable.
      // This also lets the router leave authenticated screens immediately.
      state = const SessionState(status: SessionStatus.unauthenticated);
    }
  }
}
