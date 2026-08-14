from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.ifc import AIInsight, IFCElement, IFCModelVersion, IFCSpatialNode
from app.models.project import Project
from app.models.task import Task


GENERIC_NAME_TOKENS = {
    "project", "model", "building", "construction", "ifc", "new", "the",
    "مشروع", "مبنى", "نموذج", "انشاء", "الانشاءات",
}
ELEMENT_TERMS = {
    "WINDOW": ({"window", "windows", "glazing", "نافذة", "نوافذ", "زجاج"}, {"IfcWindow"}),
    "DOOR": ({"door", "doors", "باب", "ابواب", "أبواب"}, {"IfcDoor"}),
    "WALL": ({"wall", "walls", "partition", "جدار", "حوائط", "قاطع"}, {"IfcWall", "IfcWallStandardCase"}),
    "COLUMN": ({"column", "columns", "عمود", "اعمدة", "أعمدة"}, {"IfcColumn"}),
    "SLAB": ({"slab", "slabs", "بلاطة", "بلاطات"}, {"IfcSlab"}),
    "BEAM": ({"beam", "beams", "كمرة", "كمرات"}, {"IfcBeam"}),
}

# A discipline is "present in the model" only when the IFC exposes one of its
# characteristic classes. Absence of the class next to real scheduled work in
# that discipline is the strongest deterministic mismatch signal available.
DISCIPLINE_TERMS: dict[str, tuple[set[str], set[str], str]] = {
    "ELECTRICAL": (
        {"electrical", "electric", "wiring", "cable", "cabling", "socket", "sockets", "outlet",
         "outlets", "switchboard", "switchgear", "conduit", "lighting", "luminaire", "busbar",
         "distribution board", "كهرباء", "كهربائية", "تمديدات", "انارة", "إنارة", "مقبس", "كابل"},
        {"IfcCableCarrierSegment", "IfcCableCarrierFitting", "IfcCableSegment", "IfcCableFitting",
         "IfcElectricAppliance", "IfcElectricDistributionBoard", "IfcElectricGenerator",
         "IfcElectricMotor", "IfcElectricFlowStorageDevice", "IfcLightFixture", "IfcOutlet",
         "IfcSwitchingDevice", "IfcJunctionBox", "IfcProtectiveDevice", "IfcTransformer"},
        "electrical installation",
    ),
    "MECHANICAL_HVAC": (
        {"hvac", "duct", "ducting", "ductwork", "air handling", "ahu", "chiller", "fan coil",
         "ventilation", "air conditioning", "diffuser", "تكييف", "تهوية", "مجاري هواء"},
        {"IfcDuctSegment", "IfcDuctFitting", "IfcAirTerminal", "IfcAirTerminalBox",
         "IfcAirToAirHeatRecovery", "IfcChiller", "IfcCoil", "IfcFan", "IfcBoiler",
         "IfcCompressor", "IfcCondenser", "IfcCooledBeam", "IfcCoolingTower", "IfcDamper",
         "IfcUnitaryEquipment", "IfcSpaceHeater"},
        "mechanical / HVAC installation",
    ),
    "PLUMBING": (
        {"plumbing", "sanitary", "drainage", "sewer", "water supply", "pipe", "piping",
         "pipework", "basin", "washbasin", "toilet fixture", "wc fixture", "sink", "tap",
         "صرف", "سباكة", "مواسير", "انابيب", "أنابيب", "تمديدات صحية"},
        {"IfcPipeSegment", "IfcPipeFitting", "IfcSanitaryTerminal", "IfcFlowMeter",
         "IfcInterceptor", "IfcPump", "IfcTank", "IfcValve", "IfcWasteTerminal"},
        "plumbing / sanitary installation",
    ),
    "FIRE_PROTECTION": (
        {"sprinkler", "fire alarm", "fire fighting", "firefighting", "fire suppression",
         "smoke detector", "hose reel", "اطفاء", "إطفاء", "انذار", "إنذار", "حريق"},
        {"IfcFireSuppressionTerminal", "IfcAlarm", "IfcSensor", "IfcProtectiveDeviceTrippingUnit"},
        "fire protection installation",
    ),
    "STRUCTURAL": (
        {"reinforcement", "rebar", "formwork", "concrete pour", "footing", "foundation",
         "pile", "shoring", "خرسانة", "حديد تسليح", "اساسات", "أساسات", "قواعد"},
        {"IfcFooting", "IfcPile", "IfcReinforcingBar", "IfcReinforcingMesh", "IfcBeam",
         "IfcColumn", "IfcSlab", "IfcMember", "IfcPlate"},
        "structural works",
    ),
}

