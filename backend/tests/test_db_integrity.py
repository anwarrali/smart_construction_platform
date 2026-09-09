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


def _migration_chain() -> dict[str, str | None]:
    """Every migration on disk, as {revision: down_revision}.

    Shared by the two tests below so that "what is the head" is derived once
    from the files rather than restated as a literal in each.
    """
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
    return revisions


def _heads(revisions: dict[str, str | None]) -> list[str]:
    parents = set(revisions.values()) - {None}
    return [rev for rev in revisions if rev not in parents]


def test_the_migration_chain_has_exactly_one_head():
    """A branch point would mean `alembic upgrade head` is ambiguous."""
    revisions = _migration_chain()
    heads = _heads(revisions)
    # Deliberately a literal: it is the tripwire that makes adding a migration
    # a conscious act rather than something that slips in unnoticed. Bump it
    # when you add one.
    # Bumped by `e91c4d7a3f26`, which adds `document_chunks` (RAG-indexed
    # passages) and the document indexing-state columns.
    # Bumped by `f92d5e8b4a37`, which adds `confidence`, `storey` and `space`
    # to `ifc_coordination_findings` — needed once findings could be inferred
    # from geometry rather than only observed in metadata.
    # Bumped by `a03e6f9c5b48`, which records what an uploaded file turned out
    # to be alongside what its uploader called it, and adds the BOQ, SCHEDULE
    # and TECHNICAL document kinds.
    # Bumped by `b14f7a2c9e63`, which adds `agent_runs` — the record of which
    # agent ran, why, what it called and what it produced.
    # Bumped by `c15a8d2e7f10`, the RBAC expand step: configurable roles and
    # disciplines, office membership, external project parties, and the rename
    # of `field_submissions.worker_id` to `submitted_by_id`.
    # Bumped by `d26b9f4a1e08`, which renames the discipline-scope permission
    # and seeds the new work-scope codes onto existing roles.
    # Bumped by `e48c1b6d3f27`, which records on each role which legacy enum
    # value an account created under it is written with — the last thing
    # provisioning still needed the retired `UserRole` for.
    # Bumped by `f59d2c8e4a13`, which seeds `document.view`, `site_report.view`,
    # `issue.view`, `design_change.view` and `client_portal.view` onto the roles
    # that already reach those pages, so naming the navigation decision changes
    # nobody's access.
    # Bumped by `aa41c7d2e908`, the unified file ingestion foundation: two new
    # tables (`ingested_files`, `ingestion_jobs`) and no change to any existing
    # one, so the chain lengthens and nothing else about the schema moves.
    # Bumped by `b52e9a1c4d70`, which puts the RAG indexing lifecycle on
    # `ingested_files` and gives `document_chunks` a second, mutually exclusive
    # source. Every existing chunk keeps its `document_id` untouched.
    # Bumped by `c63fa2b5e819`, which moves `document_chunks.embedding` from
    # JSONB to a pgvector `vector(1536)` with an HNSW cosine index. Needs the
    # `vector` extension, which is why the compose database image changed.
    # Bumped by `d74ab3c6f92a`, which adds `rag_index_jobs` and the
    # `index_started_at` timestamp the stale-index reaper needs. Additive: no
    # existing column is altered.
    # Bumped by `e71d5a3c9b42`, which adds `mcp_client_tokens` — long-lived,
    # project-scoped credentials for desktop MCP clients. A row rather than a
    # long-lived JWT precisely so that revoking one is an UPDATE that takes
    # effect on the next request. Additive.
    # Bumped by `f81c3a5d9e64`, which gives `documents` the `storage_key` it was
    # the only file-bearing table to lack. Additive and nullable: the bytes move
    # out of the public tree in `scripts/migrate_public_uploads.py`, which is a
    # file operation and therefore cannot live in a migration.
    # Bumped by `a92d4e1f70b3`, which grants the new `project.delete` permission
    # to the two seeded roles whose accounts could already delete a project.
    # Data only, no schema change: the code exists in the catalogue, but the
    # live resolver answers from `role_permissions` rows and the seeder that
    # writes them is a manual script, so without this the administrator who
    # could delete a project yesterday could not delete one today.
    # Bumped by `b73f5c8a2e91`, which gives `roles` an `is_archived` column and
    # backfills it from `legacy_role IS NULL` — separating the archived-role
    # policy from the migration-window translation column that was carrying it
    # by coincidence.
    assert heads == ["b73f5c8a2e91"], f"expected exactly one head, found: {heads}"

    # Every down_revision must point at a migration that actually exists —
    # a dangling reference would mean the chain is broken, not just branched.
    missing_parents = [rev for rev, parent in revisions.items()
                       if parent is not None and parent not in revisions]
    assert missing_parents == []


def test_the_running_database_is_at_the_latest_head(db):
    """The database has had every migration on disk applied to it.

    Compared against the head derived from the migration files rather than a
    literal revision. This test previously pinned `b76f1a3c9e58` and had been
    failing since `c87g2b4d0f69` was added without anyone updating it — which
    is exactly the failure mode a hardcoded value invites here. The sibling
    test above keeps the deliberate literal tripwire; this one only needs to
    know whether the running database is caught up, and the answer to that
    changes every time a migration lands.
    """
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    expected = _heads(_migration_chain())
    assert expected != [], "no migrations found on disk"
    assert current == expected[0], (
        f"database is at {current}, but the migrations on disk head at "
        f"{expected[0]} — run `alembic upgrade head`"
    )


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
        # Same category as `engineer_profiles`: these say what somebody's
        # position and specialisms are, not what they did. A deleted account
        # should take its office membership and its discipline list with it —
        # keeping them would leave a role assignment pointing at nobody.
        # The records of *work* that account produced are unaffected:
        # `field_submissions.submitted_by_id` is RESTRICT, which is why
        # retiring worker accounts deactivates them rather than deleting them.
        ("organization_memberships", "user_id"),
        ("user_disciplines", "user_id"),
        ("message_recipient_states", "user_id"),
        ("notifications", "user_id"),
        # Credential-shaped rows, the same category as password reset tokens:
        # a deleted account's pending verification codes and step-up grants
        # must go with it rather than linger as usable security state.
        ("otp_challenges", "user_id"),
        ("step_up_grants", "user_id"),
        ("password_reset_tokens", "user_id"),
        # An MCP client token is the same category again, and the argument is
        # sharper here than for a reset token: it is a *live* credential that
        # authenticates as its owner. A surviving row would be a bearer token
        # for a deleted account, which is the one outcome this table exists to
        # make impossible. Nothing it holds is a record of work — every call it
        # made is already in the audit trail under the actor's own id.
        ("mcp_client_tokens", "user_id"),
        # A push registration is one of "their own tokens" in the sense this
        # docstring means: it is a delivery address for a session, not a record
        # of work. It *must* cascade — a surviving row would keep pushing
        # notifications to a handset registered to a deleted account, and the
        # notifications themselves already cascade, so the token would outlive
        # everything it could refer to.
        ("device_tokens", "user_id"),
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
