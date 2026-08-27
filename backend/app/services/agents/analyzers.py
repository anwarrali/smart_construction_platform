"""The five agents' reasoning, as deterministic rules over tool results.

Rules rather than a language model, deliberately. Every finding here has to
carry evidence a reader can re-check, and a rule that fired on four site
reports can name those four reports. The platform's own principle applies:
deterministic backend rules for what can be decided deterministically, and a
model only where interpretation genuinely needs one. Layering LLM
interpretation on top of these findings is Phase 7 work; it would sit above
this, not replace it.

Each analyzer takes an `AgentContext` and returns findings. None of them
touches the database directly — everything arrives through granted tools.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone

from app.services.agents.contracts import AgentFinding, Certainty, Evidence

#: A site report saying nothing about work is a filing, not a report.
SITE_REPORT_SUBSTANCE_FIELDS = ("workCompleted", "workInProgress", "delays", "issuesSummary")

#: Wording that marks a delay in either language the platform is used in.
DELAY_TERMS = (
    "delay", "delayed", "late", "behind schedule", "stopped", "halted", "waiting",
    "تأخير", "متأخر", "توقف", "معطل", "بانتظار",
)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _mentions(text: str | None, terms) -> str | None:
    if not text:
        return None
    lowered = text.casefold()
    return next((term for term in terms if term in lowered), None)


def _uncertain(code: str, title: str, reason: str, action: str) -> AgentFinding:
    """The explicit "I could not tell" outcome.

    Needed because an agent that returns nothing is indistinguishable from one
    that ran and found nothing wrong, and those mean opposite things to whoever
    is deciding whether to look themselves.
    """
    return AgentFinding(
        code=code, certainty=Certainty.UNCERTAIN, severity="INFO", confidence=0.3,
        title=title, description=reason, reason=reason, recommended_action=action,
    )


# --- 1. Site Report Agent ---------------------------------------------------

def site_report_agent(context) -> list[AgentFinding]:
    """Delays, recurring problems, missing information and progress conflicts."""
    reports = context.data("get_site_reports", {"limit": 30}).get("reports", [])
    if not reports:
        return [_uncertain(
            "SITE_REPORTS_UNAVAILABLE", "No site reports could be read",
            "This project has no site reports available to this caller, so site "
            "conditions cannot be assessed.",
            "File a site report, or check whether your role can read them.",
        )]

    findings: list[AgentFinding] = []
    detail = [context.data("get_site_report", {"reportId": report["id"]}) for report in reports[:15]]
    bodies = [item.get("report") for item in detail if item.get("report")]

    # Reports that record nothing about the work.
    empty = [
        report for report in bodies
        if not any((report.get(field) or "").strip() for field in SITE_REPORT_SUBSTANCE_FIELDS)
    ]
    if empty:
        findings.append(AgentFinding(
            code="SITE_REPORTS_MISSING_CONTENT", certainty=Certainty.DETECTED,
            severity="MEDIUM", confidence=0.9,
            title=f"{len(empty)} site report(s) record no work detail",
            description=(
                f"{len(empty)} of the {len(bodies)} most recent reports contain no "
                "completed work, work in progress, delays or issues."
            ),
            reason=(
                "A report with none of those four fields filled cannot support progress "
                "verification, and leaves the day unaccounted for."
            ),
            recommended_action="Ask the authors to complete the missing sections.",
            evidence=[
                Evidence("SITE_REPORT", report["id"], f"Report {report.get('reportDate') or report['id'][:8]}",
                         {"emptyFields": list(SITE_REPORT_SUBSTANCE_FIELDS)})
                for report in empty[:10]
            ],
            affected={"siteReports": [report["id"] for report in empty]},
        ))

    # Delays named in the reports themselves.
    delayed = [
        (report, _mentions(report.get("delays") or report.get("issuesSummary"), DELAY_TERMS))
        for report in bodies
    ]
    delayed = [(report, term) for report, term in delayed if term]
    if delayed:
        findings.append(AgentFinding(
            code="SITE_REPORTED_DELAYS", certainty=Certainty.FACT,
            severity="HIGH" if len(delayed) >= 3 else "MEDIUM",
            confidence=1.0,
            title=f"{len(delayed)} site report(s) record a delay",
            description="These reports state a delay in their own words.",
            reason="Read directly from the reports' delay and issue fields; nothing is inferred.",
            recommended_action="Review the reported delays against the schedule.",
            evidence=[
                Evidence("SITE_REPORT", report["id"],
                         f"Report {report.get('reportDate') or report['id'][:8]}",
                         {"matchedTerm": term, "delays": (report.get("delays") or "")[:300]})
                for report, term in delayed[:10]
            ],
            affected={"siteReports": [report["id"] for report, _ in delayed]},
        ))

    # The same wording recurring across separate reports.
    recurring = _recurring_phrases([report.get("issuesSummary") for report in bodies])
    if recurring:
        phrase, count = recurring
        findings.append(AgentFinding(
            code="SITE_RECURRING_ISSUE", certainty=Certainty.INFERRED,
            severity="HIGH", confidence=0.65,
            title=f"The same issue wording appears in {count} reports",
            description=f"{count} separate reports mention {phrase!r}.",
            reason=(
                "Repetition across separate reports suggests an unresolved condition "
                "rather than isolated incidents. This is inferred from wording, so the "
                "reports may be describing different underlying causes."
            ),
            recommended_action="Check whether this represents one unresolved problem.",
            evidence=[
                Evidence("SITE_REPORT", report["id"], "Report mentioning the recurring phrase",
                         {"phrase": phrase})
                for report in bodies
                if phrase in (report.get("issuesSummary") or "").casefold()
            ][:10],
        ))

    # A report claiming progress that the task record does not show.
    tasks = {task["id"]: task for task in context.data("get_tasks", {"limit": 200}).get("tasks", [])}
    for report in bodies:
        reported = report.get("progressPercentageReported")
        task = tasks.get(report.get("taskId"))
        if reported is None or not task or task.get("progressPercentage") is None:
            continue
        gap = float(reported) - float(task["progressPercentage"])
        if gap >= 25:
            findings.append(AgentFinding(
                code="SITE_PROGRESS_CONFLICT", certainty=Certainty.DETECTED,
                severity="MEDIUM", confidence=0.85,
                title=f"Reported progress exceeds the recorded task progress on {task['name']!r}",
                description=(
                    f"A site report states {reported}% while the task records "
                    f"{task['progressPercentage']}%."
                ),
                reason="Two records of the same work disagree by more than 25 percentage points.",
                recommended_action="Reconcile the report against the task before relying on either.",
                evidence=[
                    Evidence("SITE_REPORT", report["id"], "Reported progress", {"reported": reported}),
                    Evidence("TASK", task["id"], task["name"], {"recorded": task["progressPercentage"]}),
                ],
                affected={"tasks": [task["id"]], "siteReports": [report["id"]]},
                related_task_ids=[task["id"]],
            ))
    return findings


def _recurring_phrases(texts) -> tuple[str, int] | None:
    """The most repeated meaningful phrase across reports, if any repeats."""
    counts: Counter = Counter()
    for text in texts:
        if not text:
            continue
        for phrase in {p.strip().casefold() for p in re.split(r"[.\n;،]", text) if len(p.strip()) > 12}:
            counts[phrase] += 1
    for phrase, count in counts.most_common(1):
        if count >= 3:
            return phrase, count
    return None


# --- 2. Document Consistency Agent ------------------------------------------

def document_consistency_agent(context) -> list[AgentFinding]:
    """Relationships first, comparison second.

    Comparing every document with every other is both quadratic and meaningless
    — a contract and a photo log have nothing to be consistent about. Documents
    are grouped by the kind the Phase 3 classifier detected, and only documents
    of the same kind, or a kind and its declared counterpart, are considered.
    """
    documents = context.data("search_documents", {"query": " ", "limit": 100}).get("documents", [])
    if not documents:
        return [_uncertain(
            "DOCUMENTS_UNAVAILABLE", "No readable documents",
            "No documents in this project are readable by this caller, so consistency "
            "cannot be assessed.",
            "Upload project documents, or check your document access.",
        )]

    findings: list[AgentFinding] = []

    # The classifier disagreeing with the filer is the cheapest real signal
    # available, and it is evidence-backed rather than inferred.
    misfiled = [
        document for document in documents
        if document.get("suggestedDocumentType")
        and document.get("documentType")
        and document["suggestedDocumentType"] not in {"OTHER", document["documentType"].upper()}
    ]
    if misfiled:
        findings.append(AgentFinding(
            code="DOCUMENT_TYPE_DISAGREEMENT", certainty=Certainty.DETECTED,
            severity="LOW", confidence=0.75,
            title=f"{len(misfiled)} document(s) are filed as something the file does not look like",
            description=(
                "The content-based classifier reached a different document kind than the "
                "uploader selected."
            ),
            reason=(
                "A misfiled document is invisible to anything that searches by type. The "
                "uploader may still be right — this is a disagreement, not a correction."
            ),
            recommended_action="Confirm the document type on each of these.",
            evidence=[
                Evidence("DOCUMENT", document["id"], document["title"], {
                    "filedAs": document["documentType"],
                    "detectedAs": document["suggestedDocumentType"],
                    "format": document.get("detectedFormat"),
                })
                for document in misfiled[:10]
            ],
            affected={"documents": [document["id"] for document in misfiled]},
        ))

    # Several documents of one governing kind, none of which can be read.
    by_kind: dict[str, list] = {}
    for document in documents:
        by_kind.setdefault((document.get("documentType") or "other").upper(), []).append(document)
    for kind in ("SPECIFICATION", "CONTRACT", "BOQ"):
        group = by_kind.get(kind, [])
        unindexed = [item for item in group if item.get("indexStatus") != "READY"]
        if len(group) >= 2 and len(unindexed) == len(group):
            findings.append(AgentFinding(
                code=f"{kind}_NOT_INDEXED", certainty=Certainty.DETECTED,
                severity="MEDIUM", confidence=0.9,
                title=f"None of the {len(group)} {kind.lower()} documents are indexed",
                description=(
                    f"{len(group)} documents of this kind exist and none has been indexed, "
                    "so their contents cannot be compared or cited."
                ),
                reason=(
                    "Consistency between documents of the same governing kind can only be "
                    "checked against their text, which requires indexing."
                ),
                recommended_action=f"Index these {kind.lower()} documents to enable content checks.",
                evidence=[
                    Evidence("DOCUMENT", item["id"], item["title"], {"indexStatus": item.get("indexStatus")})
                    for item in unindexed[:10]
                ],
                affected={"documents": [item["id"] for item in unindexed]},
            ))

    # Only where a genuine relationship exists is content actually compared.
    comparable = [
        item for kind in ("SPECIFICATION", "BOQ", "CONTRACT")
        for item in by_kind.get(kind, []) if item.get("indexStatus") == "READY"
    ]
    if len(comparable) >= 2:
        answer = context.data("query_project_knowledge", {
            "question": "What material grades, tolerances or quantities are specified?",
        })
        if answer.get("found"):
            findings.append(AgentFinding(
                code="DOCUMENT_REQUIREMENTS_RETRIEVED", certainty=Certainty.FACT,
                severity="INFO", confidence=1.0,
                title="Specification requirements were retrieved for review",
                description=(answer.get("answer") or "")[:1000],
                reason="Retrieved from indexed documents of governing kinds, with citations.",
                recommended_action=(
                    "Review the cited passages against each other; automated contradiction "
                    "detection between passages is not implemented."
                ),
                evidence=[
                    Evidence(citation.get("sourceType", "DOCUMENT"), str(citation.get("sourceId")),
                             citation.get("title") or "Cited passage",
                             {"page": citation.get("page"), "snippet": citation.get("snippet")})
                    for citation in (answer.get("citations") or [])[:10]
                ] or [Evidence("DOCUMENT", comparable[0]["id"], comparable[0]["title"], {})],
                affected={"documents": [item["id"] for item in comparable]},
            ))
    elif len(comparable) == 1:
        findings.append(_uncertain(
            "DOCUMENT_COMPARISON_NOT_POSSIBLE", "Only one indexed governing document",
            "Consistency needs at least two related documents to compare; only one "
            "specification, BOQ or contract is indexed.",
            "Index a second related document to enable comparison.",
        ))
    return findings


# --- 3. Revision Impact Agent -----------------------------------------------

def revision_impact_agent(context) -> list[AgentFinding]:
    """What a revision may have affected — never asserted without evidence."""
    analysis = context.data("analyze_ifc")
    changes = context.data("get_design_changes", {"limit": 30}).get("designChanges", [])

    if not analysis and not changes:
        return [_uncertain(
            "NO_REVISIONS_AVAILABLE", "No revisions to assess",
            "This project has no processed IFC revision and no design changes readable "
            "by this caller.",
            "Upload a model revision or raise a design change.",
        )]

    findings: list[AgentFinding] = []

    if analysis:
        interference = analysis.get("interference") or {}
        counts = analysis.get("findingsBySeverity") or {}
        serious = counts.get("HIGH", 0) + counts.get("CRITICAL", 0)
        if serious:
            findings.append(AgentFinding(
                code="REVISION_CARRIES_SERIOUS_FINDINGS", certainty=Certainty.DETECTED,
                severity="HIGH", confidence=0.9,
                title=f"The current revision carries {serious} high-severity coordination finding(s)",
                description=(
                    f"Revision {analysis.get('revision')} has {analysis.get('findingCount')} "
                    f"coordination findings, {serious} of them high severity or above."
                ),
                reason="Counted from stored coordination findings on the active revision.",
                recommended_action="Review the findings before issuing this revision for construction.",
                evidence=[Evidence("IFC_VERSION", analysis["versionId"],
                                   f"Revision {analysis.get('revision')}",
                                   {"findingsBySeverity": counts, "interference": interference})],
                affected={"ifcVersions": [analysis["versionId"]]},
            ))
        elif interference.get("analysed") is False:
            findings.append(_uncertain(
                "REVISION_NOT_ANALYSED", "The revision was not fully analysed",
                f"Interference analysis did not run: {interference.get('skippedReason')}.",
                "Check that geometry processing succeeded for this revision.",
            ))

    # A design change declaring schedule impact, against real tasks.
    tasks = context.data("get_tasks", {"limit": 200}).get("tasks", [])
    open_tasks = [task for task in tasks if task.get("status") not in {"done", "cancelled"}]
    for change in changes:
        impact_days = change.get("expectedScheduleImpactDays")
        if not impact_days:
            continue
        disciplines = change.get("affectedDisciplines") or []
        findings.append(AgentFinding(
            code="REVISION_DECLARES_SCHEDULE_IMPACT", certainty=Certainty.FACT,
            severity="HIGH" if impact_days >= 7 else "MEDIUM", confidence=1.0,
            title=f"Design change {change['title']!r} declares {impact_days} day(s) of schedule impact",
            description=(
                f"The change states a {impact_days}-day impact affecting "
                f"{', '.join(disciplines) or 'unspecified disciplines'}."
            ),
            reason="Read from the design change's own declared impact field.",
            recommended_action="Reflect the declared impact in the affected tasks' dates.",
            evidence=[Evidence("DESIGN_CHANGE", change["id"], change["title"], {
                "scheduleImpactDays": impact_days,
                "costImpact": change.get("expectedCostImpact"),
                "affectedDisciplines": disciplines,
                "status": change.get("status"),
            })],
            affected={"designChanges": [change["id"]]},
            potential_impact=f"Up to {impact_days} days on dependent work.",
        ))
        # Which open work it might touch — inference, and labelled as such.
        candidates = [
            task for task in open_tasks
            if change.get("taskId") == task["id"]
        ]
        if candidates:
            findings.append(AgentFinding(
                code="REVISION_LINKED_TASK_AT_RISK", certainty=Certainty.INFERRED,
                severity="MEDIUM", confidence=0.7,
                title=f"Open work is linked to design change {change['title']!r}",
                description=f"{len(candidates)} open task(s) are linked to this change.",
                reason=(
                    "The link is explicit in the record, but whether the change actually "
                    "disrupts the work is a judgement the platform cannot make."
                ),
                recommended_action="Confirm whether these tasks need rescheduling.",
                evidence=[Evidence("TASK", task["id"], task["name"], {"status": task.get("status")})
                          for task in candidates],
                affected={"tasks": [task["id"] for task in candidates]},
                related_task_ids=[task["id"] for task in candidates],
            ))
    return findings


# --- 4. RFI Agent -----------------------------------------------------------

#: This platform has no RFI entity. `docs/NOTIFICATIONS.md` records the
#: decision: a design change is the flow where one discipline raises something
#: another must review and respond to, so that is what this agent reads. Every
#: finding says so, rather than letting a reader assume an RFI table exists.
RFI_CARRIER = "design change"

#: Days after which a proposed change awaiting response is treated as overdue.
RFI_OVERDUE_DAYS = 7


def rfi_agent(context) -> list[AgentFinding]:
    """Unanswered and overdue requests, and recurring clarification areas."""
    changes = context.data("get_design_changes", {"limit": 50}).get("designChanges", [])
    if not changes:
        return [_uncertain(
            "NO_RFIS_AVAILABLE", "No requests to assess",
            f"This project has no {RFI_CARRIER} records readable by this caller. "
            "This platform records requests for information as design changes.",
            f"Raise a {RFI_CARRIER} when a clarification is needed.",
        )]

    findings: list[AgentFinding] = []
    awaiting = [change for change in changes if (change.get("status") or "").upper() == "PROPOSED"]

    overdue = []
    for change in awaiting:
        raised = change.get("createdAt")
        if not raised:
            continue
        try:
            age = (_today() - datetime.fromisoformat(str(raised).replace("Z", "+00:00")).date()).days
        except ValueError:
            continue
        if age >= RFI_OVERDUE_DAYS:
            overdue.append((change, age))

    if overdue:
        findings.append(AgentFinding(
            code="RFI_OVERDUE", certainty=Certainty.DETECTED,
            severity="HIGH" if len(overdue) >= 3 else "MEDIUM",
            confidence=0.9,
            title=f"{len(overdue)} request(s) have been awaiting a response for {RFI_OVERDUE_DAYS}+ days",
            description=(
                f"These {RFI_CARRIER} records are still PROPOSED and have not been "
                f"reviewed. This platform records requests for information as {RFI_CARRIER}s."
            ),
            reason=(
                f"Counted from status and age. A request left unanswered for "
                f"{RFI_OVERDUE_DAYS} days blocks whoever raised it."
            ),
            recommended_action="Assign a reviewer to each outstanding request.",
            evidence=[
                Evidence("DESIGN_CHANGE", change["id"], change["title"],
                         {"ageDays": age, "status": change.get("status"),
                          "sourceDiscipline": change.get("sourceDiscipline")})
                for change, age in overdue[:10]
            ],
            affected={"designChanges": [change["id"] for change, _ in overdue]},
        ))
    elif awaiting:
        findings.append(AgentFinding(
            code="RFI_AWAITING_RESPONSE", certainty=Certainty.FACT,
            severity="INFO", confidence=1.0,
            title=f"{len(awaiting)} request(s) are awaiting a response",
            description=f"These {RFI_CARRIER} records are proposed and not yet reviewed.",
            reason="Read from status; none has passed the overdue threshold.",
            recommended_action="No action needed yet; they are within the response window.",
            evidence=[Evidence("DESIGN_CHANGE", change["id"], change["title"],
                               {"status": change.get("status")})
                      for change in awaiting[:10]],
            affected={"designChanges": [change["id"] for change in awaiting]},
        ))

    # Repeated source disciplines: where clarification keeps being needed.
    by_discipline = Counter(
        change.get("sourceDiscipline") for change in changes if change.get("sourceDiscipline")
    )
    for discipline, count in by_discipline.most_common(1):
        if count >= 3:
            related = [c for c in changes if c.get("sourceDiscipline") == discipline]
            findings.append(AgentFinding(
                code="RFI_RECURRING_AREA", certainty=Certainty.INFERRED,
                severity="MEDIUM", confidence=0.65,
                title=f"{count} requests originate from {discipline}",
                description=f"{discipline} has raised {count} requests on this project.",
                reason=(
                    "A concentration of requests from one discipline often indicates unclear "
                    "documentation in that area. It can equally mean that discipline is simply "
                    "the most active, which is why this is an inference."
                ),
                recommended_action=f"Review whether {discipline} documentation needs clarification.",
                evidence=[Evidence("DESIGN_CHANGE", change["id"], change["title"],
                                   {"sourceDiscipline": discipline})
                          for change in related[:10]],
                affected={"designChanges": [change["id"] for change in related]},
            ))
    return findings


# --- 5. Schedule Risk Agent -------------------------------------------------

def schedule_risk_agent(context) -> list[AgentFinding]:
    """Risk on top of the existing scheduling data, not a replacement for it.

    The platform already computes the critical path in `cpm_service`. This
    reads task state and looks for the conditions that make a schedule
    unreliable; it does not recompute dates or reschedule anything.
    """
    tasks = context.data("get_tasks", {"limit": 200}).get("tasks", [])
    if not tasks:
        return [_uncertain(
            "NO_TASKS_AVAILABLE", "No tasks to assess",
            "No tasks in this project are readable by this caller, so schedule risk "
            "cannot be assessed.",
            "Check whether your role can see this project's tasks.",
        )]

    findings: list[AgentFinding] = []
    today = _today()
    open_tasks = [task for task in tasks if task.get("status") not in {"done", "cancelled"}]

    def parse(value):
        try:
            return date.fromisoformat(value) if value else None
        except (TypeError, ValueError):
            return None

    overdue = [
        task for task in open_tasks
        if (end := parse(task.get("plannedEndDate"))) and end < today
    ]
    if overdue:
        findings.append(AgentFinding(
            code="SCHEDULE_TASKS_OVERDUE", certainty=Certainty.FACT,
            severity="HIGH" if len(overdue) >= 3 else "MEDIUM", confidence=1.0,
            title=f"{len(overdue)} task(s) are past their planned end date",
            description="These tasks are not complete and their planned end date has passed.",
            reason="Read from planned end dates against today; nothing is inferred.",
            recommended_action="Reschedule or escalate each overdue task.",
            evidence=[
                Evidence("TASK", task["id"], task["name"], {
                    "plannedEndDate": task.get("plannedEndDate"),
                    "status": task.get("status"),
                    "progressPercentage": task.get("progressPercentage"),
                })
                for task in overdue[:15]
            ],
            affected={"tasks": [task["id"] for task in overdue]},
            related_task_ids=[task["id"] for task in overdue],
        ))

    # Started long ago, barely moved: at risk before it is overdue.
    stalled = [
        task for task in open_tasks
        if task.get("status") == "in_progress"
        and (task.get("progressPercentage") or 0) < 25
        and (start := parse(task.get("plannedStartDate")))
        and (today - start).days >= 14
    ]
    if stalled:
        findings.append(AgentFinding(
            code="SCHEDULE_TASKS_STALLED", certainty=Certainty.INFERRED,
            severity="MEDIUM", confidence=0.7,
            title=f"{len(stalled)} task(s) appear stalled",
            description=(
                "These tasks started at least two weeks ago and are still below 25% progress."
            ),
            reason=(
                "Low progress over an extended period usually indicates a blockage, but "
                "progress may simply not have been recorded — which is why this is inferred "
                "rather than stated."
            ),
            recommended_action="Confirm whether these are blocked or just unreported.",
            evidence=[
                Evidence("TASK", task["id"], task["name"], {
                    "plannedStartDate": task.get("plannedStartDate"),
                    "progressPercentage": task.get("progressPercentage"),
                })
                for task in stalled[:15]
            ],
            affected={"tasks": [task["id"] for task in stalled]},
            related_task_ids=[task["id"] for task in stalled],
        ))

    blocked = [task for task in open_tasks if task.get("status") == "blocked"]
    if blocked:
        findings.append(AgentFinding(
            code="SCHEDULE_TASKS_BLOCKED", certainty=Certainty.FACT,
            severity="HIGH", confidence=1.0,
            title=f"{len(blocked)} task(s) are marked blocked",
            description="These tasks carry the blocked status.",
            reason="Read from task status.",
            recommended_action="Resolve the blockers or reschedule the dependent work.",
            evidence=[Evidence("TASK", task["id"], task["name"], {"status": "blocked"})
                      for task in blocked[:15]],
            affected={"tasks": [task["id"] for task in blocked]},
            related_task_ids=[task["id"] for task in blocked],
        ))

    # Open work with no dates at all cannot be assessed, and that is a finding.
    undated = [task for task in open_tasks if not task.get("plannedEndDate")]
    if undated and len(undated) == len(open_tasks):
        findings.append(_uncertain(
            "SCHEDULE_NO_DATES", "No open task carries a planned end date",
            f"All {len(undated)} open tasks are undated, so schedule risk cannot be assessed.",
            "Add planned dates so schedule risk can be evaluated.",
        ))
    elif undated:
        findings.append(AgentFinding(
            code="SCHEDULE_TASKS_UNDATED", certainty=Certainty.DETECTED,
            severity="LOW", confidence=0.9,
            title=f"{len(undated)} open task(s) have no planned end date",
            description="These tasks cannot contribute to schedule analysis.",
            reason="Counted from tasks with no planned end date.",
            recommended_action="Add planned dates to these tasks.",
            evidence=[Evidence("TASK", task["id"], task["name"], {"plannedEndDate": None})
                      for task in undated[:15]],
            affected={"tasks": [task["id"] for task in undated]},
        ))

    # What the Site Report Agent already concluded, read the same way a person
    # would — through a tool, gated on the same permission as the review queue.
    # This is the only sanctioned form of agent-to-agent consumption: no direct
    # call, no shared state, and it degrades to nothing if the tool is refused.
    site_findings = context.data("get_findings", {
        "sourceEngine": "SITE_REPORT_AGENT_V1", "limit": 50,
    }).get("findings", [])
    reported_delays = [
        item for item in site_findings
        if item.get("type") == "SITE_REPORTED_DELAYS" and item.get("status") in {"NEW", "OPEN"}
    ]
    if reported_delays and not overdue:
        findings.append(AgentFinding(
            code="SCHEDULE_SITE_DELAYS_NOT_REFLECTED", certainty=Certainty.INFERRED,
            severity="MEDIUM", confidence=0.65,
            title="Site reports record delays that the schedule does not show",
            description=(
                "The Site Report Agent found delays recorded on site, but no task is "
                "past its planned end date."
            ),
            reason=(
                "Either the schedule has not been updated to reflect what site is "
                "reporting, or the delays are being absorbed within float. The records "
                "alone cannot distinguish the two, so this is an inference."
            ),
            recommended_action="Check whether the reported delays need reflecting in the dates.",
            evidence=[
                Evidence("AI_INSIGHT", item["id"], item["title"],
                         {"severity": item.get("severity"), "sourceEngine": item.get("sourceEngine")})
                for item in reported_delays[:5]
            ],
        ))

    # Delays reported on site that the schedule does not reflect.
    reports = context.data("get_site_reports", {"limit": 15}).get("reports", [])
    if reports and not overdue and not blocked:
        findings.append(_uncertain(
            "SCHEDULE_SITE_CROSS_CHECK_INCONCLUSIVE",
            "Site reports exist but no schedule slippage is recorded",
            "Site reports have been filed and no task is overdue or blocked. Whether "
            "reported site conditions have affected the schedule cannot be determined "
            "from task records alone.",
            "Compare the latest site reports against the schedule manually.",
        ))
    return findings
