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
    this.onHoldStart,
    this.onHoldEnd,
  });

  final RecordControlState state;
  final VoidCallback? onPressed;
  final Duration? duration;
  final bool compact;

  /// Press-and-hold recording, WhatsApp style: hold to talk, release to send.
  ///
  /// Optional because it is a phone gesture. Where these are null the control
  /// keeps its tap-to-start / tap-to-stop behaviour, which is what the web
  /// build uses — a browser tab can lose a pointer-up to a dropped pointer
  /// capture or a tab switch, and a recording that never stops is worse than
  /// one that takes two taps.
  final VoidCallback? onHoldStart;
  final VoidCallback? onHoldEnd;

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
          _pressable(
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

  /// Hold-to-talk when the caller supplied hold callbacks, tap otherwise.
  ///
  /// `onTapDown`/`onTapUp` rather than a long-press: a long press waits half a
  /// second before firing, and half a second of an engineer already talking is
  /// half a sentence missing from the recording. `onTapCancel` is treated as a
  /// release so a finger that slides off the button still ends the recording
  /// rather than leaving the microphone open.
  Widget _pressable({required Widget child}) {
    final busy = state == RecordControlState.processing;
    final holdToTalk = onHoldStart != null && onHoldEnd != null;
    if (!holdToTalk) {
      return InkWell(
        customBorder: const CircleBorder(),
        onTap: busy ? null : onPressed,
        child: child,
      );
    }
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: busy ? null : (_) => onHoldStart!(),
      onTapUp: busy ? null : (_) => onHoldEnd!(),
      onTapCancel: busy ? null : onHoldEnd,
      child: child,
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
