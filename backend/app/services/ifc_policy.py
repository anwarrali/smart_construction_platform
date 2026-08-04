"""Central IFC authorization and user-facing errors."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.core.deps import is_consultant_engineer, is_main_contractor_engineer, user_has_project_access
from app.models.enums import UserRole, UserStatus


IFC_PERMISSIONS = {
    "VIEW": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER, UserRole.CONSULTANT, UserRole.OWNER, UserRole.WORKER},
    "UPLOAD": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER},
    "MANAGE_VERSION": {UserRole.ADMIN, UserRole.PROJECT_MANAGER},
    "COMPARE": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER, UserRole.CONSULTANT},
    "REVIEW_FINDING": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER, UserRole.CONSULTANT},
    "REVIEW_SUGGESTION": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER},
    "MANAGE_LINK": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER},
    "DOWNLOAD": {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.ENGINEER, UserRole.CONSULTANT},
}


def can_ifc(db, user, project_id, permission: str) -> bool:
    if not settings.IFC_FEATURE_ENABLED or user.status != UserStatus.ACTIVE:
        return False
    if not user_has_project_access(db, user, project_id):
        return False
    if user.role not in IFC_PERMISSIONS.get(permission, set()):
        return False
    if permission == "UPLOAD" and user.role == UserRole.ENGINEER:
        return settings.IFC_ENGINEER_UPLOAD_ENABLED and is_main_contractor_engineer(user)
    if user.role == UserRole.ENGINEER and not (is_main_contractor_engineer(user) or is_consultant_engineer(user)):
        return False
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
    "IFC_GEOMETRY_FAILED": IFCError("3D view could not be generated", "The hierarchy and properties remain available.", True, "Retry geometry processing"),
    "IFC_DUPLICATE": IFCError("This IFC is already uploaded", "The exact same file already exists in this project.", False, "Open the existing version"),
    "IFC_COMPARISON_GROUP_MISMATCH": IFCError("Versions cannot be compared", "Choose two versions from the same model group.", False, "Select compatible versions"),
}


def friendly_ifc_error(code: str, support_log_id: str | None = None) -> dict:
    item = ERRORS.get(code, IFCError("IFC operation failed", "The operation could not be completed safely.", True, "Try again"))
    return {"code": code, "title": item.title, "description": item.description, "retryable": item.retryable, "suggestedAction": item.action, "supportLogId": support_log_id}
