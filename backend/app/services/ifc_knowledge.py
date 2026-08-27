"""Answering questions about the model from what the IFC pipeline extracted.

Phase 2 produced the facts — elements with measured extents, spatial structure,
and coordination findings carrying geometric evidence — but nothing could reach
them from a question. "What conflicts with beam B1?" had no path: the vector
store holds document text, and IFC content was never indexed into it.

Indexing IFC into a vector store would have been the wrong fix. Element names
and GlobalIds are identifiers, not prose, and similarity search over them
retrieves near-spellings rather than facts. These are database lookups, and
they return exact answers with the evidence attached.

Nothing here widens authorization. The caller has already been through
`ifc_policy.can_ifc(..., "VIEW")`; this module only ever reads within the one
project it is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.ifc import IFCCoordinationFinding, IFCElement, IFCModelVersion


@dataclass(frozen=True)
class KnowledgeFact:
    """One retrieved fact, with the record it came from.

    `source_reference` is what a citation is built from, so an answer can
    always be traced to a row a person can open.
    """

    statement: str
    source_type: str
    source_id: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IFCKnowledgeResult:
    facts: list[KnowledgeFact]
    #: What the subject of the question was resolved to, when one was named.
    resolved_subject: str | None = None
    #: Why nothing came back, when nothing did. Never left implicit: "no
    #: conflicts" and "no model to look in" are different answers.
    unavailable_reason: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.facts)


#: Words that are asking about interference rather than about an element.
CONFLICT_TERMS = (
    "clash", "clashes", "conflict", "conflicts", "interference", "intersect",
    "intersects", "passes through", "runs through",
    "تعارض", "تصادم", "تداخل", "يمر خلال",
)

#: Noise words stripped before looking for an element name or tag. Without this
#: "what conflicts with beam B1" searches for the whole sentence.
STOPWORDS = {
    "what", "which", "who", "does", "do", "is", "are", "the", "a", "an", "with",
    "conflicts", "conflict", "clash", "clashes", "interference", "intersects",
    "intersect", "passes", "runs", "through", "in", "on", "of", "and", "or",
    "show", "me", "tell", "about", "any", "there", "model", "ifc", "element",
    "شو", "ما", "هو", "مع", "في", "على", "عنصر", "النموذج", "تعارض", "تداخل",
}


def _active_version(db: Session, project_id) -> IFCModelVersion | None:
    """The revision a question is about: the active one, else the newest ready.

    A project can hold many revisions, and answering from a superseded one
    would be worse than not answering.
    """
    ready = ["READY", "READY_WITH_WARNINGS"]
    query = db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == project_id,
        IFCModelVersion.processing_status.in_(ready),
        IFCModelVersion.archived_at.is_(None),
    )
    return (
        query.filter(IFCModelVersion.is_active.is_(True)).first()
        or query.order_by(IFCModelVersion.created_at.desc()).first()
    )


def _subject_terms(question: str) -> list[str]:
    words = [
        word for word in re.findall(r"[\w\-]+", question, flags=re.UNICODE)
        if word.casefold() not in STOPWORDS and len(word) > 1
    ]
    # Longest first: "B1" and "Beam" both appear, but the identifier is the
    # one that will actually distinguish an element.
    return sorted(words, key=len, reverse=True)[:5]


def _find_elements(db: Session, version_id, question: str) -> list[IFCElement]:
    terms = _subject_terms(question)
    if not terms:
        return []
    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.extend([
            IFCElement.name.ilike(pattern),
            IFCElement.tag.ilike(pattern),
            func.lower(IFCElement.global_id) == term.casefold(),
        ])
    return (
        db.query(IFCElement)
        .filter(IFCElement.version_id == version_id, or_(*conditions))
        .order_by(IFCElement.name)
        .limit(10)
        .all()
    )


def _describe(element: IFCElement) -> str:
    parts = [element.entity_type, f"'{element.name}'"]
    if element.tag:
        parts.append(f"(tag {element.tag})")
    if element.discipline:
        parts.append(f"— {element.discipline.replace('_', ' ').lower()}")
    return " ".join(parts)


def answer_ifc_question(db: Session, *, project_id, question: str) -> IFCKnowledgeResult:
    """Retrieve model facts for a question, or say why there are none."""
    version = _active_version(db, project_id)
    if not version:
        return IFCKnowledgeResult(
            facts=[], unavailable_reason="This project has no processed IFC model.",
        )

    terms = _subject_terms(question)
    elements = _find_elements(db, version.id, question)
    asks_about_conflict = any(term in question.casefold() for term in CONFLICT_TERMS)

    if asks_about_conflict:
        # Whether a subject was *named* matters as much as whether one was
        # found. "Are there any clashes?" names nothing and wants them all;
        # "what conflicts with ZZZ999?" names something, and if that something
        # does not exist the honest answer says so. Returning every finding in
        # the project would be answering a question nobody asked.
        return _conflicts(db, version, elements, named_subject=bool(terms))
    if elements:
        return IFCKnowledgeResult(
            facts=[
                KnowledgeFact(
                    statement=(
                        f"{_describe(element)} is in revision "
                        f"{version.revision_code or f'v{version.version_number}'}"
                        + (f", on {element.storey.name}" if element.storey else "")
                        + "."
                    ),
                    source_type="IFC_ELEMENT", source_id=str(element.id),
                    evidence={
                        "globalId": element.global_id, "entityType": element.entity_type,
                        "discipline": element.discipline, "versionId": str(version.id),
                        "boundingBox": element.bounding_box_json,
                    },
                )
                for element in elements[:5]
            ],
            resolved_subject=elements[0].name,
        )
    return IFCKnowledgeResult(
        facts=[],
        unavailable_reason=(
            "No element in the current model matched that description. "
            "Try the element's name, tag or IFC GlobalId."
        ),
    )


def _conflicts(db: Session, version, elements, *, named_subject: bool) -> IFCKnowledgeResult:
    """Coordination findings, optionally narrowed to a named element."""
    if named_subject and not elements:
        return IFCKnowledgeResult(
            facts=[],
            unavailable_reason=(
                "No element in the current model matched that description, so there is "
                "nothing to report conflicts for. Try the element's name, tag or IFC "
                "GlobalId, or ask for all coordination findings."
            ),
        )
    query = db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == version.id,
        IFCCoordinationFinding.element_b_id.isnot(None),
        IFCCoordinationFinding.false_positive.is_(False),
    )
    subject = None
    if elements:
        subject = elements[0].name
        ids = [element.id for element in elements]
        query = query.filter(or_(
            IFCCoordinationFinding.element_a_id.in_(ids),
            IFCCoordinationFinding.element_b_id.in_(ids),
        ))
    findings = query.order_by(IFCCoordinationFinding.confidence.desc()).limit(20).all()

    if not findings:
        named = f" involving {subject}" if subject else ""
        return IFCKnowledgeResult(
            facts=[], resolved_subject=subject,
            unavailable_reason=(
                f"No coordination findings{named} are recorded against revision "
                f"{version.revision_code or f'v{version.version_number}'}."
            ),
        )

    facts = []
    for finding in findings:
        evidence = finding.geometry_evidence_json if isinstance(finding.geometry_evidence_json, dict) else {}
        location = f" on {finding.storey}" if finding.storey else ""
        facts.append(KnowledgeFact(
            # The wording repeats the finding's own hedge on purpose. A fact
            # retrieved out of its card must carry the same caveat the card
            # carries, or the caveat is lost exactly where it matters.
            statement=(
                f"{finding.title}{location}. Severity {finding.severity}, "
                f"confidence {finding.confidence:.2f}. "
                f"{evidence.get('claim', '')} — verify the solid geometry before acting."
            ),
            source_type="IFC_COORDINATION_FINDING", source_id=str(finding.id),
            evidence={
                "severity": finding.severity, "confidence": finding.confidence,
                "storey": finding.storey, "status": finding.status,
                "penetrationMetres": evidence.get("penetrationMetres"),
                "structural": (evidence.get("structural") or {}).get("globalId"),
                "service": (evidence.get("service") or {}).get("globalId"),
                "versionId": str(version.id),
            },
        ))
    return IFCKnowledgeResult(facts=facts, resolved_subject=subject)
