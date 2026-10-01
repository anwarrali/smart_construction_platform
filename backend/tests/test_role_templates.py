"""Every seeded role template grants exactly what it is written to grant.

The templates are the platform's own statement of what each kind of role does
(`app.core.role_templates`). Pinning the result here makes any change to what a
role grants a deliberate edit in two places, reviewed as such, rather than a
side effect of touching a base set. The sets were captured when templates
stopped deriving their permissions from the retired role enum, and are
identical to what that derivation produced, so the move changed nobody's access.
"""

from app.core.permission_catalogue import BY_CODE
from app.core.role_templates import BY_CODE_TEMPLATE, LEGACY_CONSULTANT_TEMPLATE, TEMPLATES
from app.services import rbac

EXPECTED: dict[str, frozenset[str]] = {
    "org_admin": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "client_portal.view", "cost_validation.review", "design_change.propose",
        "design_change.view", "document.share_external", "document.upload",
        "document.view", "ifc.compare", "ifc.download", "ifc.manage_link",
        "ifc.manage_version", "ifc.review_finding", "ifc.review_suggestion",
        "ifc.upload", "ifc.view", "issue.create", "issue.resolve", "issue.view",
        "message.broadcast", "message.send", "message.send_client",
        "org.manage_disciplines", "org.manage_roles", "org.manage_settings",
        "owner_request.create", "owner_request.review", "platform.create_project",
        "platform.manage_permissions", "platform.manage_users",
        "platform.view_all_projects", "project.delete", "project.edit",
        "project.invite_external", "project.manage_members", "project.manage_parties",
        "project.manage_reminders", "project.view_all_disciplines", "schedule.edit",
        "schedule.view", "site_report.view", "site_visit.schedule", "task.add_note",
        "task.comment", "task.create", "task.edit", "task.review",
        "task.update_progress", "task.view", "task.view_all",
    }),
    "office_director": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "client_portal.view", "cost_validation.review", "design_change.propose",
        "design_change.view", "document.share_external", "document.upload",
        "document.view", "ifc.compare", "ifc.download", "ifc.manage_link",
        "ifc.manage_version", "ifc.review_finding", "ifc.review_suggestion",
        "ifc.upload", "ifc.view", "issue.create", "issue.resolve", "issue.view",
        "message.broadcast", "message.send", "message.send_client",
        "org.manage_disciplines", "org.manage_roles", "org.manage_settings",
        "owner_request.create", "owner_request.review", "platform.create_project",
        "platform.manage_permissions", "platform.manage_users",
        "platform.view_all_projects", "project.delete", "project.edit",
        "project.invite_external", "project.manage_members", "project.manage_parties",
        "project.manage_reminders", "project.view_all_disciplines", "schedule.edit",
        "schedule.view", "site_report.view", "site_visit.schedule", "task.add_note",
        "task.comment", "task.create", "task.edit", "task.review",
        "task.update_progress", "task.view", "task.view_all",
    }),
    "technical_director": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "client_portal.view", "cost_validation.review", "design_change.propose",
        "design_change.view", "document.share_external", "document.upload",
        "document.view", "ifc.compare", "ifc.download", "ifc.manage_link",
        "ifc.manage_version", "ifc.review_finding", "ifc.review_suggestion",
        "ifc.upload", "ifc.view", "issue.create", "issue.resolve", "issue.view",
        "message.broadcast", "message.send", "message.send_client",
        "org.manage_disciplines", "org.manage_roles", "org.manage_settings",
        "owner_request.create", "owner_request.review", "platform.create_project",
        "platform.view_all_projects", "project.edit", "project.invite_external",
        "project.manage_members", "project.manage_parties", "project.manage_reminders",
        "project.view_all_disciplines", "schedule.edit", "schedule.view",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.create", "task.edit", "task.review", "task.update_progress", "task.view",
        "task.view_all",
    }),
    "project_manager": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.propose", "design_change.view",
        "document.share_external", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.manage_version", "ifc.review_finding",
        "ifc.review_suggestion", "ifc.upload", "ifc.view", "issue.create",
        "issue.resolve", "issue.view", "message.broadcast", "message.send",
        "message.send_client", "owner_request.create", "owner_request.review",
        "project.invite_external", "project.manage_members", "project.manage_parties",
        "project.manage_reminders", "project.view_all_disciplines", "schedule.edit",
        "schedule.view", "site_report.submit", "site_report.verify", "site_report.view",
        "site_visit.schedule", "task.add_note", "task.comment", "task.create",
        "task.edit", "task.review", "task.update_progress", "task.view",
        "task.view_all",
    }),
    "senior_engineer": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "site_report.submit", "site_report.view",
        "site_visit.schedule", "task.add_note", "task.comment", "task.review",
        "task.update_progress", "task.view",
    }),
    "engineer": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.review", "task.update_progress", "task.view",
    }),
    "site_engineer": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.review", "task.update_progress", "task.view",
    }),
    "bim_engineer": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.manage_version", "ifc.review_finding",
        "ifc.review_suggestion", "ifc.upload", "ifc.view", "issue.create", "issue.view",
        "message.send", "message.send_client", "owner_request.review",
        "project.view_all_disciplines", "site_report.submit", "site_report.view",
        "site_visit.schedule", "task.add_note", "task.comment", "task.review",
        "task.update_progress", "task.view",
    }),
    "cad_technician": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.propose", "design_change.view",
        "document.upload", "document.view", "field_evidence.submit",
        "field_evidence.verify", "ifc.compare", "ifc.download", "ifc.manage_link",
        "ifc.review_finding", "ifc.review_suggestion", "ifc.upload", "ifc.view",
        "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.update_progress", "task.view",
    }),
    "surveyor": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.propose", "design_change.view",
        "document.upload", "document.view", "field_evidence.submit",
        "field_evidence.verify", "ifc.compare", "ifc.download", "ifc.manage_link",
        "ifc.review_finding", "ifc.review_suggestion", "ifc.upload", "ifc.view",
        "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.update_progress", "task.view",
    }),
    "document_controller": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.propose", "design_change.view",
        "document.share_external", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.update_progress", "task.view",
    }),
    "office_staff": frozenset({
        "task.view",
    }),
    "client_representative": frozenset({
        "ai.view_insights", "client_portal.view", "design_change.view", "document.view",
        "ifc.view", "issue.view", "owner_request.create", "schedule.view",
        "site_report.view", "task.view", "task.view_all",
    }),
    "contractor_representative": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.review", "task.update_progress", "task.view",
    }),
    "subcontractor_representative": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.review", "task.update_progress", "task.view",
    }),
    "external_reviewer": frozenset({
        "ai.promote_insight", "ai.review_insight", "ai.view_insights",
        "cost_validation.review", "design_change.approve", "design_change.propose",
        "design_change.view", "document.upload", "document.view",
        "field_evidence.submit", "field_evidence.verify", "ifc.compare", "ifc.download",
        "ifc.manage_link", "ifc.review_finding", "ifc.review_suggestion", "ifc.upload",
        "ifc.view", "issue.create", "issue.view", "message.send", "message.send_client",
        "owner_request.review", "project.view_all_disciplines", "site_report.submit",
        "site_report.view", "site_visit.schedule", "task.add_note", "task.comment",
        "task.review", "task.update_progress", "task.view",
    }),
    "archived_field_staff": frozenset(),
    "legacy_consultant": frozenset({
        "ai.review_insight", "ai.view_insights", "design_change.view", "document.view",
        "ifc.compare", "ifc.download", "ifc.review_finding", "ifc.view", "issue.create",
        "issue.view", "message.send", "schedule.view", "site_report.view",
        "task.review", "task.view", "task.view_all",
    }),
}


