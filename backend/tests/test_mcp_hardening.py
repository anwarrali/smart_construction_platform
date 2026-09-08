"""What it takes to expose the MCP surface to something that is not trusted.

The surface itself was already careful about *authorization* — a tool the
caller may not use is not listed and is refused if called. Two things it was
not careful about, and this file is about both:

* **the credential.** A session token lives for minutes, so a desktop client
  either re-authenticates hourly or is handed a refresh token, which is the
  account. A client token is the third option: one project, one scope set, a
  fixed life, revocable in one UPDATE. The assertions that matter are the
  negative ones — that it cannot reach another project, cannot reach another
  route, cannot mint its replacement, and stops working the instant its owner
  is suspended or it is revoked.

* **the rate.** A client could call tools as fast as the API would answer.
  Charging is per credential and per *call*, not per request, because the
  transport accepts batches and counting requests would leave one POST able to
  carry hundreds of calls through the limit.

Every test here uses committed rows. `credentials._touch` commits, so the
flush-and-rollback fixture the older MCP tests use would leak the world into
the shared development database — the teardown below deletes explicitly
instead.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.enums import ProjectStatus, UserRole, UserStatus
from app.models.mcp_token import (
    SCOPE_PROPOSE, SCOPE_READ, TOKEN_PREFIX, McpClientToken,
)
from app.models.project import Project, ProjectMember
from app.models.rate_limit import RateLimitHit
from app.models.user import User
from app.services import rate_limit_service
from app.services.ai_tools.registry import TOOLS
from app.services.mcp import credentials, limits, protocol
from app.services.mcp import tokens as token_service
from app.services.mcp.credentials import Credential, CredentialError
from app.services.mcp.tokens import TokenError

PASSWORD = "McpHard!2345"


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
    """Two projects, four people, committed — and deleted again afterwards.

    Committed rather than flushed because half of this file goes through HTTP
    (a second connection) and the other half through `from_client_token`,
    which commits `last_used_at` on its own.
    """
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    suffix = uuid4().hex[:10]

    def user(name, status=UserStatus.ACTIVE, role=UserRole.PROJECT_MANAGER):
        person = User(full_name=name, email=f"{name.lower()}-{suffix}@example.com",
                      hashed_password=hash_password(PASSWORD), role=role, status=status)
        db.add(person)
        db.flush()
        return person

    manager = user("HardPm")
    outsider = user("HardOut")
    admin = user("HardAdmin", role=UserRole.ADMIN)

    def project(name, owner):
        row = Project(name=f"{name} {suffix}", status=ProjectStatus.ACTIVE,
                      owner_id=owner.id, project_manager_id=owner.id)
        db.add(row)
        db.flush()
        db.add(ProjectMember(project_id=row.id, user_id=owner.id,
                             role_on_project=owner.role, is_active=True))
        return row

    project_a = project("Hard A", manager)
    project_b = project("Hard B", manager)
    project_c = project("Hard C", outsider)
    db.commit()

    state = {"a": project_a, "b": project_b, "c": project_c, "manager": manager,
             "outsider": outsider, "admin": admin, "suffix": suffix}
    try:
        yield state
    finally:
        db.rollback()
        params = {
            "projects": [project_a.id, project_b.id, project_c.id],
            "users": [manager.id, outsider.id, admin.id],
            "keys": [f"user:{manager.id}", f"user:{outsider.id}", f"user:{admin.id}"],
        }
        for statement in (
            "DELETE FROM rate_limit_hits WHERE key = ANY(:keys)"
            " OR key IN (SELECT 'token:' || id::text FROM mcp_client_tokens"
            "            WHERE user_id = ANY(:users))",
            "DELETE FROM mcp_client_tokens WHERE user_id = ANY(:users)"
            " OR project_id = ANY(:projects)",
            "DELETE FROM audit_logs WHERE project_id = ANY(:projects) OR actor_id = ANY(:users)",
            "DELETE FROM project_members WHERE project_id = ANY(:projects)",
            "DELETE FROM projects WHERE id = ANY(:projects)",
            "DELETE FROM users WHERE id = ANY(:users)",
        ):
            try:
                db.execute(text(statement), params)
            except SQLAlchemyError:
                db.rollback()
        db.commit()


def mint(db, world, *, owner=None, project=None, scopes=None, lifetime_days=None):
    row, secret = token_service.issue(
        db, owner=owner or world["manager"], project_id=(project or world["a"]).id,
        name="Test client", scopes=scopes, lifetime_days=lifetime_days,
    )
    db.commit()
    return row, secret


def rpc(method, params=None, request_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        body["id"] = request_id
    if params is not None:
        body["params"] = params
    return body


def propose_tool_name() -> str:
    for tool in TOOLS:
        if tool.requires_confirmation:
            return tool.name
    raise AssertionError("the tool table has no PROPOSE tool to test with")


# --- Issuing ----------------------------------------------------------------

def test_a_token_is_bound_to_one_project_and_expires(db, world):
    row, secret = mint(db, world)
    assert row.project_id == world["a"].id
    assert row.expires_at > datetime.now(timezone.utc)
    assert secret.startswith(TOKEN_PREFIX)


def test_the_secret_is_never_stored(db, world):
    """Only its SHA-256 is kept, so the row cannot reconstruct the credential."""
    row, secret = mint(db, world)
    stored = json.dumps({column.name: str(getattr(row, column.name))
                         for column in row.__table__.columns})
    assert secret not in stored
    assert row.prefix in secret and len(row.prefix) < len(secret)


def test_read_is_granted_even_when_only_propose_is_asked_for(db, world):
    """A token that may propose but not read is a credential for nothing."""
    assert token_service.normalise_scopes([SCOPE_PROPOSE]) == f"{SCOPE_READ} {SCOPE_PROPOSE}"


def test_an_unknown_scope_is_refused_rather_than_dropped(db, world):
    """Silently ignoring it would let a client believe it holds something it
    does not — and the next scope added would be one a stale client thinks it
    already has."""
    with pytest.raises(TokenError) as error:
        token_service.normalise_scopes(["mcp:read", "mcp:admin"])
    assert error.value.status_code == 400
    assert "mcp:admin" in error.value.detail


def test_a_lifetime_beyond_the_cap_is_refused(db, world):
    with pytest.raises(TokenError) as error:
        mint(db, world, lifetime_days=settings.MCP_TOKEN_MAX_LIFETIME_DAYS + 1)
    assert error.value.status_code == 400


def test_a_person_may_not_hold_unbounded_tokens(db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKENS_PER_USER_MAX", 2)
    mint(db, world)
    mint(db, world)
    with pytest.raises(TokenError) as error:
        mint(db, world)
    assert error.value.status_code == 409


def test_a_revoked_token_does_not_count_against_the_cap(db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_TOKENS_PER_USER_MAX", 1)
    row, _ = mint(db, world)
    token_service.revoke(db, row)
    db.commit()
    assert mint(db, world)  # no longer refused


# --- Resolving --------------------------------------------------------------

def test_a_client_token_resolves_to_its_owner_and_project(db, world):
    row, secret = mint(db, world, scopes=[SCOPE_READ, SCOPE_PROPOSE])
    credential = credentials.from_client_token(db, secret)
    assert credential.kind == "token"
    assert credential.user.id == world["manager"].id
    assert credential.project_id == world["a"].id
    assert credential.allows_proposals()


def test_an_unknown_secret_is_refused(db, world):
    with pytest.raises(CredentialError) as error:
        credentials.from_client_token(db, f"{TOKEN_PREFIX}nonsense")
    assert error.value.status_code == 401


def test_a_revoked_token_stops_working_immediately(db, world):
    row, secret = mint(db, world)
    token_service.revoke(db, row)
    db.commit()
    with pytest.raises(CredentialError) as error:
        credentials.from_client_token(db, secret)
    assert error.value.status_code == 401
    assert "revoked" in error.value.detail


def test_an_expired_token_is_refused_and_says_so(db, world):
    """Distinct from 'not recognised' on purpose: a client that cannot tell the
    two apart cannot tell its user what to do about it."""
    row, secret = mint(db, world)
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with pytest.raises(CredentialError) as error:
        credentials.from_client_token(db, secret)
    assert "expired" in error.value.detail


def test_suspending_the_owner_kills_the_token(db, world):
    """The point of resolving authority per call: a month-old credential must
    die with its owner's account, not with its own clock."""
    row, secret = mint(db, world)
    world["manager"].status = UserStatus.SUSPENDED
    db.commit()
    with pytest.raises(CredentialError) as error:
        credentials.from_client_token(db, secret)
    assert error.value.status_code == 403


