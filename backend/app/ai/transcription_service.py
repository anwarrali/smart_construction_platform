from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, BadRequestError, NotFoundError, OpenAI, OpenAIError

from app.ai.action_schemas import TranscriptionResponse
from app.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIProviderTimeoutError,
    InvalidAudioError,
)
from app.core.config import settings

MAX_AUDIO_BYTES = 25 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
SUPPORTED_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "video/mp4",
    "video/webm",
    "application/octet-stream",
}


def validate_audio(filename: str, content_type: str, content: bytes) -> None:
    extension = Path(filename).suffix.lower()
    mime_type = content_type.split(";", 1)[0].strip().lower()
    if extension not in SUPPORTED_EXTENSIONS or mime_type not in SUPPORTED_MIME_TYPES:
        raise InvalidAudioError(
            "Unsupported audio file. Use MP3, MP4, MPEG, MPGA, M4A, WAV, or WebM."
        )
    if not content:
        raise InvalidAudioError("Uploaded audio is empty.")
    if len(content) > MAX_AUDIO_BYTES:
        raise InvalidAudioError("Audio file exceeds the 25 MB limit.")
    if not _matches_audio_signature(extension, content):
        raise InvalidAudioError("Audio content does not match its file extension.")


def _matches_audio_signature(extension: str, content: bytes) -> bool:
    if extension == ".wav":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    if extension in {".m4a", ".mp4"}:
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if extension in {".mp3", ".mpeg", ".mpga"}:
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
        )
    if extension == ".webm":
        return content.startswith(b"\x1a\x45\xdf\xa3")
    return False


class TranscriptionService:
    def __init__(self, client: Any | None = None):
        self._client = client

    def transcribe(
        self,
        *,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> TranscriptionResponse:
        validate_audio(filename, content_type, content)
        client = self._client or self._configured_client()
        try:
            result = client.audio.transcriptions.create(
                model=settings.OPENAI_TRANSCRIPTION_MODEL,
                file=(filename, content, content_type),
                response_format="json",
                prompt=(
                    "Construction project field update. Preserve Arabic and English speech, "
                    "task names, percentages, measurements, engineering disciplines, and "
                    "mixed Arabic-English technical terminology accurately."
                ),
            )
        except APITimeoutError as exc:
            raise AIProviderTimeoutError("The transcription service timed out. Please retry.") from exc
        except APIConnectionError as exc:
            raise AIProviderError("The transcription service is temporarily unreachable.") from exc
        except (BadRequestError, NotFoundError) as exc:
            raise AIConfigurationError(
                "OPENAI_TRANSCRIPTION_MODEL is invalid or unavailable to this OpenAI API account."
            ) from exc
        except OpenAIError as exc:
            raise AIProviderError("The transcription provider could not process this audio.") from exc
        transcript = str(getattr(result, "text", "") or "").strip()
        if not transcript:
            raise AIProviderError("No speech could be transcribed from this recording.")
        language = str(getattr(result, "language", "") or "auto")
        return TranscriptionResponse(
            transcript=transcript,
            language=language,
            model=settings.OPENAI_TRANSCRIPTION_MODEL,
        )

    @staticmethod
    def _configured_client() -> OpenAI:
        if not settings.OPENAI_API_KEY:
            raise AIConfigurationError(
                "Voice transcription is not configured. Set OPENAI_API_KEY on the backend."
            )
        return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=60.0, max_retries=2)
