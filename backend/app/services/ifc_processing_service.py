"""Durable IFC processing, comparison, coordination and impact services."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from multiprocessing import get_context
from queue import Empty
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.ifc import (
    IFCChangeRecord, IFCComparison, IFCElement, IFCEntityLink, IFCImpactSuggestion,
    IFCModelVersion, IFCProcessingJob, IFCSpatialNode, IFCSuggestion, IFCCoordinationFinding,
)
from app.models.task import Task
from app.models.notification import Notification
from app.models.project import Project
from app.models.milestone import Milestone
from app.models.enums import NotificationType
from app.services.audit_service import record_audit
from app.services.file_storage import resolve_private_storage_key
from app.services.ifc_parser import IFCParseError, IFCParser, stable_json_hash
from app.services.ifc_geometry_service import generate_geometry
from app.services.ai_insight_engine import run_project_intelligence
from app.services.ifc_compatibility_service import run_ifc_compatibility
from app.services.domain_event_dispatcher import emit_domain_event
from app.services.ifc_policy import friendly_ifc_error
from app.core.config import settings


VERSION_TRANSITIONS = {
    "UPLOADED": {"VALIDATING", "QUEUED", "FAILED", "ARCHIVED"},
    "VALIDATING": {"QUEUED", "FAILED"}, "QUEUED": {"PARSING", "FAILED"},
    "PARSING": {"BUILDING_HIERARCHY", "FAILED"},
    "BUILDING_HIERARCHY": {"EXTRACTING_ELEMENTS", "FAILED"},
    "EXTRACTING_ELEMENTS": {"EXTRACTING_PROPERTIES", "FAILED"},
    "EXTRACTING_PROPERTIES": {"QUALITY_CHECKS", "FAILED"},
    "QUALITY_CHECKS": {"ANALYZING", "FAILED"},
    "ANALYZING": {"READY", "READY_WITH_WARNINGS", "FAILED"},
    "FAILED": {"QUEUED", "ARCHIVED"}, "READY": {"ARCHIVED"},
    "READY_WITH_WARNINGS": {"ARCHIVED", "QUEUED"}, "ARCHIVED": {"READY", "READY_WITH_WARNINGS"},
}


def _parse_worker(path: str, output) -> None:
    try:
        output.put(("ok", IFCParser().parse(resolve_private_storage_key(path))))
    except IFCParseError as exc:
        output.put(("error", str(exc)))
    except Exception:
        output.put(("error", "IFC_PROCESSING_FAILED"))


def parse_with_timeout(storage_key: str):
    """Parse untrusted IFC in an isolated process with a hard wall-clock limit."""
    context = get_context("spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(target=_parse_worker, args=(storage_key, output), daemon=True)
    process.start()
    try:
        kind, value = output.get(timeout=settings.IFC_PARSE_TIMEOUT_SECONDS)
    except Empty as exc:
        process.terminate(); process.join(timeout=5)
        raise IFCParseError("IFC_PARSE_TIMEOUT") from exc
    finally:
        output.close()
    process.join(timeout=5)
    if process.is_alive():
        process.terminate(); process.join(timeout=5)
    if kind != "ok":
        raise IFCParseError(value)
    return value


def transition_version(version: IFCModelVersion, target: str, progress: int) -> None:
    if version.processing_status == target:
        version.processing_progress = progress
        return
    if target not in VERSION_TRANSITIONS.get(version.processing_status, set()):
        raise ValueError(f"Invalid IFC state transition {version.processing_status} -> {target}")
    version.processing_status = target
    version.processing_progress = progress
    version.row_version += 1


def process_version(db: Session, version_id, actor_id=None) -> None:
    version = db.get(IFCModelVersion, version_id)
    if not version or version.processing_status not in {"UPLOADED", "FAILED"}:
        return
    idempotency_key = f"parse-{version.file_hash}"
    existing = db.query(IFCProcessingJob).filter(
        IFCProcessingJob.version_id == version.id,
        IFCProcessingJob.job_type == "PARSE",
        IFCProcessingJob.idempotency_key == idempotency_key,
    ).first()
    if existing and existing.status == "RUNNING":
        return
    if existing and existing.status == "COMPLETED":
        return
    job = existing or IFCProcessingJob(
        version_id=version.id, job_type="PARSE",
        idempotency_key=idempotency_key, status="QUEUED", progress=0,
    )
    if existing:
        job.status = "QUEUED"
        job.progress = 0
        job.started_at = None
        job.completed_at = None
        job.duration_ms = None
        job.failure_code = None
        job.failure_message = None
    else:
        db.add(job)
    transition_version(version, "QUEUED", 5)
    db.commit()
    started = perf_counter()
    try:
        job.status = "RUNNING"; job.started_at = datetime.now(timezone.utc); job.progress = 10
        transition_version(version, "PARSING", 20); db.commit()
        parsed = parse_with_timeout(version.storage_key)
        transition_version(version, "BUILDING_HIERARCHY", 38)
        db.query(IFCElement).filter(IFCElement.version_id == version.id).delete(synchronize_session=False)
        db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version.id).delete(synchronize_session=False)
        db.flush()
        node_by_global: dict[str, IFCSpatialNode] = {}
        pending = list(parsed.nodes)
        for _ in range(len(pending) + 1):
            progressed = False
            for item in list(pending):
                if item.parent_global_id and item.parent_global_id not in node_by_global:
                    continue
                node = IFCSpatialNode(
                    version_id=version.id, global_id=item.global_id, entity_type=item.entity_type,
                    name=item.name, description=item.description,
                    parent_id=node_by_global.get(item.parent_global_id).id if item.parent_global_id in node_by_global else None,
                    node_type=item.node_type, elevation=item.elevation, area=item.area, volume=item.volume,
                    metadata_json=item.metadata,
                )
                db.add(node); db.flush(); node_by_global[item.global_id] = node
                pending.remove(item); progressed = True
            if not pending or not progressed:
                break
        for item in pending:
            node = IFCSpatialNode(
                version_id=version.id, global_id=item.global_id, entity_type=item.entity_type,
                name=item.name, description=item.description, node_type=item.node_type,
                elevation=item.elevation, area=item.area, volume=item.volume,
                metadata_json={**item.metadata, "unassignedParent": item.parent_global_id},
            )
            db.add(node); db.flush(); node_by_global[item.global_id] = node
        transition_version(version, "EXTRACTING_ELEMENTS", 52)
        db.commit()
        batch = []
        for item in parsed.elements:
            batch.append(IFCElement(
                version_id=version.id, global_id=item.global_id, entity_type=item.entity_type,
                name=item.name, description=item.description, object_type=item.object_type,
                predefined_type=item.predefined_type, tag=item.tag,
                storey_node_id=node_by_global.get(item.storey_global_id).id if item.storey_global_id in node_by_global else None,
                space_node_id=node_by_global.get(item.space_global_id).id if item.space_global_id in node_by_global else None,
                building_node_id=node_by_global.get(item.building_global_id).id if item.building_global_id in node_by_global else None,
                discipline=item.discipline, system_name=item.system_name, type_name=item.type_name,
                material_summary=item.material_summary, properties_json=item.properties,
                quantities_json=item.quantities, bounding_box_json=item.bounding_box,
                geometry_hash=item.geometry_hash, placement_hash=item.placement_hash, metadata_json=item.metadata,
            ))
            if len(batch) >= 1000:
                db.add_all(batch); db.flush(); batch = []
        if batch:
            db.add_all(batch)
        db.flush()
        transition_version(version, "EXTRACTING_PROPERTIES", 68)
        db.commit()
        transition_version(version, "QUALITY_CHECKS", 82)
        version.model_summary_json = parsed.summary
        if settings.IFC_COORDINATION_CHECKS_ENABLED:
            _build_coordination_findings(db, version)
        db.commit()
        transition_version(version, "ANALYZING", 92)
        db.commit()
        reviewed_suggestion_keys = {
            (item.suggestion_type, str((item.payload_json or {}).get("title", "")).casefold())
            for item in db.query(IFCSuggestion).filter(
                IFCSuggestion.version_id == version.id, IFCSuggestion.status != "PENDING",
            ).all()
        }
        db.query(IFCSuggestion).filter(IFCSuggestion.version_id == version.id, IFCSuggestion.status == "PENDING").delete(synchronize_session=False)
        for suggestion in parsed.task_suggestions:
            if ("CREATE_TASK", suggestion["title"].casefold()) in reviewed_suggestion_keys:
                continue
            duplicates = db.query(Task).filter(
                Task.project_id == version.project_id,
                Task.name.ilike(f"%{suggestion['title']}%"),
            ).count()
            payload = {**suggestion, "duplicateRisk": duplicates > 0, "existingTaskCount": duplicates}
            db.add(IFCSuggestion(
                project_id=version.project_id, version_id=version.id,
                suggestion_type="CREATE_TASK", payload_json=payload,
                confidence=suggestion["confidence"], reasoning=suggestion["reason"], status="PENDING",
            ))
        structural_count = sum(
            count for entity_type, count in parsed.summary.get("majorElementCategories", {}).items()
            if entity_type in {"IfcFooting", "IfcColumn", "IfcBeam", "IfcSlab", "IfcMember"}
        )
        if structural_count:
            for node in [item for item in parsed.nodes if item.node_type == "STOREY"][:20]:
                title = f"{node.name} structural works complete"
                if ("CREATE_MILESTONE", title.casefold()) in reviewed_suggestion_keys:
                    continue
                duplicates = db.query(Milestone).filter(Milestone.project_id == version.project_id, Milestone.name.ilike(title)).count()
                db.add(IFCSuggestion(
                    project_id=version.project_id, version_id=version.id,
                    suggestion_type="CREATE_MILESTONE",
                    payload_json={"title": title, "description": f"Review completion of structural works associated with IFC storey {node.name}.", "plannedDate": None, "relatedSpatialGlobalId": node.global_id, "duplicateRisk": duplicates > 0},
                    confidence=.68, reasoning=f"The IFC contains a storey named {node.name} and {structural_count} structural elements. Model existence does not indicate physical completion.", status="PENDING",
                ))
        version.ifc_schema = parsed.schema
        version.authoring_application = parsed.authoring_application
        version.entity_count = len(parsed.elements)
        version.model_summary_json = {
            **parsed.summary,
            "revision": version.revision_code,
            "versionType": version.version_type,
            "modelGroup": version.model_group.name,
            "processingStages": [
                {"key": "upload", "label": "Uploading file", "percentage": 5},
                {"key": "validation", "label": "Validating IFC", "percentage": 10},
                {"key": "schema", "label": "Reading IFC schema", "percentage": 20},
                {"key": "hierarchy", "label": "Extracting model hierarchy", "percentage": 38},
                {"key": "elements", "label": "Extracting elements", "percentage": 52},
                {"key": "properties", "label": "Extracting properties and quantities", "percentage": 68},
                {"key": "quality", "label": "Running model-quality checks", "percentage": 82},
                {"key": "summary", "label": "Generating intelligence summary", "percentage": 92},
                {"key": "complete", "label": "Completed", "percentage": 100},
            ],
        }
        compatibility_findings = run_ifc_compatibility(db, version)
        emit_domain_event(
            db,
            project_id=version.project_id,
            event_type="IFC_REVISION_CREATED" if version.parent_version_id else "IFC_UPLOADED",
            entity_type="IFC_MODEL_VERSION",
            entity_id=version.id,
            actor_user_id=actor_id or version.uploaded_by_id,
            payload={
                "compatibilityFindingCodes": [item.code for item in compatibility_findings],
                "elementCount": len(parsed.elements),
            },
            correlation_id=f"ifc:{version.id}",
            idempotency_key=f"IFC_PROCESSED:{version.id}",
        )
        version.model_summary_json = {
            **version.model_summary_json,
            "compatibility": {
                "status": "REVIEW_REQUIRED" if any(
                    item.severity in {"HIGH", "CRITICAL"} for item in compatibility_findings
                ) else "COMPATIBLE_WITH_AVAILABLE_EVIDENCE",
                "findingCount": len(compatibility_findings),
                "highestSeverity": next(
                    (
                        severity
                        for severity in ("CRITICAL", "HIGH", "WARNING", "INFO")
                        if any(item.severity == severity for item in compatibility_findings)
                    ),
                    None,
                ),
                "findingCodes": [item.code for item in compatibility_findings],
            },
        }
        version.asset_type_suggestion = parsed.summary["assetType"]["value"]
        version.asset_type_confidence = parsed.summary["assetType"]["confidence"]
        version.geometry_status = "GEOMETRY_PROCESSING" if settings.IFC_GEOMETRY_ENABLED else "GEOMETRY_NOT_GENERATED"
        version.analysis_status = "READY"
        transition_version(
            version,
            "READY_WITH_WARNINGS"
            if parsed.warnings or compatibility_findings
            else "READY",
            100,
        )
        job.status = "COMPLETED"; job.progress = 100; job.completed_at = datetime.now(timezone.utc)
        job.duration_ms = int((perf_counter() - started) * 1000)
        version.processing_duration_ms = job.duration_ms
        record_audit(db, actor_id=actor_id or version.uploaded_by_id, action="ifc_version_parsed", entity_type="ifc_model_version", entity_id=version.id, project_id=version.project_id, details={"schema": parsed.schema, "elements": len(parsed.elements), "warnings": len(parsed.warnings)})
        recipients = {version.uploaded_by_id}
        project = db.get(Project, version.project_id)
        if project and project.project_manager_id:
            recipients.add(project.project_manager_id)
        for recipient_id in recipients:
            db.add(Notification(
                user_id=recipient_id, title="IFC model ready",
                message=(
                    f'"{version.title}" finished processing with {len(parsed.elements)} extracted elements. '
                    f'{len(compatibility_findings)} compatibility finding(s) require review.'
                    if compatibility_findings
                    else f'"{version.title}" finished processing with {len(parsed.elements)} extracted elements.'
                ),
                type=NotificationType.SYSTEM, project_id=version.project_id,
                related_entity_type="IFC_MODEL_VERSION", related_entity_id=version.id,
            ))
        db.commit()
        # Intelligence and geometry are secondary products. A failure in either
        # must never turn successfully extracted IFC metadata into a failed model.
        try:
            run_project_intelligence(db, version.project_id, version.id)
        except Exception:
            db.rollback()
        if settings.IFC_GEOMETRY_ENABLED:
            generate_geometry(db, version.id)
    except Exception as exc:
        db.rollback(); version = db.get(IFCModelVersion, version_id); job = db.get(IFCProcessingJob, job.id)
        code = str(exc) if isinstance(exc, IFCParseError) else "IFC_PROCESSING_FAILED"
        support_id = uuid4().hex
        version.processing_status = "FAILED"; version.processing_progress = min(max(version.processing_progress, 1), 99)
        version.parsing_error_code = code; version.support_log_id = support_id
        version.parsing_error_message = friendly_ifc_error(code, support_id)["description"]
        if job:
            job.status = "FAILED"; job.failure_code = code; job.failure_message = version.parsing_error_message
            job.completed_at = datetime.now(timezone.utc); job.duration_ms = int((perf_counter() - started) * 1000)
            version.processing_duration_ms = job.duration_ms
        db.add(Notification(
            user_id=version.uploaded_by_id, title="IFC processing needs attention",
            message=f'"{version.title}" could not be processed. Support log: {support_id}.',
            type=NotificationType.SYSTEM, project_id=version.project_id,
            related_entity_type="IFC_MODEL_VERSION", related_entity_id=version.id,
        ))
        db.commit()


def compare_versions(db: Session, comparison: IFCComparison) -> IFCComparison:
    base = db.get(IFCModelVersion, comparison.base_version_id)
    target = db.get(IFCModelVersion, comparison.target_version_id)
    if not base or not target or base.model_group_id != target.model_group_id:
        raise ValueError("IFC_COMPARISON_GROUP_MISMATCH")
    comparison.status = "RUNNING"; comparison.started_at = datetime.now(timezone.utc); db.flush()
    db.query(IFCChangeRecord).filter(IFCChangeRecord.comparison_id == comparison.id).delete(synchronize_session=False)
    base_items = {item.global_id: item for item in db.query(IFCElement).filter(IFCElement.version_id == base.id)}
    target_items = {item.global_id: item for item in db.query(IFCElement).filter(IFCElement.version_id == target.id)}
    changes: list[IFCChangeRecord] = []
    for global_id in sorted(base_items.keys() - target_items.keys()):
        item = base_items[global_id]
        changes.append(_change(comparison.id, item, None, "REMOVED", "GLOBAL_ID", 1.0))
    for global_id in sorted(target_items.keys() - base_items.keys()):
        item = target_items[global_id]
        changes.append(_change(comparison.id, None, item, "ADDED", "GLOBAL_ID", 1.0))
    for global_id in sorted(base_items.keys() & target_items.keys()):
        old, new = base_items[global_id], target_items[global_id]
        property_delta = _dict_delta(old.properties_json, new.properties_json)
        quantity_delta = _dict_delta(old.quantities_json, new.quantities_json)
        location_delta = _location_delta(old, new)
        geometry_changed = old.geometry_hash != new.geometry_hash
        identity_delta = {
            key: {"before": before, "after": after}
            for key, before, after in (
                ("name", old.name, new.name), ("ifcClass", old.entity_type, new.entity_type),
                ("elementType", old.type_name, new.type_name), ("material", old.material_summary, new.material_summary),
                ("system", old.system_name, new.system_name),
                ("classification", (old.metadata_json or {}).get("classifications"), (new.metadata_json or {}).get("classifications")),
            ) if before != after
        }
        if property_delta or quantity_delta or location_delta or geometry_changed or identity_delta:
            record = _change(comparison.id, old, new, "MODIFIED", "GLOBAL_ID", 1.0)
            record.property_changes_json = {"properties": property_delta, "quantities": quantity_delta, "identity": identity_delta}
            record.location_change_json = location_delta
            record.geometry_change_json = {"changed": geometry_changed, "baseHash": old.geometry_hash, "targetHash": new.geometry_hash}
            if location_delta:
                record.change_type = "MOVED"
            record.severity = "HIGH" if old.entity_type in {"IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting"} and (geometry_changed or location_delta) else "MEDIUM"
            changes.append(record)
    db.add_all(changes); db.flush()
    _build_impacts(db, comparison, changes)
    counts = Counter(item.change_type for item in changes)
    disciplines = Counter(item.discipline or "GENERAL" for item in changes)
    unstable_ids = sum(item.global_id.startswith("STEP-") for item in [*base_items.values(), *target_items.values()])
    comparison.summary_json = {
        "total": len(changes), "counts": dict(counts), "disciplineBreakdown": dict(disciplines),
        "evidenceChangeIds": [str(item.id) for item in changes[:200]],
        "comparisonConfidence": "LOW" if unstable_ids else "HIGH", "unstableIdentifierCount": unstable_ids,
        "confidenceMessage": "Some elements have no stable IFC GlobalId; added and removed results may include identity changes." if unstable_ids else "Elements were matched using stable IFC GlobalIds.",
    }
    comparison.status = "READY"; comparison.completed_at = datetime.now(timezone.utc)
    project = db.get(Project, comparison.project_id)
    high_count = sum(item.severity == "HIGH" for item in changes)
    if project and project.project_manager_id and changes:
        db.add(Notification(
            user_id=project.project_manager_id, title="IFC comparison ready",
            message=f"Model comparison found {len(changes)} changes, including {high_count} high-severity changes.",
            type=NotificationType.SYSTEM, project_id=comparison.project_id,
            related_entity_type="IFC_COMPARISON", related_entity_id=comparison.id,
        ))
    record_audit(db, actor_id=comparison.created_by_id, action="ifc_versions_compared", entity_type="ifc_comparison", entity_id=comparison.id, project_id=comparison.project_id, details=comparison.summary_json)
    db.commit(); db.refresh(comparison); return comparison


def _build_coordination_findings(db: Session, version: IFCModelVersion) -> None:
    """Create one evidence-backed aggregate per rule; never infer unsupported engineering claims."""
    reviewed_types = {
        item.finding_type
        for item in db.query(IFCCoordinationFinding).filter(
            IFCCoordinationFinding.version_id == version.id,
            IFCCoordinationFinding.status != "PENDING",
        ).all()
    }
    db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.version_id == version.id,
        IFCCoordinationFinding.status == "PENDING",
    ).delete(synchronize_session=False)
    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).all()
    if not elements:
        return

    def add_finding(finding_type: str, items: list[IFCElement], severity: str, title: str, description: str, why: str, action: str, rule: str, extra: dict | None = None) -> None:
        if not items or finding_type in reviewed_types:
            return
        unique = list({item.id: item for item in items}.values())
        db.add(IFCCoordinationFinding(
            project_id=version.project_id, version_id=version.id, element_a_id=unique[0].id,
            finding_type=finding_type, severity=severity, title=title, description=description,
            geometry_evidence_json={
                "claim": "model-quality", "rule": rule, "whyItMatters": why,
                "recommendedAction": action, "affectedElementCount": len(unique),
                "elementIds": [str(item.id) for item in unique[:500]], **(extra or {}),
            },
            affected_disciplines_json=sorted({item.discipline or "UNCLASSIFIED" for item in unique}),
            affected_tasks_json=[], suggested_recipients_json=[], status="PENDING",
        ))

    tagged = [item for item in elements if item.tag and item.tag.strip()]
    by_tag: dict[str, list[IFCElement]] = {}
    for element in tagged:
        by_tag.setdefault(element.tag.strip().casefold(), []).append(element)
    duplicate_items: list[IFCElement] = []
    duplicate_tags: list[str] = []
    for normalized_tag, values in by_tag.items():
        if len(values) < 2:
            continue
        duplicate_items.extend(values)
        duplicate_tags.append(normalized_tag)
    add_finding(
        "DUPLICATE_TAG", duplicate_items, "MEDIUM", "Duplicate element tags detected",
        "Multiple extracted elements share the same non-empty tag. Duplicate tags may be intentional depending on authoring practices.",
        "Tags are often used to identify elements when linking model data to project records.",
        "Review the affected elements and confirm whether each duplicate is intentional before creating links.",
        "IFC_TAG_UNIQUENESS", {"duplicateTags": duplicate_tags[:100]},
    )

    rules = [
        ("MISSING_NAME", lambda x: not x.metadata_json.get("originalName"), "MEDIUM", "Element names are missing", "Some elements do not contain a name in the source IFC.", "Names make model review and coordination easier.", "Add meaningful names in the authoring model where appropriate.", "IFC_ELEMENT_NAME"),
        ("MISSING_CLASSIFICATION", lambda x: not x.metadata_json.get("classifications"), "LOW", "Element classifications are missing", "Some elements are not linked to a source classification system.", "Classifications support schedules, handover and cross-system coordination.", "Assign an appropriate verified classification in the authoring model.", "IFC_CLASSIFICATION"),
        ("MISSING_MATERIAL", lambda x: not x.material_summary, "MEDIUM", "Element materials are missing", "Material data is not defined for some extracted elements.", "Material information supports quantities, specifications and coordination.", "Define materials in the source IFC where they are relevant.", "IFC_MATERIAL"),
        ("MISSING_PROPERTIES", lambda x: not x.properties_json, "MEDIUM", "Element property sets are missing", "Some elements have no extracted property sets.", "Properties carry important design and asset information.", "Review export settings and include the required property sets.", "IFC_PROPERTY_SETS"),
        ("MISSING_QUANTITIES", lambda x: not x.quantities_json, "LOW", "Element quantities are missing", "Some elements have no extracted base quantities.", "Quantities support model checking and downstream estimating workflows.", "Enable base quantity export or provide verified quantities.", "IFC_QUANTITIES"),
        ("UNASSIGNED_STOREY", lambda x: not x.storey_node_id, "MEDIUM", "Elements are not assigned to storeys", "Some elements are not contained in a building storey.", "Storey assignment is needed for level-based review and coordination.", "Assign affected elements to the correct spatial container.", "IFC_SPATIAL_CONTAINMENT"),
        ("UNCLASSIFIED_PROXY", lambda x: x.entity_type == "IfcBuildingElementProxy", "LOW", "Unclassified proxy elements detected", "Generic proxy elements have limited semantic meaning.", "Clear IFC classes improve discipline organization and model exchange.", "Replace proxies with an appropriate IFC class when the source data supports it.", "IFC_PROXY_CLASS"),
    ]
    for finding_type, predicate, severity, title, description, why, action, rule in rules:
        add_finding(finding_type, [item for item in elements if predicate(item)], severity, title, description, why, action, rule)

    georef = (version.model_summary_json or {}).get("georeferencing") or {}
    if georef.get("status") in {"MISSING", "LOCAL_COORDINATES_ONLY"}:
        add_finding("MISSING_GEOREFERENCING", elements[:1], "MEDIUM", "Georeferencing is incomplete", georef.get("impact") or "The model has no recognized coordinate reference system.", "Reliable map and survey coordination requires an agreed coordinate reference.", "Confirm the project coordinate reference and map conversion with the BIM coordinator or survey team.", "IFC_GEOREFERENCING")


def _change(comparison_id, old, new, change_type, method, confidence):
    item = new or old
    return IFCChangeRecord(
        comparison_id=comparison_id, base_element_id=old.id if old else None,
        target_element_id=new.id if new else None, change_type=change_type,
        match_method=method, match_confidence=confidence, severity="MEDIUM" if change_type == "REMOVED" else "LOW",
        discipline=item.discipline, storey=item.storey.name if item.storey else None,
        space=item.space.name if item.space else None,
    )


def _dict_delta(old: dict, new: dict) -> dict:
    old_hash, new_hash = stable_json_hash(old or {}), stable_json_hash(new or {})
    if old_hash == new_hash:
        return {}
    keys = sorted(set(old or {}) | set(new or {}))[:200]
    return {key: {"before": (old or {}).get(key), "after": (new or {}).get(key)} for key in keys if (old or {}).get(key) != (new or {}).get(key)}


def _location_delta(old, new) -> dict:
    before = {"storeyId": str(old.storey_node_id) if old.storey_node_id else None, "spaceId": str(old.space_node_id) if old.space_node_id else None, "placementHash": old.placement_hash}
    after = {"storeyId": str(new.storey_node_id) if new.storey_node_id else None, "spaceId": str(new.space_node_id) if new.space_node_id else None, "placementHash": new.placement_hash}
    return {"before": before, "after": after} if before != after else {}


def _build_impacts(db: Session, comparison: IFCComparison, changes: list[IFCChangeRecord]) -> None:
    db.query(IFCImpactSuggestion).filter(IFCImpactSuggestion.comparison_id == comparison.id).delete(synchronize_session=False)
    target_version = db.get(IFCModelVersion, comparison.target_version_id)
    for change in changes:
        element_id = change.target_element_id or change.base_element_id
        links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == comparison.project_id, IFCEntityLink.ifc_element_id == element_id).all()
        for link in links:
            severity = "HIGH" if change.severity == "HIGH" else "MEDIUM"
            db.add(IFCImpactSuggestion(
                comparison_id=comparison.id, change_record_id=change.id,
                impact_type=f"MODEL_{change.change_type}", affected_entity_type=link.linked_entity_type,
                affected_entity_id=link.linked_entity_id, severity=severity, confidence=1.0,
                explanation=f"Linked IFC element changed ({change.change_type.lower()}); review the connected {link.linked_entity_type.lower()}.",
                evidence_json={"changeRecordId": str(change.id), "linkId": str(link.id)},
                recommended_action="Review the linked project item before continuing affected work.", status="PENDING",
            ))
        item = db.get(IFCElement, element_id)
        if item and not links:
            tasks = db.query(Task).filter(Task.project_id == comparison.project_id, Task.discipline.ilike(item.discipline or "")).limit(20).all()
            for task in tasks:
                db.add(IFCImpactSuggestion(
                    comparison_id=comparison.id, change_record_id=change.id,
                    impact_type="DISCIPLINE_REVIEW", affected_entity_type="TASK", affected_entity_id=task.id,
                    severity="HIGH" if task.status.value in {"done", "under_review", "in_progress"} else "MEDIUM",
                    confidence=.65, explanation=f"The changed {item.entity_type} shares the {item.discipline} discipline with this task; no direct element link exists.",
                    evidence_json={"changeRecordId": str(change.id), "discipline": item.discipline},
                    recommended_action="Confirm whether this model change affects the task scope.", status="PENDING",
                ))