def test_a_forced_password_change_blocks_the_token(db, world):
    row, secret = mint(db, world)
    world["manager"].must_change_password = True
    db.commit()
    with pytest.raises(CredentialError) as error:
        credentials.from_client_token(db, secret)
    assert error.value.detail == "PASSWORD_CHANGE_REQUIRED"


def test_use_is_recorded_but_not_on_every_request(db, world):
    """`last_used_at` exists so a person can tell a live token from a forgotten
    one; a write per call would put an UPDATE in the path of every tool call."""
    row, secret = mint(db, world)
    credentials.from_client_token(db, secret)
    db.refresh(row)
    first = row.last_used_at
    assert first is not None

    credentials.from_client_token(db, secret)
    db.refresh(row)
    assert row.last_used_at == first

    row.last_used_at = datetime.now(timezone.utc) - timedelta(
        seconds=credentials.TOUCH_INTERVAL_SECONDS + 5)
    db.commit()
    credentials.from_client_token(db, secret)
    db.refresh(row)
    assert row.last_used_at != first


def test_a_session_token_is_not_mistaken_for_a_client_token(db, world):
    assert not credentials.looks_like_client_token("eyJhbGciOiJIUzI1NiJ9.x.y")
    assert credentials.looks_like_client_token(f"{TOKEN_PREFIX}abc")


