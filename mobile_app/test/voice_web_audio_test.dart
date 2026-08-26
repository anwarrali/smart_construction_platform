/// The web recording upload contract.
///
/// On mobile the app names the file it just wrote, so extension, MIME type and
/// bytes agree by construction. On web the *browser* picks the container —
/// Chrome honours `aacLc` and produces MP4, Firefox supports no AAC container
/// and falls back to WebM — so the app has to read the format back off the
/// bytes before declaring it.
///
/// The backend rejects any upload whose declared extension disagrees with its
/// leading bytes (`_matches_audio_signature` in
/// `backend/app/ai/transcription_service.py`). These tests pin this detector to
/// that check: if either side drifts, web recordings start failing with a 415
/// about content not matching its extension, which is a genuinely confusing
/// thing to debug from the UI.
library;

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:construction_field/services/voice_service.dart';

Uint8List bytesOf(List<int> values) => Uint8List.fromList(values);

/// Realistic file heads, padded so offset-based checks have something to read.
Uint8List webm() => bytesOf([0x1A, 0x45, 0xDF, 0xA3, ...List.filled(28, 0)]);
Uint8List mp4() => bytesOf([
  0x00, 0x00, 0x00, 0x20, // box size
  0x66, 0x74, 0x79, 0x70, // 'ftyp'
  0x4D, 0x34, 0x41, 0x20, // 'M4A '
  ...List.filled(20, 0),
]);
Uint8List wav() => bytesOf([
  0x52, 0x49, 0x46, 0x46, // 'RIFF'
  0x24, 0x00, 0x00, 0x00, // chunk size
  0x57, 0x41, 0x56, 0x45, // 'WAVE'
  ...List.filled(20, 0),
]);
Uint8List mp3WithId3() => bytesOf([0x49, 0x44, 0x33, ...List.filled(29, 0)]);
Uint8List mp3FrameSync() => bytesOf([0xFF, 0xFB, ...List.filled(30, 0)]);

void main() {
  group('recorded audio format detection', () {
    test('WebM is recognised by its EBML header', () {
      final format = RecordedAudioFormat.detect(webm());
      expect(format.extension, 'webm');
      expect(format.mimeType, 'audio/webm');
    });

    test('MP4 is recognised by the ftyp box at offset four', () {
      // The Chrome case: `aacLc` resolves to audio/mp4, so this is the format
      // most web recordings will actually have.
      final format = RecordedAudioFormat.detect(mp4());
      expect(format.extension, 'm4a');
      expect(format.mimeType, 'audio/mp4');
    });

    test('WAV requires both the RIFF and WAVE markers', () {
      final format = RecordedAudioFormat.detect(wav());
      expect(format.extension, 'wav');
      expect(format.mimeType, 'audio/wav');
    });

    test('a RIFF container that is not WAVE is not claimed as WAV', () {
      // 'RIFF' alone also starts AVI and WebP. The backend checks both markers,
      // so claiming .wav here would produce a rejected upload.
      final avi = bytesOf([
        0x52, 0x49, 0x46, 0x46,
        0x24, 0x00, 0x00, 0x00,
        0x41, 0x56, 0x49, 0x20, // 'AVI '
        ...List.filled(20, 0),
      ]);
      expect(RecordedAudioFormat.detect(avi).extension, isNot('wav'));
    });

    test('MP3 is recognised from an ID3 tag', () {
      expect(RecordedAudioFormat.detect(mp3WithId3()).extension, 'mp3');
      expect(RecordedAudioFormat.detect(mp3WithId3()).mimeType, 'audio/mpeg');
    });

    test('MP3 is recognised from a bare frame sync', () {
      expect(RecordedAudioFormat.detect(mp3FrameSync()).extension, 'mp3');
    });

    test('every detected format is one the backend accepts', () {
      // The backend's SUPPORTED_EXTENSIONS / SUPPORTED_MIME_TYPES pair.
      const allowedExtensions = {'mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm'};
      const allowedMimeTypes = {
        'audio/mpeg', 'audio/mp4', 'audio/x-m4a', 'audio/wav',
        'audio/x-wav', 'audio/webm', 'video/mp4', 'video/webm',
      };
      for (final sample in [webm(), mp4(), wav(), mp3WithId3(), mp3FrameSync()]) {
        final format = RecordedAudioFormat.detect(sample);
        expect(allowedExtensions, contains(format.extension));
        expect(allowedMimeTypes, contains(format.mimeType));
      }
    });

    test('a truncated recording never reads past its own buffer', () {
      // A stop() that captured almost nothing must not throw a range error on
      // the offset-four check; it should simply fail to match.
      for (var length = 0; length < 8; length++) {
        expect(
          () => RecordedAudioFormat.detect(bytesOf(List.filled(length, 0))),
          returnsNormally,
        );
      }
    });

    test('an unrecognised container falls back to WebM rather than guessing wildly', () {
      final unknown = bytesOf(List.filled(32, 0x7A));
      final format = RecordedAudioFormat.detect(unknown);
      expect(format.extension, 'webm');
      // The point is that the backend then rejects it on signature, rather than
      // the app storing something mislabelled.
      expect(format.mimeType, 'audio/webm');
    });
  });
}
