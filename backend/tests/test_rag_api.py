"""The RAG HTTP surface, with authorization as the main subject.

Driven through `TestClient` rather than by calling handlers, because the
properties that matter live in the dependency and permission layers — calling a
handler directly bypasses `Depends(get_current_user)` and would make an
unprotected route look protected.

The central claim under test: **RAG cannot be used to read a document the
caller could not download.** Answering questions out of a document's text is a
read of that text, so a route that checked only project access would hand an
Owner the contents of a draft they are forbidden to fetch — quoted back with
page numbers, unlogged, and looking like a feature. Several tests below exist
purely to keep that door shut.

OpenAI is stubbed throughout; no test makes a network call or needs a key.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentType, EngineerDiscipline, ProjectStatus, TaskStatus, UserRole, UserStatus,
)
from app.models.project import Project, ProjectMember
from app.models.rbac import ProjectParty
from app.models.task import Task
from app.models.user import User, EngineerProfile
from app.services.rag import ingestion
from app.services.rag.answering import NOT_FOUND_MESSAGE, NOT_FOUND_TOKEN
from tests.embedding_stub import STUB_MODEL, StubEmbeddingClient
from tests.pdf_fixture import build_pdf

pytest.importorskip("pypdf", reason="pypdf is required for the RAG pipeline")

PASSWORD = "Correct#12345"

PAGE_ONE = "Concrete curing shall continue for seven days after placement."
PAGE_TWO = "Retention is five per cent of each interim payment certificate."
PAGE_THREE = "Every worker on site shall wear a safety helmet at all times."


# --- stubs ------------------------------------------------------------------


# The embedding stub lives in `tests/embedding_stub.py`. It has to produce
# vectors the width of the `embedding` column — `vector(N)` rejects anything
# else — and one shared definition is one place to keep that agreement.
_StubEmbeddingClient = StubEmbeddingClient


class _FailingEmbeddingClient:
    def __init__(self):
        self.embeddings = self

    def create(self, model, input):  # noqa: A002
        raise RuntimeError("provider unavailable")


def _stub_answer_client(reply: str):
    message = type("M", (), {"content": reply})()
    choice = type("C", (), {"message": message})()
    completion = type("Completion", (), {"choices": [choice]})()

    class _Client:
        def __init__(self):
            self.chat = self
            self.completions = self

        def create(self, model, messages, temperature=None):
            return completion

    return _Client()


@pytest.fixture(autouse=True)
def stub_openai(monkeypatch):
    """Every RAG route gets stubbed OpenAI clients and an enabled feature flag."""
    from app.services.rag import embeddings as embeddings_module
    from app.services.rag import answering as answering_module

    monkeypatch.setattr(settings, "RAG_ENABLED", True)

    original_embedding_init = embeddings_module.EmbeddingService.__init__

    def embedding_init(self, client=None, model=None):
        original_embedding_init(self, client=client or _StubEmbeddingClient(), model=model or STUB_MODEL)

    original_answer_init = answering_module.AnswerService.__init__

    def answer_init(self, client=None, model=None):
        original_answer_init(
            self,
            client=client or _stub_answer_client("Retention is five per cent [1]."),
            model=model or "stub",
        )

    monkeypatch.setattr(embeddings_module.EmbeddingService, "__init__", embedding_init)
    monkeypatch.setattr(answering_module.AnswerService, "__init__", answer_init)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def world(db, tmp_path):
    """Two projects, several roles, and one real PDF on disk.

    Deliberately rich: the authorization tests need an Owner, a consultant
    engineer with a discipline, an outsider, and a second project — none of
    which can be faked convincingly with less.
    """
    suffix = uuid.uuid4().hex[:8]
    created: dict = {}

    def user(name, role, discipline=None):
        person = User(
            full_name=f"{name}{suffix}",
            email=f"{name.lower()}.{suffix}@constro.io",
            hashed_password=hash_password(PASSWORD),
            role=role,
            status=UserStatus.ACTIVE,
            engineer_affiliation="external_consultant" if discipline else None,
        )
        db.add(person)
        db.flush()
        if discipline:
            db.add(EngineerProfile(user_id=person.id, discipline=discipline))
            db.flush()
        return person

    manager = user("Manager", UserRole.PROJECT_MANAGER)
    owner = user("Owner", UserRole.OWNER)
    outsider = user("Outsider", UserRole.PROJECT_MANAGER)
    consultant = user("Consult", UserRole.ENGINEER, EngineerDiscipline.ELECTRICAL)

    def project(name, manager_user):
        item = Project(
            name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
            owner_id=owner.id, project_manager_id=manager_user.id,
        )
        db.add(item)
        db.flush()
        return item

    project_a = project("Alpha", manager)
    project_b = project("Beta", outsider)
    db.add(ProjectMember(
        project_id=project_a.id, user_id=consultant.id,
        role_on_project=UserRole.ENGINEER, is_active=True,
    ))
    # The client, recorded as the external party they are. Without this the
    # owner is an external participant with no party, which `document_access`
    # correctly refuses everything to — a different refusal than the client
    # rule this suite is about. Under the redesign a client *is* a
    # `ProjectParty(kind="CLIENT")`, and the client document scope (official
    # files plus evidence of approved completed work) hangs off that record.
    client_party = ProjectParty(
        project_id=project_a.id, kind="CLIENT", display_name=f"Client {suffix}",
    )
    db.add(client_party)
    db.flush()
    db.add(ProjectMember(
        project_id=project_a.id, user_id=owner.id,
        role_on_project=UserRole.OWNER, is_active=True, party_id=client_party.id,
    ))
    db.flush()

    # A civil (not electrical) task, so a document attached to it is outside
    # the electrical consultant's discipline. This platform's disciplines are
    # ARCHITECTURAL / CIVIL / ELECTRICAL / MECHANICAL — there is no structural.
    structural_task = Task(
        project_id=project_a.id, name=f"Civil work {suffix}",
        discipline=EngineerDiscipline.CIVIL.value, status=TaskStatus.IN_PROGRESS,
        created_by_id=manager.id,
        # Both NOT NULL with no default; normally set by the tasks API, which
        # this fixture bypasses to build the permission scenario directly.
        task_code=f"CV-{suffix[:6].upper()}",
    )
    db.add(structural_task)
    db.flush()

    pdf_path = build_pdf(tmp_path / f"contract_{suffix}.pdf", [PAGE_ONE, PAGE_TWO, PAGE_THREE])

    def document(project_item, title, doc_type=DocumentType.CONTRACT, task=None, path=pdf_path):
        doc = Document(
            project_id=project_item.id,
            task_id=task.id if task else None,
            uploaded_by_id=manager.id,
            title=title,
            document_type=doc_type,
            file_url=f"http://localhost:8000/uploads/{path.name}",
            mime_type="application/pdf",
        )
        db.add(doc)
        db.flush()
        return doc

    created.update(
        manager=manager, owner=owner, outsider=outsider, consultant=consultant,
        project_a=project_a, project_b=project_b,
        pdf_path=pdf_path, upload_dir=str(tmp_path),
        doc_a=document(project_a, "Alpha Contract"),
        doc_b=document(project_b, "Beta Contract"),
        # A report on a civil task: invisible to an electrical consultant,
        # and to an Owner (not a contract/permit, task not approved).
        doc_structural=document(
            project_a, "Civil Report", DocumentType.REPORT, structural_task
        ),
    )
    db.commit()

    try:
        yield created
    finally:
        ids = [created[key].id for key in ("doc_a", "doc_b", "doc_structural")]
        db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(Document).filter(Document.id.in_(ids)).delete(synchronize_session=False)
        db.query(Task).filter(Task.id == structural_task.id).delete(synchronize_session=False)
        db.query(ProjectMember).filter(
            ProjectMember.project_id == project_a.id
        ).delete(synchronize_session=False)
        # After the memberships that reference it, before the project it hangs
        # off: the party is the middle of that chain.
        db.query(ProjectParty).filter(
            ProjectParty.project_id.in_([project_a.id, project_b.id])
        ).delete(synchronize_session=False)
        db.query(Project).filter(
            Project.id.in_([project_a.id, project_b.id])
        ).delete(synchronize_session=False)
        db.query(EngineerProfile).filter(
            EngineerProfile.user_id == consultant.id
        ).delete(synchronize_session=False)
        db.query(User).filter(
            User.id.in_([manager.id, owner.id, outsider.id, consultant.id])
        ).delete(synchronize_session=False)
        db.commit()


@pytest.fixture(autouse=True)
def upload_dir(monkeypatch, world):
    """Point the extractor at the temp directory holding the fixture PDF."""
    monkeypatch.setattr("app.services.rag.pdf_text.settings.UPLOAD_DIR", world["upload_dir"])


def _auth(client, user) -> dict:
    login = client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _index(client, headers, document_id, **params):
    return client.post(f"/api/v1/rag/documents/{document_id}/index", headers=headers, params=params)


# --- feature flag and authentication ----------------------------------------


def test_every_rag_route_refuses_an_anonymous_caller(client, world):
    # Every route on the router, including the two that index files from the
    # unified ingestion pipeline. A new RAG route reaching production without
    # authentication is the failure this enumerates against.
    for method, path, body in (
        ("post", f"/api/v1/rag/documents/{world['doc_a'].id}/index", None),
        ("get", f"/api/v1/rag/documents/{world['doc_a'].id}/status", None),
        ("post", f"/api/v1/rag/files/{uuid.uuid4()}/index", None),
        ("get", f"/api/v1/rag/files/{uuid.uuid4()}/status", None),
        ("post", "/api/v1/rag/query", {"projectId": str(world["project_a"].id), "query": "hello"}),
    ):
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} → {response.status_code}"


def test_rag_routes_report_unavailable_when_disabled(client, world, monkeypatch):
    """The flag must not break the app — it makes RAG say so, cleanly."""
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    headers = _auth(client, world["manager"])
    response = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={"projectId": str(world["project_a"].id), "query": "retention?"},
    )
    assert response.status_code == 503
    assert "not enabled" in response.json()["detail"]


# --- document and project authorization -------------------------------------


def test_a_user_outside_the_project_cannot_index_its_documents(client, world):
    response = _index(client, _auth(client, world["outsider"]), world["doc_a"].id)
    assert response.status_code == 403


def test_a_user_outside_the_project_cannot_query_it(client, world):
    response = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["outsider"]),
        json={"projectId": str(world["project_a"].id), "query": "retention?"},
    )
    assert response.status_code == 403


def test_a_document_from_another_project_is_refused(client, db, world):
    """Naming a document directly must not bypass the project filter."""
    _index(client, _auth(client, world["manager"]), world["doc_a"].id)
    response = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["manager"]),
        json={
            "projectId": str(world["project_a"].id),
            "query": "retention?",
            "documentId": str(world["doc_b"].id),
        },
    )
    # 403 (cannot read project B's document) or 400 (mismatch) — either way,
    # never 200 with project B's content.
    assert response.status_code in (400, 403)


def test_an_owner_cannot_index_a_document_they_may_not_download(client, world):
    """The exact escalation this shared permission layer exists to prevent.

    A report on an unapproved task is outside `owner_document_scope`. If RAG
    checked only project access, the Owner would get its text back with page
    citations.
    """
    response = _index(client, _auth(client, world["owner"]), world["doc_structural"].id)
    assert response.status_code == 403
    assert "finalized and approved" in response.json()["detail"]


def test_a_consultant_cannot_index_a_document_outside_their_discipline(client, world):
    """An electrical consultant, a civil task's report."""
    response = _index(client, _auth(client, world["consultant"]), world["doc_structural"].id)
    assert response.status_code == 403
    assert "discipline" in response.json()["detail"]


