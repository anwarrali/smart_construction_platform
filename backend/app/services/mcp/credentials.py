"""Who is calling the MCP surface, and how much of themselves they brought.

Two credentials reach this surface and they are not equally trusted:

  * a **session** — the platform's own access token, the same one the web app
    uses. It carries the user's whole authority for a few minutes;
  * a **client token** — a row in `mcp_client_tokens`, bound to one project and
    one scope set, valid for weeks.

`Credential` is the single object both become, so nothing downstream has to
know which arrived. It answers three questions and nothing else: whose
authority is this, which project may it reach, and may it propose.

## The rule this module exists to keep

**A credential only ever subtracts.** It never carries a permission its owner
does not hold and never widens one they do — every call still runs through
`ai_tools.call_tool` as the user, against the same permission checks, at the
moment of the call. So a token issued last month to somebody who has since
lost `tasks.create` cannot create a task, without anything having to notice
that the token was issued earlier.

What a token *can* do is take away: one project instead of all of theirs, and
`mcp:read` without `mcp:propose`. Those subtractions are enforced in two
places on purpose — the tool is hidden from `tools/list`, and refused if
called anyway. Hiding it is a courtesy to the model; the refusal is the
boundary.

## No HTTP here

Resolution failures raise `CredentialError`, which carries a status and a
sentence. `api/mcp.py` turns those into responses. Keeping the transport out
of this module is what lets the whole of it be tested with a session and a
string.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.enums import UserStatus
from app.models.mcp_token import (
    ALL_SCOPES, SCOPE_PROPOSE, SCOPE_READ, TOKEN_PREFIX, McpClientToken,
)
from app.models.user import User

#: How stale `last_used_at` is allowed to be. Its only job is to let a person
#: tell a live token from a forgotten one before revoking it, and a minute's
#: resolution answers that — where a write per request would put an UPDATE in
#: the path of every single tool call.
TOUCH_INTERVAL_SECONDS = 60


class CredentialError(Exception):
    """A credential that could not be resolved, and why, in HTTP terms.

    The status codes deliberately mirror `get_current_user`: an unusable
    credential is 401, a usable credential belonging to an unusable account is
    403. A client that already handles the session path handles these too.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Credential:
    """One resolved caller. Immutable, and never more than its owner."""

    user: User
    #: What this credential may do, as a subset of `ALL_SCOPES`.
    scopes: frozenset[str]
    #: "session" or "token". Logged, never used for a decision — every
    #: difference between the two is already expressed in the fields below.
    kind: str
    #: The single project a client token is bound to. None for a session,
    #: which may reach any project its owner can.
    project_id: uuid.UUID | None = None
    token_id: uuid.UUID | None = None
    #: What to call this in a log line. Never the secret.
    label: str = "session"

    @property
    def rate_key(self) -> str:
        """The identity the throttle counts against.

        Per credential, not per user: one runaway desktop client must not
        throttle the same person's browser session, and two clients on two
        machines each get their own budget because each holds its own token.

        A session falls back to the user id rather than to its own token,
        because an access token can be replaced by logging in again — keying on
        it would let a client reset its budget by re-authenticating.
        """
        if self.token_id is not None:
            return f"token:{self.token_id}"
        return f"user:{self.user.id}"

    def allows_project(self, project_id) -> bool:
        """A client token reaches exactly the project it was issued for.

        This is the check `user_has_project_access` cannot make: the owner may
        well have access to the other project, which is precisely why the token
        must not.
        """
        if self.project_id is None:
            return True
        return str(self.project_id) == str(project_id)

    def allows_proposals(self) -> bool:
        return SCOPE_PROPOSE in self.scopes

    def allows_definition(self, definition: dict) -> bool:
        """May this credential see and use this tool?

        Kind is read from the tool's own published definition, so a tool added
        to the table is governed by this the day it is added — there is no
        second list here to forget to update.
        """
        if SCOPE_READ not in self.scopes:
            return False
        if definition.get("requiresConfirmation") or definition.get("kind") == "PROPOSE":
            return self.allows_proposals()
        return True


def session_credential(user: User) -> Credential:
    """The web app's own token, carrying its owner's full authority.

    Given every scope rather than a narrowed set: this is the credential the
    surface already accepted before client tokens existed, and quietly
    restricting it would change behaviour nobody asked to change. The scoping
    story belongs to tokens, which are issued deliberately.
    """
    return Credential(user=user, scopes=frozenset(ALL_SCOPES), kind="session")


def looks_like_client_token(raw: str) -> bool:
    """Cheap discrimination, before anything expensive is attempted.

    A client token is recognisable by its prefix, so the endpoint never has to
    try a JWT decode, fail, and then guess. It also means a mistyped JWT is
    reported as a bad session rather than as an unknown client token.
    """
    return bool(raw) and raw.startswith(TOKEN_PREFIX)


def from_client_token(db: Session, raw: str, *, now: datetime | None = None) -> Credential:
    """Resolve a client token, applying every check a session gets and two more.

    The account checks are the same ones `get_current_user` makes, repeated
    rather than shared because they are the reason this is safe: a suspended
    person's month-old token must stop working the moment they are suspended,
    not when it expires.
    """
    now = now or datetime.now(timezone.utc)
    row = db.query(McpClientToken).filter(
        McpClientToken.token_hash == hash_token(raw),
    ).first()

    # One message for "no such token", "revoked" and "expired" would be tidier
    # and worse: a client that cannot tell an expired credential from a wrong
    # one cannot tell its user what to do about it. None of the three discloses
    # anything — the caller already holds the secret being judged.
    if row is None:
        raise CredentialError(401, "This MCP client token is not recognised")
    if row.revoked_at is not None:
        raise CredentialError(401, "This MCP client token has been revoked")
    if row.is_expired(now):
        raise CredentialError(401, "This MCP client token has expired")

    user = row.user or db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise CredentialError(401, "This MCP client token is not recognised")
    if user.status in {UserStatus.INACTIVE, UserStatus.SUSPENDED}:
        raise CredentialError(403, "User account is deactivated or suspended")
    if user.must_change_password:
        # A long-lived credential must not become the way around a forced
        # password change. The web app's own token is refused here too.
        raise CredentialError(403, "PASSWORD_CHANGE_REQUIRED")

    _touch(db, row, now)

    return Credential(
        user=user,
        scopes=frozenset(row.scope_set & set(ALL_SCOPES)),
        kind="token",
        project_id=row.project_id,
        token_id=row.id,
        label=row.prefix,
    )


def _touch(db: Session, row: McpClientToken, now: datetime) -> None:
    """Record that the token was used, at most once a minute.

    Committed here rather than left to the request: a read-only tool call
    commits nothing, so without this the timestamp of a token used purely for
    reading would never be written — which is exactly the token somebody would
    want to see before revoking it.
    """
    last = row.last_used_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < timedelta(seconds=TOUCH_INTERVAL_SECONDS):
            return
    row.last_used_at = now
    db.commit()
