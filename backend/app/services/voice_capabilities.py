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
from app.core.deps import user_has_project_access
from app.models.enums import UserStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.voice_analysis import ActionRiskLevel, SuggestedActionType
from app.services.authorization import has_permission
from app.services.voice_action_policy import action_risk

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
    #: The catalogue permission that governs this operation. Mandatory: a
    #: capability without one would be a capability nothing authorizes, which
    #: is what the retired `roles` set had become.
    permission_code: str
    #: True when the operation is meaningless without a task.
    needs_task: bool = False
    #: True when it targets an issue instead of a task.
    needs_issue: bool = False
    #: Extra gate for capabilities the platform restricts structurally rather
    #: than by permission code — the site-report draft, which only an assigned
    #: Site Engineer may create.
    membership_flag: str | None = None
    #: True for operations the platform reserves for whoever runs *this*
    #: project. Holding `task.edit` somewhere is not the same as running the
    #: job the sentence is about, and the retired registry expressed this by
    #: giving those capabilities to the project-manager role alone.
    requires_project_management: bool = False

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
        "task.create",
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.START_TASK, TASKS,
        "start a task that has not begun",
        ("ابدأ المهمة السادسة", "بلشنا بمهمة الحفر", "start the excavation task"),
        "task.update_progress",
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
        "task.update_progress",
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
        "task.edit",
        needs_task=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_ASSIGNMENT, TASKS,
        "change who is responsible for a task",
        (
            "عيّن أحمد على المهمة تبعت المخططات",
            "خلّي مهمة الكهرباء على المهندس سامي",
            "assign the HVAC task to Layla",
        ),
        "task.edit",
        needs_task=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_PRIORITY, TASKS,
        "change a task's priority",
        (
            "غيّر أولوية هاي المهمة لعالية",
            "خلي أولوية مهمة التكييف حرجة",
            "make the electrical task low priority",
        ),
        "task.edit",
        needs_task=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.UPDATE_TASK_DETAILS, TASKS,
        "rename a task or change its description",
        (
            "غيّر اسم المهمة السادسة لطلب مواد الكهرباء",
            "ضيف على وصف المهمة إنها تشمل الطابق الثاني",
            "rename task six",
        ),
        "task.edit",
        needs_task=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.DELETE_TASK, TASKS,
        "delete a task from the project",
        ("احذف المهمة السادسة", "امسح مهمة التكييف", "delete the ductwork task"),
        "task.edit",
        needs_task=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.SUBMIT_TASK_FOR_REVIEW, TASKS,
        "send a finished task to the consultant for review",
        (
            "ارسل المهمة السادسة للمراجعة",
            "خلصنا المهمة وجاهزة لمراجعة الاستشاري",
            "submit the columns task for review",
        ),
        "task.update_progress",
        needs_task=True,
    ),
    Capability(
        SuggestedActionType.ADD_TASK_NOTE, TASKS,
        "add a note to a task",
        ("سجل ملاحظة على المهمة السادسة", "add a note to the excavation task"),
        "task.add_note",
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
        "issue.create",
    ),
    Capability(
        SuggestedActionType.UPDATE_ISSUE_STATUS, ISSUES,
        "resolve, close, reopen or progress an existing issue",
        (
            "المشكلة تبعت المواد انحلّت",
            "سكّر مشكلة العزل",
            "reopen the drawings issue",
        ),
        "issue.resolve",
        needs_issue=True,
        requires_project_management=True,
    ),
    Capability(
        SuggestedActionType.ASSIGN_ISSUE, ISSUES,
        "give an issue an owner",
        ("خلّي مشكلة المواد على أحمد", "assign the insulation issue to Sami"),
        "issue.resolve",
        needs_issue=True,
        requires_project_management=True,
    ),
    # -- field evidence and reports ----------------------------------------
    Capability(
        SuggestedActionType.CREATE_FIELD_SUBMISSION, REPORTS,
        "record what was done on site for the engineer to verify",
        ("خلصنا صب الأعمدة بالمنطقة B", "we finished the block work today"),
        "field_evidence.submit",
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
        "site_report.submit",
        membership_flag="is_site_engineer",
    ),
    Capability(
        SuggestedActionType.CREATE_DESIGN_CHANGE_REPORT, REPORTS,
        "report a design change for review",
        ("في تغيير بمسار الكهرباء", "report a design change on the duct routing"),
        "design_change.propose",
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
        "message.send",
    ),
    Capability(
        SuggestedActionType.SEND_OWNER_UPDATE, MESSAGING,
        "send an update to the project owner",
        (
            "ابعت رسالة لصاحب المشروع واحكيله إن المواد تأخرت",
            "خبّر المالك إننا خلصنا الطابق الأول",
            "update the owner about the delay",
        ),
        "message.send_client",
    ),
    Capability(
        SuggestedActionType.CREATE_TASK_MESSAGE, MESSAGING,
        "post a message on a task's discussion",
        ("اكتب على المهمة السادسة إننا مستنيين المواد", "post on the task thread"),
        "task.comment",
        needs_task=True,
    ),
    # -- reviews ------------------------------------------------------------
    Capability(
        SuggestedActionType.PREPARE_CONSULTANT_REVIEW, REVIEWS,
        "record a consultant's review decision",
        ("وافقت على المهمة السادسة", "reject the columns submission, cover is short"),
        "task.review",
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


def _manages_this_project(db: Session, user: User, project_id) -> bool:
    """Whether this person runs *this* job.

    Some operations — creating work, moving deadlines, reassigning, closing
    issues — belong to whoever is accountable for the project, not to anybody
    who happens to hold the permission on some other one. The retired registry
    expressed this by reserving those capabilities for the project-manager
    role; expressed as authority rather than as a job title it is: the assigned
    manager, or somebody who may manage this project's team.
    """
    project = db.get(Project, project_id)
    if project is None:
        return False
    if project.project_manager_id == user.id:
        return True
    return has_permission(db, user, "project.manage_members", project_id)


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
    """Whether this person may perform this capability on this project.

    This is now a *use* of the platform's authorization, not a mirror of it.
    The registry used to carry its own four-name role vocabulary and decide
    from that, which made Voice a second authorization system — a role could be
    reconfigured everywhere in the platform and Voice would carry on answering
    from its own table. Every decision below comes from `has_permission`, the
    same call the web endpoint makes.

    The operation's own service still checks again when the action executes,
    and that check is still the one that counts. This runs early so the
    assistant can decline in a sentence instead of walking somebody through a
    confirmation card for something that was never going to work.
    """
    if user.status != UserStatus.ACTIVE:
        return False
    if not user_has_project_access(db, user, project_id):
        return False
    if not has_permission(db, user, capability.permission_code, project_id):
        return False
    if capability.requires_project_management and not _manages_this_project(
        db, user, project_id
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