def _all_templates():
    return {t.code: t for t in (*TEMPLATES, LEGACY_CONSULTANT_TEMPLATE)}


def test_every_template_is_pinned():
    assert set(_all_templates()) == set(EXPECTED)
    assert len(EXPECTED) == 18


def test_each_template_grants_exactly_its_pinned_set():
    for code, template in _all_templates().items():
        assert template.permissions() == EXPECTED[code], code


def test_templates_grant_only_catalogued_codes():
    for code, granted in EXPECTED.items():
        assert granted <= set(BY_CODE), (code, granted - set(BY_CODE))


def test_the_archived_template_grants_nothing():
    assert BY_CODE_TEMPLATE["archived_field_staff"].permissions() == set()
    assert BY_CODE_TEMPLATE["archived_field_staff"].is_archived
    assert [t.code for t in _all_templates().values() if t.is_archived] == ["archived_field_staff"]


def test_no_external_template_carries_office_wide_authority():
    """An external role is project-scoped by construction.

    The office-only ceiling is applied later, at resolution
    (`rbac.resolved_permissions` strips the whole `office_only` set from an
    external participant, and `effective_permissions` strips `never_external`
    again after overrides) — so an external template may *list* office work it
    shares a base set with, and still never confer it. That is asserted on
    resolved permissions in test_external_party_isolation.py.
    """
    for template in _all_templates().values():
        if template.is_internal_only:
            continue
        assert not (template.permissions() & rbac.NON_PROJECT_SCOPED), template.code


def test_only_the_office_administrator_template_is_undeletable():
    assert [t.code for t in _all_templates().values() if t.undeletable] == ["org_admin"]
    assert rbac.ADMIN_LOCKED <= EXPECTED["org_admin"]


def test_project_leadership_may_address_the_whole_project():
    holders = {code for code, granted in EXPECTED.items() if "message.broadcast" in granted}
    assert holders == {"org_admin", "office_director", "technical_director", "project_manager"}