# Values stored in Task.discipline mapped onto the discipline checks above.
DISCIPLINE_FIELD_MAP: dict[str, str] = {
    "electrical": "ELECTRICAL",
    "mechanical": "MECHANICAL_HVAC",
    "hvac": "MECHANICAL_HVAC",
    "plumbing": "PLUMBING",
    "sanitary": "PLUMBING",
    "fire": "FIRE_PROTECTION",
    "fire protection": "FIRE_PROTECTION",
    "structural": "STRUCTURAL",
}

# Storey-count bands implied by a project type, used only to warn about a model
# that is obviously a different kind of asset than the project describes.
SCALE_EXPECTATIONS: dict[str, tuple[int, int]] = {
    "villa": (1, 4), "residential villa": (1, 4), "house": (1, 4), "bungalow": (1, 2),
    "tower": (6, 200), "high rise": (8, 200), "highrise": (8, 200), "skyscraper": (15, 200),
}


@dataclass(frozen=True)
class CompatibilityFinding:
    code: str
    category: str
    severity: str
    confidence: float
    title: str
    description: str
    reason: str
    recommended_action: str
    evidence: dict
    affected: dict
    #: Family name for translation. Defaults to the code, which is already
    #: stable for findings whose subject does not vary.
    message_key: str | None = None
    #: The varying facts, so the same statement can be composed in any
    #: language. Defaults to the evidence, which already holds them.
    params: dict | None = None


def _normalize(value: str | None) -> str:
    return " ".join(re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE))


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    """Whole-phrase match on already-normalized text, so 'cable' never matches 'cables tray x'."""
    if not normalized_text or not phrase:
        return False
    return bool(re.search(rf"(?<![\w]){re.escape(phrase)}(?![\w])", normalized_text, flags=re.UNICODE))


def _tokens(value: str | None) -> set[str]:
    return {part for part in _normalize(value).split() if len(part) > 1 and part not in GENERIC_NAME_TOKENS}


def _name_score(left: str | None, right: str | None) -> float | None:
    if not left or not right:
        return None
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return None
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return round(max(overlap, SequenceMatcher(None, a, b).ratio()), 3)


def _references(text: str) -> tuple[set[str], set[str]]:
    normalized = _normalize(text)
    floors = set()
    rooms = set()
    for match in re.finditer(r"\b(?:floor|level|storey|story|الطابق|طابق|الدور)\s*[-:#]?\s*([a-z]?\d+)\b", normalized):
        floors.add(match.group(1).casefold())
    for match in re.finditer(r"\b(?:basement|بدروم|القبو|قبو)\s*[-:#]?\s*([a-z]?\d+)?\b", normalized):
        floors.add(f"b{(match.group(1) or '1').lstrip('b')}")
    for match in re.finditer(r"\b(?:room|space|غرفة)\s*[-:#]?\s*([a-z]?\d+[a-z]?)\b", normalized):
        rooms.add(match.group(1).casefold())
    return floors, rooms


def _spatial_keys(names: list[str], kind: str) -> set[str]:
    values = set()
    for name in names:
        normalized = _normalize(name)
        patterns = (
            [r"\b(?:floor|level|storey|story|الطابق|طابق|الدور)\s*[-:#]?\s*([a-z]?\d+)\b", r"\bb\s*([0-9]+)\b"]
            if kind == "floor"
            else [r"\b(?:room|space|غرفة)?\s*[-:#]?\s*([a-z]?\d+[a-z]?)\b"]
        )
        for pattern in patterns:
            for match in re.finditer(pattern, normalized):
                value = match.group(1).casefold()
                values.add(f"b{value}" if pattern.startswith(r"\bb") else value)
    return values


