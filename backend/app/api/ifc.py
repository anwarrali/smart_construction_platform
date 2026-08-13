"""Project-scoped IFC intelligence, versioning, linking and review APIs."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tasks import _is_project_manager, _next_task_code
from app.api.milestones import _next_code as _next_milestone_code
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.database import SessionLocal, get_db
from app.models.enums import IssueSeverity, IssueStatus, TaskPriority, TaskStatus, UserRole
from app.models.ifc import (
    IFCChangeRecord, IFCComparison, IFCCoordinationFinding, IFCElement, IFCEntityLink,
    IFCImpactSuggestion, IFCModelGroup, IFCModelVersion, IFCProcessingJob,
    IFCSpatialNode, IFCSuggestion,
)
from app.models.issue import Issue
from app.models.milestone import Milestone
from app.models.document import Document, MediaAsset
from app.models.site_report import SiteReport
from app.models.field_submission import FieldSubmission
from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User
from app.schemas.ifc import (
    IFCComparisonCreate, IFCComparisonOut, IFCElementOut, IFCLinkCreate, IFCLinkOut,
    IFCBulkReview, IFCModelCreate, IFCModelOut, IFCModelUpdate, IFCPaged, IFCReviewRequest,
    IFCSpatialNodeOut, IFCVersionOut, IFCVersionPatch,
)
from app.services.audit_service import record_audit
from app.services.file_storage import save_private_upload
from app.services.private_storage import private_storage
from app.services.ifc_parser import content_hash
from app.services.ifc_policy import can_ifc, friendly_ifc_error
from app.services.ifc_processing_service import compare_versions, process_version
from app.services.ifc_geometry_service import generate_geometry

router = APIRouter(prefix="/projects/{project_id}/ifc", tags=["IFC Intelligence"])


def _require(db: Session, user: User, project_id: uuid.UUID, permission: str) -> None:
    if not can_ifc(db, user, project_id, permission):
        raise HTTPException(status_code=403, detail=f"IFC {permission.lower().replace('_', ' ')} permission required")


def _group(db: Session, project_id: uuid.UUID, model_id: uuid.UUID) -> IFCModelGroup:
    item = db.query(IFCModelGroup).filter(IFCModelGroup.id == model_id, IFCModelGroup.project_id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="IFC model group not found")
    return item


def _version(db: Session, project_id: uuid.UUID, version_id: uuid.UUID) -> IFCModelVersion:
    item = db.query(IFCModelVersion).filter(IFCModelVersion.id == version_id, IFCModelVersion.project_id == project_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="IFC version not found")
    return item


def _background_process(version_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        process_version(db, version_id, actor_id)
    finally:
        db.close()


def _background_geometry(version_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        generate_geometry(db, version_id)
    finally:
        db.close()


@router.get("/models", response_model=list[IFCModelOut])
def list_models(project_id: uuid.UUID, include_archived: bool = False, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    query = db.query(IFCModelGroup).filter(IFCModelGroup.project_id == project_id)
    if not include_archived:
        query = query.filter(IFCModelGroup.archived_at.is_(None))
    return query.order_by(IFCModelGroup.updated_at.desc()).all()


@router.post("/models", response_model=IFCModelOut, status_code=201)
def create_model(project_id: uuid.UUID, payload: IFCModelCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "UPLOAD")
    item = IFCModelGroup(project_id=project_id, created_by_id=current_user.id, **payload.model_dump())
    db.add(item)
    record_audit(db, actor_id=current_user.id, action="ifc_model_created", entity_type="ifc_model_group", entity_id=item.id, project_id=project_id, details={"name": payload.name})
    try:
        db.commit(); db.refresh(item)
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="A model group with this name already exists") from exc
    return item


@router.get("/models/{model_id}", response_model=IFCModelOut)
def get_model(project_id: uuid.UUID, model_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    return _group(db, project_id, model_id)


@router.patch("/models/{model_id}", response_model=IFCModelOut)
def update_model(project_id: uuid.UUID, model_id: uuid.UUID, payload: IFCModelUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION")
    item = _group(db, project_id, model_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    record_audit(db, actor_id=current_user.id, action="ifc_model_updated", entity_type="ifc_model_group", entity_id=item.id, project_id=project_id)
    db.commit(); db.refresh(item); return item


@router.delete("/models/{model_id}")
def archive_model(project_id: uuid.UUID, model_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION")
    item = _group(db, project_id, model_id); item.archived_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action="ifc_model_archived", entity_type="ifc_model_group", entity_id=item.id, project_id=project_id)
    db.commit(); return {"message": "IFC model archived"}


@router.post("/models/{model_id}/archive")
def archive_model_action(project_id: uuid.UUID, model_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return archive_model(project_id, model_id, db, current_user)


@router.get("/models/{model_id}/versions", response_model=list[IFCVersionOut])
def list_versions(project_id: uuid.UUID, model_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _group(db, project_id, model_id)
    return db.query(IFCModelVersion).filter(IFCModelVersion.model_group_id == model_id).order_by(IFCModelVersion.version_number.desc()).all()


@router.post("/models/{model_id}/versions", response_model=IFCVersionOut, status_code=202)
async def upload_version(
    project_id: uuid.UUID, model_id: uuid.UUID, background_tasks: BackgroundTasks,
    file: UploadFile = File(...), title: str = Form(...), revision_code: str | None = Form(None),
    version_type: str = Form("DESIGN"), description: str | None = Form(None), discipline: str | None = Form(None),
    authoring_source: str | None = Form(None), parent_version_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    _require(db, current_user, project_id, "UPLOAD")
    group = _group(db, project_id, model_id)
    if group.archived_at:
        raise HTTPException(status_code=409, detail="Archived model groups cannot receive versions")
    if parent_version_id:
        parent = _version(db, project_id, parent_version_id)
        if parent.model_group_id != model_id:
            raise HTTPException(status_code=400, detail="Parent version must belong to this model group")
    storage_key, size = await private_storage.save(file, "ifc")
    with private_storage.local_path(storage_key) as stored_path:
        digest = content_hash(stored_path)
    duplicate = db.query(IFCModelVersion).filter(IFCModelVersion.project_id == project_id, IFCModelVersion.file_hash == digest).first()
    if duplicate:
        private_storage.delete(storage_key)
        detail = friendly_ifc_error("IFC_DUPLICATE"); detail["existingVersionId"] = str(duplicate.id)
        raise HTTPException(status_code=409, detail=detail)
    locked = db.query(IFCModelGroup).filter(IFCModelGroup.id == model_id).with_for_update().one()
    next_number = (db.query(func.max(IFCModelVersion.version_number)).filter(IFCModelVersion.model_group_id == model_id).scalar() or 0) + 1
    item = IFCModelVersion(
        model_group_id=model_id, project_id=project_id, version_number=next_number,
        revision_code=revision_code, version_type=version_type.strip().upper(), title=title.strip(), description=description,
        discipline=discipline or locked.discipline, authoring_source=authoring_source,
        original_filename=Path(file.filename or "model.ifc").name, storage_key=storage_key,
        file_hash=digest, file_size=size, uploaded_by_id=current_user.id,
        parent_version_id=parent_version_id, processing_status="UPLOADED",
    )
    db.add(item); db.flush()
    record_audit(db, actor_id=current_user.id, action="ifc_version_uploaded", entity_type="ifc_model_version", entity_id=item.id, project_id=project_id, details={"hash": digest, "size": size, "version": next_number})
    db.commit(); db.refresh(item)
    if settings.IFC_BACKGROUND_PROCESSING_ENABLED:
        background_tasks.add_task(_background_process, item.id, current_user.id)
    else:
        process_version(db, item.id, current_user.id); db.refresh(item)
    return item


@router.get("/versions/{version_id}", response_model=IFCVersionOut)
def get_version(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); return _version(db, project_id, version_id)


@router.patch("/versions/{version_id}", response_model=IFCVersionOut)
def patch_version(project_id: uuid.UUID, version_id: uuid.UUID, payload: IFCVersionPatch, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION"); item = _version(db, project_id, version_id)
    if item.row_version != payload.row_version:
        raise HTTPException(status_code=409, detail="The IFC version was changed by another user; refresh and retry")
    for key, value in payload.model_dump(exclude={"row_version"}, exclude_unset=True).items(): setattr(item, key, value)
    item.row_version += 1
    record_audit(db, actor_id=current_user.id, action="ifc_version_updated", entity_type="ifc_model_version", entity_id=item.id, project_id=project_id)
    db.commit(); db.refresh(item); return item


def _set_designation(db: Session, item: IFCModelVersion, field: str) -> None:
    column = IFCModelVersion.is_active if field == "active" else IFCModelVersion.is_baseline
    db.query(IFCModelVersion).filter(IFCModelVersion.model_group_id == item.model_group_id).update({column: False}, synchronize_session=False)
    setattr(item, "is_active" if field == "active" else "is_baseline", True)
    group = item.model_group
    setattr(group, "active_version_id" if field == "active" else "baseline_version_id", item.id)


@router.post("/versions/{version_id}/activate", response_model=IFCVersionOut)
def activate_version(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION"); item = _version(db, project_id, version_id)
    if item.processing_status not in {"READY", "READY_WITH_WARNINGS"}: raise HTTPException(status_code=409, detail="Only processed IFC versions can be activated")
    _set_designation(db, item, "active"); record_audit(db, actor_id=current_user.id, action="ifc_version_activated", entity_type="ifc_model_version", entity_id=item.id, project_id=project_id)
    db.commit(); db.refresh(item); return item


@router.post("/versions/{version_id}/baseline", response_model=IFCVersionOut)
def baseline_version(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION"); item = _version(db, project_id, version_id)
    if item.processing_status not in {"READY", "READY_WITH_WARNINGS"}: raise HTTPException(status_code=409, detail="Only processed IFC versions can be baselines")
    _set_designation(db, item, "baseline"); record_audit(db, actor_id=current_user.id, action="ifc_version_baselined", entity_type="ifc_model_version", entity_id=item.id, project_id=project_id)
    db.commit(); db.refresh(item); return item


@router.post("/versions/{version_id}/set-baseline", response_model=IFCVersionOut)
def set_baseline_version(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return baseline_version(project_id, version_id, db, current_user)


@router.post("/versions/{version_id}/retry", response_model=IFCVersionOut, status_code=202)
def retry_version(project_id: uuid.UUID, version_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_VERSION"); item = _version(db, project_id, version_id)
    if item.processing_status != "FAILED": raise HTTPException(status_code=409, detail="Only failed IFC processing jobs can be retried")
    background_tasks.add_task(_background_process, item.id, current_user.id); return item


@router.get("/versions/{version_id}/download")
def download_version(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "DOWNLOAD"); item = _version(db, project_id, version_id)
    if not private_storage.exists(item.storage_key): raise HTTPException(status_code=404, detail="Stored IFC file is unavailable")
    record_audit(db, actor_id=current_user.id, action="ifc_version_downloaded", entity_type="ifc_model_version", entity_id=item.id, project_id=project_id); db.commit()
    with private_storage.local_path(item.storage_key) as path:
        return FileResponse(path, filename=item.original_filename, media_type="application/x-step")


@router.get("/versions/{version_id}/hierarchy", response_model=list[IFCSpatialNodeOut])
def hierarchy(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    return db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version_id).order_by(IFCSpatialNode.node_type, IFCSpatialNode.name).all()


@router.get("/versions/{version_id}/geometry/status")
def geometry_status(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); item = _version(db, project_id, version_id)
    asset_exists = bool(item.geometry_storage_key and private_storage.exists(item.geometry_storage_key))
    status = item.geometry_status
    if status in {"GEOMETRY_READY", "GEOMETRY_PARTIAL"} and not asset_exists:
        status = "VIEWER_ASSET_MISSING"
    return {"versionId": str(item.id), "status": status, "assetReady": asset_exists,
            "error": item.geometry_error, "stats": item.geometry_stats_json or {}, "generatedAt": item.geometry_generated_at}


@router.post("/versions/{version_id}/geometry/generate", status_code=202)
def generate_version_geometry(project_id: uuid.UUID, version_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "UPLOAD"); item = _version(db, project_id, version_id)
    if item.processing_status not in {"READY", "READY_WITH_WARNINGS"}:
        raise HTTPException(status_code=409, detail="Metadata processing must finish before geometry generation")
    if item.geometry_status == "GEOMETRY_PROCESSING":
        return {"status": item.geometry_status, "message": "Geometry is already processing."}
    item.geometry_status = "GEOMETRY_PROCESSING"; item.geometry_error = None; db.commit()
    background_tasks.add_task(_background_geometry, item.id)
    return {"status": item.geometry_status, "message": "Geometry generation started."}


@router.get("/versions/{version_id}/geometry/asset")
def geometry_asset(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); item = _version(db, project_id, version_id)
    if item.geometry_status not in {"GEOMETRY_READY", "GEOMETRY_PARTIAL"} or not item.geometry_storage_key:
        raise HTTPException(status_code=409, detail={"status": item.geometry_status, "message": item.geometry_error or "Viewer geometry is not ready."})
    if not private_storage.exists(item.geometry_storage_key):
        raise HTTPException(status_code=404, detail={"status": "VIEWER_ASSET_MISSING", "message": "The generated viewer asset is missing."})
    with private_storage.local_path(item.geometry_storage_key) as path:
        return FileResponse(path, filename=f"{item.id}.bimgeom", media_type="application/vnd.construction.bim-geometry")


@router.get("/versions/{version_id}/geometry/mapping")
def geometry_mapping(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    result = {}
    for node in db.query(IFCSpatialNode).filter(
        IFCSpatialNode.version_id == version_id,
        IFCSpatialNode.node_type.in_(["BUILDING", "STOREY", "SPACE"]),
    ).all():
        step_id = (node.metadata_json or {}).get("stepId")
        if not isinstance(step_id, int):
            continue
        result[str(step_id)] = {
            "id": str(node.id), "globalId": node.global_id, "name": node.name,
            "entityType": node.entity_type, "kind": "SPATIAL", "nodeType": node.node_type,
            "buildingNodeId": str(node.id) if node.node_type == "BUILDING" else None,
            "storeyNodeId": str(node.id) if node.node_type == "STOREY" else None,
            "spaceNodeId": str(node.id) if node.node_type == "SPACE" else None,
            "category": node.node_type,
        }
    for item in db.query(IFCElement).filter(IFCElement.version_id == version_id).all():
        step_id = (item.metadata_json or {}).get("stepId")
        if not isinstance(step_id, int):
            continue
        result[str(step_id)] = {"id": str(item.id), "globalId": item.global_id, "name": item.name, "entityType": item.entity_type, "kind": "ELEMENT",
                                "buildingNodeId": str(item.building_node_id) if item.building_node_id else None,
                                "storeyNodeId": str(item.storey_node_id) if item.storey_node_id else None,
                                "spaceNodeId": str(item.space_node_id) if item.space_node_id else None,
                                "discipline": item.discipline, "systemName": item.system_name,
                                "category": (item.metadata_json or {}).get("normalizedCategory")}
    return {"versionId": str(version_id), "items": result}


@router.get("/versions/{version_id}/overview")
def version_overview(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Human-facing aggregate; raw IFC headers stay on the version/technical endpoint."""
    _require(db, current_user, project_id, "VIEW")
    version = _version(db, project_id, version_id)
    summary = version.model_summary_json or {}
    return {
        "versionId": str(version.id), "title": version.title, "revisionCode": version.revision_code,
        "processingStatus": version.processing_status, "geometryStatus": version.geometry_status,
        "counts": {"sites": summary.get("sites", 0), "buildings": summary.get("buildings", 0),
                   "storeys": summary.get("storeys", 0), "spaces": summary.get("spaces", 0),
                   **(summary.get("mainStatistics") or {})},
        "spaceCategories": summary.get("spaceCategories") or {},
        "disciplineBreakdown": summary.get("disciplineBreakdown") or {},
        "quality": summary.get("modelCompleteness") or {},
        "intelligenceSummary": summary.get("intelligenceSummary") or {},
    }


