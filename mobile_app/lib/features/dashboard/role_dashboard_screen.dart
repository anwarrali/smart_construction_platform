import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/brand_mark.dart';
import '../../core/widgets/dashboard_components.dart';
import '../../core/widgets/record_update_control.dart';
import '../../models/project.dart';
import '../../models/user.dart';
import '../projects/project_context_view_model.dart';

class RoleDashboardScreen extends ConsumerStatefulWidget {
  const RoleDashboardScreen({super.key});

  @override
  ConsumerState<RoleDashboardScreen> createState() =>
      _RoleDashboardScreenState();
}

class _RoleDashboardScreenState extends ConsumerState<RoleDashboardScreen> {
  String? _loadedProjectId;
  Future<Map<String, dynamic>>? _dashboard;

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(sessionProvider).user;
    final project = ref.watch(projectContextProvider).selected;
    if (user == null) return const Scaffold(body: LoadingView());
    if (project == null) {
      return const Scaffold(
        body: MessageView(
          icon: Icons.apartment_rounded,
          title: 'Select a project',
          message: 'Choose a project to see its dashboard.',
        ),
      );
    }
    final kind = _kindFor(user);
    if (_loadedProjectId != project.id || _dashboard == null) {
      _loadedProjectId = project.id;
      _dashboard = ref
          .read(projectRepositoryProvider)
          .dashboard(project.id, kind: kind);
    }

    return Scaffold(
      body: FutureBuilder<Map<String, dynamic>>(
        future: _dashboard,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return Column(
              children: [
                _DashboardHeader(user: user, project: project, kind: kind),
                const Expanded(
                  child: LoadingView(label: 'Loading project dashboard'),
                ),
              ],
            );
          }
          if (snapshot.hasError) {
            return Column(
              children: [
                _DashboardHeader(user: user, project: project, kind: kind),
                Expanded(
                  child: MessageView(
                    icon: Icons.cloud_off_rounded,
                    title: 'Dashboard unavailable',
                    message: '${snapshot.error}',
                    onAction: _refresh,
                  ),
                ),
              ],
            );
          }
          return RefreshIndicator(
            onRefresh: _refresh,
            child: _DashboardContent(
              user: user,
              project: project,
              kind: kind,
              data: snapshot.data ?? const {},
            ),
          );
        },
      ),
    );
  }

  Future<void> _refresh() async {
    final user = ref.read(sessionProvider).user;
    final project = ref.read(projectContextProvider).selected;
    if (user == null || project == null) return;
    setState(
      () => _dashboard = ref
          .read(projectRepositoryProvider)
          .dashboard(project.id, kind: _kindFor(user)),
    );
    await _dashboard;
  }

  String _kindFor(User user) => user.isWorker
      ? 'worker'
      : user.isSiteEngineer
      ? 'engineer'
      : user.isConsultant
      ? 'consultant'
      : user.isOwner
      ? 'owner'
      : 'manager';
}

