59 permissions — backend-only: 13, enforced+tested: 46

| Code | Scope | Default roles | Backend | Web | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `platform.manage_users` | platform | 2 | backend/app/api/organization.py:364 (+1) +8 | frontend/src/app/router/index.tsx:134 (+1) +4 | 13 backend / 3 web | enforced+tested |
| `platform.manage_permissions` | platform | 2 | backend/app/api/permissions.py:3 (+1) +2 | frontend/src/app/router/index.tsx:142 +1 | 7 backend / 1 web | enforced+tested |
| `platform.create_project` | platform | 3 | backend/app/api/projects.py:326 +3 | frontend/src/features/dashboard/DashboardSelectorPage.tsx:60 +1 | 7 backend / 3 web | enforced+tested |
| `platform.view_all_projects` | platform | 3 | backend/app/api/audit_logs.py:15 +5 | frontend/src/features/projects/pages/ProjectsPage.tsx:96 | 9 backend / 0 web | enforced+tested |
| `platform.work_in_all_projects` | platform | 2 | backend/app/api/cost_validations.py:25 +6 | — | 6 backend / 0 web | backend-only |
| `project.manage_members` | project-record | 4 | backend/app/api/projects.py:315 (+12) +7 | frontend/src/app/router/index.tsx:148 (+2) +7 | 11 backend / 5 web | enforced+tested |
| `project.edit` | project-record | 3 | backend/app/api/attachments.py:286 +4 | frontend/src/features/projects/pages/ProjectTeamPage.tsx:39 (+1) +1 | 8 backend / 0 web | enforced+tested |
| `project.manage_reminders` | project | 4 | backend/app/api/collaboration.py:435 (+2) | — | 2 backend / 0 web | backend-only |
| `project.delete` | project-record | 2 | backend/app/api/projects.py:318 (+3) +1 | frontend/src/features/projects/components/DeleteProjectDialog.tsx:15 +3 | 8 backend / 1 web | enforced+tested |
| `task.view` | project | 17 | backend/app/api/tasks.py:72 (+1) +4 | frontend/src/app/router/index.tsx:169 (+3) +5 | 10 backend / 9 web | enforced+tested |
| `task.create` | project | 4 | backend/app/api/ai_intelligence.py:202 (+1) +6 | frontend/src/features/ai-intelligence/pages/AIIntelligencePage.tsx:62 (+1) +1 | 8 backend / 0 web | enforced+tested |
| `task.edit` | project | 4 | backend/app/api/documents.py:185 (+1) +7 | frontend/src/features/tasks/pages/TaskDetailPage.tsx:31 (+2) +1 | 5 backend / 2 web | enforced+tested |
| `task.update_progress` | project | 14 | backend/app/ai/action_rules.py:12 (+2) +6 | frontend/src/features/tasks/pages/TaskDetailPage.tsx:68 | 6 backend / 1 web | enforced+tested |
| `task.view_all` | project | 6 | backend/app/api/collaboration.py:315 (+1) +5 | frontend/src/app/router/index.tsx:169 (+1) +7 | 4 backend / 4 web | enforced+tested |
| `task.review` | project | 12 | backend/app/api/attachments.py:68 (+1) +11 | frontend/src/app/router/index.tsx:226 (+1) +6 | 7 backend / 3 web | enforced+tested |
| `schedule.view` | project | 6 | backend/app/api/scheduling.py:26 (+3) +1 | frontend/src/app/router/index.tsx:207 (+1) +4 | 4 backend / 2 web | enforced+tested |
| `schedule.edit` | project | 4 | backend/app/api/ifc.py:701 (+1) +5 | frontend/src/features/milestones/pages/MilestonesPage.tsx:32 +1 | 10 backend / 0 web | enforced+tested |
| `site_visit.schedule` | project | 14 | backend/app/api/collaboration.py:312 (+2) | frontend/src/features/collaboration/pages/CollaborationPage.tsx:206 | 3 backend / 0 web | enforced+tested |
| `site_report.submit` | project | 11 | backend/app/ai/action_rules.py:17 +5 | frontend/src/features/site-reports/pages/SiteReportsPage.tsx:135 | 6 backend / 0 web | enforced+tested |
| `site_report.verify` | project | 1 | backend/app/api/site_reports.py:304 (+2) | frontend/src/features/site-reports/pages/SiteReportsPage.tsx:65 (+1) | 4 backend / 0 web | enforced+tested |
| `issue.create` | project | 15 | backend/app/ai/action_rules.py:16 +5 | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:66 (+1) +2 | 8 backend / 2 web | enforced+tested |
| `issue.resolve` | project | 4 | backend/app/api/issues.py:165 (+8) +2 | frontend/src/features/issues/pages/IssuesPage.tsx:33 | 5 backend / 0 web | enforced+tested |
| `owner_request.create` | project | 5 | backend/app/api/collaboration.py:144 | frontend/src/features/collaboration/pages/CollaborationPage.tsx:207 | 4 backend / 0 web | enforced+tested |
| `owner_request.review` | project | 14 | backend/app/api/collaboration.py:195 (+1) | frontend/src/features/collaboration/pages/CollaborationPage.tsx:208 | 1 backend / 0 web | enforced+tested |
| `design_change.propose` | project | 14 | backend/app/api/collaboration.py:239 (+1) +5 | frontend/src/features/design-changes/pages/DesignChangesPage.tsx:76 | 3 backend / 0 web | enforced+tested |
| `cost_validation.review` | project | 14 | backend/app/api/cost_validations.py:110 (+1) +1 | — | 7 backend / 0 web | backend-only |
| `design_change.approve` | project | 7 | backend/app/api/design_changes.py:283 (+3) | frontend/src/features/admin/pages/AccessControlPage.tsx:36 +1 | 7 backend / 0 web | enforced+tested |
| `ifc.view` | project | 16 | backend/app/services/agents/registry.py:56 +2 | frontend/src/app/router/index.tsx:211 +3 | 5 backend / 3 web | enforced+tested |
| `ifc.upload` | project | 14 | backend/app/services/ifc_policy.py:6 (+1) | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:62 | 2 backend / 0 web | enforced+tested |
| `ifc.manage_version` | project | 5 | backend/app/services/ifc_policy.py:6 (+2) | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:63 (+1) +1 | 2 backend / 0 web | enforced+tested |
| `document.upload` | project | 14 | backend/app/api/__init__.py:90 +3 | frontend/src/app/router/index.tsx:28 +2 | 4 backend / 1 web | enforced+tested |
| `ai.view_insights` | project | 16 | backend/app/api/ai_actions.py:29 (+1) +3 | frontend/src/app/router/index.tsx:214 +2 | 3 backend / 2 web | enforced+tested |
| `ai.review_insight` | project | 15 | backend/app/api/ai_intelligence.py:167 +2 | — | 5 backend / 0 web | backend-only |
| `ai.promote_insight` | project | 14 | backend/app/api/ai_intelligence.py:185 | frontend/src/features/ai-intelligence/pages/AIIntelligencePage.tsx:61 (+1) | 4 backend / 0 web | enforced+tested |
| `agents.view` | project | 1 | backend/app/api/agents.py:30 (+1) | frontend/src/app/router/index.tsx:217 (+2) +2 | 5 backend / 2 web | enforced+tested |
| `org.manage_roles` | platform | 3 | backend/app/api/organization.py:49 | frontend/src/app/router/PermissionGuard.tsx:8 +3 | 4 backend / 1 web | enforced+tested |
| `org.manage_disciplines` | platform | 3 | backend/app/api/organization.py:50 | frontend/src/app/router/index.tsx:145 | 3 backend / 0 web | enforced+tested |
| `org.manage_settings` | platform | 3 | backend/app/api/company.py:5 (+2) +1 | — | 3 backend / 0 web | backend-only |
| `project.manage_parties` | project-record | 4 | backend/app/api/organization.py:552 (+2) | frontend/src/app/router/index.tsx:151 (+2) +3 | 4 backend / 1 web | enforced+tested |
| `project.invite_external` | project-record | 4 | backend/app/api/projects.py:744 | — | 4 backend / 0 web | backend-only |
| `document.share_external` | project | 5 | backend/app/api/documents.py:279 (+2) | frontend/src/features/documents/components/DocumentList.tsx:139 +1 | 3 backend / 0 web | enforced+tested |
| `project.view_all_disciplines` | project | 13 | backend/app/api/field_assistant.py:37 +3 | — | 2 backend / 0 web | backend-only |
| `field_evidence.submit` | project | 11 | backend/app/models/field_submission.py:21 +4 | — | 8 backend / 0 web | backend-only |
| `field_evidence.verify` | project | 11 | backend/app/services/field_submission_authorization.py:6 (+2) +1 | frontend/src/app/router/index.tsx:235 +2 | 5 backend / 1 web | enforced+tested |
| `ifc.compare` | project | 15 | backend/app/services/ifc_policy.py:34 | — | 2 backend / 0 web | backend-only |
| `ifc.review_finding` | project | 15 | backend/app/services/ifc_policy.py:35 | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:64 (+1) +1 | 2 backend / 0 web | enforced+tested |
| `ifc.review_suggestion` | project | 14 | backend/app/services/ifc_policy.py:36 | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:63 | 2 backend / 0 web | enforced+tested |
| `ifc.download` | project | 15 | backend/app/services/ifc_policy.py:38 | frontend/src/features/ifc/pages/IFCWorkspacePage.tsx:71 (+1) +1 | 2 backend / 0 web | enforced+tested |
| `ifc.manage_link` | project | 14 | backend/app/services/ifc_policy.py:37 | — | 2 backend / 0 web | backend-only |
| `document.view` | project | 16 | backend/app/api/__init__.py:90 +3 | frontend/src/app/router/index.tsx:194 (+1) +2 | 7 backend / 4 web | enforced+tested |
| `site_report.view` | project | 16 | backend/app/api/site_reports.py:40 +1 | frontend/src/app/router/index.tsx:197 (+1) +3 | 4 backend / 2 web | enforced+tested |
| `issue.view` | project | 16 | backend/app/api/issues.py:34 | frontend/src/app/router/index.tsx:200 (+1) +3 | 4 backend / 3 web | enforced+tested |
| `design_change.view` | project | 16 | backend/app/api/design_changes.py:27 | frontend/src/app/router/index.tsx:203 (+1) +3 | 4 backend / 2 web | enforced+tested |
| `client_portal.view` | project | 4 | backend/app/api/projects.py:1063 (+1) +2 | frontend/src/app/router/index.tsx:122 (+1) +2 | 3 backend / 1 web | enforced+tested |
| `task.add_note` | project | 14 | backend/app/services/voice_capabilities.py:215 | — | 2 backend / 0 web | backend-only |
| `task.comment` | project | 14 | backend/app/ai/action_rules.py:15 +2 | — | 2 backend / 0 web | backend-only |
| `message.send` | project | 15 | backend/app/api/messages.py:455 (+1) +1 | frontend/src/features/messages/components/ContextDiscussion.tsx:19 (+1) +1 | 2 backend / 1 web | enforced+tested |
| `message.send_client` | project | 14 | backend/app/api/messages.py:488 (+1) +1 | — | 2 backend / 0 web | backend-only |
| `message.broadcast` | project | 4 | backend/app/services/authorization.py:101 +1 | frontend/src/features/messages/pages/MessagesPage.tsx:357 | 6 backend / 1 web | enforced+tested |
