"""What each action still needs before anybody can be asked to confirm it.

An engineer says *"بدي أرفع مشكلة عن شغل اليوم"*. That is a complete thought and
an incomplete instruction: the intent is unmistakable, the problem itself was
never said. The old pipeline had two ways of handling that and both were wrong.
Either the model refused to propose anything and the utterance fell through to
"could you say that again?", or it proposed an issue with no title, the strict
schema rejected the whole analysis, and the engineer got *"AI analysis is
temporarily unavailable"* — a technical error for a conversational gap.

The rule this module encodes: **a missing field is a question, never an
error.** It answers three things and nothing else, so that every caller asks
them the same way:

  * which fields an action cannot execute without (`missing_fields`),
  * what to ask for each one, in either language, when the phrasing model is
    unavailable (`FIELD_PROMPTS`),
  * what is already understood, in plain words a person could hear read back
    (`describe_understood`).

Nothing here writes, validates payload *shape* — that stays in
`app.ai.action_payload_contract`, which the rules engine enforces at execution
— or decides whether an action is allowed. It only asks "is anything still
unsaid?".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.voice_analysis import SuggestedActionType

#: The field paths used for a missing target. Kept as constants because
#: several modules and both clients compare against these exact strings.
TARGET_TASK = "target.taskId"
TARGET_ISSUE = "target.issueId"


@dataclass(frozen=True)
class FieldPrompt:
    """How to ask for one missing field.

    `description` is what the phrasing model is told is missing. It is
    deliberately plain language — "which task this is about" — because the
    model may echo it, and a field path in a spoken reply is exactly the leak
    of internals this whole change exists to prevent.

    `fills` names the payload keys one spoken answer should populate. An
    engineer describing a problem says it once; splitting that into "title" and
    "description" is bookkeeping, and asking twice for it would be absurd.
    """

    answer_type: str
    description: str
    question_en: str
    question_ar: str
    fills: tuple[str, ...] = ()


#: A short title is a label, not a paragraph. Long spoken descriptions are
#: trimmed for the title field and kept whole in the description.
TITLE_LENGTH = 120


FIELD_PROMPTS: dict[str, FieldPrompt] = {
    TARGET_TASK: FieldPrompt(
        answer_type="TASK_SELECTION",
        description="which task this is about",
        question_en="Which task do you mean?",
        question_ar="أي مهمة تقصد؟",
    ),
    "payload.progressPercentage": FieldPrompt(
        answer_type="NUMBER",
        description="how far along the work is, as a percentage",
        question_en="Roughly what percentage is it at now?",
        question_ar="شو نسبة الإنجاز تقريباً هلأ؟",
        fills=("progressPercentage",),
    ),
    "payload.issue": FieldPrompt(
        answer_type="TEXT",
        description="what the problem actually is",
        question_en="Sure — what is the problem you want to record?",
        question_ar="أكيد، شو المشكلة اللي بدك تسجلها؟",
        fills=("title", "description"),
    ),
    "payload.taskTitle": FieldPrompt(
        answer_type="TEXT",
        description="what the new task should be called",
        question_en="What should the new task be called?",
        question_ar="شو اسم المهمة الجديدة؟",
        fills=("title",),
    ),
    "payload.description": FieldPrompt(
        answer_type="TEXT",
        description="what happened on site that should be recorded",
        question_en="What would you like me to record about the work?",
        question_ar="شو بدك أسجل عن الشغل؟",
        fills=("description",),
    ),
    "payload.content": FieldPrompt(
        answer_type="TEXT",
        description="the words that should be written down",
        question_en="What should it say?",
        question_ar="شو بدك يحكي؟",
        fills=("content",),
    ),
    "payload.summaryText": FieldPrompt(
        answer_type="TEXT",
        description="what the site report should say about the day's work",
        question_en="What should the site report say about today's work?",
        question_ar="شو بدك يحكي تقرير الموقع عن شغل اليوم؟",
        fills=("summaryText",),
    ),
    "payload.decision": FieldPrompt(
        answer_type="TEXT",
        description="whether this is an approval, a rejection, or just a note",
        question_en="Is this an approval, a rejection, or a note?",
        question_ar="هاي موافقة، ولا رفض، ولا مجرد ملاحظة؟",
        fills=("decision",),
    ),
    "payload.comments": FieldPrompt(
        answer_type="TEXT",
        description="the review comments to record",
        question_en="What are your review comments?",
        question_ar="شو ملاحظاتك على المراجعة؟",
        fills=("comments",),
    ),
    "payload.dueDate": FieldPrompt(
        answer_type="DATE",
        description="the new date for the work",
        question_en="What date should it be?",
        question_ar="لأي تاريخ بدك تخليه؟",
        fills=("dueDate",),
    ),
    "payload.assignee": FieldPrompt(
        answer_type="PERSON_SELECTION",
        description="who should be responsible for it",
        question_en="Who should be responsible for it?",
        question_ar="مين بدك يكون مسؤول عنها؟",
        fills=("assigneeIds",),
    ),
    "payload.priority": FieldPrompt(
        answer_type="CHOICE",
        description="what the new priority should be",
        question_en="What priority should it be — low, medium, high or critical?",
        question_ar="شو الأولوية اللي بدك ياها — منخفضة، متوسطة، عالية، ولا حرجة؟",
        fills=("priority",),
    ),
    "payload.issueStatus": FieldPrompt(
        answer_type="CHOICE",
        description="what should happen to the issue",
        question_en="Should it be resolved, closed, reopened, or in progress?",
        question_ar="بدك تعتبرها انحلّت، ولا تسكّرها، ولا ترجع تفتحها؟",
        fills=("issueStatus",),
    ),
    "payload.resolutionNotes": FieldPrompt(
        answer_type="TEXT",
        description="how the problem was solved",
        question_en="How was it solved?",
        question_ar="كيف انحلّت؟",
        fills=("resolutionNotes",),
    ),
    TARGET_ISSUE: FieldPrompt(
        answer_type="ISSUE_SELECTION",
        description="which problem this is about",
        question_en="Which issue do you mean?",
        question_ar="أي مشكلة تقصد؟",
    ),
    "payload.recipients": FieldPrompt(
        answer_type="TEXT",
        description="who the message should go to",
        question_en="Who should I send it to?",
        question_ar="لمين ببعتها؟",
        fills=("recipientIds",),
    ),
}


#: Actions that cannot execute without a task. One list, because three modules
#: used to keep their own and drift apart.
TASK_REQUIRED_ACTIONS: frozenset[SuggestedActionType] = frozenset({
    SuggestedActionType.START_TASK,
    SuggestedActionType.UPDATE_TASK_PROGRESS,
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW,
    SuggestedActionType.CREATE_FIELD_SUBMISSION,
    SuggestedActionType.ADD_TASK_NOTE,
    SuggestedActionType.CREATE_TASK_MESSAGE,
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW,
})

#: What each action *is*, said the way a person would say it. Handed to the
#: phrasing model so it can confirm the understood half of a request without
#: ever seeing — or repeating — an action type name.
ACTION_PURPOSE: dict[SuggestedActionType, str] = {
    SuggestedActionType.CREATE_TASK: "add a new task to the project",
    SuggestedActionType.START_TASK: "start a task",
    SuggestedActionType.UPDATE_TASK_PROGRESS: "update how far along a task is",
    SuggestedActionType.SUBMIT_TASK_FOR_REVIEW: "send a finished task for review",
    SuggestedActionType.CREATE_ISSUE: "record a problem on site",
    SuggestedActionType.CREATE_FIELD_SUBMISSION: "record what was done on site",
    SuggestedActionType.ADD_TASK_NOTE: "add a note to a task",
    SuggestedActionType.CREATE_SITE_REPORT_DRAFT: "prepare a site report",
    SuggestedActionType.CREATE_TASK_MESSAGE: "post a message on a task",
    SuggestedActionType.PREPARE_CONSULTANT_REVIEW: "record a review decision",
    SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT: "report a design change",
    SuggestedActionType.SEND_PROJECT_MESSAGE: "send a message to people on the project",
    SuggestedActionType.SEND_OWNER_UPDATE: "send an update to the project owner",
}


#: payload key → the question that asks for it. One question may fill several
#: keys (an engineer describes a problem once, and it becomes both the issue's
#: title and its description), which is why this maps to a *prompt* and not to
#: a field name.
_PATH_BY_KEY: dict[str, str] = {
    "progressPercentage": "payload.progressPercentage",
    "title": "payload.taskTitle",
    "description": "payload.description",
    "content": "payload.content",
    "summaryText": "payload.summaryText",
    "decision": "payload.decision",
    "comments": "payload.comments",
    "recipientIds": "payload.recipients",
    "dueDate": "payload.dueDate",
    "assigneeIds": "payload.assignee",
    "priority": "payload.priority",
    "issueStatus": "payload.issueStatus",
}

#: Where one key means something different for one capability. An issue's
#: "title" is the problem itself, and asking "what should it be called?" for a
#: problem somebody just reported would be absurd.
_PATH_OVERRIDES: dict[tuple[SuggestedActionType, str], str] = {
    (SuggestedActionType.CREATE_ISSUE, "title"): "payload.issue",
}

#: Capabilities whose contract marks everything optional but which still cannot
#: run on an empty payload: renaming a task means changing *something*.
_NEEDS_ANY_OF: dict[SuggestedActionType, tuple[tuple[str, ...], str]] = {
    SuggestedActionType.UPDATE_TASK_DETAILS: (("title", "description"), "payload.taskTitle"),
}


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return not value
    return False


def missing_fields(
    action_type: SuggestedActionType,
    payload: dict | None,
    *,
    has_target: bool,
) -> list[str]:
    """Field paths this action still needs, in the order to ask for them.

    Derived from the capability registry — the same table the prompt is
    rendered from and the rules engine validates against — so a capability
    gains a required field in exactly one place.

    Ordered target-first on purpose: knowing *which* task or issue is what
    makes every other question answerable, and it is the one an engineer can
    answer without thinking.
    """
    from app.ai.action_payload_contract import ACTION_CONTRACTS
    from app.services.voice_capabilities import capability_for

    values = payload or {}
    capability = capability_for(action_type)
    found: list[str] = []
    if capability is not None and not has_target:
        if capability.needs_task:
            found.append(TARGET_TASK)
        elif capability.needs_issue:
            found.append(TARGET_ISSUE)

    contract = ACTION_CONTRACTS.get(action_type)
    for key in contract.required if contract else ():
        if _blank(values.get(key)):
            path = _PATH_OVERRIDES.get((action_type, key)) or _PATH_BY_KEY.get(key)
            if path and path not in found:
                found.append(path)

    any_of = _NEEDS_ANY_OF.get(action_type)
    if any_of and all(_blank(values.get(key)) for key in any_of[0]):
        found.append(any_of[1])

    # A requirement that depends on the value rather than the field: the issues
    # API refuses to resolve or close an issue without a resolution note, so
    # asking "كيف انحلّت؟" is the difference between a conversation and a 400.
    if (
        action_type == SuggestedActionType.UPDATE_ISSUE_STATUS
        and str(values.get("issueStatus") or "") in {"resolved", "closed"}
        and _blank(values.get("resolutionNotes"))
    ):
        found.append("payload.resolutionNotes")
    return found


def prompt_for(path: str) -> FieldPrompt | None:
    """The question for one missing field path, or None for an unknown path.

    Unknown paths are possible: the model may report a `missing_fields` entry
    of its own invention. They are carried on the draft — which keeps it out of
    execution — but they produce no question, because inventing one from a
    string the model made up would put that string in front of a person.
    """
    return FIELD_PROMPTS.get(path)


def apply_answer(path: str, payload: dict, answer: str) -> dict:
    """Merge one spoken answer into a draft payload.

    Returns a new dict; the caller decides whether to store it. Splitting a
    single spoken sentence across `title` and `description` happens here rather
    than at each call site, so every entry point fills an issue the same way.
    """
    prompt = FIELD_PROMPTS.get(path)
    merged = dict(payload or {})
    clean = (answer or "").strip()
    if prompt is None or not clean:
        return merged
    for key in prompt.fills:
        # A value the caller resolved to nothing must not overwrite one that is
        # already there — an unrecognised answer is a question, not an erasure.
        if key == "title":
            merged[key] = clean[:TITLE_LENGTH].strip()
        elif key == "progressPercentage":
            try:
                merged[key] = float(
                    clean.replace("%", "").replace("٪", "").strip()
                )
            except ValueError:
                continue
        elif key == "decision":
            matched = _decision(clean)
            if matched:
                merged[key] = matched
        elif key == "priority":
            matched = priority_value(clean)
            if matched:
                merged[key] = matched
        elif key == "issueStatus":
            matched = issue_status_value(clean)
            if matched:
                merged[key] = matched
        elif key in {"recipientIds", "assigneeIds", "dueDate"}:
            # Deliberately nothing. A person is not a string and a date is not
            # a phrase: both are resolved against the project — the team list,
            # the calendar — by the caller that can read them, and a value that
            # resolves to nothing must stay unresolved rather than being
            # written into the payload as text.
            continue
        else:
            merged[key] = clean
    return merged


_APPROVE = ("approve", "approved", "approval", "وافق", "موافق", "موافقة", "مقبول")
_REJECT = ("reject", "rejected", "rejection", "رفض", "مرفوض", "مرفوضة")


def _decision(answer: str) -> str | None:
    lowered = answer.casefold()
    if any(word in lowered for word in _APPROVE):
        return "APPROVE"
    if any(word in lowered for word in _REJECT):
        return "REJECT"
    if "note" in lowered or "ملاحظ" in lowered:
        return "NOTE"
    return None


#: Spoken priority, in both languages. "خطر" and "مستعجل" are what people
#: actually say for critical work; neither is a literal translation.
_PRIORITY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("critical", ("critical", "urgent", "حرج", "حرجة", "خطر", "خطير", "مستعجل", "طارئ")),
    ("high", ("high", "عالي", "عالية", "مرتفع", "مهم", "مهمة جدا")),
    ("medium", ("medium", "normal", "متوسط", "متوسطة", "عادي", "عادية")),
    ("low", ("low", "منخفض", "منخفضة", "بسيط", "مش مستعجل")),
)


def priority_value(answer: str) -> str | None:
    """The platform's priority value a spoken word means, or None.

    Normalized first: speech-to-text emits "سكّرها" and "سكرها" for the same
    word, and a shadda between two letters is enough to hide a substring.
    """
    from app.services.voice_task_matcher import normalize

    lowered = normalize(answer) or answer.casefold()
    for value, words in _PRIORITY_WORDS:
        if any(word in lowered for word in words):
            return value
    return None


_ISSUE_STATUS_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("resolved", ("resolved", "resolve", "fixed", "انحل", "انحلت", "تم حلها", "محلول")),
    ("closed", ("closed", "close", "سكر", "سكرت", "مغلق", "مغلقة", "اقفال")),
    # "in_progress" as well as "in progress": the value arrives verbatim when
    # somebody taps the option chip, and as words when they say it.
    ("in_progress", ("in_progress", "in progress", "working", "شغالين", "قيد", "جاري")),
    ("open", ("open", "reopen", "افتح", "ارجع افتح", "مفتوح", "مفتوحة")),
)


def issue_status_value(answer: str) -> str | None:
    """The platform's issue status a spoken word means, or None."""
    from app.services.voice_task_matcher import normalize

    lowered = normalize(answer) or answer.casefold()
    for value, words in _ISSUE_STATUS_WORDS:
        if any(word in lowered for word in words):
            return value
    return None


def describe_understood(
    action_type: SuggestedActionType,
    payload: dict | None,
    *,
    task_label: str | None = None,
) -> dict:
    """What is already known about this request, in words rather than fields.

    Handed to the phrasing model so its question can open with "تمام، فهمت إن
    التقدم وصل لـ50%" instead of asking cold. Keys are readable because the
    model may lift them; values are the engineer's own content.
    """
    values = payload or {}
    understood: dict[str, object] = {
        "the engineer wants to": ACTION_PURPOSE.get(action_type, "record something"),
    }
    if task_label:
        understood["task"] = task_label
    if not _blank(values.get("progressPercentage")):
        understood["completion percentage"] = values["progressPercentage"]
    for key, label in (
        ("title", "title"),
        ("description", "description"),
        ("content", "text"),
        ("summaryText", "summary"),
        ("comments", "comments"),
        ("location", "location"),
        ("decision", "decision"),
        ("dueDate", "new date"),
        ("startDate", "new start date"),
        ("priority", "priority"),
        ("issueStatus", "new issue state"),
        ("resolutionNotes", "resolution note"),
    ):
        if not _blank(values.get(key)):
            understood[label] = values[key]
    return understood
