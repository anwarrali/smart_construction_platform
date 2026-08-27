"""Argument contracts for every tool.

Separate from the registry so the shapes can be read and tested on their own,
and so an agent framework can render the JSON schema without importing
handlers. Constraints are real here rather than decorative: a tool that
accepted an unbounded string would be a way to push arbitrary text into the
platform through an agent, so lengths and ranges are stated and the runtime
rejects anything outside them before a handler runs.
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.user import CamelModel


class StrictArguments(CamelModel):
    """No unexpected fields. A hallucinated argument is a rejected call.

    `extra="forbid"` is the point: a model that invents `force=true` or
    `skip_review=true` must fail loudly rather than have it silently ignored,
    because silently ignoring it teaches nothing and hides the attempt.

    Built on `CamelModel` so a tool argument is named the way every other
    field in this API is named — `taskId`, not `task_id`. Two naming
    conventions in one product is a paper cut for a person and a source of
    invented field names for a model. `populate_by_name` means the Python
    spelling still works, so a caller cannot be wrong about which to use.
    """

    model_config = ConfigDict(
        **CamelModel.model_config, extra="forbid", str_strip_whitespace=True,
    )


class NoArguments(StrictArguments):
    pass


class TaskIdArgument(StrictArguments):
    task_id: UUID


class DocumentIdArgument(StrictArguments):
    document_id: UUID


class GetTasksArguments(StrictArguments):
    status: Optional[Literal[
        "backlog", "todo", "in_progress", "under_review",
        "rework_required", "blocked", "done", "cancelled",
    ]] = None
    assignee_id: Optional[UUID] = None
    limit: int = Field(default=50, ge=1, le=200)


class SearchDocumentsArguments(StrictArguments):
    query: str = Field(min_length=2, max_length=500)
    document_type: Optional[str] = Field(default=None, max_length=40)
    limit: int = Field(default=20, ge=1, le=100)


class GetSiteReportsArguments(StrictArguments):
    limit: int = Field(default=10, ge=1, le=50)


class QueryKnowledgeArguments(StrictArguments):
    question: str = Field(min_length=3, max_length=2000)
    language: Optional[Literal["en", "ar"]] = None


class QueryIFCArguments(StrictArguments):
    question: str = Field(min_length=3, max_length=2000)


class AnalyzeIFCArguments(StrictArguments):
    #: Omitted means the active revision, which is what a question about "the
    #: model" means. Naming a superseded one has to be deliberate.
    version_id: Optional[UUID] = None


class CreateTaskArguments(StrictArguments):
    name: str = Field(min_length=3, max_length=250)
    description: Optional[str] = Field(default=None, max_length=4000)
    assignee_id: Optional[UUID] = None
    priority: Optional[Literal["low", "medium", "high", "critical"]] = None
    due_date: Optional[str] = Field(default=None, max_length=40)


class UpdateTaskArguments(StrictArguments):
    task_id: UUID
    progress_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[Literal[
        "backlog", "todo", "in_progress", "under_review",
        "rework_required", "blocked", "done", "cancelled",
    ]] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class CreateIssueArguments(StrictArguments):
    title: str = Field(min_length=3, max_length=250)
    description: str = Field(min_length=3, max_length=4000)
    severity: Optional[Literal["low", "medium", "high", "critical"]] = None
    task_id: Optional[UUID] = None


class UpdateIssueArguments(StrictArguments):
    issue_id: UUID
    status: Optional[Literal["open", "in_progress", "resolved", "closed"]] = None
    assignee_id: Optional[UUID] = None


class SendMessageArguments(StrictArguments):
    recipient_id: UUID
    body: str = Field(min_length=1, max_length=4000)
    task_id: Optional[UUID] = None


class SiteReportIdArgument(StrictArguments):
    report_id: UUID


class GetDesignChangesArguments(StrictArguments):
    status: Optional[Literal["proposed", "approved", "rejected", "implemented"]] = None
    limit: int = Field(default=30, ge=1, le=100)


class GetFindingsArguments(StrictArguments):
    """Reading existing findings — including other agents' output."""

    severity: Optional[Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]] = None
    status: Optional[Literal["NEW", "OPEN", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]] = None
    #: Restrict to one producing engine, e.g. another agent's findings.
    source_engine: Optional[str] = Field(default=None, max_length=80)
    limit: int = Field(default=50, ge=1, le=200)
