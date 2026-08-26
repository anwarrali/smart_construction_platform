"""Remembering what was already said, one utterance to the next.

Every recording used to be its own universe. The assistant would ask *"أي مهمة
تقصد؟"*, the engineer would answer *"المهمة السادسة"*, and that answer arrived
as a brand-new request with no percentage, no verb, and nothing to do — so it
was met with "I did not catch what you would like to do." The engineer had to
say the whole sentence again, which is the interaction the feature exists to
remove.

What was missing was not memory in the model. It was the observation that an
unanswered question is *state the backend already stores*: a command sitting in
NEEDS_CLARIFICATION with drafts that name exactly which fields are outstanding.
This module reads that state and decides whether the new utterance completes
it.

Three rules keep it from doing harm:

  * **Only ever completes; never invents.** A merge copies the *pending*
    request forward and fills in the one field that was missing. It cannot
    create an action, change an action type, or alter a field that was already
    known.
  * **A new request wins.** If the new utterance proposes something of its own,
    it is a new request and is handled as one. Continuation is for utterances
    that make no sense on their own — which is precisely what an answer to a
    question is.
  * **Confirmation is untouched.** A completed request lands in exactly the
    same review-and-confirm state it would have reached had it been said in one
    breath. Nothing here executes anything.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import VoiceAnalysisStatus
from app.models.task import Task
from app.models.user import User
from app.models.voice_action import VoiceActionDraft
from app.models.voice_analysis import VoiceAnalysis
from app.schemas.voice_analysis import (
    ConstructionVoiceResult,
    SuggestedActionType,
    VoiceQueryTopic,
    VoiceRequestKind,
)
from app.services.voice_action_requirements import (
    TARGET_ISSUE,
    TARGET_TASK,
    apply_answer,
    issue_status_value,
    missing_fields,
    priority_value,
)
from app.services.voice_dates import resolve_spoken_date
from app.services.voice_entity_resolution import (
    assignable_people,
    authorized_issues,
    match_issue,
    match_people,
    resolve_recipients,
)
from app.services.voice_task_matcher import (
    match_by_position,
    match_task,
    normalize,
)

logger = logging.getLogger(__name__)

#: A spoken answer to "which task?" only has to beat this to be accepted. Lower
#: than the threshold used when interpreting a whole sentence, and deliberately
#: so: the question narrowed the space to "a task name", so far less of the
#: utterance is noise. The engineer still sees the resolved task on the review
#: card before anything executes.
FOLLOW_UP_CONFIDENCE = 0.45

#: Field paths whose answer is the engineer's words, verbatim. An ordinal or a
#: bare number is never one of these — see `_is_positional_only`.
_TEXT_ANSWER_PATHS = frozenset({
    "payload.issue",
    "payload.taskTitle",
    "payload.description",
    "payload.content",
    "payload.summaryText",
    "payload.comments",
})


def find_open_request(
    db: Session, *, user: User, project_id, exclude_id=None
) -> VoiceAnalysis | None:
    """The engineer's most recent unfinished request in this project, if any.

    Scoped to one speaker and one project, and time-boxed: an answer given
    twenty minutes later is still an answer, an answer given tomorrow is a new
    conversation. `NEEDS_CLARIFICATION` is the only status that qualifies —
    everything else is either finished, waiting on a confirmation the engineer
    can press, or cancelled.
    """
    window = max(1, int(settings.VOICE_CONVERSATION_WINDOW_MINUTES))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)
    query = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.user_id == user.id,
        VoiceAnalysis.project_id == project_id,
        VoiceAnalysis.status == VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysis.created_at >= cutoff,
    )
    if exclude_id is not None:
        query = query.filter(VoiceAnalysis.id != exclude_id)
    return query.order_by(VoiceAnalysis.created_at.desc()).first()


def outstanding_drafts(command: VoiceAnalysis) -> list[VoiceActionDraft]:
    """Drafts on a pending command that are still waiting on something."""
    return [draft for draft in command.action_drafts if draft.missing_fields]


def pending_summary(command: VoiceAnalysis, *, include_open_question: bool = False) -> dict:
    """What is still open, in the shape the analysis prompt is given.

    Sent to the interpreting model so it can read "المهمة السادسة" as an answer
    rather than as a fragment. Deliberately small: what was asked for, and what
    is already known.

    `include_open_question` carries a question that has *no field behind it* —
    "شو بدك أعمل بهالمعلومة؟". That is useful to exactly one utterance, the
    answer to it, and actively harmful to any other: an abandoned question sat
    in the window for twenty minutes and coloured every later request, so
    "بدي أرفع مشكلة" came back asking about materials nobody had mentioned. The
    clarification path sets it; the ordinary path does not.
    """
    spoken_earlier = command.raw_transcript or command.normalized_transcript or ""
    drafts = outstanding_drafts(command)
    if drafts:
        draft = drafts[0]
        return {
            "wasAskedFor": list(draft.missing_fields),
            "alreadyUnderstood": dict(
                draft.user_edited_payload or draft.extracted_payload or {}
            ),
            "spokenEarlier": spoken_earlier,
        }
    # A question with no draft behind it — "ما فهمت قصدك، ممكن توضحيلي؟" — is
    # still a question the speaker is answering. Carrying the *wording* lets
    # the model read the next utterance as the clarification it is rather than
    # as a fragment about nothing.
    asked = list(command.clarifications) if include_open_question else []
    if not asked:
        return {}
    latest = asked[-1]
    return {
        "wasAsked": latest.question_ar or latest.question_en,
        "spokenEarlier": spoken_earlier,
        **({"answeredWith": latest.answer_text} if latest.answer_text else {}),
    }


def is_possible_answer(result: ConstructionVoiceResult) -> bool:
    """True when this utterance could be completing an earlier request.

    Two kinds of utterance are excluded outright:

      * one that **proposes its own action** — that is a new instruction, and
        merging it would silently attach today's issue report to yesterday's
        progress question;
      * one that is a **classified question** — "شو المهام اللي ضايلة؟" asked
        while a request is open is a read, not an answer, and must not be
        matched against the open request's missing task. A question whose topic
        the model could not name is *not* excluded, because a bare "المهمة
        السادسة" sometimes classifies that way.

    Everything else is a candidate, and `merge_followup` decides for certain by
    trying to extract the field that was actually missing.
    """
    if result.suggested_actions:
        return False
    asked = result.request_kind in {
        VoiceRequestKind.QUESTION, VoiceRequestKind.REASONING
    }
    return not (asked and result.query.topic != VoiceQueryTopic.UNKNOWN)


def _proposed_payload(result: ConstructionVoiceResult, action_type: str) -> dict:
    """The payload the model attached to a re-proposal of this same action."""
    for action in result.suggested_actions:
        if action.type.value == action_type:
            return action.payload_dict()
    return {}


def _payload_date(value):
    """A date field from a re-proposed payload, resolved the usual way.

    Accepts both an ISO value and the speaker's own words, because the model is
    told to pass wording through and a corrected draft carries a real date.
    """
    from app.services.voice_entity_resolution import resolve_date_field

    text = str(value or "").strip()
    return resolve_date_field(text) if text else None


#: Payload keys a text question is answered from, when the answer arrived
#: inside a re-proposed action rather than as loose speech.
_TEXT_PAYLOAD_KEYS: dict[str, tuple[str, ...]] = {
    "payload.issue": ("title", "description"),
    "payload.taskTitle": ("title",),
    "payload.description": ("description",),
    "payload.content": ("content",),
    "payload.summaryText": ("summaryText",),
    "payload.comments": ("comments",),
}


def _proposed_text(path: str, proposed: dict) -> str:
    for key in _TEXT_PAYLOAD_KEYS.get(path, ()):
        text = str(proposed.get(key) or "").strip()
        if text:
            return text
    return ""


def continues_pending(
    result: ConstructionVoiceResult,
    pending: VoiceAnalysis,
    tasks: list[Task],
    spoken: str = "",
) -> bool:
    """True when a *re-proposed* action is really the answer to the open question.

    `is_possible_answer` covers the well-behaved case, where the model answers
    "لأي تاريخ بدك تخليه؟" with a bare date and proposes nothing. This covers
    the case that produced the loop seen in acceptance testing: the model
    answers the same question by proposing the *same* action again, carrying
    the date and nothing else. That is not a new instruction — it is the
    instruction already on the screen, restated with the missing piece filled
    in — but it was read as new, so the request lost its task, asked "أي مهمة
    تقصد؟" all over again, and the engineer went round the same three turns.

    Three conditions, all required, so a genuine new request can never be
    swallowed:

      * every proposed handler is one the pending request is already waiting
        on — a different operation is a different request;
      * none of them names a target of its own, because an utterance that says
        *which* task stands on its own;
      * the utterance does not name a different task from the one already
        resolved, which is the one way the first two could both hold and the
        speaker still mean something new.
    """
    drafts = outstanding_drafts(pending)
    if not drafts or not result.suggested_actions:
        return False
    open_types = {draft.action_type for draft in drafts}
    for action in result.suggested_actions:
        if action.type.value not in open_types or action.target_id is not None:
            return False
    heard = spoken or result.original_transcript or result.normalized_transcript or ""
    named = _resolve_task(heard, result, tasks)
    resolved = {draft.target_entity_id for draft in drafts if draft.target_entity_id}
    if named is not None and resolved and named.id not in resolved:
        return False
    return True


def merge_followup(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
    pending: VoiceAnalysis,
    tasks: list[Task],
) -> bool:
    """Carry the pending request onto this command, filled in. True when done.

    The pending command's drafts are *copied* rather than moved: one command
    per utterance is what makes the audio, the transcript and the audit trail
    line up, and a merged draft that lived on the older command would be
    reviewed against the wrong recording.
    """
    drafts = outstanding_drafts(pending)
    if not drafts:
        return False

    spoken = (command.raw_transcript or command.normalized_transcript or "").strip()
    filled_any = False
    carried: list[dict] = []

    for draft in drafts:
        action_type = SuggestedActionType(draft.action_type)
        payload = dict(draft.user_edited_payload or draft.extracted_payload or {})
        target_id = draft.target_entity_id
        snapshot = draft.target_snapshot
        resolved_fields: list[str] = []
        # What the model put in a *re-proposal* of this same action. When it
        # answers "لأي تاريخ؟" by restating the whole action with the date in
        # it, the answer is in the payload rather than loose in the sentence,
        # and reading only the sentence is what left the field unfilled — and
        # the conversation going round again.
        proposed = _proposed_payload(result, draft.action_type)

        for path in list(draft.missing_fields):
            if path == TARGET_TASK and target_id is None:
                task = _resolve_task(spoken, result, tasks)
                if task is not None:
                    target_id = task.id
                    snapshot = {
                        "taskId": str(task.id),
                        "status": task.status.value,
                        "progressPercentage": float(task.progress_percentage or 0),
                        "updatedAt": task.updated_at.isoformat(),
                    }
                    resolved_fields.append(path)
                continue
            if path == TARGET_ISSUE and target_id is None:
                issue_id, _ = match_issue(spoken, authorized_issues(
                    db, project_id=command.project_id
                ))
                if issue_id is not None:
                    target_id = issue_id
                    resolved_fields.append(path)
                continue
            if path == "payload.progressPercentage":
                figure = (
                    float(result.progress.percentage)
                    if result.progress.mentioned
                    and result.progress.percentage is not None
                    else proposed.get("progressPercentage")
                )
                if figure is not None:
                    payload["progressPercentage"] = float(figure)
                    resolved_fields.append(path)
                continue
            if path == "payload.dueDate":
                # "خليها بعد أسبوعين" is the whole answer to "لأي تاريخ؟", and
                # it is a date only after the calendar has been consulted.
                found = resolve_spoken_date(spoken) or _payload_date(
                    proposed.get("dueDate")
                )
                if found is not None and found.value is not None:
                    payload["dueDate"] = found.value.isoformat()
                    resolved_fields.append(path)
                continue
            if path == "payload.priority":
                matched = priority_value(spoken) or priority_value(
                    str(proposed.get("priority") or "")
                )
                if matched:
                    payload["priority"] = matched
                    resolved_fields.append(path)
                continue
            if path == "payload.issueStatus":
                matched = issue_status_value(spoken) or issue_status_value(
                    str(proposed.get("issueStatus") or "")
                )
                if matched:
                    payload["issueStatus"] = matched
                    resolved_fields.append(path)
                continue
            if path in {"payload.recipients", "payload.assignee"}:
                # Assignment resolves against the people who may hold work, so
                # a spoken answer cannot fill the field with somebody the
                # tasks API would refuse a moment later.
                people = (
                    match_people(
                        spoken, assignable_people(db, project_id=command.project_id)
                    )
                    if path == "payload.assignee"
                    else resolve_recipients(
                        db,
                        project_id=command.project_id,
                        speaker_id=user.id,
                        spoken=spoken,
                    )
                )
                if len(people) == 1:
                    key = (
                        "assigneeIds" if path == "payload.assignee" else "recipientIds"
                    )
                    payload[key] = [str(people[0].user_id)]
                    resolved_fields.append(path)
                continue
            if path in _TEXT_ANSWER_PATHS:
                said = _proposed_text(path, proposed) or (
                    spoken if spoken and not _is_positional_only(spoken) else ""
                )
                if said:
                    payload = apply_answer(path, payload, said)
                    resolved_fields.append(path)

        if resolved_fields:
            filled_any = True
        carried.append({
            "action_type": draft.action_type,
            "payload": payload,
            "target_id": target_id,
            "snapshot": snapshot,
            "confidence": float(draft.confidence),
            "risk_level": draft.risk_level,
            "required_evidence": list(draft.required_evidence or []),
            "warnings": list(draft.warnings or []),
            "missing": missing_fields(
                action_type, payload, has_target=target_id is not None
            ),
        })

    if not filled_any:
        # Nothing in this utterance answered the outstanding question. The
        # pending request stays open and this utterance is interpreted on its
        # own merits, which is the right outcome for "actually, forget it —
        # what's left on the project?".
        return False

    _attach(command, carried)

    command.provider_metadata = {
        **(command.provider_metadata or {}),
        "continuedFrom": str(pending.id),
    }
    close(db, pending, reason="continued", successor=command)
    logger.info(
        "voice request %s continued by %s (%s draft(s))",
        pending.id, command.id, len(carried),
    )
    return True


def close(
    db: Session,
    pending: VoiceAnalysis,
    *,
    reason: str,
    successor: VoiceAnalysis | None = None,
) -> None:
    """Retire a pending request so it cannot collect a later, unrelated answer.

    Cancelling is the honest record: the request never reached confirmation and
    nothing it proposed was executed. The reason and the successor are kept
    because "why did my earlier question disappear?" is otherwise unanswerable.
    """
    if pending.status not in {
        VoiceAnalysisStatus.NEEDS_CLARIFICATION,
        VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
    }:
        return
    # Imported here rather than at module scope: `voice_command_service`
    # imports this module, and the state machine belongs there.
    from app.services.voice_command_service import transition

    transition(pending, VoiceAnalysisStatus.CANCELLED)
    pending.provider_metadata = {
        **(pending.provider_metadata or {}),
        "closedReason": reason,
        **({"supersededBy": str(successor.id)} if successor is not None else {}),
    }


#: Words that mark an utterance as a correction of what is already on screen
#: rather than a new request. Deliberately narrow: a correction rewrites a
#: proposal the engineer is looking at, so a false positive edits the wrong
#: thing, while a false negative merely starts a new request they can cancel.
_CORRECTION_MARKERS: tuple[str, ...] = (
    "لا قصدي", "لا انا قصدي", "قصدي", "مش هاي", "مش هذي", "مش هيك", "بدل",
    "غلط", "خطا", "صحح", "عدل", "لا مش",
    "no i meant", "i meant", "actually", "instead", "not that", "correction",
)

#: How long a proposal stays correctable. The same window as a pending
#: question: an engineer looking at a review card and saying "لا، السابعة" is
#: doing it now, not tomorrow.
CORRECTION_WINDOW_MINUTES = 20


def find_correctable_request(
    db: Session, *, user: User, project_id, exclude_id=None
) -> VoiceAnalysis | None:
    """The proposal this speaker is most likely looking at right now.

    Includes `READY_FOR_CONFIRMATION` as well as `NEEDS_CLARIFICATION`, which
    is the whole point: "لا، قصدي المهمة السابعة" is said *at* a review card,
    after every question has already been answered. Nothing has been executed
    in either state, so nothing a correction touches has left the building.
    """
    window = max(1, int(settings.VOICE_CONVERSATION_WINDOW_MINUTES))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)
    query = db.query(VoiceAnalysis).filter(
        VoiceAnalysis.user_id == user.id,
        VoiceAnalysis.project_id == project_id,
        VoiceAnalysis.status.in_([
            VoiceAnalysisStatus.NEEDS_CLARIFICATION,
            VoiceAnalysisStatus.READY_FOR_CONFIRMATION,
        ]),
        VoiceAnalysis.created_at >= cutoff,
    )
    if exclude_id is not None:
        query = query.filter(VoiceAnalysis.id != exclude_id)
    return query.order_by(VoiceAnalysis.created_at.desc()).first()


def is_correction(spoken: str, result: ConstructionVoiceResult) -> bool:
    """Whether this utterance corrects the proposal already on screen.

    Requires an explicit marker. "المهمة السابعة" alone is an answer to a
    question; "لا، قصدي المهمة السابعة" is a correction of an answer already
    given, and the difference decides whether a value is filled in or
    overwritten.
    """
    if result.suggested_actions:
        return False
    text = normalize(spoken)
    if not text:
        return False
    if any(normalize(marker) in text for marker in _CORRECTION_MARKERS):
        return True
    # A bare "no" at the front, which is how most corrections actually start:
    # "لا، خليها 20 سبتمبر". Only at the front, and only with something after
    # it, so a sentence that merely contains a negation is not swept up.
    words = text.split()
    return len(words) > 1 and words[0] in {"لا", "لاء", "no", "nope"}


def apply_correction(
    db: Session,
    *,
    command: VoiceAnalysis,
    result: ConstructionVoiceResult,
    user: User,
    pending: VoiceAnalysis,
    tasks: list[Task],
) -> bool:
    """Rewrite the pending proposal with what the speaker just changed.

    Only values actually present in the correction are touched — "لا، قصدي
    السابعة" changes the task and leaves the percentage exactly where it was,
    which is what makes it a correction rather than a restart. Everything then
    goes back through the ordinary review: a corrected proposal is still a
    proposal, and it is confirmed like any other.
    """
    drafts = list(pending.action_drafts)
    if not drafts:
        return False
    spoken = (command.raw_transcript or command.normalized_transcript or "").strip()

    changed = False
    carried: list[dict] = []
    for draft in drafts:
        action_type = SuggestedActionType(draft.action_type)
        payload = dict(draft.user_edited_payload or draft.extracted_payload or {})
        target_id = draft.target_entity_id
        snapshot = draft.target_snapshot

        task = _resolve_task(spoken, result, tasks)
        if task is not None and task.id != target_id and draft.target_entity_type != "ISSUE":
            target_id = task.id
            snapshot = {
                "taskId": str(task.id),
                "status": task.status.value,
                "progressPercentage": float(task.progress_percentage or 0),
                "updatedAt": task.updated_at.isoformat(),
            }
            changed = True
        if result.progress.mentioned and result.progress.percentage is not None:
            if payload.get("progressPercentage") != float(result.progress.percentage):
                payload["progressPercentage"] = float(result.progress.percentage)
                changed = True
        if "dueDate" in payload or "startDate" in payload:
            corrected = resolve_spoken_date(spoken)
            if corrected is not None and corrected.value is not None:
                if payload.get("dueDate") != corrected.value.isoformat():
                    payload["dueDate"] = corrected.value.isoformat()
                    changed = True
        if payload.get("priority"):
            corrected_priority = priority_value(spoken)
            if corrected_priority and corrected_priority != payload["priority"]:
                payload["priority"] = corrected_priority
                changed = True

        carried.append({
            "action_type": draft.action_type,
            "payload": payload,
            "target_id": target_id,
            "target_type": draft.target_entity_type,
            "snapshot": snapshot,
            "confidence": float(draft.confidence),
            "risk_level": draft.risk_level,
            "required_evidence": list(draft.required_evidence or []),
            "warnings": list(draft.warnings or []),
            "missing": missing_fields(
                action_type, payload, has_target=target_id is not None
            ),
        })

    if not changed:
        # Nothing in the correction named a value this proposal holds. Treating
        # it as a correction anyway would silently re-present the same draft and
        # look like the assistant ignored what was said.
        return False

    _attach(command, carried)
    command.provider_metadata = {
        **(command.provider_metadata or {}),
        "correctedFrom": str(pending.id),
    }
    close(db, pending, reason="corrected", successor=command)
    logger.info("voice proposal %s corrected by %s", pending.id, command.id)
    return True


def _attach(command: VoiceAnalysis, carried: list[dict]) -> None:
    """Put carried drafts onto this command as its own."""
    from uuid import uuid4

    for index, item in enumerate(carried):
        command.action_drafts.append(VoiceActionDraft(
            voice_analysis_id=command.id,
            client_action_id=f"c{index + 1}-{uuid4().hex[:12]}",
            sequence=index,
            action_type=item["action_type"],
            target_entity_type=item.get("target_type")
            or ("TASK" if item["target_id"] else None),
            target_entity_id=item["target_id"],
            extracted_payload=item["payload"],
            target_snapshot=item["snapshot"],
            confidence=item["confidence"],
            missing_fields=item["missing"],
            warnings=item["warnings"],
            risk_level=item["risk_level"],
            required_evidence=item["required_evidence"],
        ))


def _resolve_task(
    spoken: str, result: ConstructionVoiceResult, tasks: list[Task]
) -> Task | None:
    """Which task the answer names — by position, by identity, or by words."""
    if not tasks:
        return None
    positional = match_by_position(spoken, tasks)
    if positional is not None:
        return positional
    if result.detected_task.task_id:
        # An identifier the model was given by us, and validated against this
        # project before it ever reached here.
        return next(
            (task for task in tasks if task.id == result.detected_task.task_id), None
        )
    reference = (
        result.query.task_reference or result.detected_task.task_title or spoken
    )
    outcome = match_task(reference, tasks)
    if outcome.is_resolved and outcome.confidence >= FOLLOW_UP_CONFIDENCE:
        return next(
            (task for task in tasks if task.id == outcome.resolved_task_id), None
        )
    return None


def _is_positional_only(spoken: str) -> bool:
    """True when the utterance is a pointer, not content.

    "المهمة السادسة" answers *which*; it must never become the text of an issue.
    """
    from app.services.voice_task_matcher import task_position

    return task_position(spoken) is not None and len(spoken.split()) <= 4
