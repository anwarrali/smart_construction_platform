"""Deciding which capability an utterance belongs to.

This is the brain, and it is deliberately the *only* thing that decides. The
capabilities behind it — answering, drafting actions, composing messages,
asking for clarification — already existed and are unchanged; what was missing
was anything that chose between them. The pipeline had one exit, so everything
went out through it, and a question about a task became a proposal to modify
that task.

Three principles, each learned from a specific failure:

  * **No single field decides.** Routing reads `request_kind`, `query.topic`,
    `detected_intents`, whether any action was proposed, and whether a progress
    figure was extracted. The first version keyed on `request_kind` *and*
    `query.topic` both being right; either one arriving wrong dropped the
    utterance into the action pipeline. Independent signals now corroborate
    each other, so one imperfect field degrades the answer instead of changing
    the route.

  * **Zero actions never means "add a note".** An empty action list is the
    model correctly declining to propose a mutation. Reading it as "the user
    must have wanted a note" was the original architectural bug; reading it as
    "ask whether they wanted a note or an issue" was the same bug wearing a
    question mark. Nothing here manufactures an action.

  * **The fallback is never action-shaped.** When routing genuinely cannot
    tell, the reply repeats what was understood and asks the engineer to say it
    again. It does not offer a menu of mutations.

`VoiceIntent` already carried sixty semantic meanings and nothing read them.
The tables below are that taxonomy finally wired to the capabilities it was
always describing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    SuggestedActionType,
    VoiceIntent,
    VoiceQueryTopic,
    VoiceRequestKind,
)
from app.services.voice_task_matcher import normalize


class VoiceRoute(str, Enum):
    """Where an utterance goes. Exactly one of these, always."""

    #: Retrieve authoritative data and reply. Nothing to confirm.
    ANSWER = "ANSWER"
    #: Draft a mutation for review, confirmation, then the rules engine.
    ACTION = "ACTION"
    #: Compose a message to a person. Confirmed before sending, like any action.
    COMMUNICATION = "COMMUNICATION"
    #: One thing is missing. Ask for it — and only it.
    CLARIFICATION = "CLARIFICATION"


#: Semantic intents that are requests for information, whatever else the
#: utterance also mentions. Reading these means a question still routes to the
#: answer path when `request_kind` arrives wrong.
_INFORMATION_INTENTS: frozenset[VoiceIntent] = frozenset({
    VoiceIntent.REQUEST_TASK_INFORMATION,
    VoiceIntent.REQUEST_INFORMATION,
})

#: Intents about telling a person something. A message that mentions a task is
#: still a message.
_COMMUNICATION_INTENTS: frozenset[VoiceIntent] = frozenset({
    VoiceIntent.SEND_MESSAGE,
    VoiceIntent.SEND_PROJECT_UPDATE,
    VoiceIntent.SEND_OWNER_UPDATE,
    VoiceIntent.SEND_ENGINEER_UPDATE,
    VoiceIntent.SEND_CONSULTANT_UPDATE,
})

#: Executable handlers that *are* the communication capability. When the model
#: proposes one of these the route is COMMUNICATION even though a draft exists,
#: so the UI previews a message rather than a task change.
#:
#: `CREATE_TASK_MESSAGE` is deliberately absent: it is scoped to a task, needs a
#: task target, and already works on the action path. Moving it here would
#: change behaviour that is not broken.
_COMMUNICATION_ACTIONS: frozenset[SuggestedActionType] = frozenset({
    SuggestedActionType.SEND_OWNER_UPDATE,
    SuggestedActionType.SEND_PROJECT_MESSAGE,
})

#: When the model says "this is a question about a task" but leaves the topic
#: unset, the intent still narrows it enough to answer. Without this a
#: correctly-understood question with an unset topic fell through to the action
#: pipeline — the exact failure seen with "شو ضايل علينا مهام؟".
_INTENT_TOPIC_FALLBACK: dict[VoiceIntent, VoiceQueryTopic] = {
    VoiceIntent.REQUEST_TASK_INFORMATION: VoiceQueryTopic.TASK_STATUS,
    VoiceIntent.REQUEST_INFORMATION: VoiceQueryTopic.PROJECT_PROGRESS,
}

#: Ways of marking a sentence as a belief rather than an observation. Written
#: in the folded form `normalize` produces, so one spelling covers the hamza
#: and diacritic variants speech-to-text emits at random.
#:
#: Matched on word boundaries, never as loose substrings, and that is not a
#: refinement — "مشكلة" folds to "مشكله", which *contains* "شكله", and "بشكل
#: عام" contains "بشك". A substring test would have marked the most common
#: sentence in the domain — "في مشكلة بالموقع" — as a hedge, which is the
#: exact opposite of what this is for.
_HEDGE_MARKERS: tuple[str, ...] = (
    "اتوقع", "بتوقع", "اعتقد", "بعتقد", "بظن", "اظن", "بشك",
    "يمكن", "ممكن يكون", "مش متاكد", "على ما اعتقد",
    "حاسس انه", "بحس انه", "شكله انه", "شكلها انه",
    "i think", "i believe", "i expect", "i suspect", "i guess", "not sure",
    "maybe", "probably", "seems like", "it looks like", "i feel like",
)

#: Arabic attaches "و" and "ف" to the front of a word, so a marker may arrive
#: as "وأتوقع". Anything else in front of it is a different word.
_HEDGE_PATTERN = re.compile(
    "(?:^|\\s|و|ف)(?:" + "|".join(re.escape(marker) for marker in _HEDGE_MARKERS)
    + ")(?:\\s|$)"
)

#: Intents that say the speaker's uncertainty is about something going wrong.
#: They decide *which* question to answer, never whether it is one.
_PROBLEM_INTENTS: frozenset[VoiceIntent] = frozenset({
    VoiceIntent.REPORT_TASK_BLOCKER,
    VoiceIntent.REPORT_TASK_DELAY,
    VoiceIntent.CREATE_ISSUE,
    VoiceIntent.REPORT_DEFECT,
    VoiceIntent.REPORT_QUALITY_ISSUE,
    VoiceIntent.REPORT_SAFETY_ISSUE,
    VoiceIntent.REPORT_MATERIAL_SHORTAGE,
    VoiceIntent.REPORT_EQUIPMENT_PROBLEM,
})


def _is_hedged(result: ConstructionVoiceResult) -> bool:
    """Whether the speaker marked the sentence as a belief, not an observation.

    Read from the transcript rather than from any classified field, because the
    field is precisely what got this wrong: the model saw "في مشكلة في
    المشروع", classified a STATEMENT, and the qualifier that changed its whole
    meaning — "أتوقع" — did not survive into any structured value.

    This is deliberately not a question detector. It is only ever consulted
    for a STATEMENT that proposed nothing, so a hedge inside an instruction
    ("أتوقع نخلص بكرة، سجّل ملاحظة") cannot reach it: that utterance carries an
    action, and an action always wins. What it prevents is the narrow failure
    of recording a suspicion as though the engineer had witnessed it.
    """
    spoken = normalize(" ".join(
        part
        for part in (result.original_transcript, result.normalized_transcript)
        if part
    ))
    return bool(spoken) and _HEDGE_PATTERN.search(f" {spoken} ") is not None


def _uncertainty_topic(result: ConstructionVoiceResult) -> VoiceQueryTopic:
    """What a hedged statement is really asking about."""
    if result.query.topic != VoiceQueryTopic.UNKNOWN:
        return result.query.topic
    if result.problems or (set(result.detected_intents) & _PROBLEM_INTENTS):
        return VoiceQueryTopic.OPEN_ISSUES
    return VoiceQueryTopic.PROJECT_PROGRESS


@dataclass(frozen=True)
class RouteDecision:
    """The chosen capability, plus what it needs to do its job."""

    route: VoiceRoute
    #: Resolved for ANSWER; UNKNOWN elsewhere.
    topic: VoiceQueryTopic = VoiceQueryTopic.UNKNOWN
    #: Why this route was chosen. Recorded on the command for support, and the
    #: single most useful thing to look at when a route surprises someone.
    reason: str = ""

    @property
    def is_answer(self) -> bool:
        return self.route == VoiceRoute.ANSWER


def route_request(result: ConstructionVoiceResult) -> RouteDecision:
    """Choose the capability for one interpreted utterance.

    Pure: no database, no user, no side effects. Everything it needs is already
    in the structured result, which is what makes the decision testable on its
    own and keeps "what did the engineer want" separate from "what is true",
    which the capabilities answer afterwards.
    """
    intents = set(result.detected_intents)
    actions = [action.type for action in result.suggested_actions]

    # 1. A proposed communication handler is unambiguous: the model picked a
    #    messaging action, so this is a message regardless of what it mentions.
    if any(action in _COMMUNICATION_ACTIONS for action in actions):
        return RouteDecision(
            VoiceRoute.COMMUNICATION,
            reason="messaging handler proposed",
        )

    # 2. Any other proposed handler is a mutation. The model only proposes when
    #    it believes something should change, and that path — draft, review,
    #    confirm, execute — is unchanged and still carries every safety check.
    if actions:
        return RouteDecision(VoiceRoute.ACTION, reason="executable action proposed")

    # From here the model proposed nothing. That is a *decision* it made, not a
    # gap to fill with a note.

    # 3. Communication intent without a handler: the engineer wants to tell
    #    somebody something but the recipient or the text is still missing.
    #    That is a communication clarification, never a task question.
    if intents & _COMMUNICATION_INTENTS:
        return RouteDecision(
            VoiceRoute.COMMUNICATION,
            reason="communication intent without a complete handler",
        )

    # 4. A question, by either signal. Two independent sources so one wrong
    #    field cannot reroute the utterance.
    # REASONING sits with QUESTION here on purpose: both are reads, both are
    # answered from project data, and neither may propose a mutation. They
    # differ only in how the answer is composed, which `answer_query` decides
    # from the topic.
    asked = (
        result.request_kind
        in {VoiceRequestKind.QUESTION, VoiceRequestKind.REASONING}
        or bool(intents & _INFORMATION_INTENTS)
    )
    if asked:
        topic = result.query.topic
        if topic == VoiceQueryTopic.UNKNOWN:
            # A reasoning request with no topic is still a request to explain,
            # and "what should we focus on" is the explanation that needs the
            # least from the utterance.
            if result.request_kind == VoiceRequestKind.REASONING:
                topic = VoiceQueryTopic.PRIORITY_FOCUS
            else:
                for intent in intents:
                    if intent in _INTENT_TOPIC_FALLBACK:
                        topic = _INTENT_TOPIC_FALLBACK[intent]
                        break
        return RouteDecision(
            VoiceRoute.ANSWER,
            topic=topic,
            reason=(
                "question with an explicit topic"
                if result.query.topic != VoiceQueryTopic.UNKNOWN
                else "question with a topic inferred from intent"
            ),
        )

    # 5. A statement the speaker hedged. "أتوقع إنه في مشكلة في المشروع" is a
    #    suspicion offered for checking, not a fact offered for recording, and
    #    the difference is the whole sentence rather than any one field. Read
    #    as a question about whatever they are unsure of — which is what the
    #    engineer meant, and what they had to say a second time to get.
    #
    #    Narrow on purpose. It is reached only for a STATEMENT that proposed
    #    nothing, so a hedge inside an instruction never sees it, and it
    #    answers rather than asks: the request was already clear enough.
    if result.request_kind == VoiceRequestKind.STATEMENT and _is_hedged(result):
        return RouteDecision(
            VoiceRoute.ANSWER,
            topic=_uncertainty_topic(result),
            reason="uncertain statement answered from the record",
        )

    # 6. An explicit progress figure with no action attached. The model
    #    extracted a percentage but could not name a target, usually because
    #    several tasks fit. That belongs to the progress capability — with the
    #    normal target clarification and confirmation — not to a note.
    if result.progress.mentioned and result.progress.percentage is not None:
        return RouteDecision(
            VoiceRoute.ACTION,
            reason="progress stated without a resolved target",
        )

    # 7. Nothing else identified it. Ask — neutrally. The one thing this must
    #    never do is offer a choice between mutations the engineer never
    #    mentioned.
    return RouteDecision(
        VoiceRoute.CLARIFICATION,
        reason="no action, no question, and no progress figure",
    )


def needs_progress_draft(result: ConstructionVoiceResult) -> bool:
    """True when routing to ACTION on a progress figure alone.

    Distinguishes case 5 above from case 2, so the caller knows it has to build
    the progress draft itself rather than translate one the model proposed.
    """
    return (
        not result.suggested_actions
        and result.progress.mentioned
        and result.progress.percentage is not None
    )