class _DashboardContent extends StatelessWidget {
  const _DashboardContent({
    required this.user,
    required this.project,
    required this.kind,
    required this.data,
  });
  final User user;
  final Project project;
  final String kind;
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final cards = _metrics(kind, data);
    return ListView(
      padding: EdgeInsets.zero,
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        _DashboardHeader(user: user, project: project, kind: kind),
        Transform.translate(
          offset: const Offset(0, -18),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.page),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ProjectProgressCard(
                  progress: project.completionPercentage,
                  status: project.status,
                ),
                if (kind == 'engineer') ...[
                  const SizedBox(height: AppSpacing.lg),
                  const SectionHeader(
                    title: 'Fast field update',
                    subtitle: 'Capture work without stopping your workflow',
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Align(
                    alignment: Alignment.center,
                    child: SizedBox(
                      width: 380,
                      child: RecordUpdateCard(
                        onPressed: () => context.push('/voice'),
                      ),
                    ),
                  ),
                ],
                if (kind == 'owner') ...[
                  const SizedBox(height: AppSpacing.lg),
                  const SectionHeader(
                    title: 'Executive intelligence',
                    subtitle: 'Current status and future smart insights',
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  SmartSummaryCard(
                    state: SmartSummaryState.ready,
                    summary: _executiveSummary(data),
                  ),
                ],
                const SizedBox(height: AppSpacing.xl),
                SectionHeader(
                  title: kind == 'engineer'
                      ? 'Needs your attention'
                      : 'Project snapshot',
                  subtitle: _sectionSubtitle(kind),
                ),
                const SizedBox(height: AppSpacing.sm),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final aspect = constraints.maxWidth < 350 ? 1.18 : 1.32;
                    return GridView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: cards.length,
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        crossAxisSpacing: AppSpacing.sm,
                        mainAxisSpacing: AppSpacing.sm,
                        childAspectRatio: aspect,
                      ),
                      itemBuilder: (_, index) {
                        final item = cards[index];
                        return DashboardMetricCard(
                          label: item.$1,
                          value: item.$2,
                          icon: item.$3,
                          tone: item.$4,
                        );
                      },
                    );
                  },
                ),
                const SizedBox(height: AppSpacing.xl),
                const SectionHeader(
                  title: 'Quick access',
                  subtitle: 'Role-appropriate project tools',
                ),
                const SizedBox(height: AppSpacing.sm),
                _QuickActions(kind: kind),
                const SizedBox(height: AppSpacing.xl),
                const SectionHeader(
                  title: 'Recent activity',
                  subtitle: 'Latest information from this project',
                ),
                const SizedBox(height: AppSpacing.sm),
                _ActivityPreview(data: data),
                const SizedBox(height: 104),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _sectionSubtitle(String kind) => switch (kind) {
    'engineer' => 'Tasks, blockers, and reviews that need action',
    'consultant' => 'Review workload and submitted work',
    'owner' => 'High-level progress, risk, and decisions',
    _ => 'Execution health and team priorities',
  };

  List<(String, String, IconData, Color)> _metrics(
    String kind,
    Map<String, dynamic> data,
  ) {
    int count(List<String> keys) {
      dynamic value = data;
      for (final key in keys) {
        if (value is Map) value = value[key];
      }
      return value is num
          ? value.toInt()
          : value is List
          ? value.length
          : 0;
    }

    if (kind == 'consultant') {
      return [
        (
          'Pending reviews',
          '${count(['pendingReviews'])}',
          Icons.fact_check_outlined,
          AppColors.info,
        ),
        (
          'Overdue reviews',
          '${count(['overdueReviews'])}',
          Icons.timer_outlined,
          AppColors.danger,
        ),
        (
          'Approved work',
          '${count(['approvedWork'])}',
          Icons.verified_outlined,
          AppColors.success,
        ),
        (
          'Awaiting rework',
          '${count(['reworkAwaitingResubmission'])}',
          Icons.replay_rounded,
          AppColors.warning,
        ),
      ];
    }
    if (kind == 'owner') {
      return [
        (
          'Delayed tasks',
          '${count(['delayedTasks'])}',
          Icons.warning_amber_rounded,
          AppColors.danger,
        ),
        (
          'Open risks',
          '${count(['openIssues'])}',
          Icons.report_problem_outlined,
          AppColors.warning,
        ),
        (
          'Decisions',
          '${count(['attentionRequired'])}',
          Icons.gavel_outlined,
          AppColors.info,
        ),
        (
          'Milestones',
          '${count(['milestones'])}',
          Icons.flag_outlined,
          AppColors.success,
        ),
      ];
    }
    if (kind == 'worker') {
      return [
        ('Assigned tasks', '${count(['assignedTasks'])}', Icons.task_alt_outlined, AppColors.info),
        ('Submitted', '${count(['submittedEvidence'])}', Icons.cloud_upload_outlined, AppColors.info),
        ('Verified', '${count(['verifiedEvidence'])}', Icons.verified_outlined, AppColors.success),
        ('Needs correction', '${count(['rejectedEvidence'])}', Icons.refresh_rounded, AppColors.warning),
      ];
    }
    return [
      (
        'Today’s tasks',
        '${count(['todayTasks'])}',
        Icons.today_outlined,
        AppColors.info,
      ),
      (
        'Overdue',
        '${count(['overdueTasks'])}',
        Icons.event_busy_outlined,
        AppColors.danger,
      ),
      (
        'Blocked',
        '${count(['blockedTasks'])}',
        Icons.block_outlined,
        AppColors.warning,
      ),
      (
        'Waiting review',
        '${count(['waitingForReview'])}',
        Icons.rate_review_outlined,
        AppColors.info,
      ),
      (
        'Rework required',
        '${count(['reworkRequired'])}',
        Icons.replay_rounded,
        AppColors.warning,
      ),
      (
        'Open issues',
        '${count(['openIssues'])}',
        Icons.report_problem_outlined,
        AppColors.danger,
      ),
    ];
  }

  String _executiveSummary(Map<String, dynamic> data) {
    final summary = data['projectSummary'] as Map? ?? const {};
    final progress =
        summary['completionPercentage'] ?? project.completionPercentage.round();
    final health = data['projectHealth'] ?? project.status;
    final delayed = data['delayedTasks'] is List
        ? (data['delayedTasks'] as List).length
        : 0;
    final risks = data['openIssues'] is List
        ? (data['openIssues'] as List).length
        : 0;
    return 'Overall progress is $progress%. Project health is ${health.toString().replaceAll('_', ' ')}. There are $delayed delayed tasks and $risks open risks requiring visibility.';
  }
}

