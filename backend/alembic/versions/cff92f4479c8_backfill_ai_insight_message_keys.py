"""Backfill message_key/message_params_json on legacy ai_insights rows.

`ae32c1d7e043` added `message_key` but deliberately left existing rows alone,
so any insight stored before that migration ran still has `message_key IS
NULL` (or, for a slightly later batch, an empty string with an empty
`message_params_json`). The frontend falls back to the stored English
sentence whenever the key is missing, so those rows never picked up Arabic —
regardless of which language the reader selected.

This migration does not invent any new localization: it reproduces, for each
existing row, exactly what `app.services.ifc_compatibility_service` already
computes for a freshly-detected finding of the same `insight_type`:

  * `DISCIPLINE_<x>_NOT_IN_IFC`  -> message_key "DISCIPLINE_NOT_IN_IFC",
    params {discipline, label, taskCount} rebuilt from evidence_json exactly
    as `run_ifc_compatibility` derives them.
  * `TASK_<x>_ELEMENTS_MISSING`  -> message_key "TASK_ELEMENTS_MISSING",
    params {category, taskCount, expectedClasses} rebuilt from evidence_json.
  * `IFC_PROJECT_NAME_MISMATCH`  -> message_key "IFC_PROJECT_NAME_MISMATCH",
    params {projectName} rebuilt from evidence_json.
  * every other `insight_type` -> the live code's own fallback
    (`finding.message_key or finding.code`, `finding.params or
    finding.evidence`), i.e. message_key = insight_type itself and
    message_params_json = evidence_json when params were never set. This
    keeps the row consistent with what the application would persist today;
    it does not fabricate a translation catalogue entry that does not exist.

Only NULL-or-empty `message_key` rows are touched. `title`, `description`,
`status`, `fingerprint`, `reviewed_*`, `resolved_at`, `created_at`,
`updated_at` and every other column are left untouched, so no insight is
re-evaluated, re-opened, or duplicated by running this.

Revision ID: cff92f4479c8
Revises: ae32c1d7e043
"""

from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op

revision = "cff92f4479c8"
down_revision = "ae32c1d7e043"
branch_labels = None
depends_on = None


# Mirrors app.services.ifc_compatibility_service.DISCIPLINE_TERMS[*][2] — the
# label text baked into the DISCIPLINE_NOT_IN_IFC translation's {{label}}
# placeholder. Kept as a local, frozen copy on purpose: a migration must keep
# producing the same output on replay even if the application's vocabulary
# changes later.
DISCIPLINE_LABELS = {
    "ELECTRICAL": "electrical installation",
    "MECHANICAL_HVAC": "mechanical / HVAC installation",
    "PLUMBING": "plumbing / sanitary installation",
    "FIRE_PROTECTION": "fire protection installation",
    "STRUCTURAL": "structural works",
}

_DISCIPLINE_RE = re.compile(r"^DISCIPLINE_(.+)_NOT_IN_IFC$")
_TASK_ELEMENTS_RE = re.compile(r"^TASK_(.+)_ELEMENTS_MISSING$")


def derive_backfill(insight_type: str, evidence: dict) -> tuple[str, dict] | None:
    """The (message_key, message_params) a fresh finding of this type would get.

    Returns None when `insight_type` is not one of the families the
    translation catalogue actually covers today (DISCIPLINE_NOT_IN_IFC,
    TASK_ELEMENTS_MISSING, IFC_PROJECT_NAME_MISMATCH) *and* the evidence does
    not match the expected shape closely enough to trust — the caller then
    falls back to the code-as-key rule instead of guessing.
    """
    evidence = evidence or {}

    match = _DISCIPLINE_RE.match(insight_type)
    if match:
        discipline = match.group(1)
        label = DISCIPLINE_LABELS.get(discipline)
        if label and evidence.get("discipline") == discipline and "matchedTaskCount" in evidence:
            return "DISCIPLINE_NOT_IN_IFC", {
                "discipline": discipline.replace("_", "/").lower(),
                "label": label,
                "taskCount": evidence["matchedTaskCount"],
            }
        return None

    match = _TASK_ELEMENTS_RE.match(insight_type)
    if match:
        category = match.group(1)
        if "taskIds" in evidence and "expectedIfcClasses" in evidence:
            return "TASK_ELEMENTS_MISSING", {
                "category": category.lower(),
                "taskCount": len(evidence["taskIds"]),
                "expectedClasses": ", ".join(sorted(evidence["expectedIfcClasses"])),
            }
        return None

    if insight_type == "IFC_PROJECT_NAME_MISMATCH":
        if "platformProjectName" in evidence:
            return "IFC_PROJECT_NAME_MISMATCH", {"projectName": evidence["platformProjectName"]}
        return None

    return None


def run_backfill(bind) -> int:
    """Apply the backfill through a plain SQLAlchemy connection or session.

    Kept separate from `upgrade()` so the exact same code Alembic runs can be
    exercised directly against a test database, without an Alembic migration
    context. Returns the number of rows updated.
    """
    rows = bind.execute(sa.text(
        "SELECT id, insight_type, evidence_json, message_params_json "
        "FROM ai_insights WHERE message_key IS NULL OR message_key = ''"
    )).mappings().all()

    for row in rows:
        evidence = row["evidence_json"] or {}
        derived = derive_backfill(row["insight_type"], evidence)
        if derived is not None:
            message_key, params = derived
        else:
            # The live write path's own fallback: the finding's code becomes
            # its own message family, and its evidence becomes its params.
            # There is no catalogue entry for these yet, so the visible text
            # does not change — only the stored key becomes what today's
            # code would have written.
            message_key, params = row["insight_type"], evidence

        # Never overwrite params a previous run may have already populated;
        # only fill in what is genuinely empty. Makes re-running a no-op.
        existing_params = row["message_params_json"] or {}
        new_params = existing_params if existing_params else params

        bind.execute(
            sa.text(
                "UPDATE ai_insights "
                "SET message_key = :message_key, message_params_json = CAST(:params AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "message_key": message_key,
                "params": json.dumps(new_params),
                "id": row["id"],
            },
        )

    return len(rows)


def upgrade() -> None:
    run_backfill(op.get_bind())


def downgrade() -> None:
    # Deliberately a no-op, not a blanket clear.
    #
    # This migration only ever touches rows that had NULL/empty message_key,
    # but nothing distinguishes "backfilled by this migration" from "written
    # by ordinary application traffic between upgrade and any later
    # downgrade" — both look identical once stored. A blind UPDATE that clears
    # every non-empty message_key would also wipe rows the live code wrote
    # correctly on its own, which is a worse outcome than leaving the backfill
    # in place. Reverting this data is a manual, audited decision, not an
    # automatic one; add a one-off script if it is ever actually needed.
    pass
