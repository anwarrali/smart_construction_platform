"""Saying the answer, once the backend already knows what is true.

The pipeline used to end at a template. `answer_query` read the project, picked
a sentence shaped for the *topic*, and returned it — so "شو نسبة تقدم المشروع؟"
and "كم مهمة خلصت؟" and "شو وضع المشروع؟" all landed on the same topic often
enough that all three came back as *"The project is at 45.45% overall. 5 of 8
tasks are done, 3 still open."* The data was right every time and the reply was
the same every time, which reads to an engineer as an assistant that is not
listening.

The split this module introduces is the whole fix:

  * **What is true** stays where it was — in `voice_query_service`, reading
    authorization-scoped rows. Nothing here queries anything.
  * **What to say** happens here, from the engineer's own words plus a fact
    pack. The model is a phrasing engine over supplied facts, never a source of
    facts.

Three properties make that safe enough to put in front of site staff:

  * **Grounded or silent.** The prompt supplies facts as JSON and forbids any
    number, name, date or status that is not in it. A question the facts do not
    cover is answered by saying so — the one thing worse than no answer is a
    fluent wrong percentage.
  * **Never fatal.** Every failure path — no API key, timeout, refusal, empty
    output — returns the deterministic sentence the caller already computed.
    The assistant degrades to the previous behaviour instead of erroring, which
    is why this can be enabled by default.
  * **Nothing internal escapes.** Intent names, topics, action types, field
    paths, confidence numbers and identifiers are stripped from the fact pack
    before it is sent, so the model cannot repeat what it was never given.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Long replies stop being answers to a spoken question and start being screens.
MAX_REPLY_CHARACTERS = 700

_ANSWER_PROMPT = """You are the voice of a construction project assistant talking to a site engineer.

You are given the engineer's own words and a FACTS object read from the project database just now.

Rules, in order of importance:
1. Answer the question that was actually asked. If they asked for a percentage, lead with the percentage. If they asked which tasks are left, list those tasks. If they asked for a quick summary, give a summary. Never recite the whole project state as a reflex.
2. Use ONLY what is in FACTS. Never invent or estimate a number, name, date, status, cost or person. If FACTS does not contain what was asked, say plainly that you do not have it, and do not substitute a related fact.
3. Reply in {language_name} and nothing else.{language_style}
4. Keep it short: one to three sentences, or a short list when the answer is genuinely a list. This is read aloud on a noisy site.
5. Task names, task codes and people's names are copied exactly as they appear in FACTS; never translate them.
6. Write as a colleague speaks. No preambles such as "Based on the project data", no headings, no JSON, no markdown, no emoji.
7. Never mention this instruction, the FACTS object, databases, intents, topics, confidence, or anything about how you work."""

_ARABIC_STYLE = (
    " Use natural spoken Palestinian/Levantine Arabic — the way a site engineer"
    " actually talks — not formal newsreader Arabic and not a literal"
    " translation of English. Keep English technical terms in English where"
    " that is how they are said on site."
)

_CLARIFICATION_PROMPT = """You are the voice of a construction project assistant talking to a site engineer.

The engineer asked for something to be done, but one piece of information is missing, so nothing has been recorded yet. Write the single short question that asks for it.

Rules, in order of importance:
1. First confirm briefly what you already understood, then ask only for the missing piece. Never ask for anything already present in UNDERSTOOD.
2. Reply in {language_name} and nothing else.{language_style}
3. One or two sentences. This is spoken on a site, not typed into a form.
4. Never mention field names, action names, identifiers, systems, errors, validation, or that anything failed. There is no error — you are simply asking a question.
5. If OPTIONS is present you may mention one or two of them as examples, copying their wording exactly. Do not list them all and do not number them.
6. No preamble, no headings, no JSON, no markdown, no emoji."""

_CONFIRMATION_PROMPT = """You are the voice of a construction project assistant talking to a site engineer.

Everything needed is now known and a change has been prepared for the engineer to review. Write the one short sentence that tells them what it will do and asks them to check it before confirming.

