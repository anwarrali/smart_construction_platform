import 'package:construction_field/core/auth/session_manager.dart';
import 'package:construction_field/features/projects/project_context_view_model.dart';
import 'package:construction_field/features/projects/projects_screen.dart';
import 'package:construction_field/models/project.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _ProjectRepository {
  Future<List<Project>> listAssigned() async => <Project>[];
}

class _Preferences {
  String? selectedProjectId = 'previous-account-project';
  bool cleared = false;

  Future<void> selectProject(String id) async {
    selectedProjectId = id;
  }

  Future<void> clearProject() async {
    selectedProjectId = null;
    cleared = true;
  }
}

class _AuthRepository {
  bool loggedOut = false;

  Future<void> logout() async {
    loggedOut = true;
  }
}

void main() {
  testWidgets(
    'empty project account can switch account without Android back exiting',
    (tester) async {
      final preferences = _Preferences();
      final authRepository = _AuthRepository();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            projectContextProvider.overrideWith(
              (ref) =>
                  ProjectContextViewModel(_ProjectRepository(), preferences),
            ),
            sessionProvider.overrideWith(
              (ref) => SessionManager(authRepository),
            ),
          ],
          child: const MaterialApp(home: ProjectsScreen()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No projects assigned'), findsOneWidget);
      expect(find.text('Switch account'), findsNWidgets(2));

      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();

      expect(find.text('Switch account?'), findsOneWidget);
      expect(find.text('Sign out'), findsOneWidget);
      expect(authRepository.loggedOut, isFalse);

      await tester.tap(find.text('Sign out'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(authRepository.loggedOut, isTrue);
      expect(preferences.cleared, isTrue);
      expect(preferences.selectedProjectId, isNull);
    },
  );
}
