import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/auth/session_manager.dart';
import '../../core/auth/voice_access.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/async_views.dart';
import '../../core/l10n/l10n_formats.dart';
import '../../core/l10n/l10n_labels.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/record_update_control.dart';
import '../../models/voice_draft.dart';
import '../../models/task.dart';
import '../../services/voice_service.dart';
import '../projects/project_context_view_model.dart';
import 'voice_outcome.dart';
import 'voice_view_model.dart';

class VoiceScreen extends ConsumerStatefulWidget {
  const VoiceScreen({super.key, this.taskId});
  final String? taskId;

  @override
  ConsumerState<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends ConsumerState<VoiceScreen> {
  VoiceViewModel? _viewModel;
  final _manual = TextEditingController();
  Timer? _uiTimer;
  VoiceAnalysis? _analysis;
  String? _error;
  bool _analyzing = false;
  List<ProjectTask> _tasks = const [];
  String? _selectedTaskId;
  bool _loadingTasks = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final project = ref.read(projectContextProvider).selected;
    if (_viewModel == null && project != null) {
      _selectedTaskId = widget.taskId;
      _viewModel = VoiceViewModel(
        project.id,
        VoiceProcessingService(ref.read(apiClientProvider)),
      );
      _loadTasks(project.id);
    }
  }