# --- What a credential may reach -------------------------------------------

def read_only(world, project=None) -> Credential:
    return Credential(user=world["manager"], scopes=frozenset({SCOPE_READ}),
                      kind="token", project_id=(project or world["a"]).id,
                      token_id=uuid4(), label="cpmcp_test")


def full(world, project=None) -> Credential:
    return Credential(user=world["manager"], scopes=frozenset({SCOPE_READ, SCOPE_PROPOSE}),
                      kind="token", project_id=(project or world["a"]).id,
                      token_id=uuid4(), label="cpmcp_test")


def test_a_read_only_credential_is_shown_no_proposal(db, world):
    listed = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                             message=rpc("tools/list"),
                             credential=read_only(world))["result"]["tools"]
    assert listed
    assert all(tool["annotations"]["readOnlyHint"] for tool in listed)


def test_the_same_caller_with_a_full_credential_is_shown_proposals(db, world):
    """Proves the filtering above is the credential's doing and not the
    permissions', which are identical in both calls."""
    listed = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                             message=rpc("tools/list"),
                             credential=full(world))["result"]["tools"]
    assert any(not tool["annotations"]["readOnlyHint"] for tool in listed)


def test_a_hidden_tool_is_also_refused_when_called_anyway(db, world):
    """Hiding it is a courtesy to the model. The refusal is the boundary."""
    reply = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                            message=rpc("tools/call", {"name": propose_tool_name(),
                                                       "arguments": {"title": "x",
                                                                     "description": "y"}}),
                            credential=read_only(world))
    assert reply["result"]["isError"] is True
    assert reply["result"]["structuredContent"]["errorCode"] == "SCOPE_DENIED"


