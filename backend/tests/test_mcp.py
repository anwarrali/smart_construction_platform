"""The MCP surface: the protocol, and what it may reach.

MCP is the first way the tool layer becomes reachable from outside this
application, so the assertions that matter most are the ones about what it
does **not** expose:

* a tool the caller may not use is not listed, and calling it anyway is
  refused — by the same runtime the agent layer goes through, not by a second
  check written here;
* a project the caller cannot reach is not reachable, whatever the URL says;
* a PROPOSE tool changes nothing, and says so loudly enough that a model
  cannot report a proposal as a completed action.

The protocol tests are separate from the transport tests on purpose:
`services/mcp/protocol.py` is pure, so JSON-RPC correctness is testable with a
session and a dict, and only the HTTP-specific behaviour needs a client.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.issue import Issue
from app.models.project import Project, ProjectMember
from app.models.task import Task
from app.models.user import User
from app.services import mcp
from app.services.ai_tools.contracts import ToolKind
from app.services.ai_tools.registry import BY_NAME, TOOLS
from app.services.mcp import protocol

PASSWORD = "McpTest!2345"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:  # pragma: no cover - only without a database
        session.close()
        pytest.skip("database is not reachable")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def world(db, monkeypatch):
    """Two projects and three people: a member, an outsider, and a suspended
    account. Flush-only — the `db` fixture's rollback is the whole teardown."""
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    suffix = uuid4().hex[:10]

    def user(name, status=UserStatus.ACTIVE, role=UserRole.PROJECT_MANAGER):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                      hashed_password=hash_password(PASSWORD), role=role, status=status)
        db.add(person)
        db.flush()
        return person

    manager = user("McpPm")
    outsider = user("McpOut")
    suspended = user("McpSusp", status=UserStatus.SUSPENDED)

    def project(name, owner):
        row = Project(name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=owner.id)
        db.add(row)
        db.flush()
        db.add(ProjectMember(project_id=row.id, user_id=owner.id,
                             role_on_project=owner.role, is_active=True))
        return row

    project_a = project("Mcp A", manager)
    project_b = project("Mcp B", outsider)
    db.add(ProjectMember(project_id=project_a.id, user_id=suspended.id,
                         role_on_project=suspended.role, is_active=True))
    db.add(Task(project_id=project_a.id, name="Pour the slab",
                created_by_id=manager.id, task_code=f"T-{suffix[:4]}"))
    db.flush()
    yield {"a": project_a, "b": project_b, "manager": manager,
           "outsider": outsider, "suspended": suspended}


def call(db, world, message, user=None, project=None):
    return protocol.handle(
        db, user=user or world["manager"],
        project_id=(project or world["a"]).id, message=message,
    )


def rpc(method, params=None, request_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    return body


# --- initialize -------------------------------------------------------------

def test_initialize_advertises_tools_and_identifies_the_server(db, world):
    reply = call(db, world, rpc("initialize", {
        "protocolVersion": protocol.PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "probe", "version": "1.0"},
    }))
    result = reply["result"]
    assert reply["jsonrpc"] == "2.0" and reply["id"] == 1
    assert result["protocolVersion"] == protocol.PROTOCOL_VERSION
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["serverInfo"]["name"] == protocol.SERVER_NAME
    assert "instructions" in result


@pytest.mark.parametrize("requested", protocol.SUPPORTED_PROTOCOL_VERSIONS)
def test_a_pinned_client_is_answered_in_its_own_version(db, world, requested):
    """Refusing over a revision difference that does not affect `tools/*`
    would break clients for no benefit."""
    reply = call(db, world, rpc("initialize", {"protocolVersion": requested}))
    assert reply["result"]["protocolVersion"] == requested


def test_an_unknown_version_is_answered_with_ours(db, world):
    reply = call(db, world, rpc("initialize", {"protocolVersion": "1999-01-01"}))
    assert reply["result"]["protocolVersion"] == protocol.PROTOCOL_VERSION