def test_project_wide_query_only_searches_documents_the_caller_may_read(client, db, world):
    """Retrieval is filtered by the same rules, not just single-document checks.

    Both documents in project A are indexed. The Owner asks a project-wide
    question whose best match lives in the document they may not read; the
    answer must not cite it.
    """
    manager_headers = _auth(client, world["manager"])
    assert _index(client, manager_headers, world["doc_a"].id).status_code == 202
    assert _index(client, manager_headers, world["doc_structural"].id).status_code == 202

    response = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["owner"]),
        json={"projectId": str(world["project_a"].id), "query": "retention percentage"},
    )
    assert response.status_code == 200
    cited = {citation["documentId"] for citation in response.json()["citations"]}
    assert str(world["doc_structural"].id) not in cited


def test_an_unknown_document_is_a_404(client, world):
    response = _index(client, _auth(client, world["manager"]), uuid.uuid4())
    assert response.status_code == 404


# --- indexing ---------------------------------------------------------------


def test_indexing_a_pdf_produces_page_aware_chunks(client, db, world):
    headers = _auth(client, world["manager"])
    response = _index(client, headers, world["doc_a"].id)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "READY"
    assert body["pageCount"] == 3
    assert body["chunkCount"] >= 3
    assert body["indexedAt"] is not None

    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["doc_a"].id
    ).order_by(DocumentChunk.chunk_index).all()
    assert {chunk.page_number for chunk in chunks} == {1, 2, 3}
    assert all(chunk.project_id == world["project_a"].id for chunk in chunks)
    retention = next(c for c in chunks if "Retention" in c.content)
    assert retention.page_number == 2, "the retention clause must cite page 2"