def test_a_read_tool_is_unaffected_by_the_narrower_scope(db, world):
    reply = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                            message=rpc("tools/call", {"name": "get_project"}),
                            credential=read_only(world))
    assert reply["result"]["isError"] is False


def test_an_unknown_tool_is_unknown_and_not_out_of_scope(db, world):
    """Answering 'not in your scope' for a name that does not exist would tell
    a client which names are real."""
    reply = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                            message=rpc("tools/call", {"name": "no_such_tool"}),
                            credential=read_only(world))
    assert reply["result"]["structuredContent"]["errorCode"] == "UNKNOWN_TOOL"


def test_omitting_the_credential_changes_nothing(db, world):
    """The default is 'as much as this user may do' — there is no value of
    `credential` that grants more than the tool layer already would."""
    without = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                              message=rpc("tools/list"))["result"]["tools"]
    with_full = protocol.handle(db, user=world["manager"], project_id=world["a"].id,
                                message=rpc("tools/list"),
                                credential=full(world))["result"]["tools"]
    assert [tool["name"] for tool in without] == [tool["name"] for tool in with_full]


def test_a_session_credential_is_not_bound_to_a_project(db, world):
    credential = credentials.session_credential(world["manager"])
    assert credential.allows_project(world["a"].id)
    assert credential.allows_project(uuid4())
    assert credential.allows_proposals()


def test_a_client_token_reaches_only_its_own_project(db, world):
    """The owner has access to project B. That is exactly why the token
    must not."""
    credential = read_only(world, project=world["a"])
    assert credential.allows_project(world["a"].id)
    assert not credential.allows_project(world["b"].id)


# --- The budget -------------------------------------------------------------

def test_only_tool_calls_are_charged():
    assert limits.cost(rpc("ping")) == 0
    assert limits.cost(rpc("tools/list")) == 0
    assert limits.cost(rpc("initialize")) == 0
    assert limits.cost(rpc("tools/call", {"name": "get_project"})) == 1


def test_a_batch_costs_one_unit_per_call_it_carries():
    """Counting requests instead of calls would leave batching as a way
    straight through the limit."""
    batch = [rpc("ping", request_id=1),
             rpc("tools/call", {"name": "get_project"}, request_id=2),
             rpc("tools/call", {"name": "get_project"}, request_id=3)]
    assert limits.cost(batch) == 2


def test_a_tool_call_sent_as_a_notification_still_costs(db):
    """It produces no response, but it still runs the tool."""
    assert limits.cost({"jsonrpc": "2.0", "method": "tools/call",
                        "params": {"name": "get_project"}}) == 1


def test_the_budget_refuses_once_it_is_spent(db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 3)
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_WINDOW_SECONDS", 60)
    key = f"user:{world['manager'].id}"

    for expected in (2, 1, 0):
        budget = limits.consume(db, key=key, units=1)
        assert budget.allowed and budget.remaining == expected
    db.commit()

    refused = limits.consume(db, key=key, units=1)
    assert not refused.allowed
    assert refused.retry_after >= 1
    assert refused.headers["Retry-After"] == str(refused.retry_after)


def test_a_refused_request_spends_nothing(db, world, monkeypatch):
    """Charging for refusals is right for a login, where an attacker should dig
    their own hole deeper, and wrong here — the caller is a legitimate client
    going too fast and needs the window to drain."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 2)
    key = f"user:{world['manager'].id}"
    limits.consume(db, key=key, units=2)
    db.commit()

    before = db.query(RateLimitHit).filter(RateLimitHit.key == key).count()
    limits.consume(db, key=key, units=1)
    db.commit()
    assert db.query(RateLimitHit).filter(RateLimitHit.key == key).count() == before


def test_a_batch_is_all_or_nothing(db, world, monkeypatch):
    """A partial result a client cannot distinguish from a complete one is
    worse than a refusal."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 5)
    key = f"user:{world['manager'].id}"
    limits.consume(db, key=key, units=3)
    db.commit()

    refused = limits.consume(db, key=key, units=3)
    db.commit()
    assert not refused.allowed
    assert db.query(RateLimitHit).filter(RateLimitHit.key == key).count() == 3


