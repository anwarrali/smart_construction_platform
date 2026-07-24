import json
import re
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    OpenAIError,
)

from app.ai.exceptions import AIConfigurationError, AIProviderError, AIProviderTimeoutError
from app.core.config import settings
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    DetectedProgress,
    SuggestedActionType,
)


SYSTEM_PROMPT = """You interpret Arabic, English, and mixed-language construction voice notes.
Return only the supplied strict schema. Preserve technical terminology and factual uncertainty.
Use only task IDs supplied in authorized_tasks; never invent or copy any other identifier.
Distinguish progress percentages from quantities such as metres, units, workers, dates, and costs.
Suggest zero or more actions from the controlled schema. Suggestions are drafts only and never executed.
For workers, suggest CREATE_FIELD_SUBMISSION only; reported progress remains unverified evidence.
For contractor engineers, actions may include UPDATE_TASK_PROGRESS, CREATE_ISSUE, ADD_TASK_NOTE,
CREATE_SITE_REPORT_DRAFT, and CREATE_TASK_MESSAGE. A task message must contain user-reviewable draft text.
When task confidence is low, leave task_id and action target_id null instead of guessing.
Map blockers to construction problem types and keep the original meaning in descriptions."""


class ConstructionVoiceAnalysisService:
    def __init__(self, client: Any | None = None):
        self._client = client

    def analyze(
        self,
        *,
        transcript: str,
        user_role: str,
        authorized_tasks: list[dict],
    ) -> ConstructionVoiceResult:
        client = self._client or self._configured_client()
        context = {
            "transcript": transcript,
            "user_role": user_role,
            "authorized_tasks": authorized_tasks,
        }
        try:
            response = client.responses.parse(
                model=settings.OPENAI_ACTION_MODEL,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                text_format=ConstructionVoiceResult,
            )
        except APITimeoutError as exc:
            raise AIProviderTimeoutError("Construction voice analysis timed out. Please retry.") from exc
        except APIConnectionError as exc:
            raise AIProviderError("Construction voice analysis is temporarily unreachable.") from exc
        except (BadRequestError, NotFoundError) as exc:
            raise AIConfigurationError(
                "OPENAI_ACTION_MODEL is unavailable or does not support structured outputs."
            ) from exc
        except OpenAIError as exc:
            raise AIProviderError("The provider could not analyze this field update.") from exc
        result = getattr(response, "output_parsed", None)
        if not isinstance(result, ConstructionVoiceResult):
            raise AIProviderError("The provider returned no valid structured field update.")
        validate_task_scope(result, {str(task["id"]) for task in authorized_tasks})
        return guard_measurements(transcript, result)

    @staticmethod
    def _configured_client() -> OpenAI:
        if not settings.OPENAI_API_KEY:
            raise AIConfigurationError("AI is not configured. Set OPENAI_API_KEY on the backend.")
        if not settings.OPENAI_ACTION_MODEL:
            raise AIConfigurationError("AI is not configured. Set OPENAI_ACTION_MODEL on the backend.")
        return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=60.0, max_retries=2)


def validate_task_scope(result: ConstructionVoiceResult, authorized_task_ids: set[str]) -> None:
    referenced = []
    if result.detected_task.task_id:
        referenced.append(result.detected_task.task_id)
    referenced.extend(
        action.target_id
        for action in result.suggested_actions
        if action.target_id is not None
    )
    if any(str(task_id) not in authorized_task_ids for task_id in referenced):
        raise ValueError("AI output referenced a task outside the authorized project scope.")


def guard_measurements(
    transcript: str, result: ConstructionVoiceResult
) -> ConstructionVoiceResult:
    """A deterministic last-line safeguard; semantic interpretation remains provider-driven."""
    progress = result.progress
    if not progress.mentioned or progress.percentage is None:
        return result
    number = f"{float(progress.percentage):g}"
    measurement = re.search(
        rf"\b{re.escape(number)}\s*(?:m|meter|meters|metre|metres|متر|كابل|cables?|units?)\b",
        transcript,
        flags=re.IGNORECASE,
    )
    explicit_progress = re.search(
        rf"(?:{re.escape(number)}\s*%|{re.escape(number)}\s*(?:percent|percentage|بالمئة|٪))",
        transcript,
        flags=re.IGNORECASE,
    )
    if not measurement or explicit_progress:
        return result
    actions = [
        action for action in result.suggested_actions
        if action.type != SuggestedActionType.UPDATE_TASK_PROGRESS
    ]
    return result.model_copy(update={
        "progress": DetectedProgress(mentioned=False, percentage=None, confidence=0),
        "suggested_actions": actions,
    })
