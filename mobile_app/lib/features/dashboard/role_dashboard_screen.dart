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
import '../../models/project.dart';
import '../../models/user.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';

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
      return Scaffold(
        body: MessageView(
          icon: Icons.apartment_rounded,
          title: context.l10n.commonSelectProject,
          message: context.l10n.dashboardSelectProjectBody,
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
                Expanded(
                  child: LoadingView(label: context.l10n.dashboardLoading),
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
                    title: context.l10n.commonUnavailable(
                      context.l10n.dashboardTitle,
                    ),
                    message: context.l10n.describeError(snapshot.error),
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
    final attention = _attention(context, kind, data);
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
                // Primary: what needs this person now. Nothing above it, and
                // on a clear project it is the whole screen above the fold.
                SectionHeader(
                  title: context.l10n.dashboardTodayTitle,
                  subtitle: context.l10n.dashboardTodayBody,
                ),
                const SizedBox(height: AppSpacing.sm),
                if (attention.isEmpty)
                  const _AllClearCard()
                else
                  for (final item in attention)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: AttentionRow(
                        label: item.label,
                        count: context.formatInt(item.count),
                        icon: item.icon,
                        tone: item.tone,
                        onTap: () => context.go(item.route),
                      ),
                    ),

                // Secondary: how the project as a whole is doing.
                const SizedBox(height: AppSpacing.lg),
                ProjectProgressCard(
                  progress: project.completionPercentage,
                  status: project.status,
                ),

                if (kind == 'owner') ...[
                  const SizedBox(height: AppSpacing.lg),
                  SectionHeader(
                    title: context.l10n.dashboardExecutiveIntelligence,
                    subtitle: context.l10n.dashboardExecutiveIntelligenceBody,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  SmartSummaryCard(
                    state: SmartSummaryState.ready,
                    summary: _executiveSummary(context, data),
                  ),
                ],

                const SizedBox(height: AppSpacing.xl),
                SectionHeader(
                  title: context.l10n.dashboardQuickAccess,
                  subtitle: context.l10n.dashboardQuickAccessBody,
                ),
                const SizedBox(height: AppSpacing.sm),
                _QuickActions(kind: kind),

                // Tertiary: context, not action. Last, and only three rows.
                const SizedBox(height: AppSpacing.xl),
                SectionHeader(
                  title: context.l10n.dashboardRecentActivity,
                  subtitle: context.l10n.dashboardRecentActivityBody,
                ),
                const SizedBox(height: AppSpacing.sm),
                _ActivityPreview(data: data),
                const SizedBox(height: 88),
              ],
            ),
          ),
        ),
      ],
    );
  }

  /// The role's exception list, worst first, zeroes removed.
  ///
  /// Only things a person can *act on* are here. "Approved work" and
  /// "verified evidence" are achievements — real numbers, but they belong on
  /// the web dashboard, because nobody standing on a slab needs them.
  List<_Attention> _attention(
    BuildContext context,
    String kind,
    Map<String, dynamic> data,
  ) {
    final l10n = context.l10n;
    int count(String key) {
      final value = data[key];
      return value is num
          ? value.toInt()
          : value is List
          ? value.length
          : 0;
    }

    final rows = switch (kind) {
      'consultant' => [
        _Attention(
          l10n.dashboardOverdueReviews,
          count('overdueReviews'),
          Icons.timer_outlined,
          AppColors.stateOverdue,
          '/reviews',
        ),
        _Attention(
          l10n.dashboardPendingReviews,
          count('pendingReviews'),
          Icons.fact_check_outlined,
          AppColors.stateReview,
          '/reviews',
        ),
        _Attention(
          l10n.dashboardAwaitingRework,
          count('reworkAwaitingResubmission'),
          Icons.replay_rounded,
          AppColors.stateProgress,
          '/reviews',
        ),
      ],
      'owner' => [
        _Attention(
          l10n.dashboardDelayedTasks,
          count('delayedTasks'),
          Icons.warning_amber_rounded,
          AppColors.stateOverdue,
          '/reports',
        ),
        _Attention(
          l10n.dashboardOpenRisks,
          count('openIssues'),
          Icons.report_problem_outlined,
          AppColors.stateReview,
          '/actions',
        ),
        _Attention(
          l10n.dashboardDecisions,
          count('attentionRequired'),
          Icons.gavel_outlined,
          AppColors.stateProgress,
          '/actions',
        ),
      ],
      'worker' => [
        _Attention(
          l10n.dashboardNeedsCorrection,
          count('rejectedEvidence'),
          Icons.refresh_rounded,
          AppColors.stateOverdue,
          '/evidence',
        ),
        _Attention(
          l10n.dashboardAssignedTasks,
          count('assignedTasks'),
          Icons.task_alt_outlined,
          AppColors.stateProgress,
          '/tasks',
        ),
      ],
      _ => [
        _Attention(
          l10n.dashboardOverdue,
          count('overdueTasks'),
          Icons.event_busy_outlined,
          AppColors.stateOverdue,
          '/tasks',
        ),
        _Attention(
          l10n.dashboardOpenIssues,
          count('openIssues'),
          Icons.report_problem_outlined,
          AppColors.stateOverdue,
          '/issues',
        ),
        _Attention(
          l10n.dashboardBlocked,
          count('blockedTasks'),
          Icons.block_outlined,
          AppColors.stateBlocked,
          '/tasks',
        ),
        _Attention(
          l10n.dashboardReworkRequired,
          count('reworkRequired'),
          Icons.replay_rounded,
          AppColors.stateReview,
          '/tasks',
        ),
        _Attention(
          l10n.dashboardWaitingReview,
          count('waitingForReview'),
          Icons.rate_review_outlined,
          AppColors.stateReview,
          '/tasks',
        ),
        _Attention(
          l10n.dashboardTodaysTasks,
          count('todayTasks'),
          Icons.today_outlined,
          AppColors.stateProgress,
          '/tasks',
        ),
      ],
    };
    return rows.where((row) => row.count > 0).toList();
  }

  String _executiveSummary(BuildContext context, Map<String, dynamic> data) {
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
    return context.l10n.dashboardExecutiveSummary(
      context.formatInt(progress is num ? progress : 0),
      context.l10n.statusLabel('$health'),
      delayed,
      risks,
    );
  }
}