def evaluate_ifc_compatibility(
    *,
    project_name: str,
    project_type: str | None,
    summary: dict,
    storey_names: list[str],
    space_names: list[str],
    element_types: set[str],
    task_texts: list[tuple[str, str]],
    previous_summary: dict | None = None,
    scheduled_tasks: list[dict] | None = None,
) -> list[CompatibilityFinding]:
    findings: list[CompatibilityFinding] = []
    overview = summary.get("projectOverview") or {}
    ifc_names = [overview.get("projectName"), overview.get("buildingName"), overview.get("siteName")]
    scores = {name: _name_score(project_name, name) for name in ifc_names if name}
    usable_scores = [score for score in scores.values() if score is not None]
    if not usable_scores:
        findings.append(CompatibilityFinding(
            "IFC_PROJECT_IDENTITY_MISSING", "MISSING_INFORMATION", "WARNING", .99,
            "IFC project identity metadata is missing",
            "The model does not expose a usable project, building, or site name for compatibility verification.",
            "No source identity value was available for a deterministic comparison.",
            "Confirm the model identity and export metadata before treating this revision as project-compatible.",
            {"platformProjectName": project_name, "ifcNames": ifc_names}, {},
        ))
    elif max(usable_scores) < .45:
        best = max(usable_scores)
        severity = "CRITICAL" if best < .25 else "HIGH"
        findings.append(CompatibilityFinding(
            "IFC_PROJECT_NAME_MISMATCH", "PROJECT_MODEL_MISMATCH", severity, round(1 - best, 3),
            "IFC identity appears inconsistent with this project",
            "The IFC project/building/site names have low similarity to the platform project name.",
            "Normalized token overlap and string similarity were below the compatibility threshold.",
            "Verify that the correct model was uploaded before activation or downstream coordination.",
            {"platformProjectName": project_name, "ifcNameScores": scores}, {"names": list(scores)},
            message_key="IFC_PROJECT_NAME_MISMATCH",
            params={"projectName": project_name},
        ))

    asset = ((summary.get("assetType") or {}).get("value") or overview.get("buildingType"))
    normalized_project_type = _normalize(project_type)
    normalized_asset = _normalize(asset)
    if normalized_project_type and normalized_asset and normalized_asset != "unknown":
        if not (_tokens(normalized_project_type) & _tokens(normalized_asset)) and _name_score(normalized_project_type, normalized_asset) < .45:
            findings.append(CompatibilityFinding(
                "IFC_ASSET_TYPE_MISMATCH", "PROJECT_MODEL_MISMATCH", "HIGH", .9,
                "IFC asset type differs from project configuration",
                f'The platform project type is “{project_type}”, while the IFC is classified as “{asset}”.',
                "The locally derived IFC asset classification does not match the configured project type.",
                "Confirm the intended asset type and review whether this model belongs to another project.",
                {"projectType": project_type, "ifcAssetType": asset}, {},
            ))

    task_floors, task_rooms = set(), set()
    referenced_terms: dict[str, list[str]] = {key: [] for key in ELEMENT_TERMS}
    for task_id, text in task_texts:
        floors, rooms = _references(text)
        task_floors.update(floors)
        task_rooms.update(rooms)
        words = set(_normalize(text).split())
        for category, (terms, _) in ELEMENT_TERMS.items():
            if words & terms:
                referenced_terms[category].append(task_id)
    model_floors = _spatial_keys(storey_names, "floor")
    model_rooms = _spatial_keys(space_names, "room")
    missing_floors = sorted(task_floors - model_floors)
    missing_rooms = sorted(task_rooms - model_rooms)
    if missing_floors:
        findings.append(CompatibilityFinding(
            "TASK_FLOOR_NOT_IN_IFC", "TASK_MODEL_MISMATCH", "HIGH", .98,
            "Task-referenced floors are missing from the IFC",
            f"Project tasks reference {', '.join(missing_floors)}, but those floor identifiers were not found in model storeys.",
            "Explicit task floor references were compared with extracted IFC storey names.",
            "Review task locations and the uploaded model hierarchy before applying model-based validation.",
            {"taskFloors": sorted(task_floors), "modelFloors": sorted(model_floors), "missingFloors": missing_floors},
            {"storeys": storey_names},
        ))
    if missing_rooms:
        findings.append(CompatibilityFinding(
            "TASK_ROOM_NOT_IN_IFC", "TASK_MODEL_MISMATCH", "HIGH", .98,
            "Task-referenced rooms are missing from the IFC",
            f"Project tasks reference room(s) {', '.join(missing_rooms)}, but those identifiers were not found in model spaces.",
            "Explicit task room references were compared with extracted IFC space names.",
            "Confirm room numbering and model revision coverage.",
            {"taskRooms": sorted(task_rooms), "modelRooms": sorted(model_rooms), "missingRooms": missing_rooms},
            {"spaces": space_names[:200]},
        ))
    for category, task_ids in referenced_terms.items():
        if not task_ids:
            continue
        expected_classes = ELEMENT_TERMS[category][1]
        if not (element_types & expected_classes):
            findings.append(CompatibilityFinding(
                f"TASK_{category}_ELEMENTS_MISSING", "TASK_MODEL_MISMATCH", "HIGH", .96,
                f"Tasks reference {category.lower()} work but the IFC contains no matching elements",
                f"{len(task_ids)} task(s) reference {category.lower()} scope; no {', '.join(sorted(expected_classes))} elements were extracted.",
                "Task terminology was compared with deterministic IFC entity classes.",
                "Verify IFC export scope/classification and confirm that the correct discipline model was uploaded.",
                {"expectedIfcClasses": sorted(expected_classes), "modelElementTypes": sorted(element_types), "taskIds": task_ids},
                {"tasks": task_ids, "categories": [category]},
                message_key="TASK_ELEMENTS_MISSING",
                params={"category": category.lower(), "taskCount": len(task_ids),
                        "expectedClasses": ", ".join(sorted(expected_classes))},
            ))

    # ── Discipline coverage ────────────────────────────────────────────────
    # Scheduled work in a discipline that the model does not represent at all is
    # the mismatch that a plain element count never surfaces.
    normalized_tasks = [(task_id, _normalize(text)) for task_id, text in task_texts]
    # An explicitly recorded task discipline is stronger evidence than wording.
    declared: dict[str, list[str]] = {}
    for item in (scheduled_tasks or []):
        key = DISCIPLINE_FIELD_MAP.get(_normalize(item.get("discipline")))
        if key:
            declared.setdefault(key, []).append(item["taskId"])
    for discipline, (terms, ifc_classes, label) in DISCIPLINE_TERMS.items():
        matching = [
            (task_id, next(term for term in sorted(terms) if _contains_phrase(text, term)))
            for task_id, text in normalized_tasks
            if any(_contains_phrase(text, term) for term in terms)
        ]
        matched_ids = {task_id for task_id, _ in matching}
        for task_id in declared.get(discipline, []):
            if task_id not in matched_ids:
                matching.append((task_id, "task.discipline field"))
        if not matching:
            continue
        present = element_types & ifc_classes
        if present:
            continue
        severity = "CRITICAL" if len(matching) >= 3 else "HIGH"
        findings.append(CompatibilityFinding(
            f"DISCIPLINE_{discipline}_NOT_IN_IFC", "DISCIPLINE_MISMATCH", severity,
            round(min(.99, .85 + .03 * len(matching)), 3),
            f"{len(matching)} {label} task(s) exist, but the IFC contains no {discipline.replace('_', '/').lower()} elements",
            f"Project tasks describe {label}, while the active model exposes none of the "
            f"characteristic IFC classes for that discipline.",
            "Task wording was matched against a fixed discipline vocabulary and compared with the "
            "IFC entity classes extracted from this revision. Absence of the classes is factual; "
            "the intent behind the task wording is not verified.",
            "Confirm whether the discipline model was omitted from this export, or whether the "
            "wrong model was uploaded for this project.",
            {
                "discipline": discipline,
                "expectedIfcClasses": sorted(ifc_classes),
                "modelElementTypes": sorted(element_types)[:60],
                "matchedTasks": [{"taskId": task_id, "matchedTerm": term} for task_id, term in matching[:20]],
                "matchedTaskCount": len(matching),
            },
            {"tasks": [task_id for task_id, _ in matching], "disciplines": [discipline]},
            message_key="DISCIPLINE_NOT_IN_IFC",
            params={"discipline": discipline.replace("_", "/").lower(), "label": label,
                    "taskCount": len(matching)},
        ))

    # ── Model scale / asset context ────────────────────────────────────────
    storey_count = len(storey_names)
    expectation = next(
        (band for keyword, band in SCALE_EXPECTATIONS.items()
         if _contains_phrase(_normalize(project_type), keyword) or _contains_phrase(_normalize(project_name), keyword)),
        None,
    )
    if expectation and storey_count:
        low, high = expectation
        if not low <= storey_count <= high:
            findings.append(CompatibilityFinding(
                "IFC_MODEL_SCALE_ANOMALY", "PROJECT_MODEL_MISMATCH", "WARNING", .8,
                "Model scale does not match the described project",
                f"The project describes an asset that normally has {low}–{high} storeys, "
                f"while this IFC contains {storey_count}.",
                "Storey count extracted from the IFC was compared with the storey band implied by "
                "the project type/name. This is an assumption based on naming, not a verified requirement.",
                "Confirm the intended building scale, or correct the project type if the model is right.",
                {"projectType": project_type, "projectName": project_name,
                 "expectedStoreyRange": [low, high], "modelStoreys": storey_count,
                 "storeyNames": storey_names[:50], "assumption": "storey band inferred from project naming"},
                {},
            ))

    # ── Scheduled work with no addressable model context ───────────────────
    if scheduled_tasks and storey_names:
        unmappable = []
        for item in scheduled_tasks:
            if not item.get("plannedStart"):
                continue
            floors, rooms = _references(item.get("text") or "")
            if not (floors or rooms):
                continue
            missing_floors_here = sorted(floors - model_floors)
            missing_rooms_here = sorted(rooms - model_rooms)
            if missing_floors_here or missing_rooms_here:
                unmappable.append({
                    "taskId": item["taskId"], "taskCode": item.get("taskCode"),
                    "name": item.get("name"), "plannedStart": item["plannedStart"],
                    "unresolvedFloors": missing_floors_here, "unresolvedRooms": missing_rooms_here,
                })
        if unmappable:
            findings.append(CompatibilityFinding(
                "SCHEDULED_WORK_NOT_MAPPABLE_TO_IFC", "SCHEDULE_MODEL_MISMATCH", "HIGH",
                round(min(.97, .8 + .02 * len(unmappable)), 3),
                "Scheduled work references locations the active model cannot identify",
                f"{len(unmappable)} task(s) with a planned start date reference a floor or room that "
                "matches no storey or space in the active IFC revision.",
                "Floor and room references were extracted from the names and descriptions of tasks that "
                "carry a planned start date, then compared with the IFC storey and space identifiers. "
                "Tasks without an explicit location reference were not evaluated.",
                "Align task locations with the model hierarchy, or upload the revision that contains "
                "these areas, before using the model to validate schedule progress.",
                {"unmappableTasks": unmappable[:20], "unmappableTaskCount": len(unmappable),
                 "modelFloors": sorted(model_floors), "modelRooms": sorted(model_rooms)[:50]},
                {"tasks": [item["taskId"] for item in unmappable]},
            ))

    if previous_summary:
        current_stats = summary.get("mainStatistics") or summary
        previous_stats = previous_summary.get("mainStatistics") or previous_summary
        current_storeys = int(current_stats.get("storeys") or summary.get("storeys") or len(storey_names))
        previous_storeys = int(previous_stats.get("storeys") or previous_summary.get("storeys") or 0)
        current_spaces = int(current_stats.get("spaces") or summary.get("spaces") or len(space_names))
        previous_spaces = int(previous_stats.get("spaces") or previous_summary.get("spaces") or 0)
        current_elements = int(summary.get("elements") or 0)
        previous_elements = int(previous_summary.get("elements") or 0)
        changed = {
            "storeys": {"before": previous_storeys, "after": current_storeys},
            "spaces": {"before": previous_spaces, "after": current_spaces},
            "elements": {"before": previous_elements, "after": current_elements},
        }
        major_storey_change = previous_storeys and abs(current_storeys - previous_storeys) >= max(3, previous_storeys * .5)
        major_space_change = previous_spaces >= 5 and abs(current_spaces - previous_spaces) / previous_spaces >= .7
        major_element_change = previous_elements >= 10 and abs(current_elements - previous_elements) / previous_elements >= .8
        if major_storey_change or major_space_change or major_element_change:
            findings.append(CompatibilityFinding(
                "IFC_MAJOR_REVISION_DRIFT", "IFC_MISMATCH", "HIGH", .99,
                "New IFC revision changes the model structure substantially",
                "Storey, space, or element counts changed beyond deterministic revision-drift thresholds.",
                "The new extracted hierarchy was compared with the previous processed revision.",
                "Review the revision comparison and approved design changes before making this model active.",
                changed, {},
            ))
    return findings


