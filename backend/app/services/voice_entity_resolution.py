"""Turning what somebody *said* into the thing they meant.

An engineer says "المهمة تبعت المخططات", "صاحب المشروع", "الأسبوع الجاي",
"أولوية خطر", "مشكلة المواد". None of those is an identifier, a date, or an
enum value, and every one of them has to become exactly that before any
operation can run.

The rule for all of it: **resolve against what the project actually contains,
never against what the model believes.** Tasks and issues are matched inside
the list the speaker is already authorized to see; people are matched inside
the project's own team; dates are computed by `voice_dates`; priorities and
issue states are matched against the platform's own enums. A model-supplied
identifier is only ever *checked*, never trusted — which is what keeps a
hallucinated UUID from reaching a database.

Ambiguity is a result. Two people called Ahmad, two issues about materials, a
weekday that could be today or next week: each of those returns "more than one
fits" and the caller asks. Nothing here guesses when the cost of guessing is a
wrong task, a wrong person, or a wrong date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.enums import IssueStatus, UserRole
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.voice_task_matcher import (
    CANDIDATE_THRESHOLD,
    MAX_CANDIDATES,
    normalize,
    task_position,
)

#: Below this an issue is not plausibly the one that was meant.
ISSUE_MATCH_THRESHOLD = 0.34


@dataclass(frozen=True)
class Person:
    """One project member, reduced to what resolution and display need."""

    user_id: UUID
    name: str
    role: str

    def as_option(self) -> dict:
        return {"value": str(self.user_id), "label": self.name, "role": self.role}


def project_people(db: Session, *, project_id, exclude_user_id=None) -> list[Person]:
    """Everyone active on this project, other than the speaker.

    The team list is the whole universe of resolvable people: a name that does
    not appear here cannot be resolved, and that refusal is the point.
    """
    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True,  # noqa: E712
    ).all()
    people: list[Person] = []
    for member in members:
        if exclude_user_id is not None and member.user_id == exclude_user_id:
            continue
        person = db.get(User, member.user_id)
        if person is None:
            continue
        people.append(
            Person(person.id, person.full_name or "", member.role_on_project.value)
        )
    return sorted(people, key=lambda item: item.name)


def project_owner(db: Session, project_id) -> Person | None:
    """The project's owner, resolved from the project itself.

    "ابعت لصاحب المشروع" needs no clarification and never should: the project
    knows who its owner is, and asking would be the assistant pretending not
    to.
    """
    project = db.get(Project, project_id)
    if not project or not project.owner_id:
        return None
    person = db.get(User, project.owner_id)
    if person is None:
        return None
    return Person(person.id, person.full_name or "", "owner")


#: Spoken ways of naming somebody by their part in the project rather than by
#: name. Substring-matched, because Arabic attaches the article and
#: prepositions directly: "للاستشاري" is one word.
_ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "owner": ("مالك", "صاحب المشروع", "صاحب المشرو", "owner", "client"),
    "project_manager": ("مدير", "manager", "pm"),
    "engineer": ("مهندس", "engineer"),
    "worker": ("عامل", "عمال", "worker"),
    "consultant": ("استشار", "consultant", "reviewer"),
    "contractor": ("مقاول", "contractor"),
}


def match_people(spoken: str, people: list[Person]) -> list[Person]:
    """The people an utterance names — by identifier, by name, or by role.

    Returning several is a real outcome: "ابعت لأحمد" on a project with two
    Ahmads is a question, not a coin toss.
    """
    text = normalize(spoken)
    if not text:
        return []
    try:
        chosen = UUID(spoken.strip())
    except ValueError:
        chosen = None
    if chosen is not None:
        return [person for person in people if person.user_id == chosen]

    spoken_tokens = [token for token in text.split() if len(token) > 2]
    scored = [
        (person, _name_overlap(spoken_tokens, text, person)) for person in people
    ]
    best = max((score for _, score in scored), default=0)
    if best:
        # Only the closest matches. Saying a full name should not return
        # everybody who shares a first name with them — but two people who
        # match equally well still both come back, because that is a question.
        return [person for person, score in scored if score == best]
    for role, words in _ROLE_WORDS.items():
        if any(word in text for word in words):
            matched = [person for person in people if role in person.role]
            if matched:
                return matched
    return []


def _name_overlap(spoken_tokens: list[str], text: str, person: Person) -> int:
    """How much of this person's name the utterance contains.

    Arabic attaches prepositions to the following word, so "ابعت لأحمد" carries
    the name as "لاحمد" — one token, no space, and invisible to an exact
    comparison. A spoken token therefore counts when it *ends with* a name
    token, which is what a leading clitic looks like after normalization.

    Counting rather than answering yes/no is what lets a full name beat a
    shared first name: "أحمد خليل" scores two against that person and one
    against every other Ahmad on the project.
    """
    normalized = normalize(person.name)
    if not normalized:
        return 0
    matched = 0
    for name_token in normalized.split():
        if len(name_token) < 3:
            continue
        if any(
            spoken == name_token or spoken.endswith(name_token)
            for spoken in spoken_tokens
        ):
            matched += 1
    return matched


#: Words that follow the same prepositions a name does but are not people.
#: Compared after normalization, so "المهمة" and "مهمه" are the same entry.
_NOT_A_PERSON: frozenset[str] = frozenset({
    "مهمه", "المهمه", "مهام", "المهام", "مشروع", "المشروع", "تقرير", "التقرير",
    "مشكله", "المشكله", "موقع", "الموقع", "شغل", "الشغل", "عمل", "العمل",
    "فريق", "الفريق", "مراجعه", "المراجعه", "يوم", "اليوم", "بكرا", "بكره",
    "تاريخ", "التاريخ", "موعد", "الموعد", "نسبه", "النسبه", "حاله", "الحاله",
    "كل", "الكل", "هاي", "هذا", "هذه", "هيك", "حتى", "لانه", "لان",
})

#: Arabic function words that begin with the same ل- the name clitic does.
#: "لازم" is not "ازم", and without this list every "لازم نخلص الشغل" would
#: produce a sentence about a person nobody mentioned. Compared whole, after
#: normalization.
_LAM_WORDS: frozenset[str] = frozenset({
    "لازم", "لسه", "لسا", "لهيك", "لحتى", "لحد", "لكن", "لكنه", "لما", "لو",
    "لانه", "لان", "لغايه", "لعند", "لوحده", "للاسف", "لهلا", "ليش", "لهذا",
})

#: Only Arabic letters or a Latin word. A number, a percent sign or a date is
#: never a person, and letting one through would put "19" in a sentence saying
#: it could not be found.
_NAME_TOKEN = re.compile(r"^(?:[ء-ي]{3,}|[A-Za-z]{2,})$")

#: How many words of a spoken name to keep. "نور علي" is two; anything longer
#: is the rest of the sentence.
_MAX_NAME_WORDS = 2


def named_person_reference(spoken: str | None) -> str | None:
    """The words the speaker used to name somebody, when they named one.

    Exists for one sentence: *"ما لقيت مستخدم باسم أحمد ضمن أعضاء المشروع."*
    When a name resolves to nobody, the assistant has to say **which** name it
    could not find — "who should be responsible for it?" is a question the
    engineer has already answered, and asking it again reads as not listening.

    Deliberately conservative. It reads a name only where Arabic and English
    both mark one — the attached ل- clitic, or "to"/"for" — and refuses
    anything that is plainly not a person. Returning None is a normal outcome,
    and the caller falls back to wording that names no name rather than
    inventing one.
    """
    if not spoken:
        return None
    tokens = [token for token in re.split(r"[\s،,.؟?!:؛;]+", spoken.strip()) if token]
    for index, token in enumerate(tokens):
        candidate: str | None = None
        if normalize(token) in _LAM_WORDS:
            continue
        if token.startswith("لل") and len(token) > 3:
            candidate = "ال" + token[2:]
        elif token.startswith("ل") and len(token) > 3:
            candidate = token[1:]
        elif token.casefold() in {"to", "for", "الى", "إلى"}:
            following = tokens[index + 1: index + 1 + _MAX_NAME_WORDS]
            candidate = following[0] if following else None
            if candidate is not None:
                parts = [
                    part for part in following
                    if _NAME_TOKEN.match(part)
                    and normalize(part) not in _NOT_A_PERSON
                ]
                return " ".join(parts[:_MAX_NAME_WORDS]) or None
        if candidate is None or not _NAME_TOKEN.match(candidate):
            continue
        if normalize(candidate) in _NOT_A_PERSON:
            continue
        parts = [candidate]
        for extra in tokens[index + 1: index + _MAX_NAME_WORDS]:
            if _NAME_TOKEN.match(extra) and normalize(extra) not in _NOT_A_PERSON:
                parts.append(extra)
        return " ".join(parts[:_MAX_NAME_WORDS])
    return None


def assignable_people(db: Session, *, project_id) -> list[Person]:
    """Project members who may actually hold a task.

    Not the same list as `project_people`, and the difference is a real bug it
    fixes: assignment used to resolve a spoken name against *every* member,
    including the owner and anybody whose project role cannot carry work. The
    name resolved, the draft reached the review card looking correct, and
    execution failed at the tasks API with "every assignee must be an active
    Engineer, Worker, Consultant, or assigned Project Manager" — a rule the
    assistant could have applied before ever proposing it.

    The eligibility rule itself is imported from the tasks API rather than
    restated, so the two lists cannot drift.
    """
    from app.api.tasks import TASK_ASSIGNEE_ROLES
    from app.models.enums import UserStatus

    members = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.is_active == True,  # noqa: E712
    ).all()
    project = db.get(Project, project_id)
    people: list[Person] = []
    for member in members:
        if member.role_on_project not in TASK_ASSIGNEE_ROLES:
            continue
        person = db.get(User, member.user_id)
        if person is None or person.role not in TASK_ASSIGNEE_ROLES:
            continue
        if getattr(person, "status", None) != UserStatus.ACTIVE:
            continue
        if member.role_on_project == UserRole.PROJECT_MANAGER and (
            project is None or project.project_manager_id != member.user_id
        ):
            # Any project manager may be a member; only *this* project's
            # assigned manager is eligible to be given its work.
            continue
        people.append(
            Person(person.id, person.full_name or "", member.role_on_project.value)
        )
    return sorted(people, key=lambda item: item.name)


def resolve_recipients(
    db: Session,
    *,
    project_id,
    speaker_id,
    spoken: str,
    include_owner: bool = True,
) -> list[Person]:
    """Who a message is for, from the words around it."""
    people = project_people(db, project_id=project_id, exclude_user_id=speaker_id)
    owner = project_owner(db, project_id) if include_owner else None
    if owner is not None and owner.user_id != speaker_id and any(
        word in normalize(spoken) for word in _ROLE_WORDS["owner"]
    ):
        # The project has exactly one owner of record. Several people may carry
        # an owner *role* on the team, and asking "which owner?" when the
        # project itself knows the answer is the assistant being pedantic about
        # something nobody is confused by.
        return [owner]
    if owner is not None and owner.user_id != speaker_id:
        if not any(person.user_id == owner.user_id for person in people):
            people = [*people, owner]
        elif any(word in normalize(spoken) for word in _ROLE_WORDS["owner"]):
            # The owner may sit in the team list under a different project
            # role; the spoken word "المالك" should still find them.
            people = [
                Person(person.user_id, person.name, "owner")
                if person.user_id == owner.user_id else person
                for person in people
            ]
    return match_people(spoken, people)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def authorized_issues(db: Session, *, project_id, limit: int = 50) -> list[Issue]:
    """Open-first issues on this project, newest first.

    Scoped by project only, mirroring the issues API, which lets any project
    member read the project's issues. The *write* path is still governed by
    `app.api.issues.update_issue`, which decides who may change what.
    """
    return db.query(Issue).filter(
        Issue.project_id == project_id
    ).order_by(
        Issue.status.in_([IssueStatus.RESOLVED, IssueStatus.CLOSED]),
        Issue.created_at.desc(),
    ).limit(limit).all()


@dataclass(frozen=True)
class IssueMatch:
    issue_id: UUID
    title: str
    status: str
    score: float

    def as_option(self) -> dict:
        return {
            "value": str(self.issue_id),
            "label": self.title,
            "status": self.status,
            "score": round(self.score, 3),
        }


def rank_issues(spoken: str | None, issues: list[Issue]) -> list[IssueMatch]:
    """Issues ordered by how well they fit what was said.

    Word overlap rather than the task scorer: an issue's text is a sentence
    somebody typed ("المواد الكهربائية ما وصلت"), not a coded task name, so
    concepts and level numbers have nothing to work on and shared words are the
    honest signal.
    """
    text = normalize(spoken)
    spoken_tokens = {token for token in text.split() if len(token) > 2}
    ranked: list[IssueMatch] = []
    for issue in issues:
        haystack = normalize(f"{issue.title} {issue.description or ''}")
        tokens = {token for token in haystack.split() if len(token) > 2}
        overlap = len(spoken_tokens & tokens) / len(spoken_tokens) if spoken_tokens else 0.0
        ranked.append(IssueMatch(
            issue_id=issue.id,
            title=issue.title,
            status=str(getattr(issue.status, "value", issue.status)),
            score=overlap,
        ))
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def match_issue(
    spoken: str | None, issues: list[Issue]
) -> tuple[UUID | None, list[IssueMatch]]:
    """One issue, or the shortlist to ask about.

    A positional reference ("المشكلة الثانية") indexes the same list the
    engineer was just shown, exactly as it does for tasks.
    """
    if not issues:
        return None, []
    position = task_position(spoken)
    if position is not None and 1 <= position <= len(issues):
        issue = issues[position - 1]
        return issue.id, []
    ranked = rank_issues(spoken, issues)
    plausible = [item for item in ranked if item.score >= CANDIDATE_THRESHOLD]
    if plausible and plausible[0].score >= ISSUE_MATCH_THRESHOLD and (
        len(plausible) == 1 or plausible[0].score - plausible[1].score >= 0.2
    ):
        return plausible[0].issue_id, []
    return None, (plausible or ranked)[:MAX_CANDIDATES]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedDate:
    """A spoken date, resolved or not."""

    value: date | None
    spoken: str
    options: tuple[date, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.value is not None


def resolve_date_field(
    value: str | None, *, fallback_text: str | None = None, today: date | None = None
) -> ResolvedDate | None:
    """Read a payload date field, which arrives as whatever the speaker said.

    The model is told to pass the words through untouched, so this accepts both
    an already-ISO value (a corrected draft, or a client that sent a real date)
    and a phrase like "الأسبوع الجاي". When the field itself says nothing, the
    whole utterance is tried — people say "خلّي المهمة السادسة الأسبوع الجاي"
    without repeating the date into a field.
    """
    from app.services.voice_dates import resolve_spoken_date

    raw = (value or "").strip()
    if raw:
        try:
            return ResolvedDate(date.fromisoformat(raw), raw)
        except ValueError:
            pass
    spoken = resolve_spoken_date(raw or None, today=today)
    if spoken is None and fallback_text:
        spoken = resolve_spoken_date(fallback_text, today=today)
    if spoken is None:
        return None
    return ResolvedDate(spoken.value, spoken.spoken, spoken.options)
