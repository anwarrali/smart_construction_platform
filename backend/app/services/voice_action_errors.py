"""Why an action did not happen, said in a way the speaker can act on.

Execution failures used to reach the engineer as whatever string the backend
happened to raise: *"Only the assigned Project Manager can delete tasks"*,
*"At least one authorized recipient is required"*, *"422"*. The Flutter client,
correctly refusing to print developer English, collapsed all of them into one
sentence — "something went wrong" — so a permission problem, a missing
recipient and a genuine outage were indistinguishable. The engineer could not
tell which of the three they were looking at, and two of them are things they
could have fixed in five seconds.

This module is the translation layer, and it has exactly two jobs:

  * **Classify.** Turn an `HTTPException` from any existing service into a
    stable `error_code`. The classification is deliberately conservative: an
    unrecognised failure is `ACTION_FAILED`, never a guess.
  * **Explain.** Give that code a sentence in the speaker's language, phrased
    as something a person says — "ما عندك صلاحية لتعديل هاي المهمة" — with the
    technical detail kept for the logs and the audit trail.

What it must never do is invent a reason. If the backend did not say why, the
reply says that plainly rather than offering a plausible-sounding cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException

#: Stable machine codes. The client never shows these; they exist so support,
#: metrics and tests can talk about one failure without matching on prose.
PERMISSION_DENIED = "PERMISSION_DENIED"
NOT_FOUND = "NOT_FOUND"
RECIPIENT_REQUIRED = "RECIPIENT_REQUIRED"
RECIPIENT_NOT_ALLOWED = "RECIPIENT_NOT_ALLOWED"
VALIDATION_ERROR = "VALIDATION_ERROR"
WORKFLOW_CONFLICT = "WORKFLOW_CONFLICT"
STALE_TARGET = "STALE_TARGET"
EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
ACTION_FAILED = "ACTION_FAILED"
#: Codes added after acceptance testing, where every one of the failures below
#: reached the engineer as "something is missing" or "action failed" even
#: though the backend knew exactly what was wrong. Each one names the thing
#: that is actually missing, or actually refused.
TARGET_TASK_REQUIRED = "TARGET_TASK_REQUIRED"
TARGET_TASK_NOT_FOUND = "TARGET_TASK_NOT_FOUND"
TARGET_ISSUE_REQUIRED = "TARGET_ISSUE_REQUIRED"
ASSIGNEE_REQUIRED = "ASSIGNEE_REQUIRED"
ASSIGNEE_NOT_ELIGIBLE = "ASSIGNEE_NOT_ELIGIBLE"
DATE_REQUIRED = "DATE_REQUIRED"
NO_CHANGE_REQUESTED = "NO_CHANGE_REQUESTED"
NEEDS_REVIEW_BEFORE_EXECUTION = "NEEDS_REVIEW_BEFORE_EXECUTION"
TASK_NOT_STARTABLE = "TASK_NOT_STARTABLE"
PROGRESS_LOCKED = "PROGRESS_LOCKED"
PROGRESS_DECREASE_UNCONFIRMED = "PROGRESS_DECREASE_UNCONFIRMED"
PROGRESS_OUT_OF_RANGE = "PROGRESS_OUT_OF_RANGE"
REVIEW_NOT_REQUIRED = "REVIEW_NOT_REQUIRED"
REVIEW_NOT_COMPLETE = "REVIEW_NOT_COMPLETE"
DELETION_NOT_CONFIRMED = "DELETION_NOT_CONFIRMED"


@dataclass(frozen=True)
class ActionFailure:
    """One failure, classified and explained."""

    error_code: str
    text_ar: str
    text_en: str
    #: The backend's own words. Logged and stored, never shown.
    detail: str = ""
    status_code: int | None = None
    details: dict = field(default_factory=dict)

    def text_for(self, language: str | None) -> str:
        return self.text_ar if str(language or "").startswith("ar") else self.text_en

    def as_dict(self, language: str | None = None) -> dict:
        return {
            "errorCode": self.error_code,
            "userMessage": self.text_for(language),
            "userMessageAr": self.text_ar,
            "userMessageEn": self.text_en,
            "details": self.details,
        }


#: code → (Arabic, English). Written as speech, not as documentation: these are
#: read aloud on a site, so they say what happened and, where there is one,
#: what to do instead.
_MESSAGES: dict[str, tuple[str, str]] = {
    PERMISSION_DENIED: (
        "ما عندك صلاحية تعمل هذا التعديل.",
        "You do not have permission to make this change.",
    ),
    NOT_FOUND: (
        "ما لقيت الشي اللي بدك تعدله. يمكن يكون انحذف أو تغيّر.",
        "I could not find what you wanted to change — it may have been removed.",
    ),
    RECIPIENT_REQUIRED: (
        "لمين بدك أبعت الرسالة؟",
        "Who should I send it to?",
    ),
    RECIPIENT_NOT_ALLOWED: (
        "ما بقدر أبعت لهذا الشخص من هذا المشروع.",
        "I cannot send to that person from this project.",
    ),
    VALIDATION_ERROR: (
        "في معلومة ناقصة أو مش مظبوطة قبل ما أقدر أنفذها.",
        "Something is missing or does not fit before I can do that.",
    ),
    WORKFLOW_CONFLICT: (
        "ما بقدر أعمل هذا حسب وضع المهمة الحالي.",
        "That does not fit the current state of this work.",
    ),
    STALE_TARGET: (
        "تغيّر الوضع من وقت ما راجعناه. راجعه مرة كمان وأكّده.",
        "This changed since you reviewed it. Have another look and confirm again.",
    ),
    EVIDENCE_REQUIRED: (
        "لازم صور قبل ما أقدر أسجل هذا التحديث.",
        "Photos are required before I can record this update.",
    ),
    CLARIFICATION_REQUIRED: (
        "لسه في معلومة ناقصة قبل ما أنفذها.",
        "Something is still missing before I can do that.",
    ),
    SERVICE_UNAVAILABLE: (
        "ما قدرت أنفذ الطلب حاليًا لأن الخدمة مش متاحة. جرّب مرة ثانية.",
        "I could not do that right now — the service is unavailable. Try again.",
    ),
    ACTION_FAILED: (
        "ما قدرت أنفذ الطلب. ما تغيّر إشي بالمشروع.",
        "I could not do that. Nothing in the project was changed.",
    ),
    TARGET_TASK_REQUIRED: (
        "ما عرفت أي مهمة تقصد، فما نفذت إشي. احكيلي اسم المهمة أو رقمها وبعملها.",
        "I did not know which task you meant, so I changed nothing. "
        "Tell me the task name or its number and I will do it.",
    ),
    TARGET_TASK_NOT_FOUND: (
        "المهمة مش موجودة — يمكن تكون انحذفت أو انتقلت لمشروع تاني.",
        "That task no longer exists — it may have been deleted or moved.",
    ),
    TARGET_ISSUE_REQUIRED: (
        "ما عرفت أي مشكلة تقصد، فما غيّرت إشي. احكيلي أي وحدة فيهم.",
        "I did not know which issue you meant, so I changed nothing. "
        "Tell me which one.",
    ),
    ASSIGNEE_REQUIRED: (
        "ما قدرت أعيّن المهمة لأني ما حددت الشخص. مين بدك يكون مسؤول عنها؟",
        "I could not assign the task because I do not know who to assign it "
        "to. Who should be responsible for it?",
    ),
    ASSIGNEE_NOT_ELIGIBLE: (
        "ما بقدر أعيّن المهمة لهذا الشخص. المهام بتنعطى لأعضاء المشروع "
        "النشطين فقط.",
        "I cannot assign the task to that person. Tasks go to active members "
        "of this project.",
    ),
    DATE_REQUIRED: (
        "المهمة جاهزة للتحديث، بس التاريخ المطلوب مش واضح. لأي يوم بدك تخليه؟",
        "The task is ready to update, but the date you want is not clear. "
        "What day should it be?",
    ),
    NO_CHANGE_REQUESTED: (
        "ما لقيت إشي جديد أغيّره، فما عدّلت إشي.",
        "I could not find anything new to change, so I changed nothing.",
    ),
    NEEDS_REVIEW_BEFORE_EXECUTION: (
        "ما كنت متأكد إني فهمت الطلب صح، فما نفذته. راجع التفاصيل وعدّلها وبعدين أكّد.",
        "I was not confident I understood that, so I did not do it. "
        "Check the details, edit them, and confirm.",
    ),
    TASK_NOT_STARTABLE: (
        "ما بقدر أبدأ هاي المهمة — بس المهام اللي لسه ما بدأت بتنبدأ.",
        "I cannot start that task — only a task that has not started yet can "
        "be started.",
    ),
    PROGRESS_LOCKED: (
        "ما بقدر أحدّث نسبة الإنجاز — المهمة صارت بمرحلة المراجعة أو خلصت.",
        "I cannot update the percentage — the task is already in review or "
        "finished.",
    ),
    PROGRESS_DECREASE_UNCONFIRMED: (
        "النسبة اللي حكيتها أقل من المسجّلة. إذا بدك تصحّحها، أكّد التصحيح.",
        "The percentage you gave is lower than the one on record. "
        "If that is a correction, confirm it explicitly.",
    ),
    PROGRESS_OUT_OF_RANGE: (
        "نسبة الإنجاز لازم تكون بين 0 و100.",
        "Progress has to be between 0 and 100.",
    ),
    REVIEW_NOT_REQUIRED: (
        "هاي المهمة ما بتحتاج مراجعة استشاري، فما بعتها.",
        "That task does not need a Consultant review, so I did not send it.",
    ),
    REVIEW_NOT_COMPLETE: (
        "ما بقدر أبعتها للمراجعة قبل ما توصل 100%.",
        "I cannot send it for review before it reaches 100%.",
    ),
    DELETION_NOT_CONFIRMED: (
        "الحذف بدو تأكيد صريح منك، فما حذفت إشي.",
        "Deleting needs your explicit confirmation, so I deleted nothing.",
    ),
}


class VoiceActionError(HTTPException):
    """A failure the backend already knows the reason for.

    Raised where the voice layer itself refuses — a task it could not resolve,
    a person who cannot hold work, a field still unanswered — so the reason
    survives all the way to the engineer instead of being guessed back out of
    an English sentence a moment later. `classify` returns it unchanged.

    `detail` stays developer English for the logs and the execution record;
    `text_ar` and `text_en` are what the engineer hears, and either may be
    overridden to name the specific thing that was missing.
    """

    def __init__(
        self,
        code: str,
        *,
        detail: str,
        status_code: int = 422,
        text_ar: str | None = None,
        text_en: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        arabic, english = _MESSAGES.get(code, _MESSAGES[ACTION_FAILED])
        self.error_code = code
        self.text_ar = text_ar or arabic
        self.text_en = text_en or english
        self.failure_details = details or {}

    @property
    def failure(self) -> "ActionFailure":
        return ActionFailure(
            error_code=self.error_code,
            text_ar=self.text_ar,
            text_en=self.text_en,
            detail=str(self.detail),
            status_code=self.status_code,
            details=self.failure_details,
        )


def missing_field_failure(paths: list[str]) -> VoiceActionError:
    """The "still waiting on something" refusal, naming what it is waiting on.

    "لسه في معلومة ناقصة" told the engineer nothing they could act on. The
    outstanding field already has a question written for it in their own
    language — see `app.services.voice_action_requirements` — so the refusal
    says the same words the assistant would have used to ask.
    """
    from app.services.voice_action_requirements import prompt_for

    questions_ar: list[str] = []
    questions_en: list[str] = []
    for path in paths:
        prompt = prompt_for(path)
        if prompt is None:
            continue
        questions_ar.append(prompt.question_ar)
        questions_en.append(prompt.question_en)
    detail = "Required clarification is still missing: " + ", ".join(paths)
    if not questions_ar:
        return VoiceActionError(
            CLARIFICATION_REQUIRED, detail=detail, status_code=409
        )
    return VoiceActionError(
        CLARIFICATION_REQUIRED,
        detail=detail,
        status_code=409,
        text_ar="ما نفذت الطلب لأنه لسه بدي أعرف: " + " ".join(questions_ar),
        text_en=(
            "I did not do that because I still need to know: "
            + " ".join(questions_en)
        ),
        details={"missingFields": list(paths)},
    )

#: Phrases from existing services that identify a failure more precisely than
#: its status code can. Matched case-insensitively against the raised detail.
#:
#: This is a *reading* of the existing backend, not a new contract imposed on
#: it: rewriting every service to return codes would touch dozens of endpoints
#: that the UI depends on. Anything unmatched still classifies by status code,
#: so a reworded message degrades to "permission denied" rather than to a lie.
_DETAIL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("authorized recipient is required", RECIPIENT_REQUIRED),
    ("select one responsible person", RECIPIENT_REQUIRED),
    ("outside your authorized project contacts", RECIPIENT_NOT_ALLOWED),
    ("recipient is not available", RECIPIENT_NOT_ALLOWED),
    ("owner as the only recipient", RECIPIENT_NOT_ALLOWED),
    ("no available owner", RECIPIENT_NOT_ALLOWED),
    ("required clarification is still missing", CLARIFICATION_REQUIRED),
    ("required photos", EVIDENCE_REQUIRED),
    ("changed after review", STALE_TARGET),
    ("refresh the voice command", STALE_TARGET),
    # Sentences the existing task, issue and assignment services already
    # raise. Each is a reason the engineer can act on, and each used to reach
    # them as the same generic "something is missing or does not fit".
    ("a target task is required", TARGET_TASK_REQUIRED),
    ("target task is unavailable", TARGET_TASK_NOT_FOUND),
    ("a target issue is required", TARGET_ISSUE_REQUIRED),
    ("no assignee was selected", ASSIGNEE_REQUIRED),
    ("every assignee must be an active", ASSIGNEE_NOT_ELIGIBLE),
    ("assigned project manager is eligible", ASSIGNEE_NOT_ELIGIBLE),
    ("execution tasks may only be assigned", ASSIGNEE_NOT_ELIGIBLE),
    ("cannot be assigned to a", ASSIGNEE_NOT_ELIGIBLE),
    ("duplicate task assignees", ASSIGNEE_NOT_ELIGIBLE),
    ("no new date was provided", DATE_REQUIRED),
    ("no change was provided", NO_CHANGE_REQUESTED),
    ("must be reviewed and edited before execution", NEEDS_REVIEW_BEFORE_EXECUTION),
    ("only a to do task can be started", TASK_NOT_STARTABLE),
    ("progress is locked by workflow", PROGRESS_LOCKED),
    ("progress decrease requires", PROGRESS_DECREASE_UNCONFIRMED),
    ("progress must be between", PROGRESS_OUT_OF_RANGE),
    ("does not require consultant review", REVIEW_NOT_REQUIRED),
    ("progress must be 100%", REVIEW_NOT_COMPLETE),
    ("requires an explicit confirmation", DELETION_NOT_CONFIRMED),
)


def classify(exc: HTTPException) -> ActionFailure:
    """Turn one raised failure into a code and a sentence.

    A `VoiceActionError` already carries both, chosen where the reason was
    known. Re-deriving them from its English sentence would be the one place
    this module could turn a precise reason back into a vague one.
    """
    if isinstance(exc, VoiceActionError):
        return exc.failure
    status = int(getattr(exc, "status_code", 0) or 0)
    detail = str(getattr(exc, "detail", "") or "")
    lowered = detail.casefold()

    code = None
    for phrase, candidate in _DETAIL_PATTERNS:
        if phrase in lowered:
            code = candidate
            break
    if code is None:
        code = {
            400: VALIDATION_ERROR,
            403: PERMISSION_DENIED,
            404: NOT_FOUND,
            409: WORKFLOW_CONFLICT,
            422: VALIDATION_ERROR,
            503: SERVICE_UNAVAILABLE,
        }.get(status, ACTION_FAILED)
    return failure(code, detail=detail, status_code=status)


def failure(code: str, *, detail: str = "", status_code: int | None = None,
            details: dict | None = None) -> ActionFailure:
    """Build a failure from a code this module knows."""
    arabic, english = _MESSAGES.get(code, _MESSAGES[ACTION_FAILED])
    return ActionFailure(
        error_code=code,
        text_ar=arabic,
        text_en=english,
        detail=detail,
        status_code=status_code,
        details=details or {},
    )


#: action type → (Arabic, English) description of what succeeded, in the same
#: voice as everything else the assistant says. Used to narrate a result
#: without another provider call: the sentence is short, factual, and the same
#: every time, which is what a confirmation of something already done should be.
_SUCCESS: dict[str, tuple[str, str]] = {
    "CREATE_TASK": ("تم إنشاء المهمة.", "The task was created."),
    "START_TASK": ("تم بدء المهمة.", "The task was started."),
    "UPDATE_TASK_PROGRESS": ("تم تحديث نسبة الإنجاز.", "Progress was updated."),
    "UPDATE_TASK_SCHEDULE": ("تم تحديث موعد المهمة.", "The task dates were updated."),
    "UPDATE_TASK_ASSIGNMENT": ("تم تحديث المسؤول عن المهمة.", "The task assignment was updated."),
    "UPDATE_TASK_PRIORITY": ("تم تغيير أولوية المهمة.", "The task priority was changed."),
    "UPDATE_TASK_DETAILS": ("تم تحديث تفاصيل المهمة.", "The task details were updated."),
    "DELETE_TASK": ("تم حذف المهمة.", "The task was deleted."),
    "SUBMIT_TASK_FOR_REVIEW": ("تم إرسال المهمة للمراجعة.", "The task was sent for review."),
    "CREATE_ISSUE": ("تم تسجيل المشكلة.", "The issue was recorded."),
    "UPDATE_ISSUE_STATUS": ("تم تحديث حالة المشكلة.", "The issue was updated."),
    "ASSIGN_ISSUE": ("تم تحديث المسؤول عن المشكلة.", "The issue assignment was updated."),
    "CREATE_FIELD_SUBMISSION": ("تم إرسال التقرير للمهندس للمراجعة.", "Your report was sent for engineer review."),
    "ADD_TASK_NOTE": ("تمت إضافة الملاحظة.", "The note was added."),
    "CREATE_SITE_REPORT_DRAFT": ("تم تجهيز مسودة تقرير الموقع.", "The site report draft is ready."),
    "CREATE_TASK_MESSAGE": ("تم إرسال الرسالة على المهمة.", "The message was posted on the task."),
    "PREPARE_CONSULTANT_REVIEW": ("تم تسجيل قرار المراجعة.", "The review decision was recorded."),
    "CREATE_DESIGN_CHANGE_REPORT": ("تم تسجيل طلب تغيير التصميم.", "The design change was recorded."),
    "SEND_PROJECT_MESSAGE": ("تم إرسال الرسالة.", "The message was sent."),
    "SEND_OWNER_UPDATE": ("تم إرسال الرسالة لصاحب المشروع.", "The update was sent to the project owner."),
}


def success_message(action_type: str, language: str | None) -> str:
    """What to say once the backend has confirmed the change.

    Only ever called on a result the backend reported as successful — saying
    "تم" for something that did not happen is the single most damaging thing
    this assistant could do.
    """
    arabic, english = _SUCCESS.get(
        str(action_type), ("تمام، تم تنفيذ الطلب.", "Done.")
    )
    return arabic if str(language or "").startswith("ar") else english