def test_reindexing_leaves_no_duplicate_chunks(client, db, world):
    """Idempotence: the same document indexed twice yields one set of chunks."""
    headers = _auth(client, world["manager"])
    first = _index(client, headers, world["doc_a"].id).json()
    second = _index(client, headers, world["doc_a"].id).json()

    assert first["chunkCount"] == second["chunkCount"]
    stored = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == world["doc_a"].id
    ).count()
    assert stored == second["chunkCount"]

    indexes = [
        row[0] for row in db.query(DocumentChunk.chunk_index)
        .filter(DocumentChunk.document_id == world["doc_a"].id).all()
    ]
    assert len(indexes) == len(set(indexes)), "duplicate chunk_index values"


def test_a_missing_file_fails_cleanly_without_looking_indexed(client, db, world):
    """Constraint: a failed run must never leave the document appearing READY."""
    world["doc_a"].file_url = "http://localhost:8000/uploads/does-not-exist.pdf"
    db.commit()

    response = _index(client, _auth(client, world["manager"]), world["doc_a"].id)
    assert response.status_code == 400

    db.expire_all()
    document = db.query(Document).filter(Document.id == world["doc_a"].id).one()
    assert document.index_status == "FAILED"
    assert document.index_error
    assert document.indexed_at is None
    assert ingestion.chunk_count(db, document.id) == 0