/// One exception the role can act on.
class _Attention {
  const _Attention(this.label, this.count, this.icon, this.tone, this.route);
  final String label;
  final int count;
  final IconData icon;
  final Color tone;
  final String route;
}

/// Shown when a role has no outstanding exceptions at all.
///
/// "Nothing needs you" is a real answer and worth stating plainly; the
/// previous grid said it with six zeroes, which reads as no data rather than
/// as good news.
class _AllClearCard extends StatelessWidget {
  const _AllClearCard();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.lg),
    decoration: BoxDecoration(
      color: AppColors.stateVerifiedWash,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      border: Border.all(
        color: AppColors.stateVerified.withValues(alpha: .22),
      ),
    ),
    child: Row(
      children: [
        const Icon(
          Icons.check_circle_outline_rounded,
          color: AppColors.stateVerified,
          size: 26,
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.dashboardAllClearTitle,
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 2),
              Text(
                context.l10n.dashboardAllClearBody,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ],
    ),
  );
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
        ? context.l10n.dashboardGreetingMorning
        : hour < 18
        ? context.l10n.dashboardGreetingAfternoon
        : context.l10n.dashboardGreetingEvening;
    // The header holds a `Spacer`, so it needs a bounded height — but the
    // previous hardcoded 238 was sized against the old, smaller type and
    // overflowed by 13px once the headings matched the web. Deriving it from
    // the user's text scale fixes that and also stops the much larger
    // overflow an accessibility text setting would otherwise cause. Clamped
    // so an extreme setting cannot push the header off the screen.
    final textScale = MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 1.5);
    return Container(
      // A *minimum* height, not a fixed one. Pinning the header to a constant
      // meant every extra pixel of content overflowed it: a long greeting, a
      // long role caption, or a translation wider than the English original
      // all pushed it over — which is exactly what a device pass caught, at
      // 5.5px, once the copy came from the message catalogue. Sizing to the
      // content removes the whole class of failure instead of re-tuning the
      // number for whichever string happens to be longest today.
      constraints: BoxConstraints(minHeight: 254 * textScale),
      decoration: const BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(AppRadius.sheet),
        ),
      ),
      child: Stack(
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
                        tooltip: context.l10n.commonNotifications,
                        icon: Icons.notifications_none_rounded,
                        onTap: () => context.push('/notifications'),
                      ),
                      const SizedBox(width: 8),
                      // Profile left the bottom bar to make room for the
                      // voice action; it lives here, where an avatar is the
                      // conventional place to look for it.
                      _HeaderAvatar(user: user),
                    ],
                  ),
                  // Was a Spacer, which requires a bounded height the
                  // content-sized header no longer provides.
                  const SizedBox(height: 26),
                  Text(
                    context.l10n.dashboardGreeting(greeting, firstName),
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
                          color: AppColors.stateVerified,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 7),
                      Expanded(
                        child: Text(
                          _roleTitle(context, kind),
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
                  // The chip carried a downward chevron but did nothing when
                  // tapped, so the only way to change project was a separate
                  // icon in the corner. The affordance now does what it says.
                  Semantics(
                    button: true,
                    label: context.l10n.dashboardChangeProject,
                    child: Material(
                      color: Colors.white.withValues(alpha: .1),
                      borderRadius: BorderRadius.circular(AppRadius.control),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(AppRadius.control),
                        onTap: () => context.go('/projects'),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            borderRadius:
                                BorderRadius.circular(AppRadius.control),
                            border: Border.all(
                              color: Colors.white.withValues(alpha: .1),
                            ),
                          ),
                          child: Row(
                            children: [
                              const Icon(
                                Icons.apartment_rounded,
                                color: AppColors.accent,
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
                                Icons.unfold_more_rounded,
                                color: Colors.white54,
                                size: 19,
                              ),
                            ],
                          ),
                        ),
                      ),
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

  String _roleTitle(BuildContext context, String kind) => switch (kind) {
    'engineer' => context.l10n.roleCaptionSiteEngineer,
    'consultant' => context.l10n.roleCaptionConsultant,
    'owner' => context.l10n.roleCaptionOwner,
    'worker' => context.l10n.roleCaptionWorker,
    _ => context.l10n.roleCaptionProjectManager,
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

/// The user's own avatar, which opens the profile.
class _HeaderAvatar extends StatelessWidget {
  const _HeaderAvatar({required this.user});
  final User user;

  @override
  Widget build(BuildContext context) {
    final initials = user.fullName
        .trim()
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .take(2)
        .map((part) => part.characters.first)
        .join();
    return Tooltip(
      message: context.l10n.dashboardOpenProfile,
      child: Semantics(
        button: true,
        label: context.l10n.dashboardOpenProfile,
        child: InkResponse(
          onTap: () => context.go('/profile'),
          radius: 26,
          child: Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .12),
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white.withValues(alpha: .18)),
            ),
            child: Text(
              // Initials rather than an icon: it is the one place the app
              // confirms *which account* is signed in, which matters on a
              // shared site phone.
              initials.isEmpty ? '·' : initials.toUpperCase(),
              textDirection: TextDirection.ltr,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.kind});
  final String kind;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // Deliberately never repeats a bottom-navigation destination: a tile that
    // goes where the bar already goes is a wasted third of the row. These are
    // the sections that have no permanent home — including Design Changes,
    // which the backend has always served and mobile had no way to reach.
    final actions = switch (kind) {
      'consultant' => [
        (l10n.navDesignChanges, Icons.architecture_rounded, '/design-changes'),
        (l10n.navIfcModels, Icons.view_in_ar_outlined, '/ifc'),
        (l10n.navMyActions, Icons.checklist_rounded, '/actions'),
      ],
      'owner' => [
        (l10n.navMyActions, Icons.checklist_rounded, '/actions'),
        (l10n.navDesignChanges, Icons.architecture_rounded, '/design-changes'),
        (l10n.navDocuments, Icons.folder_outlined, '/documents'),
      ],
      'worker' => [
        (l10n.navDocuments, Icons.folder_outlined, '/documents'),
        (l10n.navMyActions, Icons.checklist_rounded, '/actions'),
      ],
      _ => [
        (l10n.navMyActions, Icons.checklist_rounded, '/actions'),
        (l10n.navDesignChanges, Icons.architecture_rounded, '/design-changes'),
        (l10n.navIfcModels, Icons.view_in_ar_outlined, '/ifc'),
      ],
    };
    return Row(
      children: actions
          .map(
            (action) => Expanded(
              child: Padding(
                // Directional: a physical `right` inset put the gap on the
                // wrong side of every tile in Arabic, so the row sat flush
                // against the leading edge and had a hole at the trailing one.
                padding: EdgeInsetsDirectional.only(
                  end: action != actions.last ? 10 : 0,
                ),
                child: InkWell(
                  borderRadius: BorderRadius.circular(AppRadius.panel),
                  onTap: () => context.go(action.$3),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 16,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(AppRadius.panel),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Column(
                      children: [
                        Icon(action.$2, color: AppColors.primary),
                        const SizedBox(height: 8),
                        // Two lines with a reserved height, not one line
                        // ellipsised: Arabic section names are routinely
                        // twice the English width, and "تغييرات التصميم" at
                        // a third of the screen has to wrap rather than
                        // become "تغييرات…". The fixed box keeps every tile
                        // the same height whichever language is active.
                        SizedBox(
                          height: 28,
                          child: Center(
                            child: Text(
                              action.$1,
                              maxLines: 2,
                              textAlign: TextAlign.center,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 11,
                                height: 1.15,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
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
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              const Icon(
                Icons.history_rounded,
                color: AppColors.mutedForeground,
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(context.l10n.dashboardNoActivity)),
            ],
          ),
        ),
      );
    }
    return Card(
      child: Column(
        children: List.generate(items.length, (index) {
          final item = items[index] is Map ? items[index] as Map : const {};
          // The feed sends the raw audit action (`reminders_dispatched`).
          // Every entry goes through the catalogue, and an action with no
          // translation becomes a generic translated sentence — never the
          // identifier itself, which is what a device pass found on screen.
          final label = context.l10n.activityLabel(
            '${item['action'] ?? item['type'] ?? ''}',
          );
          final actor = item['actorName'] ?? item['user'] ?? item['actor'];
          final actorName = actor is Map ? actor['fullName'] : actor;
          final timestamp = DateTime.tryParse('${item['timestamp'] ?? ''}');
          final caption = [
            if ('${actorName ?? ''}'.trim().isNotEmpty) '$actorName',
            if (timestamp != null) context.formatDateTime(timestamp),
          ].join('  ·  ');
          return Column(
            children: [
              ListTile(
                leading: Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: AppColors.stateProgressWash,
                    borderRadius: BorderRadius.circular(AppRadius.control),
                  ),
                  child: const Icon(
                    Icons.history_rounded,
                    color: AppColors.stateProgress,
                    size: 20,
                  ),
                ),
                title: Text(
                  label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: caption.isEmpty ? null : Text(caption),
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