def _descendant_ids(nodes: list[IFCSpatialNode], root_id: uuid.UUID) -> set[uuid.UUID]:
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for item in nodes:
        children.setdefault(item.parent_id, []).append(item.id)
    result = {root_id}; pending = [root_id]
    while pending:
        current = pending.pop()
        for child_id in children.get(current, []):
            if child_id not in result:
                result.add(child_id); pending.append(child_id)
    return result


@router.get("/spatial/{node_id}/details")
def spatial_details(project_id: uuid.UUID, node_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    node = db.query(IFCSpatialNode).join(IFCModelVersion, IFCModelVersion.id == IFCSpatialNode.version_id).filter(
        IFCSpatialNode.id == node_id, IFCModelVersion.project_id == project_id,
    ).first()
    if not node:
        raise HTTPException(status_code=404, detail="IFC spatial node not found")
    all_nodes = db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == node.version_id).all()
    descendants = _descendant_ids(all_nodes, node.id)
    query = db.query(IFCElement).filter(IFCElement.version_id == node.version_id)
    if node.node_type == "SPACE": query = query.filter(IFCElement.space_node_id == node.id)
    elif node.node_type == "STOREY": query = query.filter(IFCElement.storey_node_id == node.id)
    elif node.node_type == "BUILDING": query = query.filter(IFCElement.building_node_id == node.id)
    rows = query.with_entities(IFCElement.id, IFCElement.entity_type, IFCElement.discipline, IFCElement.metadata_json).all()
    categories = Counter((metadata or {}).get("normalizedCategory") or entity_type for _, entity_type, _, metadata in rows)
    disciplines = Counter(discipline or "UNKNOWN" for _, _, discipline, _ in rows)
    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.spatial_node_id.in_(descendants)).all()
    link_counts = Counter(item.linked_entity_type for item in links)
    child_counts = Counter(item.node_type for item in all_nodes if item.id in descendants and item.id != node.id)
    return {
        "node": IFCSpatialNodeOut.model_validate(node), "childCounts": dict(child_counts),
        "elementCount": len(rows), "elementCategories": dict(categories), "disciplines": dict(disciplines),
        "relatedElementIds": [str(row[0]) for row in rows[:500]], "projectActivity": dict(link_counts),
        "measurements": (node.metadata_json or {}).get("measurements") or {},
        "spaceClassification": (node.metadata_json or {}).get("spaceClassification"),
        "availabilityNotice": "Relationships not present in the IFC model are shown as unavailable; no values are fabricated.",
    }