def test_an_embedding_failure_leaves_no_partial_index(client, db, world, monkeypatch):
    """The provider dies mid-run: status FAILED, zero chunks, query refused."""
    from app.services.rag import embeddings as embeddings_module

    def failing_init(self, client=None, model=None):
        self._client = _FailingEmbeddingClient()
        self._model = "stub"

    monkeypatch.setattr(embeddings_module.EmbeddingService, "__init__", failing_init)

    headers = _auth(client, world["manager"])
    response = _index(client, headers, world["doc_a"].id)
    assert response.status_code == 400

    db.expire_all()
    document = db.query(Document).filter(Document.id == world["doc_a"].id).one()
    assert document.index_status == "FAILED"
    assert ingestion.chunk_count(db, document.id) == 0

    query = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={
            "projectId": str(world["project_a"].id),
            "query": "retention?",
            "documentId": str(world["doc_a"].id),
        },
    )
    assert query.status_code == 409, "a failed index must not be queryable"


def test_a_non_pdf_document_is_refused(client, db, world, tmp_path):
    fake = Path(world["upload_dir"]) / "fake.pdf"
    fake.write_bytes(b"PK\x03\x04 not a pdf at all")
    world["doc_a"].file_url = "http://localhost:8000/uploads/fake.pdf"
    db.commit()

    response = _index(client, _auth(client, world["manager"]), world["doc_a"].id)
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


