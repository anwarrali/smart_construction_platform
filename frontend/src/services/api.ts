import axiosInstance from "./axios";
import { ENDPOINTS } from "./endpoints";
import type {
  LoginRequest,
  CreateUserRequest,
  CreateUserResponse,
  UpdateUserRequest,
  User,
  ResetPasswordRequest,
  ConfirmResetPasswordRequest,
} from "../types/auth";
import type {
  CreateProjectRequest,
  UpdateProjectRequest,
  Project,
  ProjectsResponse,
  ProjectFilters,
  ProjectSummary,
  ProjectMember,
  ProjectApprovalConfig,
  ProjectApprovalConfigUpdate,
  OwnerDashboardData,
} from "../types/project";
import type {
  CreateTaskRequest,
  UpdateTaskRequest,
  Task,
  TasksResponse,
  TaskFilters,
  TaskAnalytics,
} from "../types/task";
import type {
  UploadDocumentRequest,
  Document,
  DocumentsResponse,
  DocumentFilters,
} from "../types/document";
import type {
  UsersResponse,
  UserFilters,
  UpdateProfileRequest,
  UserProfile,
} from "../types/user";
import { parseQueryParams } from "../utils/helpers";
import type { Attachment, AttachmentEntityType } from "../types/attachment";
import type {
  McpToken,
  McpTokenCreateRequest,
  McpTokenCreated,
} from "../types/mcp";
import type { Milestone, MilestoneInput } from "../types/milestone";
import type {
  Conversation,
  ConversationDetail,
  ConversationPage,
  ConversationType,
  ProjectMessage,
  RecipientOptions,
  SharedEntityType,
} from "../types/message";
import type { StepUpChallenge, StepUpVerifyResult } from "../types/stepUp";
import type {
  IngestedFile,
  IngestedFileFilters,
  IngestedFilePage,
  IngestionRetryResult,
  IngestionUploadConstraints,
} from "../types/ingestion";
import type { ConsultantDashboardData, ConsultantReviewDetail, ConsultantReviewSummary } from "../types/consultant";
import type {
  VoiceCommand,
  VoiceReportReadiness,
  VoiceTaskCandidates,
} from "../types/voice";
import type { FieldSubmission } from "../types/fieldSubmission";
import type {
  EvidencePhotoArchiveItem,
  EvidencePhotoArchivePage,
  EvidencePhotoFilters,
  PhotoCategory,
} from "../types/photoArchive";
import type { IFCComparison, IFCElement, IFCFinding, IFCFindingIssue, IFCFindingReviewResult, IFCFindingReviewStatus, IFCModelGroup, IFCPage, IFCSpatialDetails, IFCSpatialNode, IFCSuggestion, IFCUploadConstraints, IFCVersion } from "../types/ifc";
import type { AIActionPage, AIActionVersion } from "../types/aiAction";
import type { DocumentIndexStatus, RagQueryResponse } from "../types/rag";
import type {
  AgentCatalogue, AgentRunRecord, AgentRunResult, AgentSubscriptions,
  OrchestrationReport,
} from "../types/agent";
import type { AIInsight, AIInsightSource, AIIntelligenceOverview } from "../types/aiInsight";

