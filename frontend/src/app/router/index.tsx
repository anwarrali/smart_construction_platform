import { lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ROUTES } from "../../utils/constants";
import { ProtectedRoute } from "./ProtectedRoute";
import { PermissionGuard } from "./PermissionGuard";
import { OfficeRolesPage } from "../../features/admin/pages/OfficeRolesPage";
import {
  LEGACY_PROJECT_PREFIXES,
  LegacyProjectPrefixRedirect,
} from "./LegacyProjectPrefixRedirect";
import { PublicLayout } from "../../layouts/PublicLayout";
import { DashboardLayout } from "../../layouts/DashboardLayout";
import { AuthLayout } from "../../layouts/AuthLayout";
import { NotFoundPage } from "../../pages/NotFound/NotFoundPage";
import { WebPushBridge } from "./WebPushBridge";

/*
 * ## One workspace, one URL
 *
 * A project used to be reachable at four addresses -
 * `/project-manager/projects/:id/...`, `/engineer/projects/:id/...`,
 * `/consultant-engineer/projects/:id/...` and `/projects/:id/...` - chosen by
 * the signed-in person's role. They rendered *the same components*: TasksPage
 * at all four, DocumentsPage at all four. What differed was the guard on each
 * copy, and those differed from each other by accident rather than by design -
 * which is how an office's own internal engineer ended up holding
 * `document.upload` with no documents page anywhere to upload from.
 *
 * There is one address now, `/projects/:projectId/...`, and what somebody may
 * do inside it is decided by permission - the same permission the endpoint
 * behind the page checks. Roles are configured by the office, so a URL keyed
 * on a role name could not have survived the redesign in any case: no route
 * table can anticipate "Resident Engineer".
 *
 * The retired prefixes stay registered, as redirects. They are in push
 * notifications already delivered, in bookmarks and in history, and a 404 on
 * one of them is a regression no matter how much tidier the table looks.
 *
 * Every route destination below is lazy: each `import()` becomes its own
 * chunk, fetched only when a person actually navigates there, instead of one
 * ~1.9MB bundle up front. Layouts, guards and NotFoundPage stay eager — they
 * are needed on (almost) every load, or in NotFoundPage's case are tiny
 * enough that splitting them out would not be worth a second request.
 * DashboardLayout/PublicLayout/AuthLayout each wrap their own `<Outlet/>` in
 * a `<Suspense>`, so the chrome around a lazy page never disappears while its
 * chunk loads.
 */

/* ── Public pages ── */
const LandingPage = lazy(() => import("../../pages/landing/LandingPage").then((m) => ({ default: m.LandingPage })));
const LoginPage = lazy(() => import("../../pages/auth/LoginPage").then((m) => ({ default: m.LoginPage })));
const ForgotPasswordPage = lazy(() => import("../../pages/auth/ForgotPasswordPage").then((m) => ({ default: m.ForgotPasswordPage })));
const ResetPasswordPage = lazy(() => import("../../pages/auth/ResetPasswordPage").then((m) => ({ default: m.ResetPasswordPage })));

/* ── Dashboard selector ── */
const DashboardSelectorPage = lazy(() => import("../../features/dashboard/DashboardSelectorPage").then((m) => ({ default: m.DashboardSelectorPage })));

/* ── Role-specific dashboards ── */
const OwnerDashboard = lazy(() => import("../../features/dashboard/owner/pages/OwnerDashboard").then((m) => ({ default: m.OwnerDashboard })));
const ExecutiveOverviewPage = lazy(() => import("../../features/dashboard/owner/pages/ExecutiveOverviewPage").then((m) => ({ default: m.ExecutiveOverviewPage })));
const AdminDashboard = lazy(() => import("../../features/dashboard/admin/pages/AdminDashboard").then((m) => ({ default: m.AdminDashboard })));
const AccessControlPage = lazy(() => import("../../features/admin/pages/AccessControlPage").then((m) => ({ default: m.AccessControlPage })));
const EngineerDashboard = lazy(() => import("../../features/dashboard/engineer/pages/EngineerDashboard").then((m) => ({ default: m.EngineerDashboard })));
const ConsultantDashboard = lazy(() => import("../../features/dashboard/consultant/pages/ConsultantDashboard").then((m) => ({ default: m.ConsultantDashboard })));
const ConsultantReviewsPage = lazy(() => import("../../features/dashboard/consultant/pages/ConsultantReviewsPage").then((m) => ({ default: m.ConsultantReviewsPage })));
const ConsultantReviewDetailPage = lazy(() => import("../../features/dashboard/consultant/pages/ConsultantReviewDetailPage").then((m) => ({ default: m.ConsultantReviewDetailPage })));

