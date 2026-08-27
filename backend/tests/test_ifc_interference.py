"""Structural/service interference detection, and the limits it must respect.

The rule exists to answer "does this duct run through that beam?" from measured
geometry. It must be equally reliable about what it does *not* know: a bounding
box is not the element, touching is not interference, and a model whose length
unit is unstated cannot be measured at all.
"""

import pytest

from app.services.ifc_interference import (
    BASE_CONFIDENCE,
    MAXIMUM_CONFIDENCE,
    InterferenceElement,
    detect_interferences,
    unit_scale,
)

METRES = {"LENGTHUNIT": "m"}


def element(name, discipline, low, high, entity_type="IfcBeam", **kwargs):
    return InterferenceElement(
        element_id=f"id-{name}", global_id=f"gid-{name}", name=name,
        entity_type=entity_type, discipline=discipline,
        minimum=tuple(low) if low else None, maximum=tuple(high) if high else None,
        **kwargs,
    )


def beam(name="B1", low=(0, 0, 3.0), high=(0.3, 4.0, 3.4), **kwargs):
    return element(name, "STRUCTURAL", low, high, "IfcBeam", **kwargs)


def duct(name="D1", low=(0, 0, 3.1), high=(4.0, 0.5, 3.6), **kwargs):
    return element(name, "MECHANICAL", low, high, "IfcDuctSegment", **kwargs)


# --- The finding it exists to make -----------------------------------------

def test_a_duct_through_a_beam_is_reported():
    findings, report = detect_interferences([beam(), duct()], units=METRES)
    assert len(findings) == 1
    assert report["analysed"] is True
    finding = findings[0]
    assert finding.structural.name == "B1"
    assert finding.service.name == "D1"
    # x overlaps 0.3, y overlaps 0.5, z overlaps 0.3 -> shallowest axis is 0.3
    assert finding.penetration_metres == pytest.approx(0.3)
    assert finding.severity == "HIGH"


def test_the_finding_carries_evidence_that_can_be_traced_back():
    findings, _ = detect_interferences([beam(storey="Level 1"), duct(storey="Level 1")], units=METRES)
    evidence = findings[0].evidence
    assert evidence["structural"]["globalId"] == "gid-B1"
    assert evidence["service"]["globalId"] == "gid-D1"
    # Both source boxes are kept, so the arithmetic can be re-checked later.
    assert evidence["structural"]["boundingBox"]["min"] == [0, 0, 3.0]
    assert evidence["overlapBox"]["min"] == [0, 0, 3.1]
    assert evidence["overlapBox"]["max"] == [0.3, 0.5, 3.4]
    assert evidence["location"]["storey"] == "Level 1"
    assert evidence["lengthUnit"] == "m"


def test_the_claim_is_a_candidate_and_says_how_to_verify_it():
    findings, _ = detect_interferences([beam(), duct()], units=METRES)
    finding = findings[0]
    assert finding.evidence["claim"] == "potential-interference"
    assert "not the elements" in finding.description or "not prove" in finding.evidence["verification"]
    assert "Potential interference" in finding.title
    # Never worded as a settled clash.
    assert "clash detected" not in finding.title.casefold()


def test_confidence_never_reaches_certainty_however_deep_the_overlap():
    # A service buried entirely inside a very large structural element.
    massive = beam(low=(-50, -50, -50), high=(50, 50, 50))
    findings, _ = detect_interferences([massive, duct()], units=METRES)
    assert findings[0].confidence <= MAXIMUM_CONFIDENCE
    assert findings[0].confidence < 1.0


def test_a_shallow_overlap_is_less_confident_than_a_deep_one():
    shallow = duct(low=(0, 0, 3.38), high=(4.0, 0.5, 3.6))  # 0.02 m into the beam
    deep, _ = detect_interferences([beam(), duct()], units=METRES)
    thin, _ = detect_interferences([beam(), shallow], units=METRES)
    assert thin[0].confidence == BASE_CONFIDENCE
    assert deep[0].confidence > thin[0].confidence


# --- What it must refuse to report -----------------------------------------

def test_elements_that_only_touch_are_not_interfering():
    # A tray resting exactly on the beam's top face: overlap is zero.
    tray = element("CT1", "ELECTRICAL", (0, 0, 3.4), (4.0, 0.3, 3.9), "IfcCableCarrierSegment")
    findings, report = detect_interferences([beam(), tray], units=METRES)
    assert findings == []
    assert report["analysed"] is True


def test_a_sub_millimetre_overlap_is_treated_as_modelling_noise():
    grazing = duct(low=(0, 0, 3.3995), high=(4.0, 0.5, 3.9))  # 0.5 mm
    assert detect_interferences([beam(), grazing], units=METRES)[0] == []


def test_separated_elements_produce_nothing():
    high_duct = duct(low=(0, 0, 6.0), high=(4.0, 0.5, 6.5))
    assert detect_interferences([beam(), high_duct], units=METRES)[0] == []


def test_two_structural_elements_are_not_paired_with_each_other():
    # Structure meeting structure is how a frame is built, not a finding.
    findings, report = detect_interferences([beam("B1"), beam("B2")], units=METRES)
    assert findings == []
    assert report["skippedReason"] == "NO_STRUCTURAL_AND_SERVICE_PAIR_AVAILABLE"


def test_services_overlapping_each_other_are_not_reported_by_this_rule():
    findings, _ = detect_interferences([duct("D1"), duct("D2")], units=METRES)
    assert findings == []


def test_architectural_elements_are_not_paired_with_services():
    # Services pass through walls and slabs by design, through sleeves and
    # openings. Pairing them would bury the structural signal in routine work.
    wall = element("W1", "ARCHITECTURAL", (0, 0, 3.0), (0.3, 4.0, 3.4), "IfcWall")
    assert detect_interferences([wall, duct()], units=METRES)[0] == []


