"""Central IFC authorization and user-facing errors.

Authorization here used to be a private role dictionary — eight verbs mapped to
sets of the retired `UserRole` enum, plus an affiliation check. That made the
IFC workspace the platform's second-largest authorization system after Voice,
and it meant the catalogue's `ifc.view` / `ifc.upload` / `ifc.manage_version`
entries were decorative: they appeared in the access-control matrix and
governed nothing.

Every verb now resolves through `has_permission`, so the entries in the matrix
are the entries that decide. The catalogue defaults were copied from the
retired dictionary verb by verb, so an unconfigured installation behaves
exactly as it did.

The two feature flags stay. They are operational kill-switches — "is IFC on at
all", "may non-managers upload yet" — not statements about who a person is, and
an administrator toggling a permission should not be able to turn a half-built
feature on.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.deps import user_has_project_access
from app.models.enums import UserStatus
from app.services.authorization import has_permission

#: The IFC verbs, and the catalogue permission that governs each.
IFC_VERB_PERMISSION: dict[str, str] = {
    "VIEW": "ifc.view",
    "UPLOAD": "ifc.upload",
    "MANAGE_VERSION": "ifc.manage_version",
    "COMPARE": "ifc.compare",
    "REVIEW_FINDING": "ifc.review_finding",
    "REVIEW_SUGGESTION": "ifc.review_suggestion",
    "MANAGE_LINK": "ifc.manage_link",
    "DOWNLOAD": "ifc.download",
}


def can_ifc(db, user, project_id, permission: str) -> bool:
    """Whether this person may perform this IFC verb on this project."""
    if not settings.IFC_FEATURE_ENABLED or user.status != UserStatus.ACTIVE:
        return False
    if not user_has_project_access(db, user, project_id):
        return False

    code = IFC_VERB_PERMISSION.get(permission)
    if code is None:
        # An unknown verb is a programming error, not an open door.
        return False
    if not has_permission(db, user, code, project_id):
        return False

    if permission == "UPLOAD" and not has_permission(
        db, user, "ifc.manage_version", project_id
    ):
        # Uploading below version-management level is still behind its own
        # rollout flag. Phrased as "does not also manage versions" rather than
        # "is an Engineer", because the role that may upload is now
        # configurable and the flag is about the feature's maturity, not about
        # anybody's job title.
        return settings.IFC_ENGINEER_UPLOAD_ENABLED

    return True


@dataclass(frozen=True)
class IFCError:
    title: str
    description: str
    retryable: bool
    action: str


ERRORS = {
    "IFC_FILE_CORRUPTED": IFCError("IFC file could not be read", "The file may be incomplete or exported in an unsupported format.", True, "Export the model again or retry"),
    "IFC_PARSER_UNAVAILABLE": IFCError("IFC processing is unavailable", "The server IFC parser is not installed correctly.", True, "Contact support"),
    "IFC_ENTITY_LIMIT_EXCEEDED": IFCError("Model is too large", "This model exceeds the configured safe entity limit.", False, "Upload a discipline or storey model"),
    "IFC_PARSE_TIMEOUT": IFCError("IFC processing timed out", "The model did not finish parsing within the configured safety window.", True, "Retry or upload a smaller discipline model"),
    "IFC_PARSER_OUT_OF_MEMORY": IFCError("Model needs more memory than this server has", "Processing was stopped by the operating system before it could finish.", True, "Upload a discipline or storey model, or ask an administrator for a larger processing host"),
    "IFC_PROCESSING_FAILED": IFCError("IFC processing did not complete", "Extraction stopped before the model could be stored. The uploaded file is unchanged.", True, "Retry processing, then contact support with the support log ID"),
    "IFC_GEOMETRY_FAILED": IFCError("3D view could not be generated", "The hierarchy and properties remain available.", True, "Retry geometry processing"),
    "IFC_DUPLICATE": IFCError("This IFC is already uploaded", "The exact same file already exists in this project.", False, "Open the existing version"),
    "IFC_COMPARISON_GROUP_MISMATCH": IFCError("Versions cannot be compared", "Choose two versions from the same model group.", False, "Select compatible versions"),
}


def friendly_ifc_error(code: str, support_log_id: str | None = None) -> dict:
    item = ERRORS.get(code, IFCError("IFC operation failed", "The operation could not be completed safely.", True, "Try again"))
    return {"code": code, "title": item.title, "description": item.description, "retryable": item.retryable, "suggestedAction": item.action, "supportLogId": support_log_id}
