"""Add the shared QA/QC discipline

Quality assurance / quality control tasks had no discipline to be filed
under: the shared catalogue covered the design and site trades but not QA/QC,
and the catalogue is only seeded on a fresh database, so adding it to
`role_templates.DISCIPLINES` alone would never reach an existing deployment.

Data only, and idempotent: the row is inserted if no shared `qa_qc`
discipline exists yet. An office that already created its own QA/QC
discipline keeps it — office rows shadow shared ones by code.

Revision ID: g4d1e7a2b958
Revises: f2b7d4e9a061
"""

import uuid

from alembic import op
import sqlalchemy as sa

revision = "g4d1e7a2b958"
down_revision = "f2b7d4e9a061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO disciplines (id, organization_id, code, name_en, name_ar, ifc_disciplines, legacy_code, rank, is_active)
            SELECT :id, NULL, 'qa_qc', 'QA/QC', 'ضبط وتأكيد الجودة', '[]'::jsonb, NULL, 160, true
            WHERE NOT EXISTS (SELECT 1 FROM disciplines WHERE code = 'qa_qc' AND organization_id IS NULL)
            """
        ),
        {"id": str(uuid.uuid4())},
    )


def downgrade() -> None:
    # Only remove it while nothing refers to it; a downgrade must not strip a
    # discipline from people or tasks that were filed under it.
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM disciplines d
            WHERE d.code = 'qa_qc' AND d.organization_id IS NULL
              AND NOT EXISTS (SELECT 1 FROM user_disciplines u WHERE u.discipline_id = d.id)
              AND NOT EXISTS (SELECT 1 FROM project_member_disciplines p WHERE p.discipline_id = d.id)
              AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.discipline = 'qa_qc')
            """
        )
    )
