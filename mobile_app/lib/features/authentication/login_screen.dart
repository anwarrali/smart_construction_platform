import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/network/network_exceptions.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_shadows.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/brand_mark.dart';
import '../../core/l10n/l10n_labels.dart';

/// Whether a sign-in failure means "the server was never reached", as opposed
/// to "the server answered and said no".
bool _isConnectionFailure(Object? error) =>
    error is NetworkException &&
    (error.failure == NetworkFailure.offline ||
        error.failure == NetworkFailure.timeout);

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _identity = TextEditingController();
  final _password = TextEditingController();
  final _passwordFocus = FocusNode();
  bool _obscure = true;

  @override
  void dispose() {
    _identity.dispose();
    _password.dispose();
    _passwordFocus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final loading = session.status == SessionStatus.authenticating;
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      backgroundColor: AppColors.primary,
      body: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.only(bottom: keyboard),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: constraints.maxHeight),
            child: Column(
              children: [
                _BrandHeader(compact: constraints.maxHeight < 680),
                Transform.translate(
                  offset: const Offset(0, -26),
                  child: Container(
                    width: double.infinity,
                    constraints: BoxConstraints(
                      minHeight: constraints.maxHeight * .58,
                    ),
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.xl,
                      30,
                      AppSpacing.xl,
                      AppSpacing.xl,
                    ),
                    decoration: const BoxDecoration(
                      color: AppColors.background,
                      borderRadius: BorderRadius.vertical(
                        top: Radius.circular(AppRadius.sheet),
                      ),
                      boxShadow: AppShadows.elevated,
                    ),
                    child: AutofillGroup(
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              context.l10n.loginSignIn,
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 5),
                            Text(
                              context.l10n.loginSubtitle,
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                            const SizedBox(height: AppSpacing.xl),
                            TextFormField(
                              controller: _identity,
                              autofillHints: const [
                                AutofillHints.username,
                                AutofillHints.email,
                              ],
                              keyboardType: TextInputType.emailAddress,
                              textInputAction: TextInputAction.next,
                              onFieldSubmitted: (_) =>
                                  _passwordFocus.requestFocus(),
                              decoration: InputDecoration(
                                labelText: context.l10n.loginEmailLabel,
                                hintText: context.l10n.loginEmailHint,
                                prefixIcon: const Icon(
                                  Icons.person_outline_rounded,
                                ),
                              ),
                              validator: (value) =>
                                  value == null || value.trim().isEmpty
                                  ? context.l10n.validationEnterEmailOrUsername
                                  : null,
                            ),
                            const SizedBox(height: AppSpacing.md),
                            TextFormField(
                              controller: _password,
                              focusNode: _passwordFocus,
                              autofillHints: const [AutofillHints.password],
                              obscureText: _obscure,
                              textInputAction: TextInputAction.done,
                              onFieldSubmitted: (_) =>
                                  loading ? null : _submit(),
                              decoration: InputDecoration(
                                labelText: context.l10n.loginPasswordLabel,
                                hintText: context.l10n.loginPasswordHint,
                                prefixIcon: const Icon(
                                  Icons.lock_outline_rounded,
                                ),
                                suffixIcon: IconButton(
                                  tooltip: _obscure
                                      ? context.l10n.loginShowPassword
                                      : context.l10n.loginHidePassword,
                                  onPressed: () =>
                                      setState(() => _obscure = !_obscure),
                                  icon: Icon(
                                    _obscure
                                        ? Icons.visibility_outlined
                                        : Icons.visibility_off_outlined,
                                  ),
                                ),
                              ),
                              validator: (value) =>
                                  value == null || value.isEmpty
                                  ? context.l10n.validationEnterPassword
                                  : null,
                            ),
                            if (session.error != null) ...[
                              const SizedBox(height: AppSpacing.md),
                              Container(
                                width: double.infinity,
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: AppColors.stateOverdueWash,
                                  borderRadius: BorderRadius.circular(
                                    AppRadius.control,
                                  ),
                                ),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Icon(
                                      Icons.error_outline,
                                      color: AppColors.destructive,
                                      size: 20,
                                    ),
                                    const SizedBox(width: 9),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            context.l10n.describeLoginError(
                                              session.error,
                                            ),
                                            style: const TextStyle(
                                              color: AppColors.destructive,
                                              fontSize: 13,
                                            ),
                                          ),
                                          // "Check the server is running and
                                          // you are on the right network" is
                                          // sound advice that cannot be acted
                                          // on without knowing *which* server
                                          // was called. A stale LAN address
                                          // baked into the build looks exactly
                                          // like a wrong password from here,
                                          // and that cost a real debugging
                                          // session on a real phone. The
                                          // address is shown only when the
                                          // failure is actually a connection
                                          // failure, so an ordinary bad
                                          // password does not put
                                          // infrastructure detail on screen.
                                          if (_isConnectionFailure(
                                            session.error,
                                          ))
                                            Padding(
                                              padding: const EdgeInsets.only(
                                                top: 6,
                                              ),
                                              child: Text(
                                                ref
                                                    .read(configProvider)
                                                    .apiBaseUrl,
                                                textDirection:
                                                    TextDirection.ltr,
                                                style: AppTheme.measured
                                                    .copyWith(
                                                      color: AppColors
                                                          .destructive,
                                                      fontSize: 11.5,
                                                    ),
                                              ),
                                            ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: AppSpacing.xl),
                            FilledButton(
                              onPressed: loading ? null : _submit,
                              child: loading
                                  ? const SizedBox.square(
                                      dimension: 22,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2.4,
                                        color: Colors.white,
                                      ),
                                    )
                                  : Row(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Text(context.l10n.loginSubmit),
                                        const SizedBox(width: 8),
                                        const Icon(
                                          Icons.arrow_forward_rounded,
                                          size: 19,
                                        ),
                                      ],
                                    ),
                            ),
                            const SizedBox(height: AppSpacing.md),
                            Center(
                              child: TextButton.icon(
                                onPressed: loading
                                    ? null
                                    : () => context.push('/contact-admin'),
                                icon: const Icon(
                                  Icons.support_agent_rounded,
                                  size: 20,
                                ),
                                label: Text(context.l10n.loginNeedHelp),
                              ),
                            ),
                            const SizedBox(height: AppSpacing.sm),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(
                                  Icons.lock_rounded,
                                  size: 13,
                                  color: AppColors.mutedForeground,
                                ),
                                const SizedBox(width: 5),
                                Flexible(
                                  child: Text(
                                    context.l10n.loginSecureAccess,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      color: AppColors.mutedForeground,
                                      fontSize: 11,
                                    ),
                                  ),
                                ),
                              ],
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
      ),
    );
  }

  Future<void> _submit() async {
    FocusManager.instance.primaryFocus?.unfocus();
    if (!_formKey.currentState!.validate()) return;
    await ref
        .read(sessionProvider.notifier)
        .login(_identity.text, _password.text);
  }
}

class _BrandHeader extends StatelessWidget {
  const _BrandHeader({required this.compact});
  final bool compact;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: compact ? 280 : 330,
    child: Stack(
      fit: StackFit.expand,
      children: [
        const ColoredBox(color: AppColors.primary),
        SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl,
              AppSpacing.lg,
              AppSpacing.xl,
              52,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                // The sign-in lockup is the shared brand component, so this
                // screen cannot drift from the splash and app bar the way the
                // hand-rolled title it replaced did — that copy survived the
                // first rename purely because its casing differed.
                const StructIQLogo(size: 30, inverted: true, showDescriptor: true),
                SizedBox(height: compact ? 28 : 42),
                Text(
                  context.l10n.loginWelcomeBack,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 31,
                    height: 1.05,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -.6,
                  ),
                ),
                const SizedBox(height: 9),
                Text(
                  context.l10n.loginWelcomeBody,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    height: 1.45,
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
