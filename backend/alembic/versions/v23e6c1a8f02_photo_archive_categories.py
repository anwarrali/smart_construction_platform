"""smart evidence photo archive and normalized categories

Revision ID: v23e6c1a8f02
Revises: u22d5b0f7e91
"""

import re
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "v23e6c1a8f02"
down_revision = "u22d5b0f7e91"
branch_labels = None
depends_on = None

SYSTEM_CATEGORIES = (
    "FOUNDATIONS", "STRUCTURAL", "MASONRY", "ARCHITECTURAL", "ELECTRICAL",
    "MECHANICAL", "PLUMBING", "HVAC", "FINISHING", "DOORS", "WINDOWS",
    "SAFETY", "EXCAVATION", "CONCRETE", "REINFORCEMENT", "OTHER",
)
NAMESPACE = uuid.UUID("52f64a21-4338-48c1-b7a2-3ecf46832740")


def _code(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")[:80]


def upgrade() -> None:
    op.create_table(
        "photo_categories",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_photo_categories_system_code", "photo_categories", ["code"],
        unique=True, postgresql_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_photo_categories_project_code", "photo_categories", ["project_id", "code"],
        unique=True, postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "ix_photo_categories_project_active", "photo_categories", ["project_id", "active"]
    )

    op.create_table(
        "photo_category_assignments",
        sa.Column("field_submission_photo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=20), server_default="HUMAN", nullable=False),
        sa.Column("ai_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("ai_decision", sa.String(length=20), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["photo_categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["field_submission_photo_id"], ["field_submission_photos.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "field_submission_photo_id", "category_id",
            name="uq_photo_category_assignment",
        ),
    )
    op.create_index(
        "ix_photo_category_assignments_field_submission_photo_id",
        "photo_category_assignments", ["field_submission_photo_id"],
    )
    op.create_index(
        "ix_photo_category_assignments_category_id",
        "photo_category_assignments", ["category_id"],
    )
    op.create_index(
        "ix_photo_category_assignments_category_photo",
        "photo_category_assignments", ["category_id", "field_submission_photo_id"],
    )

    category_table = sa.table(
        "photo_categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("project_id", postgresql.UUID(as_uuid=True)),
        sa.column("is_system", sa.Boolean),
        sa.column("active", sa.Boolean),
    )
    system_rows = [
        {
            "id": uuid.uuid5(NAMESPACE, f"system:{code}"),
            "name": code.replace("_", " ").title(),
            "code": code,
            "project_id": None,
            "is_system": True,
            "active": True,
        }
        for code in SYSTEM_CATEGORIES
    ]
    op.bulk_insert(category_table, system_rows)

    bind = op.get_bind()
    legacy_rows = bind.execute(sa.text("""
        SELECT p.id AS photo_id, s.project_id, a.uploaded_by_id, p.category
        FROM field_submission_photos p
        JOIN field_submissions s ON s.id = p.field_submission_id
        JOIN attachments a ON a.id = p.attachment_id
        WHERE p.category IS NOT NULL AND btrim(p.category) <> ''
    """)).mappings().all()
    custom_inserted: set[uuid.UUID] = set()
    for row in legacy_rows:
        code = _code(row["category"])
        if not code:
            continue
        if code in SYSTEM_CATEGORIES:
            category_id = uuid.uuid5(NAMESPACE, f"system:{code}")
        else:
            category_id = uuid.uuid5(NAMESPACE, f"project:{row['project_id']}:{code}")
            if category_id not in custom_inserted:
                bind.execute(category_table.insert().values(
                    id=category_id,
                    name=row["category"].strip(),
                    code=code,
                    project_id=row["project_id"],
                    is_system=False,
                    active=True,
                ))
                custom_inserted.add(category_id)
        bind.execute(sa.text("""
            INSERT INTO photo_category_assignments
                (id, field_submission_photo_id, category_id, assigned_by_id, source)
            VALUES (:id, :photo_id, :category_id, :assigned_by_id, 'HUMAN')
            ON CONFLICT (field_submission_photo_id, category_id) DO NOTHING
        """), {
            "id": uuid.uuid4(),
            "photo_id": row["photo_id"],
            "category_id": category_id,
            "assigned_by_id": row["uploaded_by_id"],
        })

    op.drop_index("ix_field_submission_photos_category", table_name="field_submission_photos")
    op.drop_column("field_submission_photos", "category")
    op.create_index(
        "ix_field_submission_photos_created_at",
        "field_submission_photos", ["created_at"],
    )
    op.create_index(
        "ix_field_submissions_project_status_created",
        "field_submissions", ["project_id", "status", "created_at"],
    )
    op.create_index(
        "ix_field_submissions_task_status",
        "field_submissions", ["task_id", "status"],
    )
    op.create_index(
        "ix_field_submissions_worker_created",
        "field_submissions", ["worker_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_field_submissions_worker_created", table_name="field_submissions")
    op.drop_index("ix_field_submissions_task_status", table_name="field_submissions")
    op.drop_index("ix_field_submissions_project_status_created", table_name="field_submissions")
    op.drop_index("ix_field_submission_photos_created_at", table_name="field_submission_photos")
    op.add_column(
        "field_submission_photos",
        sa.Column("category", sa.String(length=80), nullable=True),
    )
    op.execute("""
        UPDATE field_submission_photos p
        SET category = c.name
        FROM photo_category_assignments a
        JOIN photo_categories c ON c.id = a.category_id
        WHERE a.field_submission_photo_id = p.id
          AND a.id = (
              SELECT a2.id FROM photo_category_assignments a2
              WHERE a2.field_submission_photo_id = p.id
              ORDER BY a2.created_at, a2.id LIMIT 1
          )
    """)
    op.create_index(
        "ix_field_submission_photos_category",
        "field_submission_photos", ["category"],
    )
    op.drop_index(
        "ix_photo_category_assignments_category_photo",
        table_name="photo_category_assignments",
    )
    op.drop_index(
        "ix_photo_category_assignments_category_id",
        table_name="photo_category_assignments",
    )
    op.drop_index(
        "ix_photo_category_assignments_field_submission_photo_id",
        table_name="photo_category_assignments",
    )
    op.drop_table("photo_category_assignments")
    op.drop_index("ix_photo_categories_project_active", table_name="photo_categories")
    op.drop_index("uq_photo_categories_project_code", table_name="photo_categories")
    op.drop_index("uq_photo_categories_system_code", table_name="photo_categories")
    op.drop_table("photo_categories")
