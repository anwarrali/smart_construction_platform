import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import '../../models/voice_draft.dart';
import '../../services/voice_service.dart';

class VoiceViewModel {
  VoiceViewModel(this.projectId, this._processing) {
    _playerStateSubscription = _player.onPlayerStateChanged.listen((state) {
      isPlaying = state == PlayerState.playing;
    });
    _positionSubscription = _player.onPositionChanged.listen((value) {
      playbackPosition = value;
    });
    _durationSubscription = _player.onDurationChanged.listen((value) {
      playbackDuration = value;
    });
    _completeSubscription = _player.onPlayerComplete.listen((_) {
      isPlaying = false;
      playbackPosition = Duration.zero;
    });
  }
  final String projectId;
  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  final VoiceProcessingService _processing;
  Timer? _timer;
  Timer? _amplitudeTimer;
  late final StreamSubscription<PlayerState> _playerStateSubscription;
  late final StreamSubscription<Duration> _positionSubscription;
  late final StreamSubscription<Duration> _durationSubscription;
  late final StreamSubscription<void> _completeSubscription;
  Duration duration = Duration.zero;
  Duration playbackPosition = Duration.zero;
  Duration playbackDuration = Duration.zero;
  VoiceDraftStatus status = VoiceDraftStatus.idle;
  bool isPlaying = false;
  String? path;
  String? transcription;
  String? transcriptionLanguage;
  VoiceAnalysis? analysis;
  String? _requestId;
  final List<double> amplitudeSamples = [];

  Future<void> start() async {
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission is required.');
    }
    final directory = await getTemporaryDirectory();
    path =
        '${directory.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
    _requestId =
        'mobile-${DateTime.now().microsecondsSinceEpoch}-${projectId.replaceAll('-', '')}';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: path!,
    );
    duration = Duration.zero;
    playbackPosition = Duration.zero;
    playbackDuration = Duration.zero;
    amplitudeSamples.clear();
    status = VoiceDraftStatus.recording;
    _timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => duration += const Duration(seconds: 1),
    );
    _startAmplitudeSampling();
  }

  Future<void> pause() async {
    await _recorder.pause();
    _timer?.cancel();
    _amplitudeTimer?.cancel();
    status = VoiceDraftStatus.paused;
  }

  Future<void> resume() async {
    await _recorder.resume();
    status = VoiceDraftStatus.recording;
    _timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => duration += const Duration(seconds: 1),
    );
    _startAmplitudeSampling();
  }

  Future<void> stop() async {
    path = await _recorder.stop();
    _timer?.cancel();
    _amplitudeTimer?.cancel();
    playbackDuration = duration;
    status = VoiceDraftStatus.recorded;
  }

  Future<VoiceTranscription> transcribe(void Function() onChanged) async {
    if (path == null) throw StateError('Record audio before transcribing.');
    status = VoiceDraftStatus.uploading;
    onChanged();
    try {
      final result = await _processing.transcribe(
        projectId: projectId,
        filePath: path!,
        onSendProgress: (sent, total) {
          if (total > 0 && sent >= total) {
            status = VoiceDraftStatus.transcribing;
            onChanged();
          }
        },
      );
      transcription = result.transcript;
      transcriptionLanguage = result.language;
      status = VoiceDraftStatus.ready;
      onChanged();
      return result;
    } catch (_) {
      status = VoiceDraftStatus.error;
      onChanged();
      rethrow;
    }
  }

  Future<VoiceAnalysis> analyze({
    String? taskId,
    required void Function() onChanged,
  }) async {
    if (path == null) throw StateError('Record audio before analysis.');
    status = VoiceDraftStatus.uploading;
    onChanged();
    try {
      final value = await _processing.createAnalysis(
        projectId: projectId,
        taskId: taskId,
        filePath: path!,
        duration: duration,
        requestId: _requestId ??=
            'mobile-${DateTime.now().microsecondsSinceEpoch}-${projectId.replaceAll('-', '')}',
        onSendProgress: (sent, total) {
          if (total > 0 && sent >= total) {
            status = VoiceDraftStatus.transcribing;
            onChanged();
          }
        },
      );
      analysis = value;
      transcription = value.rawTranscript;
      transcriptionLanguage = value.detectedLanguage;
      status = value.failed ? VoiceDraftStatus.error : VoiceDraftStatus.ready;
      onChanged();
      return value;
    } catch (_) {
      status = VoiceDraftStatus.error;
      onChanged();
      rethrow;
    }
  }

  Future<VoiceAnalysis> retryAnalysis(void Function() onChanged) async {
    final current = analysis;
    if (current == null) throw StateError('No analysis to retry.');
    status = VoiceDraftStatus.transcribing;
    onChanged();
    final value = await _processing.retryAnalysis(current.id);
    analysis = value;
    transcription = value.rawTranscript;
    transcriptionLanguage = value.detectedLanguage;
    status = value.failed ? VoiceDraftStatus.error : VoiceDraftStatus.ready;
    onChanged();
    return value;
  }

  Future<List<Map<String, dynamic>>> confirm(
    List<Map<String, dynamic>> actions,
  ) {
    final current = analysis;
    if (current == null) throw StateError('No analysis to confirm.');
    return _processing.confirmActions(current.id, actions, current);
  }

  Future<VoiceAnalysis> answerClarification(
    String clarificationId,
    String answer,
  ) async {
    final current = analysis;
    if (current == null) throw StateError('No analysis to clarify.');
    final updated = await _processing.answerClarification(
      analysis: current,
      clarificationId: clarificationId,
      answer: answer,
    );
    analysis = updated;
    return updated;
  }

  Future<void> play() async {
    if (path == null) return;
    if (isPlaying) {
      await _player.pause();
      return;
    }
    if (_player.state == PlayerState.paused) {
      await _player.resume();
    } else {
      await _player.play(DeviceFileSource(path!));
    }
  }

  Future<void> seek(Duration position) async {
    await _player.seek(position);
    playbackPosition = position;
  }

  Future<void> delete() async {
    await _player.stop();
    if (await _recorder.isRecording()) await _recorder.stop();
    _timer?.cancel();
    path = null;
    duration = Duration.zero;
    playbackPosition = Duration.zero;
    playbackDuration = Duration.zero;
    amplitudeSamples.clear();
    isPlaying = false;
    transcription = null;
    transcriptionLanguage = null;
    analysis = null;
    status = VoiceDraftStatus.idle;
  }

  void _startAmplitudeSampling() {
    _amplitudeTimer?.cancel();
    _amplitudeTimer = Timer.periodic(const Duration(milliseconds: 110), (
      _,
    ) async {
      try {
        final amplitude = await _recorder.getAmplitude();
        final normalized = ((amplitude.current + 60) / 60).clamp(.04, 1.0);
        amplitudeSamples.add(normalized);
        if (amplitudeSamples.length > 72) amplitudeSamples.removeAt(0);
      } catch (_) {
        // A missed sample should not interrupt the recording.
      }
    });
  }

  Future<VoiceIntentProposal> propose(String transcript) =>
      _processing.analyze(projectId: projectId, transcript: transcript);
  Future<void> dispose() async {
    _timer?.cancel();
    _amplitudeTimer?.cancel();
    await _playerStateSubscription.cancel();
    await _positionSubscription.cancel();
    await _durationSubscription.cancel();
    await _completeSubscription.cancel();
    await _recorder.dispose();
    await _player.dispose();
  }
}
