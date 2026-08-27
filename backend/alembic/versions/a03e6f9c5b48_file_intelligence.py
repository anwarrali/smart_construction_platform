"""File intelligence: detected format, suggested type, and three document kinds

Adds `detected_format`, `suggested_document_type` and `classification_json` to
`documents`, and extends the `document_type` enum with BOQ, SCHEDULE and
TECHNICAL.

`document_type` is what the uploader picked from a dropdown. Nothing has ever
looked inside the file to agree or disagree, so a bill of quantities filed as
"other" was invisible to anything reasoning about document types — and there
was no "bill of quantities" to pick in the first place. The new columns record
what the file turned out to be, alongside the human's choice rather than
instead of it.

Existing rows are left NULL: no classification has been run for them, and
inventing one would be indistinguishable from having actually looked.

`ALTER TYPE … ADD VALUE` is transactional from PostgreSQL 12 onwards, which
this deployment (15) satisfies. The new values are not written by this
migration, so they are committed before anything uses them.

Revision ID: a03e6f9c5b48
Revises: f92d5e8b4a37
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a03e6f9c5b48"
down_revision = "f92d5e8b4a37"
branch_labels = None
depends_on = None

NEW_TYPES = ("BOQ", "SCHEDULE", "TECHNICAL")


def upgrade() -> None:
    for value in NEW_TYPES:
        op.execute(f"ALTER TYPE document_type ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("documents", sa.Column("detected_format", sa.String(length=40), nullable=True))
    op.add_column("documents", sa.Column("suggested_document_type", sa.String(length=40), nullable=True))
    op.add_column(
        "documents",
        sa.Column("classification_json", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="{}"),
    )
    op.create_index("ix_documents_detected_format", "documents", ["detected_format"])
    op.create_index("ix_documents_suggested_document_type", "documents", ["suggested_document_type"])


def downgrade() -> None:
    op.drop_index("ix_documents_suggested_document_type", table_name="documents")
    op.drop_index("ix_documents_detected_format", table_name="documents")
    op.drop_column("documents", "classification_json")
    op.drop_column("documents", "suggested_document_type")
    op.drop_column("documents", "detected_format")
    # PostgreSQL cannot remove a value from an enum. Leaving BOQ/SCHEDULE/
    # TECHNICAL in place is harmless: nothing requires them to be absent, and
    # rebuilding the type would need every dependent column rewritten.
