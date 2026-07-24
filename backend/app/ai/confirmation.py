from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from jose import JWTError, jwt

from app.ai.action_schemas import VoiceActionType
from app.core.config import settings


def create_confirmation_token(*, user_id: UUID, project_id: UUID, task_id: UUID,
                              progress: float, transcript: str) -> str:
    payload = {
        "type": "voice_ai_confirmation",
        "jti": str(uuid4()),
        "sub": str(user_id),
        "project_id": str(project_id),
        "task_id": str(task_id),
        "action_type": VoiceActionType.UPDATE_TASK_PROGRESS.value,
        "progress": progress,
        "transcript": transcript,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_confirmation_token(token: str, *, user_id: UUID) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError("This voice action preview is invalid or has expired.") from exc
    if payload.get("type") != "voice_ai_confirmation" or payload.get("sub") != str(user_id):
        raise ValueError("This voice action preview does not belong to the current user.")
    if payload.get("action_type") != VoiceActionType.UPDATE_TASK_PROGRESS.value:
        raise ValueError("This voice action type is not executable.")
    return payload
