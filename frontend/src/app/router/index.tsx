import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ROUTES } from "../../utils/constants";
import { ProtectedRoute } from "./ProtectedRoute";
import { RoleGuard } from "./RoleGuard";
import { MainContractorEngineerGuard } from "./MainContractorEngineerGuard";
import { ConsultantEngineerGuard } from "./ConsultantEngineerGuard";
import { PublicLayout } from "../../layouts/PublicLayout";
import { DashboardLayout } from "../../layouts/DashboardLayout";
import { AuthLayout } from "../../layouts/AuthLayout";

/* ── Public pages ── */
import { LandingPage } from "../../pages/landing/LandingPage";
import { LoginPage } from "../../pages/auth/LoginPage";
import { ForgotPasswordPage } from "../../pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "../../pages/auth/ResetPasswordPage";
import { NotFoundPage } from "../../pages/NotFound/NotFoundPage";

/* ── Dashboard selector ── */
import { DashboardSelectorPage } from "../../features/dashboard/DashboardSelectorPage";

/* ── Role-specific dashboards ── */
import { OwnerDashboard } from "../../features/dashboard/owner/pages/OwnerDashboard";
import { ExecutiveOverviewPage } from "../../features/dashboard/owner/pages/ExecutiveOverviewPage";
import { AdminDashboard } from "../../features/dashboard/admin/pages/AdminDashboard";
import { EngineerDashboard } from "../../features/dashboard/engineer/pages/EngineerDashboard";
import { ConsultantDashboard } from "../../features/dashboard/consultant/pages/ConsultantDashboard";
import { ConsultantReviewsPage } from "../../features/dashboard/consultant/pages/ConsultantReviewsPage";
import { ConsultantReviewDetailPage } from "../../features/dashboard/consultant/pages/ConsultantReviewDetailPage";

/* ── Feature pages ── */
import { ProjectsPage } from "../../features/projects/pages/ProjectsPage";
import { ProjectDetailPage } from "../../features/projects/pages/ProjectDetailPage";
import { ProjectSchedulePage } from "../../features/projects/pages/ProjectSchedulePage";
import { TasksPage } from "../../features/tasks/pages/TasksPage";
import { TaskDetailPage } from "../../features/tasks/pages/TaskDetailPage";
import { DocumentsPage } from "../../features/documents/pages/DocumentsPage";
import { NotificationsPage } from "../../features/notifications/pages/NotificationsPage";
import { UsersPage } from "../../features/users/pages/UserPage";
import { ProfilePage } from "../../features/users/pages/ProfilePage";
import { IssuesPage } from "../../features/issues/pages/IssuesPage";
import { DesignChangesPage } from "../../features/design-changes/pages/DesignChangesPage";
import { SiteReportsPage } from "../../features/site-reports/pages/SiteReportsPage";
import { ProjectTeamPage } from "../../features/projects/pages/ProjectTeamPage";
import { MilestonesPage } from "../../features/milestones/pages/MilestonesPage";
import { MessagesPage } from "../../features/messages/pages/MessagesPage";
import { EvidencePhotoArchivePage } from "../../features/photo-archive/pages/EvidencePhotoArchivePage";
import { VoiceReportsPage } from "../../features/voice/pages/VoiceReportsPage";
import { IFCWorkspacePage } from "../../features/ifc/pages/IFCWorkspacePage";
import { AIIntelligencePage } from "../../features/ai-intelligence/pages/AIIntelligencePage";
import { CollaborationPage } from "../../features/collaboration/pages/CollaborationPage";

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
              <Route path={ROUTES.PROJECT_EVIDENCE} element={<EvidencePhotoArchivePage />} />
              <Route path={ROUTES.PROJECT_IFC} element={<IFCWorkspacePage />} />
              <Route path={ROUTES.PROJECT_AI_INTELLIGENCE} element={<AIIntelligencePage />} />
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