# --- status -----------------------------------------------------------------


def test_status_reports_not_indexed_before_any_run(client, world):
    response = client.get(
        f"/api/v1/rag/documents/{world['doc_a'].id}/status",
        headers=_auth(client, world["manager"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_INDEXED"
    assert body["chunkCount"] == 0
    assert body["error"] is None


def test_status_reports_the_failure_reason(client, db, world):
    world["doc_a"].file_url = "http://localhost:8000/uploads/missing.pdf"
    db.commit()
    headers = _auth(client, world["manager"])
    _index(client, headers, world["doc_a"].id)

    body = client.get(
        f"/api/v1/rag/documents/{world['doc_a'].id}/status", headers=headers
    ).json()
    assert body["status"] == "FAILED"
    assert body["error"]
    assert body["indexedAt"] is None


def test_status_reports_counts_after_a_successful_run(client, world):
    headers = _auth(client, world["manager"])
    _index(client, headers, world["doc_a"].id)

    body = client.get(
        f"/api/v1/rag/documents/{world['doc_a'].id}/status", headers=headers
    ).json()
    assert body["status"] == "READY"
    assert body["pageCount"] == 3
    assert body["chunkCount"] >= 3
    assert body["error"] is None


# --- query, grounding and citations -----------------------------------------


def test_a_grounded_answer_cites_the_document_and_page(client, world):
    headers = _auth(client, world["manager"])
    _index(client, headers, world["doc_a"].id)

    response = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={
            "projectId": str(world["project_a"].id),
            "query": "what is the retention percentage",
            "documentId": str(world["doc_a"].id),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["found"] is True
    assert body["chunksUsed"] >= 1
    assert body["citations"], "a grounded answer must carry citations"
    top = body["citations"][0]
    assert top["documentId"] == str(world["doc_a"].id)
    assert top["title"] == "Alpha Contract"
    assert top["page"] == 2, "the retention clause is on page 2"
    assert "Retention" in top["snippet"]


def test_the_response_never_contains_an_embedding(client, world):
    """Vectors are internal; the schema has no field that could leak one."""
    headers = _auth(client, world["manager"])
    _index(client, headers, world["doc_a"].id)
    response = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={"projectId": str(world["project_a"].id), "query": "retention?"},
    )
    assert "embedding" not in response.text.lower()


def test_an_unanswerable_question_says_so_rather_than_inventing(client, world, monkeypatch):
    from app.services.rag import answering as answering_module

    def refusing_init(self, client=None, model=None):
        self._client = _stub_answer_client(NOT_FOUND_TOKEN)
        self._model = "stub"

    headers = _auth(client, world["manager"])
    _index(client, headers, world["doc_a"].id)
    monkeypatch.setattr(answering_module.AnswerService, "__init__", refusing_init)

    body = client.post(
        "/api/v1/rag/query",
        headers=headers,
        json={
            "projectId": str(world["project_a"].id),
            "query": "what is the site manager's shoe size",
            "documentId": str(world["doc_a"].id),
        },
    ).json()

    assert body["found"] is False
    assert body["answer"] == NOT_FOUND_MESSAGE
    assert body["citations"] == []


def test_querying_a_project_with_nothing_indexed_reports_not_found(client, world):
    """No index, no context — and therefore no invented answer."""
    body = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["manager"]),
        json={"projectId": str(world["project_a"].id), "query": "retention?"},
    ).json()
    assert body["found"] is False
    assert body["chunksUsed"] == 0
    assert body["citations"] == []


def test_querying_an_unindexed_document_directly_is_a_conflict(client, world):
    response = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["manager"]),
        json={
            "projectId": str(world["project_a"].id),
            "query": "retention?",
            "documentId": str(world["doc_a"].id),
        },
    )
    assert response.status_code == 409


def test_a_too_short_query_is_rejected_by_validation(client, world):
    response = client.post(
        "/api/v1/rag/query",
        headers=_auth(client, world["manager"]),
        json={"projectId": str(world["project_a"].id), "query": "a"},
    )
    assert response.status_code == 422
