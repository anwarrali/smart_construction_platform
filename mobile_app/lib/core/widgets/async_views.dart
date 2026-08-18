import 'package:flutter/material.dart';
import '../l10n/l10n_labels.dart';
import '../theme/app_colors.dart';
import '../theme/app_radius.dart';

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label});

  /// A specific label such as "Loading tasks"; falls back to the generic
  /// translated one. It cannot default to a literal in the constructor
  /// because a const default cannot be locale-aware.
  final String? label;

  @override
  Widget build(BuildContext context) {
    final text = label ?? context.l10n.commonLoading;
    return Center(
    child: Semantics(
      label: text,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox.square(
            dimension: 36,
            child: CircularProgressIndicator(strokeWidth: 3),
          ),
          const SizedBox(height: 14),
          Text(text, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    ),
  );
  }
}

class MessageView extends StatelessWidget {
  const MessageView({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
  });
  final IconData icon;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 70,
            height: 70,
            decoration: BoxDecoration(
              color: AppColors.accentWash,
              borderRadius: BorderRadius.circular(AppRadius.panel),
            ),
            child: Icon(icon, size: 34, color: AppColors.accent),
          ),
          const SizedBox(height: 16),
          Text(
            title,
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(message, textAlign: TextAlign.center),
          if (onAction != null) ...[
            const SizedBox(height: 20),
            FilledButton.tonal(
              onPressed: onAction,
              // Was a literal 'Retry', which stayed English in an Arabic
              // session. It sat outside `Text('…')` so the hardcoded-copy
              // test never saw it.
              child: Text(actionLabel ?? context.l10n.commonRetry),
            ),
          ],
        ],
      ),
    ),
  );
}
