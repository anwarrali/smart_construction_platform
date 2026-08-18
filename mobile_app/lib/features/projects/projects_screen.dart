import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/session_manager.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_shadows.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/async_views.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/project.dart';
import 'project_context_view_model.dart';

class ProjectsScreen extends ConsumerStatefulWidget {
  const ProjectsScreen({super.key});
  @override
  ConsumerState<ProjectsScreen> createState() => _ProjectsScreenState();
}

class _ProjectsScreenState extends ConsumerState<ProjectsScreen> {
  bool _switchingAccount = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(projectContextProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(projectContextProvider);
    final Widget content;
    if (state.loading) {
      content = LoadingView(label: context.l10n.projectsLoading);
    } else if (state.error != null) {
      content = MessageView(
        icon: Icons.cloud_off_rounded,
        title: context.l10n.commonUnavailable(context.l10n.projectsTitle),
        message: context.l10n.describeError(state.error),
        onAction: () => ref.read(projectContextProvider.notifier).load(),
      );
    } else if (state.projects.isEmpty) {
      content = MessageView(
        icon: Icons.apartment_rounded,
        title: context.l10n.projectsNoneAssigned,
        message: context.l10n.projectsNoneAssignedBody,
        actionLabel: context.l10n.projectsSwitchAccount,
        onAction: _switchingAccount ? null : _requestAccountSwitch,
      );
    } else {
      content = RefreshIndicator(
        onRefresh: () => ref.read(projectContextProvider.notifier).load(),
        child: ListView.separated(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.page,
            AppSpacing.lg,
            AppSpacing.page,
            100,
          ),
          itemCount: state.projects.length,
          separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.md),
          itemBuilder: (context, index) {
            final project = state.projects[index];
            return _ProjectCard(
              project: project,
              selected: state.selected?.id == project.id,
              onTap: () async {
                await ref.read(projectContextProvider.notifier).select(project);
                if (context.mounted) context.go('/home');
              },
            );
          },
        ),
      );
    }

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _requestAccountSwitch();
      },
      child: Scaffold(
        body: Column(
          children: [
            _ProjectsHeader(
              switchingAccount: _switchingAccount,
              onSwitchAccount: _requestAccountSwitch,
            ),
            Expanded(child: content),
          ],
        ),
      ),
    );
  }

  Future<void> _requestAccountSwitch() async {
    if (_switchingAccount) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: const Icon(Icons.switch_account_rounded),
        title: Text(context.l10n.projectsSwitchAccountQuestion),
        content: Text(context.l10n.projectsSwitchAccountBody),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(context.l10n.commonCancel),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(dialogContext, true),
            icon: const Icon(Icons.logout_rounded),
            label: Text(context.l10n.commonSignOut),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _switchingAccount = true);
    try {
      await ref.read(projectContextProvider.notifier).clearForLogout();
      await ref.read(sessionProvider.notifier).logout();
    } finally {
      if (mounted) setState(() => _switchingAccount = false);
    }
  }
}

class _ProjectsHeader extends StatelessWidget {
  const _ProjectsHeader({
    required this.switchingAccount,
    required this.onSwitchAccount,
  });

  final bool switchingAccount;
  final VoidCallback onSwitchAccount;

  @override
  Widget build(BuildContext context) => Container(
    height: 188,
    decoration: const BoxDecoration(
      color: AppColors.primary,
      borderRadius: BorderRadius.vertical(
        bottom: Radius.circular(AppRadius.sheet),
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
              24,
              AppSpacing.page,
              30,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  context.l10n.projectsMyProjects,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  context.l10n.projectsSelectWorkspace,
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
        SafeArea(
          bottom: false,
          child: Align(
            // Directional: the chip belongs on the side opposite the
            // heading, which is the left in Arabic. Hardcoding topRight
            // put it on top of the heading under RTL.
            alignment: AlignmentDirectional.topEnd,
            child: Padding(
              padding: const EdgeInsets.only(
                top: AppSpacing.sm,
                right: AppSpacing.sm,
              ),
              child: TextButton.icon(
                onPressed: switchingAccount ? null : onSwitchAccount,
                style: TextButton.styleFrom(
                  foregroundColor: Colors.white,
                  disabledForegroundColor: Colors.white54,
                  backgroundColor: Colors.white.withValues(alpha: .10),
                ),
                icon: switchingAccount
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.switch_account_rounded, size: 19),
                label: Text(context.l10n.projectsSwitchAccount),
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

class _ProjectCard extends StatelessWidget {
  const _ProjectCard({
    required this.project,
    required this.selected,
    required this.onTap,
  });
  final Project project;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      border: Border.all(
        color: selected ? AppColors.accent : AppColors.border,
        width: selected ? 1.5 : 1,
      ),
      boxShadow: AppShadows.card,
    ),
    child: InkWell(
      borderRadius: BorderRadius.circular(AppRadius.panel),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: AppColors.primary,
                    borderRadius: BorderRadius.circular(15),
                  ),
                  child: const Icon(
                    Icons.apartment_rounded,
                    color: AppColors.accent,
                  ),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        project.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      if (project.location != null) ...[
                        const SizedBox(height: 4),
                        Row(
                          children: [
                            const Icon(
                              Icons.location_on_outlined,
                              size: 14,
                              color: AppColors.mutedForeground,
                            ),
                            const SizedBox(width: 3),
                            Expanded(
                              child: Text(
                                project.location!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: Theme.of(context).textTheme.bodySmall,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                StatusBadge(project.status, compact: true),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              children: [
                Text(
                  context.l10n.projectsProgress,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                Text(
                  context.formatPercent(project.completionPercentage),
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            LinearProgressIndicator(
              value: project.completionPercentage.clamp(0, 100) / 100,
              minHeight: 8,
              borderRadius: BorderRadius.circular(10),
            ),
            const SizedBox(height: AppSpacing.md),
            Row(
              children: [
                if (project.openIssueCount > 0) ...[
                  const Icon(
                    Icons.report_problem_outlined,
                    size: 16,
                    color: AppColors.stateReview,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    context.l10n.projectsOpenIssues(project.openIssueCount),
                    style: const TextStyle(
                      fontSize: 11,
                      color: AppColors.stateReview,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
                const Spacer(),
                Text(
                  selected
                      ? context.l10n.projectsCurrentProject
                      : context.l10n.projectsOpenWorkspace,
                  style: TextStyle(
                    fontSize: 12,
                    color: selected ? AppColors.stateVerified : AppColors.primary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(width: 4),
                Icon(
                  selected
                      ? Icons.check_circle_rounded
                      : Icons.arrow_forward_rounded,
                  size: 17,
                  color: selected ? AppColors.stateVerified : AppColors.primary,
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}
