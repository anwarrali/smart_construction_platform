"""Deterministic IFC ↔ project execution intelligence.

No LLM is required for detection. Every insight is persisted with structured
evidence, confidence, a deterministic fingerprint, and a human review state.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.field_submission import FieldSubmission
from app.models.enums import DesignChangeStatus, FieldSubmissionStatus, TaskStatus
from app.models.design_change import DesignChange
from app.models.ifc import AIInsight, IFCChangeRecord, IFCComparison, IFCCoordinationFinding, IFCElement, IFCEntityLink, IFCModelVersion, IFCSpatialNode
from app.models.issue import Issue
from app.models.project import Project
from app.models.task import Task

MODELED_DISCIPLINES = {"ARCHITECTURAL", "STRUCTURAL", "MECHANICAL", "ELECTRICAL", "PLUMBING", "FIRE_PROTECTION", "SITE_CIVIL", "INFRASTRUCTURE"}
ACTIVE_TASK_STATES = {TaskStatus.BACKLOG, TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.UNDER_REVIEW, TaskStatus.REWORK_REQUIRED, TaskStatus.BLOCKED}


def _value(value) -> str:
    return str(getattr(value, "value", value) or "").upper()


def _fingerprint(rule: str, project_id, version_id, context: dict) -> str:
    payload = json.dumps({"rule": rule, "project": str(project_id), "version": str(version_id) if version_id else None, "context": context}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def calculate_alignment(
    discipline_elements: dict[str, int], task_disciplines: dict[str, int], *,
    task_count: int, issue_count: int, linked_task_count: int,
    linked_issue_count: int, verified_evidence_count: int, linked_evidence_count: int,
) -> dict:
    """Calculate the documented transparent score from structured counts."""
    modeled = {key: count for key, count in discipline_elements.items() if key in MODELED_DISCIPLINES and count > 0}
    covered_elements = sum(count for discipline, count in modeled.items() if task_disciplines.get(discipline, 0) > 0)
    task_scope = covered_elements / max(sum(modeled.values()), 1)
    discipline_coverage = sum(task_disciplines.get(value, 0) > 0 for value in modeled) / max(len(modeled), 1)
    location_linkage = linked_task_count / max(task_count, 1) if task_count else 0
    issue_linkage = linked_issue_count / max(issue_count, 1) if issue_count else 0
    evidence_coverage = linked_evidence_count / max(verified_evidence_count, 1) if verified_evidence_count else 0
    components = {
        "taskScopeCoverage": round(task_scope * 100, 1),
        "disciplineCoverage": round(discipline_coverage * 100, 1),
        "locationLinkedTasks": round(min(location_linkage, 1) * 100, 1),
        "ifcLinkedIssues": round(min(issue_linkage, 1) * 100, 1),
        "verifiedEvidenceCoverage": round(min(evidence_coverage, 1) * 100, 1),
    }
    overall = .40 * task_scope + .25 * discipline_coverage + .15 * min(location_linkage, 1) + .10 * min(issue_linkage, 1) + .10 * min(evidence_coverage, 1)
    return {
        "overall": round(overall * 100, 1), "components": components,
        "weights": {"taskScopeCoverage": 40, "disciplineCoverage": 25, "locationLinkedTasks": 15, "ifcLinkedIssues": 10, "verifiedEvidenceCoverage": 10},
        "ifcDisciplines": modeled, "taskDisciplines": dict(task_disciplines),
        "taskCount": task_count, "issueCount": issue_count,
        "linkedTaskCount": linked_task_count, "linkedIssueCount": linked_issue_count,
        "linkedEvidenceCount": linked_evidence_count,
    }


def _store(db: Session, *, project_id, version_id, rule: str, category: str, severity: str, confidence: float,
           title: str, description: str, reason: str, recommended_action: str, evidence: dict,
           affected: dict | None = None, task_ids: list | None = None, issue_ids: list | None = None,
           evidence_ids: list | None = None, potential_impact: str | None = None, context: dict | None = None,
           params: dict | None = None) -> AIInsight:
    fingerprint = _fingerprint(rule, project_id, version_id, context or evidence)
    item = db.query(AIInsight).filter(AIInsight.fingerprint == fingerprint).first()
    if not item:
        item = AIInsight(project_id=project_id, model_revision_id=version_id, fingerprint=fingerprint,
                         insight_type=rule, category=category, severity=severity, confidence=confidence,
                         title=title, description=description, reason=reason, recommended_action=recommended_action,
                         message_params_json=params or {}, evidence_json=evidence, affected_json=affected or {},
                         related_task_ids_json=[str(value) for value in task_ids or []],
                         related_issue_ids_json=[str(value) for value in issue_ids or []],
                         related_evidence_ids_json=[str(value) for value in evidence_ids or []],
                         potential_impact=potential_impact, source_engine="DETERMINISTIC_RULE_ENGINE_V1", status="NEW")
        db.add(item)
    elif item.status in {"NEW", "UNDER_REVIEW"}:
        item.severity=severity;item.confidence=confidence;item.description=description;item.reason=reason
        item.recommended_action=recommended_action;item.evidence_json=evidence;item.affected_json=affected or {}
        item.message_params_json=params or {}
        item.related_task_ids_json=[str(value) for value in task_ids or []]
        item.related_issue_ids_json=[str(value) for value in issue_ids or []]
        item.related_evidence_ids_json=[str(value) for value in evidence_ids or []]
        item.potential_impact=potential_impact
    return item


def alignment_facts(db: Session, project_id, version: IFCModelVersion) -> dict:
    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).all()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    issues = db.query(Issue).filter(Issue.project_id == project_id).all()
    discipline_elements = Counter((item.discipline or "UNCLASSIFIED").upper() for item in elements)
    task_disciplines = Counter(_value(item.discipline) or "UNASSIGNED" for item in tasks)
    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.version_id == version.id).all()
    linked_task_ids = {item.linked_entity_id for item in links if item.linked_entity_type == "TASK"}
    linked_issue_ids = {item.linked_entity_id for item in links if item.linked_entity_type == "ISSUE"}
    linked_evidence_ids = {item.linked_entity_id for item in links if item.linked_entity_type in {"FIELD_SUBMISSION", "EVIDENCE"}}
    verified = db.query(FieldSubmission).filter(FieldSubmission.project_id == project_id, FieldSubmission.status == FieldSubmissionStatus.VERIFIED).count()
    return calculate_alignment(
        dict(discipline_elements), dict(task_disciplines), task_count=len(tasks), issue_count=len(issues),
        linked_task_count=len(linked_task_ids), linked_issue_count=len(linked_issue_ids),
        verified_evidence_count=verified, linked_evidence_count=len(linked_evidence_ids),
    )


def run_project_intelligence(db: Session, project_id, version_id=None) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project does not exist")
    version = db.get(IFCModelVersion, version_id) if version_id else db.query(IFCModelVersion).filter(
        IFCModelVersion.project_id == project_id, IFCModelVersion.processing_status.in_(["READY", "READY_WITH_WARNINGS"]),
    ).order_by(IFCModelVersion.is_active.desc(), IFCModelVersion.created_at.desc()).first()
    if not version or version.project_id != project_id:
        return {"versionId": None, "alignment": None, "generated": 0, "message": "No processed IFC revision is available."}
    before = db.query(AIInsight).filter(AIInsight.project_id == project_id).count()
    facts = alignment_facts(db, project_id, version)
    elements = db.query(IFCElement).filter(IFCElement.version_id == version.id).all()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    task_by_id = {item.id:item for item in tasks}
    storeys = {item.id:item.name for item in db.query(IFCSpatialNode).filter(IFCSpatialNode.version_id == version.id, IFCSpatialNode.node_type == "STOREY").all()}

    if facts["overall"] < 50 and len(elements) >= 10:
        _store(db, project_id=project_id, version_id=version.id, rule="MODEL_PROJECT_ALIGNMENT_LOW", category="MODEL",
               severity="WARNING", confidence=min(.97,.65+(50-facts["overall"])/100), title="Possible model / project scope mismatch",
               description=f"The IFC ↔ project alignment score is {facts['overall']}%. Significant modeled scope is not represented in linked execution data.",
               reason="The weighted structured coverage metrics fall below the 50% review threshold.",
               recommended_action="Verify that this IFC revision belongs to the project and review missing task/location/evidence mappings.",
               params={"alignmentScore": facts["overall"]},
               potential_impact="Execution planning may not reflect the current design model.", evidence=facts,
               affected={"versionId":str(version.id)}, context={"overallBand":int(facts["overall"]//5)})

    if facts["linkedTaskCount"] and facts["components"]["verifiedEvidenceCoverage"] < 25:
        _store(db, project_id=project_id, version_id=version.id, rule="LOW_VERIFIED_EVIDENCE_COVERAGE", category="EVIDENCE",
               severity="ATTENTION", confidence=.95, title="Model-linked work has limited verified evidence coverage",
               description=f"Only {facts['components']['verifiedEvidenceCoverage']}% of the project's verified field evidence is linked to this IFC revision.",
               reason="Explicit IFC evidence links were compared with verified field-submission records.",
               recommended_action="Review field submissions and link verified evidence to the relevant building, floor, room, task, or IFC objects.",
               params={"coverage": facts["components"]["verifiedEvidenceCoverage"]},
               evidence={"linkedEvidenceCount":facts["linkedEvidenceCount"],"verifiedEvidenceCoverage":facts["components"]["verifiedEvidenceCoverage"]},
               affected={"versionId":str(version.id)}, context={"coverageBand":int(facts["components"]["verifiedEvidenceCoverage"]//5)})

    for discipline, element_count in facts["ifcDisciplines"].items():
        task_count = facts["taskDisciplines"].get(discipline, 0)
        if element_count < 5 or task_count:
            continue
        confidence = .97 if element_count >= 25 else .88
        _store(db, project_id=project_id, version_id=version.id, rule="MODELED_DISCIPLINE_WITHOUT_TASKS", category="TASKS",
               severity="WARNING" if confidence >= .9 else "ATTENTION", confidence=confidence,
               title=f"{discipline.replace('_',' ').title()} model scope has no related tasks",
               description=f"The revision contains {element_count:,} {discipline.lower()} elements, while the project has zero tasks assigned to that discipline.",
               reason="Strong deterministic IFC discipline evidence exists and no matching task discipline was found.",
               recommended_action=f"Review grouped {discipline.lower()} installation and inspection task suggestions.",
               params={"discipline": discipline.lower(), "elementCount": element_count},
               evidence={"modeledElementCount":element_count,"taskCount":0,"discipline":discipline},
               affected={"disciplines":[discipline]}, context={"discipline":discipline})
        by_storey=Counter(storeys.get(item.storey_node_id,"Unassigned") for item in elements if item.discipline==discipline)
        for storey,count in by_storey.most_common(12):
            if count < 5: continue
            related=[str(item.id) for item in elements if item.discipline==discipline and storeys.get(item.storey_node_id,"Unassigned")==storey][:500]
            _store(db, project_id=project_id, version_id=version.id, rule="SUGGEST_GROUPED_TASK", category="SUGGESTED_TASK",
                   severity="SUGGESTION", confidence=.86, title=f"Install {discipline.replace('_',' ').lower()} scope — {storey}",
                   description=f"Review a grouped work package covering {count} modeled {discipline.lower()} elements on {storey}.",
                   reason="Elements are grouped by model revision, discipline, and storey; no matching discipline task exists.",
                   recommended_action="Review, edit, and create a task only if this work package matches the construction plan.",
               params={"discipline": discipline.lower(), "storey": storey, "elementCount": count},
                   evidence={"discipline":discipline,"storey":storey,"elementCount":count,"grouping":["discipline","storey"]},
                   affected={"storeys":[storey],"elements":related,"disciplines":[discipline]},context={"discipline":discipline,"storey":storey})

    links = db.query(IFCEntityLink).filter(IFCEntityLink.project_id == project_id, IFCEntityLink.version_id == version.id).all()
    task_links=defaultdict(list)
    for link in links:
        if link.linked_entity_type=="TASK": task_links[link.linked_entity_id].append(link)
    for task_id,task_link_rows in task_links.items():
        task=task_by_id.get(task_id)
        if not task or task.status!=TaskStatus.DONE: continue
        verified=db.query(FieldSubmission).filter(FieldSubmission.task_id==task.id,FieldSubmission.status==FieldSubmissionStatus.VERIFIED).count()
        if verified==0:
            _store(db,project_id=project_id,version_id=version.id,rule="COMPLETED_LINKED_TASK_WITHOUT_VERIFIED_EVIDENCE",category="EVIDENCE",severity="ATTENTION",confidence=.99,
                   title="Completed task without verified field evidence",description=f'“{task.name}” is Done and linked to {len(task_link_rows)} BIM location/object record(s), but has no verified field submission.',
                   reason="Task status, explicit IFC links, and verified field-submission count were compared directly.",recommended_action="Review available site records before treating model-linked execution as verified.",
                   evidence={"taskStatus":"done","ifcLinkCount":len(task_link_rows),"verifiedSubmissionCount":0},task_ids=[task.id],context={"taskId":str(task.id)})

    category_elements=defaultdict(list)
    linked_element_ids={link.ifc_element_id for link in links if link.linked_entity_type=="TASK" and link.ifc_element_id}
    for element in elements:
        category=(element.metadata_json or {}).get("normalizedCategory")
        if category and category!="UNKNOWN":category_elements[category].append(element)
    for category,items in category_elements.items():
        uncovered=[item for item in items if item.id not in linked_element_ids]
        if len(items)>=10 and len(uncovered)>=10:
            _store(db,project_id=project_id,version_id=version.id,rule="MODELED_OBJECTS_WITHOUT_EXECUTION_COVERAGE",category="TASKS",severity="SUGGESTION",confidence=.95,
                   title=f"Modeled {category.replace('_',' ').lower()} objects without execution coverage",
                   description=f"{len(uncovered):,} of {len(items):,} modeled {category.replace('_',' ').lower()} objects have no explicit task link.",
                   reason="Modeled element IDs were compared with explicit IFC-to-task links. This is a planning-gap suggestion, not an error.",
                   recommended_action="Review whether grouped installation or inspection tasks should cover these objects.",
                   evidence={"modeledCount":len(items),"taskLinkedCount":len(items)-len(uncovered),"uncoveredCount":len(uncovered)},
                   affected={"categories":[category],"elements":[str(item.id) for item in uncovered[:500]]},context={"category":category})

    # Existing task → model mapping suggestions require a discipline match and
    # at least one concrete model term. They remain reviewable suggestions and
    # never create links automatically.
    generic_tokens={"install","installation","inspect","inspection","work","works","level","floor","building","complete","construction","task"}
    def tokens(value):
        normalized="".join(char.lower() if char.isalnum() else " " for char in str(value or ""))
        return {part for part in normalized.split() if len(part)>=4 and part not in generic_tokens}
    for task in tasks:
        discipline=_value(task.discipline)
        task_tokens=tokens(f"{task.name} {task.description or ''}")
        if discipline not in facts["ifcDisciplines"] or not task_tokens:
            continue
        matches=[]
        matched_terms=set()
        for element in elements:
            if (element.discipline or "").upper()!=discipline:
                continue
            category=(element.metadata_json or {}).get("normalizedCategory")
            element_tokens=tokens(f"{element.name} {element.entity_type} {element.system_name or ''} {category or ''} {storeys.get(element.storey_node_id,'')}")
            overlap=task_tokens & element_tokens
            if overlap:
                matches.append(element)
                matched_terms.update(overlap)
        if len(matches)>=2:
            confidence=min(.94,.72+.04*len(matched_terms))
            _store(db,project_id=project_id,version_id=version.id,rule="EXISTING_TASK_POSSIBLE_IFC_MATCH",category="TASKS",severity="SUGGESTION",confidence=confidence,
                   title="Existing task may match modeled objects",description=f'“{task.name}” appears to correspond to {len(matches)} modeled {discipline.lower()} object(s).',
                   reason="The task discipline and explicit model terms match; no link is created until a user reviews the mapping.",recommended_action="Review the candidate objects and confirm only the correct IFC links.",
                   evidence={"discipline":discipline,"matchedTerms":sorted(matched_terms),"candidateCount":len(matches)},task_ids=[task.id],
                   affected={"disciplines":[discipline],"elements":[str(item.id) for item in matches[:500]]},context={"taskId":str(task.id),"terms":sorted(matched_terms)})

    for finding in db.query(IFCCoordinationFinding).filter(
        IFCCoordinationFinding.project_id==project_id, IFCCoordinationFinding.version_id==version.id,
        IFCCoordinationFinding.status.in_(["PENDING","ACKNOWLEDGED"]), IFCCoordinationFinding.false_positive.is_(False),
    ).all():
        affected_elements=[str(value) for value in (finding.element_a_id,finding.element_b_id) if value]
        severity="WARNING" if finding.severity.upper() in {"HIGH","CRITICAL"} else "ATTENTION"
        _store(db,project_id=project_id,version_id=version.id,rule="IFC_MODEL_QUALITY_FINDING",category="MODEL",severity=severity,confidence=1,
               title=finding.title,description=finding.description,reason="An existing deterministic IFC model-quality rule produced this finding.",
               recommended_action="Review the affected model elements; create an issue or task only when project follow-up is required.",
               evidence={"findingId":str(finding.id),"findingType":finding.finding_type,"geometryEvidence":finding.geometry_evidence_json or {}},
               affected={"elements":affected_elements,"disciplines":finding.affected_disciplines_json or []},context={"findingId":str(finding.id)})

    comparisons=db.query(IFCComparison).filter(IFCComparison.project_id==project_id,IFCComparison.target_version_id==version.id,IFCComparison.status=="COMPLETED").all()
    approved_design_changes=db.query(DesignChange).filter(
        DesignChange.project_id==project_id,
        DesignChange.status==DesignChangeStatus.APPROVED,
    ).all()
    for comparison in comparisons:
        changes=db.query(IFCChangeRecord).filter(IFCChangeRecord.comparison_id==comparison.id).all()
        affected_task_ids=set()
        removed_active=[];changed_completed=[]
        for change in changes:
            element_ids=[value for value in (change.base_element_id,change.target_element_id) if value]
            change_links=db.query(IFCEntityLink).filter(IFCEntityLink.project_id==project_id,IFCEntityLink.ifc_element_id.in_(element_ids),IFCEntityLink.linked_entity_type=="TASK").all() if element_ids else []
            for link in change_links:
                task=task_by_id.get(link.linked_entity_id)
                if not task:continue
                affected_task_ids.add(task.id)
                if change.change_type=="REMOVED" and task.status in ACTIVE_TASK_STATES:removed_active.append((change,task))
                if change.change_type in {"MODIFIED","MOVED"} and task.status==TaskStatus.DONE:changed_completed.append((change,task))
        expected_wall_removals=[]
        for change in changes:
            if change.change_type != "REMOVED" or not change.base_element_id:
                continue
            removed_element=db.get(IFCElement,change.base_element_id)
            if not removed_element or removed_element.entity_type not in {"IfcWall","IfcWallStandardCase"}:
                continue
            for design_change in approved_design_changes:
                text=f"{design_change.title} {design_change.description or ''}".casefold()
                removal=any(term in text for term in ("remove wall","remove partition","demolish wall","wall removal","إزالة الجدار","ازالة الجدار","إزالة الحائط"))
                if removal:
                    expected_wall_removals.append((change,design_change))
                    break
        for change,design_change in expected_wall_removals:
            _store(db,project_id=project_id,version_id=version.id,rule="REVISION_MATCHES_APPROVED_DESIGN_CHANGE",category="DESIGN_CONFLICT",severity="INFO",confidence=.82,
                   title="IFC removal may match an approved design change",description=f'The removed wall may implement approved design change “{design_change.title}”.',
                   reason="A wall-removal revision record was correlated with explicit removal language in an approved design change; engineering confirmation is still required.",
                   recommended_action="Confirm the affected wall identity and close the finding if the revision implements the approved change.",
                   evidence={"comparisonId":str(comparison.id),"changeRecordId":str(change.id),"designChangeId":str(design_change.id),"designChangeStatus":"approved"},
                   context={"changeId":str(change.id),"designChangeId":str(design_change.id)})
        if affected_task_ids:
            _store(db,project_id=project_id,version_id=version.id,rule="REVISION_AFFECTS_LINKED_WORK",category="REVISION",severity="WARNING",confidence=.99,
                   title="Revision affects linked construction work",description=f"Revision {version.revision_code or version.version_number} changes objects linked to {len(affected_task_ids)} project task(s).",
                   reason="Revision change records were joined to explicit IFC element-to-task links.",recommended_action="Review affected work before continuing execution.",
                   evidence={"comparisonId":str(comparison.id),"changedRecordCount":len(changes),"affectedTaskCount":len(affected_task_ids)},task_ids=list(affected_task_ids),context={"comparisonId":str(comparison.id)})
        for change,task in removed_active:
            _store(db,project_id=project_id,version_id=version.id,rule="ACTIVE_TASK_REFERENCES_REMOVED_ELEMENT",category="REVISION",severity="CRITICAL",confidence=1,
                   title="Active task references removed BIM element",description=f'“{task.name}” references an element removed in the latest compared revision.',reason="An exact revision removal record and explicit task link were found.",
                   recommended_action="Pause and review the latest design revision with the responsible engineer; do not change task state automatically.",evidence={"comparisonId":str(comparison.id),"changeRecordId":str(change.id),"changeType":"REMOVED"},task_ids=[task.id],context={"changeId":str(change.id),"taskId":str(task.id)})
        for change,task in changed_completed:
            _store(db,project_id=project_id,version_id=version.id,rule="REVISION_CHANGED_COMPLETED_SCOPE",category="REVISION",severity="WARNING",confidence=.98,
                   title="Design revision changed completed work scope",description=f'“{task.name}” is Done, but its linked BIM element is {change.change_type.lower()} in the latest revision.',reason="A deterministic revision record intersects an explicit completed-task link.",
                   recommended_action="Engineering review is required to determine whether completed site work is affected.",evidence={"comparisonId":str(comparison.id),"changeRecordId":str(change.id),"changeType":change.change_type},task_ids=[task.id],context={"changeId":str(change.id),"taskId":str(task.id)})
    db.flush()
    from app.services.ai_traceability_service import register_structured_sources
    for insight in db.query(AIInsight).filter(AIInsight.project_id == project_id).all():
        register_structured_sources(db, insight)
    db.commit()
    after=db.query(AIInsight).filter(AIInsight.project_id==project_id).count()
    return {"versionId":str(version.id),"alignment":facts,"generated":max(0,after-before),"total":after,"completedAt":datetime.now(timezone.utc).isoformat()}
