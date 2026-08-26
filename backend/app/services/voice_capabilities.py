"""What voice can do, why it can do it, and who is allowed to.

This is the registry the whole v3 layer turns on. The product rule it encodes
is one sentence: *anything this person can do through the platform, they can
ask for in their own words.* That is impossible to hold together with a list of
phrases — "غيّر الموعد", "أجّل المهمة", "خلي التسليم يوم 15", "move the
deadline" and "push it a week" are one operation and five hundred sentences —
so nothing here is keyed on wording. Each entry describes a **capability**: an
operation the platform already performs, what it needs before it can run, which
permission governs it, and how a person would ask for it.

Four consumers read this table and none of them keeps its own copy:

  * the **prompt**, which is rendered per speaker and lists only the
    capabilities that speaker actually holds, with examples of how people ask;
  * **draft building**, which asks for whatever a capability still needs;
  * the **permission pre-check**, which declines in words rather than letting
    an engineer confirm something the backend will refuse a second later;
  * the **rules engine**, which re-checks everything at execution time anyway.

The registry is deliberately *not* the authority on permission. It mirrors the
platform's own rules so the assistant can be honest early, and the real check
always runs again inside the same service the web UI calls. A capability listed
here can still be refused at execution, and that refusal is the one that counts.

Payload *fields* are not defined here either — they live in
`app.ai.action_payload_contract`, which the rules engine validates against and
the prompt renders. This module composes that table with everything else a
capability needs, so the two can never disagree about what a field is called.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.action_payload_contract import ACTION_CONTRACTS
from app.core.deps import (
    is_consultant_engineer,
    is_main_contractor_engineer,
    is_worker,
    user_has_project_access,
)
from app.models.enums import UserRole, UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.voice_analysis import ActionRiskLevel, SuggestedActionType
from app.services.authorization import has_permission
from app.services.voice_action_policy import action_risk

#: Coarse role names used by the registry, matching how the rest of the voice
#: code already talks about people.
WORKER = "worker"
ENGINEER = "contractor_engineer"
CONSULTANT = "external_consultant"
MANAGER = "project_manager"

#: Categories exist for one reason: to group the rendered capability list so a
#: speaker's prompt reads as sections rather than as thirty flat lines.
TASKS = "tasks"
ISSUES = "issues"
REPORTS = "reports"
MESSAGING = "messaging"
REVIEWS = "reviews"


@dataclass(frozen=True)
class Capability:
    """One thing the assistant can do, and everything needed to decide about it."""

    action: SuggestedActionType
    category: str
    #: What it does, in words a person would use. Read by the prompt and by the
    #: confirmation composer, so it must never contain a field name.
    purpose: str
    #: How people actually ask for it. These are teaching examples for the
    #: model, not patterns to match — the model generalizes from them, which is
    #: exactly what a phrase list cannot do.
    examples: tuple[str, ...]
    #: Roles that may perform it at all, mirroring `VoiceRulesEngine`.
    roles: frozenset[str]
    #: Catalogue permission checked before proposing, when the platform has one
    #: for this operation. `None` means the operation's own service is the only
    #: gate — messaging, for example, decides per recipient.
    permission_code: str | None = None
    #: True when the operation is meaningless without a task.
    needs_task: bool = False
    #: True when it targets an issue instead of a task.
    needs_issue: bool = False
    #: Extra gate for capabilities the platform restricts structurally rather
    #: than by permission code — the site-report draft, which only an assigned
    #: Site Engineer may create.
    membership_flag: str | None = None

    @property
    def required_fields(self) -> tuple[str, ...]:
        return ACTION_CONTRACTS[self.action].required

    @property
    def optional_fields(self) -> tuple[str, ...]:
        return ACTION_CONTRACTS[self.action].optional

    @property
    def risk(self) -> ActionRiskLevel:
        return action_risk(self.action)

    @property
    def is_destructive(self) -> bool:
        return self.action in DESTRUCTIVE


#: Operations that remove something. They get their own confirmation wording
#: and they refuse to execute without an explicit acknowledgement, because a
#: misheard sentence must never be able to delete work.
DESTRUCTIVE: frozenset[SuggestedActionType] = frozenset({
    SuggestedActionType.DELETE_TASK,
})


_ALL_ENGINEERS = frozenset({ENGINEER, MANAGER})


CAPABILITIES: tuple[Capability, ...] = (
    # -- tasks --------------------------------------------------------------
    Capability(
        SuggestedActionType.CREATE_TASK, TASKS,
        "add a new task to the project",
        (
            "أنشئ مهمة لمهندس الكهرباء عشان يراجع المخططات",
            "ضيف مهمة جديدة اسمها فحص العزل",
            "create a task to inspect the waterproofing",
        ),
        frozenset({MANAGER}),
        permission_code="task.create",
    ),
    Capability(
        SuggestedActionType.START_TASK, TASKS,
        "start a task that has not begun",
        ("ابدأ المهمة السادسة", "بلشنا بمهمة الحفر", "start the excavation task"),
        _ALL_ENGINEERS,
        permission_code="task.update_progress",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_PROGRESS, TASKS,
        "update how far along a task is",
        (
            "خلصنا نص المهمة السادسة",
            "المهمة تبعت الكهرباء صارت 70%",
            "the rebar task is at eighty percent",
        ),
        _ALL_ENGINEERS,
        permission_code="task.update_progress",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_SCHEDULE, TASKS,
        "change when a task is due to start or finish",
        (
            "خلّي موعد المهمة السادسة الأسبوع الجاي",
            "المهمة تبعت الكهرباء تأخرت، خلّي موعدها يوم 15",
            "أجّل مهمة التكييف لبعد أسبوعين",
            "move the ductwork deadline to 15 September",
        ),
        frozenset({MANAGER}),
        permission_code="task.edit",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_ASSIGNMENT, TASKS,
        "change who is responsible for a task",
        (
            "عيّن أحمد على المهمة تبعت المخططات",
            "خلّي مهمة الكهرباء على المهندس سامي",
            "assign the HVAC task to Layla",
        ),
        frozenset({MANAGER}),
        permission_code="task.edit",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_PRIORITY, TASKS,
        "change a task's priority",
        (
            "غيّر أولوية هاي المهمة لعالية",
            "خلي أولوية مهمة التكييف حرجة",
            "make the electrical task low priority",
        ),
        frozenset({MANAGER}),
        permission_code="task.edit",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_DETAILS, TASKS,
        "rename a task or change its description",
        (
            "غيّر اسم المهمة السادسة لطلب مواد الكهرباء",
            "ضيف على وصف المهمة إنها تشمل الطابق الثاني",
            "rename task six",
        ),
        frozenset({MANAGER}),
        permission_code="task.edit",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.DELETE_TASK, TASKS,
        "delete a task from the project",
        ("احذف المهمة السادسة", "امسح مهمة التكييف", "delete the ductwork task"),
        frozenset({MANAGER}),
        permission_code="task.edit",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.SUBMIT_TASK_FOR_REVIEW, TASKS,
        "send a finished task to the consultant for review",
        (
            "ارسل المهمة السادسة للمراجعة",
            "خلصنا المهمة وجاهزة لمراجعة الاستشاري",
            "submit the columns task for review",
        ),
        _ALL_ENGINEERS,
        permission_code="task.update_progress",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.ADD_TASK_NOTE, TASKS,
        "add a note to a task",
        ("سجل ملاحظة على المهمة السادسة", "add a note to the excavation task"),
        _ALL_ENGINEERS,
        needs_task=True,
    ),
    # -- issues -------------------------------------------------------------
    Capability(
        SuggestedActionType.CREATE_ISSUE, ISSUES,
        "record a problem on site",
        (
            "سجل مشكلة إن المواد الكهربائية ما وصلت",
            "في مشكلة بالعزل بالطابق الثاني",
            "report an issue about the missing drawings",
        ),
        _ALL_ENGINEERS | {CONSULTANT},
        permission_code="issue.create",
    ),
    Capability(
        SuggestedActionType.UPDATE_ISSUE_STATUS, ISSUES,
        "resolve, close, reopen or progress an existing issue",
        (
            "المشكلة تبعت المواد انحلّت",
            "سكّر مشكلة العزل",
            "reopen the drawings issue",
        ),
        frozenset({MANAGER}),
        permission_code="issue.resolve",
        needs_issue=True,
    ),
    Capability(
        SuggestedActionType.ASSIGN_ISSUE, ISSUES,
        "give an issue an owner",
        ("خلّي مشكلة المواد على أحمد", "assign the insulation issue to Sami"),
        frozenset({MANAGER}),
        permission_code="issue.resolve",
        needs_issue=True,
    ),
    # -- field evidence and reports ----------------------------------------
    Capability(
        SuggestedActionType.CREATE_FIELD_SUBMISSION, REPORTS,
        "record what was done on site for the engineer to verify",
        ("خلصنا صب الأعمدة بالمنطقة B", "we finished the block work today"),
        frozenset({WORKER}),
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.CREATE_SITE_REPORT_DRAFT, REPORTS,
        "prepare a site report for today's work",
        (
            "ارفع تقرير موقع عن شغل اليوم",
            "بدي أرفع تقرير، خلصنا صب الأعمدة بالمنطقة B",
            "write up today's site report",
        ),
        _ALL_ENGINEERS,
        permission_code="site_report.submit",
        membership_flag="is_site_engineer",
    ),
    Capability(
        SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT, REPORTS,
        "report a design change for review",
        ("في تغيير بمسار الكهرباء", "report a design change on the duct routing"),
        _ALL_ENGINEERS,
        permission_code="design_change.propose",
    ),
    # -- messaging ----------------------------------------------------------
    Capability(
        SuggestedActionType.SEND_PROJECT_MESSAGE, MESSAGING,
        "send a message to someone on the project",
        (
            "ابعت رسالة للمهندس سامي واحكيله إن المواد تأخرت",
            "ابعت لأحمد إنه الاجتماع الساعة 10",
            "message the consultant about tomorrow's inspection",
        ),
        _ALL_ENGINEERS,
    ),
    Capability(
        SuggestedActionType.SEND_OWNER_UPDATE, MESSAGING,
        "send an update to the project owner",
        (
            "ابعت رسالة لصاحب المشروع واحكيله إن المواد تأخرت",
            "خبّر المالك إننا خلصنا الطابق الأول",
            "update the owner about the delay",
        ),
        _ALL_ENGINEERS,
    ),
    Capability(
        SuggestedActionType.CREATE_TASK_MESSAGE, MESSAGING,
        "post a message on a task's discussion",
        ("اكتب على المهمة السادسة إننا مستنيين المواد", "post on the task thread"),
        _ALL_ENGINEERS,
        needs_task=True,
    ),
    # -- reviews ------------------------------------------------------------
    Capability(
        SuggestedActionType.PREPARE_CONSULTANT_REVIEW, REVIEWS,
        "record a consultant's review decision",
        ("وافقت على المهمة السادسة", "reject the columns submission, cover is short"),
        frozenset({CONSULTANT}),
        permission_code="task.review",
        needs_task=True,
    ),
)

BY_ACTION: dict[SuggestedActionType, Capability] = {
    item.action: item for item in CAPABILITIES
}


def capability_for(action: SuggestedActionType | str) -> Capability | None:
    try:
        return BY_ACTION.get(SuggestedActionType(action))
    except ValueError:
        return None


def voice_role(user: User) -> str:
    """The registry's name for this person's role.

    The same mapping the provider call already uses, kept in one place so a
    consultant is a consultant everywhere in the voice layer.
    """
    if is_worker(user):
        return WORKER
    if is_consultant_engineer(user):
        return CONSULTANT
    if user.role == UserRole.PROJECT_MANAGER:
        return MANAGER
    if user.role == UserRole.ENGINEER:
        return ENGINEER
    return str(user.role.value)


def _is_project_manager(db: Session, user: User, project_id) -> bool:
    """Manager *of this project*, which is what every task rule actually means."""
    if user.role != UserRole.PROJECT_MANAGER:
        return False
    project = db.get(Project, project_id)
    return bool(project and project.project_manager_id == user.id)


def _has_membership_flag(db: Session, user: User, project_id, flag: str) -> bool:
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id,
        ProjectMember.is_active == True,  # noqa: E712
    ).first()
    return bool(membership and getattr(membership, flag, False))


def is_available(
    db: Session, *, user: User, project_id, capability: Capability
) -> bool:
    """Whether this person could perform this capability on this project.

    A mirror of the platform's own rules, never a replacement for them: the
    service that performs the operation checks again, and that check is the one
    that decides. This exists so the assistant can say "ما عندك صلاحية" in a
    sentence instead of walking somebody through a review card for something
    that was never going to work.
    """
    if user.status != UserStatus.ACTIVE:
        return False
    if not user_has_project_access(db, user, project_id):
        return False
    if voice_role(user) not in capability.roles:
        return False
    # Task-level operations that the platform reserves for the project's own
    # manager. Role alone is not enough: a manager of another project is not a
    # manager here.
    if capability.roles == frozenset({MANAGER}) and not _is_project_manager(
        db, user, project_id
    ):
        return False
    if MANAGER in capability.roles and ENGINEER in capability.roles:
        # Shared engineer/manager capabilities still require the engineer to be
        # a main-contractor engineer, exactly as the rules engine requires.
        if user.role == UserRole.ENGINEER and not is_main_contractor_engineer(user):
            return False
    if capability.permission_code and not has_permission(
        db, user, capability.permission_code, project_id
    ):
        return False
    if capability.membership_flag and not _has_membership_flag(
        db, user, project_id, capability.membership_flag
    ):
        return False
    return True


def available_capabilities(db: Session, *, user: User, project_id) -> list[Capability]:
    """Everything this person may ask for on this project, in registry order."""
    return [
        capability for capability in CAPABILITIES
        if is_available(db, user=user, project_id=project_id, capability=capability)
    ]


def render_catalogue(capabilities: list[Capability]) -> str:
    """The capability list as the model sees it.

    Rendered per speaker rather than baked into the prompt, which is what makes
    the assistant's offer honest: a worker is never shown how to ask for a task
    to be deleted, so it never proposes one and never has to refuse one.
    """
    if not capabilities:
        return "This speaker currently has no executable capabilities. Answer questions only."
    lines = ["CAPABILITIES YOU MAY PROPOSE FOR THIS SPEAKER (nothing else is executable):"]
    for category in (TASKS, ISSUES, REPORTS, MESSAGING, REVIEWS):
        group = [item for item in capabilities if item.category == category]
        if not group:
            continue
        lines.append(f"[{category}]")
        for capability in group:
            needs = []
            if capability.needs_task:
                needs.append("a task")
            if capability.needs_issue:
                needs.append("an issue")
            needs.extend(capability.required_fields)
            lines.append(
                f"- {capability.action.value}: {capability.purpose}."
                + (f" Needs: {', '.join(needs)}." if needs else "")
                + " People say it like: "
                + "; ".join(f'"{example}"' for example in capability.examples)
            )
    return "\n".join(lines)