class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader({
    required this.user,
    required this.project,
    required this.kind,
  });
  final User user;
  final Project project;
  final String kind;

  @override
  Widget build(BuildContext context) {
    final firstName =
        user.fullName.trim().split(RegExp(r'\s+')).firstOrNull ?? user.fullName;
    final hour = DateTime.now().hour;
    final greeting = hour < 12
        ? 'Good morning'
        : hour < 18
        ? 'Good afternoon'
        : 'Good evening';
    return Container(
      height: 238,
      decoration: const BoxDecoration(
        color: AppColors.navy,
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(AppRadius.extraLarge),
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.page,
                12,
                AppSpacing.page,
                34,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const BrandMark(compact: true),
                      const Spacer(),
                      _HeaderIcon(
                        tooltip: 'Notifications',
                        icon: Icons.notifications_none_rounded,
                        onTap: () => context.push('/notifications'),
                      ),
                      const SizedBox(width: 8),
                      _HeaderIcon(
                        tooltip: 'Change project',
                        icon: Icons.swap_horiz_rounded,
                        onTap: () => context.go('/projects'),
                      ),
                    ],
                  ),
                  const Spacer(),
                  Text(
                    '$greeting, $firstName',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -.4,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Row(
                    children: [
                      Container(
                        width: 7,
                        height: 7,
                        decoration: const BoxDecoration(
                          color: AppColors.success,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 7),
                      Expanded(
                        child: Text(
                          _roleTitle(kind),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 15),
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: .1),
                      borderRadius: BorderRadius.circular(13),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: .1),
                      ),
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.apartment_rounded,
                          color: AppColors.bronze,
                          size: 19,
                        ),
                        const SizedBox(width: 9),
                        Expanded(
                          child: Text(
                            project.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        const Icon(
                          Icons.keyboard_arrow_down_rounded,
                          color: Colors.white54,
                          size: 19,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _roleTitle(String kind) => switch (kind) {
    'engineer' => 'Main Contractor · Site Engineer',
    'consultant' => 'Consultant Engineer · Review & Quality',
    'owner' => 'Project Owner · Executive View',
    'worker' => 'Construction Worker · Field Evidence',
    _ => 'Project Manager · Field Monitoring',
  };
}

class _HeaderIcon extends StatelessWidget {
  const _HeaderIcon({
    required this.tooltip,
    required this.icon,
    required this.onTap,
  });
  final String tooltip;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    onPressed: onTap,
    style: IconButton.styleFrom(
      backgroundColor: Colors.white.withValues(alpha: .1),
      foregroundColor: Colors.white,
    ),
    icon: Icon(icon),
  );
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.kind});
  final String kind;

  @override
  Widget build(BuildContext context) {
    final actions = switch (kind) {
      'consultant' => const [
        ('Reviews', Icons.fact_check_outlined, '/reviews'),
        ('Documents', Icons.folder_outlined, '/documents'),
        ('Reports', Icons.description_outlined, '/reports'),
      ],
      'owner' => const [
        ('Reports', Icons.description_outlined, '/reports'),
        ('Projects', Icons.apartment_rounded, '/projects'),
        ('Messages', Icons.forum_outlined, '/messages'),
      ],
      'worker' => const [
        ('My Tasks', Icons.task_alt_outlined, '/tasks'),
        ('Field Evidence', Icons.photo_camera_back_outlined, '/evidence'),
        ('Profile', Icons.person_outline, '/profile'),
      ],
      'manager' => const [
        ('Tasks', Icons.task_alt_outlined, '/tasks'),
        ('Reports', Icons.description_outlined, '/reports'),
        ('Issues', Icons.report_problem_outlined, '/issues'),
      ],
      _ => const [
        ('My Tasks', Icons.task_alt_outlined, '/tasks'),
        ('Reports', Icons.description_outlined, '/reports'),
        ('Messages', Icons.forum_outlined, '/messages'),
      ],
    };
    return Row(
      children: actions
          .map(
            (action) => Expanded(
              child: Padding(
                padding: EdgeInsets.only(
                  right: action != actions.last ? 10 : 0,
                ),
                child: InkWell(
                  borderRadius: BorderRadius.circular(AppRadius.medium),
                  onTap: () => context.go(action.$3),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 16,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(AppRadius.medium),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Column(
                      children: [
                        Icon(action.$2, color: AppColors.navy),
                        const SizedBox(height: 8),
                        Text(
                          action.$1,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _ActivityPreview extends StatelessWidget {
  const _ActivityPreview({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final raw =
        data['recentActivities'] ??
        data['recentActivity'] ??
        data['teamActivity'];
    final items = raw is List ? raw.take(3).toList() : const [];
    if (items.isEmpty) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(18),
          child: Row(
            children: [
              Icon(Icons.history_rounded, color: AppColors.textSecondary),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'New project activity will appear here as your team works.',
                ),
              ),
            ],
          ),
        ),
      );
    }
    return Card(
      child: Column(
        children: List.generate(items.length, (index) {
          final item = items[index] is Map ? items[index] as Map : const {};
          final description =
              item['description'] ??
              item['action'] ??
              item['type'] ??
              'Project activity';
          return Column(
            children: [
              ListTile(
                leading: Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: AppColors.infoSoft,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.history_rounded,
                    color: AppColors.info,
                    size: 20,
                  ),
                ),
                title: Text(
                  '$description',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: item['user'] == null ? null : Text('${item['user']}'),
              ),
              if (index != items.length - 1)
                const Divider(height: 1, indent: 66),
            ],
          );
        }),
      ),
    );
  }
}

extension _FirstOrNull<T> on List<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
