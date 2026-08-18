import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../core/auth/session_manager.dart';
import '../core/auth/voice_access.dart';
import '../core/l10n/l10n_labels.dart';
import '../core/widgets/async_views.dart';
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
import '../models/user.dart';

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
          return MobileShell(
            location: state.uri.path,
            destinations: _destinationsFor(user),
            // Voice is for every normal system user, not for two field roles
            // — see `canUseVoice`.
            showVoiceAction: canUseVoice(user),
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
            builder: (context, __) {
              final user = ref.read(sessionProvider).user;
              return _projectCollection(
                ref,
                context,
                context.l10n.siteReportsTitle,
                ApiEndpoints.siteReports,
                context.l10n.siteReportsEmpty,
                Icons.description_outlined,
                entityType: 'SITE_REPORT',
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
            builder: (context, __) {
              final user = ref.read(sessionProvider).user;
              return _projectCollection(
                ref,
                context,
                context.l10n.issuesTitle,
                ApiEndpoints.issues,
                context.l10n.issuesEmpty,
                Icons.report_problem_outlined,
                entityType: 'ISSUE',
                createRoute:
                    user?.role == 'engineer' || user?.isProjectManager == true
                    ? '/issues/new'
                    : null,
              );
            },
          ),
          GoRoute(
            path: '/design-changes',
            builder: (context, __) => _projectCollection(
              ref,
              context,
              context.l10n.navDesignChanges,
              (id) => '/design-changes/project/$id',
              context.l10n.designChangesEmpty,
              Icons.architecture_rounded,
              entityType: 'DESIGN_CHANGE',
            ),
          ),
          GoRoute(
            path: '/documents',
            builder: (context, __) => _projectCollection(
              ref,
              context,
              context.l10n.documentsTitle,
              (id) => '/documents/project/$id',
              context.l10n.documentsEmpty,
              Icons.folder_outlined,
              entityType: 'DOCUMENT',
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

/// The bottom-navigation destinations for a role.
///
/// Presentation only. Every destination leads to a screen that fetches from
/// an authorized endpoint, so a role that should not see a section is stopped
/// by the backend, not by its absence from this list.
///
/// **Four destinations, not five.** The fifth slot is the raised voice action
/// in the middle of the bar, and Profile — which nobody opens while standing
/// on a slab — moved to the dashboard header. What is left is the question
/// "what does this person do on site all day", answered per role:
/// their work, their exceptions, and the people they need to reach.
List<ShellDestination> _destinationsFor(User? user) {
  ShellDestination home() => ShellDestination(
    path: '/home',
    icon: Icons.home_outlined,
    selectedIcon: Icons.home_rounded,
    label: (context) => context.l10n.navHome,
  );
  ShellDestination messages() => ShellDestination(
    path: '/messages',
    icon: Icons.forum_outlined,
    selectedIcon: Icons.forum_rounded,
    label: (context) => context.l10n.navMessages,
  );

  if (user?.isConsultant == true) {
    return [
      home(),
      ShellDestination(
        path: '/reviews',
        icon: Icons.fact_check_outlined,
        selectedIcon: Icons.fact_check_rounded,
        label: (context) => context.l10n.navReviews,
      ),
      ShellDestination(
        path: '/documents',
        icon: Icons.folder_outlined,
        selectedIcon: Icons.folder_rounded,
        label: (context) => context.l10n.navDocuments,
      ),
      messages(),
    ];
  }
  if (user?.isWorker == true) {
    return [
      home(),
      ShellDestination(
        path: '/tasks',
        icon: Icons.task_outlined,
        selectedIcon: Icons.task_rounded,
        label: (context) => context.l10n.navMyTasks,
      ),
      ShellDestination(
        path: '/evidence',
        icon: Icons.photo_camera_back_outlined,
        selectedIcon: Icons.photo_camera_back_rounded,
        label: (context) => context.l10n.navEvidence,
      ),
      messages(),
    ];
  }
  if (user?.isOwner == true) {
    return [
      home(),
      ShellDestination(
        path: '/reports',
        icon: Icons.description_outlined,
        selectedIcon: Icons.description_rounded,
        label: (context) => context.l10n.navReports,
      ),
      // Not '/projects': that route lives outside the shell, so making it a
      // destination dropped the user out of the navigation entirely.
      ShellDestination(
        path: '/actions',
        icon: Icons.checklist_outlined,
        selectedIcon: Icons.checklist_rounded,
        label: (context) => context.l10n.navMyActions,
      ),
      messages(),
    ];
  }
  if (user?.isProjectManager == true) {
    return [
      home(),
      ShellDestination(
        path: '/tasks',
        icon: Icons.task_outlined,
        selectedIcon: Icons.task_rounded,
        label: (context) => context.l10n.navTasks,
      ),
      ShellDestination(
        path: '/issues',
        icon: Icons.report_problem_outlined,
        selectedIcon: Icons.report_problem_rounded,
        label: (context) => context.l10n.navIssues,
      ),
      messages(),
    ];
  }
  return [
    home(),
    ShellDestination(
      path: '/tasks',
      icon: Icons.task_outlined,
      selectedIcon: Icons.task_rounded,
      label: (context) => context.l10n.navMyTasks,
    ),
    ShellDestination(
      path: '/reports',
      icon: Icons.description_outlined,
      selectedIcon: Icons.description_rounded,
      label: (context) => context.l10n.navReports,
    ),
    messages(),
  ];
}

Widget _projectCollection(
  Ref ref,
  BuildContext context,
  String title,
  String Function(String) path,
  String empty,
  IconData icon, {
  String? createRoute,
  String? entityType,
}) {
  final project = ref.read(projectContextProvider).selected;
  return project == null
      // Was a bare sentence centred in white space; every other
      // "nothing to show" in the app is a MessageView with an icon and a
      // next step, and this one is reached from the navigation bar.
      ? Scaffold(
          appBar: AppBar(title: Text(title)),
          body: MessageView(
            icon: Icons.apartment_rounded,
            title: context.l10n.commonNoProjectSelected,
            message: context.l10n.commonSelectProjectFirst,
          ),
        )
      : RemoteCollectionScreen(
          title: title,
          path: path(project.id),
          emptyMessage: empty,
          icon: icon,
          createRoute: createRoute,
          entityType: entityType,
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