def test_a_model_with_no_geometry_at_all_says_so_rather_than_reporting_clean():
    # Geometry disabled or tessellation failed. Reporting this the same way as
    # "no services in this model" would let a model look checked when nothing
    # about it could be measured.
    blind = [element("B1", "STRUCTURAL", None, None), element("D1", "MECHANICAL", None, None)]
    findings, report = detect_interferences(blind, units=METRES)
    assert findings == []
    assert report["skippedReason"] == "NO_ELEMENT_GEOMETRY_AVAILABLE"
    assert report["elementsWithoutGeometry"] == 2


def test_elements_without_geometry_are_counted_not_guessed():
    findings, report = detect_interferences(
        [beam(), duct(), element("D2", "MECHANICAL", None, None, "IfcDuctSegment")],
        units=METRES,
    )
    assert len(findings) == 1
    assert report["elementsWithoutGeometry"] == 1


# --- Units, the trap that would silently invert every threshold ------------

def test_a_millimetre_model_uses_millimetre_thresholds():
    # The same geometry as the metre case, expressed in millimetres.
    findings, report = detect_interferences(
        [beam(low=(0, 0, 3000), high=(300, 4000, 3400)),
         duct(low=(0, 0, 3100), high=(4000, 500, 3600))],
        units={"LENGTHUNIT": "mm"},
    )
    assert len(findings) == 1
    # Still 0.3 real metres, not 300.
    assert findings[0].penetration_metres == pytest.approx(0.3)
    assert findings[0].severity == "HIGH"
    assert report["lengthUnit"] == "mm"


def test_a_millimetre_model_still_discards_noise():
    # 0.5 mm of overlap, which in metres would have looked like half a kilometre.
    findings, _ = detect_interferences(
        [beam(low=(0, 0, 3000), high=(300, 4000, 3400)),
         duct(low=(0, 0, 3399.5), high=(4000, 500, 3600))],
        units={"LENGTHUNIT": "mm"},
    )
    assert findings == []


def test_an_unstated_length_unit_stops_the_analysis_instead_of_assuming_metres():
    findings, report = detect_interferences([beam(), duct()], units={})
    assert findings == []
    assert report["analysed"] is False
    assert report["skippedReason"] == "UNKNOWN_LENGTH_UNIT"


def test_no_findings_and_could_not_look_are_distinguishable():
    _, looked = detect_interferences([beam(), duct(low=(0, 0, 9), high=(1, 1, 9.5))], units=METRES)
    _, blind = detect_interferences([beam(), duct()], units=None)
    assert looked["analysed"] is True and looked["skippedReason"] is None
    assert blind["analysed"] is False and blind["skippedReason"]


@pytest.mark.parametrize("label, expected", [("m", 1.0), ("mm", 0.001), ("cm", 0.01), ("km", 1000.0)])
def test_known_units_scale_to_metres(label, expected):
    assert unit_scale({"LENGTHUNIT": label}) == expected


def test_an_unrecognised_unit_is_not_guessed():
    assert unit_scale({"LENGTHUNIT": "furlong"}) is None


# --- Severity, ordering and scale ------------------------------------------

@pytest.mark.parametrize("depth, expected", [(0.30, "HIGH"), (0.10, "HIGH"), (0.05, "MEDIUM"), (0.02, "LOW")])
def test_severity_follows_penetration_depth(depth, expected):
    service = duct(low=(0, 0, 3.4 - depth), high=(4.0, 0.5, 3.9))
    assert detect_interferences([beam(), service], units=METRES)[0][0].severity == expected


def test_worst_findings_are_listed_first():
    deep = duct("Deep", low=(0, 0, 3.1), high=(4.0, 0.5, 3.6))
    shallow = duct("Shallow", low=(0, 0, 3.38), high=(4.0, 0.5, 3.9))
    findings, _ = detect_interferences([beam(), shallow, deep], units=METRES)
    assert [item.service.name for item in findings] == ["Deep", "Shallow"]


def test_the_same_model_always_produces_the_same_order():
    items = [beam(), duct("D1"), duct("D2", low=(0, 0, 3.1), high=(4.0, 0.5, 3.6))]
    first, _ = detect_interferences(items, units=METRES)
    second, _ = detect_interferences(list(reversed(items)), units=METRES)
    assert [(f.structural.global_id, f.service.global_id) for f in first] \
        == [(f.structural.global_id, f.service.global_id) for f in second]


def test_a_pair_is_reported_once_not_from_both_sides():
    findings, _ = detect_interferences([beam(), duct()], units=METRES)
    assert len(findings) == 1


def test_the_queue_is_capped_so_a_bad_model_stays_reviewable():
    ducts = [duct(f"D{index}", low=(0, 0, 3.1), high=(4.0, 0.5, 3.6)) for index in range(40)]
    findings, report = detect_interferences([beam(), *ducts], units=METRES, max_findings=10)
    assert len(findings) == 10
    assert report["truncated"] is True


def test_a_large_model_does_not_compare_every_pair():
    # 300 beams spread along a line, 300 ducts elsewhere: the broad-phase grid
    # must keep this far below the 90,000 comparisons of a naive double loop.
    beams = [beam(f"B{i}", low=(i * 10, 0, 3.0), high=(i * 10 + 0.3, 4.0, 3.4)) for i in range(300)]
    ducts = [duct(f"D{i}", low=(i * 10, 0, 3.1), high=(i * 10 + 1, 0.5, 3.6)) for i in range(300)]
    findings, report = detect_interferences([*beams, *ducts], units=METRES)
    assert len(findings) == 300
    assert report["comparisons"] < 5000
