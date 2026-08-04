import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/dependency_injection.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_radius.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/widgets/record_update_control.dart';
import '../../models/voice_draft.dart';
import '../../models/task.dart';
import '../../services/voice_service.dart';
import '../projects/project_context_view_model.dart';
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
    final project = ref.watch(projectContextProvider).selected;
    if (project == null || _viewModel == null) {
      return const Scaffold(
        body: Center(child: Text('Select a project first.')),
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
            backgroundColor: AppColors.navy,
            title: const Text('Construction Voice Assistant'),
            flexibleSpace: FlexibleSpaceBar(
              background: Stack(
                fit: StackFit.expand,
                children: [
                  const ColoredBox(color: AppColors.navy),
                  SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(54, 72, 20, 18),
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
                          const Text(
                            'Speak naturally about work, issues, or project updates.',
                            style: TextStyle(
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
                    decoration: const InputDecoration(
                      labelText: 'Task context (recommended)',
                      prefixIcon: Icon(Icons.task_alt_outlined),
                    ),
                    items: [
                      const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('Let AI suggest an assigned task'),
                      ),
                      ..._tasks.map(
                        (task) => DropdownMenuItem<String?>(
                          value: task.id,
                          child: Text('${task.code} · ${task.name}'),
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
                    label: const Text('Submit for AI analysis'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(54),
                    ),
                  ),
                  const SizedBox(height: 7),
                  const Text(
                    'Your recording is used to prepare this project action and is stored according to the project data policy.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
                if (_error != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  Container(
                    padding: const EdgeInsets.all(13),
                    decoration: BoxDecoration(
                      color: AppColors.dangerSoft,
                      borderRadius: BorderRadius.circular(AppRadius.medium),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.error_outline_rounded,
                          color: AppColors.danger,
                          size: 20,
                        ),
                        const SizedBox(width: 9),
                        Expanded(
                          child: Text(
                            _error!,
                            style: const TextStyle(
                              color: AppColors.danger,
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
                    label: const Text('Retry retained audio'),
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

  static String _labelIntent(String intent) {
    final words = intent.toLowerCase().split('_');
    return words
        .map(
          (word) => word.isEmpty
              ? word
              : '${word[0].toUpperCase()}${word.substring(1)}',
        )
        .join(' ');
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
      _error = error.toString().replaceFirst('Bad state: ', '');
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
      _error = '$error';
    } finally {
      _analyzing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _run(Future<void> Function() action) async {
    try {
      await action();
      _error = null;
    } catch (error) {
      _error = error.toString().replaceFirst('Bad state: ', '');
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

  Future<void> _confirm(List<Map<String, dynamic>> actions) async {
    setState(() => _analyzing = true);
    try {
      final results = await _viewModel!.confirm(actions);
      if (!mounted) return;
      final succeeded = results.where((item) => item['success'] == true).length;
      final workerReport = results.any(
        (item) =>
            item['type'] == 'CREATE_FIELD_SUBMISSION' &&
            item['success'] == true,
      );
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          icon: const Icon(
            Icons.verified_user_outlined,
            color: AppColors.success,
          ),
          title: Text(workerReport ? 'Report sent' : 'Action completed'),
          content: Text(
            workerReport
                ? 'Your report was sent to the responsible engineer for review.'
                : '$succeeded of ${results.length} selected actions succeeded.\n\n'
                      '${results.map((item) => '• ${item['message']}').join('\n')}',
            textDirection: TextDirection.ltr,
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } catch (error) {
      _error = '$error';
    } finally {
      _analyzing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _answerClarification(
    String clarificationId,
    String answer,
  ) async {
    setState(() => _analyzing = true);
    try {
      final updated = await _viewModel!.answerClarification(
        clarificationId,
        answer,
      );
      if (!mounted) return;
      setState(() => _analysis = updated);
    } catch (error) {
      _error = '$error';
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
        borderRadius: BorderRadius.circular(AppRadius.large),
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
                    label: 'Pause',
                    onTap: onPause!,
                  ),
                if (onDelete != null)
                  _SmallAction(
                    icon: Icons.delete_outline_rounded,
                    label: 'Delete',
                    onTap: onDelete!,
                  ),
                if (onRetry != null)
                  _SmallAction(
                    icon: Icons.replay_rounded,
                    label: 'Record again',
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
      color: AppColors.infoSoft,
      borderRadius: BorderRadius.circular(AppRadius.medium),
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
              ? 'Uploading recording securely…'
              : 'Transcribing speech…',
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
    label: active ? 'Live recording waveform' : 'Recorded audio waveform',
    child: Container(
      width: double.infinity,
      height: 78,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: active ? AppColors.dangerSoft : AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppRadius.medium),
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
      ..color = active ? AppColors.danger : AppColors.navy
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
            children: [Text(_audioTime(position)), Text(_audioTime(duration))],
          ),
        ),
      ],
    );
  }
}

String _audioTime(Duration value) =>
    '${value.inMinutes.toString().padLeft(2, '0')}:${(value.inSeconds % 60).toString().padLeft(2, '0')}';

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
      color: AppColors.warningSoft,
      borderRadius: BorderRadius.circular(AppRadius.large),
      border: Border.all(color: AppColors.warning.withValues(alpha: .35)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          'معلومة إضافية مطلوبة',
          textDirection: TextDirection.rtl,
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Text(
          widget.clarification.questionAr,
          textDirection: TextDirection.rtl,
          style: const TextStyle(fontSize: 16, height: 1.5),
        ),
        Text(
          widget.clarification.questionEn,
          style: const TextStyle(color: AppColors.textSecondary),
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
          textDirection: TextDirection.rtl,
          keyboardType: widget.clarification.expectedAnswerType == 'NUMBER'
              ? TextInputType.number
              : TextInputType.text,
          decoration: const InputDecoration(
            labelText: 'الإجابة',
            hintText: 'اكتب إجابة قصيرة ومحددة',
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: widget.onCancel,
                child: const Text('إلغاء'),
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
                child: const Text('متابعة'),
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
  final Future<void> Function(List<Map<String, dynamic>>) onConfirm;

  @override
  State<_AnalysisReviewCard> createState() => _AnalysisReviewCardState();
}

class _AnalysisReviewCardState extends State<_AnalysisReviewCard> {
  late final List<bool> _selected;
  late final List<TextEditingController> _editors;
  bool _highRiskAcknowledged = false;

  @override
  void initState() {
    super.initState();
    final actions = widget.analysis.result!.suggestedActions;
    _selected = List<bool>.filled(actions.length, true);
    _editors = actions.map((action) {
      final value = action.type == 'UPDATE_TASK_PROGRESS'
          ? action.payload['progressPercentage']
          : action.payload['content'] ??
                action.payload['description'] ??
                action.payload['summaryText'];
      return TextEditingController(text: value?.toString() ?? '');
    }).toList();
  }

  @override
  void dispose() {
    for (final editor in _editors) {
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
        borderRadius: BorderRadius.circular(AppRadius.large),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.auto_awesome_rounded, color: AppColors.bronze),
              SizedBox(width: 9),
              Expanded(
                child: Text(
                  'Review what I understood',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Choose and edit the actions you want to confirm.',
            style: TextStyle(
              color: AppColors.warning,
              fontWeight: FontWeight.w700,
            ),
          ),
          _section('TRANSCRIPT', analysis.rawTranscript ?? ''),
          _section('AI SUMMARY', result.summary),
          _section(
            'TASK',
            '${result.detectedTask['taskTitle'] ?? 'Select a task'}',
          ),
          if (result.progress['mentioned'] == true)
            _section(
              'PROGRESS',
              '${result.progress['percentage']}% mentioned — not yet official',
            ),
          if (result.workCompleted.isNotEmpty)
            _section('WORK COMPLETED', result.workCompleted.join('\n• ')),
          if (result.problems.isNotEmpty)
            _section(
              'PROBLEMS / BLOCKERS',
              result.problems
                  .map(
                    (problem) =>
                        '${problem['type']}: ${problem['description']}',
                  )
                  .join('\n'),
            ),
          const SizedBox(height: AppSpacing.lg),
          const Text(
            'SUGGESTED ACTIONS',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: AppColors.textSecondary,
              letterSpacing: .7,
            ),
          ),
          const SizedBox(height: 8),
          if (result.suggestedActions.isEmpty)
            const Text('No safe executable action was suggested.')
          else
            ...List.generate(result.suggestedActions.length, (index) {
              final action = result.suggestedActions[index];
              return Card(
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: _selected[index],
                        onChanged: (value) =>
                            setState(() => _selected[index] = value ?? false),
                        title: Text(
                          _VoiceScreenState._labelIntent(action.type),
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        subtitle: Text(
                          '${action.reason}\n${(action.confidence * 100).round()}% confidence',
                        ),
                        controlAffinity: ListTileControlAffinity.leading,
                      ),
                      if (_editable(action))
                        TextField(
                          controller: _editors[index],
                          enabled: _selected[index],
                          keyboardType: action.type == 'UPDATE_TASK_PROGRESS'
                              ? TextInputType.number
                              : TextInputType.multiline,
                          maxLines: action.type == 'UPDATE_TASK_PROGRESS'
                              ? 1
                              : 3,
                          decoration: InputDecoration(
                            labelText: action.type == 'UPDATE_TASK_PROGRESS'
                                ? 'Confirmed progress (0–100)'
                                : 'Review/edit value',
                          ),
                        ),
                    ],
                  ),
                ),
              );
            }),
          if (_selected.asMap().entries.any(
            (entry) =>
                entry.value &&
                entry.key < analysis.actionDrafts.length &&
                analysis.actionDrafts[entry.key].riskLevel == 'HIGH',
          ))
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: _highRiskAcknowledged,
              onChanged: (value) =>
                  setState(() => _highRiskAcknowledged = value ?? false),
              title: const Text(
                'I reviewed the affected task, recipients, and workflow impact.',
              ),
            ),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: widget.onCancel,
                  child: const Text('Discard'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: FilledButton(
                  onPressed:
                      _selected.any((value) => value) &&
                          (!_selected.asMap().entries.any(
                                (entry) =>
                                    entry.value &&
                                    entry.key < analysis.actionDrafts.length &&
                                    analysis
                                            .actionDrafts[entry.key]
                                            .riskLevel ==
                                        'HIGH',
                              ) ||
                              _highRiskAcknowledged)
                      ? () => widget.onConfirm(_confirmedActions())
                      : null,
                  child: const Text('Confirm selected'),
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
            color: AppColors.textSecondary,
            letterSpacing: .7,
          ),
        ),
        const SizedBox(height: 5),
        Text(value, style: const TextStyle(height: 1.45)),
      ],
    ),
  );

  bool _editable(VoiceSuggestedAction action) =>
      action.type == 'UPDATE_TASK_PROGRESS' ||
      action.payload.containsKey('content') ||
      action.payload.containsKey('description') ||
      action.payload.containsKey('summaryText');

  List<Map<String, dynamic>> _confirmedActions() {
    final actions = widget.analysis.result!.suggestedActions;
    return [
      for (var index = 0; index < actions.length; index++)
        if (_selected[index])
          {
            'actionIndex': index,
            if (actions[index].targetId != null)
              'targetId': actions[index].targetId,
            'payload': _editedPayload(actions[index], _editors[index].text),
          },
    ];
  }

  Map<String, dynamic> _editedPayload(
    VoiceSuggestedAction action,
    String value,
  ) {
    final payload = Map<String, dynamic>.from(action.payload);
    if (action.type == 'UPDATE_TASK_PROGRESS') {
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
      color: AppColors.successSoft,
      borderRadius: BorderRadius.circular(AppRadius.medium),
    ),
    child: const Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.shield_outlined, color: AppColors.success),
        SizedBox(width: 10),
        Expanded(
          child: Text(
            'Your recording is used to prepare this project action and is stored according to the project data policy.',
            style: TextStyle(fontSize: 12, height: 1.45),
          ),
        ),
      ],
    ),
  );
}
