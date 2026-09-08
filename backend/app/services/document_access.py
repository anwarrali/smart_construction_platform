"""Who may read which document, and which ingested file.

One implementation, several callers: the documents API, RAG retrieval, and the
AI tool layer all narrow through here. That matters most for retrieval, because
a path that checked only project access would be a clean bypass of document
permissions — a client could ask about a draft they are forbidden to download
and get it quoted back with page citations. Unlogged, and it would read like a
feature rather than a leak.

Four layers, applied in order. The first one that decides, decides:

  1. **project access** — `user_has_project_access`. Nothing below runs without it.
  2. **party scope** — a participant who is on the project for an outside party
     reads what has been shared with that party, and nothing else.
  3. **`project.view_all_disciplines`** — office staff who hold it see every document.
  4. **discipline scope** — office staff who do not are narrowed to documents
     attached to work in their own disciplines, plus project-level documents.

## Why the party check comes first

It is the difference between a deny-list and an allow-list. An external
participant's access is decided *only* by what someone deliberately shared, so
no permission, role or misconfiguration further down can widen it. Putting
`project.view_all_disciplines` first instead would mean a contractor whose role happened
to carry that code — and the seeded contractor template inherits it, because it
inherits an Engineer's permissions — would read the whole project. That is the
exact failure this ordering exists to make impossible.

The client is the one external party with a rule of its own, and it is the rule
the client portal already had: official project files, plus evidence of work
that has been completed and approved. Sharing can add to that; nothing takes it
away.

## Ingested files

`readable_ingested_file_ids` lives in this module rather than beside the
ingestion pipeline, and that is deliberate: the two rules must be readable side
by side or they will drift, and the one that drifts is the one nobody audits.

An `IngestedFile` has no party-share table and no task, so the four layers
above cannot be applied mechanically. Each is *derived* instead, and the
derivation is written out in `readable_ingested_files_query`. The property that
matters is that no layer comes out weaker than its document equivalent — a
contractor who may read three shared documents must not thereby be able to read
every file on the project.

## Migration note

Contractor-side engineers used to read every document on their projects, and
under the party scope they would read none. `app.db.rbac_backfill` therefore
writes explicit shares for everything they could already see. Deny-by-default
governs from that point on; it is not applied retroactively to revoke access
nobody decided to revoke.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.deps import user_has_project_access
from app.models.document import Document
from app.models.enums import DocumentType, TaskStatus
from app.models.ingestion import IngestedFile
from app.models.rbac import DocumentPartyShare
from app.models.task import Task
from app.models.user import User
from app.services import rbac
from app.services.authorization import has_permission


def party_document_scope(query, db: Session, party_id: uuid.UUID, user_id: uuid.UUID):
    """Narrow to what this external party may read.

    Deny-by-default: an explicit share, or something this person uploaded
    themselves. A contractor who submits a document does not lose sight of it
    while it waits to be shared back.
    """
    shared = db.query(DocumentPartyShare.document_id).filter(
        DocumentPartyShare.party_id == party_id
    ).scalar_subquery()
    return query.filter(or_(
        Document.id.in_(shared),
        Document.uploaded_by_id == user_id,
    ))


def _official_or_approved():
    """Official project files, and evidence of approved completed work.

    The client portal's rule, expressed once. Kept byte-for-byte identical to
    the predicate the Owner role carried before the redesign, because both the
    migrated path and the pre-migration fallback below rely on it meaning
    exactly the same thing.
    """
    official = and_(
        Document.task_id.is_(None),
        Document.document_type.in_([DocumentType.CONTRACT, DocumentType.PERMIT]),
    )
    approved_work = Document.task.has(and_(
        Task.status == TaskStatus.DONE,
        Task.review_status == "approved",
    ))
    return official, approved_work


def client_document_scope(query, db: Session, party_id: uuid.UUID | None, user_id: uuid.UUID):
    """The client portal's rule, plus anything shared with the client party."""
    official, approved_work = _official_or_approved()
    conditions = [official, approved_work]
    if party_id is not None:
        shared = db.query(DocumentPartyShare.document_id).filter(
            DocumentPartyShare.party_id == party_id
        ).scalar_subquery()
        conditions.append(Document.id.in_(shared))
    return query.filter(or_(*conditions))


