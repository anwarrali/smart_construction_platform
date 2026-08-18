/// The failures the voice flow can raise, as values rather than sentences.
///
/// These used to be `StateError('Record audio before analysis.')`, and the
/// screen recovered the text with `toString().replaceFirst('Bad state: ', '')`
/// — which pins the message to English and to Dart's formatting. Naming the
/// condition instead lets the screen translate it.
enum VoiceFailure {
  microphonePermission,
  recordBeforeTranscribing,
  recordBeforeAnalysis,
  nothingToRetry,
  nothingToConfirm,
  nothingToClarify,
  actionUnavailable,
}

class VoiceException implements Exception {
  const VoiceException(this.failure);
  final VoiceFailure failure;

  @override
  String toString() => 'VoiceException(${failure.name})';
}