def test_two_credentials_have_separate_budgets(db, world, monkeypatch):
    """A runaway desktop client must not throttle the same person's browser."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 1)
    first, second = f"token:{uuid4()}", f"token:{uuid4()}"
    assert limits.consume(db, key=first, units=1).allowed
    assert limits.consume(db, key=second, units=1).allowed
    assert not limits.consume(db, key=first, units=1).allowed
    db.rollback()


def test_the_session_key_is_the_user_and_the_token_key_is_the_token(db, world):
    """Keying a session on its access token would let a client reset its budget
    by logging in again."""
    session = credentials.session_credential(world["manager"])
    assert session.rate_key == f"user:{world['manager'].id}"
    token = read_only(world)
    assert token.rate_key == f"token:{token.token_id}"


def test_limiting_can_be_switched_off(db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 0)
    assert not limits.is_enabled()
    budget = limits.consume(db, key=f"user:{world['manager'].id}", units=50)
    assert budget.allowed and budget.headers == {}


def test_retry_after_waits_for_the_oldest_hit_not_the_newest(db, world, monkeypatch):
    """`seconds_since_last` would tell a throttled caller to retry immediately."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 2)
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_WINDOW_SECONDS", 100)
    key = f"user:{world['manager'].id}"
    now = datetime.now(timezone.utc)
    rate_limit_service.record_hit(db, scope=limits.SCOPE, key=key,
                                  now=now - timedelta(seconds=90))
    rate_limit_service.record_hit(db, scope=limits.SCOPE, key=key, now=now)
    db.commit()

    refused = limits.consume(db, key=key, units=1, now=now)
    assert not refused.allowed
    # The oldest of the two leaves the window in ten seconds; the newest would
    # have suggested a hundred.
    assert 5 <= refused.retry_after <= 15


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