def discipline_document_scope(
    query, db: Session, current_user: User, project_id: uuid.UUID
):
    """Narrow office staff to their own disciplines.

    Reads the configurable discipline assignment rather than the retired
    single-valued `EngineerProfile.discipline`, so somebody who covers
    Mechanical *and* Electrical now sees both — a case the old model could not
    represent at all.

    Somebody with no discipline recorded is not narrowed. Narrowing them to the
    empty set would hide the whole project from a person the office put on it,
    which is a worse failure than showing them a drawing outside their
    specialism.
    """
    disciplines = rbac.disciplines_for_member(db, current_user.id, project_id)
    codes = rbac.discipline_codes(disciplines)
    if not codes:
        return query
    authorized_tasks = db.query(Task.id).filter(
        Task.project_id == project_id,
        Task.discipline.in_(codes),
    ).scalar_subquery()
    return query.filter(or_(
        Document.task_id.is_(None),
        Document.task_id.in_(authorized_tasks),
    ))


def readable_documents_query(db: Session, current_user: User, project_id: uuid.UUID):
    """A Document query narrowed to what this user may read in this project.

    Returns a *query* rather than a list of ids so the filtering stays in the
    database and the caller can compose it into a subquery — a project with
    thousands of documents does not have to be materialised in Python to answer
    one question.

    Assumes project access has already been checked; callers raise on that
    first, because the failure messages differ.
    """
    query = db.query(Document).filter(Document.project_id == project_id)

    context = rbac.membership_context(db, current_user.id, project_id)
    if context.is_external:
        if context.party.kind == "CLIENT":
            return client_document_scope(query, db, context.party.id, current_user.id)
        return party_document_scope(query, db, context.party.id, current_user.id)

    if not current_user.is_internal:
        # On the project without a party record, and not office staff. There is
        # no basis for showing them anything beyond their own uploads.
        return query.filter(Document.uploaded_by_id == current_user.id)

    if has_permission(db, current_user, "project.view_all_disciplines", project_id):
        return query

    return discipline_document_scope(query, db, current_user, project_id)


# `_pre_migration_scope` stood here and is gone with the contract step. It
# reproduced the retired role-based document scoping for an account the
# backfill had not reached — an Owner who had no client party yet would
# otherwise have fallen through to "the whole project", turning a half-finished
# migration into a disclosure. There is no such account any more:
# `resolved_permissions` refuses one outright.