  @override
  void dispose() {
    _uiTimer?.cancel();
    _viewModel?.dispose();
    _manual.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Voice is available to every normal system user and not to Admin. The
    // screen states that rather than 404-ing, because a route can be reached
    // by a deep link as well as by the navigation bar.
    if (!canUseVoice(ref.watch(sessionProvider).user)) {
      return Scaffold(
        appBar: AppBar(title: Text(context.l10n.voiceTitle)),
        body: MessageView(
          icon: Icons.mic_off_rounded,
          title: context.l10n.voiceUnavailableTitle,
          message: context.l10n.voiceUnavailableBody,
        ),
      );
    }
    final project = ref.watch(projectContextProvider).selected;
    if (project == null || _viewModel == null) {
      return Scaffold(
        appBar: AppBar(title: Text(context.l10n.voiceTitle)),
        body: MessageView(
          icon: Icons.apartment_rounded,
          title: context.l10n.commonNoProjectSelected,
          message: context.l10n.commonSelectProjectFirst,
        ),
      );
    }
    final viewModel = _viewModel!;
    return Scaffold(
      backgroundColor: AppColors.background,
      body: CustomScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        slivers: [
          SliverAppBar(
            pinned: true,
            expandedHeight: 176,
            backgroundColor: AppColors.primary,
            title: Text(context.l10n.voiceTitle),
            flexibleSpace: FlexibleSpaceBar(
              background: Stack(
                fit: StackFit.expand,
                children: [
                  const ColoredBox(color: AppColors.primary),
                  SafeArea(
                    child: Padding(
                      // Directional: the 54 clears the back button, which is
                      // on the leading edge — the right-hand side in Arabic.
                      // A physical `fromLTRB` put the gap on the wrong side
                      // and let the project name run under the button.
                      padding: const EdgeInsetsDirectional.fromSTEB(
                        54,
                        72,
                        20,
                        18,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Text(
                            project.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 19,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 5),
                          Text(
                            context.l10n.voiceSpeakNaturally,
                            style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.page,
              AppSpacing.lg,
              AppSpacing.page,
              40,
            ),
            sliver: SliverList.list(
              children: [
                if (widget.taskId == null) ...[
                  DropdownButtonFormField<String?>(
                    value: _selectedTaskId,
                    // Without `isExpanded` the selected task's code and name
                    // size the field to their own width, which overflowed by
                    // 6.1px once the Arabic label widened the decoration.
                    isExpanded: true,
                    decoration: InputDecoration(
                      labelText: context.l10n.voiceTaskContext,
                      prefixIcon: const Icon(Icons.task_alt_outlined),
                    ),
                    items: [
                      DropdownMenuItem<String?>(
                        value: null,
                        child: Text(
                          context.l10n.voiceLetAiSuggest,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      ..._tasks.map(
                        (task) => DropdownMenuItem<String?>(
                          value: task.id,
                          child: Text(
                            '${task.code} · ${task.name}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ],
                    onChanged: _loadingTasks
                        ? null
                        : (value) => setState(() => _selectedTaskId = value),
                  ),
                  const SizedBox(height: AppSpacing.md),
                ],
                Align(
                  alignment: Alignment.center,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 560),
                    child: _RecorderPanel(
                      status: viewModel.status,
                      duration: viewModel.duration,
                      samples: viewModel.amplitudeSamples,
                      isPlaying: viewModel.isPlaying,
                      playbackPosition: viewModel.playbackPosition,
                      playbackDuration: viewModel.playbackDuration,
                      onPrimary: _primaryRecordAction,
                      onSeek: viewModel.seek,
                      onPause: viewModel.status == VoiceDraftStatus.recording
                          ? () => _run(viewModel.pause)
                          : null,
                      onDelete:
                          viewModel.status == VoiceDraftStatus.recorded ||
                              viewModel.status == VoiceDraftStatus.ready ||
                              viewModel.status == VoiceDraftStatus.error
                          ? () => _run(viewModel.delete)
                          : null,
                      onRetry:
                          viewModel.status == VoiceDraftStatus.recorded ||
                              viewModel.status == VoiceDraftStatus.ready ||
                              viewModel.status == VoiceDraftStatus.error
                          ? _retry
                          : null,
                    ),
                  ),
                ),
                if (viewModel.status == VoiceDraftStatus.recorded) ...[
                  const SizedBox(height: AppSpacing.md),
                  FilledButton.icon(
                    onPressed: _analyzing ? null : _analyzeRecording,
                    icon: const Icon(Icons.auto_awesome_rounded),
                    label: Text(context.l10n.voiceSubmitForAnalysis),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(54),
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    context.l10n.voicePrivacyNote,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.mutedForeground,
                    ),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  Container(
                    padding: const EdgeInsets.all(13),
                    decoration: BoxDecoration(
                      color: AppColors.stateOverdueWash,
                      borderRadius: BorderRadius.circular(AppRadius.panel),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.error_outline_rounded,
                          color: AppColors.destructive,
                          size: 20,
                        ),
                        const SizedBox(width: 9),
                        Expanded(
                          child: Text(
                            _error!,
                            style: const TextStyle(
                              color: AppColors.destructive,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                if (_analysis?.completed == true) ...[
                  const SizedBox(height: AppSpacing.xl),
                  _AnalysisReviewCard(
                    analysis: _analysis!,
                    onCancel: _cancelTranscript,
                    onConfirm: _confirm,
                  ),
                ],
                if (_analysis?.needsClarification == true &&
                    _analysis!.clarifications.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.xl),
                  _ClarificationCard(
                    clarification: _analysis!.clarifications.first,
                    onAnswer: _answerClarification,
                    onCancel: _cancelTranscript,
                  ),
                ],
                if (_analysis?.failed == true) ...[
                  const SizedBox(height: AppSpacing.md),
                  OutlinedButton.icon(
                    onPressed: _retryAnalysis,
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(context.l10n.voiceRetryAudio),
                  ),
                ],
                const SizedBox(height: AppSpacing.xl),
                const _SafetyNotice(),
              ],
            ),
          ),
        ],
      ),
    );
  }



  Future<void> _primaryRecordAction() async {
    final viewModel = _viewModel!;
    switch (viewModel.status) {
      case VoiceDraftStatus.idle:
        await _run(viewModel.start);
        if (viewModel.status == VoiceDraftStatus.recording) {
          _startUiUpdates();
        }
      case VoiceDraftStatus.error:
        if (viewModel.path == null) {
          await _run(viewModel.start);
          if (viewModel.status == VoiceDraftStatus.recording) {
            _startUiUpdates();
          }
        } else {
          await _run(viewModel.play);
        }
      case VoiceDraftStatus.recording:
        await _run(viewModel.stop);
        _uiTimer?.cancel();
      case VoiceDraftStatus.paused:
        await _run(viewModel.resume);
        _startUiUpdates();
      case VoiceDraftStatus.recorded:
        await _run(viewModel.play);
        _startUiUpdates();
      case VoiceDraftStatus.ready:
        await _run(viewModel.play);
        _startUiUpdates();
      case VoiceDraftStatus.uploading:
      case VoiceDraftStatus.transcribing:
        break;
    }
  }

  Future<void> _analyzeRecording() async {
    final viewModel = _viewModel!;
    setState(() {
      _analyzing = true;
      _error = null;
    });
    // Captured before the await: the error handler must not touch
    // `context` across an async gap.
    final l10n = context.l10n;
    try {
      final result = await viewModel.analyze(
        taskId: _selectedTaskId,
        onChanged: () {
          if (mounted) setState(() {});
        },
      );
      _manual.text = result.rawTranscript ?? '';
      _analysis = result;
      _error = result.errorDetail;
    } catch (error) {
      _error = l10n.describeError(error);
    } finally {
      _analyzing = false;
    }
    if (mounted) setState(() {});
  }

  Future<void> _loadTasks(String projectId) async {
    setState(() => _loadingTasks = true);
    try {
      _tasks = await ref
          .read(taskRepositoryProvider)
          .list(projectId, assignedOnly: true);
    } catch (_) {
      _tasks = const [];
    } finally {
      _loadingTasks = false;
      if (mounted) setState(() {});
    }
  }

  void _startUiUpdates() {
    _uiTimer?.cancel();
    _uiTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (!mounted) return;
      setState(() {});
      final viewModel = _viewModel;
      if (viewModel != null &&
          viewModel.status != VoiceDraftStatus.recording &&
          !viewModel.isPlaying) {
        _uiTimer?.cancel();
      }
    });
  }

  Future<void> _retry() async {
    await _viewModel!.delete();
    if (mounted) setState(() {});
    await _primaryRecordAction();
  }

  Future<void> _retryAnalysis() async {
    // Captured before the await: the error handler must not touch
    // `context` across an async gap.
    final l10n = context.l10n;
    setState(() {
      _analyzing = true;
      _error = null;
    });
    try {
      final result = await _viewModel!.retryAnalysis(() {
        if (mounted) setState(() {});
      });
      _analysis = result;
      _manual.text = result.rawTranscript ?? '';
      _error = result.errorDetail;
    } catch (error) {
      _error = l10n.describeError(error);
    } finally {
      _analyzing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    // Captured before the await: the error handler must not touch `context`
    // across an async gap.
    final l10n = context.l10n;
    try {
      await action();
      _error = null;
    } catch (error) {
      _error = l10n.describeError(error);
    }
    if (mounted) setState(() {});
  }

  Future<void> _cancelTranscript() async {
    await _viewModel!.delete();
    _manual.clear();
    _analysis = null;
    _error = null;
    if (mounted) setState(() {});
  }

  Future<void> _confirm(List<VoiceDraftConfirmation> actions) async {
    // Captured before the await: the error handler must not touch
    // `context` across an async gap.
    final l10n = context.l10n;
    setState(() => _analyzing = true);
    try {
      final raw = await _viewModel!.confirm(actions);
      if (!mounted) return;
      // The backend's own per-action success flags are the only evidence of
      // execution. Nothing is inferred from the request having completed.
      final results = raw.map(VoiceActionOutcome.fromJson).toList();
      await showDialog<void>(
        context: context,
        builder: (context) => _OutcomeDialog(results: results),
      );
    } catch (error) {
      _error = l10n.describeError(error);
    } finally {
      _analyzing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _answerClarification(
    String clarificationId,
    String answer,
  ) async {
    // Captured before the await: the error handler must not touch
    // `context` across an async gap.
    final l10n = context.l10n;
    setState(() => _analyzing = true);
    try {
      final updated = await _viewModel!.answerClarification(
        clarificationId,
        answer,
      );
      if (!mounted) return;
      setState(() => _analysis = updated);
    } catch (error) {
      _error = l10n.describeError(error);
    } finally {
      _analyzing = false;
      if (mounted) setState(() {});
    }
  }
}

class _RecorderPanel extends StatelessWidget {
  const _RecorderPanel({
    required this.status,
    required this.duration,
    required this.samples,
    required this.isPlaying,
    required this.playbackPosition,
    required this.playbackDuration,
    required this.onPrimary,
    required this.onSeek,
    this.onPause,
    this.onDelete,
    this.onRetry,
  });
  final VoiceDraftStatus status;
  final Duration duration;
  final List<double> samples;
  final bool isPlaying;
  final Duration playbackPosition;
  final Duration playbackDuration;
  final VoidCallback onPrimary;
  final ValueChanged<Duration> onSeek;
  final VoidCallback? onPause;
  final VoidCallback? onDelete;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final controlState = switch (status) {
      VoiceDraftStatus.recording => RecordControlState.recording,
      VoiceDraftStatus.paused => RecordControlState.paused,
      VoiceDraftStatus.uploading ||
      VoiceDraftStatus.transcribing => RecordControlState.processing,
      VoiceDraftStatus.recorded || VoiceDraftStatus.ready =>
        isPlaying ? RecordControlState.playing : RecordControlState.completed,
      VoiceDraftStatus.error => RecordControlState.error,
      _ => RecordControlState.idle,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 28),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.panel),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          if (status == VoiceDraftStatus.uploading ||
              status == VoiceDraftStatus.transcribing) ...[
            _PipelineState(status: status),
            const SizedBox(height: 18),
          ],
          if (status == VoiceDraftStatus.recording ||
              status == VoiceDraftStatus.paused ||
              status == VoiceDraftStatus.recorded ||
              status == VoiceDraftStatus.ready ||
              status == VoiceDraftStatus.error) ...[
            _AudioWaveform(
              samples: samples,
              active: status == VoiceDraftStatus.recording,
            ),
            const SizedBox(height: 22),
          ],
          RecordUpdateControl(
            state: controlState,
            duration: duration,
            onPressed: onPrimary,
          ),
          if (status == VoiceDraftStatus.recorded ||
              status == VoiceDraftStatus.ready ||
              status == VoiceDraftStatus.error) ...[
            const SizedBox(height: 18),
            _PlaybackProgress(
              position: playbackPosition,
              duration: playbackDuration,
              onSeek: onSeek,
            ),
          ],
          if (onPause != null || onDelete != null || onRetry != null) ...[
            const SizedBox(height: 20),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.center,
              children: [
                if (onPause != null)
                  _SmallAction(
                    icon: Icons.pause_rounded,
                    label: context.l10n.voicePause,
                    onTap: onPause!,
                  ),
                if (onDelete != null)
                  _SmallAction(
                    icon: Icons.delete_outline_rounded,
                    label: context.l10n.voiceDelete,
                    onTap: onDelete!,
                  ),
                if (onRetry != null)
                  _SmallAction(
                    icon: Icons.replay_rounded,
                    label: context.l10n.voiceRecordAgain,
                    onTap: onRetry!,
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _PipelineState extends StatelessWidget {
  const _PipelineState({required this.status});
  final VoiceDraftStatus status;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(13),
    decoration: BoxDecoration(
      color: AppColors.stateProgressWash,
      borderRadius: BorderRadius.circular(AppRadius.panel),
    ),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2.5),
        ),
        const SizedBox(width: 10),
        Text(
          status == VoiceDraftStatus.uploading
              ? context.l10n.voiceUploading
              : context.l10n.voiceTranscribing,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ],
    ),
  );
}

class _AudioWaveform extends StatelessWidget {
  const _AudioWaveform({required this.samples, required this.active});
  final List<double> samples;
  final bool active;

  @override
  Widget build(BuildContext context) => Semantics(
    label: active
        ? context.l10n.voiceLiveWaveform
        : context.l10n.voiceRecordedWaveform,
    child: Container(
      width: double.infinity,
      height: 78,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: active ? AppColors.stateOverdueWash : AppColors.muted,
        borderRadius: BorderRadius.circular(AppRadius.panel),
      ),
      child: CustomPaint(
        painter: _WaveformPainter(samples: samples, active: active),
      ),
    ),
  );
}

class _WaveformPainter extends CustomPainter {
  const _WaveformPainter({required this.samples, required this.active});
  final List<double> samples;
  final bool active;

  @override
  void paint(Canvas canvas, Size size) {
    final barCount = (size.width / 6).floor().clamp(12, 72);
    final values = samples.length > barCount
        ? samples.sublist(samples.length - barCount)
        : samples;
    final paint = Paint()
      ..color = active ? AppColors.destructive : AppColors.primary
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final gap = size.width / barCount;
    final missing = barCount - values.length;
    for (var index = 0; index < barCount; index++) {
      final value = index < missing ? .04 : values[index - missing];
      final height = (8 + (size.height - 12) * value).clamp(8.0, size.height);
      final x = gap * index + gap / 2;
      canvas.drawLine(
        Offset(x, (size.height - height) / 2),
        Offset(x, (size.height + height) / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) => true;
}

class _PlaybackProgress extends StatelessWidget {
  const _PlaybackProgress({
    required this.position,
    required this.duration,
    required this.onSeek,
  });
  final Duration position;
  final Duration duration;
  final ValueChanged<Duration> onSeek;

  @override
  Widget build(BuildContext context) {
    final maximum = duration.inMilliseconds <= 0
        ? 1.0
        : duration.inMilliseconds.toDouble();
    final current = position.inMilliseconds.toDouble().clamp(0.0, maximum);
    return Column(
      children: [
        Slider(
          value: current,
          max: maximum,
          onChanged: (value) => onSeek(Duration(milliseconds: value.round())),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(context.formatClock(position)),
              Text(context.formatClock(duration)),
            ],
          ),
        ),
      ],
    );
  }
}

class _SmallAction extends StatelessWidget {
  const _SmallAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => ActionChip(
    avatar: Icon(icon, size: 17),
    label: Text(label),
    onPressed: onTap,
  );
}

class _ClarificationCard extends StatefulWidget {
  const _ClarificationCard({
    required this.clarification,
    required this.onAnswer,
    required this.onCancel,
  });

  final VoiceClarificationItem clarification;
  final Future<void> Function(String, String) onAnswer;
  final VoidCallback onCancel;

  @override
  State<_ClarificationCard> createState() => _ClarificationCardState();
}

class _ClarificationCardState extends State<_ClarificationCard> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(AppSpacing.lg),
    decoration: BoxDecoration(
      color: AppColors.stateReviewWash,
      borderRadius: BorderRadius.circular(AppRadius.panel),
      border: Border.all(color: AppColors.stateReview.withValues(alpha: .35)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Was three hardcoded Arabic literals plus a forced RTL direction, so
        // an English session got an Arabic card. The heading and the controls
        // come from the catalogue now; the *question* is content the server
        // produced in both languages, so each half keeps its own direction.
        Text(
          context.l10n.voiceClarificationTitle,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Text(
          widget.clarification.questionAr,
          textDirection: TextDirection.rtl,
          style: const TextStyle(fontSize: 16, height: 1.5),
        ),
        Text(
          widget.clarification.questionEn,
          textDirection: TextDirection.ltr,
          style: const TextStyle(color: AppColors.mutedForeground),
        ),
        if (widget.clarification.options.isNotEmpty) ...[
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: widget.clarification.options
                .map(
                  (option) => ActionChip(
                    label: Text('${option['label'] ?? option['value']}'),
                    onPressed: () =>
                        setState(() => _controller.text = '${option['value']}'),
                  ),
                )
                .toList(),
          ),
        ],
        const SizedBox(height: 12),
        TextField(
          controller: _controller,
          // No forced direction: the person answers in whichever language
          // they are working in, and the field follows the keyboard.
          keyboardType: widget.clarification.expectedAnswerType == 'NUMBER'
              ? TextInputType.number
              : TextInputType.text,
          decoration: InputDecoration(
            labelText: context.l10n.voiceClarificationAnswerLabel,
            hintText: context.l10n.voiceClarificationAnswerHint,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: widget.onCancel,
                child: Text(context.l10n.commonCancel),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: FilledButton(
                onPressed: () {
                  final answer = _controller.text.trim();
                  if (answer.isNotEmpty) {
                    widget.onAnswer(widget.clarification.id, answer);
                  }
                },
                child: Text(context.l10n.voiceContinue),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}

class _AnalysisReviewCard extends StatefulWidget {
  const _AnalysisReviewCard({
    required this.analysis,
    required this.onCancel,
    required this.onConfirm,
  });
  final VoiceAnalysis analysis;
  final VoidCallback onCancel;
  final Future<void> Function(List<VoiceDraftConfirmation>) onConfirm;

  @override
  State<_AnalysisReviewCard> createState() => _AnalysisReviewCardState();
}

/// The review list, keyed by draft id throughout.
///
/// Selection and edits used to be parallel `List`s indexed by position in
/// `result.suggestedActions`, built once in `initState` with `late final`.
/// Two consequences, both real:
///
///   * the state outlived the analysis it was built from — a retry or a
///     clarification answer replaces `widget.analysis`, but `initState` does
///     not run again for a reused `State`, so the lists described the *old*
///     analysis while the build method read the new one;
///   * positions were then handed to the confirm call, which used them to
///     subscript a *different* list (the server's drafts).
///
/// Maps keyed by `draft.id` remove both failure modes: an entry either
/// belongs to a draft that still exists or it is dropped, and nothing is ever
/// addressed by where it happens to sit. `didUpdateWidget` reconciles the
/// maps when the analysis is replaced.
class _AnalysisReviewCardState extends State<_AnalysisReviewCard> {
  final Map<String, bool> _selected = {};
  final Map<String, TextEditingController> _editors = {};
  bool _highRiskAcknowledged = false;

  List<VoiceActionDraftItem> get _drafts => widget.analysis.actionDrafts;

  @override
  void initState() {
    super.initState();
    _sync();
  }

  @override
  void didUpdateWidget(covariant _AnalysisReviewCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.analysis, widget.analysis)) _sync();
  }

  /// Brings the maps in line with the current drafts: new drafts default to
  /// selected, drafts that disappeared release their controller.
  void _sync() {
    final live = {for (final draft in _drafts) draft.id};
    for (final id in _editors.keys.toList()) {
      if (!live.contains(id)) _editors.remove(id)!.dispose();
    }
    _selected.removeWhere((id, _) => !live.contains(id));
    for (final draft in _drafts) {
      _selected.putIfAbsent(draft.id, () => true);
      _editors.putIfAbsent(
        draft.id,
        () => TextEditingController(text: _initialValue(draft)),
      );
    }
  }

  String _initialValue(VoiceActionDraftItem draft) {
    final payload = draft.userEditedPayload ?? draft.extractedPayload;
    final value = draft.actionType == 'UPDATE_TASK_PROGRESS'
        ? payload['progressPercentage']
        : payload['content'] ??
              payload['description'] ??
              payload['summaryText'];
    return value?.toString() ?? '';
  }

  /// The model's stated reason for a draft, matched by the server-supplied
  /// sequence rather than by list position.
  String? _reasonFor(VoiceActionDraftItem draft) {
    final suggestions = widget.analysis.result?.suggestedActions ?? const [];
    if (draft.sequence < 0 || draft.sequence >= suggestions.length) return null;
    final suggestion = suggestions[draft.sequence];
    // Only trust the pairing when the two agree on what the action is.
    return suggestion.type == draft.actionType ? suggestion.reason : null;
  }

  @override
  void dispose() {
    for (final editor in _editors.values) {
      editor.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final analysis = widget.analysis;
    final result = analysis.result!;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.panel),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome_rounded, color: AppColors.accent),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  context.l10n.voiceReviewUnderstood,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.voiceChooseActions,
            style: const TextStyle(
              color: AppColors.stateReview,
              fontWeight: FontWeight.w700,
            ),
          ),
          // The transcript and the summary are content, shown exactly as
          // produced; only the section labels around them are translated.
          _section(context.l10n.voiceTranscript, analysis.rawTranscript ?? ''),
          _section(context.l10n.voiceAiSummary, result.summary),
          _section(
            context.l10n.voiceTask,
            '${result.detectedTask['taskTitle'] ?? context.l10n.voiceSelectTask}',
          ),
          if (result.progress['mentioned'] == true)
            _section(
              context.l10n.voiceProgressLabel,
              context.l10n.voiceProgressMentioned(
                '${result.progress['percentage']}',
              ),
            ),
          if (result.workCompleted.isNotEmpty)
            _section(
              context.l10n.voiceWorkCompleted,
              result.workCompleted.join('\n• '),
            ),
          if (result.problems.isNotEmpty)
            _section(
              context.l10n.voiceProblems,
              result.problems
                  .map(
                    (problem) =>
                        '${problem['type']}: ${problem['description']}',
                  )
                  .join('\n'),
            ),
          const SizedBox(height: AppSpacing.lg),
          Text(
            context.l10n.voiceSuggestedActions,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: AppColors.mutedForeground,
              letterSpacing: .7,
            ),
          ),
          const SizedBox(height: 8),
          // Rendered from the *drafts*, because a draft is the thing that
          // actually executes. The model's suggestion list is used only for
          // the human-readable reason, paired by sequence.
          if (_drafts.isEmpty)
            Text(context.l10n.voiceNoSafeAction)
          else
            ..._drafts.map((draft) {
              final selected = _selected[draft.id] ?? false;
              final reason = _reasonFor(draft);
              return Card(
                // Keyed by draft id so Flutter never recycles one action's
                // field state onto another when the list changes.
                key: ValueKey(draft.id),
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: selected,
                        onChanged: (value) => setState(
                          () => _selected[draft.id] = value ?? false,
                        ),
                        title: Text(
                          context.l10n.voiceIntentLabel(draft.actionType),
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        subtitle: Text(
                          [
                            if (reason != null && reason.isNotEmpty) reason,
                            context.l10n.voiceConfidence(
                              (draft.confidence * 100).round(),
                            ),
                          ].join('\n'),
                        ),
                        controlAffinity: ListTileControlAffinity.leading,
                      ),
                      if (_editableDraft(draft))
                        TextField(
                          controller: _editors[draft.id],
                          enabled: selected,
                          keyboardType:
                              draft.actionType == 'UPDATE_TASK_PROGRESS'
                              ? TextInputType.number
                              : TextInputType.multiline,
                          maxLines: draft.actionType == 'UPDATE_TASK_PROGRESS'
                              ? 1
                              : 3,
                          decoration: InputDecoration(
                            labelText:
                                draft.actionType == 'UPDATE_TASK_PROGRESS'
                                ? context.l10n.voiceConfirmedProgress
                                : context.l10n.voiceReviewEditValue,
                          ),
                        ),
                    ],
                  ),
                ),
              );
            }),
          if (_hasSelectedHighRisk)
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _highRiskAcknowledged,
              onChanged: (value) =>
                  setState(() => _highRiskAcknowledged = value ?? false),
              title: Text(context.l10n.voiceReviewedAffected),
            ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: widget.onCancel,
                  child: Text(context.l10n.voiceDiscard),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton(
                  onPressed:
                      _selectedDrafts.isNotEmpty &&
                          (!_hasSelectedHighRisk || _highRiskAcknowledged)
                      ? () => widget.onConfirm(_confirmedActions())
                      : null,
                  child: Text(context.l10n.voiceConfirmSelected),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _section(String title, String value) => Padding(
    padding: const EdgeInsets.only(top: AppSpacing.lg),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w800,
            color: AppColors.mutedForeground,
            letterSpacing: .7,
          ),
        ),
        const SizedBox(height: 5),
        Text(value, style: const TextStyle(height: 1.45)),
      ],
    ),
  );

  /// Which selected drafts exist, in the server's own order.
  List<VoiceActionDraftItem> get _selectedDrafts =>
      [for (final draft in _drafts) if (_selected[draft.id] ?? false) draft];

  bool get _hasSelectedHighRisk =>
      _selectedDrafts.any((draft) => draft.riskLevel == 'HIGH');

  bool _editableDraft(VoiceActionDraftItem draft) {
    final payload = draft.userEditedPayload ?? draft.extractedPayload;
    return draft.actionType == 'UPDATE_TASK_PROGRESS' ||
        payload.containsKey('content') ||
        payload.containsKey('description') ||
        payload.containsKey('summaryText');
  }

  /// The confirmation request: one entry per selected draft, addressed by
  /// draft id. No positions cross this boundary.
  List<VoiceDraftConfirmation> _confirmedActions() => [
    for (final draft in _selectedDrafts)
      VoiceDraftConfirmation(
        draftId: draft.id,
        targetId: draft.targetEntityId,
        payload: _editedPayload(draft, _editors[draft.id]?.text ?? ''),
      ),
  ];

  /// The draft's payload with the one user-editable value applied.
  ///
  /// Starts from the draft's own payload — never from another action's — so
  /// an edit cannot carry fields across actions.
  Map<String, dynamic> _editedPayload(
    VoiceActionDraftItem draft,
    String value,
  ) {
    final payload = Map<String, dynamic>.from(
      draft.userEditedPayload ?? draft.extractedPayload,
    );
    if (draft.actionType == 'UPDATE_TASK_PROGRESS') {
      payload['progressPercentage'] = double.tryParse(value);
    } else if (payload.containsKey('content')) {
      payload['content'] = value.trim();
    } else if (payload.containsKey('description')) {
      payload['description'] = value.trim();
    } else if (payload.containsKey('summaryText')) {
      payload['summaryText'] = value.trim();
    }
    return payload;
  }
}

class _SafetyNotice extends StatelessWidget {
  const _SafetyNotice();
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(
      color: AppColors.stateVerifiedWash,
      borderRadius: BorderRadius.circular(AppRadius.panel),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.shield_outlined, color: AppColors.stateVerified),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            context.l10n.voicePrivacyNote,
            style: const TextStyle(fontSize: 12, height: 1.45),
          ),
        ),
      ],
    ),
  );
}

/// The result of a confirmation, stated honestly.
///
/// The affirmative treatment — verified shield, verdant tone — is bound to
/// [VoiceOutcome.isAffirmative], which is true only when every confirmed
/// action actually executed. A partial run is amber and a total failure is
/// red, and both list what did not happen and why. The previous dialog used
/// the green shield unconditionally.
class _OutcomeDialog extends StatelessWidget {
  const _OutcomeDialog({required this.results});

  final List<VoiceActionOutcome> results;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final outcome = VoiceOutcome.of(results);
    final (icon, tone) = switch (outcome) {
      VoiceOutcome.success => (
        Icons.verified_user_outlined,
        AppColors.stateVerified,
      ),
      VoiceOutcome.partial => (
        Icons.warning_amber_rounded,
        AppColors.stateReview,
      ),
      VoiceOutcome.failure => (
        Icons.error_outline_rounded,
        AppColors.destructive,
      ),
      VoiceOutcome.nothing => (
        Icons.info_outline_rounded,
        AppColors.stateProgress,
      ),
    };
    final succeeded = results.where((item) => item.succeeded).length;

    return AlertDialog(
      icon: Icon(icon, color: tone),
      title: Text(outcome.title(l10n), textAlign: TextAlign.center),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (outcome == VoiceOutcome.nothing)
              Text(l10n.voiceOutcomeNothingBody)
            else ...[
              Text(
                l10n.voiceActionsSucceeded(succeeded, results.length),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: AppSpacing.sm),
              for (final result in results)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _OutcomeRow(result: result),
                ),
            ],
          ],
        ),
      ),
      actions: [
        FilledButton(
          onPressed: () => Navigator.pop(context),
          child: Text(context.l10n.commonDone),
        ),
      ],
    );
  }
}

/// One action and what became of it.
class _OutcomeRow extends StatelessWidget {
  const _OutcomeRow({required this.result});

  final VoiceActionOutcome result;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final tone = result.succeeded
        ? AppColors.stateVerified
        : AppColors.destructive;
    final reason = result.reason(l10n);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          result.succeeded
              ? Icons.check_circle_outline_rounded
              : Icons.cancel_outlined,
          size: 18,
          color: tone,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                result.label(l10n),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              Text(
                result.succeeded
                    ? l10n.voiceOutcomeExecuted
                    : l10n.voiceOutcomeNotExecuted,
                style: TextStyle(color: tone, fontSize: 12),
              ),
              if (reason != null) ...[
                const SizedBox(height: 2),
                Text(
                  '${l10n.voiceOutcomeReason}: $reason',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