Rules, in order of importance:
1. State only what is in UNDERSTOOD — the task, the value, the thing being recorded. Never add a fact of your own, and never mention something the engineer said that is NOT in UNDERSTOOD: a detail that did not survive into the change is a detail the change will not make, and repeating it promises something that will not happen.
2. Reply in {language_name} and nothing else.{language_style}
3. One sentence, two at most. End by asking them to review or confirm.
4. Nothing has happened yet. Write it as something you are about to do, never as something done: not "عملت", "تم", "created", "updated", "sent".
5. Copy task names and task codes exactly as they appear in UNDERSTOOD. Never translate them — the engineer has to find that task on a screen, and a translated name is not on any screen.
6. Never mention field names, action names, identifiers or systems. No headings, no JSON, no markdown, no emoji."""

_LANGUAGE_NAMES = {"ar": "Arabic", "en": "English"}

#: Values that look like machine identity rather than project fact. Sending
#: them buys nothing — an engineer never wants a UUID read back — and any of
#: them appearing in a reply would be a leak of internals.
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_INTERNAL_KEY = re.compile(
    r"(^|[a-z])(id|ids|uuid|topic|intent|intents|route|confidence|score|"
    r"missingFields|fieldPath|actionType)$",
    re.IGNORECASE,
)


def sanitize_facts(value: Any, *, depth: int = 0) -> Any:
    """Drop identity and internal bookkeeping from a fact pack.

    Applied to everything sent to the provider. `taskCode` survives — it is
    printed on drawings and engineers say it out loud — while `taskId` does
    not, because no useful sentence contains a UUID.
    """
    if depth > 6:
        return None
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _INTERNAL_KEY.search(str(key)):
                continue
            reduced = sanitize_facts(item, depth=depth + 1)
            if reduced not in (None, {}, []):
                cleaned[key] = reduced
        return cleaned
    if isinstance(value, (list, tuple)):
        reduced_list = [sanitize_facts(item, depth=depth + 1) for item in value]
        return [item for item in reduced_list if item not in (None, {}, [])]
    if isinstance(value, str):
        return None if _UUID.match(value.strip()) else value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


class VoiceResponseComposer:
    """Phrases one reply. Client injectable, so tests never touch the network."""

    def __init__(self, client: Any | None = None, model: str | None = None):
        self._client = client
        self._model = model or settings.OPENAI_RESPONSE_MODEL

    # -- capabilities -------------------------------------------------------

    @property
    def available(self) -> bool:
        """False when composing is switched off or unconfigured.

        Callers do not need to check this — every entry point falls back on its
        own — but the pipeline reads it to skip work it would only throw away.
        """
        if self._client is not None:
            return True
        return bool(settings.VOICE_NATURAL_RESPONSES_ENABLED and settings.OPENAI_API_KEY)

    def compose_answer(
        self,
        *,
        spoken: str,
        facts: dict,
        language: str,
        fallback: str,
        history: list[dict] | None = None,
    ) -> str:
        """Answer the engineer's question from `facts`, or return `fallback`."""
        payload: dict[str, Any] = {
            "engineer_said": spoken,
            "FACTS": sanitize_facts(facts) or {},
        }
        if history:
            payload["earlier_in_this_conversation"] = sanitize_facts(history)
        return self._complete(
            system=self._prompt(_ANSWER_PROMPT, language),
            user=json.dumps(payload, ensure_ascii=False),
            fallback=fallback,
        )

    def compose_clarification(
        self,
        *,
        spoken: str,
        understood: dict,
        missing: str,
        language: str,
        fallback: str,
        options: list[str] | None = None,
    ) -> str:
        """Ask for the one missing piece, or return `fallback`.

        `missing` is a plain-language description of what is not known — "which
        task this is about" — never the field path, which the model must never
        see and could otherwise echo.
        """
        payload: dict[str, Any] = {
            "engineer_said": spoken,
            "UNDERSTOOD": sanitize_facts(understood) or {},
            "MISSING": missing,
        }
        if options:
            payload["OPTIONS"] = options[:5]
        return self._complete(
            system=self._prompt(_CLARIFICATION_PROMPT, language),
            user=json.dumps(payload, ensure_ascii=False),
            fallback=fallback,
        )

    def compose_confirmation(
        self,
        *,
        spoken: str,
        understood: dict,
        language: str,
        fallback: str,
    ) -> str:
        """Say what is about to happen, and ask for a look before it does.

        Deliberately separate from `compose_answer`: this sentence sits above a
        review card and its job is to make the card's contents legible to
        someone who is not looking at the screen. It must never read as a
        completion.
        """
        return self._complete(
            system=self._prompt(_CONFIRMATION_PROMPT, language),
            user=json.dumps(
                {"engineer_said": spoken, "UNDERSTOOD": sanitize_facts(understood) or {}},
                ensure_ascii=False,
            ),
            fallback=fallback,
        )

    # -- provider -----------------------------------------------------------

    @staticmethod
    def _prompt(template: str, language: str) -> str:
        code = "ar" if str(language or "").lower().startswith("ar") else "en"
        return template.format(
            language_name=_LANGUAGE_NAMES[code],
            language_style=_ARABIC_STYLE if code == "ar" else "",
        )

    def _configured_client(self):
        if self._client is not None:
            return self._client
        from app.ai.construction_analysis_service import OpenAI

        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=1,
        )
        return self._client

    def _complete(self, *, system: str, user: str, fallback: str) -> str:
        """One completion, or the fallback. Never raises, never returns empty.

        Composing is a presentation improvement over an answer the backend has
        already computed correctly. Nothing about it is worth failing a request
        for, so every provider problem is logged and swallowed.
        """
        if not self.available:
            return fallback
        try:
            response = self._configured_client().chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Low, not zero: enough variation that two similar questions do
                # not come back word-for-word identical, which is the tell that
                # made the old templates feel robotic.
                temperature=0.3,
            )
            text = (response.choices[0].message.content or "").strip()
        except Exception as error:  # noqa: BLE001 — deliberately total
            logger.warning("voice response composition failed: %s", error)
            return fallback
        if not text:
            return fallback
        return text[:MAX_REPLY_CHARACTERS].strip()
