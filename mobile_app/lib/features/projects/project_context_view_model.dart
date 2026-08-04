import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../models/project.dart';

class ProjectContextState {
  const ProjectContextState({
    this.projects = const [],
    this.selected,
    this.loading = true,
    this.error,
  });
  final List<Project> projects;
  final Project? selected;
  final bool loading;
  final String? error;
}

final projectContextProvider =
    StateNotifierProvider<ProjectContextViewModel, ProjectContextState>((ref) {
      return ProjectContextViewModel(
        ref.read(projectRepositoryProvider),
        ref.read(preferencesProvider),
      );
    });

class ProjectContextViewModel extends StateNotifier<ProjectContextState> {
  ProjectContextViewModel(this._repository, this._preferences)
    : super(const ProjectContextState());
  final dynamic _repository;
  final dynamic _preferences;

  Future<void> load() async {
    state = const ProjectContextState(loading: true);
    try {
      final projects = await _repository.listAssigned() as List<Project>;
      final remembered = _preferences.selectedProjectId as String?;
      Project? selected;
      for (final project in projects) {
        if (project.id == remembered ||
            (remembered == null && projects.length == 1)) {
          selected = project;
        }
      }
      state = ProjectContextState(
        projects: projects,
        selected: selected,
        loading: false,
      );
    } catch (error) {
      state = ProjectContextState(loading: false, error: '$error');
    }
  }

  Future<void> select(Project project) async {
    await _preferences.selectProject(project.id);
    state = ProjectContextState(
      projects: state.projects,
      selected: project,
      loading: false,
    );
  }

  void clear() => state = const ProjectContextState();

  Future<void> clearForLogout() async {
    await _preferences.clearProject();
    state = const ProjectContextState();
  }
}
