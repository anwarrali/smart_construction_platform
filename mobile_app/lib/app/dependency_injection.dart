import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/network/api_client.dart';
import '../core/network/connectivity_service.dart';
import '../core/storage/preferences_service.dart';
import '../core/storage/secure_storage_service.dart';
import '../repositories/auth_repository.dart';
import '../repositories/project_repository.dart';
import '../repositories/message_repository.dart';
import '../repositories/notification_repository.dart';
import '../repositories/task_repository.dart';
import '../repositories/field_submission_repository.dart';
import '../services/auth_service.dart';
import '../services/project_service.dart';
import '../services/message_service.dart';
import '../services/notification_service.dart';
import '../services/task_service.dart';
import '../services/field_submission_service.dart';
import 'app_config.dart';

final configProvider = Provider<AppConfig>((_) => throw UnimplementedError());
final secureStorageProvider = Provider<SecureStorageService>(
  (_) => throw UnimplementedError(),
);
final preferencesProvider = Provider<PreferencesService>(
  (_) => throw UnimplementedError(),
);
final apiClientProvider = Provider<ApiClient>(
  (_) => throw UnimplementedError(),
);
final connectivityProvider = Provider<ConnectivityService>(
  (_) => throw UnimplementedError(),
);
final authRepositoryProvider = Provider<AuthRepository>(
  (_) => throw UnimplementedError(),
);
final projectRepositoryProvider = Provider<ProjectRepository>(
  (_) => throw UnimplementedError(),
);
final taskRepositoryProvider = Provider<TaskRepository>(
  (_) => throw UnimplementedError(),
);
final notificationRepositoryProvider = Provider<NotificationRepository>(
  (_) => throw UnimplementedError(),
);
final messageRepositoryProvider = Provider<MessageRepository>(
  (_) => throw UnimplementedError(),
);
final fieldSubmissionRepositoryProvider = Provider<FieldSubmissionRepository>(
  (_) => throw UnimplementedError(),
);

class AppDependencies {
  const AppDependencies(this.overrides);
  final List<Override> overrides;

  static Future<AppDependencies> create() async {
    final config = AppConfig.fromEnvironment();
    final secure = SecureStorageService(
      const FlutterSecureStorage(
        aOptions: AndroidOptions(encryptedSharedPreferences: true),
      ),
    );
    final preferences = PreferencesService(
      await SharedPreferences.getInstance(),
    );
    final api = ApiClient(config, secure);
    return AppDependencies([
      configProvider.overrideWithValue(config),
      secureStorageProvider.overrideWithValue(secure),
      preferencesProvider.overrideWithValue(preferences),
      apiClientProvider.overrideWithValue(api),
      connectivityProvider.overrideWithValue(
        ConnectivityService(Connectivity()),
      ),
      authRepositoryProvider.overrideWithValue(
        AuthRepositoryImpl(AuthService(api, secure)),
      ),
      projectRepositoryProvider.overrideWithValue(
        ProjectRepository(ProjectService(api)),
      ),
      taskRepositoryProvider.overrideWithValue(
        TaskRepository(TaskService(api)),
      ),
      notificationRepositoryProvider.overrideWithValue(
        NotificationRepository(NotificationService(api)),
      ),
      messageRepositoryProvider.overrideWithValue(
        MessageRepository(MessageService(api)),
      ),
      fieldSubmissionRepositoryProvider.overrideWithValue(
        FieldSubmissionRepository(FieldSubmissionService(api)),
      ),
    ]);
  }
}
