import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_shadows.dart';
import '../l10n/l10n_formats.dart';
import '../l10n/l10n_labels.dart';

enum RecordControlState {
  idle,
  recording,
  paused,
  processing,
  completed,
  playing,
  error,
}

class RecordUpdateControl extends StatelessWidget {
  const RecordUpdateControl({
    super.key,
    required this.state,
    required this.onPressed,
    this.duration,
    this.compact = false,
  });

  final RecordControlState state;
  final VoidCallback? onPressed;
  final Duration? duration;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final active = state == RecordControlState.recording;
    final tone = active
        ? AppColors.destructive
        : state == RecordControlState.error
        ? AppColors.stateReview
        : AppColors.accent;
    final icon = switch (state) {
      RecordControlState.recording => Icons.stop_rounded,
      RecordControlState.paused => Icons.play_arrow_rounded,
      RecordControlState.processing => Icons.sync_rounded,
      RecordControlState.completed => Icons.play_arrow_rounded,
      RecordControlState.playing => Icons.pause_rounded,
      RecordControlState.error => Icons.replay_rounded,
      RecordControlState.idle => Icons.mic_rounded,
    };
    final label = switch (state) {
      RecordControlState.recording => context.l10n.recordStop,
      RecordControlState.paused => context.l10n.recordResume,
      RecordControlState.processing => context.l10n.recordProcessing,
      RecordControlState.completed => context.l10n.recordPlay,
      RecordControlState.playing => context.l10n.recordPausePlayback,
      RecordControlState.error => context.l10n.recordTryAgain,
      RecordControlState.idle => context.l10n.navRecordUpdate,
    };
    final size = compact ? 64.0 : 92.0;
    return Semantics(
      button: true,
      label: label,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            customBorder: const CircleBorder(),
            onTap: state == RecordControlState.processing ? null : onPressed,
            child: Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: tone,
                border: Border.all(color: Colors.white, width: compact ? 4 : 6),
                boxShadow: [
                  ...AppShadows.elevated,
                  BoxShadow(
                    color: tone.withValues(alpha: .25),
                    blurRadius: active ? 28 : 18,
                    spreadRadius: active ? 4 : 0,
                  ),
                ],
              ),
              child: state == RecordControlState.processing
                  ? const Padding(
                      padding: EdgeInsets.all(22),
                      child: CircularProgressIndicator(
                        color: Colors.white,
                        strokeWidth: 3,
                      ),
                    )
                  : Icon(icon, color: Colors.white, size: compact ? 30 : 42),
            ),
          ),
          if (!compact) ...[
            const SizedBox(height: 12),
            Text(label, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 3),
            Text(
              duration == null
                  ? context.l10n.recordCapture
                  // Shared clock formatting, so the recorder and the playback
                  // transport cannot drift apart.
                  : context.formatClock(duration!),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }

}

class RecordUpdateCard extends StatelessWidget {
  const RecordUpdateCard({super.key, required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      border: Border.all(color: AppColors.border),
      boxShadow: AppShadows.card,
    ),
    child: Column(
      children: [
        RecordUpdateControl(
          state: RecordControlState.idle,
          onPressed: onPressed,
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: AppColors.muted,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.shield_outlined,
                size: 16,
                color: AppColors.stateVerified,
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  context.l10n.recordReviewHint,
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}