def bearer(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def url(project) -> str:
    return f"/api/v1/mcp/projects/{project.id}"


def test_a_client_token_authenticates_the_mcp_surface(client, db, world):
    _, secret = mint(db, world)
    response = client.post(url(world["a"]), headers=bearer(secret), json=rpc("tools/list"))
    assert response.status_code == 200, response.text
    assert response.json()["result"]["tools"]


def test_a_client_token_is_refused_on_another_project(client, db, world):
    """Its owner can reach project B perfectly well. The token cannot."""
    _, secret = mint(db, world, project=world["a"])
    response = client.post(url(world["b"]), headers=bearer(secret), json=rpc("tools/list"))
    assert response.status_code == 403
    assert "different project" in response.json()["detail"]


def test_a_client_token_cannot_authenticate_the_rest_api(client, db, world):
    """No route outside the MCP endpoint consults that table, so this is a
    property of the design rather than a check somebody remembered to write."""
    _, secret = mint(db, world)
    assert client.get("/api/v1/auth/me", headers=bearer(secret)).status_code == 401
    assert client.get("/api/v1/mcp/tokens", headers=bearer(secret)).status_code == 401


def test_a_revoked_token_is_refused_over_http(client, db, world):
    row, secret = mint(db, world)
    assert client.post(url(world["a"]), headers=bearer(secret),
                       json=rpc("ping")).status_code == 200
    token_service.revoke(db, row)
    db.commit()
    assert client.post(url(world["a"]), headers=bearer(secret),
                       json=rpc("ping")).status_code == 401


def test_a_read_only_token_cannot_propose_over_http(client, db, world):
    _, secret = mint(db, world, scopes=[SCOPE_READ])
    response = client.post(url(world["a"]), headers=bearer(secret), json=rpc(
        "tools/call", {"name": propose_tool_name(),
                       "arguments": {"title": "Nope", "description": "x"}}))
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True


def test_the_budget_is_published_on_every_answer(client, db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 5)
    headers = auth(client, world["manager"])
    response = client.post(url(world["a"]), headers=headers,
                           json=rpc("tools/call", {"name": "get_project"}))
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


def test_too_many_calls_are_refused_with_retry_after(client, db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 2)
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_WINDOW_SECONDS", 60)
    headers = auth(client, world["manager"])
    call = rpc("tools/call", {"name": "get_project"})

    for _ in range(2):
        assert client.post(url(world["a"]), headers=headers, json=call).status_code == 200

    refused = client.post(url(world["a"]), headers=headers, json=call)
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1


def test_a_notification_that_costs_a_unit_still_reports_the_budget(
        client, db, world, monkeypatch):
    """202 carries no body, so the headers are the only thing a self-pacing
    client has to go on."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 5)
    headers = auth(client, world["manager"])
    response = client.post(url(world["a"]), headers=headers, json={
        "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_project"}})
    assert response.status_code == 202
    assert not response.content
    assert response.headers["X-RateLimit-Remaining"] == "4"


def test_cheap_methods_are_never_charged(client, db, world, monkeypatch):
    """A client that reconnects often should not be throttled for doing the
    right thing."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 1)
    headers = auth(client, world["manager"])
    for message in (rpc("ping"), rpc("tools/list"), rpc("initialize", {})):
        assert client.post(url(world["a"]), headers=headers,
                           json=message).status_code == 200


def test_a_batch_cannot_smuggle_calls_past_the_limit(client, db, world, monkeypatch):
    """Four units of budget, two batches of three. The second must not fit,
    which it would if a batch cost one unit like every other request."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 4)
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_WINDOW_SECONDS", 60)
    headers = auth(client, world["manager"])
    call = rpc("tools/call", {"name": "get_project"}, request_id=None)
    batch = [dict(call, id=index) for index in range(3)]

    assert client.post(url(world["a"]), headers=headers, json=batch).status_code == 200
    assert client.post(url(world["a"]), headers=headers, json=batch).status_code == 429


def test_a_batch_larger_than_the_whole_budget_is_a_client_error(client, db, world, monkeypatch):
    """Retrying it will never succeed, so 429 would be a promise the server
    cannot keep."""
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 2)
    headers = auth(client, world["manager"])
    call = rpc("tools/call", {"name": "get_project"}, request_id=None)
    response = client.post(url(world["a"]), headers=headers,
                           json=[dict(call, id=index) for index in range(5)])
    assert response.status_code == 400
    assert "at most 2" in response.json()["detail"]


def test_a_client_token_and_its_owners_session_do_not_share_a_budget(
        client, db, world, monkeypatch):
    monkeypatch.setattr(settings, "MCP_RATE_LIMIT_CALLS", 1)
    _, secret = mint(db, world)
    call = rpc("tools/call", {"name": "get_project"})

    assert client.post(url(world["a"]), headers=bearer(secret), json=call).status_code == 200
    assert client.post(url(world["a"]), headers=bearer(secret), json=call).status_code == 429
    # Same person, different credential, untouched budget.
    assert client.post(url(world["a"]), headers=auth(client, world["manager"]),
                       json=call).status_code == 200


# --- The token API ----------------------------------------------------------

def test_the_secret_is_returned_once_and_never_listed(client, db, world):
    headers = auth(client, world["manager"])
    created = client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "Laptop", "projectId": str(world["a"].id)})
    assert created.status_code == 201, created.text
    body = created.json()
    secret = body["token"]
    assert secret.startswith(TOKEN_PREFIX)
    assert body["record"]["prefix"] in secret

    listed = client.get("/api/v1/mcp/tokens", headers=headers)
    assert listed.status_code == 200
    assert secret not in listed.text
    assert any(item["id"] == body["record"]["id"] for item in listed.json())


def test_a_token_cannot_be_issued_for_an_unreachable_project(client, db, world):
    headers = auth(client, world["outsider"])
    response = client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "Sneaky", "projectId": str(world["a"].id)})
    assert response.status_code == 403


def test_an_unknown_scope_is_refused_over_http(client, db, world):
    headers = auth(client, world["manager"])
    response = client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "Wide", "projectId": str(world["a"].id), "scopes": ["mcp:everything"]})
    assert response.status_code == 400


def test_a_person_sees_only_their_own_tokens(client, db, world):
    mint(db, world, owner=world["manager"])
    outsider_headers = auth(client, world["outsider"])
    assert client.get("/api/v1/mcp/tokens", headers=outsider_headers).json() == []


def test_an_administrator_sees_every_token(client, db, world):
    """Revoking a compromised credential cannot wait for its owner to be
    reachable."""
    row, _ = mint(db, world, owner=world["manager"])
    listed = client.get("/api/v1/mcp/tokens", headers=auth(client, world["admin"])).json()
    assert any(item["id"] == str(row.id) for item in listed)


def test_revoking_takes_effect_on_the_next_request(client, db, world):
    headers = auth(client, world["manager"])
    created = client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "Doomed", "projectId": str(world["a"].id)}).json()
    secret = created["token"]
    assert client.post(url(world["a"]), headers=bearer(secret),
                       json=rpc("ping")).status_code == 200

    deleted = client.delete(f"/api/v1/mcp/tokens/{created['record']['id']}", headers=headers)
    assert deleted.status_code == 204
    assert client.post(url(world["a"]), headers=bearer(secret),
                       json=rpc("ping")).status_code == 401


def test_somebody_elses_token_is_not_found(client, db, world):
    """The same answer as 'no such token', because to this caller it is the
    same fact."""
    row, _ = mint(db, world, owner=world["manager"])
    response = client.delete(f"/api/v1/mcp/tokens/{row.id}",
                             headers=auth(client, world["outsider"]))
    assert response.status_code == 404


def test_revoking_still_works_with_the_surface_switched_off(client, db, world, monkeypatch):
    """An operator who has just turned MCP off in a hurry must still be able to
    take the credentials back."""
    row, _ = mint(db, world)
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    headers = auth(client, world["manager"])
    assert client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "x", "projectId": str(world["a"].id)}).status_code == 503
    assert client.delete(f"/api/v1/mcp/tokens/{row.id}", headers=headers).status_code == 204


def test_issuing_and_revoking_are_both_audited(client, db, world):
    """A long-lived credential appearing or disappearing is worth keeping —
    unlike a read, which is not."""
    headers = auth(client, world["manager"])
    created = client.post("/api/v1/mcp/tokens", headers=headers, json={
        "name": "Audited", "projectId": str(world["a"].id)}).json()
    client.delete(f"/api/v1/mcp/tokens/{created['record']['id']}", headers=headers)

    session = SessionLocal()
    try:
        actions = {row.action for row in session.query(AuditLog).filter(
            AuditLog.actor_id == world["manager"].id).all()}
        assert {"mcp_token_created", "mcp_token_revoked"} <= actions
        entry = session.query(AuditLog).filter(
            AuditLog.actor_id == world["manager"].id,
            AuditLog.action == "mcp_token_created").first()
        # The prefix, never the secret and never the hash.
        assert created["record"]["prefix"] in entry.details
        assert created["token"] not in entry.details
    finally:
        session.close()


def test_the_stored_row_carries_no_column_that_could_impersonate(db, world):
    """A structural assertion, not a behavioural one: a table with no secret
    column cannot leak one however the service layer changes."""
    columns = {column.name for column in McpClientToken.__table__.columns}
    assert "token" not in columns and "secret" not in columns
    assert "token_hash" in columns
