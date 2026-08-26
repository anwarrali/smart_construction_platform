from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
import re
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import user_has_project_access
from app.models.enums import TaskStatus, UserStatus, VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft, VoiceClarification
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    SuggestedActionType,
    VoiceIntent,
    VoiceQueryTopic,
    VoiceRequestKind,
)
from app.schemas.voice_command import VoiceDraftUpdate
from app.ai.action_payload_contract import ACTION_CONTRACTS
from app.ai.response_composer import VoiceResponseComposer
from app.services.audit_service import record_audit
from app.services.voice_analysis_authorization import authorized_voice_tasks
from app.services.voice_action_policy import action_risk
from app.services.voice_action_requirements import (
    TARGET_ISSUE,
    TARGET_TASK,
    apply_answer,
    describe_understood,
    issue_status_value,
    missing_fields,
    priority_value,
    prompt_for,
)
from app.services import voice_conversation_service
from app.services.voice_capabilities import (
    ISSUES,
    REPORTS,
    TASKS,
    available_capabilities,
    capability_for,
    is_available,
)
from app.services.voice_dates import describe_date
from app.services.voice_entity_resolution import (
    Person,
    assignable_people,
    authorized_issues,
    match_issue,
    match_people,
    named_person_reference,
    project_owner,
    project_people,
    resolve_date_field,
    resolve_recipients,
)
from app.services.voice_language import reply_language
from app.services.voice_query_service import (
    VoiceAnswer,
    answer_query,
    project_snapshot,
)
from app.services.voice_router import VoiceRoute, needs_progress_draft, route_request
from app.services.voice_task_matcher import (
    MAX_CANDIDATES,
    TaskMatch,
    match_by_position,
    match_task,
)


logger = logging.getLogger(__name__)


