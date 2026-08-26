import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import '../../models/voice_draft.dart';
import '../../services/voice_service.dart';
import 'voice_errors.dart';

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

  /// Identifies the current attempt.
  ///
  /// Abandoning a hung upload cannot cancel the HTTP request already in flight,
  /// so its response may still arrive afterwards. Without a token to compare
  /// against, that late response would overwrite the state the engineer has
  /// already moved on from — putting them back into a result screen for a
  /// recording they discarded. Every async completion checks the token it
  /// started with and drops itself if the attempt has been superseded.
  int _attempt = 0;

  Future<void> start() async {
    _attempt++;
    if (!await _recorder.hasPermission()) {
      throw const VoiceException(VoiceFailure.microphonePermission);
    }
    // `path_provider` ships no web implementation — `PathProviderPlugin` is
    // absent from the generated web plugin registrant — so calling
    // `getTemporaryDirectory()` in a browser throws `MissingPluginException`.
    // That is neither a `VoiceException` nor a `NetworkException`, so it fell
    // through `describeError` to the generic "something went wrong", which is
    // why a web user saw no hint that the platform was the problem.
    //
    // Skipping it loses nothing. `record` documents `path` as "Required on all
    // IO platforms" and its web backend ignores the argument outright: it
    // records into an in-memory blob and returns that blob's URL from `stop()`.
    // So on web the browser decides where the audio lives, and `path` stays
    // null until `stop()` fills it in with the `blob:` URL.
    final String destination;
    if (kIsWeb) {
      destination = 'voice_${DateTime.now().millisecondsSinceEpoch}.webm';
      path = null;
    } else {
      final directory = await getTemporaryDirectory();
      destination =
          '${directory.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
      path = destination;
    }
    _requestId =
        'mobile-${DateTime.now().microsecondsSinceEpoch}-${projectId.replaceAll('-', '')}';
    // The encoder is deliberately the same on every platform. On web `record`
    // maps `aacLc` to the first container the browser supports — MP4 in
    // Chrome — and falls back to the browser default (WebM) where it supports
    // none, as Firefox does. Both are containers the backend accepts, and the
    // upload path detects which one actually arrived rather than assuming.
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc),
      path: destination,
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
    if (path == null) {
      throw const VoiceException(VoiceFailure.recordBeforeTranscribing);
    }
    final attempt = _attempt;
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
      if (attempt != _attempt) return result;
      transcription = result.transcript;
      transcriptionLanguage = result.language;
      status = VoiceDraftStatus.ready;
      onChanged();
      return result;
    } catch (_) {
      // A failure must always land somewhere the engineer can act from.
      if (attempt == _attempt) {
        status = VoiceDraftStatus.error;
        onChanged();
      }
      rethrow;
    }
  }

  Future<VoiceAnalysis> analyze({
    String? taskId,
    required void Function() onChanged,
  }) async {
    if (path == null) {
      throw const VoiceException(VoiceFailure.recordBeforeAnalysis);
    }
    final attempt = _attempt;
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
      if (attempt != _attempt) return value;
      analysis = value;
      transcription = value.rawTranscript;
      transcriptionLanguage = value.detectedLanguage;
      status = value.failed ? VoiceDraftStatus.error : VoiceDraftStatus.ready;
      onChanged();
      return value;
    } catch (_) {
      if (attempt == _attempt) {
        status = VoiceDraftStatus.error;
        onChanged();
      }
      rethrow;
    }
  }

  Future<VoiceAnalysis> retryAnalysis(void Function() onChanged) async {
    final current = analysis;
    if (current == null) {
      throw const VoiceException(VoiceFailure.nothingToRetry);
    }
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
    List<VoiceDraftConfirmation> actions,
  ) {
    final current = analysis;
    if (current == null) {
      throw const VoiceException(VoiceFailure.nothingToConfirm);
    }
    return _processing.confirmActions(current.id, actions, current);
  }

  Future<VoiceAnalysis> answerClarification(
    String clarificationId,
    String answer,
  ) async {
    final current = analysis;
    if (current == null) {
      throw const VoiceException(VoiceFailure.nothingToClarify);
    }
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
      // On web `path` is the `blob:` URL `stop()` returned, not a file the
      // platform can open, so it has to be played as a URL source.
      await _player.play(kIsWeb ? UrlSource(path!) : DeviceFileSource(path!));
    }
  }

  Future<void> seek(Duration position) async {
    await _player.seek(position);
    playbackPosition = position;
  }

  /// Give up on whatever is in flight and return to a usable idle state.
  ///
  /// This is the escape hatch from `uploading`/`transcribing`, which otherwise
  /// have no controls at all. Superseding the attempt first means a response
  /// that arrives later is discarded rather than dragging the engineer back
  /// into a result for a recording they abandoned. Nothing was confirmed, so
  /// nothing was written, so abandoning is always safe.
  Future<void> abandon() async {
    _attempt++;
    await delete();
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
