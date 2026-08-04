abstract final class ApiEndpoints {
  static const login = '/auth/login';
  static const refresh = '/auth/refresh';
  static const me = '/auth/me';
  static const logout = '/auth/logout';
  static const forgotPassword = '/auth/forgot-password';
  static const company = '/company/settings';
  static const projects = '/projects';
  static String ownerDashboard(String id) => '/projects/$id/owner-dashboard';
  static const myTasks = '/tasks/my-tasks';
  static String projectTasks(String id) => '/tasks/project/$id';
  static String task(String id) => '/tasks/$id';
  static String progress(String id) => '/tasks/$id/progress';
  static String startTask(String id) => '/tasks/$id/start';
  static String workUpdates(String id) => '/tasks/$id/work-updates';
  static String comments(String id) => '/tasks/$id/comments';
  static String blockers(String id) => '/tasks/$id/blockers';
  static String submitReview(String id) => '/tasks/$id/submit-review';
  static String engineerDashboard(String id) =>
      '/dashboard/engineer/projects/$id';
  static String projectDashboard(String id) => '/dashboard/projects/$id';
  static String consultantDashboard(String id) =>
      '/consultant/projects/$id/dashboard';
  static String consultantReviews(String id) =>
      '/consultant/projects/$id/reviews';
  static String consultantReview(String projectId, String reviewId) =>
      '/consultant/projects/$projectId/reviews/$reviewId';
  static String startReview(String id) => '/tasks/$id/start-review';
  static String approveTask(String id) => '/tasks/$id/approve';
  static String rejectTask(String id) => '/tasks/$id/reject';
  static String requestClarification(String id) =>
      '/tasks/$id/request-clarification';
  static String siteReports(String id) => '/site-reports/project/$id';
  static const submitSiteReport = '/site-reports/submit';
  static String issues(String id) => '/issues/project/$id';
  static const createIssue = '/issues';
  static const notifications = '/notifications';
  static const unreadNotifications = '/notifications/unread-count';
  static String readNotification(String id) => '/notifications/$id/read';
  static const messages = '/messages';
  static const participants = '/messages/participants';
  static const messageConversations = '/messages/conversations';
  static const messageRecipientOptions = '/messages/recipient-options';
  static const messageAnnouncements = '/messages/announcements';
  static String conversation(String id) => '/messages/conversations/$id';
  static String conversationMessages(String id) =>
      '/messages/conversations/$id/messages';
  static String conversationRead(String id) =>
      '/messages/conversations/$id/read';
  static String messageContext(String type, String id) =>
      '/messages/context/$type/$id';
  static const profile = '/users/profile';
  static const attachments = '/attachments/upload';
  static const fieldSubmissions = '/field-submissions';
  static String taskFieldSubmissions(String taskId) =>
      '/field-submissions/task/$taskId';
  static const myFieldSubmissions = '/field-submissions/mine';
  static const workerDashboard = '/field-submissions/worker-dashboard';
  static String photoCategories(String projectId) =>
      '/projects/$projectId/photo-categories';
  static String ifcModels(String projectId) => '/projects/$projectId/ifc/models';
  static String ifcVersions(String projectId, String modelId) =>
      '/projects/$projectId/ifc/models/$modelId/versions';
  static const fieldContext = '/field/context';
  static const validateProposal = '/field/action-proposals/validate';
  static const confirmProposal = '/field/action-proposals/confirm';
  static const aiTranscribe = '/ai/transcribe';
  static const aiAnalyzeCommand = '/ai/analyze-command';
  static const voiceAnalyses = '/ai/voice-analyses';
  static const voiceCommands = '/voice/commands';
  static const aiActions = '/ai/actions';
  static String revertAiAction(String id) => '/ai/actions/$id/revert';
  static String voiceCommand(String id) => '/voice/commands/$id';
  static String voiceDraft(String commandId, String draftId) =>
      '/voice/commands/$commandId/draft-actions/$draftId';
  static String voiceClarifications(String id) =>
      '/voice/commands/$id/clarifications';
  static String confirmVoiceCommand(String id) =>
      '/voice/commands/$id/confirm';
  static String executeVoiceCommand(String id) =>
      '/voice/commands/$id/execute';
  static String voiceAnalysis(String id) => '/ai/voice-analyses/$id';
  static const ownerRequests = '/owner-requests';
  static String ownerRequest(String id) => '/owner-requests/$id';
  static const siteVisits = '/site-visits';
  static const myActionCenter = '/my-action-center';
  static String projectActivity(String id) => '/projects/$id/activity';
  static String retryVoiceAnalysis(String id) =>
      '/ai/voice-analyses/$id/retry';
  static String confirmVoiceAnalysis(String id) =>
      '/ai/voice-analyses/$id/confirm';
}