ALLOWED_TRANSITIONS: dict[VoiceAnalysisStatus, set[VoiceAnalysisStatus]] = {
    VoiceAnalysisStatus.UPLOADED: {
        VoiceAnalysisStatus.TRANSCRIBING,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.TRANSCRIBING: {
        VoiceAnalysisStatus.TRANSCRIBED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.TRANSCRIBED: {
        VoiceAnalysisStatus.ANALYZING,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.ANALYZING: {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
        # An answered question ends here: it proposed nothing, so it never
        # reaches confirmation.
        VoiceAnalysisStatus.COMPLETED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.NEEDS_CLARIFICATION: {
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
        # An answered clarification can finish the request outright: the answer
        # to "which task?" on a *question* is the question answered, and a
        # re-interpreted request may turn out to be a read. Without this the
        # re-interpretation raised 409 and the engineer saw nothing at all.
        VoiceAnalysisStatus.COMPLETED,
        VoiceAnalysisStatus.CANCELLED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.READY_FOR_CONFIRMATION: {
        VoiceAnalysisStatus.CONFIRMED,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.COMPLETED: {
        VoiceAnalysisStatus.CONFIRMED,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.CONFIRMED: {
        VoiceAnalysisStatus.EXECUTING,
        VoiceAnalysisStatus.CANCELLED,
    },
    VoiceAnalysisStatus.EXECUTING: {
        VoiceAnalysisStatus.EXECUTED,
        VoiceAnalysisStatus.PARTIALLY_EXECUTED,
        VoiceAnalysisStatus.FAILED,
    },
    VoiceAnalysisStatus.FAILED: {
        VoiceAnalysisStatus.UPLOADED,
        VoiceAnalysisStatus.CANCELLED,
    },
}


def transition(command: VoiceAnalysis, target: VoiceAnalysisStatus) -> None:
    if command.status == target:
        return
    if target not in ALLOWED_TRANSITIONS.get(command.status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Voice command cannot transition from {command.status.value} to {target.value}",
        )
    command.status = target
    command.row_version += 1


def assert_command_access(
    db: Session, command: VoiceAnalysis, user: User, *, owner_only: bool = False
) -> None:
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="An active account is required")
    if not user_has_project_access(db, user, command.project_id):
        raise HTTPException(status_code=403, detail="Voice command project is not accessible")
    if owner_only and command.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the initiating user may change this command")
    if not owner_only and command.user_id != user.id:
        from app.services.voice_analysis_authorization import can_view_voice_analysis
        if not can_view_voice_analysis(db, user, command):
            raise HTTPException(status_code=403, detail="Voice command is not accessible")


def assert_version(command: VoiceAnalysis, expected: int) -> None:
    if command.row_version != expected:
        raise HTTPException(
            status_code=409,
            detail="Voice command changed. Refresh and confirm the current draft.",
        )




def spoken_task_reference(
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    suggestion=None,
) -> str:
    """The best available description of *which* task the engineer meant.

    Assembled from most-specific to least: the title the model heard, the
    location it extracted, the action's own text, and finally the transcript.
    The transcript is included rather than used alone because a daily update
    names three different tasks in one breath — matching every action against
    the whole utterance would score them all identically — while an action
    with no extracted reference of its own still needs *something* to match.
    """
    parts: list[str] = []
    if suggestion is not None:
        payload = suggestion.payload_dict()
        parts.extend(
            str(payload[key])
            for key in ("title", "location", "note", "content", "description")
            if payload.get(key)
        )
    if result.detected_task.task_title:
        parts.insert(0, result.detected_task.task_title)
    if result.location and result.location.text:
        parts.append(result.location.text)
    if result.discipline and result.discipline.value:
        parts.append(str(result.discipline.value))
    if not parts:
        parts.append(command.raw_transcript or result.summary or "")
    return " ".join(part for part in parts if part)[:1000]


def interpret_command(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
) -> None:
    """Interpret one utterance, and guarantee the engineer hears something back.

    The routing itself is `_route_command`; this wrapper exists for the one
    rule that has to hold across every path through it: **no silent states.**
    A command that reaches the client with no question, no proposal and no
    sentence is a person speaking and the screen doing nothing, which is
    indistinguishable from the app being broken.
    """
    language = reply_language(
        command.raw_transcript or command.normalized_transcript,
        command.detected_language or result.detected_language,
    )
    try:
        _route_command(db, command=command, result=result, user=user)
    finally:
        language = str(
            (command.provider_metadata or {}).get("replyLanguage") or language
        )
        ensure_visible_state(command, language=language, reason="interpretation")


def _route_command(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
) -> None:
    """Decide what the utterance was for, then take the matching path.

    The pipeline used to have one exit: build drafts, ask for a target, wait for
    confirmation. That is the correct shape for "ابدأ المهمة" and the wrong
    shape for "شو حالة الحفر؟", and the difference was invisible because both
    sentences mention a task. Everything that is *about* a task was therefore
    treated as a request to *change* a task.

    Three paths now:

      * **Continue.** An utterance that answers a question asked a moment ago
        completes the request that asked it, rather than starting a new one —
        see `voice_conversation_service`. Tried first, and only for utterances
        that propose nothing and ask nothing of their own.
      * **Read.** A question is answered from the database and the command
        finishes. There is no confirmation step because there is nothing to
        confirm — the read path cannot mutate anything.
      * **Write.** Unchanged in shape. Drafts, target validation, clarification,
        explicit confirmation, then the rules engine. What changed is that a
        field the speaker did not say is now a question rather than a failure,
        and the review card waits until nothing is outstanding.

    A statement that contradicts the record gets a third, narrow treatment: it
    is surfaced as a question rather than silently recorded, because "المهمة
    الخامسة متوقفة" against a task the database calls Done at 100% is either a
    correction or a misunderstanding, and guessing which one is not safe.
    """
    command.normalized_transcript = (
        result.normalized_transcript or result.summary
    ).strip()

    decision = route_request(result)
    language = reply_language(
        command.raw_transcript or command.normalized_transcript,
        command.detected_language or result.detected_language,
    )
    command.provider_metadata = {
        **(command.provider_metadata or {}),
        # Recorded because "why did it go there?" is the first question anyone
        # asks about a surprising route, and the answer is otherwise invisible.
        "route": decision.route.value,
        "routeReason": decision.reason,
        # The language the engineer spoke, which is the language every reply on
        # this command is written in — regardless of the interface's locale.
        "replyLanguage": language,
    }

    def continue_language(earlier: VoiceAnalysis | None) -> str:
        """Keep a conversation in the language it started in.

        A one-word answer carries almost no signal — "rawan ibrahim" is Latin
        script inside an Arabic conversation, and answering it in English
        because of that would be the assistant losing the thread over two
        words. When an utterance *continues* an earlier request, the earlier
        request decides.
        """
        return str(
            (getattr(earlier, "provider_metadata", None) or {}).get("replyLanguage")
            or language
        )

    spoken = command.raw_transcript or command.normalized_transcript or ""

    # A correction comes first of all: "لا، قصدي المهمة السابعة" is said at a
    # review card, about a proposal that is already complete, and treating it
    # as a new request would leave the wrong proposal standing beside it.
    correctable = voice_conversation_service.find_correctable_request(
        db, user=user, project_id=command.project_id, exclude_id=command.id,
    )
    if correctable is not None and voice_conversation_service.is_correction(
        spoken, result
    ):
        tasks = authorized_voice_tasks(db, user, command.project_id)
        db.flush()
        if voice_conversation_service.apply_correction(
            db, command=command, result=result, user=user, pending=correctable,
            tasks=tasks,
        ):
            language = continue_language(correctable)
            command.provider_metadata = {
                **(command.provider_metadata or {}),
                "route": VoiceRoute.ACTION.value,
                "routeReason": "corrected the proposal already under review",
                "replyLanguage": language,
            }
            _finish_action_drafts(
                db, command=command, candidates=tasks, language=language,
                ranked={}, options={}, result=result, user=user,
            )
            return

    # An unfinished request from a moment ago comes next: "المهمة السادسة" is
    # meaningless on its own and is the whole answer in context. Only utterances
    # that propose nothing of their own are considered, so a real new
    # instruction can never be swallowed by an old question.
    pending = voice_conversation_service.find_open_request(
        db, user=user, project_id=command.project_id, exclude_id=command.id,
    )
    answers_pending = False
    if pending is not None:
        answers_pending = voice_conversation_service.is_possible_answer(result)
        if not answers_pending:
            # The model sometimes answers a question by restating the whole
            # action with the missing piece filled in, rather than by saying
            # the piece alone. Read as a new request, that answer loses the
            # task the pending request had already resolved and asks for it
            # again — the loop that made "19 سبتمبر" un-answerable. The
            # predicate below is deliberately narrow; see `continues_pending`.
            answers_pending = voice_conversation_service.continues_pending(
                result,
                pending,
                authorized_voice_tasks(db, user, command.project_id),
                spoken,
            )
    if pending is not None and answers_pending:
        tasks = authorized_voice_tasks(db, user, command.project_id)
        db.flush()
        if voice_conversation_service.merge_followup(
            db, command=command, result=result, user=user, pending=pending,
            tasks=tasks,
        ):
            language = continue_language(pending)
            command.provider_metadata = {
                **(command.provider_metadata or {}),
                "route": VoiceRoute.ACTION.value,
                "routeReason": "answered the question asked a moment ago",
                "replyLanguage": language,
            }
            _finish_action_drafts(
                db, command=command, candidates=tasks, language=language,
                ranked={}, options={}, result=result, user=user,
            )
            return

    if decision.route == VoiceRoute.ANSWER:
        if _answer_question(db, command=command, result=result, user=user,
                            topic=decision.topic, language=language,
                            pending=pending):
            return
        # Understood as a question but not answerable from project data. Say
        # that, rather than falling into a menu of mutations nobody asked for.
        _finish_unanswerable(db, command=command, result=result, language=language)
        return

    # Reconciliation runs before the clarification fallback: a statement that
    # disagrees with the record is *not* an unclassifiable utterance, and asking
    # "could you say that again?" would throw away the one useful thing we
    # know — that the engineer and the database disagree.
    if result.request_kind == VoiceRequestKind.STATEMENT:
        if _raise_contradiction(db, command=command, result=result, user=user,
                                language=language):
            return

    if decision.route == VoiceRoute.CLARIFICATION:
        # A request the speaker is not allowed to make is not an unclear
        # request. Saying "ما التقطت شو بدك تعمل" to somebody who said exactly
        # what they wanted is the assistant blaming them for its own rule.
        blocked = capability_for(result.blocked_capability) if result.blocked_capability else None
        if blocked is not None and not is_available(
            db, user=user, project_id=command.project_id, capability=blocked
        ):
            _refuse_capability(
                db, command=command, capability=blocked, language=language,
            )
            return
        _ask_neutral_clarification(db, command=command, result=result,
                                   user=user, language=language, pending=pending)
        return

    # ACTION and COMMUNICATION both build drafts and both keep the existing
    # review-and-confirm safety model; they differ in what the client renders,
    # which the recorded route tells it.
    build_action_drafts(
        db, command=command, result=result, user=user,
        synthesize_progress=needs_progress_draft(result),
        language=language,
    )
    # A new instruction replaces an unanswered one. Left open, the old question
    # would collect the *next* utterance as its answer, which is how an
    # abandoned request comes back to life three sentences later.
    if pending is not None and command.action_drafts:
        voice_conversation_service.close(
            db, pending, reason="superseded", successor=command,
        )


def renders_something(command: VoiceAnalysis) -> bool:
    """Whether a client has anything to show for this command.

    The three things a client can render, and the only three: a question it is
    waiting on, a proposal to review, or a sentence. A command with none of
    them is a screen that answers a person's words with nothing — the failure
    this predicate exists to make impossible.

    Deliberately expressed the way the clients decide, not the way the pipeline
    thinks: an *answered* clarification renders nothing, because the card that
    showed it is gone the moment it has an answer.
    """
    if any(not item.answer_text for item in command.clarifications):
        return True
    if command.action_drafts and not any(
        draft.missing_fields for draft in command.action_drafts
    ):
        return True
    answer = (command.structured_result or {}).get("answer") or {}
    return bool(str(answer.get("text") or "").strip())


def ensure_visible_state(
    command: VoiceAnalysis, *, language: str, reason: str = "unclassified"
) -> None:
    """Guarantee this command says *something* back.

    Every path through interpretation ends here. A path that produced a
    question, a proposal or an answer passes through untouched; one that
    produced none of them gets a plain sentence saying so, because the
    alternative — the state that caused this function to exist — is a person
    speaking and the assistant appearing to freeze.

    The fallback is deliberately about *this exchange*, not about the system:
    no status code, no exception class, nothing about pipelines. Whatever went
    wrong is in the logs; what the person needs is to know they should say it
    again.
    """
    if renders_something(command):
        return
    logger.warning(
        "voice command %s produced no renderable state (%s); using the fallback reply",
        command.id, reason,
    )
    arabic = "ما قدرت أكمل معالجة طلبك. ممكن تحكيلي مرة تانية شو بدك؟"
    english = "I could not finish that. Could you tell me again what you need?"
    _record_answer(command, VoiceAnswer(
        topic="UNRESOLVED",
        text_en=english,
        text_ar=arabic,
        data={},
        language=language,
        spoken_text=arabic if language.startswith("ar") else english,
    ))


def _record_answer(command: VoiceAnalysis, answer: VoiceAnswer) -> None:
    """Attach an answer to the command's stored result.

    Written into `structured_result` rather than a new column: it is derived
    output belonging to one analysis, the column is already JSONB, and a
    migration would buy nothing.
    """
    command.structured_result = {
        **(command.structured_result or {}),
        "answer": answer.as_dict(),
    }


def _answer_question(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
    topic: VoiceQueryTopic,
    language: str = "en",
    pending: VoiceAnalysis | None = None,
) -> bool:
    """Answer a question from project data. True when the command is finished.

    `topic` comes from the router, not from `result.query`, because the router
    may have recovered it from `detected_intents` when the model left the field
    unset — which is exactly the case that used to fall through to the action
    pipeline.

    Retrieval and phrasing are two steps on purpose. The topic decides *what to
    read*; the engineer's own words decide *what to say about it*. When both
    ran together, three different questions that mapped to one topic came back
    as one identical sentence — right data, wrong answer.
    """
    tasks = authorized_voice_tasks(db, user, command.project_id)
    answer = answer_query(
        db,
        user=user,
        project_id=command.project_id,
        query=result.query.model_copy(update={"topic": topic}),
        tasks=tasks,
        spoken=command.raw_transcript,
    )
    if answer is None:
        return False

    if not answer.is_answered:
        # The question was about one task and several fit. This is the one case
        # where "which task do you mean?" is the right reply to a question.
        db.flush()
        command.clarifications.append(VoiceClarification(
            sequence=len(command.clarifications) + 1,
            field_path="query.taskId",
            question_ar="أي مهمة تقصد؟",
            question_en="Which task do you mean?",
            expected_answer_type="TASK_SELECTION",
            options=[match.as_option() for match in answer.candidates[:MAX_CANDIDATES]],
        ))
        _record_answer(command, replace(answer, language=language))
        transition(command, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
        return True

    phrased = _phrase_answer(
        db, command=command, answer=answer, tasks=tasks, language=language,
    )
    reminder = _pending_reminder(pending, language)
    if reminder:
        # A question asked in the middle of a request does not cancel the
        # request. Answering and then saying what is still outstanding is what
        # keeps the thread — otherwise the engineer answers a question, gets a
        # helpful reply, and never learns that their half-finished instruction
        # is still sitting there waiting for a date.
        phrased = replace(
            phrased, spoken_text=f"{phrased.spoken_text} {reminder}".strip()
        )
    _record_answer(command, phrased)
    # COMPLETED is the terminal state for a read: nothing was proposed, so
    # there is nothing for the engineer to confirm or cancel.
    transition(command, VoiceAnalysisStatus.COMPLETED)
    return True


def _pending_reminder(pending: VoiceAnalysis | None, language: str) -> str:
    """What is still outstanding on an earlier request, in one short clause.

    Read from the pending command's own unanswered question rather than
    re-derived, so the reminder and the question can never say different
    things.
    """
    if pending is None:
        return ""
    outstanding = [
        item for item in pending.clarifications if not item.answer_text
    ]
    if not outstanding:
        return ""
    question = outstanding[0]
    if language.startswith("ar"):
        return f"وبالنسبة للطلب السابق، لسه بحاجة أعرف: {question.question_ar}"
    return f"On your earlier request, I still need to know: {question.question_en}"


def _phrase_answer(
    db: Session,
    *,
    command: VoiceAnalysis,
    answer: VoiceAnswer,
    tasks: list[Task],
    language: str,
) -> VoiceAnswer:
    """Say the answer in the engineer's words and language, or keep the template.

    The fact pack is the whole project snapshot plus whatever the topic
    retrieved, so one read serves any phrasing of the question: "كم مهمة خلصت؟"
    and "شو المهام اللي ضايلة؟" are answered from the same rows without a second
    query and without either answer being a summary of the other.

    The deterministic sentence is always computed first and passed as the
    fallback, so a provider outage costs naturalness and nothing else.
    """
    composer = VoiceResponseComposer()
    template = answer.text_for(language)
    if not composer.available:
        return replace(answer, language=language, spoken_text=template)
    facts = {
        **project_snapshot(db, project_id=command.project_id, tasks=tasks),
        "whatTheyAskedAbout": answer.data,
    }
    spoken = composer.compose_answer(
        spoken=command.raw_transcript or command.normalized_transcript or "",
        facts=facts,
        language=language,
        fallback=template,
    )
    return replace(answer, language=language, spoken_text=spoken)


def _finish_unanswerable(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    language: str = "en",
) -> None:
    """Say that a question could not be answered, and stop.

    The alternative — falling through to the action pipeline — is what turned
    "شو ضايل علينا مهام؟" into a task picker. An honest "I don't have that"
    is a worse answer and a far better behaviour.
    """
    answer = VoiceAnswer(
        topic="UNANSWERED",
        text_en=(
            "I understood the question but could not find that information in "
            "this project."
        ),
        text_ar="فهمت سؤالك بس ما لقيت هالمعلومة في هذا المشروع.",
        data={"summary": result.summary},
        language=language,
    )
    _record_answer(command, replace(answer, spoken_text=answer.text_for(language)))
    db.flush()
    transition(command, VoiceAnalysisStatus.COMPLETED)


#: The field path of the question that has no field behind it. Named so the
#: "did we already ask this?" check reads as a question about the conversation
#: rather than as a string comparison.
NEUTRAL_QUESTION = "intent"


def _ask_neutral_clarification(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User | None = None,
    language: str = "en",
    pending: VoiceAnalysis | None = None,
) -> None:
    """Ask what the engineer wants done, from what they actually said.

    This replaces "do you want to add a note or report an issue?", which
    presented two writes to an engineer who had asked for neither. What it must
    not become is the opposite failure: asking "ما التقطت شو بدك تعمل" again,
    word for word, to somebody who has just answered that exact question. A
    repeated question reads as the assistant not listening, which is what it
    looks like from the outside whether or not it is true.

    So the question is built from what *was* understood — the summary, and any
    problem the model heard — and offers the things this speaker could actually
    do about it. "تمام، فهمت إن المواد الكهربائية تأخرت. بدك أسجلها كمشكلة؟" is
    answerable; "say it again in different words" is a dead end.
    """
    db.flush()
    understood: dict[str, object] = {}
    if result.summary:
        understood["what they told me"] = result.summary
    problems = [problem.description for problem in result.problems if problem.description]
    if problems:
        understood["problems they mentioned"] = problems
    if result.materials:
        understood["materials they mentioned"] = [
            item.name for item in result.materials if item.name
        ]

    # Only what this person could actually do about it. Offering to record an
    # issue to somebody who cannot raise one is the "menu of mutations" problem
    # in a friendlier voice.
    options: list[str] = []
    if user is not None:
        # Ordered by what the utterance was *about*. Somebody describing a
        # delay is far likelier to want it recorded as a problem than to want a
        # task started, and offering the first four capabilities in registry
        # order buried "record a problem on site" under three task operations.
        preferred = (
            (ISSUES, REPORTS, TASKS) if (problems or result.materials)
            else (TASKS, ISSUES, REPORTS)
        )
        holds = [
            capability
            for capability in available_capabilities(
                db, user=user, project_id=command.project_id
            )
            if capability.category in preferred
        ]
        options = [
            capability.purpose
            for category in preferred
            for capability in holds
            if capability.category == category
        ][:3]

    # "Have I asked this already?" is a question about the conversation, not
    # about this one recording. Asked only of *this* command, the answer was
    # always no — every utterance is a new command — so the same words came
    # back verbatim every time, which reads as an assistant that is not
    # listening. The earlier request in the window is the memory that makes
    # the second attempt sound like a second attempt.
    asked_before = pending is not None and any(
        item.field_path == NEUTRAL_QUESTION for item in pending.clarifications
    )
    repeated = asked_before or any(
        item.answer_text for item in command.clarifications
    )
    if language.startswith("ar"):
        question_ar = (
            "تمام، سمعتك. بس شو بدك أعمل بهالمعلومة؟"
            if repeated
            else "ما التقطت شو بدك تعمل بالضبط. ممكن تعيدها بكلمات تانية؟"
        )
        question_en = "What would you like me to do about it?"
    else:
        question_ar = "شو بدك أعمل بهالمعلومة؟"
        question_en = (
            "I heard you. What would you like me to do about it?"
            if repeated
            else "I did not catch what you would like to do. "
            "Could you say it again in different words?"
        )

    composer = VoiceResponseComposer()
    if composer.available and understood:
        phrased = composer.compose_clarification(
            spoken=command.raw_transcript or command.normalized_transcript or "",
            understood=understood,
            missing="what they would like you to do about it",
            language=language,
            fallback=question_ar if language.startswith("ar") else question_en,
            options=options,
        )
        if language.startswith("ar"):
            question_ar = phrased
        else:
            question_en = phrased

    command.clarifications.append(VoiceClarification(
        sequence=len(command.clarifications) + 1,
        field_path="intent",
        question_ar=question_ar,
        question_en=question_en,
        expected_answer_type="TEXT",
        options=[],
    ))
    # The question is also the reply text, so a client that renders only the
    # answer still shows the engineer something conversational rather than a
    # blank card.
    _record_answer(command, VoiceAnswer(
        topic="UNCLASSIFIED",
        text_en=question_en,
        text_ar=question_ar,
        data={"summary": result.summary},
        language=language,
        spoken_text=question_ar if language.startswith("ar") else question_en,
    ))
    transition(command, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
    if pending is not None and not voice_conversation_service.outstanding_drafts(
        pending
    ):
        # This command now carries the open question, so the older *neutral*
        # one must stop being a candidate for the next answer. Left open, two
        # bodiless questions compete for the same reply and the conversation
        # cannot settle — the state that made this question repeat.
        #
        # A pending request with drafts is never touched here: its question is
        # about a field, the engineer can still answer it, and closing it would
        # throw away a half-finished instruction because one unrelated sentence
        # in between was unclear.
        voice_conversation_service.close(
            db, pending, reason="superseded", successor=command,
        )


def _raise_contradiction(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
    language: str = "en",
) -> bool:
    """Surface a stated fact that disagrees with the record. True when handled.

    Only the disagreement is detected here, never resolved: the engineer may be
    correcting stale data or may have the wrong task, and both are common
    enough on site that picking one silently is how wrong data gets recorded.
    """
    tasks = authorized_voice_tasks(db, user, command.project_id)
    outcome = match_task(
        spoken_task_reference(command, result), tasks, limit=MAX_CANDIDATES
    )
    if not outcome.is_resolved:
        return False
    task = next((item for item in tasks if item.id == outcome.resolved_task_id), None)
    if task is None:
        return False

    stated_blocked = any(
        intent in {VoiceIntent.PAUSE_TASK, VoiceIntent.REPORT_TASK_BLOCKER}
        for intent in result.detected_intents
    )
    recorded_done = task.status == TaskStatus.DONE or float(task.progress_percentage or 0) == 100
    if not (stated_blocked and recorded_done):
        return False

    status_word = getattr(task.status, "value", str(task.status))
    label = f"{task.task_code} — {task.name}" if task.task_code else task.name
    db.flush()
    command.clarifications.append(VoiceClarification(
        sequence=len(command.clarifications) + 1,
        field_path="statement.contradiction",
        question_ar=(
            f"{label} مسجّلة حالياً كمكتملة بنسبة "
            f"{float(task.progress_percentage or 0):g}%. "
            "أنت ذكرت أنها متوقفة. هل تقصد أنها توقفت رغم تسجيلها كمكتملة؟"
        ),
        question_en=(
            f"{label} is currently recorded as {status_word} at "
            f"{float(task.progress_percentage or 0):g}%. You said it is stopped. "
            "Did you mean it stopped despite being recorded complete?"
        ),
        expected_answer_type="TEXT",
        options=[],
    ))
    contradiction = command.clarifications[-1]
    _record_answer(command, VoiceAnswer(
        topic="STATEMENT_CONTRADICTION",
        text_en=contradiction.question_en,
        text_ar=contradiction.question_ar,
        data={
            "taskId": str(task.id),
            "recordedStatus": status_word,
            "recordedProgress": float(task.progress_percentage or 0),
        },
        language=language,
        spoken_text=(
            contradiction.question_ar
            if language.startswith("ar")
            else contradiction.question_en
        ),
    ))
    transition(command, VoiceAnalysisStatus.NEEDS_CLARIFICATION)
    return True


def build_action_drafts(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
    synthesize_progress: bool = False,
    language: str = "en",
) -> None:
    """Turn proposed actions into reviewable drafts.

    Four things happen to every proposal on the way to a draft, and each one
    exists because the alternative was a failure the engineer could not act on:

      * **Permission.** The capability registry says whether this person could
        do this on this project at all. If not, the assistant says so in a
        sentence instead of walking them through a review card for something
        the backend was always going to refuse.
      * **Target.** Which task — or which issue, for the issue capabilities —
        resolved against the list this person is already authorized to see.
      * **Fields.** Spoken values become real ones: "الأسبوع الجاي" becomes a
        date, "خطر" becomes a priority, "صاحب المشروع" becomes a person. The
        model supplies words; the backend supplies meaning.
      * **Completeness.** Whatever is still unsaid becomes a question, never an
        error — see `voice_action_requirements`.

    `synthesize_progress` is set by the router when the model extracted a
    percentage but proposed no handler for it — "وصلنا لنص الشغل" with several
    plausible tasks. That belongs to the progress capability, with the ordinary
    target clarification and confirmation, and this is the *only* draft this
    module creates that the model did not propose. It is not a fallback: it is
    driven by a structured figure the model did extract, and it never fires
    without one.
    """
    command.normalized_transcript = (
        result.normalized_transcript or result.summary
    ).strip()
    candidates = authorized_voice_tasks(db, user, command.project_id)
    candidate_ids = {task.id for task in candidates}
    suggestions = list(result.suggested_actions)
    if synthesize_progress and not suggestions:
        from app.schemas.voice_analysis import SuggestedAction

        suggestions = [SuggestedAction(
            type=SuggestedActionType.UPDATE_TASK_PROGRESS,
            target_id=command.task_id or result.detected_task.task_id,
            reason="Progress stated in the recording",
            payload={"progressPercentage": float(result.progress.percentage)},
            confidence=float(result.progress.confidence or 0.5),
        )]

    # A Worker statement is always evidence. If the model returned only an
    # informational summary, deterministically create the evidence draft.
    if user.role.value == "worker" and not suggestions:
        from app.schemas.voice_analysis import SuggestedAction

        target_id = command.task_id or result.detected_task.task_id
        suggestions = [
            SuggestedAction(
                type=SuggestedActionType.CREATE_FIELD_SUBMISSION,
                target_id=target_id,
                reason="Worker voice report requires Engineer verification",
                payload={"description": result.summary},
                confidence=max(float(result.detected_task.confidence), 0.5),
            )
        ]

    # Candidates per draft, so the clarification can offer the few tasks that
    # actually resemble what was said instead of the whole project.
    draft_candidates: dict[str, list[TaskMatch]] = {}
    option_lists: dict[str, list[dict]] = {}
    refused: list = []
    spoken = command.raw_transcript or command.normalized_transcript or ""

    for index, suggestion in enumerate(suggestions):
        capability = capability_for(suggestion.type)
        if capability is None:
            continue
        if not is_available(
            db, user=user, project_id=command.project_id, capability=capability
        ):
            refused.append(capability)
            continue

        client_action_id = suggestion.client_action_id or f"a{index + 1}-{uuid4().hex[:12]}"
        warnings: list[str] = list(suggestion.warnings)
        task = None
        issue_id = None

        if capability.needs_issue:
            issues = authorized_issues(db, project_id=command.project_id)
            issue_id, issue_options = _resolve_issue_target(
                suggestion, result, spoken, issues
            )
            if issue_id is None and issue_options:
                option_lists[client_action_id] = [
                    match.as_option() for match in issue_options
                ]
        else:
            target_id = command.task_id or suggestion.target_id
            if target_id not in candidate_ids:
                target_id = None
            task = db.get(Task, target_id) if target_id else None
            if capability.needs_task and task is None:
                # The model left the target open — usually because it correctly
                # refused to guess between similar task names. Resolve it here
                # against the authorized list rather than asking the engineer to
                # recall an exact stored title, which is the interaction this
                # whole feature exists to remove.
                outcome = match_task(
                    spoken_task_reference(command, result, suggestion), candidates
                )
                if outcome.is_resolved:
                    task = db.get(Task, outcome.resolved_task_id)
                    if outcome.confidence < 0.75:
                        warnings.append(
                            "Task identified from your description. Confirm it is the one you meant."
                        )
                else:
                    # Position first: "المهمة السادسة" names a task nothing in
                    # the scorer can see, because the sixth task's *words* are
                    # "Order electrical materials".
                    positioned = match_by_position(spoken, candidates)
                    if positioned is not None:
                        task = positioned
                    else:
                        draft_candidates[client_action_id] = outcome.candidates

        payload, field_options, field_warnings = _resolve_payload_fields(
            db,
            command=command,
            user=user,
            capability=capability,
            payload=suggestion.payload_dict(),
            spoken=spoken,
            language=language,
        )
        warnings.extend(field_warnings)
        option_lists.setdefault(client_action_id, []).extend(field_options)

        if float(suggestion.confidence) < settings.VOICE_MIN_EXECUTION_CONFIDENCE:
            warnings.append("Low AI confidence: review or edit this action before confirmation.")
        if (
            suggestion.type == SuggestedActionType.UPDATE_TASK_PROGRESS
            and result.progress.approximate
        ):
            # "نص الشغل" is a defensible 50 and worth proposing, but it is an
            # interpretation of words rather than a number the engineer spoke.
            # Saying so on the confirmation card is what keeps the difference
            # between the two visible at the moment it matters.
            warnings.append(
                "Percentage inferred from your wording, not stated directly. "
                "Confirm or edit it."
            )
        if user.role.value == "worker" and suggestion.type != SuggestedActionType.CREATE_FIELD_SUBMISSION:
            warnings.append("Worker reports cannot change official task values.")
            suggestion = suggestion.model_copy(update={
                "type": SuggestedActionType.CREATE_FIELD_SUBMISSION,
                "payload": {"description": result.summary},
            })
            capability = capability_for(suggestion.type)
            payload = suggestion.payload_dict()
        snapshot = None
        if task:
            snapshot = {
                "taskId": str(task.id),
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "updatedAt": task.updated_at.isoformat(),
            }
        configured_evidence: list[str] = []
        evidence_policy = task.voice_evidence_requirements if task else {}
        minimum_photos = int((evidence_policy or {}).get("minimumPhotos") or 0)
        if minimum_photos:
            configured_evidence.append(f"PHOTO:{minimum_photos}")
        configured_evidence.extend(
            f"VIEW:{str(view).upper()}" for view in (evidence_policy or {}).get("views", [])
        )
        target_id = issue_id if capability.needs_issue else (task.id if task else None)
        # What this action still needs is computed from one table rather than
        # trusted from the model's own `missing_fields`, which is advisory and
        # frequently empty on exactly the utterances that are incomplete —
        # "بدي أرفع مشكلة" with no problem in it. Each entry becomes a
        # question below; none of them ever becomes an error.
        missing = missing_fields(
            suggestion.type, payload, has_target=target_id is not None
        )
        command.action_drafts.append(VoiceActionDraft(
            voice_analysis_id=command.id,
            client_action_id=client_action_id,
            # The draft's position in `suggestedActions`, so every downstream
            # list agrees on one order.
            sequence=index,
            action_type=suggestion.type.value,
            target_entity_type=(
                "ISSUE" if capability.needs_issue and target_id else
                "TASK" if task else None
            ),
            target_entity_id=target_id,
            extracted_payload=payload,
            target_snapshot=snapshot,
            confidence=float(suggestion.confidence),
            missing_fields=missing,
            warnings=warnings,
            risk_level=action_risk(suggestion.type).value,
            required_evidence=configured_evidence,
        ))
    # No manufactured fallback draft.
    #
    # This is where an utterance the model proposed nothing for used to become
    # an ADD_TASK_NOTE built from the raw transcript, which then demanded a
    # target and asked "which task do you mean?". That is how a question like
    # "شو حالة الحفر؟" turned into a note. Silence from the model is
    # information: it means the sentence asked for nothing to be changed.
    # `interpret_command` has already tried to answer it as a question before
    # reaching here, so the only honest remaining move is one short clarifying
    # question about a field a draft actually needs.
    if refused and not command.action_drafts:
        _refuse_capability(db, command=command, capability=refused[0], language=language)
        return
    _finish_action_drafts(
        db, command=command, candidates=candidates, language=language,
        ranked=draft_candidates, options=option_lists, result=result, user=user,
    )


def _resolve_issue_target(suggestion, result, spoken: str, issues: list):
    """Which issue an issue-capability is about."""
    proposed = suggestion.target_id
    if proposed is not None:
        match = next((item for item in issues if item.id == proposed), None)
        if match is not None:
            return match.id, []
    reference = result.query.task_reference or spoken
    return match_issue(reference, issues)


def _resolve_payload_fields(
    db: Session,
    *,
    command: VoiceAnalysis,
    user: User,
    capability,
    payload: dict,
    spoken: str,
    language: str,
) -> tuple[dict, list[dict], list[str]]:
    """Turn spoken values in a payload into values the platform can store.

    Everything here is deterministic and checked against the project: a date is
    computed, a person is looked up in the team, a priority is matched against
    the platform's own enum. The model is never asked to produce an identifier
    or to do arithmetic, because both are things it can do fluently and wrongly.

    Returns the resolved payload, any option lists a clarification should
    offer, and warnings for the confirmation card.
    """
    resolved = dict(payload)
    options: list[dict] = []
    warnings: list[str] = []

    # An acknowledgement of a destructive action belongs to the person, not to
    # the model. Whatever it put here is dropped; the confirm endpoint sets it
    # from the engineer's own explicit high-risk confirmation.
    resolved.pop("confirmDeletion", None)

    # "بدي أرفع مشكلة" is a request, not a problem. The model is told not to
    # invent a title from the request itself and mostly does not, but when it
    # does the result is an issue called "بدي أرفع مشكلة" — so the echo is
    # caught here rather than trusted, and the field goes back to being a
    # question.
    if _echoes_the_request(resolved.get("title"), spoken):
        resolved.pop("title", None)
        resolved.pop("description", None)

    # -- dates --------------------------------------------------------------
    # Only for capabilities that *have* a date field. Hunting for one in every
    # sentence would write `dueDate` onto an issue report that happened to
    # mention "اليوم" — a field its contract forbids, so the rules engine would
    # reject the whole action at execution for something nobody asked for.
    allowed = ACTION_CONTRACTS[capability.action].allowed
    for key in ("dueDate", "startDate"):
        if key not in allowed:
            continue
        spoken_value = resolved.get(key)
        # The due date is worth looking for in the whole utterance, because
        # people say "خلّي المهمة السادسة الأسبوع الجاي" without repeating the
        # date into a field. A start date is only ever taken from its own.
        if not spoken_value and key != "dueDate":
            continue
        found = resolve_date_field(
            spoken_value,
            fallback_text=spoken if key == "dueDate" else None,
            today=_today(),
        )
        if found is None:
            resolved.pop(key, None)
            continue
        if found.is_resolved:
            resolved[key] = found.value.isoformat()
            if str(spoken_value or "") != resolved[key]:
                warnings.append(
                    f"Understood \"{found.spoken}\" as "
                    f"{describe_date(found.value, language=language)}."
                )
        else:
            # Understood, but it could be two different days. Offer both rather
            # than picking one — a deadline that silently moved by a week is
            # exactly the failure this avoids.
            resolved.pop(key, None)
            options.extend(
                {
                    "value": option.isoformat(),
                    "label": describe_date(option, language=language),
                }
                for option in found.options
            )

    # -- priority and issue state ------------------------------------------
    if resolved.get("priority"):
        matched = priority_value(str(resolved["priority"]))
        if matched:
            resolved["priority"] = matched
        else:
            resolved.pop("priority", None)
    if resolved.get("issueStatus"):
        matched = issue_status_value(str(resolved["issueStatus"]))
        if matched:
            resolved["issueStatus"] = matched
        else:
            resolved.pop("issueStatus", None)

    # -- people -------------------------------------------------------------
    if capability.action == SuggestedActionType.SEND_OWNER_UPDATE:
        owner = project_owner(db, command.project_id)
        if owner is not None:
            # The project knows who its owner is. Asking would be the assistant
            # pretending not to.
            resolved["recipientIds"] = [str(owner.user_id)]
    for key in ("recipientIds", "assigneeIds"):
        if key not in _PEOPLE_FIELDS_BY_ACTION.get(capability.action, ()):
            continue
        if key == "assigneeIds":
            # Who may *hold* work is a narrower list than who is on the
            # project, and resolving against the wider one is how "عيّن المهمة
            # لفلان" reached a review card looking correct and then failed at
            # execution: the tasks API refuses anybody who is not an active
            # Engineer, Worker, Consultant or this project's own Manager. The
            # assistant now applies that rule before proposing, so an
            # ineligible person is a question rather than a late error.
            team = assignable_people(db, project_id=command.project_id)
        else:
            team = project_people(
                db, project_id=command.project_id, exclude_user_id=None
            )
            owner = project_owner(db, command.project_id)
            if owner is not None and not any(
                person.user_id == owner.user_id for person in team
            ):
                team = [*team, owner]
        # An identifier the model supplied is *checked*, never trusted: it
        # survives only if it names somebody actually on this project.
        known = {str(person.user_id) for person in team}
        valid = [
            str(value) for value in resolved.get(key) or []
            if str(value) in known
        ]
        if valid:
            resolved[key] = valid
            continue
        resolved.pop(key, None)
        matched = [
            person for person in match_people(spoken, team)
            if person.user_id != user.id
        ]
        if len(matched) == 1:
            resolved[key] = [str(matched[0].user_id)]
        elif matched:
            options.extend(person.as_option() for person in matched[:MAX_CANDIDATES])
        else:
            options.extend(
                person.as_option()
                for person in team
                if person.user_id != user.id
            )
    return resolved, options, warnings


#: Which people field each capability carries. Kept explicit so a recipient can
#: never be written onto an action that has no business having one.
_PEOPLE_FIELDS_BY_ACTION = {
    SuggestedActionType.SEND_PROJECT_MESSAGE: ("recipientIds",),
    SuggestedActionType.SEND_OWNER_UPDATE: ("recipientIds",),
    SuggestedActionType.UPDATE_TASK_ASSIGNMENT: ("assigneeIds",),
    SuggestedActionType.ASSIGN_ISSUE: ("assigneeIds",),
    SuggestedActionType.CREATE_ISSUE: ("recipientIds",),
}


def _echoes_the_request(title, spoken: str) -> bool:
    """Whether a proposed title is just the instruction repeated back.

    Compared whole rather than by keyword: a real description shares words with
    the request ("سجل مشكلة إن المواد ما وصلت" → "المواد ما وصلت") and only an
    echo is the *entire* utterance.
    """
    from app.services.voice_task_matcher import normalize

    text = normalize(str(title or ""))
    heard = normalize(spoken)
    if not text or not heard:
        return False
    return text == heard or (len(heard.split()) <= 6 and heard.startswith(text))


def _today():
    """Today, in the timezone the rest of the scheduling code uses."""
    return datetime.now(timezone.utc).date()


def _refuse_capability(
    db: Session, *, command: VoiceAnalysis, capability, language: str
) -> None:
    """Say that this person cannot do this, and stop.

    Reached only when the *platform* would refuse: the registry mirrors its
    rules, and the operation's own service checks again for anything that gets
    past. Saying it here, in one sentence, is the difference between "ما عندك
    صلاحية لتعديل مواعيد المهام" and walking somebody through a confirmation
    card that fails the moment they press it.
    """
    arabic = f"ما عندك صلاحية {_PURPOSE_AR.get(capability.action, 'تعمل هذا التعديل')}."
    english = f"You do not have permission to {capability.purpose}."
    _record_answer(command, VoiceAnswer(
        topic="NOT_PERMITTED",
        text_en=english,
        text_ar=arabic,
        data={},
        language=language,
        spoken_text=arabic if language.startswith("ar") else english,
    ))
    db.flush()
    transition(command, VoiceAnalysisStatus.COMPLETED)


#: The Arabic half of a refusal. Written out rather than translated at runtime
#: because "you do not have permission to update how far along a task is" is
#: not a sentence anybody says in either language.
_PURPOSE_AR: dict[SuggestedActionType, str] = {
    SuggestedActionType.CREATE_TASK: "تنشئ مهام",
    SuggestedActionType.START_TASK: "تبدأ المهام",
    SuggestedActionType.UPDATE_TASK_PROGRESS: "تحدّث نسبة إنجاز المهام",
    SuggestedActionType.UPDATE_TASK_SCHEDULE: "تعدّل مواعيد المهام",
    SuggestedActionType.UPDATE_TASK_ASSIGNMENT: "تغيّر المسؤول عن المهام",
    SuggestedActionType.UPDATE_TASK_PRIORITY: "تغيّر أولوية المهام",
    SuggestedActionType.UPDATE_TASK_DETAILS: "تعدّل تفاصيل المهام",
    SuggestedActionType.DELETE_TASK: "تحذف المهام",
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW: "ترسل المهام للمراجعة",
    SuggestedActionType.CREATE_ISSUE: "تسجّل مشاكل",
    SuggestedActionType.UPDATE_ISSUE_STATUS: "تغيّر حالة المشاكل",
    SuggestedActionType.ASSIGN_ISSUE: "تغيّر المسؤول عن المشاكل",
    SuggestedActionType.CREATE_FIELD_SUBMISSION: "تسجّل تقارير ميدانية",
    SuggestedActionType.ADD_TASK_NOTE: "تضيف ملاحظات على المهام",
    SuggestedActionType.CREATE_SITE_REPORT_DRAFT: "ترفع تقارير موقع",
    SuggestedActionType.CREATE_TASK_MESSAGE: "تكتب رسائل على المهام",
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW: "تسجّل قرارات المراجعة",
    SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT: "تسجّل تغييرات التصميم",
    SuggestedActionType.SEND_PROJECT_MESSAGE: "تبعت رسائل على المشروع",
    SuggestedActionType.SEND_OWNER_UPDATE: "تبعت رسائل لصاحب المشروع",
}


def _finish_action_drafts(
    db: Session,
    *,
    command: VoiceAnalysis,
    candidates: list[Task],
    language: str,
    ranked: dict[str, list[TaskMatch]],
    options: dict[str, list[dict]] | None = None,
    result: ConstructionVoiceResult | None = None,
    user: User | None = None,
) -> None:
    """Ask for anything still missing, then settle the command's status.

    Shared by the ordinary drafting path and by a request continued from an
    earlier utterance, so a half-finished request that is completed in two
    breaths lands in exactly the same state as one said in a single breath.
    """
    db.flush()
    if not command.action_drafts:
        # Routed to a write, but nothing survived to draft — the model named a
        # messaging intent without a handler, or every proposal was refused.
        # There is still a person waiting, and what they need is the question
        # this path can actually ask: what would you like me to do about it?
        if result is not None:
            _ask_neutral_clarification(
                db, command=command, result=result, user=user, language=language,
            )
            return
    create_target_clarifications(
        db, command, candidates=candidates, ranked=ranked, options=options,
        language=language, spoken=command.raw_transcript,
    )
    complete = bool(command.action_drafts) and not any(
        draft.missing_fields for draft in command.action_drafts
    )
    if complete:
        _record_review_summary(db, command, language=language)
    else:
        # Whatever is outstanding, the engineer is being asked about it — so
        # the reply is that question, and the review card stays away until
        # there is a complete proposal to review. An incomplete card reading
        # "Task: unknown" is not a review; it is a puzzle.
        _record_pending_question(command, language=language)
    transition(
        command,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION
        if complete
        # Nothing executable, or something still unresolved: either way there
        # is a question outstanding and nothing to confirm.
        else VoiceAnalysisStatus.NEEDS_CLARIFICATION,
    )


def _record_review_summary(
    db: Session, command: VoiceAnalysis, *, language: str
) -> None:
    """Say what is about to happen, above the review card.

    Someone who has just spoken two sentences a minute apart cannot be expected
    to reconstruct the request from a card of fields. One sentence — "تمام،
    بحدّث المهمة الثالثة لـ50%، راجعها وأكدها" — restores the thread. It is
    phrased as a proposal, never as a completion: nothing has been written, and
    the confirm button is still the only thing that writes.
    """
    described: list[dict] = []
    for draft in command.action_drafts:
        try:
            action_type = SuggestedActionType(draft.action_type)
        except ValueError:  # pragma: no cover — an action type we no longer ship
            continue
        task_label = None
        if draft.target_entity_id:
            target = db.get(Task, draft.target_entity_id)
            if target is not None:
                task_label = (
                    f"{target.task_code} — {target.name}"
                    if target.task_code
                    else target.name
                )
        described.append(describe_understood(
            action_type,
            dict(draft.user_edited_payload or draft.extracted_payload or {}),
            task_label=task_label,
        ))
    if not described:
        return
    arabic = language.startswith("ar")
    fallback_ar = "تمام، جهّزت التعديل. راجعه وأكّده."
    fallback_en = "Ready — have a look at this and confirm it."
    sentence = fallback_ar if arabic else fallback_en
    composer = VoiceResponseComposer()
    if composer.available:
        # A daily update can propose several things at once; the sentence
        # covers all of them, because confirming is one decision.
        sentence = composer.compose_confirmation(
            spoken=command.raw_transcript or command.normalized_transcript or "",
            understood=described[0] if len(described) == 1 else {"changes": described},
            language=language,
            fallback=sentence,
        )
    _record_answer(command, VoiceAnswer(
        topic="REVIEW",
        text_en=fallback_en if arabic else sentence,
        text_ar=sentence if arabic else fallback_ar,
        data={},
        language=language,
        spoken_text=sentence,
    ))


def _record_pending_question(command: VoiceAnalysis, *, language: str) -> None:
    """Surface the outstanding question as the command's spoken reply.

    Every client already renders the answer text. Putting the question there
    too means a half-finished request reads as a conversation — "تمام، فهمت إن
    التقدم صار 50%. أي مهمة تقصدي؟" — on any surface, including ones that never
    learned about clarification cards.
    """
    unanswered = [item for item in command.clarifications if not item.answer_text]
    if not unanswered:
        return
    question = unanswered[0]
    _record_answer(command, VoiceAnswer(
        topic="CLARIFICATION",
        text_en=question.question_en,
        text_ar=question.question_ar,
        data={},
        language=language,
        spoken_text=(
            question.question_ar
            if language.startswith("ar")
            else question.question_en
        ),
    ))


def create_target_clarifications(
    db: Session,
    command: VoiceAnalysis,
    *,
    candidates: list[Task] | None = None,
    ranked: dict[str, list[TaskMatch]] | None = None,
    options: dict[str, list[dict]] | None = None,
    language: str = "en",
    spoken: str | None = None,
) -> None:
    """Ask one targeted question per unresolved field.

    Every field a draft is missing becomes a question here — not just the task
    target, which is all this used to handle. An issue with no problem in it, a
    site report with nothing to report, a schedule change with no date, a
    message with nobody to send it to: each one used to reach the schema, fail
    validation, and surface as a processing error. They are all the same
    situation, and it is a question.

    Whatever could be offered as a choice is: the tasks that fit what was said,
    the two days a bare weekday could mean, the people who share the name that
    was spoken. `ranked` carries the task shortlist per draft and `options`
    carries everything resolution produced. When neither has anything, the
    question still stands on its own — an engineer can always answer in words.

    The wording is phrased by the model where that is available and by the
    tables in `voice_action_requirements` where it is not. Both say the same
    thing; only one of them sounds like a person.
    """
    composer = VoiceResponseComposer()
    sequence = len(command.clarifications)
    heard = spoken or command.raw_transcript or command.normalized_transcript or ""
    asked = {
        (item.voice_action_draft_id, item.field_path)
        for item in command.clarifications
        if not item.answer_text
    }

    for draft in command.action_drafts:
        payload = dict(draft.user_edited_payload or draft.extracted_payload or {})
        try:
            action_type = SuggestedActionType(draft.action_type)
        except ValueError:  # pragma: no cover — an action type we no longer ship
            continue
        # Only the first outstanding field is asked about. Two questions at
        # once is a form, and the answer to "which task?" often makes the rest
        # answerable without asking at all.
        for path in list(draft.missing_fields):
            prompt = prompt_for(path)
            if prompt is None or (draft.id, path) in asked:
                continue

            choices = _field_options(
                db,
                command=command,
                draft=draft,
                path=path,
                prompt=prompt,
                ranked=ranked,
                resolved=options,
                candidates=candidates,
            )
            question_ar, question_en = _phrase_question(
                composer,
                action_type=action_type,
                payload=payload,
                prompt=prompt,
                heard=heard,
                language=language,
                labels=[
                    str(item["label"]) for item in choices if item.get("label")
                ],
                task_label=_target_label(db, draft),
            )
            # Said *before* the question and after the phrasing, so it can
            # never be paraphrased away. An engineer who named somebody and is
            # then simply asked "who?" has been told nothing about what went
            # wrong; naming the person who could not be found is the whole
            # difference between a dead end and a conversation.
            note_ar, note_en = _unresolved_person_note(path, heard, choices)
            if note_ar:
                question_ar = f"{note_ar} {question_ar}".strip()
                question_en = f"{note_en} {question_en}".strip()
            sequence += 1
            command.clarifications.append(VoiceClarification(
                voice_action_draft_id=draft.id,
                sequence=sequence,
                field_path=path,
                question_ar=question_ar,
                question_en=question_en,
                expected_answer_type=prompt.answer_type,
                options=choices[:MAX_CANDIDATES],
            ))
            break
    # No "do you want to add a note or report an issue?" here any more.
    #
    # That question offered an engineer who had asked for neither a choice
    # between two mutations, and it fired whenever the model proposed nothing —
    # which is most often precisely because nothing should be proposed. Routing
    # decides the reply now: an unanswerable question says so, and an
    # unclassifiable utterance gets `_ask_neutral_clarification`. Draft-building
    # only ever asks about fields a draft actually needs.


#: The two questions that are about a person, and the only ones the note below
#: applies to.
_PERSON_PATHS = frozenset({"payload.assignee", "payload.recipients"})


def _unresolved_person_note(
    path: str, heard: str, choices: list[dict]
) -> tuple[str, str]:
    """Why the person the engineer named is not in the answer, in one clause.

    Returns two empty strings whenever there is nothing honest to say — no
    person question, no name recoverable from the utterance, or a name that
    *does* appear among the people on offer. Only a name that was spoken and
    matches nobody available produces a sentence, which is exactly the case
    that used to surface as a bare "who should be responsible for it?" and,
    if the engineer pressed on, as a generic execution failure.

    The available people are the ones already being offered as options, so the
    note and the option list can never contradict each other.
    """
    if path not in _PERSON_PATHS:
        return "", ""
    name = named_person_reference(heard)
    if not name:
        return "", ""
    available = [
        Person(item["value"], str(item.get("label") or ""), str(item.get("role") or ""))
        for item in choices
        if item.get("value") is not None
    ]
    if match_people(name, available):
        return "", ""
    if path == "payload.assignee":
        return (
            f"ما لقيت حدا اسمه «{name}» ضمن أعضاء المشروع اللي بيقدروا يستلموا هاي المهمة.",
            f"I could not find anyone called \"{name}\" among the project members "
            "who can take this task.",
        )
    return (
        f"ما لقيت حدا اسمه «{name}» ضمن أعضاء المشروع.",
        f"I could not find anyone called \"{name}\" on this project.",
    )


def _field_options(
    db: Session,
    *,
    command: VoiceAnalysis,
    draft: VoiceActionDraft,
    path: str,
    prompt,
    ranked: dict[str, list[TaskMatch]] | None,
    resolved: dict[str, list[dict]] | None,
    candidates: list[Task] | None,
) -> list[dict]:
    """What this question can offer as a tap instead of a sentence."""
    supplied = [
        item for item in (resolved or {}).get(draft.client_action_id, [])
        if _option_fits(path, item)
    ]
    if supplied:
        return supplied
    if path == TARGET_TASK:
        shortlist = (ranked or {}).get(draft.client_action_id)
        if shortlist is None:
            shortlist = match_task(
                command.normalized_transcript or command.raw_transcript,
                list(candidates or []),
            ).candidates
        return [match.as_option() for match in shortlist[:MAX_CANDIDATES]]
    if path == TARGET_ISSUE:
        return [
            {"value": str(issue.id), "label": issue.title,
             "status": str(getattr(issue.status, "value", issue.status))}
            for issue in authorized_issues(db, project_id=command.project_id)[
                :MAX_CANDIDATES
            ]
        ]
    if prompt.answer_type == "NUMBER":
        return [
            {"value": 25, "label": "25%"},
            {"value": 50, "label": "50%"},
            {"value": 75, "label": "75%"},
            {"value": 100, "label": "100%"},
        ]
    if path in {"payload.recipients", "payload.assignee"}:
        # The project's own team, so choosing is a tap and typing a name is
        # never required. An assignment offers only the people who may actually
        # hold work: an option the tasks API would refuse is not an option.
        people = (
            assignable_people(db, project_id=command.project_id)
            if path == "payload.assignee"
            else project_people(
                db, project_id=command.project_id, exclude_user_id=command.user_id
            )
        )
        return [person.as_option() for person in people[:MAX_CANDIDATES]]
    if path == "payload.priority":
        return [
            {"value": "low", "label": "Low"},
            {"value": "medium", "label": "Medium"},
            {"value": "high", "label": "High"},
            {"value": "critical", "label": "Critical"},
        ]
    if path == "payload.issueStatus":
        return [
            {"value": "in_progress", "label": "In progress"},
            {"value": "resolved", "label": "Resolved"},
            {"value": "closed", "label": "Closed"},
            {"value": "open", "label": "Reopen"},
        ]
    return []


def _option_fits(path: str, option: dict) -> bool:
    """Whether an option resolution produced belongs to this question.

    Resolution collects options for whatever it could not settle — two dates,
    two people — onto one list per draft. A person is not an answer to "which
    date?", so each question takes only the options shaped like its own field.
    """
    value = str(option.get("value") or "")
    if path == "payload.dueDate":
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
    if path in {"payload.recipients", "payload.assignee"}:
        return "role" in option
    if path == TARGET_ISSUE:
        return "status" in option and "score" in option
    return False


def _target_label(db: Session, draft: VoiceActionDraft) -> str | None:
    """The task this draft is about, as an engineer would name it."""
    if not draft.target_entity_id or draft.target_entity_type != "TASK":
        return None
    target = db.get(Task, draft.target_entity_id)
    if target is None:
        return None
    return f"{target.task_code} — {target.name}" if target.task_code else target.name


def _phrase_question(
    composer: VoiceResponseComposer,
    *,
    action_type: SuggestedActionType,
    payload: dict,
    prompt,
    heard: str,
    language: str,
    labels: list[str],
    task_label: str | None,
) -> tuple[str, str]:
    """One question, in both halves, with the spoken language phrased naturally.

    The other language keeps the plain template: it is the fallback for a
    client that has to render something, and spending a second provider call on
    a sentence nobody will read would be waste.
    """
    question_ar = prompt.question_ar
    question_en = prompt.question_en
    if not composer.available:
        return question_ar, question_en
    phrased = composer.compose_clarification(
        spoken=heard,
        understood=describe_understood(action_type, payload, task_label=task_label),
        missing=prompt.description,
        language=language,
        fallback=question_ar if language.startswith("ar") else question_en,
        options=labels,
    )
    if language.startswith("ar"):
        return phrased, question_en
    return question_ar, phrased


def update_draft(
    db: Session,
    *,
    command: VoiceAnalysis,
    draft: VoiceActionDraft,
    update: VoiceDraftUpdate,
    user: User,
) -> VoiceActionDraft:
    assert_command_access(db, command, user, owner_only=True)
    assert_version(command, update.row_version)
    if command.status not in {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    }:
        raise HTTPException(status_code=409, detail="This draft is no longer editable")
    if draft.voice_analysis_id != command.id:
        raise HTTPException(status_code=404, detail="Draft action not found")
    if update.target_id:
        allowed = {task.id for task in authorized_voice_tasks(db, user, command.project_id)}
        if update.target_id not in allowed:
            raise HTTPException(status_code=422, detail="Selected task is outside the allowed task list")
        task = db.get(Task, update.target_id)
        draft.target_entity_type = "TASK"
        draft.target_entity_id = task.id
        draft.target_snapshot = {
            "taskId": str(task.id),
            "status": task.status.value,
            "progressPercentage": float(task.progress_percentage or 0),
            "updatedAt": task.updated_at.isoformat(),
        }
    draft.user_edited_payload = dict(update.payload)
    draft.selected_for_execution = update.selected_for_execution
    # Recomputed from the edited payload rather than patched: an engineer who
    # types the missing description into the card has answered the question,
    # and the draft must stop reporting it as outstanding.
    draft.missing_fields = missing_fields(
        SuggestedActionType(draft.action_type),
        dict(draft.user_edited_payload or draft.extracted_payload or {}),
        has_target=draft.target_entity_id is not None,
    )
    command.row_version += 1
    if all(not item.missing_fields for item in command.action_drafts):
        if command.status == VoiceAnalysisStatus.NEEDS_CLARIFICATION:
            transition(command, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)
    record_audit(
        db,
        actor_id=user.id,
        action="voice_draft_edited",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={"draft_id": draft.id, "action_type": draft.action_type},
    )
    db.commit()
    db.refresh(draft)
    return draft


def answer_clarification(
    db: Session,
    *,
    command: VoiceAnalysis,
    clarification: VoiceClarification,
    answer: str,
    user: User,
) -> bool:
    """Fold one typed or tapped answer back into the request that asked for it.

    Returns True when the answer still has to be *interpreted* — when the
    question it answered was not attached to any draft, so there is no field to
    put it in. "ما فهمت قصدك، ممكن توضحيلي؟" is exactly that question, and its
    answer used to be stored and then dropped: the request had no draft to
    complete, nothing re-read the answer, and the engineer was left looking at
    a screen with the clarification card gone and nothing in its place. The
    caller re-runs interpretation on the two utterances together.

    The spoken equivalent lives in `voice_conversation_service`: an engineer
    who answers by talking gets a new recording, and that recording is merged
    into this same pending request. Both routes end in the same place — the
    field filled, the next question asked if there is one, and the review card
    shown only once nothing is outstanding.
    """
    assert_command_access(db, command, user, owner_only=True)
    if command.status != VoiceAnalysisStatus.NEEDS_CLARIFICATION:
        raise HTTPException(status_code=409, detail="This command is not waiting for clarification")
    if clarification.voice_analysis_id != command.id or clarification.answer_text:
        raise HTTPException(status_code=409, detail="Clarification is unavailable or already answered")
    clean = answer.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Please say or type an answer.")

    language = str(
        (command.provider_metadata or {}).get("replyLanguage")
        or reply_language(command.raw_transcript, command.detected_language)
    )
    candidates = authorized_voice_tasks(db, user, command.project_id)
    draft = (
        db.get(VoiceActionDraft, clarification.voice_action_draft_id)
        if clarification.voice_action_draft_id
        else None
    )

    unresolved = False
    if clarification.expected_answer_type == "TASK_SELECTION":
        task = _selected_task(clean, candidates, language=language)
        if draft is not None:
            draft.target_entity_type = "TASK"
            draft.target_entity_id = task.id
            draft.target_snapshot = {
                "taskId": str(task.id),
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "updatedAt": task.updated_at.isoformat(),
            }
        elif clarification.field_path == "query.taskId":
            # A question that needed a subject. Answering it answers the
            # question, rather than merely recording which task was meant.
            _answer_after_selection(
                db, command=command, user=user, task=task, language=language,
                tasks=candidates,
            )
    elif clarification.expected_answer_type == "NUMBER":
        progress = _spoken_number(clean)
        if progress is None or not 0 <= progress <= 100:
            raise HTTPException(
                status_code=422,
                detail=(
                    "بدي نسبة بين 0 و100، مثلاً 50."
                    if language.startswith("ar")
                    else "Give me a percentage between 0 and 100 — 50, for example."
                ),
            )
        if draft is not None:
            draft.user_edited_payload = {
                **dict(draft.user_edited_payload or draft.extracted_payload or {}),
                "progressPercentage": progress,
            }
    elif clarification.expected_answer_type == "ISSUE_SELECTION" and draft is not None:
        issues = authorized_issues(db, project_id=command.project_id)
        issue_id, _ = match_issue(clean, issues)
        if issue_id is None:
            try:
                chosen = UUID(clean)
            except ValueError:
                chosen = None
            issue_id = next(
                (item.id for item in issues if item.id == chosen), None
            )
        if issue_id is None:
            unresolved = True
        else:
            draft.target_entity_type = "ISSUE"
            draft.target_entity_id = issue_id
    elif clarification.expected_answer_type == "DATE" and draft is not None:
        found = resolve_date_field(clean, today=_today())
        if found is None or not found.is_resolved:
            unresolved = True
        else:
            draft.user_edited_payload = {
                **dict(draft.user_edited_payload or draft.extracted_payload or {}),
                "dueDate": found.value.isoformat(),
            }
    elif (
        clarification.expected_answer_type == "PERSON_SELECTION"
        and draft is not None
    ):
        chosen = _resolved_people(
            db, command=command, user=user, answer=clean,
            path=clarification.field_path,
        )
        if not chosen:
            unresolved = True
        else:
            key = (
                "assigneeIds"
                if clarification.field_path == "payload.assignee"
                else "recipientIds"
            )
            draft.user_edited_payload = {
                **dict(draft.user_edited_payload or draft.extracted_payload or {}),
                key: [str(person.user_id) for person in chosen],
            }
    elif clarification.field_path == "payload.recipients" and draft is not None:
        chosen = _resolved_people(db, command=command, user=user, answer=clean)
        if not chosen:
            unresolved = True
        else:
            draft.user_edited_payload = {
                **dict(draft.user_edited_payload or draft.extracted_payload or {}),
                "recipientIds": [str(person.user_id) for person in chosen],
            }
    elif draft is not None and prompt_for(clarification.field_path) is not None:
        draft.user_edited_payload = apply_answer(
            clarification.field_path,
            dict(draft.user_edited_payload or draft.extracted_payload or {}),
            clean,
        )

    if draft is not None:
        # Recomputed rather than edited: the same table that decided a field
        # was missing decides it is now present, so the two can never disagree.
        draft.missing_fields = missing_fields(
            SuggestedActionType(draft.action_type),
            dict(draft.user_edited_payload or draft.extracted_payload or {}),
            has_target=draft.target_entity_id is not None,
        )

    clarification.answer_text = clean
    clarification.answer_source = "TEXT"
    clarification.answered_at = datetime.now(timezone.utc)
    command.row_version += 1

    outstanding = [item for item in command.action_drafts if item.missing_fields]
    if outstanding:
        # One question at a time. Answering "which task?" often makes the next
        # field obvious, so the next question is only written now, with the
        # extra context the answer just supplied.
        create_target_clarifications(
            db, command, candidates=candidates, language=language,
        )
        _record_pending_question(command, language=language)
    elif command.action_drafts:
        _record_review_summary(db, command, language=language)
        transition(command, VoiceAnalysisStatus.READY_FOR_CONFIRMATION)

    # An answer with nowhere to go is not an answer yet — either because the
    # question belonged to no draft, or because what was said does not fit the
    # field that was asked about. People answer the question they have in mind
    # rather than the one on the screen ("لصاحب المشروع" to "what should it
    # say?"), and a 422 for that is the assistant blaming them for listening
    # imperfectly. Both cases go back through interpretation together.
    needs_interpretation = unresolved or (draft is None and not command.action_drafts)

    record_audit(
        db,
        actor_id=user.id,
        action="voice_clarification_answered",
        entity_type="voice_analysis",
        entity_id=command.id,
        project_id=command.project_id,
        details={
            "clarification_id": clarification.id,
            "field_path": clarification.field_path,
            "needs_interpretation": needs_interpretation,
        },
    )
    if not needs_interpretation:
        # Nothing further will run, so this is the last chance to be sure the
        # engineer has something to look at.
        ensure_visible_state(command, language=language, reason="clarification")
    db.commit()
    return needs_interpretation


def _selected_task(answer: str, candidates: list[Task], *, language: str) -> Task:
    """The task an answer names — by id, by position, or by what it says.

    Typed answers arrive as an identifier when the engineer tapped an option
    and as words when they typed or spoke. Both are accepted, because "المهمة
    السادسة" is a perfectly clear answer that the option list happens not to
    contain as a value.
    """
    try:
        chosen = UUID(answer)
    except ValueError:
        chosen = None
    if chosen is not None:
        task = next((item for item in candidates if item.id == chosen), None)
        if task is None:
            raise HTTPException(status_code=422, detail="Selected task is not available")
        return task

    positioned = match_by_position(answer, candidates)
    if positioned is not None:
        return positioned
    outcome = match_task(answer, candidates)
    if outcome.is_resolved:
        task = next(
            (item for item in candidates if item.id == outcome.resolved_task_id), None
        )
        if task is not None:
            return task
    raise HTTPException(
        status_code=422,
        detail=(
            "ما عرفت أي مهمة تقصد. احكيلي اسمها أو رقمها."
            if language.startswith("ar")
            else "I could not tell which task that is. Tell me its name or its number."
        ),
    )


def _resolved_people(
    db: Session, *, command: VoiceAnalysis, user: User, answer: str,
    path: str = "payload.recipients",
) -> list:
    """Everybody an answer names, or nothing. Never guesses between two people.

    Sending the wrong person a project update is not recoverable by editing a
    field afterwards, so two matches resolve to nothing and the request is
    re-read in context — which asks again rather than picking one.

    An assignment resolves against the people who may hold work rather than
    against the whole team, for the same reason the drafting path does: a name
    that resolves to somebody the tasks API will refuse is not resolved, it is
    a failure postponed to execution.
    """
    if path == "payload.assignee":
        matched = match_people(
            answer, assignable_people(db, project_id=command.project_id)
        )
    else:
        matched = resolve_recipients(
            db, project_id=command.project_id, speaker_id=user.id, spoken=answer,
        )
    return matched if len(matched) == 1 else []


#: Arabic-Indic digits, so "٥٠" is a percentage exactly as "50" is.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _spoken_number(answer: str) -> float | None:
    text = answer.translate(_ARABIC_DIGITS).replace("%", " ").replace("٪", " ")
    found = re.search(r"\d+(?:\.\d+)?", text)
    return float(found.group()) if found else None


def _answer_after_selection(
    db: Session,
    *,
    command: VoiceAnalysis,
    user: User,
    task: Task,
    language: str,
    tasks: list[Task],
) -> None:
    """Re-answer a question once the engineer has said which task they meant."""
    stored = (command.structured_result or {}).get("answer") or {}
    topic = stored.get("topic")
    if not topic:
        return
    try:
        query_topic = VoiceQueryTopic(topic)
    except ValueError:
        return
    from app.schemas.voice_analysis import DetectedQuery

    answer = answer_query(
        db,
        user=user,
        project_id=command.project_id,
        query=DetectedQuery(
            topic=query_topic,
            task_reference=f"{task.task_code or ''} {task.name}".strip(),
        ),
        tasks=tasks,
        spoken=command.raw_transcript,
    )
    if answer is None or not answer.is_answered:
        return
    _record_answer(
        command,
        _phrase_answer(
            db, command=command, answer=answer, tasks=tasks, language=language
        ),
    )
    transition(command, VoiceAnalysisStatus.COMPLETED)
