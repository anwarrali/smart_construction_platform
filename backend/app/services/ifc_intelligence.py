"""Human-facing IFC semantics. All inferences are deterministic and evidence-backed."""
from __future__ import annotations

import re
from typing import Any


SPACE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MASTER_BEDROOM", ("master bedroom", "primary bedroom")),
    ("BEDROOM", ("bedroom", "bed room", "sleeping room")),
    ("BATHROOM", ("bathroom", "bath room", "shower room", "washroom")),
    ("WC", ("wc", "toilet", "lavatory")),
    ("KITCHEN", ("kitchen", "pantry")),
    ("LIVING_ROOM", ("living room", "family room")),
    ("SALON", ("salon", "majlis")),
    ("OFFICE", ("office", "workroom")),
    ("CORRIDOR", ("corridor", "hallway", "passage")),
    ("LOBBY", ("lobby", "reception", "foyer")),
    ("STORAGE", ("storage", "store room", "storeroom")),
    ("BALCONY", ("balcony", "terrace")),
    ("PARKING", ("parking", "garage", "car park")),
    ("UTILITY_ROOM", ("utility room", "plant room", "service room", "laundry")),
)

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("DOOR", ("door", "doorset")), ("WINDOW", ("window", "glazing")),
    ("WALL", ("wall", "partition")), ("SLAB", ("slab", "floor deck")),
    ("ROOF", ("roof",)), ("COLUMN", ("column", "pillar")),
    ("BEAM", ("beam", "girder")), ("STAIR", ("stair", "step")),
    ("ELEVATOR", ("elevator", "lift")), ("FURNITURE", ("furniture", "furnishing")),
    ("FIRE_PROTECTION_EQUIPMENT", ("sprinkler", "fire alarm", "fire suppression", "smoke detector")),
    ("PLUMBING_EQUIPMENT", ("sanitary", "plumbing", "toilet", "basin", "sink", "pipe")),
    ("ELECTRICAL_EQUIPMENT", ("electrical", "light", "socket", "outlet", "switch", "cable")),
    ("MECHANICAL_EQUIPMENT", ("hvac", "air terminal", "duct", "fan", "pump", "chiller", "boiler")),
)

DIRECT_CATEGORIES = {
    "IfcDoor": "DOOR", "IfcWindow": "WINDOW", "IfcWall": "WALL", "IfcWallStandardCase": "WALL",
    "IfcSlab": "SLAB", "IfcRoof": "ROOF", "IfcColumn": "COLUMN", "IfcBeam": "BEAM",
    "IfcStair": "STAIR", "IfcStairFlight": "STAIR", "IfcTransportElement": "ELEVATOR",
    "IfcFurniture": "FURNITURE", "IfcFurnishingElement": "FURNITURE", "IfcSystemFurnitureElement": "FURNITURE",
}


def _contains(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def classify_space(fields: list[tuple[str, Any]]) -> dict[str, Any]:
    """Classify a space only when a source string contains a recognized whole phrase."""
    for source, raw in fields:
        value = str(raw or "").strip()
        lowered = value.casefold()
        if not lowered:
            continue
        for category, phrases in SPACE_RULES:
            match = next((phrase for phrase in phrases if _contains(lowered, phrase)), None)
            if match:
                confidence = .98 if source in {"IfcSpace.Name", "IfcSpace.LongName"} else .9
                return {"category": category, "label": category.replace("_", " ").title(), "confidence": confidence,
                        "source": source, "evidence": value, "method": "DETERMINISTIC"}
    return {"category": "UNKNOWN", "label": "Unknown / Unclassified Space", "confidence": 0.0,
            "source": "MISSING", "evidence": None, "method": "UNCLASSIFIED"}


def classify_element_category(entity_type: str, fields: list[tuple[str, Any]]) -> dict[str, Any]:
    direct = DIRECT_CATEGORIES.get(entity_type)
    if direct:
        return {"category": direct, "confidence": .99, "source": "IfcProduct class",
                "evidence": entity_type, "method": "DETERMINISTIC"}
    # Only infer categories from generic classes; a contradictory specialist IFC class remains authoritative.
    if entity_type not in {"IfcBuildingElementProxy", "IfcProxy", "IfcFlowTerminal", "IfcFlowFitting", "IfcFlowSegment", "IfcDistributionElement", "IfcElementAssembly"}:
        return {"category": "UNKNOWN", "confidence": 0.0, "source": "MISSING", "evidence": None, "method": "UNCLASSIFIED"}
    for source, raw in fields:
        value = str(raw or "").strip()
        lowered = value.casefold()
        if not lowered:
            continue
        for category, phrases in CATEGORY_RULES:
            match = next((phrase for phrase in phrases if _contains(lowered, phrase)), None)
            if match:
                return {"category": category, "confidence": .86, "source": source,
                        "evidence": value, "method": "DETERMINISTIC"}
    return {"category": "UNKNOWN", "confidence": 0.0, "source": "MISSING", "evidence": None, "method": "UNCLASSIFIED"}


def measurement(value: float | None, unit: str | None, source_type: str, source_property: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"value": value, "unit": unit, "sourceType": source_type, "sourceProperty": source_property,
            "confidence": 1.0 if source_type == "IFC_QUANTITY" else .9}