def run_ifc_compatibility(db: Session, version: IFCModelVersion) -> list[CompatibilityFinding]:
    project = db.get(Project, version.project_id)
    if not project:
        return []
    nodes = db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version.id).all()
    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).all()
    tasks = db.query(Task).filter(Task.project_id == version.project_id).all()
    previous = db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == version.project_id,
        IFCModelVersion.id != version.id,
        IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
    ).order_by(IFCModelVersion.created_at.desc()).first()
    findings = evaluate_ifc_compatibility(
        project_name=project.name,
        project_type=project.project_type,
        summary=version.model_summary_json or {},
        storey_names=[node.name for node in nodes if node.node_type == "STOREY"],
        space_names=[node.name for node in nodes if node.node_type == "SPACE"],
        element_types={element.entity_type for element in elements},
        task_texts=[(str(task.id), f"{task.name} {task.description or ''}") for task in tasks],
        previous_summary=previous.model_summary_json if previous else None,
        scheduled_tasks=[
            {
                "taskId": str(task.id),
                "taskCode": task.task_code,
                "name": task.name,
                "discipline": task.discipline,
                "text": f"{task.name} {task.description or ''}",
                "plannedStart": task.planned_start_date.isoformat() if task.planned_start_date else None,
            }
            for task in tasks
        ],
    )
    for finding in findings:
        fingerprint = hashlib.sha256(
            json.dumps(
                {"project": str(project.id), "version": str(version.id), "code": finding.code},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        item = db.query(AIInsight).filter(AIInsight.fingerprint == fingerprint).first()
        payload = asdict(finding)
        if not item:
            item = AIInsight(
                project_id=project.id,
                model_revision_id=version.id,
                fingerprint=fingerprint,
                insight_type=finding.code,
                category=finding.category,
                severity=finding.severity,
                confidence=finding.confidence,
                title=finding.title,
                description=finding.description,
                reason=finding.reason,
                recommended_action=finding.recommended_action,
                evidence_json=finding.evidence,
                affected_json=finding.affected,
                message_key=finding.message_key or finding.code,
                message_params_json=finding.params or finding.evidence,
                source_engine="IFC_COMPATIBILITY_RULES_V1",
                status="OPEN",
            )
            db.add(item)
        elif item.status in {"OPEN", "NEW", "ACKNOWLEDGED", "UNDER_REVIEW"}:
            item.severity = payload["severity"]
            item.confidence = payload["confidence"]
            item.description = payload["description"]
            item.evidence_json = payload["evidence"]
            item.affected_json = payload["affected"]
            item.message_key = finding.message_key or finding.code
            item.message_params_json = finding.params or finding.evidence
    db.flush()
    return findings
