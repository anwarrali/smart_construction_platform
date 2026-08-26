"""Answering an engineer's question from the project record.

The division of labour here is the whole point of the module. The language
model decides *what was asked* — a topic and, when relevant, which task the
speaker meant. This module decides *what is true*, by reading the same
authorization-scoped rows the rest of the application reads. The model never
narrates a task's status, because a fluent sentence about a percentage that
does not exist is worse than no answer at all.

Two consequences follow, and both are deliberate:

  * **No second provider call.** A question is answered from `authorized_voice_tasks`
    and the task graph already loaded for context, so the read path costs a few
    database queries rather than another round trip to OpenAI. Asking "شو ضايل
    علينا؟" should feel like reading a screen, not like waiting for an AI.

  * **No mutation, ever.** Nothing in this module writes. That is what makes it
    safe to skip the confirmation step: there is nothing to confirm, because a
    question cannot change project data. The confirmation model is untouched
    for everything that can.

Answers are produced in both Arabic and English and the caller picks; task
names, codes and identifiers are never translated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.enums import IssueStatus, TaskStatus
from app.models.issue import Issue
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.schemas.voice_analysis import DetectedQuery, VoiceQueryTopic
from app.services.voice_task_matcher import (
    MAX_CANDIDATES,
    TaskMatch,
    match_by_position,
    match_task,
)

#: A question about one task cannot be answered until we know which task. Below
#: this the matcher's best guess is not trustworthy enough to answer *as fact*,
#: so the caller offers candidates instead. Higher than the action-path
#: threshold on purpose: a wrong answer is quieter than a wrong mutation and
#: therefore likelier to be believed.
ANSWER_RESOLVE_CONFIDENCE = 0.55

#: Long lists stop being answers and start being screens to read.
MAX_LISTED_TASKS = 6


@dataclass(frozen=True)
class VoiceAnswer:
    """A spoken-question answer, in both languages plus the data behind it."""

    topic: str
    text_en: str
    text_ar: str
    #: Structured facts the UI may render instead of, or beside, the sentence.
    data: dict = field(default_factory=dict)
    #: Set when the topic needed a task and more than one plausibly matched.
    candidates: list[TaskMatch] = field(default_factory=list)
    #: The sentence actually said to the engineer, phrased for *their* question
    #: and in the language they spoke. Empty until the caller composes it, at
    #: which point `as_dict` prefers it over the topic template. The templates
    #: stay as the fallback: they are always correct and never fail.
    spoken_text: str = ""
    #: "ar" or "en" — the language the engineer used, not the UI's locale.
    language: str = ""

    @property
    def is_answered(self) -> bool:
        return bool(self.spoken_text or self.text_en or self.text_ar)

    def text_for(self, language: str | None) -> str:
        arabic = str(language or "").lower().startswith("ar")
        preferred = self.text_ar if arabic else self.text_en
        return preferred or (self.text_en if arabic else self.text_ar)

    def as_dict(self) -> dict:
        language = self.language or "en"
        return {
            "topic": self.topic,
            "textEn": self.text_en,
            "textAr": self.text_ar,
            # One field the client can render without knowing anything about
            # how it was produced, already in the right language.
            "text": self.spoken_text or self.text_for(language),
            "language": language,
            "data": self.data,
            "candidates": [match.as_option() for match in self.candidates],
        }


#: Task status → (English, Arabic). Kept beside the answers rather than in the
#: enum because these are conversational words, not the UI's status chips.
_STATUS_WORDS: dict[str, tuple[str, str]] = {
    "BACKLOG": ("in the backlog", "في قائمة الانتظار"),
    "TODO": ("not started yet", "لم تبدأ بعد"),
    "IN_PROGRESS": ("in progress", "قيد التنفيذ"),
    "UNDER_REVIEW": ("under review", "قيد المراجعة"),
    "REWORK_REQUIRED": ("returned for rework", "بحاجة إلى إعادة عمل"),
    "DONE": ("done", "مكتملة"),
    "BLOCKED": ("blocked", "متوقفة"),
    "CANCELLED": ("cancelled", "ملغاة"),
}


def _status_words(task: Task) -> tuple[str, str]:
    # `TaskStatus` values are lowercase ("done", "in_progress"); the keys above
    # are the enum *names*. Folding here keeps the table readable and stops a
    # silent fallback to "recorded" for every status.
    return _STATUS_WORDS.get(_status_name(task), ("recorded", "مسجلة"))


def _status_name(task: Task) -> str:
    return str(getattr(task.status, "value", task.status)).upper()


def _label(task: Task) -> str:
    return f"{task.task_code} — {task.name}" if task.task_code else task.name


def _percent(task: Task) -> str:
    return f"{float(task.progress_percentage or 0):g}"


def _join(labels: list[str], *, arabic: bool) -> str:
    separator = "، " if arabic else ", "
    return separator.join(labels)


#: Reasoning topics: several facts read together and explained, with a
#: recommendation where the data supports one. Project-scoped, so they never
#: ask which task is meant.
REASONING_TOPICS = {
    VoiceQueryTopic.WHY_BLOCKED,
    VoiceQueryTopic.WHY_DELAYED,
    VoiceQueryTopic.PRIORITY_FOCUS,
    VoiceQueryTopic.RECOMMENDED_NEXT_STEP,
}

#: Topics that are about the project as a whole and must never ask "which task?".
PROJECT_LEVEL_TOPICS = {
    VoiceQueryTopic.NEXT_TASK,
    VoiceQueryTopic.REMAINING_TASKS,
    VoiceQueryTopic.NOT_STARTED_TASKS,
    VoiceQueryTopic.IN_PROGRESS_TASKS,
    VoiceQueryTopic.COMPLETED_TASKS,
    VoiceQueryTopic.BLOCKED_TASKS,
    VoiceQueryTopic.PROJECT_PROGRESS,
    VoiceQueryTopic.OPEN_ISSUES,
    VoiceQueryTopic.REPORT_READINESS,
}

#: Site reports are read from the site-report record itself, never from the
#: task graph. Kept in their own set rather than folded into the project-level
#: ones because they need a different query, a different authorization scope,
#: and an answer that says which document it came from.
SITE_REPORT_TOPICS = {
    VoiceQueryTopic.LATEST_SITE_REPORT,
    VoiceQueryTopic.SITE_REPORTS,
}

#: Topics that genuinely need one task before they mean anything.
TASK_LEVEL_TOPICS = {
    VoiceQueryTopic.TASK_STATUS,
    VoiceQueryTopic.TASK_PROGRESS,
    VoiceQueryTopic.TASK_ASSIGNEE,
    VoiceQueryTopic.TASK_LOCATION,
    VoiceQueryTopic.TASK_BLOCKERS,
    VoiceQueryTopic.TASK_NEXT_STEP,
}


#: A fact pack is read aloud, not scrolled. Past this many tasks the list stops
#: informing the answer and starts costing latency and tokens.
MAX_FACT_TASKS = 30
MAX_FACT_ISSUES = 8


def project_snapshot(db: Session, *, project_id, tasks: list[Task]) -> dict:
    """Everything true about this project that a spoken question might need.

    This is what makes one retrieval able to serve many different questions.
    The topic decides which *shape* of answer the templates produce; the
    snapshot lets the phrasing model answer what was actually asked — "كم مهمة
    خلصت؟" and "شو المهام اللي لسه ضايلة؟" and "شو وضع المشروع؟" are three
    different answers over one read of the same rows.

    Deliberately facts only: counts, names, statuses, dates. No opinion, no
    ranking, nothing derived that the caller could not check against a screen.
    """
    project = db.get(Project, project_id)
    today = datetime.now(timezone.utc).date()
    done = [task for task in tasks if task.status == TaskStatus.DONE]
    cancelled = [task for task in tasks if task.status == TaskStatus.CANCELLED]
    open_tasks = [
        task for task in tasks
        if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
    ]
    issues = db.query(Issue).filter(
        Issue.project_id == project_id,
        Issue.status.notin_([IssueStatus.RESOLVED, IssueStatus.CLOSED]),
    ).order_by(Issue.created_at.desc()).limit(MAX_FACT_ISSUES).all()

    def described(task: Task) -> dict:
        entry = {
            "name": _label(task),
            "state": _status_words(task)[0],
            "percentComplete": float(task.progress_percentage or 0),
        }
        planned_end = getattr(task, "planned_end_date", None)
        if planned_end:
            entry["plannedEndDate"] = planned_end.isoformat()
            if task in open_tasks and planned_end < today:
                entry["pastItsPlannedEndDate"] = True
        blockers = _incomplete_dependencies(task, tasks)
        if blockers:
            entry["waitingOn"] = [_label(item) for item in blockers]
        return entry

    return {
        "projectName": getattr(project, "name", None),
        "overallPercentComplete": float(
            getattr(project, "completion_percentage", 0) or 0
        ),
        "taskCounts": {
            "total": len(tasks),
            "completed": len(done),
            "stillOpen": len(open_tasks),
            "inProgress": len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            "notStarted": len([
                t for t in tasks if t.status in {TaskStatus.TODO, TaskStatus.BACKLOG}
            ]),
            "blocked": len([t for t in tasks if t.status == TaskStatus.BLOCKED]),
            "cancelled": len(cancelled),
        },
        "completedTasks": [described(task) for task in done[:MAX_FACT_TASKS]],
        "openTasks": [described(task) for task in open_tasks[:MAX_FACT_TASKS]],
        "openIssues": [
            {
                "title": item.title,
                "severity": getattr(item.severity, "value", str(item.severity)),
                "state": getattr(item.status, "value", str(item.status)),
            }
            for item in issues
        ],
        "openIssueCount": len(issues),
    }


def answer_query(
    db: Session,
    *,
    user: User,
    project_id,
    query: DetectedQuery,
    tasks: list[Task],
    spoken: str | None = None,
) -> VoiceAnswer | None:
    """Answer one question, or return None when this module cannot.

    `tasks` is the caller's already-authorized list. This function never widens
    it, so a question can only ever be answered about work the speaker may
    already see.

    Returning `None` is a real outcome, not a failure: it means the pipeline
    should fall back to asking a short clarifying question rather than
    inventing either an answer or an action.
    """
    topic = query.topic
    if topic == VoiceQueryTopic.UNKNOWN:
        return None

    if topic in REASONING_TOPICS:
        return _answer_reasoning(db, project_id=project_id, topic=topic, tasks=tasks)

    if topic in SITE_REPORT_TOPICS:
        return _answer_site_report_question(
            db, user=user, project_id=project_id, topic=topic
        )

    if topic in PROJECT_LEVEL_TOPICS:
        return _answer_project_question(db, project_id=project_id, topic=topic, tasks=tasks, user=user)

    if topic in TASK_LEVEL_TOPICS:
        reference = query.task_reference or spoken
        # "مين مسؤول عن المهمة السادسة؟" names a task by its position, which no
        # amount of word matching can see: the sixth task's words are "Order
        # electrical materials". The action path has resolved positions since
        # v2.3; a question deserves the same answer to the same phrase.
        positioned = match_by_position(reference, tasks) or match_by_position(
            spoken, tasks
        )
        if positioned is not None:
            return _answer_task_question(db, task=positioned, topic=topic, tasks=tasks)
        outcome = match_task(reference, tasks, limit=MAX_CANDIDATES)
        if not outcome.is_resolved or outcome.confidence < ANSWER_RESOLVE_CONFIDENCE:
            # Only now is "which task do you mean?" the right response — the
            # question is genuinely about one task and more than one fits.
            return VoiceAnswer(
                topic=topic.value,
                text_en="",
                text_ar="",
                candidates=outcome.candidates,
            )
        task = next(
            (item for item in tasks if item.id == outcome.resolved_task_id), None
        )
        if task is None:
            return None
        return _answer_task_question(db, task=task, topic=topic, tasks=tasks)

    return None


# ---------------------------------------------------------------------------
# Site reports
# ---------------------------------------------------------------------------

#: Review state → (English, Arabic). The stored values are the strings the
#: site-report API writes; anything else is shown as filed rather than guessed.
_REVIEW_WORDS: dict[str, tuple[str, str]] = {
    "draft": ("still a draft", "لسه مسودة"),
    "submitted": ("submitted", "مرفوع"),
    "approved": ("approved", "معتمد"),
    "rejected": ("returned", "مرفوض"),
}


def _report_body(report) -> str:
    """The report's own words, in the order the form asks for them.

    A site report is several free-text fields and any of them may be the only
    one filled in. Reading them in form order and taking the first that has
    content is what makes "شو كان آخر تقرير؟" answerable for a report whose
    author wrote everything under *work completed* and left the summary empty.
    """
    for value in (
        report.summary_text,
        report.work_completed,
        report.work_in_progress,
        report.notes,
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _report_facts(db: Session, report) -> dict:
    """One site report, reduced to what an answer may state."""
    author = db.get(User, report.submitted_by_id) if report.submitted_by_id else None
    status = str(report.review_status or "").lower()
    return {
        "reportDate": report.report_date.isoformat() if report.report_date else None,
        "submittedBy": getattr(author, "full_name", None),
        "reviewStatus": status,
        "summary": _report_body(report),
        "workCompleted": str(report.work_completed or "").strip() or None,
        "delays": str(report.delays or "").strip() or None,
        "issuesSummary": str(report.issues_summary or "").strip() or None,
        "weather": str(report.weather_conditions or "").strip() or None,
        "workersCount": report.workers_count,
        "progressPercentageReported": (
            float(report.progress_percentage_reported)
            if report.progress_percentage_reported is not None
            else None
        ),
    }


def _answer_site_report_question(
    db: Session, *, user: User, project_id, topic: VoiceQueryTopic
) -> VoiceAnswer | None:
    """Answer from the filed site reports, and say that is where it came from.

    This is the whole point of the topic existing. "اعطيني آخر تقرير موقع" used
    to land on PROJECT_PROGRESS or REPORT_READINESS — the only nearby topics —
    and came back as a project summary or as a readiness count. Both were
    truthful and neither was the document that was asked for, and an assistant
    that answers a different question confidently is worse than one that says
    it has nothing.

    So the reply always names the record: its date, who filed it, and its
    review state. A project summary never carries those, which is what makes
    the two answers impossible to confuse.
    """
    from app.services.voice_analysis_authorization import authorized_site_reports
    from app.services.voice_dates import describe_date

    limit = 1 if topic == VoiceQueryTopic.LATEST_SITE_REPORT else MAX_LISTED_TASKS
    reports = authorized_site_reports(db, user, project_id, limit=limit)
    if not reports:
        # Said as "there is no site report", never as "I could not find that
        # information": an empty record is a fact about the project, and the
        # engineer should not be left wondering whether the assistant looked.
        return VoiceAnswer(
            topic=topic.value,
            text_en="There are no site reports filed on this project yet.",
            text_ar="ما في ولا تقرير موقع مرفوع على هذا المشروع لهلأ.",
            data={"siteReports": [], "siteReportCount": 0},
        )

    if topic == VoiceQueryTopic.SITE_REPORTS:
        listed = [_report_facts(db, report) for report in reports]
        english_dates = _join(
            [
                f"{item['reportDate']}"
                + (f" by {item['submittedBy']}" if item["submittedBy"] else "")
                for item in listed
            ],
            arabic=False,
        )
        arabic_dates = _join(
            [
                describe_date(report.report_date, language="ar")
                if report.report_date
                else ""
                for report in reports
            ],
            arabic=True,
        )
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"The last {len(listed)} site reports: {english_dates}.",
            text_ar=f"آخر {len(listed)} تقارير موقع: {arabic_dates}.",
            data={"siteReports": listed, "siteReportCount": len(listed)},
        )

    report = reports[0]
    facts = _report_facts(db, report)
    review_en, review_ar = _REVIEW_WORDS.get(
        facts["reviewStatus"], ("filed", "مسجّل")
    )
    when_en = facts["reportDate"] or "an unrecorded date"
    when_ar = (
        describe_date(report.report_date, language="ar")
        if report.report_date
        else "بدون تاريخ"
    )
    by_en = f" filed by {facts['submittedBy']}" if facts["submittedBy"] else ""
    by_ar = f" من {facts['submittedBy']}" if facts["submittedBy"] else ""
    body = facts["summary"]
    body_en = f" It says: {body}" if body else " It carries no written summary."
    body_ar = f" وبيقول: {body}" if body else " وما فيه ملخص مكتوب."
    extras_en: list[str] = []
    extras_ar: list[str] = []
    if facts["delays"]:
        extras_en.append(f"Delays: {facts['delays']}.")
        extras_ar.append(f"التأخيرات: {facts['delays']}.")
    if facts["issuesSummary"]:
        extras_en.append(f"Issues: {facts['issuesSummary']}.")
        extras_ar.append(f"المشاكل: {facts['issuesSummary']}.")
    return VoiceAnswer(
        topic=topic.value,
        text_en=(
            f"The latest site report is dated {when_en}{by_en} and is {review_en}."
            f"{body_en} " + " ".join(extras_en)
        ).strip(),
        text_ar=(
            f"آخر تقرير موقع بتاريخ {when_ar}{by_ar} وحالته {review_ar}."
            f"{body_ar} " + " ".join(extras_ar)
        ).strip(),
        data={"siteReport": facts, "siteReportCount": 1},
    )


# ---------------------------------------------------------------------------
# One task
# ---------------------------------------------------------------------------

def _answer_task_question(
    db: Session, *, task: Task, topic: VoiceQueryTopic, tasks: list[Task]
) -> VoiceAnswer:
    english, arabic = _status_words(task)
    label = _label(task)
    percent = _percent(task)
    data = {
        "taskId": str(task.id),
        "taskCode": task.task_code,
        "name": task.name,
        "status": _status_name(task),
        "progressPercentage": float(task.progress_percentage or 0),
    }

    if topic in {VoiceQueryTopic.TASK_STATUS, VoiceQueryTopic.TASK_PROGRESS}:
        review = ""
        review_ar = ""
        if task.review_required and task.status == TaskStatus.UNDER_REVIEW:
            review = " It is awaiting Consultant review."
            review_ar = " وهي بانتظار مراجعة الاستشاري."
        elif task.review_required and task.status == TaskStatus.DONE:
            review = " Consultant review is complete."
            review_ar = " وتمت مراجعة الاستشاري."
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{label} is {english} at {percent}%.{review}",
            text_ar=f"{label} {arabic} بنسبة {percent}%.{review_ar}",
            data=data,
        )

    if topic == VoiceQueryTopic.TASK_ASSIGNEE:
        names = [assignee.full_name for assignee in task.assignees]
        data["assignees"] = names
        if not names:
            return VoiceAnswer(
                topic=topic.value,
                text_en=f"{label} has nobody assigned yet.",
                text_ar=f"{label} لا يوجد لها مسؤول حتى الآن.",
                data=data,
            )
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{label} is assigned to {_join(names, arabic=False)}.",
            text_ar=f"{label} مسؤول عنها {_join(names, arabic=True)}.",
            data=data,
        )

    if topic == VoiceQueryTopic.TASK_LOCATION:
        location = (task.description or "").strip()
        data["description"] = location or None
        if not location:
            return VoiceAnswer(
                topic=topic.value,
                text_en=f"No location is recorded for {label}.",
                text_ar=f"لا يوجد موقع مسجّل لـ {label}.",
                data=data,
            )
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{label}: {location}",
            text_ar=f"{label}: {location}",
            data=data,
        )

    # TASK_BLOCKERS and TASK_NEXT_STEP both reason over the dependency graph.
    incomplete = _incomplete_dependencies(task, tasks)
    data["blockers"] = [
        {"taskId": str(item.id), "taskCode": item.task_code, "name": item.name}
        for item in incomplete
    ]

    if topic == VoiceQueryTopic.TASK_BLOCKERS:
        if incomplete:
            names = [_label(item) for item in incomplete]
            return VoiceAnswer(
                topic=topic.value,
                text_en=(
                    f"{label} cannot start until these finish: "
                    f"{_join(names, arabic=False)}."
                ),
                text_ar=(
                    f"{label} لا يمكن أن تبدأ قبل انتهاء: "
                    f"{_join(names, arabic=True)}."
                ),
                data=data,
            )
        if task.status in {TaskStatus.TODO, TaskStatus.BACKLOG}:
            return VoiceAnswer(
                topic=topic.value,
                text_en=f"Nothing is blocking {label}. It is ready to start.",
                text_ar=f"لا يوجد ما يعيق {label}. جاهزة للبدء.",
                data=data,
            )
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"Nothing is blocking {label}. It is {english} at {percent}%.",
            text_ar=f"لا يوجد ما يعيق {label}. هي {arabic} بنسبة {percent}%.",
            data=data,
        )

    # TASK_NEXT_STEP — what the workflow expects after this task.
    successors = [
        other
        for other in tasks
        if any(edge.depends_on_task_id == task.id for edge in other.dependencies)
    ][:MAX_LISTED_TASKS]
    data["successors"] = [
        {"taskId": str(item.id), "taskCode": item.task_code, "name": item.name}
        for item in successors
    ]
    if task.status != TaskStatus.DONE and task.review_required and float(task.progress_percentage or 0) == 100:
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{label} is at 100% and needs to be submitted for Consultant review.",
            text_ar=f"{label} وصلت إلى 100% وتحتاج إلى إرسالها لمراجعة الاستشاري.",
            data=data,
        )
    if successors:
        names = [_label(item) for item in successors]
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"After {label} comes: {_join(names, arabic=False)}.",
            text_ar=f"بعد {label} تأتي: {_join(names, arabic=True)}.",
            data=data,
        )
    return VoiceAnswer(
        topic=topic.value,
        text_en=f"No task in this project depends on {label}.",
        text_ar=f"لا توجد مهمة في هذا المشروع تعتمد على {label}.",
        data=data,
    )


def _incomplete_dependencies(task: Task, tasks: list[Task]) -> list[Task]:
    """Predecessors that are not Done, restricted to tasks the user can see."""
    visible = {item.id: item for item in tasks}
    blockers: list[Task] = []
    for edge in task.dependencies:
        predecessor = visible.get(edge.depends_on_task_id)
        if predecessor is not None and predecessor.status != TaskStatus.DONE:
            blockers.append(predecessor)
    return blockers


# ---------------------------------------------------------------------------
# Whole project
# ---------------------------------------------------------------------------

def _answer_project_question(
    db: Session, *, project_id, topic: VoiceQueryTopic, tasks: list[Task], user: User
) -> VoiceAnswer:
    def listed(subset: list[Task], english: str, arabic: str) -> VoiceAnswer:
        data = {
            "count": len(subset),
            "tasks": [
                {
                    "taskId": str(item.id),
                    "taskCode": item.task_code,
                    "name": item.name,
                    "status": _status_name(item),
                    "progressPercentage": float(item.progress_percentage or 0),
                }
                for item in subset[:MAX_LISTED_TASKS]
            ],
        }
        if not subset:
            return VoiceAnswer(
                topic=topic.value,
                text_en=f"There are no {english}.",
                text_ar=f"لا توجد {arabic}.",
                data=data,
            )
        names = [_label(item) for item in subset[:MAX_LISTED_TASKS]]
        more_en = (
            f" and {len(subset) - MAX_LISTED_TASKS} more"
            if len(subset) > MAX_LISTED_TASKS
            else ""
        )
        more_ar = (
            f" و{len(subset) - MAX_LISTED_TASKS} غيرها"
            if len(subset) > MAX_LISTED_TASKS
            else ""
        )
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{len(subset)} {english}: {_join(names, arabic=False)}{more_en}.",
            text_ar=f"{len(subset)} {arabic}: {_join(names, arabic=True)}{more_ar}.",
            data=data,
        )

    open_tasks = [
        task for task in tasks
        if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
    ]

    if topic == VoiceQueryTopic.REMAINING_TASKS:
        return listed(open_tasks, "tasks remaining", "مهام متبقية")

    if topic == VoiceQueryTopic.NOT_STARTED_TASKS:
        return listed(
            [task for task in tasks if task.status in {TaskStatus.TODO, TaskStatus.BACKLOG}],
            "tasks not started", "مهام لم تبدأ",
        )

    if topic == VoiceQueryTopic.IN_PROGRESS_TASKS:
        return listed(
            [task for task in tasks if task.status == TaskStatus.IN_PROGRESS],
            "tasks in progress", "مهام قيد التنفيذ",
        )

    if topic == VoiceQueryTopic.COMPLETED_TASKS:
        return listed(
            [task for task in tasks if task.status == TaskStatus.DONE],
            "tasks completed", "مهام مكتملة",
        )

    if topic == VoiceQueryTopic.BLOCKED_TASKS:
        blocked = [
            task for task in tasks
            if task.status == TaskStatus.BLOCKED or _incomplete_dependencies(task, tasks)
        ]
        return listed(blocked, "tasks blocked", "مهام متوقفة")

    if topic == VoiceQueryTopic.NEXT_TASK:
        # "Next" means the first task nothing is holding up — dependency order,
        # not merely the next row.
        ready = [
            task for task in tasks
            if task.status in {TaskStatus.TODO, TaskStatus.BACKLOG}
            and not _incomplete_dependencies(task, tasks)
        ]
        if not ready:
            in_progress = [task for task in tasks if task.status == TaskStatus.IN_PROGRESS]
            if in_progress:
                return listed(in_progress, "tasks already in progress", "مهام قيد التنفيذ حالياً")
            return VoiceAnswer(
                topic=topic.value,
                text_en="There is no task ready to start; every remaining task is waiting on another.",
                text_ar="لا توجد مهمة جاهزة للبدء؛ كل المهام المتبقية تنتظر مهمة أخرى.",
                data={"count": 0, "tasks": []},
            )
        first = ready[0]
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"The next task ready to start is {_label(first)}.",
            text_ar=f"المهمة الجاهزة للبدء هي {_label(first)}.",
            data={
                "taskId": str(first.id),
                "taskCode": first.task_code,
                "name": first.name,
                "alternatives": [_label(item) for item in ready[1:MAX_LISTED_TASKS]],
            },
        )

    if topic == VoiceQueryTopic.PROJECT_PROGRESS:
        project = db.get(Project, project_id)
        done = len([task for task in tasks if task.status == TaskStatus.DONE])
        overall = float(getattr(project, "completion_percentage", 0) or 0)
        return VoiceAnswer(
            topic=topic.value,
            text_en=(
                f"The project is at {overall:g}% overall. "
                f"{done} of {len(tasks)} tasks are done, {len(open_tasks)} still open."
            ),
            text_ar=(
                f"المشروع منجز بنسبة {overall:g}% إجمالاً. "
                f"{done} من {len(tasks)} مهمة مكتملة، و{len(open_tasks)} ما زالت مفتوحة."
            ),
            data={
                "completionPercentage": overall,
                "doneCount": done,
                "totalCount": len(tasks),
                "openCount": len(open_tasks),
            },
        )

    if topic == VoiceQueryTopic.OPEN_ISSUES:
        # Both terminal states count as closed; only RESOLVED was excluded at
        # first, which would have reported long-closed issues as open.
        issues = db.query(Issue).filter(
            Issue.project_id == project_id,
            Issue.status.notin_([IssueStatus.RESOLVED, IssueStatus.CLOSED]),
        ).order_by(Issue.created_at.desc()).limit(MAX_LISTED_TASKS).all()
        data = {
            "count": len(issues),
            "issues": [
                {"id": str(item.id), "title": item.title,
                 "severity": getattr(item.severity, "value", str(item.severity))}
                for item in issues
            ],
        }
        if not issues:
            return VoiceAnswer(
                topic=topic.value,
                text_en="There are no open issues on this project.",
                text_ar="لا توجد مشاكل مفتوحة في هذا المشروع.",
                data=data,
            )
        titles = [item.title for item in issues]
        return VoiceAnswer(
            topic=topic.value,
            text_en=f"{len(issues)} open issues: {_join(titles, arabic=False)}.",
            text_ar=f"{len(issues)} مشاكل مفتوحة: {_join(titles, arabic=True)}.",
            data=data,
        )

    # REPORT_READINESS — the same threshold the report-readiness endpoint uses,
    # read here rather than duplicated so both surfaces agree.
    from app.models.voice_action import VoiceExecutionLog
    from app.models.voice_analysis import VoiceAnalysis

    start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    updates = db.query(VoiceExecutionLog.id).join(
        VoiceAnalysis, VoiceExecutionLog.voice_analysis_id == VoiceAnalysis.id
    ).filter(
        VoiceAnalysis.project_id == project_id,
        VoiceExecutionLog.actor_user_id == user.id,
        VoiceExecutionLog.result == "EXECUTED",
        VoiceExecutionLog.created_at >= start,
        VoiceExecutionLog.created_at < start + timedelta(days=1),
    ).count()
    ready = updates >= 2
    return VoiceAnswer(
        topic=topic.value,
        text_en=(
            f"Yes — {updates} confirmed updates today, enough for a site report."
            if ready
            else f"Not yet — {updates} confirmed updates today."
        ),
        text_ar=(
            f"نعم — {updates} تحديثات مؤكدة اليوم، وهي كافية لإعداد تقرير موقع."
            if ready
            else f"ليس بعد — {updates} تحديثات مؤكدة اليوم."
        ),
        data={"ready": ready, "updateCount": updates},
    )


# ---------------------------------------------------------------------------
# Reasoning
# ---------------------------------------------------------------------------

def _overdue(tasks: list[Task]) -> list[Task]:
    """Open work whose planned end date has passed."""
    today = datetime.now(timezone.utc).date()
    return [
        task for task in tasks
        if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
        and getattr(task, "planned_end_date", None)
        and task.planned_end_date < today
    ]


def _answer_reasoning(
    db: Session, *, project_id, topic: VoiceQueryTopic, tasks: list[Task]
) -> VoiceAnswer:
    """Explain, rather than report.

    Everything here reads the same authorized rows a status answer reads; the
    difference is that it combines them. "ليش ما بنقدر نبدأ؟" is answered by the
    dependency graph plus the open issues plus the schedule, not by any single
    column, and an answer quoting only one of them would be true and useless.

    Recommendations are offered only where the data supports one, and they name
    the specific thing to clear. An assistant that ends every answer with
    generic advice teaches people to stop reading the advice.
    """
    open_tasks = [
        task for task in tasks
        if task.status not in {TaskStatus.DONE, TaskStatus.CANCELLED}
    ]
    blocked = [(task, _incomplete_dependencies(task, tasks)) for task in open_tasks]
    blocked = [(task, deps) for task, deps in blocked if deps]
    issues = db.query(Issue).filter(
        Issue.project_id == project_id,
        Issue.status.notin_([IssueStatus.RESOLVED, IssueStatus.CLOSED]),
    ).order_by(Issue.created_at.desc()).limit(MAX_LISTED_TASKS).all()
    late = _overdue(open_tasks)

    data = {
        "blockedCount": len(blocked),
        "openIssueCount": len(issues),
        "overdueCount": len(late),
        "openCount": len(open_tasks),
    }

    if topic in {VoiceQueryTopic.WHY_BLOCKED, VoiceQueryTopic.WHY_DELAYED}:
        english: list[str] = []
        arabic: list[str] = []
        if blocked:
            names = [
                f"{_label(task)} (waiting on "
                f"{_join([_label(dep) for dep in deps], arabic=False)})"
                for task, deps in blocked[:3]
            ]
            names_ar = [
                f"{_label(task)} (تنتظر "
                f"{_join([_label(dep) for dep in deps], arabic=True)})"
                for task, deps in blocked[:3]
            ]
            english.append(
                f"{len(blocked)} tasks are waiting on unfinished work: "
                f"{_join(names, arabic=False)}."
            )
            arabic.append(
                f"{len(blocked)} مهام تنتظر أعمالاً غير منتهية: "
                f"{_join(names_ar, arabic=True)}."
            )
        if issues:
            titles = [item.title for item in issues[:3]]
            english.append(
                f"{len(issues)} open issues may be holding work up: "
                f"{_join(titles, arabic=False)}."
            )
            arabic.append(
                f"{len(issues)} مشاكل مفتوحة قد تكون سبب التوقف: "
                f"{_join(titles, arabic=True)}."
            )
        if late:
            english.append(f"{len(late)} tasks are past their planned end date.")
            arabic.append(f"{len(late)} مهام تجاوزت تاريخ الانتهاء المخطط.")
        if not english:
            return VoiceAnswer(
                topic=topic.value,
                text_en=(
                    "Nothing in the project data explains a hold-up: no task is "
                    "waiting on another, there are no open issues, and nothing "
                    "is overdue."
                ),
                text_ar=(
                    "لا يوجد في بيانات المشروع ما يفسر التوقف: لا مهمة تنتظر "
                    "أخرى، ولا توجد مشاكل مفتوحة، ولا شيء متأخر عن موعده."
                ),
                data=data,
            )
        if blocked:
            first = blocked[0][1][0]
            english.append(f"Finishing {_label(first)} would unblock the most work.")
            arabic.append(f"إنهاء {_label(first)} سيفتح أكبر قدر من العمل.")
        return VoiceAnswer(
            topic=topic.value,
            text_en=" ".join(english),
            text_ar=" ".join(arabic),
            data=data,
        )

    # PRIORITY_FOCUS and RECOMMENDED_NEXT_STEP: what to do next, and why that.
    # Ordered by what actually costs the project most: work already late, then
    # work holding other work up, then work simply ready to begin.
    if late:
        target = late[0]
        return VoiceAnswer(
            topic=topic.value,
            text_en=(
                f"{_label(target)} is past its planned end date and still "
                f"{_status_words(target)[0]} at {_percent(target)}%. "
                "That is the most urgent thing on the project right now."
            ),
            text_ar=(
                f"{_label(target)} تجاوزت تاريخ الانتهاء المخطط وما زالت "
                f"{_status_words(target)[1]} بنسبة {_percent(target)}%. "
                "هذا أهم ما يحتاج انتباهك الآن."
            ),
            data={**data, "taskId": str(target.id)},
        )
    if blocked:
        task, deps = blocked[0]
        return VoiceAnswer(
            topic=topic.value,
            text_en=(
                f"Clearing {_label(deps[0])} would release {_label(task)} "
                "and is the highest-value next step."
            ),
            text_ar=(
                f"إنهاء {_label(deps[0])} سيفتح {_label(task)} "
                "وهو أفضل خطوة تالية."
            ),
            data={**data, "taskId": str(deps[0].id)},
        )
    ready = [
        task for task in open_tasks
        if task.status in {TaskStatus.TODO, TaskStatus.BACKLOG}
        and not _incomplete_dependencies(task, tasks)
    ]
    if ready:
        return VoiceAnswer(
            topic=topic.value,
            text_en=(
                "Nothing is blocked. The next task ready to start is "
                f"{_label(ready[0])}."
            ),
            text_ar=(
                "لا يوجد ما هو متوقف. المهمة الجاهزة للبدء هي "
                f"{_label(ready[0])}."
            ),
            data={**data, "taskId": str(ready[0].id)},
        )
    in_progress = [task for task in open_tasks if task.status == TaskStatus.IN_PROGRESS]
    if in_progress:
        return VoiceAnswer(
            topic=topic.value,
            text_en=(
                "Everything ready to start is already underway; "
                f"{_label(in_progress[0])} is the furthest along at "
                f"{_percent(in_progress[0])}%."
            ),
            text_ar=(
                "كل ما هو جاهز للبدء قيد التنفيذ فعلاً؛ "
                f"{_label(in_progress[0])} هي الأكثر تقدماً بنسبة "
                f"{_percent(in_progress[0])}%."
            ),
            data={**data, "taskId": str(in_progress[0].id)},
        )
    return VoiceAnswer(
        topic=topic.value,
        text_en="There is no open work left on this project.",
        text_ar="لا يوجد عمل مفتوح متبقٍ في هذا المشروع.",
        data=data,
    )
