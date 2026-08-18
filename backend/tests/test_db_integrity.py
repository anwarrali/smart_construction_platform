"""Database/Alembic integrity checks from the schema audit.

These pin the state a `alembic upgrade head` run must leave the database in —
not a guess about what a "healthy" schema looks like in the abstract, but the
specific things the audit actually checked: a single migration head, and the
three project_id indexes added for query paths confirmed (by grep, not
assumption) to filter on that column directly.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal


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
        session.close()


def test_the_migration_chain_has_exactly_one_head():
    """A branch point would mean `alembic upgrade head` is ambiguous."""
    # Some migrations declare `revision: str = "..."` (a type annotation),
    # most just `revision = "..."` — match both rather than assume one style.
    REVISION_RE = re.compile(r"^revision\s*(?::\s*[\w\[\], ]+)?\s*=\s*[\"']([\w]+)[\"']")
    DOWN_REVISION_RE = re.compile(
        r"^down_revision\s*(?::\s*[\w\[\], ]+)?\s*=\s*(None|[\"']([\w]+)[\"'])"
    )
    versions_dir = Path(__file__).resolve().parent.parent / "alembic" / "versions"
    revisions: dict[str, str | None] = {}
    for path in versions_dir.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = down_revision = None
        for line in source.splitlines():
            match = REVISION_RE.match(line.strip())
            if match:
                revision = match.group(1)
                continue
            match = DOWN_REVISION_RE.match(line.strip())
            if match:
                down_revision = match.group(2)
        if revision:
            revisions[revision] = down_revision

    parents = set(revisions.values()) - {None}
    heads = [rev for rev in revisions if rev not in parents]
    # Bumped by `c87g2b4d0f69`, which gives voice action drafts a `sequence`
    # so their order stops depending on a tied `created_at`.
    assert heads == ["c87g2b4d0f69"], f"expected exactly one head, found: {heads}"

    # Every down_revision must point at a migration that actually exists —
    # a dangling reference would mean the chain is broken, not just branched.
    missing_parents = [rev for rev, parent in revisions.items()
                       if parent is not None and parent not in revisions]
    assert missing_parents == []


def test_the_running_database_is_at_the_latest_head(db):
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert current == "b76f1a3c9e58"


def test_the_project_id_indexes_the_audit_added_are_present(db):
    rows = db.execute(text(
        "SELECT tablename, indexname FROM pg_indexes WHERE indexname IN "
        "('ix_notifications_project_id', 'ix_ifc_comparisons_project_id', "
        "'ix_ai_insight_sources_project_id')"
    )).fetchall()
    found = {table: index for table, index in rows}
    assert found == {
        "notifications": "ix_notifications_project_id",
        "ifc_comparisons": "ix_ifc_comparisons_project_id",
        "ai_insight_sources": "ix_ai_insight_sources_project_id",
    }


def test_no_foreign_key_referencing_users_cascades_over_audit_or_work_records(db):
    """A hard user delete must never silently erase audit history or the
    record of work someone did — those relationships are RESTRICT/SET NULL,
    never CASCADE. Only membership/session-shaped rows (project membership,
    notifications addressed to them, their own tokens) may cascade.
    """
    cascading_rows = db.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.referential_constraints rc
        JOIN information_schema.table_constraints tc
          ON tc.constraint_name = rc.constraint_name AND tc.table_schema = rc.constraint_schema
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = rc.unique_constraint_name
        WHERE ccu.table_name = 'users' AND tc.table_schema = 'public' AND rc.delete_rule = 'CASCADE'
    """)).fetchall()
    cascading = {(table, column) for table, column in cascading_rows}

    allowed_membership_cascades = {
        ("consultant_engineer_scopes", "engineer_user_id"),
        ("consultant_engineer_scopes", "consultant_user_id"),
        ("contractor_profiles", "user_id"),
        ("conversation_participants", "user_id"),
        ("engineer_profiles", "user_id"),
        ("message_recipient_states", "user_id"),
        ("notifications", "user_id"),
        # Credential-shaped rows, the same category as password reset tokens:
        # a deleted account's pending verification codes and step-up grants
        # must go with it rather than linger as usable security state.
        ("otp_challenges", "user_id"),
        ("step_up_grants", "user_id"),
        ("password_reset_tokens", "user_id"),
        ("project_consultant_reviewers", "user_id"),
        ("project_members", "user_id"),
        ("project_view_states", "user_id"),
        ("reminder_events", "recipient_id"),
        ("site_visit_participants", "user_id"),
        ("task_assignees", "user_id"),
        ("user_permission_overrides", "user_id"),
    }
    unexpected = cascading - allowed_membership_cascades
    assert unexpected == set(), f"unexpected cascade-on-user-delete: {unexpected}"


def test_email_is_globally_unique():
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'users' "
            "AND indexdef ILIKE '%UNIQUE%' AND indexdef ILIKE '%email%'"
        )).fetchone()
        assert row is not None
    finally:
        db.close()


def test_task_code_is_unique_per_project_not_globally():
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT conname FROM pg_constraint WHERE conname = 'uq_tasks_project_task_code'"
        )).fetchone()
        assert row is not None
    finally:
        db.close()
