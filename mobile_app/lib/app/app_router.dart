import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../core/auth/session_manager.dart';
import '../core/widgets/mobile_shell.dart';
import '../features/authentication/login_screen.dart';
import '../features/contact_admin/contact_admin_screen.dart';
import '../features/dashboard/role_dashboard_screen.dart';
import '../features/messages/conversation_screen.dart';
import '../features/messages/messages_screen.dart';
import '../features/issues/create_issue_screen.dart';
import '../features/notifications/notification_detail_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/projects/project_context_view_model.dart';
import '../features/projects/projects_screen.dart';
import '../features/reviews/consultant_review_detail_screen.dart';
import '../features/reviews/consultant_reviews_screen.dart';
import '../features/shared/remote_collection_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/site_reports/create_site_report_screen.dart';
import '../features/tasks/task_detail_screen.dart';
import '../features/tasks/tasks_screen.dart';
import '../features/voice_command/voice_screen.dart';
import '../features/voice_command/ai_diagnostics_screen.dart';
import '../features/field_evidence/worker_field_submission_screen.dart';
import '../features/field_evidence/worker_submissions_screen.dart';
import '../features/ifc/ifc_models_screen.dart';
import '../features/collaboration/collaboration_screen.dart';
import '../core/constants/api_endpoints.dart';
import '../models/notification_item.dart';
import '../models/chat_message.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = _RouterRefresh(ref);
  ref.onDispose(notifier.dispose);
  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: notifier,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      final location = state.matchedLocation;
      if (session.status == SessionStatus.checking) {
        return location == '/splash' ? null : '/splash';
      }
      if (session.status == SessionStatus.authenticating) {
        return location == '/login' ? null : '/login';
      }
      if (session.status == SessionStatus.unauthenticated) {
        return location == '/login' || location == '/contact-admin'
            ? null
            : '/login';
      }
      if (location == '/login' || location == '/splash') {
        final projects = ref.read(projectContextProvider);
        if (projects.projects.isEmpty && !projects.loading) return '/projects';
        return projects.selected == null ? '/projects' : '/home';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(
        path: '/contact-admin',
        builder: (_, __) => const ContactAdminScreen(),
      ),
      GoRoute(path: '/projects', builder: (_, __) => const ProjectsScreen()),
      ShellRoute(
        builder: (context, state, child) {
          final user = ref.read(sessionProvider).user;
          final destinations = user?.isConsultant == true
              ? const [
                  NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    label: 'Home',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.rate_review_outlined),
                    label: 'Reviews',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.folder_outlined),
                    label: 'Documents',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.message_outlined),
                    label: 'Messages',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    label: 'Profile',
                  ),
                ]
              : user?.isWorker == true
              ? const [
                  NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    label: 'Home',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.task_outlined),
                    label: 'My Tasks',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.photo_camera_back_outlined),
                    label: 'Evidence',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.message_outlined),
                    label: 'Messages',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    label: 'Profile',
                  ),
                ]
              : user?.isOwner == true
              ? const [
                  NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    label: 'Home',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.description_outlined),
                    label: 'Reports',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.apartment),
                    label: 'Projects',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.message_outlined),
                    label: 'Messages',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    label: 'Profile',
                  ),
                ]
              : user?.isProjectManager == true
              ? const [
                  NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    label: 'Home',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.task_outlined),
                    label: 'Tasks',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.report_problem_outlined),
                    label: 'Issues',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.message_outlined),
                    label: 'Messages',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    label: 'Profile',
                  ),
                ]
              : const [
                  NavigationDestination(
                    icon: Icon(Icons.home_outlined),
                    selectedIcon: Icon(Icons.home_rounded),
                    label: 'Home',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.task_outlined),
                    selectedIcon: Icon(Icons.task_rounded),
                    label: 'My Tasks',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.description_outlined),
                    selectedIcon: Icon(Icons.description_rounded),
                    label: 'Reports',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.message_outlined),
                    selectedIcon: Icon(Icons.message_rounded),
                    label: 'Messages',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.person_outline),
                    selectedIcon: Icon(Icons.person_rounded),
                    label: 'Profile',
                  ),
                ];
          return MobileShell(
            location: state.uri.path,
            destinations: destinations,
            showRecordAction:
                user?.isSiteEngineer == true || user?.isWorker == true,
            child: child,
          );
        },
        routes: [
          GoRoute(
            path: '/home',
            builder: (_, __) => const RoleDashboardScreen(),
          ),
          GoRoute(path: '/tasks', builder: (_, __) => const TasksScreen()),
          GoRoute(
            path: '/reports',
            builder: (_, __) {
              final user = ref.read(sessionProvider).user;
              return _projectCollection(
                ref,
                'Site Reports',
                ApiEndpoints.siteReports,
                'No site reports have been submitted.',
                Icons.description_outlined,
                createRoute:
                    user?.isSiteEngineer == true ||
                        user?.isProjectManager == true
                    ? '/reports/new'
                    : null,
              );
            },
          ),
          GoRoute(
            path: '/reviews',
            builder: (_, __) => const ConsultantReviewsScreen(),
          ),
          GoRoute(
            path: '/reviews/:id',
            builder: (_, state) => ConsultantReviewDetailScreen(
              reviewId: state.pathParameters['id']!,
            ),
          ),
          GoRoute(
            path: '/issues',
            builder: (_, __) {
              final user = ref.read(sessionProvider).user;
              return _projectCollection(
                ref,
                'Issues & Blockers',
                ApiEndpoints.issues,
                'No issues have been reported.',
                Icons.report_problem_outlined,
                createRoute:
                    user?.role == 'engineer' || user?.isProjectManager == true
                    ? '/issues/new'
                    : null,
              );
            },
          ),
          GoRoute(
            path: '/documents',
            builder: (_, __) => _projectCollection(
              ref,
              'Documents',
              (id) => '/documents/project/$id',
              'No documents are available.',
              Icons.folder_outlined,
            ),
          ),
          GoRoute(
            path: '/messages',
            builder: (_, __) => const MessagesScreen(),
          ),
          GoRoute(path: '/actions', builder: (_, __) => const CollaborationScreen()),
          GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
          GoRoute(
            path: '/evidence',
            builder: (_, __) => const WorkerSubmissionsScreen(),
          ),
          GoRoute(path: '/ifc', builder: (_, __) => const IfcModelsScreen()),
        ],
      ),
      GoRoute(
        path: '/tasks/:id',
        builder: (_, state) =>
            TaskDetailScreen(taskId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/tasks/:id/evidence/new',
        builder: (_, state) => WorkerFieldSubmissionScreen(
          taskId: state.pathParameters['id']!,
          resubmissionOfId: state.uri.queryParameters['resubmission'],
        ),
      ),
      GoRoute(
        path: '/tasks/:id/discussion',
        builder: (_, state) => ConversationScreen(
          contextType: 'TASK',
          contextId: state.pathParameters['id']!,
        ),
      ),
      GoRoute(
        path: '/voice',
        builder: (_, state) =>
            VoiceScreen(taskId: state.uri.queryParameters['taskId']),
      ),
      GoRoute(
        path: '/dev/ai-diagnostics',
        builder: (_, __) => const AiDiagnosticsScreen(),
      ),
      GoRoute(
        path: '/issues/new',
        builder: (_, __) => const CreateIssueScreen(),
      ),
      GoRoute(
        path: '/reports/new',
        builder: (_, __) => const CreateSiteReportScreen(),
      ),
      GoRoute(
        path: '/notifications',
        builder: (_, __) => const NotificationsScreen(),
      ),
      GoRoute(
        path: '/notifications/:id',
        builder: (_, state) => NotificationDetailScreen(
          notification: state.extra is NotificationItem
              ? state.extra! as NotificationItem
              : null,
        ),
      ),
      GoRoute(
        path: '/messages/:conversationId',
        builder: (_, state) => ConversationScreen(
          conversationId: state.pathParameters['conversationId']!,
          conversation: state.extra is ProjectConversation
              ? state.extra! as ProjectConversation
              : null,
        ),
      ),
    ],
  );
});

Widget _projectCollection(
  Ref ref,
  String title,
  String Function(String) path,
  String empty,
  IconData icon, {
  String? createRoute,
}) {
  final project = ref.read(projectContextProvider).selected;
  return project == null
      ? const Scaffold(body: Center(child: Text('Select a project first.')))
      : RemoteCollectionScreen(
          title: title,
          path: path(project.id),
          emptyMessage: empty,
          icon: icon,
          createRoute: createRoute,
        );
}

class _RouterRefresh extends ChangeNotifier {
  _RouterRefresh(this.ref) {
    _session = ref.listen(sessionProvider, (_, __) => _requestRefresh());
    _project = ref.listen(projectContextProvider, (_, __) => _requestRefresh());
  }
  final Ref ref;
  late final ProviderSubscription _session;
  late final ProviderSubscription _project;
  bool _refreshPending = false;
  bool _disposed = false;

  void _requestRefresh() {
    if (_disposed || _refreshPending) return;

    if (SchedulerBinding.instance.schedulerPhase == SchedulerPhase.idle) {
      notifyListeners();
      return;
    }

    _refreshPending = true;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _refreshPending = false;
      if (!_disposed) notifyListeners();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _session.close();
    _project.close();
    super.dispose();
  }
}
