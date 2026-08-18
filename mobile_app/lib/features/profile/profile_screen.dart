import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/auth/session_manager.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../projects/project_context_view_model.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../app/locale_controller.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(sessionProvider).user;
    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final role = user.isSiteEngineer
        ? context.l10n.roleCaptionSiteEngineer
        : user.isConsultant
        ? context.l10n.roleCaptionConsultantShort
        : context.l10n.roleLabel(user.role);
    final screenHeight = MediaQuery.sizeOf(context).height;
    final headerHeight = (screenHeight * .32).clamp(210.0, 260.0);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    return Scaffold(
      body: ListView(
        padding: EdgeInsets.zero,
        children: [
          Container(
            height: headerHeight,
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
                      AppSpacing.lg,
                      AppSpacing.page,
                      32,
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        Container(
                          width: 88,
                          height: 88,
                          decoration: BoxDecoration(
                            color: AppColors.accent,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 4),
                          ),
                          alignment: Alignment.center,
                          child: Text(
                            user.fullName.isEmpty
                                ? '?'
                                : user.fullName[0].toUpperCase(),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 34,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        const SizedBox(height: 13),
                        Text(
                          user.fullName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          role,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: AppColors.accentWash,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.page,
              AppSpacing.lg,
              AppSpacing.page,
              88 + bottomInset,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.profileAccountInformation,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: AppSpacing.sm),
                Card(
                  child: Column(
                    children: [
                      _ProfileTile(
                        icon: Icons.email_outlined,
                        title: context.l10n.profileEmail,
                        value: user.email,
                      ),
                      if (user.phoneNumber != null)
                        _ProfileTile(
                          icon: Icons.phone_outlined,
                          title: context.l10n.profilePhone,
                          value: user.phoneNumber!,
                        ),
                      if (user.discipline != null)
                        _ProfileTile(
                          icon: Icons.engineering_outlined,
                          title: context.l10n.commonDiscipline,
                          value: context.l10n.disciplineLabel(user.discipline),
                        ),
                      if (user.organization != null)
                        _ProfileTile(
                          icon: Icons.business_outlined,
                          title: context.l10n.profileOrganization,
                          value: user.organization!,
                        ),
                      _ProfileTile(
                        icon: Icons.verified_user_outlined,
                        title: context.l10n.profileAccountStatus,
                        value: context.l10n.statusLabel(user.status),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                Text(
                  context.l10n.profileLanguage,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 3),
                Text(
                  context.l10n.profileLanguageBody,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: AppSpacing.sm),
                const _LanguageCard(),
                const SizedBox(height: AppSpacing.xl),
                Text(
                  context.l10n.profileSecurity,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: AppSpacing.sm),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.lock_outline_rounded,
                          color: AppColors.stateVerified,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                context.l10n.profileSecureSession,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 3),
                              Text(
                                context.l10n.profileSecureSessionBody,
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: AppColors.mutedForeground,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.destructive,
                    side: const BorderSide(color: AppColors.destructive),
                  ),
                  onPressed: () async {
                    await ref
                        .read(projectContextProvider.notifier)
                        .clearForLogout();
                    await ref.read(sessionProvider.notifier).logout();
                  },
                  icon: const Icon(Icons.logout_rounded),
                  label: Text(context.l10n.commonLogOut),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileTile extends StatelessWidget {
  const _ProfileTile({
    required this.icon,
    required this.title,
    required this.value,
  });
  final IconData icon;
  final String title;
  final String value;
  @override
  Widget build(BuildContext context) => ListTile(
    leading: Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: AppColors.muted,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(icon, color: AppColors.primary, size: 20),
    ),
    title: Text(
      title,
      style: const TextStyle(fontSize: 11, color: AppColors.mutedForeground),
    ),
    subtitle: Text(
      value.replaceAll('_', ' '),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(
        fontWeight: FontWeight.w700,
        color: AppColors.foreground,
      ),
    ),
  );
}

/// The language chooser.
///
/// Three explicit options rather than a toggle, because "follow the device"
/// is a real third state: it is the default, and a user who has never chosen
/// should keep tracking their phone if they change its language later.
class _LanguageCard extends ConsumerWidget {
  const _LanguageCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(localeControllerProvider);
    final controller = ref.read(localeControllerProvider.notifier);
    final options = <(Locale?, String)>[
      (null, context.l10n.languageSystem),
      (const Locale('en'), context.l10n.languageEnglish),
      (const Locale('ar'), context.l10n.languageArabic),
    ];
    return Card(
      child: Column(
        children: [
          for (final (locale, label) in options)
            RadioListTile<String?>(
              value: locale?.languageCode,
              groupValue: state.override?.languageCode,
              onChanged: (_) => controller.select(locale),
              // A language name is written in its own script, so this one
              // label opts out of the surrounding text direction.
              title: Text(
                label,
                textDirection: locale?.languageCode == 'ar'
                    ? TextDirection.rtl
                    : locale == null
                    ? null
                    : TextDirection.ltr,
              ),
              dense: true,
            ),
        ],
      ),
    );
  }
}