@router.get("/versions/{version_id}/storeys", response_model=list[IFCSpatialNodeOut])
def storeys(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    return db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version_id, IFCSpatialNode.node_type == "STOREY").order_by(IFCSpatialNode.elevation, IFCSpatialNode.name).all()


@router.get("/versions/{version_id}/spaces", response_model=list[IFCSpatialNodeOut])
def spaces(project_id: uuid.UUID, version_id: uuid.UUID, storey_id: uuid.UUID | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    query = db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version_id, IFCSpatialNode.node_type == "SPACE")
    if storey_id: query = query.filter(IFCSpatialNode.parent_id == storey_id)
    return query.order_by(IFCSpatialNode.name).all()


@router.get("/versions/{version_id}/elements", response_model=IFCPaged)
def elements(project_id: uuid.UUID, version_id: uuid.UUID, q: str | None = None, entity_type: str | None = None, discipline: str | None = None, storey_id: uuid.UUID | None = None, space_id: uuid.UUID | None = None, material: str | None = None, system: str | None = None, element_type: str | None = None, completeness: str | None = None, element_ids: str | None = None, sort_by: str = "name", sort_direction: str = "asc", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    query = db.query(IFCElement).filter(IFCElement.version_id == version_id)
    if q: query = query.filter(or_(IFCElement.name.ilike(f"%{q}%"), IFCElement.global_id.ilike(f"%{q}%"), IFCElement.tag.ilike(f"%{q}%"), IFCElement.type_name.ilike(f"%{q}%")))
    if entity_type: query = query.filter(IFCElement.entity_type == entity_type)
    if discipline: query = query.filter(IFCElement.discipline == discipline)
    if storey_id: query = query.filter(IFCElement.storey_node_id == storey_id)
    if space_id: query = query.filter(IFCElement.space_node_id == space_id)
    if material: query = query.filter(IFCElement.material_summary.ilike(f"%{material}%"))
    if system: query = query.filter(IFCElement.system_name.ilike(f"%{system}%"))
    if element_type: query = query.filter(IFCElement.type_name.ilike(f"%{element_type}%"))
    if completeness: query = query.filter(IFCElement.metadata_json["completenessStatus"].as_string() == completeness.upper())
    if element_ids:
        values = [value.strip() for value in element_ids.split(",") if value.strip()][:500]
        database_ids = []
        for value in values:
            try: database_ids.append(uuid.UUID(value))
            except ValueError: pass
        query = query.filter(or_(IFCElement.id.in_(database_ids), IFCElement.global_id.in_(values)))
    sort_columns = {"name": IFCElement.name, "ifcClass": IFCElement.entity_type, "discipline": IFCElement.discipline, "type": IFCElement.type_name, "tag": IFCElement.tag}
    order = sort_columns.get(sort_by, IFCElement.name)
    order = order.desc() if sort_direction.lower() == "desc" else order.asc()
    total = query.count(); rows = query.order_by(order, IFCElement.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [IFCElementOut.model_validate(row).model_dump(mode="json", by_alias=True) for row in rows], "total": total, "page": page, "pageSize": page_size}


@router.get("/versions/{version_id}/elements/{element_id}", response_model=IFCElementOut)
def element_detail(project_id: uuid.UUID, version_id: uuid.UUID, element_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    item = db.query(IFCElement).filter(IFCElement.id == element_id, IFCElement.version_id == version_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC element not found")
    return item


@router.get("/versions/{version_id}/search", response_model=IFCPaged)
def search_version(project_id: uuid.UUID, version_id: uuid.UUID, q: str = Query(..., min_length=1, max_length=200), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return elements(project_id, version_id, q=q, page=page, page_size=page_size, db=db, current_user=current_user)


@router.get("/versions/{version_id}/project-data")
def version_project_data(project_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); _version(db, project_id, version_id)
    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.version_id == version_id).all()
    counts: dict[str, int] = {}
    for link in links: counts[link.linked_entity_type] = counts.get(link.linked_entity_type, 0) + 1
    return {"linkCounts": counts, "links": [IFCLinkOut.model_validate(x).model_dump(mode="json", by_alias=True) for x in links]}


def _linked_project_data(db: Session, project_id: uuid.UUID, links: list[IFCEntityLink]) -> list[dict]:
    result = []
    for link in links:
        model = _TARGETS.get(link.linked_entity_type)
        target = db.get(model, link.linked_entity_id) if model else None
        if not target or target.project_id != project_id:
            continue
        result.append({
            "link": IFCLinkOut.model_validate(link).model_dump(mode="json", by_alias=True),
            "entity": {"id": str(target.id), "type": link.linked_entity_type, "title": getattr(target, "name", None) or getattr(target, "title", None) or getattr(target, "original_filename", None) or getattr(target, "caption", None), "status": str(getattr(getattr(target, "status", None), "value", getattr(target, "status", "")))},
        })
    return result


@router.get("/spatial/{node_id}/project-data")
def spatial_project_data(project_id: uuid.UUID, node_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    node = db.query(IFCSpatialNode).join(IFCModelVersion, IFCModelVersion.id == IFCSpatialNode.version_id).filter(IFCSpatialNode.id == node_id, IFCModelVersion.project_id == project_id).first()
    if not node: raise HTTPException(status_code=404, detail="IFC spatial node not found")
    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.spatial_node_id == node.id).all()
    return {"spatialNode": IFCSpatialNodeOut.model_validate(node).model_dump(mode="json", by_alias=True), "projectData": _linked_project_data(db, project_id, links)}


@router.get("/elements/{element_id}/project-data")
def element_project_data(project_id: uuid.UUID, element_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    element = db.query(IFCElement).join(IFCModelVersion, IFCModelVersion.id == IFCElement.version_id).filter(IFCElement.id == element_id, IFCModelVersion.project_id == project_id).first()
    if not element: raise HTTPException(status_code=404, detail="IFC element not found")
    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.ifc_element_id == element.id).all()
    return {"element": IFCElementOut.model_validate(element).model_dump(mode="json", by_alias=True), "projectData": _linked_project_data(db, project_id, links)}


@router.post("/comparisons", response_model=IFCComparisonOut, status_code=201)
def create_comparison(project_id: uuid.UUID, payload: IFCComparisonCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "COMPARE")
    if not settings.IFC_COMPARISON_ENABLED:
        raise HTTPException(status_code=503, detail="IFC version comparison is disabled")
    base, target = _version(db, project_id, payload.base_version_id), _version(db, project_id, payload.target_version_id)
    if base.model_group_id != target.model_group_id: raise HTTPException(status_code=400, detail=friendly_ifc_error("IFC_COMPARISON_GROUP_MISMATCH"))
    if base.processing_status not in {"READY", "READY_WITH_WARNINGS"} or target.processing_status not in {"READY", "READY_WITH_WARNINGS"}: raise HTTPException(status_code=409, detail="Both IFC versions must finish processing")
    existing = db.query(IFCComparison).filter(IFCComparison.base_version_id == base.id, IFCComparison.target_version_id == target.id).first()
    if existing: return existing
    item = IFCComparison(project_id=project_id, base_version_id=base.id, target_version_id=target.id, created_by_id=current_user.id)
    db.add(item); db.flush()
    try: return compare_versions(db, item)
    except ValueError as exc: db.rollback(); raise HTTPException(status_code=400, detail=friendly_ifc_error(str(exc))) from exc


@router.get("/comparisons", response_model=list[IFCComparisonOut])
def list_comparisons(project_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); return db.query(IFCComparison).filter(IFCComparison.project_id == project_id).order_by(IFCComparison.created_at.desc()).all()


@router.get("/comparisons/{comparison_id}", response_model=IFCComparisonOut)
def comparison_detail(project_id: uuid.UUID, comparison_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); item = db.query(IFCComparison).filter(IFCComparison.id == comparison_id, IFCComparison.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC comparison not found")
    return item


@router.get("/comparisons/{comparison_id}/changes")
def comparison_changes(project_id: uuid.UUID, comparison_id: uuid.UUID, severity: str | None = None, change_type: str | None = None, discipline: str | None = None, storey: str | None = None, entity_type: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    comparison_detail(project_id, comparison_id, db, current_user)
    query = db.query(IFCChangeRecord).filter(IFCChangeRecord.comparison_id == comparison_id)
    if severity: query = query.filter(IFCChangeRecord.severity == severity.upper())
    if change_type: query = query.filter(IFCChangeRecord.change_type == change_type.upper())
    if discipline: query = query.filter(IFCChangeRecord.discipline == discipline.upper())
    if storey: query = query.filter(IFCChangeRecord.storey == storey)
    rows = query.order_by(IFCChangeRecord.severity.desc(), IFCChangeRecord.created_at).all()
    result = []
    for row in rows:
        element = db.get(IFCElement, row.target_element_id or row.base_element_id)
        if entity_type and (not element or element.entity_type != entity_type):
            continue
        result.append({
            "id": str(row.id), "changeType": row.change_type, "severity": row.severity,
            "discipline": row.discipline, "storey": row.storey, "space": row.space,
            "ifcClass": element.entity_type if element else None, "elementName": element.name if element else None,
            "globalId": element.global_id if element else None, "matchMethod": row.match_method,
            "matchConfidence": row.match_confidence, "propertyChanges": row.property_changes_json,
            "geometryChange": row.geometry_change_json, "locationChange": row.location_change_json,
        })
    return result


@router.get("/comparisons/{comparison_id}/impacts")
def comparison_impacts(project_id: uuid.UUID, comparison_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    comparison_detail(project_id, comparison_id, db, current_user)
    return db.query(IFCImpactSuggestion).filter(IFCImpactSuggestion.comparison_id == comparison_id).order_by(IFCImpactSuggestion.severity.desc()).all()


@router.post("/comparisons/{comparison_id}/analyze-impact")
def analyze_comparison_impact(project_id: uuid.UUID, comparison_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "COMPARE")
    item = db.query(IFCComparison).filter(IFCComparison.id == comparison_id, IFCComparison.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC comparison not found")
    compare_versions(db, item)
    return db.query(IFCImpactSuggestion).filter(IFCImpactSuggestion.comparison_id == item.id).order_by(IFCImpactSuggestion.severity.desc()).all()


@router.patch("/impacts/{impact_id}")
def review_impact(project_id: uuid.UUID, impact_id: uuid.UUID, payload: IFCReviewRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "REVIEW_SUGGESTION")
    item = db.query(IFCImpactSuggestion).join(IFCComparison, IFCComparison.id == IFCImpactSuggestion.comparison_id).filter(IFCImpactSuggestion.id == impact_id, IFCComparison.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC impact suggestion not found")
    target = payload.status.upper()
    if target not in {"ACKNOWLEDGED", "DISMISSED"}: raise HTTPException(status_code=400, detail="Status must be ACKNOWLEDGED or DISMISSED")
    item.status = target; item.reviewed_by_id = current_user.id; item.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action="ifc_impact_reviewed", entity_type="ifc_impact_suggestion", entity_id=item.id, project_id=project_id, details={"status": target, "note": payload.note}); db.commit(); return item


_TARGETS = {
    "TASK": Task, "ISSUE": Issue, "MILESTONE": Milestone,
    "DOCUMENT": Document, "SITE_REPORT": SiteReport,
    "FIELD_SUBMISSION": FieldSubmission, "MEDIA_ASSET": MediaAsset,
}


@router.post("/links", response_model=IFCLinkOut, status_code=201)
def create_link(project_id: uuid.UUID, payload: IFCLinkCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_LINK"); version = _version(db, project_id, payload.version_id)
    target_type = payload.linked_entity_type.upper(); target_model = _TARGETS.get(target_type)
    if not target_model: raise HTTPException(status_code=400, detail="Unsupported project link type")
    target = db.get(target_model, payload.linked_entity_id)
    if not target or target.project_id != project_id: raise HTTPException(status_code=400, detail="Linked entity must belong to this project")
    if payload.ifc_element_id and not db.query(IFCElement.id).filter(IFCElement.id == payload.ifc_element_id, IFCElement.version_id == version.id).first(): raise HTTPException(status_code=400, detail="IFC element must belong to this version")
    if payload.spatial_node_id and not db.query(IFCSpatialNode.id).filter(IFCSpatialNode.id == payload.spatial_node_id, IFCSpatialNode.version_id == version.id).first(): raise HTTPException(status_code=400, detail="Spatial node must belong to this version")
    item = IFCEntityLink(project_id=project_id, version_id=version.id, ifc_element_id=payload.ifc_element_id, spatial_node_id=payload.spatial_node_id, linked_entity_type=target_type, linked_entity_id=payload.linked_entity_id, link_type=payload.link_type.upper(), source="USER", confidence=1.0, confirmed_by_id=current_user.id, confirmed_at=datetime.now(timezone.utc))
    db.add(item); record_audit(db, actor_id=current_user.id, action="ifc_link_created", entity_type="ifc_entity_link", entity_id=item.id, project_id=project_id, details={"targetType": target_type, "targetId": str(payload.linked_entity_id)})
    try: db.commit(); db.refresh(item)
    except IntegrityError as exc: db.rollback(); raise HTTPException(status_code=409, detail="This IFC link already exists") from exc
    return item


@router.get("/links", response_model=list[IFCLinkOut])
def list_links(project_id: uuid.UUID, version_id: uuid.UUID | None = None, linked_entity_type: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); query = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id)
    if version_id: query = query.filter(IFCEntityLink.version_id == version_id)
    if linked_entity_type: query = query.filter(IFCEntityLink.linked_entity_type == linked_entity_type.upper())
    return query.order_by(IFCEntityLink.created_at.desc()).all()


@router.delete("/links/{link_id}")
def delete_link(project_id: uuid.UUID, link_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "MANAGE_LINK"); item = db.query(IFCEntityLink).filter(IFCEntityLink.id == link_id, IFCEntityLink.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC link not found")
    record_audit(db, actor_id=current_user.id, action="ifc_link_deleted", entity_type="ifc_entity_link", entity_id=item.id, project_id=project_id); db.delete(item); db.commit(); return {"message": "IFC link removed"}


@router.get("/suggestions")
def list_suggestions(project_id: uuid.UUID, status: str | None = None, version_id: uuid.UUID | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); query = db.query(IFCSuggestion).filter(IFCSuggestion.project_id == project_id)
    if status: query = query.filter(IFCSuggestion.status == status.upper())
    if version_id: query = query.filter(IFCSuggestion.version_id == version_id)
    rows = query.order_by(IFCSuggestion.created_at.desc()).all()
    result = []
    for item in rows:
        payload = item.payload_json if isinstance(item.payload_json, dict) else {}
        result.append({
            "id": str(item.id), "versionId": str(item.version_id), "suggestionType": item.suggestion_type,
            "payloadJson": payload, "title": str(payload.get("title") or item.suggestion_type.replace("_", " ").title()),
            "discipline": str(payload.get("discipline") or "UNCLASSIFIED"), "priority": str(payload.get("priority") or "MEDIUM"),
            "reason": item.reasoning, "affectedElementCount": int(payload.get("elementCount") or len(payload.get("relatedGlobalIds") or [])),
            "expectedBenefit": str(payload.get("expectedBenefit") or "Provides a reviewable project action based on extracted IFC data."),
            "recommendedAction": str(payload.get("recommendedAction") or "Review the source evidence before accepting this suggestion."),
            "sourceFinding": str(payload.get("sourceFinding") or payload.get("reason") or "IFC model analysis"),
            "confidence": item.confidence, "status": item.status, "aiInferred": False, "createdAt": item.created_at,
        })
    return result


def _create_task_from_suggestion(db: Session, current_user: User, project_id: uuid.UUID, item: IFCSuggestion, edited_payload: dict | None = None) -> Task:
    if not _is_project_manager(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can accept an IFC task suggestion")
    data = {**item.payload_json, **(edited_payload or {})}
    title = str(data.get("title") or "").strip()
    if not title: raise HTTPException(status_code=400, detail="Accepted task suggestions require a title")
    task = Task(
        project_id=project_id, task_code=_next_task_code(db, project_id), name=title,
        description=data.get("description") or item.reasoning, discipline=data.get("discipline"),
        priority=TaskPriority.MEDIUM, status=TaskStatus.BACKLOG, created_by_id=current_user.id,
        progress_percentage=0, review_required=True,
        voice_evidence_requirements=data.get("suggestedEvidenceRequirements") or {},
    )
    db.add(task); db.flush(); item.payload_json = data
    item.applied_entity_type = "TASK"; item.applied_entity_id = task.id
    record_audit(db, actor_id=current_user.id, action="created_from_ifc_suggestion", entity_type="task", entity_id=task.id, project_id=project_id, details={"suggestionId": str(item.id)})
    return task


def _create_milestone_from_suggestion(db: Session, current_user: User, project_id: uuid.UUID, item: IFCSuggestion, edited_payload: dict | None = None) -> Milestone:
    if not _is_project_manager(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Only the assigned Project Manager can accept an IFC milestone suggestion")
    data = {**item.payload_json, **(edited_payload or {})}
    title = str(data.get("title") or "").strip()
    try:
        planned_date = date.fromisoformat(str(data.get("plannedDate") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Set a planned date before accepting this milestone suggestion") from exc
    if not title: raise HTTPException(status_code=400, detail="Accepted milestone suggestions require a title")
    milestone = Milestone(project_id=project_id, milestone_code=_next_milestone_code(db, project_id), name=title, description=data.get("description") or item.reasoning, planned_date=planned_date, created_by_id=current_user.id)
    db.add(milestone); db.flush(); item.payload_json = data
    item.applied_entity_type = "MILESTONE"; item.applied_entity_id = milestone.id
    record_audit(db, actor_id=current_user.id, action="created_from_ifc_suggestion", entity_type="milestone", entity_id=milestone.id, project_id=project_id, details={"suggestionId": str(item.id)})
    return milestone


@router.patch("/suggestions/{suggestion_id}")
def review_suggestion(project_id: uuid.UUID, suggestion_id: uuid.UUID, payload: IFCReviewRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "REVIEW_SUGGESTION")
    item = db.query(IFCSuggestion).filter(IFCSuggestion.id == suggestion_id, IFCSuggestion.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC suggestion not found")
    target = payload.status.upper()
    if target not in {"ACCEPTED", "REJECTED"}: raise HTTPException(status_code=400, detail="Status must be ACCEPTED or REJECTED")
    if item.status != "PENDING": raise HTTPException(status_code=409, detail="This suggestion has already been reviewed")
    if target == "ACCEPTED" and item.suggestion_type == "CREATE_TASK":
        _create_task_from_suggestion(db, current_user, project_id, item, payload.edited_payload)
    elif target == "ACCEPTED" and item.suggestion_type == "CREATE_MILESTONE":
        _create_milestone_from_suggestion(db, current_user, project_id, item, payload.edited_payload)
    elif target == "ACCEPTED":
        raise HTTPException(status_code=400, detail="This suggestion type cannot be applied automatically")
    item.status = target; item.reviewed_by_id = current_user.id; item.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action=f"ifc_suggestion_{target.lower()}", entity_type="ifc_suggestion", entity_id=item.id, project_id=project_id, details={"note": payload.note, "appliedEntityId": str(item.applied_entity_id) if item.applied_entity_id else None})
    db.commit(); db.refresh(item); return item


@router.post("/suggestions/{suggestion_id}/accept")
def accept_suggestion(project_id: uuid.UUID, suggestion_id: uuid.UUID, payload: IFCReviewRequest | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    request = payload or IFCReviewRequest(status="ACCEPTED")
    request.status = "ACCEPTED"
    return review_suggestion(project_id, suggestion_id, request, db, current_user)


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(project_id: uuid.UUID, suggestion_id: uuid.UUID, payload: IFCReviewRequest | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    request = payload or IFCReviewRequest(status="REJECTED")
    request.status = "REJECTED"
    return review_suggestion(project_id, suggestion_id, request, db, current_user)


@router.post("/suggestions/bulk-review")
def bulk_review_suggestions(project_id: uuid.UUID, payload: IFCBulkReview, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "REVIEW_SUGGESTION")
    target = payload.status.upper()
    if target not in {"ACCEPTED", "REJECTED"}: raise HTTPException(status_code=400, detail="Status must be ACCEPTED or REJECTED")
    if len(payload.suggestion_ids) != len(set(payload.suggestion_ids)): raise HTTPException(status_code=409, detail="Duplicate suggestion IDs are not allowed")
    items = db.query(IFCSuggestion).filter(IFCSuggestion.project_id == project_id, IFCSuggestion.id.in_(payload.suggestion_ids)).with_for_update().all()
    if len(items) != len(payload.suggestion_ids): raise HTTPException(status_code=404, detail="One or more IFC suggestions do not exist in this project")
    if any(item.status != "PENDING" for item in items): raise HTTPException(status_code=409, detail="One or more IFC suggestions have already been reviewed")
    for item in items:
        if target == "ACCEPTED":
            if item.suggestion_type != "CREATE_TASK": raise HTTPException(status_code=400, detail="This suggestion type requires individual editing before acceptance")
            _create_task_from_suggestion(db, current_user, project_id, item)
        item.status = target; item.reviewed_by_id = current_user.id; item.reviewed_at = datetime.now(timezone.utc)
        record_audit(db, actor_id=current_user.id, action=f"ifc_suggestion_{target.lower()}", entity_type="ifc_suggestion", entity_id=item.id, project_id=project_id, details={"bulk": True, "note": payload.note})
    db.commit(); return {"reviewed": len(items), "status": target}


@router.get("/findings")
def list_findings(project_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); query = db.query(IFCCoordinationFinding).filter(IFCCoordinationFinding.project_id == project_id)
    if status: query = query.filter(IFCCoordinationFinding.status == status.upper())
    rows = query.order_by(IFCCoordinationFinding.severity.desc(), IFCCoordinationFinding.created_at.desc()).all()
    grouped: dict[tuple, dict] = {}
    for item in rows:
        evidence = item.geometry_evidence_json if isinstance(item.geometry_evidence_json, dict) else {}
        key = (item.version_id, item.finding_type, item.status)
        element_ids = evidence.get("elementIds") if isinstance(evidence.get("elementIds"), list) else [str(item.element_a_id)]
        if item.element_b_id:
            element_ids.append(str(item.element_b_id))
        if key not in grouped:
            grouped[key] = {
                "id": str(item.id), "versionId": str(item.version_id), "findingType": item.finding_type,
                "severity": item.severity, "title": item.title, "description": item.description,
                "discipline": ", ".join(item.affected_disciplines_json or []) or "Unclassified",
                "disciplines": item.affected_disciplines_json or [], "status": item.status,
                "ifcRule": evidence.get("rule") or item.finding_type,
                "whyItMatters": evidence.get("whyItMatters") or "This may reduce model reliability for coordination workflows.",
                "recommendedAction": evidence.get("recommendedAction") or "Review the affected elements in the source model.",
                "affectedElementIds": [], "createdAt": item.created_at,
            }
        grouped[key]["affectedElementIds"].extend(element_ids)
    result = []
    for value in grouped.values():
        value["affectedElementIds"] = list(dict.fromkeys(value["affectedElementIds"]))
        value["affectedElementCount"] = len(value["affectedElementIds"])
        result.append(value)
    return result


@router.get("/findings/{finding_id}")
def get_finding(project_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW"); item = db.query(IFCCoordinationFinding).filter(IFCCoordinationFinding.id == finding_id, IFCCoordinationFinding.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC finding not found")
    return item


@router.post("/findings/{finding_id}/create-issue", status_code=201)
def finding_to_issue(project_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "REVIEW_FINDING")
    if current_user.role not in {UserRole.PROJECT_MANAGER, UserRole.ENGINEER}:
        raise HTTPException(status_code=403, detail="This role cannot create an official issue from an IFC finding")
    finding = db.query(IFCCoordinationFinding).filter(IFCCoordinationFinding.id == finding_id, IFCCoordinationFinding.project_id == project_id).first()
    if not finding: raise HTTPException(status_code=404, detail="IFC finding not found")
    if finding.status != "PENDING": raise HTTPException(status_code=409, detail="This finding has already been reviewed")
    severity = IssueSeverity.HIGH if finding.severity in {"HIGH", "CRITICAL"} else IssueSeverity.MEDIUM
    issue = Issue(project_id=project_id, title=finding.title, description=f"{finding.description}\n\nIFC evidence: finding {finding.id}", category="IFC_COORDINATION", severity=severity, status=IssueStatus.OPEN, raised_by_id=current_user.id, affects_schedule=finding.severity in {"HIGH", "CRITICAL"})
    db.add(issue); db.flush()
    db.add(IFCEntityLink(project_id=project_id, version_id=finding.version_id, ifc_element_id=finding.element_a_id, linked_entity_type="ISSUE", linked_entity_id=issue.id, link_type="SOURCE_FINDING", source="USER", confidence=1, confirmed_by_id=current_user.id, confirmed_at=datetime.now(timezone.utc)))
    finding.status = "ISSUE_CREATED"; finding.reviewed_by_id = current_user.id; finding.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action="ifc_finding_issue_created", entity_type="issue", entity_id=issue.id, project_id=project_id, details={"findingId": str(finding.id)}); db.commit(); db.refresh(issue); return {"id": issue.id, "title": issue.title, "status": issue.status}


@router.patch("/findings/{finding_id}")
def review_finding(project_id: uuid.UUID, finding_id: uuid.UUID, payload: IFCReviewRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "REVIEW_FINDING"); item = db.query(IFCCoordinationFinding).filter(IFCCoordinationFinding.id == finding_id, IFCCoordinationFinding.project_id == project_id).first()
    if not item: raise HTTPException(status_code=404, detail="IFC finding not found")
    target = payload.status.upper()
    if target not in {"ACKNOWLEDGED", "IGNORED", "FALSE_POSITIVE"}: raise HTTPException(status_code=400, detail="Unsupported finding review status")
    item.status = target; item.false_positive = target == "FALSE_POSITIVE"; item.reviewed_by_id = current_user.id; item.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, actor_id=current_user.id, action="ifc_finding_reviewed", entity_type="ifc_coordination_finding", entity_id=item.id, project_id=project_id, details={"status": target, "note": payload.note}); db.commit(); return item


@router.post("/findings/{finding_id}/ignore")
def ignore_finding(project_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return review_finding(project_id, finding_id, IFCReviewRequest(status="IGNORED"), db, current_user)


@router.post("/findings/{finding_id}/mark-false-positive")
def mark_finding_false_positive(project_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return review_finding(project_id, finding_id, IFCReviewRequest(status="FALSE_POSITIVE"), db, current_user)


@router.get("/storeys/{storey_id}/project-data")
def storey_project_data(project_id: uuid.UUID, storey_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return spatial_project_data(project_id, storey_id, db, current_user)


@router.get("/spaces/{space_id}/project-data")
def space_project_data(project_id: uuid.UUID, space_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return spatial_project_data(project_id, space_id, db, current_user)


@router.get("/processing-jobs")
def processing_jobs(project_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _require(db, current_user, project_id, "VIEW")
    return db.query(IFCProcessingJob).join(IFCModelVersion, IFCModelVersion.id == IFCProcessingJob.version_id).filter(IFCModelVersion.project_id == project_id).order_by(IFCProcessingJob.created_at.desc()).limit(100).all()