/* ── Feature pages ── */
const ProjectsPage = lazy(() => import("../../features/projects/pages/ProjectsPage").then((m) => ({ default: m.ProjectsPage })));
const ProjectDetailPage = lazy(() => import("../../features/projects/pages/ProjectDetailPage").then((m) => ({ default: m.ProjectDetailPage })));
const ProjectSchedulePage = lazy(() => import("../../features/projects/pages/ProjectSchedulePage").then((m) => ({ default: m.ProjectSchedulePage })));
const TasksPage = lazy(() => import("../../features/tasks/pages/TasksPage").then((m) => ({ default: m.TasksPage })));
const TaskDetailPage = lazy(() => import("../../features/tasks/pages/TaskDetailPage").then((m) => ({ default: m.TaskDetailPage })));
const DocumentsPage = lazy(() => import("../../features/documents/pages/DocumentsPage").then((m) => ({ default: m.DocumentsPage })));
const NotificationsPage = lazy(() => import("../../features/notifications/pages/NotificationsPage").then((m) => ({ default: m.NotificationsPage })));
const NotificationRedirectPage = lazy(() => import("../../features/notifications/pages/NotificationRedirectPage").then((m) => ({ default: m.NotificationRedirectPage })));
const UsersPage = lazy(() => import("../../features/users/pages/UserPage").then((m) => ({ default: m.UsersPage })));
const ProfilePage = lazy(() => import("../../features/users/pages/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const IssuesPage = lazy(() => import("../../features/issues/pages/IssuesPage").then((m) => ({ default: m.IssuesPage })));
const DesignChangesPage = lazy(() => import("../../features/design-changes/pages/DesignChangesPage").then((m) => ({ default: m.DesignChangesPage })));
const SiteReportsPage = lazy(() => import("../../features/site-reports/pages/SiteReportsPage").then((m) => ({ default: m.SiteReportsPage })));
const ProjectTeamPage = lazy(() => import("../../features/projects/pages/ProjectTeamPage").then((m) => ({ default: m.ProjectTeamPage })));
const ProjectPartiesPage = lazy(() => import("../../features/projects/pages/ProjectPartiesPage").then((m) => ({ default: m.ProjectPartiesPage })));
const MilestonesPage = lazy(() => import("../../features/milestones/pages/MilestonesPage").then((m) => ({ default: m.MilestonesPage })));
const MessagesPage = lazy(() => import("../../features/messages/pages/MessagesPage").then((m) => ({ default: m.MessagesPage })));
const EvidencePhotoArchivePage = lazy(() => import("../../features/photo-archive/pages/EvidencePhotoArchivePage").then((m) => ({ default: m.EvidencePhotoArchivePage })));
const VoiceReportsPage = lazy(() => import("../../features/voice/pages/VoiceReportsPage").then((m) => ({ default: m.VoiceReportsPage })));
const VoiceAssistantPage = lazy(() => import("../../features/voice/pages/VoiceAssistantPage").then((m) => ({ default: m.VoiceAssistantPage })));
const IFCWorkspacePage = lazy(() => import("../../features/ifc/pages/IFCWorkspacePage").then((m) => ({ default: m.IFCWorkspacePage })));
const AIIntelligencePage = lazy(() => import("../../features/ai-intelligence/pages/AIIntelligencePage").then((m) => ({ default: m.AIIntelligencePage })));
const CollaborationPage = lazy(() => import("../../features/collaboration/pages/CollaborationPage").then((m) => ({ default: m.CollaborationPage })));
const McpClientsPage = lazy(() => import("../../features/settings/pages/McpClientsPage").then((m) => ({ default: m.McpClientsPage })));

export const Router = () => {
  return (
    <BrowserRouter>
      {/* Inside BrowserRouter because it navigates on a notification click.
          Renders nothing. */}
      <WebPushBridge />
      <Routes>
        {/* ── Public ── */}
        <Route element={<PublicLayout />}>
          <Route path={ROUTES.HOME} element={<LandingPage />} />
        </Route>

        {/* ── Auth ── */}
        <Route element={<AuthLayout />}>
          <Route path={ROUTES.LOGIN} element={<LoginPage />} />
          <Route path={ROUTES.FORGOT_PASSWORD} element={<ForgotPasswordPage />} />
          <Route path={ROUTES.RESET_PASSWORD} element={<ResetPasswordPage />} />
        </Route>

        {/* ── Protected / Dashboard shell ── */}
        <Route element={<ProtectedRoute />}>
          <Route element={<DashboardLayout />}>
            {/* Where a sign-in lands. Picks a home by permission. */}
            <Route path={ROUTES.DASHBOARD} element={<DashboardSelectorPage />} />

            {/* ── The client portal ──
                `client_portal.view` is the capability `get_owner_dashboard`
                used to spell as `role in {OWNER, ADMIN}`. Deliberately not
                office-only: the client is an external party, and this is the
                one view that exists for them. */}
            <Route element={<PermissionGuard permissions={["client_portal.view"]} />}>
              <Route path={ROUTES.OWNER_DASHBOARD} element={<OwnerDashboard />} />
              <Route path={ROUTES.EXECUTIVE_OVERVIEW} element={<ExecutiveOverviewPage />} />
            </Route>

            {/* ── Office administration ──
                `platform.manage_users` is what "runs the platform for this
                office" actually names, and it is admin-locked, so an office
                cannot configure itself out of reaching these pages. */}
            <Route element={<PermissionGuard permissions={["platform.manage_users"]} />}>
              <Route path={ROUTES.ADMIN_DASHBOARD} element={<AdminDashboard />} />
              <Route path={ROUTES.USERS}           element={<UsersPage />} />
              <Route path={ROUTES.ADMIN_TEAMS}     element={<ProjectTeamPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["platform.manage_permissions"]} />}>
              <Route path={ROUTES.ADMIN_ACCESS_CONTROL} element={<AccessControlPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["org.manage_roles", "org.manage_disciplines"]} />}>
              <Route path={ROUTES.ADMIN_OFFICE_ROLES} element={<OfficeRolesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_members"]} />}>
              <Route path={ROUTES.ADMIN_PROJECT_TEAM} element={<ProjectTeamPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_parties"]} />}>
              <Route path={ROUTES.ADMIN_PROJECT_TEAM.replace("/team", "/parties")} element={<ProjectPartiesPage />} />
            </Route>

            {/* ── Notification landing ──
                Deliberately ungated. A push notification can only carry an id,
                so this is where a tap lands before the app resolves it to the
                real page, and anybody can receive one. The server has already
                scoped the notification to the caller, so this exposes nothing
                a guard here would protect. */}
            <Route path={ROUTES.NOTIFICATION_DETAIL} element={<NotificationRedirectPage />} />

            {/* ── The shared project workspace ──
                One URL space. Each module names the permission its own API
                checks, so an office that takes IFC away from a role stops
                seeing the tab as well as the data. */}
            <Route path={ROUTES.PROJECTS} element={<ProjectsPage />} />
            <Route element={<PermissionGuard permissions={["task.view"]} />}>
              <Route path={ROUTES.PROJECT_DETAIL}    element={<ProjectDetailPage />} />
              <Route path={ROUTES.PROJECT_DASHBOARD} element={<ProjectDetailPage />} />
              <Route path={ROUTES.PROJECT_MY_WORK}   element={<EngineerDashboard />} />
              <Route path={ROUTES.PROJECT_TASKS}     element={<TasksPage />} />
              <Route path={ROUTES.PROJECT_TASK_DETAIL} element={<TaskDetailPage />} />
              <Route path={ROUTES.PROJECT_MESSAGES}  element={<MessagesPage />} />
              <Route path={ROUTES.PROJECT_NOTIFICATIONS} element={<NotificationsPage />} />
              <Route path={ROUTES.PROJECT_EVIDENCE}  element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.PROJECT_COLLABORATION} element={<CollaborationPage />} />
              <Route path={ROUTES.PROJECT_REQUESTS}  element={<CollaborationPage initialTab="requests" />} />
              <Route path={ROUTES.PROJECT_SITE_VISITS} element={<CollaborationPage initialTab="schedule" />} />
              <Route path={ROUTES.PROJECT_ACTIVITY}  element={<CollaborationPage initialTab="activity" />} />
              <Route path={ROUTES.PROJECT_VOICE_ASSISTANT} element={<VoiceAssistantPage />} />
            </Route>

            {/* The four module-view codes. They name the navigation decision
                the per-role URL table used to make; the endpoints behind them
                have never gated on role, so what each page *shows* is
                unchanged and still scoped per row. */}
            <Route element={<PermissionGuard permissions={["document.view"]} />}>
              <Route path={ROUTES.PROJECT_DOCUMENTS} element={<DocumentsPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["site_report.view"]} />}>
              <Route path={ROUTES.PROJECT_SITE_REPORTS} element={<SiteReportsPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["issue.view"]} />}>
              <Route path={ROUTES.PROJECT_ISSUES} element={<IssuesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["design_change.view"]} />}>
              <Route path={ROUTES.PROJECT_DESIGN_CHANGES} element={<DesignChangesPage />} />
            </Route>

            <Route element={<PermissionGuard permissions={["schedule.view"]} />}>
              <Route path={ROUTES.PROJECT_SCHEDULE}   element={<ProjectSchedulePage />} />
              <Route path={ROUTES.PROJECT_MILESTONES} element={<MilestonesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["ifc.view"]} />}>
              <Route path={ROUTES.PROJECT_IFC} element={<IFCWorkspacePage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["ai.view_insights"]} />}>
              <Route path={ROUTES.PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
            </Route>

            {/* The review queue. `task.review` is office-only, so an external
                participant can never reach it however their role is
                configured. */}
            <Route element={<PermissionGuard permissions={["task.review"]} />}>
              <Route path={ROUTES.PROJECT_REVIEW_QUEUE}   element={<ConsultantDashboard />} />
              <Route path={ROUTES.PROJECT_REVIEWS}        element={<ConsultantReviewsPage />} />
              <Route path={ROUTES.PROJECT_REVIEW_DETAIL}  element={<ConsultantReviewDetailPage />} />
              <Route path={ROUTES.PROJECT_REVIEW_HISTORY} element={<ConsultantReviewsPage history />} />
            </Route>
            <Route element={<PermissionGuard permissions={["field_evidence.verify"]} />}>
              <Route path={ROUTES.PROJECT_VOICE_REPORTS} element={<VoiceReportsPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_members"]} />}>
              <Route path={ROUTES.PROJECT_TEAM} element={<ProjectTeamPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_parties"]} />}>
              <Route path={ROUTES.PROJECT_PARTIES} element={<ProjectPartiesPage />} />
            </Route>

            {/* ── Retired per-role prefixes ──
                Registered so every link that has already been sent keeps
                working. Each redirects into the shared workspace above,
                preserving module, query string and hash. */}
            {LEGACY_PROJECT_PREFIXES.map((prefix) => (
              <Route key={prefix} path={`${prefix}/*`} element={<LegacyProjectPrefixRedirect />} />
            ))}
            {LEGACY_PROJECT_PREFIXES.map((prefix) => (
              <Route key={`${prefix}-root`} path={prefix} element={<LegacyProjectPrefixRedirect />} />
            ))}

            {/* ── Portfolio ──
                The same components as the workspace above, without a project
                selected: each renders a picker and then scopes to the choice.
                They therefore carry the same permission as their in-project
                twin, which is what stops the two disagreeing about who may
                open a page. */}
            <Route element={<PermissionGuard permissions={["task.view"]} />}>
              <Route path={ROUTES.TASKS}       element={<TasksPage />} />
              <Route path={ROUTES.TASK_DETAIL} element={<TaskDetailPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["document.view"]} />}>
              <Route path={ROUTES.DOCUMENTS} element={<DocumentsPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["site_report.view"]} />}>
              <Route path={ROUTES.SITE_REPORTS} element={<SiteReportsPage />} />
              <Route path={ROUTES.REPORTS}      element={<Navigate to={ROUTES.SITE_REPORTS} replace />} />
            </Route>
            <Route element={<PermissionGuard permissions={["issue.view"]} />}>
              <Route path={ROUTES.ISSUES} element={<IssuesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["design_change.view"]} />}>
              <Route path={ROUTES.DESIGN_CHANGES} element={<DesignChangesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["schedule.view"]} />}>
              <Route path={ROUTES.PROJECT_MILESTONES_PORTFOLIO} element={<MilestonesPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_members"]} />}>
              <Route path={ROUTES.TEAM} element={<ProjectTeamPage />} />
            </Route>
            <Route element={<PermissionGuard permissions={["project.manage_parties"]} />}>
              <Route path={ROUTES.TEAM.replace("/team", "/parties")} element={<ProjectPartiesPage />} />
            </Route>

            {/* Everybody signed in: their own notifications, their own
                messages, their own outstanding actions. None of this is
                project-scoped, and each endpoint returns only the caller's own
                rows. */}
            <Route path={ROUTES.NOTIFICATIONS}   element={<NotificationsPage />} />
            <Route path={ROUTES.MESSAGES}        element={<MessagesPage />} />
            <Route path={ROUTES.MY_ACTIONS}      element={<CollaborationPage initialTab="actions" />} />
            <Route path={ROUTES.REQUESTS}        element={<CollaborationPage initialTab="requests" />} />
            <Route path={ROUTES.SCHEDULE}        element={<CollaborationPage initialTab="schedule" />} />
            <Route path={ROUTES.SETTINGS}        element={<ProfilePage />} />
            {/* Deliberately ungated. An MCP client token is one of "their own
                tokens" in the same sense as a device registration: it carries
                its holder's authority and no more, the endpoints return only
                the caller's own rows, and the page explains itself when the
                surface is switched off. A permission here would decide, in the
                client, a question the server already answers. */}
            <Route path={ROUTES.MCP_CLIENTS}     element={<McpClientsPage />} />
            <Route path={ROUTES.CHANGE_PASSWORD} element={<ProfilePage />} />
          </Route>
        </Route>

        {/* ── 404 ── */}
        <Route path={ROUTES.NOT_FOUND} element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to={ROUTES.NOT_FOUND} replace />} />
      </Routes>
    </BrowserRouter>
  );
};
