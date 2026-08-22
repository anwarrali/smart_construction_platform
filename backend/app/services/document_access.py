"""Who may read which document.

Extracted from `api/documents.py`, where these rules previously lived as two
private helpers. They are shared now because RAG answers questions *out of*
document text, and a retrieval path that checked only project access would be
a clean bypass of document permissions: an Owner could ask about a draft they
are forbidden to download and get it quoted back with page citations. That is
worse than the download endpoint being open, because it is unlogged and reads
like a feature rather than a leak.

One implementation, two callers. Duplicating these rules is exactly how they
would drift apart, and the drift would be silent.

Three layers, applied in order:

  1. project access      — `user_has_project_access`
  2. owner scope         — Owners see official project files and evidence of
                           approved, completed work; not drafts in progress
  3. consultant scope    — a consultant engineer sees documents in their own
                           discipline, plus project-level documents

Layers 2 and 3 are role-conditional; a Project Manager or Admin passes both.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.deps import is_consultant_engineer, user_has_project_access
from app.models.document import Document
from app.models.enums import DocumentType, TaskStatus, UserRole
from app.models.task import Task
from app.models.user import User


def consultant_document_scope(query, db: Session, current_user: User, project_id: uuid.UUID):
    """Narrow a Document query to a consultant engineer's own discipline."""
    if not current_user.engineer_profile:
        raise HTTPException(status_code=403, detail="Consultant specialization is required")
    discipline = current_user.engineer_profile.discipline.value
    authorized_tasks = db.query(Task.id).filter(
        Task.project_id == project_id,
        Task.discipline == discipline,
    )
    return query.filter(or_(Document.task_id.is_(None), Document.task_id.in_(authorized_tasks)))


def owner_document_scope(query):
    """Owners see official project files and evidence from approved completed work only."""
    return query.filter(or_(
        and_(
            Document.task_id.is_(None),
            Document.document_type.in_([DocumentType.CONTRACT, DocumentType.PERMIT]),
        ),
        Document.task.has(and_(
            Task.status == TaskStatus.DONE,
            Task.review_status == "approved",
        )),
    ))


def readable_documents_query(db: Session, current_user: User, project_id: uuid.UUID):
    """A Document query narrowed to what this user may read in this project.

    The basis for RAG retrieval. Returning a *query* rather than a list of ids
    keeps the filtering in the database and lets the caller compose it into a
    subquery, so a project with thousands of documents does not have to be
    materialised in Python to answer one question.

    Assumes project access has already been checked — callers are expected to
    have raised on that first, because the failure messages differ.
    """
    query = db.query(Document).filter(Document.project_id == project_id)
    if current_user.role == UserRole.OWNER:
        query = owner_document_scope(query)
    if is_consultant_engineer(current_user):
        query = consultant_document_scope(query, db, current_user, project_id)
    return query


def readable_document_ids(db: Session, current_user: User, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Ids of the documents this user may read in this project."""
    return [row[0] for row in readable_documents_query(db, current_user, project_id).with_entities(Document.id).all()]


def assert_document_readable(db: Session, current_user: User, document: Document) -> None:
    """Raise unless this user may read this specific document.

    Deliberately reuses `readable_documents_query` rather than re-deriving the
    rules: if the two ever disagreed, the single-document check and the
    retrieval filter would grant different access, and the retrieval path is
    the one nobody would think to audit.
    """
    if not user_has_project_access(db, current_user, document.project_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    permitted = (
        readable_documents_query(db, current_user, document.project_id)
        .filter(Document.id == document.id)
        .first()
    )
    if permitted is None:
        if current_user.role == UserRole.OWNER:
            raise HTTPException(
                status_code=403,
                detail="Owners can access finalized and approved documents only",
            )
        raise HTTPException(status_code=403, detail="This document is outside your discipline")