def test_initialize_works_without_client_info(db, world):
    assert call(db, world, rpc("initialize", {}))["result"]["protocolVersion"]


def test_ping_answers_with_an_empty_object(db, world):
    assert call(db, world, rpc("ping"))["result"] == {}


def test_a_notification_produces_no_response(db, world):
    """A JSON-RPC notification must be answered by silence."""
    assert call(db, world, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_a_request_without_an_id_is_treated_as_a_notification(db, world):
    assert call(db, world, {"jsonrpc": "2.0", "method": "ping"}) is None


# --- Protocol errors --------------------------------------------------------

def test_a_wrong_jsonrpc_version_is_refused(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, {"jsonrpc": "1.0", "method": "ping", "id": 1})
    assert error.value.code == protocol.INVALID_REQUEST


def test_a_missing_method_is_refused(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, {"jsonrpc": "2.0", "id": 1})
    assert error.value.code == protocol.INVALID_REQUEST


def test_an_unknown_method_is_method_not_found(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, rpc("resources/list"))
    assert error.value.code == protocol.METHOD_NOT_FOUND


def test_non_object_params_are_refused(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1, 2]})
    assert error.value.code == protocol.INVALID_PARAMS


def test_a_tool_call_without_a_name_is_refused(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, rpc("tools/call", {"arguments": {}}))
    assert error.value.code == protocol.INVALID_PARAMS


def test_non_object_tool_arguments_are_refused(db, world):
    with pytest.raises(protocol.ProtocolError) as error:
        call(db, world, rpc("tools/call", {"name": "get_project", "arguments": "nope"}))
    assert error.value.code == protocol.INVALID_PARAMS


def test_absent_arguments_default_to_empty(db, world):
    """A no-argument tool should be callable without an `arguments` key."""
    reply = call(db, world, rpc("tools/call", {"name": "get_project"}))
    assert reply["result"]["isError"] is False


# --- tools/list -------------------------------------------------------------

def test_the_tool_list_is_in_mcp_shape(db, world):
    tools = call(db, world, rpc("tools/list"))["result"]["tools"]
    assert tools
    for tool in tools:
        assert set(tool) == {"name", "title", "description", "inputSchema", "annotations"}
        assert tool["inputSchema"]["type"] == "object"
        assert set(tool["annotations"]) >= {"readOnlyHint", "destructiveHint"}


def test_the_published_schema_is_the_one_the_runtime_validates_against(db, world):
    """What a client is told and what the server enforces cannot drift,
    because they are the same object."""
    tools = {t["name"]: t for t in call(db, world, rpc("tools/list"))["result"]["tools"]}
    for name, published in tools.items():
        assert published["inputSchema"] == BY_NAME[name].json_schema()


def test_a_read_tool_is_marked_read_only_and_a_proposal_is_not(db, world):
    tools = {t["name"]: t for t in call(db, world, rpc("tools/list"))["result"]["tools"]}
    assert tools["get_project"]["annotations"]["readOnlyHint"] is True
    if "create_task" in tools:
        assert tools["create_task"]["annotations"]["readOnlyHint"] is False


def test_a_proposal_tool_says_it_changes_nothing(db, world):
    """The single most damaging failure this surface could enable is a model
    reporting a proposal as a completed action."""
    for definition in (t.as_definition() for t in TOOLS if t.kind is ToolKind.PROPOSE):
        described = protocol.tool_descriptor(definition)["description"]
        assert "PROPOSAL ONLY" in described
        assert "must confirm" in described
        assert "Never report" in described


def test_no_tool_is_marked_destructive_because_none_writes(db, world):
    for tool in call(db, world, rpc("tools/list"))["result"]["tools"]:
        assert tool["annotations"]["destructiveHint"] is False


# --- Authorization ----------------------------------------------------------

