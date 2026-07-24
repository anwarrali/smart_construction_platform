import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_radius.dart';
import '../theme/app_shadows.dart';

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
        ? AppColors.danger
        : state == RecordControlState.error
        ? AppColors.warning
        : AppColors.bronze;
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
      RecordControlState.recording => 'Stop recording',
      RecordControlState.paused => 'Resume recording',
      RecordControlState.processing => 'Processing…',
      RecordControlState.completed => 'Play recording',
      RecordControlState.playing => 'Pause playback',
      RecordControlState.error => 'Try again',
      RecordControlState.idle => 'Record Update',
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
                  ? 'Capture a hands-free field update'
                  : _duration(duration!),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }

  String _duration(Duration value) =>
      '${value.inMinutes.toString().padLeft(2, '0')}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';
}

class RecordUpdateCard extends StatelessWidget {
  const RecordUpdateCard({super.key, required this.onPressed});
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(AppRadius.large),
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
            color: AppColors.surfaceMuted,
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.shield_outlined, size: 16, color: AppColors.success),
              SizedBox(width: 6),
              Flexible(
                child: Text(
                  'You review every proposal before submission',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}
