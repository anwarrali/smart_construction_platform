from typing import Any

import json

from openai import APIConnectionError, APITimeoutError, BadRequestError, NotFoundError, OpenAI, OpenAIError

from app.ai.action_schemas import VoiceAction
from app.ai.exceptions import AIConfigurationError, AIProviderError, AIProviderTimeoutError
from app.core.config import settings


SYSTEM_PROMPT = """You convert construction field transcripts into one proposed application action.
Return only the structured schema. Never claim that an action was executed.
For task actions, use only an exact task ID from the supplied project task context. Never invent IDs.
Match Arabic, English, or mixed speech to the supplied names/codes only when confident. If ambiguous,
leave task_id null, preserve the spoken task in task_reference, and set requires_clarification true.
Use unknown when intent is ambiguous or outside the supported action types.
All mutating actions require confirmation. Preserve the user's factual wording in description.
Confidence must reflect uncertainty, especially for mixed Arabic/English technical terminology."""


class ActionAnalyzer:
    def __init__(self, client: Any | None = None):
        self._client = client

    def analyze(self, transcript: str, task_context: list[dict] | None = None) -> VoiceAction:
        client = self._client or self._configured_client()
        try:
            response = client.responses.parse(
                model=settings.OPENAI_ACTION_MODEL,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({
                        "transcript": transcript,
                        "project_tasks": task_context or [],
                    }, ensure_ascii=False)},
                ],
                text_format=VoiceAction,
            )
        except APITimeoutError as exc:
            raise AIProviderTimeoutError("The action analysis service timed out. Please retry.") from exc
        except APIConnectionError as exc:
            raise AIProviderError("The action analysis service is temporarily unreachable.") from exc
        except (BadRequestError, NotFoundError) as exc:
            raise AIConfigurationError(
                "OPENAI_ACTION_MODEL is invalid, unavailable, or does not support structured outputs. "
                "Configure a supported model available to this OpenAI API account."
            ) from exc
        except OpenAIError as exc:
            raise AIProviderError("The action analysis provider could not process this command.") from exc
        action = getattr(response, "output_parsed", None)
        if not isinstance(action, VoiceAction):
            raise AIProviderError("The action analyzer returned no valid structured proposal.")
        return action

    @staticmethod
    def _configured_client() -> OpenAI:
        if not settings.OPENAI_API_KEY:
            raise AIConfigurationError(
                "AI action analysis is not configured. Set OPENAI_API_KEY on the backend."
            )
        if not settings.OPENAI_ACTION_MODEL:
            raise AIConfigurationError(
                "AI action analysis is not configured. Set OPENAI_ACTION_MODEL on the backend "
                "to a supported model available to this OpenAI API account."
            )
        return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=60.0, max_retries=2)
