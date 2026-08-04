"""Deterministic IFC extraction. Model strings are untrusted data and are never executable."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.ifc_intelligence import classify_element_category, classify_space, measurement


SPATIAL_TYPES = ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace", "IfcZone")
HIERARCHY_TYPES = (*SPATIAL_TYPES, "IfcSystem")
NODE_TYPE = {
    "IfcProject": "PROJECT", "IfcSite": "SITE", "IfcBuilding": "BUILDING",
    "IfcBuildingStorey": "STOREY", "IfcSpace": "SPACE", "IfcZone": "ZONE", "IfcSystem": "SYSTEM",
}
STRUCTURAL = {"IfcBeam", "IfcColumn", "IfcFooting", "IfcPile", "IfcMember", "IfcPlate", "IfcReinforcingBar", "IfcReinforcingMesh", "IfcTendon"}
ARCHITECTURAL = {"IfcWall", "IfcDoor", "IfcWindow", "IfcCurtainWall", "IfcRoof", "IfcStair", "IfcRamp", "IfcRailing", "IfcCovering", "IfcSlab"}
ELECTRICAL = {"IfcCableCarrierFitting", "IfcCableCarrierSegment", "IfcCableFitting", "IfcCableSegment", "IfcElectricAppliance", "IfcElectricDistributionBoard", "IfcElectricFlowStorageDevice", "IfcElectricGenerator", "IfcElectricMotor", "IfcElectricTimeControl", "IfcJunctionBox", "IfcLamp", "IfcLightFixture", "IfcOutlet", "IfcProtectiveDevice", "IfcSwitchingDevice", "IfcTransformer"}
PLUMBING = {"IfcPipeFitting", "IfcPipeSegment", "IfcSanitaryTerminal", "IfcWasteTerminal", "IfcInterceptor", "IfcTank"}
FIRE = {"IfcAlarm", "IfcFireSuppressionTerminal"}
MECHANICAL = {"IfcAirTerminal", "IfcAirTerminalBox", "IfcBoiler", "IfcBurner", "IfcChiller", "IfcCoil", "IfcCompressor", "IfcCondenser", "IfcCooledBeam", "IfcCoolingTower", "IfcDamper", "IfcDuctFitting", "IfcDuctSegment", "IfcEvaporator", "IfcEvaporativeCooler", "IfcFan", "IfcFilter", "IfcFlowMeter", "IfcHeatExchanger", "IfcHumidifier", "IfcPump", "IfcSpaceHeater", "IfcUnitaryEquipment", "IfcValve", "IfcVibrationIsolator"}
SITE_CIVIL = {"IfcGeographicElement", "IfcCivilElement", "IfcEarthworksElement", "IfcPavement", "IfcKerb", "IfcRail", "IfcTrackElement"}
INFRASTRUCTURE = {"IfcAlignment", "IfcBridge", "IfcBridgePart", "IfcRoad", "IfcRailway", "IfcMarineFacility", "IfcFacilityPart"}
FURNITURE_EQUIPMENT = {"IfcFurniture", "IfcFurnishingElement", "IfcSystemFurnitureElement", "IfcMedicalDevice", "IfcTransportElement"}


class IFCParseError(ValueError):
    pass


@dataclass
class ParsedSpatialNode:
    global_id: str
    entity_type: str
    name: str
    description: str | None
    parent_global_id: str | None
    node_type: str
    elevation: float | None = None
    area: float | None = None
    volume: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedElement:
    global_id: str
    entity_type: str
    name: str
    description: str | None
    object_type: str | None
    predefined_type: str | None
    tag: str | None
    storey_global_id: str | None
    space_global_id: str | None
    building_global_id: str | None
    discipline: str
    system_name: str | None
    type_name: str | None
    material_summary: str | None
    properties: dict
    quantities: dict
    bounding_box: dict | None
    geometry_hash: str | None
    placement_hash: str | None
    metadata: dict


@dataclass
class ParsedIFC:
    schema: str
    authoring_application: str | None
    nodes: list[ParsedSpatialNode]
    elements: list[ParsedElement]
    summary: dict
    warnings: list[str]
    task_suggestions: list[dict]


def _clean(value: Any, maximum: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\x00", "").strip()
    return text[:maximum] or None


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return _clean(value, 500)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k)[:200]: _json_safe(v, depth + 1) for k, v in list(value.items())[:500]}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in list(value)[:500]]
    return _clean(value, 1000)


def _global_id(entity: Any) -> str:
    value = _clean(getattr(entity, "GlobalId", None), 64)
    return value or f"STEP-{entity.id()}"


def discipline_for_class(entity_type: str, *, system_name: str | None = None, predefined_type: str | None = None, name: str | None = None, object_type: str | None = None, material: str | None = None) -> tuple[str, float, str, list[str]]:
    evidence = [f"IFC class: {entity_type}"]
    combined = f"{system_name or ''} {predefined_type or ''} {name or ''} {object_type or ''} {material or ''}".casefold()
    if entity_type in FIRE or any(word in combined for word in ("fire", "sprinkler", "smoke", "suppression")):
        return "FIRE_PROTECTION", .92, "IFC class or system meaning indicates fire protection.", [*evidence, *([f"System/type: {combined.strip()}"] if combined.strip() else [])]
    if entity_type in STRUCTURAL:
        return "STRUCTURAL", .95, "The IFC class is normally used for structural components.", evidence
    if entity_type in ARCHITECTURAL:
        return "ARCHITECTURAL", .92, "The IFC class is normally used for architectural components.", evidence
    if entity_type in ELECTRICAL or entity_type.startswith(("IfcCable", "IfcElectric", "IfcLight")):
        return "ELECTRICAL", .95, "The IFC class identifies electrical distribution or equipment.", evidence
    if entity_type in PLUMBING or entity_type.startswith(("IfcPipe", "IfcSanitary")):
        return "PLUMBING", .92, "The IFC class identifies plumbing distribution or fixtures.", evidence
    if entity_type in MECHANICAL or entity_type.startswith(("IfcDuct", "IfcAir")):
        return "MECHANICAL", .92, "The IFC class identifies mechanical services or equipment.", evidence
    if entity_type in SITE_CIVIL:
        return "SITE_CIVIL", .9, "The IFC class identifies a site or civil component.", evidence
    if entity_type in INFRASTRUCTURE:
        return "INFRASTRUCTURE", .95, "The IFC class identifies infrastructure works.", evidence
    if entity_type in FURNITURE_EQUIPMENT:
        return "FURNITURE_EQUIPMENT", .9, "The IFC class identifies furniture or specialist equipment.", evidence
    generic = entity_type.startswith(("IfcFlow", "IfcDistribution")) or entity_type in {"IfcBuildingElementProxy", "IfcProxy"}
    if generic:
        rules = (
            ("FIRE_PROTECTION", ("fire", "sprinkler", "smoke", "suppression")),
            ("MECHANICAL", ("hvac", "air", "duct", "fan", "chiller", "boiler")),
            ("ELECTRICAL", ("electrical", "light", "socket", "outlet", "switch", "cable")),
            ("PLUMBING", ("plumbing", "sanitary", "pipe", "toilet", "basin", "sink")),
        )
        for discipline, words in rules:
            matches = [word for word in words if word in combined]
            if matches:
                source = "; ".join(value for value in (system_name, predefined_type, name, object_type) if value)
                return discipline, .84, "A generic IFC class was normalized from multiple descriptive source attributes.", [*evidence, f"Attributes: {source}", f"Matched: {', '.join(matches)}"]
    return "UNCLASSIFIED", .35, "The source attributes do not provide enough evidence for a reliable discipline.", evidence


def _parent_global_id(entity: Any) -> str | None:
    decomposes = getattr(entity, "Decomposes", None) or []
    for relationship in decomposes:
        parent = getattr(relationship, "RelatingObject", None)
        if parent:
            return _global_id(parent)
    return None


def _spatial_ancestors(entity: Any) -> tuple[str | None, str | None, str | None]:
    storey = space = building = None
    relationships = getattr(entity, "ContainedInStructure", None) or []
    current = getattr(relationships[0], "RelatingStructure", None) if relationships else None
    visited: set[int] = set()
    while current and current.id() not in visited:
        visited.add(current.id())
        kind = current.is_a()
        if kind == "IfcSpace" and not space:
            space = _global_id(current)
        elif kind == "IfcBuildingStorey" and not storey:
            storey = _global_id(current)
        elif kind == "IfcBuilding" and not building:
            building = _global_id(current)
        parent_id = _parent_global_id(current)
        parent = None
        for relationship in getattr(current, "Decomposes", None) or []:
            candidate = getattr(relationship, "RelatingObject", None)
            if candidate and _global_id(candidate) == parent_id:
                parent = candidate
                break
        current = parent
    return storey, space, building


def _placement_hash(entity: Any) -> str | None:
    placement = getattr(entity, "ObjectPlacement", None)
    return hashlib.sha256(str(placement).encode("utf-8", "replace")).hexdigest() if placement else None


def _representation_hash(entity: Any) -> str | None:
    representation = getattr(entity, "Representation", None)
    return hashlib.sha256(str(representation).encode("utf-8", "replace")).hexdigest() if representation else None


def _psets(entity: Any) -> tuple[dict, dict]:
    try:
        from ifcopenshell.util.element import get_psets
        values = _json_safe(get_psets(entity, psets_only=False, qtos_only=False)) or {}
    except Exception:
        values = {}
    properties = {k: v for k, v in values.items() if not str(k).startswith("Qto_")}
    quantities = {k: v for k, v in values.items() if str(k).startswith("Qto_")}
    return properties, quantities


def _type_and_material(entity: Any) -> tuple[str | None, str | None]:
    type_name = material = None
    try:
        from ifcopenshell.util.element import get_material, get_type
        item_type = get_type(entity)
        type_name = _clean(getattr(item_type, "Name", None), 250) if item_type else None
        item_material = get_material(entity)
        material = _clean(getattr(item_material, "Name", None) or item_material, 1000) if item_material else None
    except Exception:
        pass
    return type_name, material


def _systems(entity: Any) -> str | None:
    names: list[str] = []
    for assignment in getattr(entity, "HasAssignments", None) or []:
        group = getattr(assignment, "RelatingGroup", None)
        if group and group.is_a("IfcSystem"):
            value = _clean(getattr(group, "Name", None), 250)
            if value:
                names.append(value)
    return ", ".join(dict.fromkeys(names)) or None


def _classifications(entity: Any) -> list[dict]:
    result: list[dict] = []
    for association in getattr(entity, "HasAssociations", None) or []:
        reference = getattr(association, "RelatingClassification", None)
        if not reference:
            continue
        source = getattr(reference, "ReferencedSource", None)
        item = {
            "system": _clean(getattr(source, "Name", None), 200),
            "code": _clean(getattr(reference, "Identification", None) or getattr(reference, "ItemReference", None), 200),
            "name": _clean(getattr(reference, "Name", None), 300),
            "source": "IFC_SOURCE",
        }
        if any(item.values()):
            result.append(item)
    return result[:50]


def _decimal_degrees(value: Any) -> float | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        degrees, minutes, seconds = float(value[0]), float(value[1]), float(value[2])
        millionths = float(value[3]) / 1_000_000 if len(value) > 3 else 0
        sign = -1 if degrees < 0 else 1
        return sign * (abs(degrees) + minutes / 60 + (seconds + millionths) / 3600)
    except (TypeError, ValueError):
        return None


def _georeferencing(model: Any) -> dict:
    sites = model.by_type("IfcSite")
    site = sites[0] if sites else None
    latitude = _decimal_degrees(getattr(site, "RefLatitude", None)) if site else None
    longitude = _decimal_degrees(getattr(site, "RefLongitude", None)) if site else None
    elevation = getattr(site, "RefElevation", None) if site else None
    crs_items = model.by_type("IfcProjectedCRS") if "IFC2X3" not in str(getattr(model, "schema", "")).upper() else []
    crs = crs_items[0] if crs_items else None
    conversions = model.by_type("IfcMapConversion") if "IFC2X3" not in str(getattr(model, "schema", "")).upper() else []
    conversion = conversions[0] if conversions else None
    crs_name = _clean(getattr(crs, "Name", None), 250) if crs else None
    epsg = None
    if crs_name:
        import re
        match = re.search(r"EPSG\s*[: ]\s*(\d+)", crs_name, re.IGNORECASE)
        epsg = match.group(1) if match else None
    has_crs = bool(crs_name or epsg)
    has_coordinates = latitude is not None and longitude is not None
    has_conversion = conversion is not None
    if has_crs and (has_coordinates or has_conversion):
        status = "FULLY_GEOREFERENCED"
        impact = "The model includes a recognized coordinate reference and positioning information suitable for map coordination."
    elif has_crs or has_coordinates or has_conversion:
        status = "PARTIALLY_GEOREFERENCED"
        impact = "Some positioning data is available, but the coordinate reference or map conversion is incomplete. Confirm it before map coordination."
    elif site:
        status = "LOCAL_COORDINATES_ONLY"
        impact = "Local coordinates are available, but no recognized coordinate reference system was found. The model cannot yet be positioned accurately on a map."
    else:
        status = "MISSING"
        impact = "Georeferencing data is missing. The model cannot be reliably positioned against survey or map data."
    return {
        "status": status, "impact": impact, "coordinateReferenceSystem": crs_name,
        "epsgCode": epsg, "latitude": latitude, "longitude": longitude,
        "easting": getattr(conversion, "Eastings", None) if conversion else None,
        "northing": getattr(conversion, "Northings", None) if conversion else None,
        "elevation": elevation,
        "orthogonalHeight": getattr(conversion, "OrthogonalHeight", None) if conversion else None,
        "mapConversion": _json_safe(conversion.get_info()) if conversion else None,
        "source": "IFC_SOURCE" if (site or crs or conversion) else "MISSING",
    }


def _model_units(model: Any) -> dict:
    result: dict[str, str] = {}
    projects = model.by_type("IfcProject")
    assignment = getattr(projects[0], "UnitsInContext", None) if projects else None
    for unit in getattr(assignment, "Units", None) or []:
        unit_type = _clean(getattr(unit, "UnitType", None), 80)
        name = _clean(getattr(unit, "Name", None), 80)
        prefix = _clean(getattr(unit, "Prefix", None), 40)
        if unit_type and name:
            symbols = {"METRE": "m", "SQUARE_METRE": "m²", "CUBIC_METRE": "m³", "GRAM": "g", "SECOND": "s", "AMPERE": "A", "KELVIN": "K"}
            prefixes = {"MILLI": "m", "CENTI": "c", "DECI": "d", "KILO": "k"}
            result[unit_type] = f"{prefixes.get(prefix or '', prefix or '')}{symbols.get(name, name)}"
    return result


def _completeness(elements: list[ParsedElement]) -> dict:
    total = len(elements)
    def metric(predicate) -> dict:
        count = sum(1 for item in elements if predicate(item))
        return {"count": count, "total": total, "percentage": round(count * 100 / total, 1) if total else 0}
    metrics = {
        "names": metric(lambda x: bool(x.metadata.get("originalName"))),
        "validGlobalIds": metric(lambda x: bool(x.metadata.get("sourceGlobalId"))),
        "properties": metric(lambda x: bool(x.properties)),
        "materials": metric(lambda x: bool(x.material_summary)),
        "quantities": metric(lambda x: bool(x.quantities)),
        "storeyAssignments": metric(lambda x: bool(x.storey_global_id)),
        "systemAssignments": metric(lambda x: bool(x.system_name)),
        "classifications": metric(lambda x: bool(x.metadata.get("classifications"))),
    }
    complete = sum(1 for item in elements if item.metadata.get("completenessStatus") == "COMPLETE")
    metrics["completeElements"] = {"count": complete, "total": total, "percentage": round(complete * 100 / total, 1) if total else 0}
    metrics["missingImportantData"] = {"count": total - complete, "total": total, "percentage": round((total - complete) * 100 / total, 1) if total else 0}
    return metrics


def _main_statistics(elements: list[ParsedElement], nodes: list[ParsedSpatialNode]) -> dict:
    counts = Counter(item.entity_type for item in elements)
    def total(*classes: str) -> int:
        return sum(counts.get(name, 0) for name in classes)
    disciplines = Counter(item.discipline for item in elements)
    normalized = Counter(item.metadata.get("normalizedCategory") for item in elements)
    return {
        "storeys": sum(node.node_type == "STOREY" for node in nodes), "spaces": sum(node.node_type == "SPACE" for node in nodes),
        "walls": normalized["WALL"], "doors": normalized["DOOR"], "windows": normalized["WINDOW"],
        "slabs": normalized["SLAB"], "roofs": normalized["ROOF"], "columns": normalized["COLUMN"], "beams": normalized["BEAM"],
        "stairs": normalized["STAIR"], "ramps": total("IfcRamp", "IfcRampFlight"), "elevators": normalized["ELEVATOR"],
        "furniture": normalized["FURNITURE"],
        "equipment": total("IfcBuildingElementProxy", "IfcDistributionElement", "IfcDistributionControlElement", "IfcEnergyConversionDevice"),
        "structuralElements": disciplines.get("STRUCTURAL", 0), "mechanicalElements": disciplines.get("MECHANICAL", 0),
        "electricalElements": disciplines.get("ELECTRICAL", 0), "plumbingElements": disciplines.get("PLUMBING", 0),
        "fireProtectionElements": disciplines.get("FIRE_PROTECTION", 0), "siteCivilElements": disciplines.get("SITE_CIVIL", 0),
        "infrastructureElements": disciplines.get("INFRASTRUCTURE", 0), "unclassifiedElements": disciplines.get("UNCLASSIFIED", 0),
    }


def _asset_type(nodes: list[ParsedSpatialNode], elements: list[ParsedElement]) -> tuple[str, float, list[str]]:
    buildings = sum(node.node_type == "BUILDING" for node in nodes)
    storeys = sum(node.node_type == "STOREY" for node in nodes)
    names = " ".join(node.name.casefold() for node in nodes if node.node_type in {"BUILDING", "SPACE"})
    evidence = [f"{buildings} building(s)", f"{storeys} storey(s)"]
    keyword_types = {
        "HOSPITAL": ("hospital", "clinic", "ward", "operating"),
        "SCHOOL": ("school", "classroom", "library"),
        "HOTEL": ("hotel", "guest room", "suite"),
        "INDUSTRIAL_BUILDING": ("factory", "plant", "industrial"),
        "WAREHOUSE": ("warehouse", "storage hall"),
        "OFFICE_BUILDING": ("office", "meeting room"),
        "RESIDENTIAL_BUILDING": ("apartment", "bedroom", "living room"),
    }
    if buildings > 1:
        return "MULTI_BUILDING_DEVELOPMENT", .92, evidence
    for label, keywords in keyword_types.items():
        matches = [word for word in keywords if word in names]
        if matches:
            return label, min(.95, .72 + .06 * len(matches)), [*evidence, *matches]
    if buildings == 1 and storeys:
        return "BUILDING", .65, evidence
    if any(element.entity_type in {"IfcBridge", "IfcRoad", "IfcRailway"} for element in elements):
        return "INFRASTRUCTURE_ASSET", .9, evidence
    return "UNKNOWN", .35, evidence


def _task_suggestions(elements: list[ParsedElement]) -> list[dict]:
    counts = Counter(item.entity_type for item in elements)
    mapping = {
        "IfcFooting": ("Foundation installation", "STRUCTURAL"),
        "IfcReinforcingBar": ("Reinforcement installation", "STRUCTURAL"),
        "IfcColumn": ("Column installation", "STRUCTURAL"),
        "IfcBeam": ("Beam installation", "STRUCTURAL"),
        "IfcSlab": ("Slab works", "STRUCTURAL"),
        "IfcDoor": ("Door installation", "ARCHITECTURAL"),
        "IfcWindow": ("Window installation", "ARCHITECTURAL"),
        "IfcDuctSegment": ("HVAC duct installation", "MECHANICAL"),
        "IfcPipeSegment": ("Pipe installation", "PLUMBING"),
        "IfcCableCarrierSegment": ("Electrical containment installation", "ELECTRICAL"),
        "IfcLightFixture": ("Lighting fixture installation", "ELECTRICAL"),
    }
    result = []
    for entity_type, (title, discipline) in mapping.items():
        count = counts.get(entity_type, 0)
        if count:
            related = [item.global_id for item in elements if item.entity_type == entity_type][:200]
            result.append({
                "title": title, "description": f"Install and verify {count} {entity_type} elements.",
                "discipline": discipline, "elementCount": count, "relatedGlobalIds": related,
                "suggestedEvidenceRequirements": {"minimumPhotos": 1},
                "priority": "MEDIUM", "expectedBenefit": "Improves traceability between model scope and project delivery records.",
                "recommendedAction": "Review the affected model elements and confirm whether a project task is required.",
                "sourceFinding": f"{count} {entity_type} elements extracted from the IFC model.",
                "confidence": .82, "reason": f"The IFC contains {count} {entity_type} entities.",
            })
    return result


class IFCParser:
    def parse(self, path: Path) -> ParsedIFC:
        try:
            import ifcopenshell
        except ImportError as exc:
            raise IFCParseError("IFC_PARSER_UNAVAILABLE") from exc
        try:
            model = ifcopenshell.open(str(path))
        except Exception as exc:
            raise IFCParseError("IFC_FILE_CORRUPTED") from exc
        schema = _clean(getattr(model, "schema", None), 40) or "UNKNOWN"
        model_units = _model_units(model)
        all_entities = list(model)
        if len(all_entities) > settings.IFC_MAX_ENTITY_COUNT:
            raise IFCParseError("IFC_ENTITY_LIMIT_EXCEEDED")
        nodes: list[ParsedSpatialNode] = []
        seen_global_ids: set[str] = set()
        warnings: list[str] = []
        for entity_type in HIERARCHY_TYPES:
            for entity in model.by_type(entity_type):
                global_id = _global_id(entity)
                if global_id in seen_global_ids:
                    global_id = f"{global_id}-{entity.id()}"
                    warnings.append(f"Duplicate spatial GlobalId normalized at STEP #{entity.id()}")
                seen_global_ids.add(global_id)
                properties, quantities = _psets(entity)
                space_classification = classify_space([
                    ("IfcSpace.Name", getattr(entity, "Name", None)), ("IfcSpace.LongName", getattr(entity, "LongName", None)),
                    ("IfcSpace.ObjectType", getattr(entity, "ObjectType", None)), ("IfcSpace.Description", getattr(entity, "Description", None)),
                    ("IfcSpace.Properties", json.dumps(properties, ensure_ascii=False)),
                ]) if entity_type == "IfcSpace" else None
                area = _first_numeric(quantities, ("GrossFloorArea", "NetFloorArea", "Area"))
                volume = _first_numeric(quantities, ("GrossVolume", "NetVolume", "Volume"))
                nodes.append(ParsedSpatialNode(
                    global_id=global_id, entity_type=entity_type,
                    name=_clean(getattr(entity, "Name", None), 300) or f"Unnamed {entity_type}",
                    description=_clean(getattr(entity, "Description", None)),
                    parent_global_id=_parent_global_id(entity), node_type=NODE_TYPE[entity_type],
                    elevation=float(entity.Elevation) if entity_type == "IfcBuildingStorey" and getattr(entity, "Elevation", None) is not None else None,
                    area=area, volume=volume,
                    metadata={"stepId": entity.id(), "properties": properties, "quantities": quantities,
                              "spaceClassification": space_classification,
                              "measurements": {"area": measurement(area, model_units.get("AREAUNIT"), "IFC_QUANTITY", "IfcElementQuantity"),
                                               "volume": measurement(volume, model_units.get("VOLUMEUNIT"), "IFC_QUANTITY", "IfcElementQuantity")}},
                ))
        # IFC2x3 does not define IfcSpatialElement (it uses
        # IfcSpatialStructureElement), so filter by concrete spatial classes
        # instead of asking an older schema about a newer abstract type.
        products = [
            item for item in model.by_type("IfcProduct")
            if item.is_a() not in SPATIAL_TYPES and item.is_a() != "IfcAnnotation"
        ]
        elements: list[ParsedElement] = []
        element_ids: set[str] = set()
        for entity in products:
            global_id = _global_id(entity)
            if global_id in element_ids:
                warnings.append(f"Duplicate element GlobalId normalized at STEP #{entity.id()}")
                global_id = f"{global_id}-{entity.id()}"
            element_ids.add(global_id)
            entity_type = entity.is_a()
            storey, space, building = _spatial_ancestors(entity)
            properties, quantities = _psets(entity)
            type_name, material = _type_and_material(entity)
            material_status = "DEFINED" if material else "MISSING_FROM_SOURCE"
            if material and "IfcMaterialVirtual" in material:
                material = None
                material_status = "VIRTUAL_REFERENCE"
            system_name = _systems(entity)
            predefined_type = _clean(getattr(entity, "PredefinedType", None), 100)
            original_name = _clean(getattr(entity, "Name", None), 300)
            object_type = _clean(getattr(entity, "ObjectType", None), 200)
            discipline, discipline_confidence, discipline_reason, discipline_attributes = discipline_for_class(
                entity_type, system_name=system_name, predefined_type=predefined_type,
                name=original_name, object_type=object_type, material=material,
            )
            normalized_category = classify_element_category(entity_type, [
                ("IfcProduct.Name", original_name), ("IfcProduct.ObjectType", object_type),
                ("IfcTypeObject.Name", type_name), ("IfcSystem.Name", system_name), ("IfcProduct.PredefinedType", predefined_type),
            ])
            source_global_id = _clean(getattr(entity, "GlobalId", None), 64)
            classifications = _classifications(entity)
            missing = []
            if not original_name: missing.append("name")
            if not source_global_id: missing.append("GlobalId")
            if not properties: missing.append("properties")
            if not material: missing.append("material")
            if not quantities: missing.append("quantities")
            if not storey: missing.append("storey assignment")
            if not classifications: missing.append("classification")
            elements.append(ParsedElement(
                global_id=global_id, entity_type=entity_type,
                name=original_name or f"Unnamed {entity_type}",
                description=_clean(getattr(entity, "Description", None)),
                object_type=object_type,
                predefined_type=predefined_type,
                tag=_clean(getattr(entity, "Tag", None), 120),
                storey_global_id=storey, space_global_id=space, building_global_id=building,
                discipline=discipline, system_name=system_name,
                type_name=type_name, material_summary=material,
                properties=properties, quantities=quantities, bounding_box=None,
                geometry_hash=_representation_hash(entity), placement_hash=_placement_hash(entity),
                metadata={
                    "stepId": entity.id(), "originalName": original_name, "sourceGlobalId": source_global_id,
                    "classifications": classifications, "disciplineSource": "CALCULATED",
                    "disciplineConfidence": discipline_confidence, "disciplineReason": discipline_reason,
                    "disciplineSourceAttributes": discipline_attributes, "missingData": missing,
                    "completenessStatus": "COMPLETE" if not missing else ("PARTIAL" if len(missing) < 4 else "INCOMPLETE"),
                    "materialStatus": material_status, "units": model_units,
                    "normalizedCategory": normalized_category["category"], "categoryInference": normalized_category,
                },
            ))
        if not any(node.node_type == "STOREY" for node in nodes):
            warnings.append("The model has no IfcBuildingStorey hierarchy; elements appear under Unassigned.")
        if not any(node.node_type == "SPACE" for node in nodes):
            warnings.append("The model has no IfcSpace entities; room intelligence is unavailable.")
        authoring_application = None
        applications = model.by_type("IfcApplication")
        if applications:
            app = applications[0]
            authoring_application = _clean(f"{getattr(app, 'ApplicationFullName', '')} {getattr(app, 'Version', '')}", 250)
        asset_type, confidence, evidence = _asset_type(nodes, elements)
        discipline_counts = Counter(item.discipline for item in elements)
        class_counts = Counter(item.entity_type for item in elements)
        project_node = next((node for node in nodes if node.node_type == "PROJECT"), None)
        site_node = next((node for node in nodes if node.node_type == "SITE"), None)
        building_node = next((node for node in nodes if node.node_type == "BUILDING"), None)
        room_categories = Counter(
            (node.metadata.get("spaceClassification") or {}).get("category", "UNKNOWN")
            for node in nodes if node.node_type == "SPACE"
        )
        strengths = []
        completeness = _completeness(elements)
        if completeness["validGlobalIds"]["percentage"] >= 95:
            strengths.append("GlobalId coverage is high, supporting reliable element tracking across revisions.")
        if completeness["systemAssignments"]["percentage"] >= 80:
            strengths.append("Most extracted elements have system assignments for coordination filtering.")
        missing_information = []
        for key, label in (("quantities", "explicit quantity sets"), ("materials", "material information"), ("classifications", "formal classification")):
            metric_value = completeness[key]
            if metric_value["percentage"] < 50:
                missing_information.append(f"{label.capitalize()} cover {metric_value['percentage']}% of extracted elements.")
        intelligence_text = (
            f"This IFC contains {sum(node.node_type == 'BUILDING' for node in nodes)} building(s), "
            f"{sum(node.node_type == 'STOREY' for node in nodes)} storey(s), {sum(node.node_type == 'SPACE' for node in nodes)} "
            f"defined space(s), and {len(elements)} extracted element(s). "
            + (" ".join(strengths[:1]) if strengths else "Available facts are presented with their source and confidence.")
        )
        summary = {
            "schema": schema, "sites": sum(node.node_type == "SITE" for node in nodes),
            "buildings": sum(node.node_type == "BUILDING" for node in nodes),
            "storeys": sum(node.node_type == "STOREY" for node in nodes),
            "spaces": sum(node.node_type == "SPACE" for node in nodes),
            "zones": sum(node.node_type == "ZONE" for node in nodes),
            "elements": len(elements), "disciplineBreakdown": dict(discipline_counts),
            "majorElementCategories": dict(class_counts.most_common(20)),
            "projectOverview": {
                "projectName": project_node.name if project_node else None,
                "siteName": site_node.name if site_node else None,
                "buildingName": building_node.name if building_node else None,
                "buildingType": asset_type if asset_type != "UNKNOWN" else None,
                "ifcSchema": schema, "authoringApplication": authoring_application,
                "projectPhase": None, "modelDescription": project_node.description if project_node else None,
                "sources": {
                    "projectName": "IFC_SOURCE" if project_node else "MISSING", "siteName": "IFC_SOURCE" if site_node else "MISSING",
                    "buildingName": "IFC_SOURCE" if building_node else "MISSING", "buildingType": "CALCULATED" if asset_type != "UNKNOWN" else "MISSING",
                    "ifcSchema": "IFC_SOURCE", "authoringApplication": "IFC_SOURCE" if authoring_application else "MISSING",
                    "projectPhase": "MISSING", "modelDescription": "IFC_SOURCE" if project_node and project_node.description else "MISSING",
                },
            },
            "mainStatistics": _main_statistics(elements, nodes),
            "spaceCategories": dict(room_categories),
            "modelCompleteness": completeness,
            "intelligenceSummary": {"text": intelligence_text, "strengths": strengths,
                                    "missingInformation": missing_information, "coordinationRisks": [],
                                    "recommendedNextSteps": ["Review missing source information before relying on automated takeoff or coordination decisions."],
                                    "source": "STRUCTURED_IFC_ANALYTICS", "reviewNotice": "Automated analysis — engineering review required."},
            "georeferencing": _georeferencing(model),
            "units": model_units,
            "hierarchyCounts": dict(Counter(node.node_type for node in nodes)),
            "assetType": {"value": asset_type, "confidence": confidence, "evidence": evidence},
            "warnings": warnings,
        }
        return ParsedIFC(
            schema=schema, authoring_application=authoring_application, nodes=nodes,
            elements=elements, summary=summary, warnings=warnings,
            task_suggestions=_task_suggestions(elements),
        )


def _first_numeric(data: dict, keys: tuple[str, ...]) -> float | None:
    def walk(value: Any):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys and isinstance(item, (int, float)) and not isinstance(item, bool):
                    return float(item)
                found = walk(item)
                if found is not None:
                    return found
        return None
    return walk(data)


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json_safe(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
