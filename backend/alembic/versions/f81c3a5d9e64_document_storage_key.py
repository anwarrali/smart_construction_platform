"""Give documents a private-storage key

`documents` was the one file-bearing table with no `storage_key`. Its `file_url`
held an absolute public URL under the `/uploads` static mount, which is exactly
what made the document download endpoint's authorization advisory: the check ran
and then returned a location that needed no check to fetch.

`attachments` already had both columns, so it needed no schema change — only its
bytes moved. This migration adds the missing column and nothing else.

## Why nullable, and why no backfill here

The column is nullable and stays nullable. A migration runs inside a
transaction against the database; moving a file between two Docker volumes is
neither transactional nor something Alembic can roll back. Committing a
`storage_key` for bytes that had not actually been moved would leave rows
claiming a location nothing serves — a worse failure than the honest null,
because it looks correct.

So the file move and the backfill are one idempotent script,
`scripts/migrate_public_uploads.py`, run once after this migration. Until it has
run for a given row, `storage_key` is null and
`GET /documents/{id}/download` answers 409 with an explicit reason rather than
falling back to the public path. Refusing is the point: a fallback would
reinstate the vulnerability for exactly the rows that predate the fix.

Revision ID: f81c3a5d9e64
Revises: e71d5a3c9b42
"""

from alembic import op
import sqlalchemy as sa

revision = "f81c3a5d9e64"
down_revision = "e71d5a3c9b42"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_documents_storage_key"


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.String(length=500), nullable=True))
    # Indexed for the same reason `attachments.storage_key` is: the backfill
    # script and any future storage audit look rows up by key, not by id.
    op.create_index(INDEX_NAME, "documents", ["storage_key"])


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="documents")
    op.drop_column("documents", "storage_key")