const api = {
  auth: {
    login: (data: LoginRequest) => {
      const formData = new URLSearchParams();
      formData.append("username", data.email);
      formData.append("password", data.password);
      return axiosInstance
        .post<{
          access_token: string;
          refresh_token: string;
          token_type?: string;
        }>(ENDPOINTS.AUTH.LOGIN, formData, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
        })
        .then((res) => ({
          accessToken: res.data.access_token,
          refreshToken: res.data.refresh_token,
          tokenType: res.data.token_type || "bearer",
          expiresIn: 0,
        }));
    },

    refresh: (refreshToken: string) =>
      axiosInstance
        .post<{
          access_token: string;
          refresh_token: string;
          token_type?: string;
        }>(ENDPOINTS.AUTH.REFRESH, { refresh_token: refreshToken })
        .then((res) => ({
          accessToken: res.data.access_token,
          refreshToken: res.data.refresh_token,
          tokenType: res.data.token_type || "bearer",
          expiresIn: 0,
        })),

    logout: (refreshToken?: string) =>
      axiosInstance.post<void>(ENDPOINTS.AUTH.LOGOUT, { refresh_token: refreshToken }).then((res) => res.data),

    forgotPassword: (data: ResetPasswordRequest) =>
      axiosInstance
        .post<void>(ENDPOINTS.AUTH.FORGOT_PASSWORD, { email: data.email })
        .then((res) => res.data),

    resetPassword: (data: ConfirmResetPasswordRequest) =>
      axiosInstance
        .post<void>(ENDPOINTS.AUTH.RESET_PASSWORD, {
          token: data.token,
          new_password: data.newPassword,
        })
        .then((res) => res.data),

    me: () =>
      axiosInstance.get<User>(ENDPOINTS.AUTH.ME).then((res) => res.data),
  },

  users: {
    list: (filters?: UserFilters) =>
      axiosInstance
        .get<UsersResponse>(
          `${ENDPOINTS.USERS.BASE}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get<UserProfile>(ENDPOINTS.USERS.BY_ID(id))
        .then((res) => res.data),
    getProfile: () =>
      axiosInstance
        .get<UserProfile>(ENDPOINTS.USERS.PROFILE)
        .then((res) => res.data),
    updateProfile: (data: UpdateProfileRequest) =>
      axiosInstance
        .put<UserProfile>(ENDPOINTS.USERS.UPDATE_PROFILE, data)
        .then((res) => res.data),
    changePassword: (currentPassword: string, newPassword: string) =>
      axiosInstance
        .put<void>(ENDPOINTS.USERS.CHANGE_PASSWORD, {
          currentPassword,
          newPassword,
        })
        .then((res) => res.data),
    uploadAvatar: (file: File) => {
      const formData = new FormData();
      formData.append("avatar", file);
      return axiosInstance
        .post<{ avatarUrl: string }>(ENDPOINTS.USERS.AVATAR, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((res) => res.data);
    },
    deactivate: (id: string) =>
      axiosInstance
        .put<void>(`${ENDPOINTS.USERS.BY_ID(id)}/deactivate`)
        .then((res) => res.data),
    activate: (id: string) =>
      axiosInstance
        .put<void>(`${ENDPOINTS.USERS.BY_ID(id)}/activate`)
        .then((res) => res.data),
    delete: (id: string) =>
      axiosInstance
        .delete<void>(ENDPOINTS.USERS.BY_ID(id))
        .then((res) => res.data),
    create: (data: CreateUserRequest) =>
      axiosInstance
        .post<CreateUserResponse>(ENDPOINTS.USERS.BASE, data)
        .then((res) => res.data),
    update: (id: string, data: UpdateUserRequest) =>
      axiosInstance
        .put<UserProfile>(ENDPOINTS.USERS.BY_ID(id), data)
        .then((res) => res.data),
    resetPassword: (id: string) =>
      axiosInstance
        .post<{ temporaryPassword: string; mustChangePassword: boolean }>(ENDPOINTS.USERS.RESET_PASSWORD(id))
        .then((res) => res.data),
  },

  projects: {
    list: (filters?: ProjectFilters) =>
      axiosInstance
        .get<ProjectsResponse>(
          `${ENDPOINTS.PROJECTS.BASE}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get<Project>(ENDPOINTS.PROJECTS.BY_ID(id))
        .then((res) => res.data),
    create: (data: CreateProjectRequest) =>
      axiosInstance
        .post<Project>(ENDPOINTS.PROJECTS.BASE, data)
        .then((res) => res.data),
    update: (id: string, data: UpdateProjectRequest) =>
      axiosInstance
        .put<Project>(ENDPOINTS.PROJECTS.BY_ID(id), data)
        .then((res) => res.data),
    delete: (id: string) =>
      axiosInstance
        .delete<void>(ENDPOINTS.PROJECTS.BY_ID(id))
        .then((res) => res.data),
    getSummary: () =>
      axiosInstance
        .get<ProjectSummary>(ENDPOINTS.PROJECTS.SUMMARY)
        .then((res) => res.data),
    getMembers: (id: string) =>
      axiosInstance.get<ProjectMember[]>(ENDPOINTS.PROJECTS.MEMBERS(id)).then((res) => res.data),
    getApprovalWorkflow: (id: string) =>
      axiosInstance.get<ProjectApprovalConfig>(ENDPOINTS.PROJECTS.APPROVAL_WORKFLOW(id)).then((res) => res.data),
    updateApprovalWorkflow: (id: string, data: ProjectApprovalConfigUpdate) =>
      axiosInstance.put<ProjectApprovalConfig>(ENDPOINTS.PROJECTS.APPROVAL_WORKFLOW(id), data).then((res) => res.data),
    getAvailableEngineers: (id: string) =>
      axiosInstance.get<User[]>(ENDPOINTS.PROJECTS.AVAILABLE_ENGINEERS(id)).then((res) => res.data),
    getAvailableTeamMembers: (id: string, filters?: { search?: string; role?: string; discipline?: string; affiliation?: string }) =>
      axiosInstance.get<User[]>(`${ENDPOINTS.PROJECTS.AVAILABLE_TEAM_MEMBERS(id)}?${parseQueryParams(filters || {})}`).then((res) => res.data),
    /**
     * Add somebody to a project.
     *
     * `projectRoleId`, `partyId` and `disciplineIds` are the configurable
     * model. `roleOnProject` is still sent because the legacy column is
     * still NOT NULL until the contract migration; the server derives it
     * when it is omitted.
     */
    addMember: (projectId: string, userId: string, roleOnProject: string, assignmentTitle?: string, isSiteEngineer = false, projectDiscipline?: string, projectNotes?: string, extra?: { projectRoleId?: string; partyId?: string | null; disciplineIds?: string[] }) =>
      axiosInstance.post<ProjectMember>(ENDPOINTS.PROJECTS.ADD_MEMBER(projectId), {
        userId, roleOnProject, assignmentTitle, isSiteEngineer, projectDiscipline, projectNotes,
        ...(extra || {}),
      }).then((res) => res.data),
    updateMemberAssignment: (projectId: string, userId: string, data: { assignmentTitle?: string; isSiteEngineer?: boolean; projectRoleId?: string; projectDiscipline?: string; disciplineIds?: string[]; projectNotes?: string }) =>
      axiosInstance.patch<ProjectMember>(ENDPOINTS.PROJECTS.UPDATE_ASSIGNMENT(projectId, userId), data).then((res) => res.data),
    removeMember: (projectId: string, userId: string) =>
      axiosInstance.delete(ENDPOINTS.PROJECTS.REMOVE_MEMBER(projectId, userId)).then((res) => res.data),
    transferMember: (sourceProjectId: string, userId: string, targetProjectId: string, isSiteEngineer = false) =>
      axiosInstance.post<ProjectMember>(`${ENDPOINTS.PROJECTS.REMOVE_MEMBER(sourceProjectId, userId)}/transfer`, {
        targetProjectId, isSiteEngineer,
      }).then((res) => res.data),
    getOwnerDashboard: (id: string) =>
      axiosInstance
        .get<OwnerDashboardData>(ENDPOINTS.PROJECTS.OWNER_DASHBOARD(id))
        .then((res) => res.data),
  },

  tasks: {
    list: (filters?: TaskFilters) =>
      axiosInstance
        .get<TasksResponse>(
          `${ENDPOINTS.TASKS.BASE}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get<Task>(ENDPOINTS.TASKS.BY_ID(id))
        .then((res) => res.data),
    getReviewAuthority: (id: string) =>
      axiosInstance.get<{
        taskId: string;
        approvalMode: "CENTRALIZED_REVIEW" | "DISCIPLINE_BASED_REVIEW";
        canReview: boolean;
        reviewers: Array<{ id: string; fullName: string; organization?: string }>;
      }>(ENDPOINTS.TASKS.REVIEW_AUTHORITY(id)).then((res) => res.data),
    getByProject: (projectId: string, filters?: TaskFilters) =>
      axiosInstance
        .get<TasksResponse>(
          `${ENDPOINTS.TASKS.BY_PROJECT(projectId)}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getMyTasks: (filters?: TaskFilters) =>
      axiosInstance
        .get<TasksResponse>(
          `${ENDPOINTS.TASKS.MY_TASKS}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    create: (data: CreateTaskRequest) =>
      axiosInstance
        .post<Task>(ENDPOINTS.TASKS.BASE, data)
        .then((res) => res.data),
    update: (id: string, data: UpdateTaskRequest) =>
      axiosInstance
        .put<Task>(ENDPOINTS.TASKS.BY_ID(id), data)
        .then((res) => res.data),
    delete: (id: string) =>
      axiosInstance
        .delete<void>(ENDPOINTS.TASKS.BY_ID(id))
        .then((res) => res.data),
    getAnalytics: (projectId: string) =>
      axiosInstance
        .get<TaskAnalytics>(ENDPOINTS.TASKS.ANALYTICS(projectId))
        .then((res) => res.data),
    updateProgress: (id: string, progressPercentage: number, note?: string) =>
      axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/progress`, { progressPercentage, note }).then(res => res.data),
    start: (id: string) => axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/start`).then(res => res.data),
    startRework: (id: string) => axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/start-rework`).then(res => res.data),
    resumeAfterBlocker: (id: string) => axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/resume-after-blocker`).then(res => res.data),
    addWorkUpdate: (id: string, data: Record<string, unknown>) => axiosInstance.post(`${ENDPOINTS.TASKS.BY_ID(id)}/work-updates`, data).then(res => res.data),
    blockers: (id: string) => axiosInstance.get(`${ENDPOINTS.TASKS.BY_ID(id)}/blockers`).then(res => res.data),
    reportBlocker: (id: string, data: Record<string, unknown>) => axiosInstance.post(`${ENDPOINTS.TASKS.BY_ID(id)}/blockers`, data).then(res => res.data),
    activity: (id: string) => axiosInstance.get(`${ENDPOINTS.TASKS.BY_ID(id)}/activity`).then(res => res.data),
    submitReview: (id: string, completionNote?: string) =>
      axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/submit-review`, { completionNote }).then(res => res.data),
    completeExecution: (id: string) => axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/complete-execution`).then(res => res.data),
    startReview: (id: string) => axiosInstance.put(`${ENDPOINTS.TASKS.BY_ID(id)}/start-review`).then(res => res.data),
    approve: (id: string, comments: string) =>
      axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/approve`, { comments }).then(res => res.data),
    reject: (id: string, comments: string, rejectionReason: string, requiredCorrections?: string) =>
      axiosInstance.put<Task>(`${ENDPOINTS.TASKS.BY_ID(id)}/reject`, { comments, rejectionReason, requiredCorrections }).then(res => res.data),
    requestClarification: (id: string, question: string) => axiosInstance.put(`${ENDPOINTS.TASKS.BY_ID(id)}/request-clarification`, { question }).then(res => res.data),
    respondClarification: (id: string, response: string) => axiosInstance.put(`${ENDPOINTS.TASKS.BY_ID(id)}/respond-clarification`, { response }).then(res => res.data),
    comments: (id: string) => axiosInstance.get(`${ENDPOINTS.TASKS.BY_ID(id)}/comments`).then(res => res.data),
    addComment: (id: string, content: string) => axiosInstance.post(`${ENDPOINTS.TASKS.BY_ID(id)}/comments`, { content }).then(res => res.data),
    reviews: (id: string) => axiosInstance.get(`${ENDPOINTS.TASKS.BY_ID(id)}/reviews`).then(res => res.data),
    dependencies: (id: string) => axiosInstance.get(ENDPOINTS.TASKS.DEPENDENCIES(id)).then(res => res.data),
    addDependency: (id: string, dependsOnTaskId: string) => axiosInstance.post(ENDPOINTS.TASKS.DEPENDENCIES(id), {
      dependsOnTaskId, dependencyType: "finish_to_start", lagDays: 0,
    }).then(res => res.data),
    removeDependency: (taskId: string, dependencyId: string) => axiosInstance.delete(`${ENDPOINTS.TASKS.DEPENDENCIES(taskId)}/${dependencyId}`).then(res => res.data),
  },

  fieldSubmissions: {
    byTask: (taskId: string) =>
      axiosInstance.get<FieldSubmission[]>(ENDPOINTS.FIELD_SUBMISSIONS.BY_TASK(taskId)).then((res) => res.data),
    pending: (projectId: string) =>
      axiosInstance.get<FieldSubmission[]>(ENDPOINTS.FIELD_SUBMISSIONS.PENDING, {
        params: { project_id: projectId },
      }).then((res) => res.data),
    getById: (id: string) =>
      axiosInstance.get<FieldSubmission>(ENDPOINTS.FIELD_SUBMISSIONS.BY_ID(id)).then((res) => res.data),
    verify: (id: string, comment?: string) =>
      axiosInstance.put<FieldSubmission>(ENDPOINTS.FIELD_SUBMISSIONS.VERIFY(id), { comment }).then((res) => res.data),
    verifyAndApply: (
      id: string,
      data: {
        progressPercentage: number;
        expectedTaskUpdatedAt: string;
        comment?: string;
        correctionConfirmed?: boolean;
      },
    ) => axiosInstance.put<FieldSubmission>(
      ENDPOINTS.FIELD_SUBMISSIONS.VERIFY_AND_APPLY(id), data,
    ).then((res) => res.data),
    reject: (id: string, reason: string) =>
      axiosInstance.put<FieldSubmission>(ENDPOINTS.FIELD_SUBMISSIONS.REJECT(id), { reason }).then((res) => res.data),
    replacePhotoCategories: (photoId: string, categoryIds: string[]) =>
      axiosInstance.put<PhotoCategory[]>(
        ENDPOINTS.FIELD_SUBMISSIONS.PHOTO_CATEGORIES(photoId),
        { categoryIds },
      ).then((res) => res.data),
  },

  voice: {
    getCommand: (id: string) =>
      axiosInstance.get<VoiceCommand>(ENDPOINTS.VOICE.COMMAND(id)).then((res) => res.data),
    getAudio: (id: string) =>
      axiosInstance.get<Blob>(ENDPOINTS.VOICE.AUDIO(id), { responseType: "blob" })
        .then((res) => res.data),

    /**
     * Upload one recording and get back the fully interpreted command.
     *
     * `signal` is required in practice rather than optional decoration: an
     * engineer who re-records while the previous upload is in flight must not
     * receive the earlier interpretation afterwards, and the only reliable way
     * to guarantee that is to abort the obsolete request rather than to
     * remember to ignore its response.
     */
    createCommand: (
      body: {
        projectId: string;
        taskId?: string;
        durationSeconds?: number;
        idempotencyKey: string;
        audio: Blob;
        filename: string;
      },
      signal?: AbortSignal,
    ) => {
      const form = new FormData();
      form.append("project_id", body.projectId);
      if (body.taskId) form.append("task_id", body.taskId);
      if (body.durationSeconds) form.append("duration_seconds", String(body.durationSeconds));
      form.append("idempotency_key", body.idempotencyKey);
      form.append("audio", body.audio, body.filename);
      return axiosInstance
        .post<VoiceCommand>(ENDPOINTS.VOICE.COMMANDS, form, { signal, timeout: 120000 })
        .then((res) => res.data);
    },

    taskCandidates: (projectId: string, q: string, signal?: AbortSignal) =>
      axiosInstance
        .get<VoiceTaskCandidates>(ENDPOINTS.VOICE.TASK_CANDIDATES, {
          params: { project_id: projectId, q },
          signal,
        })
        .then((res) => res.data),

    updateDraft: (
      commandId: string,
      draftId: string,
      body: {
        targetId?: string;
        payload: Record<string, unknown>;
        selectedForExecution: boolean;
        rowVersion: number;
      },
    ) =>
      axiosInstance
        .put<VoiceCommand>(ENDPOINTS.VOICE.DRAFT(commandId, draftId), body)
        .then((res) => res.data),

    answerClarification: (commandId: string, clarificationId: string, answerText: string) =>
      axiosInstance
        .post<VoiceCommand>(ENDPOINTS.VOICE.CLARIFICATIONS(commandId), {
          clarificationId,
          answerText,
        })
        .then((res) => res.data),

    confirm: (
      commandId: string,
      body: { selectedDraftIds: string[]; rowVersion: number; detailedConfirmation: boolean },
    ) =>
      axiosInstance
        .post<VoiceCommand>(ENDPOINTS.VOICE.CONFIRM(commandId), body)
        .then((res) => res.data),

    execute: (commandId: string, rowVersion: number) =>
      axiosInstance
        .post<VoiceCommand>(ENDPOINTS.VOICE.EXECUTE(commandId), { rowVersion })
        .then((res) => res.data),

    cancel: (commandId: string) =>
      axiosInstance
        .post<VoiceCommand>(ENDPOINTS.VOICE.CANCEL(commandId), {})
        .then((res) => res.data),

    reportReadiness: (projectId: string, reportDate?: string) =>
      axiosInstance
        .get<VoiceReportReadiness>(ENDPOINTS.VOICE.REPORT_READINESS, {
          params: { project_id: projectId, ...(reportDate ? { report_date: reportDate } : {}) },
        })
        .then((res) => res.data),
  },

  photoArchive: {
    list: (projectId: string, filters?: EvidencePhotoFilters) =>
      axiosInstance.get<EvidencePhotoArchivePage>(
        `${ENDPOINTS.PHOTO_ARCHIVE.LIST(projectId)}?${parseQueryParams(filters || {})}`,
      ).then((res) => res.data),
    detail: (projectId: string, photoId: string) =>
      axiosInstance.get<EvidencePhotoArchiveItem>(
        ENDPOINTS.PHOTO_ARCHIVE.DETAIL(projectId, photoId),
      ).then((res) => res.data),
    categories: (projectId: string, includeInactive = false) =>
      axiosInstance.get<PhotoCategory[]>(ENDPOINTS.PHOTO_ARCHIVE.CATEGORIES(projectId), {
        params: { include_inactive: includeInactive },
      }).then((res) => res.data),
    createCategory: (projectId: string, name: string) =>
      axiosInstance.post<PhotoCategory>(
        ENDPOINTS.PHOTO_ARCHIVE.CATEGORIES(projectId), { name },
      ).then((res) => res.data),
    updateCategory: (
      projectId: string,
      categoryId: string,
      data: { name?: string; active?: boolean },
    ) => axiosInstance.patch<PhotoCategory>(
      ENDPOINTS.PHOTO_ARCHIVE.CATEGORY(projectId, categoryId), data,
    ).then((res) => res.data),
    deactivateCategory: (projectId: string, categoryId: string) =>
      axiosInstance.delete<PhotoCategory>(
        ENDPOINTS.PHOTO_ARCHIVE.CATEGORY(projectId, categoryId),
      ).then((res) => res.data),
  },

  consultant: {
    dashboard: (projectId: string) => axiosInstance.get<ConsultantDashboardData>(ENDPOINTS.CONSULTANT.DASHBOARD(projectId)).then(res => res.data),
    reviews: (projectId: string, filters?: Record<string, unknown>) => axiosInstance.get<ConsultantReviewSummary[]>(`${ENDPOINTS.CONSULTANT.REVIEWS(projectId)}?${parseQueryParams(filters || {})}`).then(res => res.data),
    history: (projectId: string, filters?: Record<string, unknown>) => axiosInstance.get<ConsultantReviewSummary[]>(`${ENDPOINTS.CONSULTANT.HISTORY(projectId)}?${parseQueryParams(filters || {})}`).then(res => res.data),
    review: (projectId: string, reviewId: string) => axiosInstance.get<ConsultantReviewDetail>(ENDPOINTS.CONSULTANT.REVIEW(projectId, reviewId)).then(res => res.data),
  },

  milestones: {
    list: (projectId: string) => axiosInstance
      .get<Milestone[]>(`${ENDPOINTS.MILESTONES.BASE}?${parseQueryParams({ projectId })}`).then((res) => res.data),
    create: (data: MilestoneInput) => axiosInstance
      .post<Milestone>(ENDPOINTS.MILESTONES.BASE, data).then((res) => res.data),
    update: (id: string, data: Partial<MilestoneInput>) => axiosInstance
      .put<Milestone>(ENDPOINTS.MILESTONES.BY_ID(id), data).then((res) => res.data),
    delete: (id: string) => axiosInstance.delete(ENDPOINTS.MILESTONES.BY_ID(id)).then((res) => res.data),
  },

  stepUp: {
    purposes: () => axiosInstance
      .get<{ code: string; label: string }[]>(ENDPOINTS.STEP_UP.PURPOSES).then((res) => res.data),
    request: (purpose: string) => axiosInstance
      .post<StepUpChallenge>(ENDPOINTS.STEP_UP.REQUEST, { purpose }).then((res) => res.data),
    verify: (purpose: string, code: string) => axiosInstance
      .post<StepUpVerifyResult>(ENDPOINTS.STEP_UP.VERIFY, { purpose, code }).then((res) => res.data),
  },

  messages: {
    participants: (projectId: string) => axiosInstance
      .get<User[]>(`${ENDPOINTS.MESSAGES.PARTICIPANTS}?${parseQueryParams({ projectId })}`).then((res) => res.data),
    recipientOptions: (projectId: string) => axiosInstance
      .get<RecipientOptions>(`${ENDPOINTS.MESSAGES.RECIPIENT_OPTIONS}?${parseQueryParams({ projectId })}`).then((res) => res.data),
    conversations: (projectId: string, filters?: {
      conversationType?: ConversationType | "";
      unreadOnly?: boolean;
      participantId?: string;
      search?: string;
      page?: number;
      pageSize?: number;
    }) => axiosInstance.get<ConversationPage>(
      `${ENDPOINTS.MESSAGES.CONVERSATIONS}?${parseQueryParams({ projectId, ...(filters || {}) })}`,
    ).then((res) => res.data),
    conversation: (id: string) => axiosInstance
      .get<ConversationDetail>(ENDPOINTS.MESSAGES.CONVERSATION(id)).then((res) => res.data),
    createConversation: (data: {
      projectId: string;
      recipientIds?: string[];
      groupCode?: string;
      title?: string;
      contextType?: "TASK" | "ISSUE";
      contextId?: string;
      content?: string;
    }) => axiosInstance.post<Conversation>(ENDPOINTS.MESSAGES.CONVERSATIONS, data).then((res) => res.data),
    sendToConversation: (id: string, content: string) => axiosInstance
      .post<ProjectMessage>(ENDPOINTS.MESSAGES.CONVERSATION_MESSAGES(id), { content }).then((res) => res.data),
    markConversationRead: (id: string) => axiosInstance
      .put<Conversation>(ENDPOINTS.MESSAGES.CONVERSATION_READ(id)).then((res) => res.data),
    announce: (projectId: string, content: string, title?: string, groupCode = "ALL_PROJECT_MEMBERS") =>
      axiosInstance.post<Conversation>(ENDPOINTS.MESSAGES.ANNOUNCEMENTS, {
        projectId, content, title, groupCode,
      }).then((res) => res.data),
    context: (projectId: string, type: "TASK" | "ISSUE", id: string) =>
      axiosInstance.get<ConversationDetail | null>(
        `${ENDPOINTS.MESSAGES.CONTEXT(type, id)}?${parseQueryParams({ projectId })}`,
      ).then((res) => res.data),
    createContext: (
      projectId: string, type: "TASK" | "ISSUE", id: string,
      content: string, recipientIds?: string[],
    ) => axiosInstance.post<Conversation>(ENDPOINTS.MESSAGES.CONTEXT(type, id), {
      projectId, contextType: type, contextId: id, content,
      recipientIds: recipientIds || [],
    }).then((res) => res.data),
    unreadCount: (projectId?: string) => axiosInstance
      .get<{ count: number }>(`${ENDPOINTS.MESSAGES.UNREAD_COUNT}?${parseQueryParams({ projectId })}`).then((res) => res.data),
    forward: (messageId: string, data: {
      recipientIds?: string[];
      groupCode?: string;
      note?: string;
      title?: string;
    }) => axiosInstance.post<Conversation>(ENDPOINTS.MESSAGES.FORWARD(messageId), data).then((res) => res.data),
    shareEntity: (data: {
      entityType: SharedEntityType;
      entityId: string;
      recipientIds?: string[];
      groupCode?: string;
      note?: string;
      title?: string;
    }) => axiosInstance.post<Conversation>(ENDPOINTS.MESSAGES.SHARE, data).then((res) => res.data),
  },

  documents: {
    list: (filters?: DocumentFilters) =>
      axiosInstance
        .get<DocumentsResponse>(
          `${ENDPOINTS.DOCUMENTS.BASE}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get<Document>(ENDPOINTS.DOCUMENTS.BY_ID(id))
        .then((res) => res.data),
    upload: (data: UploadDocumentRequest) => {
      const formData = new FormData();
      formData.append("file", data.file);
      formData.append("title", data.title);
      formData.append("project_id", data.projectId);
      if (data.documentType)
        formData.append("document_type", data.documentType);
      if (data.taskId) formData.append("task_id", data.taskId);
      if (data.notes) formData.append("notes", data.notes);
      return axiosInstance
        .post<Document>(ENDPOINTS.DOCUMENTS.UPLOAD, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((res) => res.data);
    },
    delete: (id: string) =>
      axiosInstance
        .delete<void>(ENDPOINTS.DOCUMENTS.BY_ID(id))
        .then((res) => res.data),
    downloadUrl: (id: string) =>
      axiosInstance
        .get<{ url: string }>(ENDPOINTS.DOCUMENTS.DOWNLOAD(id))
        .then((res) => res.data),
    getByProject: (projectId: string, filters?: DocumentFilters) =>
      axiosInstance
        .get<DocumentsResponse>(
          `${ENDPOINTS.DOCUMENTS.BY_PROJECT(projectId)}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    search: (query: string, projectId?: string) =>
      axiosInstance
        .get<DocumentsResponse>(
          `${ENDPOINTS.DOCUMENTS.SEARCH}?query=${query}&projectId=${projectId || ""}`,
        )
        .then((res) => res.data),
  },
  reports: {
    list: (filters?: { projectId?: string; page?: number; limit?: number }) =>
      axiosInstance
        .get(`${ENDPOINTS.REPORTS.BASE}?${parseQueryParams(filters || {})}`)
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get(`${ENDPOINTS.REPORTS.BY_ID(id)}`)
        .then((res) => res.data),
    getByProject: (projectId: string) =>
      axiosInstance
        .get(ENDPOINTS.REPORTS.BY_PROJECT(projectId))
        .then((res) => res.data),
    create: (data: {
      projectId: string;
      reportType: string;
      title: string;
      content: string;
      photos?: File[];
      reportDate: string;
      weatherConditions?: string;
      workersCount?: number;
      equipment?: string;
      workCompleted?: string;
      workInProgress?: string;
      delays?: string;
      issuesSummary?: string;
      notes?: string;
      taskId?: string;
      reviewStatus?: "draft" | "submitted";
    }) => {
      const formData = new FormData();
      formData.append("project_id", data.projectId);
      formData.append("report_type", data.reportType);
      formData.append("title", data.title);
      formData.append("content", data.content);
      formData.append("report_date", data.reportDate);
      if (data.taskId) formData.append("task_id", data.taskId);
      if (data.reviewStatus) formData.append("review_status", data.reviewStatus);
      if (data.weatherConditions) formData.append("weather_conditions", data.weatherConditions);
      if (data.workersCount !== undefined) formData.append("workers_count", String(data.workersCount));
      if (data.equipment) formData.append("equipment", data.equipment);
      if (data.workCompleted) formData.append("work_completed", data.workCompleted);
      if (data.workInProgress) formData.append("work_in_progress", data.workInProgress);
      if (data.delays) formData.append("delays", data.delays);
      if (data.issuesSummary) formData.append("issues_summary", data.issuesSummary);
      if (data.notes) formData.append("notes", data.notes);
      if (data.photos) {
        data.photos.forEach((photo) => formData.append("photos", photo));
      }
      return axiosInstance
        .post(ENDPOINTS.REPORTS.SUBMIT, formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((res) => res.data);
    },
    update: (id: string, data: Record<string, unknown>) =>
      axiosInstance.put(`${ENDPOINTS.SITE_REPORTS.BY_ID(id)}`, data).then((res) => res.data),
  },

  notifications: {
    list: (page: number = 1, limit: number = 20, projectId?: string, filters?: { unread?: boolean; notificationType?: string; search?: string }) =>
      axiosInstance
        .get(`${ENDPOINTS.NOTIFICATIONS.BASE}?${parseQueryParams({ page, limit, projectId, ...filters })}`)
        .then((res) => res.data),
    markRead: (id: string) =>
      axiosInstance
        .put<void>(ENDPOINTS.NOTIFICATIONS.MARK_READ(id))
        .then((res) => res.data),
    markAllRead: (projectId?: string) =>
      axiosInstance
        .put<void>(`${ENDPOINTS.NOTIFICATIONS.MARK_ALL_READ}?${parseQueryParams({ projectId })}`)
        .then((res) => res.data),
    getUnreadCount: () =>
      axiosInstance
        .get<{ count: number }>(ENDPOINTS.NOTIFICATIONS.UNREAD_COUNT)
        .then((res) => res.data),
    getById: (id: string) =>
      axiosInstance
        .get(ENDPOINTS.NOTIFICATIONS.BY_ID(id))
        .then((res) => res.data),
    registerDevice: (data: {
      token: string;
      platform: "android" | "ios" | "web";
      deviceId?: string;
      deviceName?: string;
      appVersion?: string;
    }) =>
      axiosInstance
        .post(ENDPOINTS.NOTIFICATIONS.DEVICES, data)
        .then((res) => res.data),
    unregisterDevice: (data: { token?: string; deviceId?: string }) =>
      // DELETE with a body: the identifier is not a resource path segment, and
      // an FCM token is far too long to sit safely in a URL.
      axiosInstance
        .delete<void>(ENDPOINTS.NOTIFICATIONS.DEVICES, { data })
        .then((res) => res.data),
    listDevices: () =>
      axiosInstance
        .get(ENDPOINTS.NOTIFICATIONS.DEVICES)
        .then((res) => res.data),
    sendTestNotification: () =>
      axiosInstance
        .post(ENDPOINTS.NOTIFICATIONS.DEV_TEST)
        .then((res) => res.data),
  },

  // Realtime. Only the ticket goes through axios — it needs the bearer token,
  // and minting it here means the stream inherits the same session handling
  // (including refresh-on-401) as every other call.
  realtime: {
    ticket: () =>
      axiosInstance
        .post<{ ticket: string; expiresInSeconds: number; heartbeatSeconds: number }>(
          ENDPOINTS.REALTIME.TICKET,
        )
        .then((res) => res.data),
    health: () =>
      axiosInstance.get(ENDPOINTS.REALTIME.HEALTH).then((res) => res.data),
  },

  // Document question answering. Uses the shared axios instance, so the access
  // token, refresh-on-401 and step-up handling are inherited rather than
  // reimplemented here.
  rag: {
    indexDocument: (documentId: string, force = false) =>
      axiosInstance
        .post<DocumentIndexStatus>(
          `${ENDPOINTS.RAG.INDEX(documentId)}${force ? "?force=true" : ""}`,
        )
        .then((res) => res.data),
    getStatus: (documentId: string) =>
      axiosInstance
        .get<DocumentIndexStatus>(ENDPOINTS.RAG.STATUS(documentId))
        .then((res) => res.data),
    query: (data: { projectId: string; query: string; documentId?: string }) =>
      axiosInstance
        .post<RagQueryResponse>(ENDPOINTS.RAG.QUERY, data)
        .then((res) => res.data),
  },

  scheduling: {
    getGanttData: (projectId: string) =>
      axiosInstance
        .get(ENDPOINTS.SCHEDULING.GANTT(projectId))
        .then((res) => res.data),
    getCriticalPath: (projectId: string) =>
      axiosInstance
        .get(ENDPOINTS.SCHEDULING.CRITICAL_PATH(projectId))
        .then((res) => res.data),
    getDelayAnalysis: (projectId: string) =>
      axiosInstance
        .get(ENDPOINTS.SCHEDULING.DELAY_ANALYSIS(projectId))
        .then((res) => res.data),
    shiftTask: (projectId: string, taskId: string, shiftDays: number, notes?: string) =>
      axiosInstance
        .post(ENDPOINTS.SCHEDULING.SHIFT(projectId), {
          task_id: taskId,
          shift_days: shiftDays,
          notes: notes,
        })
        .then((res) => res.data),
  },

  siteReports: {
    list: (filters?: { projectId?: string; status?: string; discipline?: string; dateFrom?: string; dateTo?: string; submittedById?: string; hasAttachments?: boolean }) =>
      axiosInstance
        .get(`${ENDPOINTS.SITE_REPORTS.LIST}?${parseQueryParams(filters || {})}`)
        .then((res) => res.data),
    getByProject: (projectId: string) =>
      axiosInstance
        .get(ENDPOINTS.SITE_REPORTS.BY_PROJECT(projectId))
        .then((res) => res.data),
    review: (id: string, data: { approved: boolean; rejectionReason?: string }) =>
      axiosInstance
        .put(ENDPOINTS.SITE_REPORTS.REVIEW(id), data)
        .then((res) => res.data),
  },

  dashboard: {
    getStats: () =>
      axiosInstance
        .get(ENDPOINTS.DASHBOARD.STATS)
        .then((res) => res.data),
    getProjectStats: (id: string) =>
      axiosInstance.get(ENDPOINTS.DASHBOARD.PROJECT(id)).then((res) => res.data),
    getEngineerProjectStats: (id: string) =>
      axiosInstance.get(ENDPOINTS.DASHBOARD.ENGINEER_PROJECT(id)).then((res) => res.data),
  },

  issues: {
    list: (filters?: { projectId?: string; taskId?: string; status?: string; discipline?: string; dateFrom?: string; dateTo?: string; raisedById?: string; hasAttachments?: boolean }) =>
      axiosInstance
        .get(`${ENDPOINTS.ISSUES.BASE}?${parseQueryParams(filters || {})}`)
        .then((res) => res.data),
    create: (data: Record<string, unknown>) =>
      axiosInstance.post(ENDPOINTS.ISSUES.BASE, data).then((res) => res.data),
    update: (id: string, data: Record<string, unknown>) =>
      axiosInstance.put(ENDPOINTS.ISSUES.BY_ID(id), data).then((res) => res.data),
  },

  attachments: {
    list: (filters: { projectId?: string; entityType?: AttachmentEntityType; entityId?: string; dateFrom?: string; dateTo?: string }) =>
      axiosInstance.get<Attachment[]>(`${ENDPOINTS.ATTACHMENTS.BASE}?${parseQueryParams(filters)}`).then((res) => res.data),
    upload: (file: File, projectId: string, entityType: AttachmentEntityType, entityId: string) => {
      const form = new FormData();
      form.append("file", file); form.append("project_id", projectId);
      form.append("entity_type", entityType); form.append("entity_id", entityId);
      return axiosInstance.post<Attachment>(ENDPOINTS.ATTACHMENTS.UPLOAD, form, {
        headers: { "Content-Type": "multipart/form-data" },
      }).then((res) => res.data);
    },
    delete: (id: string) => axiosInstance.delete(ENDPOINTS.ATTACHMENTS.BY_ID(id)).then((res) => res.data),
  },
  field: {
    context: () => axiosInstance.get<{ projects: Array<{ id: string; name: string; assignmentTitle?: string; isSiteEngineer: boolean }> }>(ENDPOINTS.FIELD.CONTEXT).then((res) => res.data),
    validateProposal: (proposal: Record<string, unknown>) => axiosInstance.post(ENDPOINTS.FIELD.VALIDATE_PROPOSAL, proposal).then((res) => res.data),
    confirmProposal: (proposal: Record<string, unknown>) => axiosInstance.post(ENDPOINTS.FIELD.CONFIRM_PROPOSAL, proposal).then((res) => res.data),
  },

  designChanges: {
    list: (filters?: { projectId?: string; status?: string; discipline?: string; dateFrom?: string; dateTo?: string; proposedById?: string; hasAttachments?: boolean }) => axiosInstance
      .get(`${ENDPOINTS.DESIGN_CHANGES.BASE}?${parseQueryParams(filters || {})}`)
      .then((res) => res.data),
    create: (data: Record<string, unknown>) => axiosInstance
      .post(ENDPOINTS.DESIGN_CHANGES.BASE, data).then((res) => res.data),
    approve: (id: string) => axiosInstance.put(`${ENDPOINTS.DESIGN_CHANGES.BY_ID(id)}/approve`).then(res => res.data),
    reject: (id: string, reviewNotes: string) => axiosInstance.put(`${ENDPOINTS.DESIGN_CHANGES.BY_ID(id)}/reject`, { reviewNotes }).then(res => res.data),
  },

  settings: {
    getGeneral: () =>
      axiosInstance.get(ENDPOINTS.SETTINGS.GENERAL).then((res) => res.data),
    updateGeneral: (data: Record<string, unknown>) =>
      axiosInstance
        .put(ENDPOINTS.SETTINGS.GENERAL, data)
        .then((res) => res.data),
  },

  ifc: {
    uploadConstraints: (projectId: string) => axiosInstance.get<IFCUploadConstraints>(ENDPOINTS.IFC.UPLOAD_CONSTRAINTS(projectId)).then((res) => res.data),
    models: (projectId: string) => axiosInstance.get<IFCModelGroup[]>(ENDPOINTS.IFC.MODELS(projectId)).then((res) => res.data),
    createModel: (projectId: string, data: { name: string; discipline?: string; description?: string }) =>
      axiosInstance.post<IFCModelGroup>(ENDPOINTS.IFC.MODELS(projectId), data).then((res) => res.data),
    versions: (projectId: string, modelId: string) => axiosInstance.get<IFCVersion[]>(ENDPOINTS.IFC.VERSIONS(projectId, modelId)).then((res) => res.data),
    version: (projectId: string, versionId: string) => axiosInstance.get<IFCVersion>(ENDPOINTS.IFC.VERSION(projectId, versionId)).then((res) => res.data),
    retryVersion: (projectId: string, versionId: string) => axiosInstance.post<IFCVersion>(`${ENDPOINTS.IFC.VERSION(projectId, versionId)}/retry`).then((res) => res.data),
    /* Revision lifecycle. Both routes require `ifc.manage_version` and refuse a
       revision that has not finished processing; both clear the designation
       from every other revision in the same model group, which is why callers
       update the whole list and not only the row that came back. */
    activateVersion: (projectId: string, versionId: string) =>
      axiosInstance.post<IFCVersion>(`${ENDPOINTS.IFC.VERSION(projectId, versionId)}/activate`).then((res) => res.data),
    baselineVersion: (projectId: string, versionId: string) =>
      axiosInstance.post<IFCVersion>(`${ENDPOINTS.IFC.VERSION(projectId, versionId)}/baseline`).then((res) => res.data),
    /**
     * The original IFC, as bytes.
     *
     * Returned rather than navigated to: the file lives in private storage
     * behind `ifc.download`, so it has to travel over the authenticated client
     * like every other request. The server names the file in
     * `Content-Disposition`; that name is preferred when the browser exposes
     * the header, and the version's own `originalFilename` is the fallback.
     */
    downloadVersion: (projectId: string, versionId: string) =>
      axiosInstance
        .get<Blob>(`${ENDPOINTS.IFC.VERSION(projectId, versionId)}/download`, { responseType: "blob" })
        .then((res) => ({
          blob: res.data,
          filename: /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(
            String(res.headers["content-disposition"] || ""),
          )?.[1],
        })),
    uploadVersion: (projectId: string, modelId: string, file: File, data: { title: string; revisionCode?: string; versionType: string; discipline?: string }, onProgress?: (percentage: number) => void) => {
      const form = new FormData(); form.append("file", file); form.append("title", data.title);
      if (data.revisionCode) form.append("revision_code", data.revisionCode);
      form.append("version_type", data.versionType);
      if (data.discipline) form.append("discipline", data.discipline);
      return axiosInstance.post<IFCVersion>(ENDPOINTS.IFC.VERSIONS(projectId, modelId), form, { headers: { "Content-Type": "multipart/form-data" }, onUploadProgress: (event) => onProgress?.(event.total ? Math.round(event.loaded * 100 / event.total) : 0) }).then((res) => res.data);
    },
    hierarchy: (projectId: string, versionId: string) => axiosInstance.get<IFCSpatialNode[]>(ENDPOINTS.IFC.HIERARCHY(projectId, versionId)).then((res) => res.data),
    spatialDetails: (projectId: string, nodeId: string) => axiosInstance.get<IFCSpatialDetails>(ENDPOINTS.IFC.SPATIAL_DETAILS(projectId, nodeId)).then((res) => res.data),
    spatialProjectData: (projectId: string, nodeId: string) => axiosInstance.get<{projectData:Array<{entity:{id:string;type:string;title?:string;status?:string}}> }>(ENDPOINTS.IFC.SPATIAL_PROJECT_DATA(projectId, nodeId)).then((res) => res.data),
    geometryStatus: (projectId: string, versionId: string) => axiosInstance.get<{versionId:string; status:string; assetReady:boolean; error?:string; stats:Record<string,unknown>; generatedAt?:string}>(ENDPOINTS.IFC.GEOMETRY_STATUS(projectId, versionId)).then((res) => res.data),
    generateGeometry: (projectId: string, versionId: string) => axiosInstance.post<{status:string;message:string}>(ENDPOINTS.IFC.GEOMETRY_GENERATE(projectId, versionId)).then((res) => res.data),
    geometryAsset: (projectId: string, versionId: string) => axiosInstance.get<ArrayBuffer>(ENDPOINTS.IFC.GEOMETRY_ASSET(projectId, versionId), { responseType: "arraybuffer" }).then((res) => res.data),
    geometryMapping: (projectId: string, versionId: string) => axiosInstance.get<{versionId:string;items:Record<string,{id:string;globalId:string;name:string;entityType:string;kind?:"ELEMENT"|"SPATIAL";nodeType?:string;buildingNodeId?:string;storeyNodeId?:string;spaceNodeId?:string;discipline?:string;systemName?:string;category?:string}>}>(ENDPOINTS.IFC.GEOMETRY_MAPPING(projectId, versionId)).then((res) => res.data),
    elements: (projectId: string, versionId: string, filters: Record<string, unknown> = {}) => axiosInstance.get<{items: IFCElement[]; total: number}>(`${ENDPOINTS.IFC.ELEMENTS(projectId, versionId)}?${parseQueryParams(filters)}`).then((res) => res.data),
    element: (projectId: string, versionId: string, elementId: string) => axiosInstance.get<IFCElement>(`${ENDPOINTS.IFC.ELEMENTS(projectId, versionId)}/${elementId}`).then((res) => res.data),
    elementProjectData: (projectId: string, elementId: string) => axiosInstance.get<{projectData:Array<{entity:{id:string;type:string;title?:string;status?:string}}> }>(ENDPOINTS.IFC.ELEMENT_PROJECT_DATA(projectId, elementId)).then((res) => res.data),
    comparisons: (projectId: string) => axiosInstance.get<IFCComparison[]>(ENDPOINTS.IFC.COMPARISONS(projectId)).then((res) => res.data),
    compare: (projectId: string, baseVersionId: string, targetVersionId: string) => axiosInstance.post<IFCComparison>(ENDPOINTS.IFC.COMPARISONS(projectId), { baseVersionId, targetVersionId }).then((res) => res.data),
    comparisonChanges: (projectId: string, comparisonId: string, filters: Record<string, unknown> = {}) => axiosInstance.get<any[]>(`${ENDPOINTS.IFC.COMPARISONS(projectId)}/${comparisonId}/changes?${parseQueryParams(filters)}`).then((res) => res.data),
    suggestions: (projectId: string, versionId?: string) => axiosInstance.get<IFCSuggestion[]>(`${ENDPOINTS.IFC.SUGGESTIONS(projectId)}?${parseQueryParams(versionId ? { versionId } : {})}`).then((res) => res.data),
    reviewSuggestion: (projectId: string, id: string, status: "ACCEPTED" | "REJECTED", editedPayload?: Record<string, unknown>) => axiosInstance.patch(`${ENDPOINTS.IFC.SUGGESTIONS(projectId)}/${id}`, { status, editedPayload }).then((res) => res.data),
    /* Paged, and filtered server-side. `versionId` is what bounds the query —
       findings accumulate per revision — and severity/discipline are matched
       on the server because filtering a page in the browser would filter only
       that page. */
    findings: (projectId: string, filters: Record<string, unknown> = {}) =>
      axiosInstance.get<IFCPage<IFCFinding>>(`${ENDPOINTS.IFC.FINDINGS(projectId)}?${parseQueryParams(filters)}`).then((res) => res.data),
    /* The four review actions `app/api/ifc.py` already exposes. `ignore` and
       `markFalsePositive` are the server's own shortcut routes for the same
       PATCH, kept as separate methods so a caller states the decision it is
       making rather than assembling a status string. All four require
       `ifc.review_finding`; `createIssue` additionally requires `issue.create`
       and is refused with 409 unless the finding is still PENDING. */
    reviewFinding: (projectId: string, findingId: string, status: IFCFindingReviewStatus, note?: string) =>
      axiosInstance.patch<IFCFindingReviewResult>(ENDPOINTS.IFC.FINDING(projectId, findingId), { status, note }).then((res) => res.data),
    ignoreFinding: (projectId: string, findingId: string) =>
      axiosInstance.post<IFCFindingReviewResult>(`${ENDPOINTS.IFC.FINDING(projectId, findingId)}/ignore`).then((res) => res.data),
    markFindingFalsePositive: (projectId: string, findingId: string) =>
      axiosInstance.post<IFCFindingReviewResult>(`${ENDPOINTS.IFC.FINDING(projectId, findingId)}/mark-false-positive`).then((res) => res.data),
    createIssueFromFinding: (projectId: string, findingId: string) =>
      axiosInstance.post<IFCFindingIssue>(`${ENDPOINTS.IFC.FINDING(projectId, findingId)}/create-issue`).then((res) => res.data),
  },
  aiIntelligence: {
    overview: (projectId:string) => axiosInstance.get<AIIntelligenceOverview>(ENDPOINTS.AI_INTELLIGENCE.OVERVIEW(projectId)).then(res=>res.data),
    insights: (projectId:string,filters:Record<string,unknown>={}) => axiosInstance.get<AIInsight[]>(`${ENDPOINTS.AI_INTELLIGENCE.INSIGHTS(projectId)}?${parseQueryParams(filters)}`).then(res=>res.data),
    sources: (projectId:string,id:string) => axiosInstance.get<AIInsightSource[]>(`${ENDPOINTS.AI_INTELLIGENCE.INSIGHT(projectId,id)}/sources`).then(res=>res.data),
    run: (projectId:string,versionId?:string) => axiosInstance.post(ENDPOINTS.AI_INTELLIGENCE.RUN(projectId),null,{params:versionId?{version_id:versionId}:undefined}).then(res=>res.data),
    review: (projectId:string,id:string,status:string,note?:string) => axiosInstance.patch<AIInsight>(ENDPOINTS.AI_INTELLIGENCE.INSIGHT(projectId,id),{status,note}).then(res=>res.data),
    createIssue: (projectId:string,id:string) => axiosInstance.post(`${ENDPOINTS.AI_INTELLIGENCE.INSIGHT(projectId,id)}/create-issue`).then(res=>res.data),
    createTask: (projectId:string,id:string,data:Record<string,unknown>={}) => axiosInstance.post(`${ENDPOINTS.AI_INTELLIGENCE.INSIGHT(projectId,id)}/create-task`,data).then(res=>res.data),
  },
  /**
   * The five project agents.
   *
   * Thin on purpose: these six endpoints already existed and were fully
   * tested, and had no client at all. Nothing is reshaped on the way through —
   * a finding's `certainty`, the tool calls a run made and the reason a skip
   * happened are all carried to the UI as the server stated them, because the
   * point of the run log is that it can be checked.
   */
  agents: {
    list: (projectId: string) =>
      axiosInstance.get<AgentCatalogue>(ENDPOINTS.AGENTS.BASE(projectId)).then((res) => res.data),
    runOne: (projectId: string, agentName: string) =>
      axiosInstance
        .post<AgentRunResult>(ENDPOINTS.AGENTS.RUN_ONE(projectId, agentName))
        .then((res) => res.data),
    /** One governed pass over every agent this caller may run. */
    orchestrate: (projectId: string) =>
      axiosInstance
        .post<OrchestrationReport>(ENDPOINTS.AGENTS.ORCHESTRATE(projectId))
        .then((res) => res.data),
    runs: (projectId: string, agentName?: string, limit = 50) =>
      axiosInstance
        .get<{ runs: AgentRunRecord[] }>(ENDPOINTS.AGENTS.RUNS(projectId), {
          params: { agent_name: agentName, limit },
        })
        .then((res) => res.data.runs),
    subscriptions: (projectId: string) =>
      axiosInstance
        .get<AgentSubscriptions>(ENDPOINTS.AGENTS.SUBSCRIPTIONS(projectId))
        .then((res) => res.data),
  },
  aiActions: {
    list: (projectId:string,page=1,pageSize=25) => axiosInstance
      .get<AIActionPage>(ENDPOINTS.AI_ACTIONS.BASE,{params:{project_id:projectId,page,page_size:pageSize}})
      .then(res=>res.data),
    get: (id:string) => axiosInstance.get<AIActionVersion>(ENDPOINTS.AI_ACTIONS.ACTION(id)).then(res=>res.data),
    revert: (id:string,requestId:string,reason:string) => axiosInstance
      .post<{action:AIActionVersion;message:string}>(ENDPOINTS.AI_ACTIONS.REVERT(id),{requestId,reason})
      .then(res=>res.data),
    revertLast: (projectId:string,requestId:string,reason:string) => axiosInstance
      .post<{action:AIActionVersion;message:string}>(ENDPOINTS.AI_ACTIONS.REVERT_LAST,{requestId,reason},{params:{project_id:projectId}})
      .then(res=>res.data),
  },

  /**
   * The unified file ingestion pipeline.
   *
   * Separate from `api.documents`, which it does not replace: a document is a
   * library entry with a title and a type somebody chose, while this is the
   * file itself — including the members of a design package, which have no
   * library entry of their own.
   */
  ingestion: {
    constraints: (projectId: string) =>
      axiosInstance
        .get<IngestionUploadConstraints>(
          ENDPOINTS.INGESTION.UPLOAD_CONSTRAINTS(projectId),
        )
        .then((res) => res.data),
    list: (projectId: string, filters?: IngestedFileFilters) =>
      axiosInstance
        .get<IngestedFilePage>(
          `${ENDPOINTS.INGESTION.BASE(projectId)}?${parseQueryParams(filters || {})}`,
        )
        .then((res) => res.data),
    getById: (projectId: string, fileId: string) =>
      axiosInstance
        .get<IngestedFile>(ENDPOINTS.INGESTION.FILE(projectId, fileId))
        .then((res) => res.data),
    upload: (projectId: string, file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return axiosInstance
        .post<IngestedFile>(ENDPOINTS.INGESTION.BASE(projectId), formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((res) => res.data);
    },
    retry: (projectId: string, fileId: string) =>
      axiosInstance
        .post<IngestionRetryResult>(ENDPOINTS.INGESTION.RETRY(projectId, fileId))
        .then((res) => res.data),
    // A blob, not a URL: the server streams the object and never publishes
    // where it is stored.
    download: (projectId: string, fileId: string) =>
      axiosInstance
        .get<Blob>(ENDPOINTS.INGESTION.DOWNLOAD(projectId, fileId), {
          responseType: "blob",
        })
        .then((res) => res.data),
  },

  /**
   * MCP client tokens.
   *
   * Authenticated with the session like every other call in this file, which
   * is the point: an MCP token is understood only by the MCP endpoint, so it
   * cannot reach these routes and cannot mint itself a replacement.
   *
   * There is no `getById`. A token is only ever read as part of the list, and
   * the one thing a single-token endpoint could add — the secret — does not
   * exist on the server after the moment it was created.
   */
  mcpTokens: {
    list: (includeRevoked = false) =>
      axiosInstance
        .get<McpToken[]>(ENDPOINTS.MCP.TOKENS, {
          params: { include_revoked: includeRevoked },
        })
        .then((res) => res.data),
    // The only response in the application that carries a credential. Never
    // logged, never stored: the page shows it once and forgets it.
    create: (data: McpTokenCreateRequest) =>
      axiosInstance
        .post<McpTokenCreated>(ENDPOINTS.MCP.TOKENS, data)
        .then((res) => res.data),
    revoke: (tokenId: string) =>
      axiosInstance
        .delete<void>(ENDPOINTS.MCP.TOKEN(tokenId))
        .then((res) => res.data),
  },

  upload: {
    single: (file: File, folder?: string) => {
      const formData = new FormData();
      formData.append("file", file);
      if (folder) formData.append("folder", folder);
      return axiosInstance
        .post<{ url: string; fileId: string }>(
          ENDPOINTS.UPLOAD.SINGLE,
          formData,
          {
            headers: { "Content-Type": "multipart/form-data" },
          },
        )
        .then((res) => res.data);
    },
  },
};

export default api;
