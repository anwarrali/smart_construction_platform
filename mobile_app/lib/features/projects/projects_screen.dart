import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/auth/session_manager.dart';
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
      content = const LoadingView(label: 'Loading assigned projects');
    } else if (state.error != null) {
      content = MessageView(
        icon: Icons.cloud_off_rounded,
        title: 'Projects unavailable',
        message: state.error!,
        onAction: () => ref.read(projectContextProvider.notifier).load(),
      );
    } else if (state.projects.isEmpty) {
      content = MessageView(
        icon: Icons.apartment_rounded,
        title: 'No projects assigned',
        message:
            'Contact your administrator or project manager for access, '
            'or switch to another account.',
        actionLabel: 'Switch account',
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
        title: const Text('Switch account?'),
        content: const Text(
          'You will be signed out and returned to the sign-in screen.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Cancel'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(dialogContext, true),
            icon: const Icon(Icons.logout_rounded),
            label: const Text('Sign out'),
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
      color: AppColors.navy,
      borderRadius: BorderRadius.vertical(
        bottom: Radius.circular(AppRadius.extraLarge),
      ),
    ),
    child: Stack(
      fit: StackFit.expand,
      children: [
        const SafeArea(
          bottom: false,
          child: Padding(
            padding: EdgeInsets.fromLTRB(
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
                  'My Projects',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                SizedBox(height: 7),
                Text(
                  'Select a workspace to continue',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
        SafeArea(
          bottom: false,
          child: Align(
            alignment: Alignment.topRight,
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
                label: const Text('Switch account'),
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
      borderRadius: BorderRadius.circular(AppRadius.large),
      border: Border.all(
        color: selected ? AppColors.bronze : AppColors.border,
        width: selected ? 1.5 : 1,
      ),
      boxShadow: AppShadows.card,
    ),
    child: InkWell(
      borderRadius: BorderRadius.circular(AppRadius.large),
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
                    color: AppColors.navy,
                    borderRadius: BorderRadius.circular(15),
                  ),
                  child: const Icon(
                    Icons.apartment_rounded,
                    color: AppColors.bronze,
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
                              color: AppColors.textSecondary,
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
                  'Project progress',
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                Text(
                  '${project.completionPercentage.round()}%',
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: AppColors.navy,
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
                    color: AppColors.warning,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '${project.openIssueCount} open issues',
                    style: const TextStyle(
                      fontSize: 11,
                      color: AppColors.warning,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
                const Spacer(),
                Text(
                  selected ? 'Current project' : 'Open workspace',
                  style: TextStyle(
                    fontSize: 12,
                    color: selected ? AppColors.success : AppColors.navy,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(width: 4),
                Icon(
                  selected
                      ? Icons.check_circle_rounded
                      : Icons.arrow_forward_rounded,
                  size: 17,
                  color: selected ? AppColors.success : AppColors.navy,
                ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}
