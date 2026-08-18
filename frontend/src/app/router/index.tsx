import { lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ROUTES } from "../../utils/constants";
import { ProtectedRoute } from "./ProtectedRoute";
import { RoleGuard } from "./RoleGuard";
import { MainContractorEngineerGuard } from "./MainContractorEngineerGuard";
import { ConsultantEngineerGuard } from "./ConsultantEngineerGuard";
import { PublicLayout } from "../../layouts/PublicLayout";
import { DashboardLayout } from "../../layouts/DashboardLayout";
import { AuthLayout } from "../../layouts/AuthLayout";
import { NotFoundPage } from "../../pages/NotFound/NotFoundPage";

/*
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
const UsersPage = lazy(() => import("../../features/users/pages/UserPage").then((m) => ({ default: m.UsersPage })));
const ProfilePage = lazy(() => import("../../features/users/pages/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const IssuesPage = lazy(() => import("../../features/issues/pages/IssuesPage").then((m) => ({ default: m.IssuesPage })));
const DesignChangesPage = lazy(() => import("../../features/design-changes/pages/DesignChangesPage").then((m) => ({ default: m.DesignChangesPage })));
const SiteReportsPage = lazy(() => import("../../features/site-reports/pages/SiteReportsPage").then((m) => ({ default: m.SiteReportsPage })));
const ProjectTeamPage = lazy(() => import("../../features/projects/pages/ProjectTeamPage").then((m) => ({ default: m.ProjectTeamPage })));
const MilestonesPage = lazy(() => import("../../features/milestones/pages/MilestonesPage").then((m) => ({ default: m.MilestonesPage })));
const MessagesPage = lazy(() => import("../../features/messages/pages/MessagesPage").then((m) => ({ default: m.MessagesPage })));
const EvidencePhotoArchivePage = lazy(() => import("../../features/photo-archive/pages/EvidencePhotoArchivePage").then((m) => ({ default: m.EvidencePhotoArchivePage })));
const VoiceReportsPage = lazy(() => import("../../features/voice/pages/VoiceReportsPage").then((m) => ({ default: m.VoiceReportsPage })));
const IFCWorkspacePage = lazy(() => import("../../features/ifc/pages/IFCWorkspacePage").then((m) => ({ default: m.IFCWorkspacePage })));
const AIIntelligencePage = lazy(() => import("../../features/ai-intelligence/pages/AIIntelligencePage").then((m) => ({ default: m.AIIntelligencePage })));
const CollaborationPage = lazy(() => import("../../features/collaboration/pages/CollaborationPage").then((m) => ({ default: m.CollaborationPage })));

export const Router = () => {
  return (
    <BrowserRouter>
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
            {/* Role-based entry */}
            <Route path={ROUTES.DASHBOARD}       element={<DashboardSelectorPage />} />
            <Route element={<RoleGuard allowedRoles={["owner"]} />}>
              <Route path={ROUTES.OWNER_DASHBOARD} element={<OwnerDashboard />} />
              <Route path={ROUTES.EXECUTIVE_OVERVIEW} element={<ExecutiveOverviewPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin"]} />}>
              <Route path={ROUTES.ADMIN_DASHBOARD} element={<AdminDashboard />} />
              <Route path={ROUTES.USERS}           element={<UsersPage />} />
              <Route path={ROUTES.ADMIN_TEAMS}     element={<ProjectTeamPage />} />
              <Route path={ROUTES.ADMIN_ACCESS_CONTROL} element={<AccessControlPage />} />
              <Route path={ROUTES.ADMIN_PROJECT_TEAM} element={<ProjectTeamPage />} />
              <Route path={ROUTES.PROJECT_MILESTONES} element={<MilestonesPage />} />
            </Route>

            {/* Core features */}
            <Route path={ROUTES.PROJECTS}        element={<ProjectsPage />} />
            <Route element={<RoleGuard allowedRoles={["admin", "project_manager", "consultant"]} />}>
              <Route path={ROUTES.PROJECT_DETAIL}  element={<ProjectDetailPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["project_manager"]} />}>
              <Route path={ROUTES.PM_PROJECTS} element={<ProjectsPage />} />
              <Route path={ROUTES.PM_PROJECT_DASHBOARD} element={<ProjectDetailPage />} />
              <Route path={ROUTES.PM_PROJECT_TASKS} element={<TasksPage />} />
              <Route path={ROUTES.PM_PROJECT_TASK_DETAIL} element={<TaskDetailPage />} />
              <Route path={ROUTES.PM_PROJECT_DOCUMENTS} element={<DocumentsPage />} />
              <Route path={ROUTES.PM_PROJECT_SITE_REPORTS} element={<SiteReportsPage />} />
              <Route path={ROUTES.PM_PROJECT_ISSUES} element={<IssuesPage />} />
              <Route path={ROUTES.PM_PROJECT_DESIGN_CHANGES} element={<DesignChangesPage />} />
              <Route path={ROUTES.PM_PROJECT_TEAM} element={<ProjectTeamPage />} />
              <Route path={ROUTES.PM_PROJECT_SCHEDULE} element={<ProjectSchedulePage />} />
              <Route path={ROUTES.PM_PROJECT_MILESTONES} element={<MilestonesPage />} />
              <Route path={ROUTES.PM_PROJECT_MESSAGES} element={<MessagesPage />} />
              <Route path={ROUTES.PM_PROJECT_NOTIFICATIONS} element={<NotificationsPage />} />
              <Route path={ROUTES.PM_PROJECT_EVIDENCE} element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.PM_PROJECT_IFC} element={<IFCWorkspacePage />} />
              <Route path={ROUTES.PM_PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
              <Route path={ROUTES.PM_PROJECT_COLLABORATION} element={<CollaborationPage />} />
              <Route path={ROUTES.PM_PROJECT_REQUESTS} element={<CollaborationPage initialTab="requests" />} />
              <Route path={ROUTES.PM_PROJECT_SITE_VISITS} element={<CollaborationPage initialTab="schedule" />} />
              <Route path={ROUTES.PM_PROJECT_ACTIVITY} element={<CollaborationPage initialTab="activity" />} />
            </Route>
            <Route element={<MainContractorEngineerGuard />}>
              <Route path={ROUTES.ENGINEER_PROJECTS} element={<ProjectsPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_DASHBOARD} element={<EngineerDashboard />} />
              <Route path={ROUTES.ENGINEER_PROJECT_TASKS} element={<TasksPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_TASK_DETAIL} element={<TaskDetailPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_SITE_REPORTS} element={<SiteReportsPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_ISSUES} element={<IssuesPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_DOCUMENTS} element={<DocumentsPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_NOTIFICATIONS} element={<NotificationsPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_EVIDENCE} element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_VOICE_REPORTS} element={<VoiceReportsPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_IFC} element={<IFCWorkspacePage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_MESSAGES} element={<MessagesPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_COLLABORATION} element={<CollaborationPage />} />
              <Route path={ROUTES.ENGINEER_PROJECT_REQUESTS} element={<CollaborationPage initialTab="requests" />} />
              <Route path={ROUTES.ENGINEER_PROJECT_SITE_VISITS} element={<CollaborationPage initialTab="schedule" />} />
              <Route path={ROUTES.ENGINEER_PROJECT_ACTIVITY} element={<CollaborationPage initialTab="activity" />} />
            </Route>
            <Route element={<ConsultantEngineerGuard />}>
              <Route path={ROUTES.CONSULTANT_PROJECTS} element={<ProjectsPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_DASHBOARD} element={<ConsultantDashboard />} />
              <Route path={ROUTES.CONSULTANT_PENDING_REVIEWS} element={<ConsultantReviewsPage />} />
              <Route path={ROUTES.CONSULTANT_REVIEW_DETAIL} element={<ConsultantReviewDetailPage />} />
              <Route path={ROUTES.CONSULTANT_REVIEW_HISTORY} element={<ConsultantReviewsPage history />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_DOCUMENTS} element={<DocumentsPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_SITE_REPORTS} element={<SiteReportsPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_ISSUES} element={<IssuesPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_DESIGN_CHANGES} element={<DesignChangesPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_NOTIFICATIONS} element={<NotificationsPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_EVIDENCE} element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_IFC} element={<IFCWorkspacePage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_MESSAGES} element={<MessagesPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_COLLABORATION} element={<CollaborationPage />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_REQUESTS} element={<CollaborationPage initialTab="requests" />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_SITE_VISITS} element={<CollaborationPage initialTab="schedule" />} />
              <Route path={ROUTES.CONSULTANT_PROJECT_ACTIVITY} element={<CollaborationPage initialTab="activity" />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin", "project_manager", "consultant"]} />}>
              <Route path={ROUTES.PROJECT_SCHEDULE} element={<ProjectSchedulePage />} />
              <Route path={ROUTES.TASKS}           element={<TasksPage />} />
              <Route path={ROUTES.TASK_DETAIL}     element={<TaskDetailPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin", "owner", "project_manager", "consultant"]} />}>
              <Route path={ROUTES.DOCUMENTS}       element={<DocumentsPage />} />
              <Route path={ROUTES.REPORTS}         element={<Navigate to={ROUTES.SITE_REPORTS} replace />} />
              <Route path={ROUTES.NOTIFICATIONS}   element={<NotificationsPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin", "owner", "project_manager", "engineer", "consultant"]} />}>
              <Route path={ROUTES.PROJECT_DASHBOARD} element={<ProjectDetailPage />} />
              <Route path={ROUTES.PROJECT_EVIDENCE} element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.PROJECT_IFC} element={<IFCWorkspacePage />} />
              <Route path={ROUTES.PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
              <Route path={ROUTES.PROJECT_MESSAGES} element={<MessagesPage />} />
              <Route path={ROUTES.PROJECT_REQUESTS} element={<CollaborationPage initialTab="requests" />} />
              <Route path={ROUTES.PROJECT_SITE_VISITS} element={<CollaborationPage initialTab="schedule" />} />
              <Route path={ROUTES.PROJECT_ACTIVITY} element={<CollaborationPage initialTab="activity" />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin"]} />}>
              <Route path={ROUTES.PROJECT_TASKS} element={<TasksPage />} />
              <Route path={ROUTES.PROJECT_TASK_DETAIL} element={<TaskDetailPage />} />
              <Route path={ROUTES.PROJECT_TEAM} element={<ProjectTeamPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin", "owner"]} />}>
              <Route path={ROUTES.PROJECT_DOCUMENTS} element={<DocumentsPage />} />
              <Route path={ROUTES.PROJECT_SITE_REPORTS} element={<SiteReportsPage />} />
              <Route path={ROUTES.PROJECT_ISSUES} element={<IssuesPage />} />
              <Route path={ROUTES.PROJECT_DESIGN_CHANGES} element={<DesignChangesPage />} />
            </Route>
            <Route path={ROUTES.MESSAGES}        element={<MessagesPage />} />
            <Route path={ROUTES.MY_ACTIONS} element={<CollaborationPage initialTab="actions" />} />
            <Route path={ROUTES.REQUESTS} element={<CollaborationPage initialTab="requests" />} />
            <Route path={ROUTES.SCHEDULE} element={<CollaborationPage initialTab="schedule" />} />
            <Route path={ROUTES.PROJECT_COLLABORATION} element={<CollaborationPage />} />
            <Route path={ROUTES.SETTINGS}        element={<ProfilePage />} />
            <Route path={ROUTES.CHANGE_PASSWORD} element={<ProfilePage />} />

            {/* Extended features */}
            <Route element={<RoleGuard allowedRoles={["admin", "project_manager", "consultant"]} />}>
              <Route path={ROUTES.ISSUES}          element={<IssuesPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["admin", "owner", "project_manager", "consultant"]} />}>
              <Route path={ROUTES.SITE_REPORTS}    element={<SiteReportsPage />} />
              <Route path={ROUTES.DESIGN_CHANGES}  element={<DesignChangesPage />} />
            </Route>
            <Route element={<RoleGuard allowedRoles={["project_manager"]} />}>
              <Route path={ROUTES.TEAM} element={<ProjectTeamPage />} />
            </Route>
          </Route>
        </Route>

        {/* ── 404 ── */}
        <Route path={ROUTES.NOT_FOUND} element={<NotFoundPage />} />
        <Route path="*" element={<Navigate to={ROUTES.NOT_FOUND} replace />} />
      </Routes>
    </BrowserRouter>
  );
};
