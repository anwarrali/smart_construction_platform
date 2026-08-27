"""Deterministic structural/MEP interference detection from real IFC geometry.

Until now the platform could describe a model and check its metadata quality,
but it could not answer the question a coordinator actually asks: *does this
duct run through that beam?* The module docs record why — a geometric claim was
refused outright while nothing supplied geometric evidence, which is the right
call. Guessing a clash from names would be inventing engineering findings.

What changed is the evidence, not the willingness to claim: the tessellation
worker now records each element's real world-coordinate extent, so overlap is
arithmetic on measured boxes rather than inference from text.

The limit of that evidence is stated in every finding this produces. An
axis-aligned bounding box is the smallest upright box containing an element,
not the element. Two boxes can overlap while the solids inside them never
touch — a diagonal brace beside a duct is the standard example. So the claim
is always "potential interference, verify in the model", never "clash", and
confidence is capped well below certainty no matter how deep the overlap is.
Solid-geometry intersection would be needed to promote that to a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Metres per unit, by the length-unit label the parser records. A model whose
#: unit is not in here is not analysed at all: every threshold below is a real
#: distance, and applying "10 mm" to unknown units would silently mean 10 km.
UNIT_SCALE_TO_METRES = {"m": 1.0, "mm": 0.001, "cm": 0.01, "dm": 0.1, "km": 1000.0}

#: The one pairing this rule makes. `discipline` comes from the parser's own
#: evidence-backed classification, where STRUCTURAL is exactly the load-bearing
#: set (beams, columns, footings, piles, members, plates) — walls and slabs are
#: classified ARCHITECTURAL. That matters: services routinely pass through
#: walls and slabs by design, through sleeves and openings, so pairing against
#: those would bury the real signal in routine penetrations. Passing through a
#: beam or a column is the case that needs an engineer to look.
STRUCTURAL_DISCIPLINE = "STRUCTURAL"
SERVICE_DISCIPLINES = frozenset({"MECHANICAL", "ELECTRICAL", "PLUMBING", "FIRE_PROTECTION"})

#: Overlap below this is contact or modelling noise, not interference. Elements
#: that merely touch — a duct resting on a support — overlap by ~0.
MINIMUM_PENETRATION_METRES = 0.01
#: Penetration depth at which a service passing through structure stops being a
#: detail and starts being a design question.
HIGH_SEVERITY_PENETRATION_METRES = 0.10
MEDIUM_SEVERITY_PENETRATION_METRES = 0.03

#: Confidence is a property of the *method*, not of how bad the overlap looks.
#: A box overlap is evidence of a candidate, never proof of a clash, so this
#: never approaches 1.0 — Phase 8 policy keys off these numbers and must not be
#: handed false certainty.
BASE_CONFIDENCE = 0.55
DEEP_OVERLAP_CONFIDENCE_BONUS = 0.15
MAXIMUM_CONFIDENCE = 0.70

#: Grid cell edge, in metres, for the broad-phase index.
CELL_SIZE_METRES = 2.0
#: A single element spanning more cells than this is checked against every
#: service element instead of being smeared across the grid.
MAX_CELLS_PER_ELEMENT = 512
#: Ceiling on reported pairs. A badly coordinated federated model can produce
#: tens of thousands; a review queue that long is not reviewable.
MAX_FINDINGS = 500


@dataclass(frozen=True)
class InterferenceElement:
    """One element as this rule needs to see it. No database types."""

    element_id: str
    global_id: str
    name: str
    entity_type: str
    discipline: str | None
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    storey: str | None = None
    space: str | None = None
    system: str | None = None


@dataclass(frozen=True)
class InterferenceFinding:
    structural: InterferenceElement
    service: InterferenceElement
    severity: str
    confidence: float
    penetration_metres: float
    overlap_metres: tuple[float, float, float]
    overlap_min: tuple[float, float, float]
    overlap_max: tuple[float, float, float]
    title: str
    description: str
    evidence: dict = field(default_factory=dict)


def unit_scale(units: dict | None) -> float | None:
    """Metres per model unit, or None when the model does not say."""
    label = (units or {}).get("LENGTHUNIT")
    return UNIT_SCALE_TO_METRES.get(str(label).strip()) if label else None


def _overlap(left: InterferenceElement, right: InterferenceElement):
    """Per-axis intersection extent, or None if the boxes miss on any axis."""
    low, high, extent = [], [], []
    for axis in range(3):
        start = max(left.minimum[axis], right.minimum[axis])
        end = min(left.maximum[axis], right.maximum[axis])
        if end <= start:
            return None
        low.append(start)
        high.append(end)
        extent.append(end - start)
    return low, high, extent


def _cells(item: InterferenceElement, cell_size: float):
    """Grid cells a box touches, or None when it covers too many to be worth indexing."""
    ranges = []
    total = 1
    for axis in range(3):
        first = int(item.minimum[axis] // cell_size)
        last = int(item.maximum[axis] // cell_size)
        total *= (last - first + 1)
        if total > MAX_CELLS_PER_ELEMENT:
            return None
        ranges.append(range(first, last + 1))
    return [(x, y, z) for x in ranges[0] for y in ranges[1] for z in ranges[2]]


def _severity(penetration_metres: float) -> str:
    if penetration_metres >= HIGH_SEVERITY_PENETRATION_METRES:
        return "HIGH"
    if penetration_metres >= MEDIUM_SEVERITY_PENETRATION_METRES:
        return "MEDIUM"
    return "LOW"


def _confidence(penetration_metres: float) -> float:
    value = BASE_CONFIDENCE
    if penetration_metres >= 0.05:
        value += DEEP_OVERLAP_CONFIDENCE_BONUS
    return round(min(value, MAXIMUM_CONFIDENCE), 2)


def _location(structural: InterferenceElement, service: InterferenceElement) -> dict:
    """Where a person should go to look. Only what the model actually stated."""
    return {
        "storey": structural.storey or service.storey,
        "space": structural.space or service.space,
        "storeySource": "IFC_SPATIAL_CONTAINMENT" if (structural.storey or service.storey) else "MISSING",
        "system": service.system,
    }


def detect_interferences(
    elements: list[InterferenceElement],
    *,
    units: dict | None = None,
    max_findings: int = MAX_FINDINGS,
) -> tuple[list[InterferenceFinding], dict]:
    """Find service elements whose measured extent overlaps structural elements.

    Returns the findings and a report of what was analysed — including the
    reasons analysis was limited or skipped, because "no findings" and "could
    not look" must never be presented as the same answer.
    """
    scale = unit_scale(units)
    report = {
        "method": "AXIS_ALIGNED_BOUNDING_BOX_OVERLAP",
        "structuralElements": 0,
        "serviceElements": 0,
        "elementsWithoutGeometry": 0,
        "comparisons": 0,
        "lengthUnit": (units or {}).get("LENGTHUNIT"),
        "analysed": False,
        "skippedReason": None,
        "truncated": False,
    }
    if scale is None:
        # Every threshold here is a real distance. Without a known unit the
        # analysis cannot be performed honestly, so it is not performed.
        report["skippedReason"] = "UNKNOWN_LENGTH_UNIT"
        return [], report

    structural, services = [], []
    for item in elements:
        if item.minimum is None or item.maximum is None:
            report["elementsWithoutGeometry"] += 1
            continue
        if item.discipline == STRUCTURAL_DISCIPLINE:
            structural.append(item)
        elif item.discipline in SERVICE_DISCIPLINES:
            services.append(item)
    report["structuralElements"] = len(structural)
    report["serviceElements"] = len(services)
    if not structural and not services and report["elementsWithoutGeometry"]:
        # Distinct from "this model has no services": geometry is disabled, or
        # tessellation failed, so nothing could be measured. Collapsing the two
        # would let a model report a clean result it was never able to check.
        report["skippedReason"] = "NO_ELEMENT_GEOMETRY_AVAILABLE"
        return [], report
    if not structural or not services:
        report["skippedReason"] = "NO_STRUCTURAL_AND_SERVICE_PAIR_AVAILABLE"
        return [], report

    report["analysed"] = True
    cell_size = CELL_SIZE_METRES / scale
    minimum_penetration = MINIMUM_PENETRATION_METRES / scale

    grid: dict[tuple, list[InterferenceElement]] = {}
    oversized: list[InterferenceElement] = []
    for item in structural:
        cells = _cells(item, cell_size)
        if cells is None:
            oversized.append(item)
            continue
        for cell in cells:
            grid.setdefault(cell, []).append(item)

    findings: list[InterferenceFinding] = []
    for service in services:
        cells = _cells(service, cell_size)
        candidates: dict[str, InterferenceElement] = {item.element_id: item for item in oversized}
        if cells is None:
            for bucket in grid.values():
                for item in bucket:
                    candidates[item.element_id] = item
        else:
            for cell in cells:
                for item in grid.get(cell, ()):
                    candidates[item.element_id] = item
        for candidate in candidates.values():
            report["comparisons"] += 1
            result = _overlap(candidate, service)
            if not result:
                continue
            low, high, extent = result
            penetration = min(extent)
            if penetration < minimum_penetration:
                continue
            penetration_metres = penetration * scale
            findings.append(InterferenceFinding(
                structural=candidate,
                service=service,
                severity=_severity(penetration_metres),
                confidence=_confidence(penetration_metres),
                penetration_metres=round(penetration_metres, 4),
                overlap_metres=tuple(round(value * scale, 4) for value in extent),
                overlap_min=tuple(low),
                overlap_max=tuple(high),
                title=(
                    f"Potential interference between {candidate.entity_type} "
                    f"'{candidate.name}' and {service.entity_type} '{service.name}'"
                ),
                description=(
                    f"The measured extents of {candidate.entity_type} '{candidate.name}' "
                    f"({STRUCTURAL_DISCIPLINE.lower()}) and {service.entity_type} "
                    f"'{service.name}' ({(service.discipline or '').lower()}) overlap by "
                    f"{round(penetration_metres, 3)} m at their shallowest axis. "
                    "Bounding boxes are not the elements themselves, so this is a candidate "
                    "for review, not a confirmed clash."
                ),
                evidence={
                    "claim": "potential-interference",
                    "method": "AXIS_ALIGNED_BOUNDING_BOX_OVERLAP",
                    "verification": (
                        "Open both elements in the 3D viewer or the authoring model and check "
                        "the solid geometry. Bounding-box overlap does not prove the solids intersect."
                    ),
                    "penetrationMetres": round(penetration_metres, 4),
                    "overlapMetres": [round(value * scale, 4) for value in extent],
                    "overlapBox": {"min": list(low), "max": list(high)},
                    "lengthUnit": (units or {}).get("LENGTHUNIT"),
                    "structural": _describe(candidate),
                    "service": _describe(service),
                    "location": _location(candidate, service),
                },
            ))
            if len(findings) >= max_findings:
                report["truncated"] = True
                break
        if report["truncated"]:
            break

    # Worst first, and stable: equal findings keep a repeatable order so the
    # same model produces the same queue every run.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings.sort(key=lambda item: (
        order[item.severity], -item.penetration_metres,
        item.structural.global_id, item.service.global_id,
    ))
    report["findingCount"] = len(findings)
    return findings, report


def _describe(item: InterferenceElement) -> dict:
    return {
        "elementId": item.element_id, "globalId": item.global_id, "name": item.name,
        "entityType": item.entity_type, "discipline": item.discipline,
        "storey": item.storey, "system": item.system,
        "boundingBox": {"min": list(item.minimum), "max": list(item.maximum)},
    }