def test_the_list_is_filtered_to_what_this_caller_may_use(db, world, monkeypatch):
    """Listing a tool the caller cannot use would teach a model to attempt
    something that will be refused — and would disclose that the capability
    exists behind a permission they do not hold."""
    import app.services.ai_tools.runtime as runtime

    monkeypatch.setattr(
        runtime, "has_permission",
        lambda db, user, code, project_id=None: code != "ifc.view",
    )
    names = {t["name"] for t in call(db, world, rpc("tools/list"))["result"]["tools"]}
    assert "query_ifc" not in names
    assert "analyze_ifc" not in names
    assert "get_project" in names


def test_a_tool_the_caller_may_not_use_is_refused_when_called_anyway(db, world, monkeypatch):
    """Filtering the list is a courtesy. This is the boundary."""
    import app.services.ai_tools.runtime as runtime

    monkeypatch.setattr(
        runtime, "has_permission",
        lambda db, user, code, project_id=None: code != "ifc.view",
    )
    reply = call(db, world, rpc("tools/call", {"name": "query_ifc",
                                               "arguments": {"question": "what is this"}}))
    result = reply["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["errorCode"] == "FORBIDDEN"


def test_an_outsider_lists_no_tools_for_a_project_they_cannot_reach(db, world):
    tools = call(db, world, rpc("tools/list"), user=world["outsider"])["result"]["tools"]
    assert tools == []


def test_an_outsider_calling_a_tool_is_refused(db, world):
    reply = call(db, world, rpc("tools/call", {"name": "get_project"}),
                 user=world["outsider"])
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "FORBIDDEN"


def test_a_suspended_account_is_refused_even_as_a_project_member(db, world):
    """Membership is not enough; the account must be active."""
    reply = call(db, world, rpc("tools/call", {"name": "get_project"}),
                 user=world["suspended"])
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "FORBIDDEN"


def test_a_caller_cannot_reach_another_project_through_the_protocol(db, world):
    """Project isolation at the data boundary: the manager of A gets nothing
    for B, even though the message itself is identical."""
    reply = call(db, world, rpc("tools/call", {"name": "get_project"}),
                 user=world["manager"], project=world["b"])
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "FORBIDDEN"


def test_the_protocol_adds_no_authorization_of_its_own(db, world, monkeypatch):
    """Every listed tool comes from `available_tools`, so there is exactly one
    place the decision is made."""
    called = {}
    import app.services.ai_tools as tools_module

    original = tools_module.available_tools

    def spy(db, *, user, project_id):
        called["args"] = (user.id, project_id)
        return original(db, user=user, project_id=project_id)

    monkeypatch.setattr(protocol.ai_tools, "available_tools", spy)
    call(db, world, rpc("tools/list"))
    assert called["args"] == (world["manager"].id, world["a"].id)


# --- Results ----------------------------------------------------------------

def test_a_successful_call_returns_content_and_structured_content(db, world):
    result = call(db, world, rpc("tools/call", {"name": "get_project"}))["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    # The text block is the same payload, so a client that reads only content
    # loses nothing.
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert result["structuredContent"]["ok"] is True
    assert result["structuredContent"]["data"]["name"].startswith("Mcp A")


def test_an_unknown_tool_is_a_result_not_a_protocol_error(db, world):
    """"There is no such tool" is the platform answering, not the client
    being malformed."""
    reply = call(db, world, rpc("tools/call", {"name": "delete_everything"}))
    assert "error" not in reply
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "UNKNOWN_TOOL"


def test_bad_arguments_come_back_as_a_tool_error(db, world):
    reply = call(db, world, rpc("tools/call", {
        "name": "get_task", "arguments": {"task_id": "not-a-uuid"}}))
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "INVALID_ARGUMENTS"


def test_a_read_tool_returns_data_scoped_to_the_project(db, world):
    result = call(db, world, rpc("tools/call", {"name": "get_tasks"}))["result"]
    assert result["isError"] is False
    names = [t["name"] for t in result["structuredContent"]["data"]["tasks"]]
    assert "Pour the slab" in names


# --- Proposals change nothing ----------------------------------------------

def test_a_proposal_persists_nothing(db, world):
    """The guarantee that makes exposing PROPOSE tools safe at all."""
    before_tasks = db.query(Task).filter(Task.project_id == world["a"].id).count()
    before_issues = db.query(Issue).filter(Issue.project_id == world["a"].id).count()

    reply = call(db, world, rpc("tools/call", {
        "name": "create_task",
        "arguments": {"title": "Proposed by a model", "description": "x"},
    }))
    db.flush()
    assert db.query(Task).filter(Task.project_id == world["a"].id).count() == before_tasks
    assert db.query(Issue).filter(Issue.project_id == world["a"].id).count() == before_issues

    payload = reply["result"]["structuredContent"]
    if payload["ok"]:
        assert payload["requiresConfirmation"] is True
        assert "not been performed" in payload["proposal"]["confirmation"]


# --- Transport --------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def auth(client, user) -> dict:
    login = client.post("/api/v1/auth/login",
                        data={"username": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture()
def committed(db, world):
    """The HTTP tests need rows a second connection can see."""
    db.commit()
    try:
        yield world
    finally:
        db.rollback()
        users = [world["manager"].id, world["outsider"].id, world["suspended"].id]
        params = {"projects": [world["a"].id, world["b"].id], "users": users,
                  # `tools/call` is charged against the caller since MCP gained
                  # a rate limit, so these tests now leave counter rows behind
                  # as well as content rows.
                  "keys": [f"user:{user_id}" for user_id in users]}
        for statement in (
            "DELETE FROM rate_limit_hits WHERE key = ANY(:keys)",
            "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
            "DELETE FROM tasks WHERE project_id = ANY(:projects)",
            "DELETE FROM project_members WHERE project_id = ANY(:projects)",
            "DELETE FROM projects WHERE id = ANY(:projects)",
            "DELETE FROM revoked_tokens WHERE 1=0",
            "DELETE FROM users WHERE id = ANY(:users)",
        ):
            try:
                db.execute(text(statement), params)
            except SQLAlchemyError:
                db.rollback()
        db.commit()


def url(project) -> str:
    return f"/api/v1/mcp/projects/{project.id}"


def test_the_endpoint_speaks_json_rpc_over_post(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers,
                           json=rpc("initialize", {"protocolVersion": protocol.PROTOCOL_VERSION}))
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == protocol.SERVER_NAME
    assert response.headers["MCP-Protocol-Version"] == protocol.PROTOCOL_VERSION


def test_the_negotiated_version_header_is_echoed(client, committed):
    headers = auth(client, committed["manager"])
    headers["MCP-Protocol-Version"] = "2024-11-05"
    response = client.post(url(committed["a"]), headers=headers, json=rpc("ping"))
    assert response.headers["MCP-Protocol-Version"] == "2024-11-05"


def test_an_anonymous_caller_is_refused(client, committed):
    response = client.post(url(committed["a"]), json=rpc("ping"))
    assert response.status_code == 401


def test_a_caller_without_project_access_is_refused_at_the_transport(client, committed):
    headers = auth(client, committed["outsider"])
    response = client.post(url(committed["a"]), headers=headers, json=rpc("tools/list"))
    assert response.status_code == 403


def test_the_surface_reports_unavailable_when_disabled(client, committed, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers, json=rpc("ping"))
    assert response.status_code == 503
    assert "not enabled" in response.json()["detail"]


def test_the_optional_get_stream_says_it_is_not_offered(client, committed):
    headers = auth(client, committed["manager"])
    response = client.get(url(committed["a"]), headers=headers)
    assert response.status_code == 405
    assert "POST" in response.json()["detail"]


def test_malformed_json_is_a_parse_error(client, committed):
    headers = auth(client, committed["manager"])
    headers["Content-Type"] = "application/json"
    response = client.post(url(committed["a"]), headers=headers, content=b"{not json")
    assert response.status_code == 200
    assert response.json()["error"]["code"] == protocol.PARSE_ERROR


def test_an_empty_body_is_refused(client, committed):
    headers = auth(client, committed["manager"])
    headers["Content-Type"] = "application/json"
    response = client.post(url(committed["a"]), headers=headers, content=b"")
    assert response.json()["error"]["code"] == protocol.INVALID_REQUEST


def test_an_oversized_body_is_refused_before_parsing(client, committed):
    headers = auth(client, committed["manager"])
    headers["Content-Type"] = "application/json"
    response = client.post(url(committed["a"]), headers=headers,
                           content=b"[" + b"0," * 200_000 + b"0]")
    assert response.status_code == 413


def test_a_batch_returns_one_reply_per_request(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers, json=[
        rpc("ping", request_id=1),
        rpc("tools/list", request_id=2),
    ])
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [1, 2]


def test_a_batch_of_only_notifications_is_accepted_with_no_body(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers, json=[
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ])
    assert response.status_code == 202
    assert not response.content


def test_an_empty_batch_is_refused(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers, json=[])
    assert response.json()["error"]["code"] == protocol.INVALID_REQUEST


def test_a_single_notification_is_accepted_with_no_body(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers,
                           json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert response.status_code == 202


def test_a_non_object_message_is_refused(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(url(committed["a"]), headers=headers, json="hello")
    assert response.json()["error"]["code"] == protocol.INVALID_REQUEST


def test_an_unknown_project_is_refused_rather_than_answered(client, committed):
    headers = auth(client, committed["manager"])
    response = client.post(f"/api/v1/mcp/projects/{uuid4()}", headers=headers,
                           json=rpc("tools/list"))
    assert response.status_code == 403


# --- Audit ------------------------------------------------------------------

def test_a_proposal_is_recorded_in_the_audit_trail(client, committed):
    headers = auth(client, committed["manager"])
    client.post(url(committed["a"]), headers=headers, json=rpc("tools/call", {
        "name": "create_task",
        "arguments": {"title": "Audited proposal", "description": "x"},
    }))

    session = SessionLocal()
    try:
        entries = session.query(AuditLog).filter(
            AuditLog.project_id == committed["a"].id,
            AuditLog.action == "mcp_tool_proposed",
        ).all()
        assert entries
        # `AuditLog.details` is a JSON-serialised Text column, not JSONB.
        details = json.loads(entries[0].details)
        assert details["tool"] == "create_task"
        # The arguments are project content and are deliberately absent — a
        # proposal's text must not end up in a table people read casually.
        assert "arguments" not in details
        assert "Audited proposal" not in entries[0].details
    finally:
        session.close()


def test_a_read_is_not_written_to_the_audit_trail(client, committed):
    """Thousands of reads a day would drown the entries that matter."""
    headers = auth(client, committed["manager"])
    client.post(url(committed["a"]), headers=headers,
                json=rpc("tools/call", {"name": "get_project"}))

    session = SessionLocal()
    try:
        assert session.query(AuditLog).filter(
            AuditLog.project_id == committed["a"].id,
            AuditLog.action == "mcp_tool_proposed",
        ).count() == 0
    finally:
        session.close()


# --- The module contract ----------------------------------------------------

def test_every_registered_tool_can_be_described(db, world):
    """A tool added to the table must not break the MCP listing."""
    for tool in TOOLS:
        descriptor = protocol.tool_descriptor(tool.as_definition())
        assert descriptor["name"] == tool.name
        assert descriptor["description"]
        assert descriptor["inputSchema"]["type"] == "object"


def test_the_protocol_module_exposes_no_write_path():
    """It maps and dispatches; it never reaches a model or a service directly."""
    source = (protocol.__file__ or "")
    assert source
    with open(source, encoding="utf-8") as handle:
        text_body = handle.read()
    for forbidden in ("db.commit(", "db.add(", "db.delete(", "OPENAI_API_KEY"):
        assert forbidden not in text_body, f"protocol.py should not contain {forbidden!r}"