def readable_document_ids(db: Session, current_user: User, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of the documents this user may read in this project."""
    return [
        row[0] for row in
        readable_documents_query(db, current_user, project_id)
        .with_entities(Document.id).all()
    ]


def readable_document_ids_across(
    db: Session, current_user: User, project_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Readable document ids across several projects.

    Resolved per project rather than as one clause, because the rule genuinely
    differs by project: the same person can be office staff on one and a
    contractor's representative on another, and a single combined filter could
    only express whichever of the two it was written for. The loop costs one
    query per accessible project, which is a small number for the endpoints
    that need it (a document list, a cross-project search).
    """
    ids: list[uuid.UUID] = []
    for project_id in project_ids:
        ids.extend(readable_document_ids(db, current_user, project_id))
    return ids


def assert_document_readable(db: Session, current_user: User, document: Document) -> None:
    """Raise unless this user may read this specific document.

    Deliberately reuses `readable_documents_query` rather than re-deriving the
    rules: if the two ever disagreed, the single-document check and the
    retrieval filter would grant different access, and the retrieval path is the
    one nobody would think to audit.
    """
    if not user_has_project_access(db, current_user, document.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    permitted = (
        readable_documents_query(db, current_user, document.project_id)
        .filter(Document.id == document.id)
        .first()
    )
    if permitted is not None:
        return

    context = rbac.membership_context(db, current_user.id, document.project_id)
    if context.is_external and context.party.kind == "CLIENT":
        raise HTTPException(
            status_code=403,
            detail="Clients can access finalized and approved documents only",
        )
    if context.is_external:
        raise HTTPException(
            status_code=403,
            detail="This document has not been shared with your organization",
        )
    raise HTTPException(status_code=403, detail="This document is outside your discipline")


# --- Ingested files ---------------------------------------------------------
#
# The unified ingestion pipeline's files, under the *same* four-layer rule as
# documents, derived rather than copied. See the module docstring.


def readable_ingested_files_query(db: Session, current_user: User, project_id: uuid.UUID):
    """An `IngestedFile` query narrowed to what this user may read here.

    Layer by layer, with the derivation stated because the reasoning is the
    whole safety argument:

    **Party scope.** `party_document_scope` grants what was explicitly shared
    with the party, plus the person's own uploads. There is no share table for
    ingested files, so the shared set is empty and the rule reduces to *own
    uploads only*. That is deny-by-default, exactly as intended — not an
    oversight to be fixed by widening it. When file sharing is built, it plugs
    in here as another `or_` arm.

    **Client scope.** `client_document_scope` grants official project files
    (contracts, permits), evidence of approved completed work, and shares. An
    ingested file has no `document_type` and no task, so none of the first two
    can be evaluated for it and no share exists. Reduces to own uploads only.

    **On the project with no party, not office staff.** Identical to the
    document rule: their own uploads.

    **`project.view_all_disciplines`.** Identical: everything in the project.

    **Discipline scope.** `discipline_document_scope` grants documents with no
    task (project-level) plus those on tasks in the person's disciplines. Every
    ingested file has no task — it is project-level by construction — so this
    grants all of them. Not a widening: it is what the same predicate already
    says about a document with no task.

    Assumes project access has been checked, matching
    `readable_documents_query`.
    """
    query = db.query(IngestedFile).filter(IngestedFile.project_id == project_id)

    context = rbac.membership_context(db, current_user.id, project_id)
    if context.is_external:
        # Both party kinds reduce to the same thing today. Kept as one branch
        # rather than two identical ones so that adding file sharing later has
        # one place to change, not two that must be changed together.
        return query.filter(IngestedFile.uploaded_by_id == current_user.id)

    if not current_user.is_internal:
        return query.filter(IngestedFile.uploaded_by_id == current_user.id)

    # Office staff, with or without `project.view_all_disciplines`: an ingested
    # file is project-level, which both branches of the document rule grant.
    return query


def readable_ingested_file_ids(
    db: Session, current_user: User, project_id: uuid.UUID
) -> list[uuid.UUID]:
    """Ids of the ingested files this user may read in this project.

    Returns `[]` — meaning *zero readable files* — rather than raising, when
    the caller has no project access or lacks `document.view`. Both checks are
    here and not left to the caller: a retrieval path that forgot one would
    widen silently, and this is the function every such path goes through.

    An empty list is never interpreted as "all" anywhere downstream; see
    `VectorStore.search`.
    """
    if not user_has_project_access(db, current_user, project_id):
        return []
    # The same code the unified file endpoints check before showing a file
    # list. Reading a file's text through retrieval is a read of that file.
    if not has_permission(db, current_user, "document.view", project_id):
        return []
    return [
        row[0] for row in
        readable_ingested_files_query(db, current_user, project_id)
        .with_entities(IngestedFile.id).all()
    ]


def assert_ingested_file_readable(
    db: Session, current_user: User, file: IngestedFile
) -> None:
    """Raise unless this user may read this specific ingested file.

    Reuses the query above rather than re-deriving the rules, for the same
    reason `assert_document_readable` does: if the single-file check and the
    retrieval filter ever disagreed, the retrieval path is the one nobody
    would think to audit.
    """
    if not user_has_project_access(db, current_user, file.project_id):
        raise HTTPException(status_code=404, detail="File not found")
    if not has_permission(db, current_user, "document.view", file.project_id):
        raise HTTPException(
            status_code=403, detail="You cannot open this project's files"
        )
    permitted = (
        readable_ingested_files_query(db, current_user, file.project_id)
        .filter(IngestedFile.id == file.id)
        .first()
    )
    if permitted is None:
        raise HTTPException(
            status_code=403,
            detail="This file has not been shared with you",
        )
