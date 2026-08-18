"""Regression test for a live-QA-discovered crash in POST /auth/refresh.

The refresh token is single-use: a successful refresh rotates it, inserting
the *old* token's hash into `revoked_tokens` so it cannot be replayed. The
"already revoked?" check and that insert are two separate statements, not one
atomic operation — so two requests racing to refresh the *same* refresh token
(exactly what happens in the browser when several API calls 401 at once and
each independently starts a refresh) can both pass the check before either
commits. The loser then hits the unique constraint on `token_hash` at insert
time. Before this fix that was an unhandled `IntegrityError` — a raw 500,
observed live as a browser-side "CORS policy" error (the real cause of the
CORS-looking failure is that an unhandled exception's response never gets the
CORSMiddleware treatment a normal error response does) that broke every
in-flight request on the page. The fix catches the constraint violation and
answers with the same clean 401 the pre-existing check already gives a
that's-already-been-used token.
"""

import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import refresh
from app.core.security import create_refresh_token, hash_token
from app.db.database import SessionLocal
from app.models.enums import UserRole, UserStatus
from app.models.user import User


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


def _purge(user_id, token_hashes):
    session = SessionLocal()
    try:
        session.rollback()
        session.execute(text("DELETE FROM revoked_tokens WHERE token_hash = ANY(:hashes)"),
                        {"hashes": list(token_hashes)})
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def user(db):
    suffix = uuid.uuid4().hex[:10]
    person = User(
        full_name="Refresh Race User", email=f"refresh-race-{suffix}@example.com",
        hashed_password="x", role=UserRole.ENGINEER, status=UserStatus.ACTIVE,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


def test_two_concurrent_refreshes_of_the_same_token_never_500(user):
    """Fires two real, concurrent `refresh()` calls — each with its own DB
    session, as two real HTTP requests would have — for the identical
    refresh token, synchronized to maximize the chance both pass the
    revoked-token check before either commits. Exactly one of them may
    succeed; the other must fail cleanly (401), never with an unhandled
    exception."""
    token = create_refresh_token(data={"sub": str(user.id)})
    barrier = threading.Barrier(2)
    results: list[tuple[str, object]] = []
    lock = threading.Lock()

    def attempt():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            try:
                result = refresh({"refresh_token": token}, db=session)
                with lock:
                    results.append(("ok", result))
            except HTTPException as exc:
                with lock:
                    results.append(("http_exception", exc))
        except Exception as exc:  # noqa: BLE001 - this is exactly what must not happen
            with lock:
                results.append(("unhandled", exc))
        finally:
            session.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    try:
        assert len(results) == 2, f"expected both threads to finish, got {results}"

        unhandled = [item for kind, item in results if kind == "unhandled"]
        assert not unhandled, f"refresh() raised unhandled exception(s) under a race: {unhandled}"

        # Exactly one request can ever win: whichever one commits first
        # rotates the token, so the other necessarily finds it already
        # revoked — either via the pre-existing check (no race) or via the
        # new exception handler (raced past the check). Never zero, never two.
        outcomes = [kind for kind, _ in results]
        assert outcomes.count("ok") == 1, f"expected exactly one winner, got: {results}"
        for kind, item in results:
            if kind == "http_exception":
                assert item.status_code == 401, f"expected a clean 401 for the losing request, got {item.status_code}"
    finally:
        issued_hashes = {hash_token(token)}
        for kind, item in results:
            if kind == "ok" and item.get("refresh_token"):
                issued_hashes.add(hash_token(item["refresh_token"]))
        _purge(user.id, issued_hashes)
