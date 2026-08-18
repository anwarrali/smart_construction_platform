// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppL10nEn extends AppL10n {
  AppL10nEn([String locale = 'en']) : super(locale);

  @override
  String get commonLoading => 'Loading…';

  @override
  String get commonRetry => 'Retry';

  @override
  String get commonCancel => 'Cancel';

  @override
  String get commonConfirm => 'Confirm';

  @override
  String get commonSubmit => 'Submit';

  @override
  String get commonSubmitting => 'Submitting…';

  @override
  String get commonSaveDraft => 'Save Draft';

  @override
  String get commonCreate => 'Create';

  @override
  String get commonDelete => 'Delete';

  @override
  String get commonUpdate => 'Update';

  @override
  String get commonApprove => 'Approve';

  @override
  String get commonDone => 'Done';

  @override
  String get commonAll => 'All';

  @override
  String get commonOptional => '(optional)';

  @override
  String get commonStatus => 'Status';

  @override
  String get commonPriority => 'Priority';

  @override
  String get commonDiscipline => 'Discipline';

  @override
  String get commonDescription => 'Description';

  @override
  String get commonTitle => 'Title';

  @override
  String get commonCategory => 'Category';

  @override
  String get commonNote => 'Note';

  @override
  String get commonProject => 'Project';

  @override
  String get commonProgress => 'Progress';

  @override
  String get commonNotifications => 'Notifications';

  @override
  String get commonToday => 'Today';

  @override
  String get commonYesterday => 'Yesterday';

  @override
  String get commonViewAll => 'View all';

  @override
  String get commonSignOut => 'Sign out';

  @override
  String get commonLogOut => 'Log out';

  @override
  String get commonSelectProject => 'Select a project';

  @override
  String get commonSelectProjectFirst => 'Select a project first.';

  @override
  String get commonNoProjectSelected => 'No project selected';

  @override
  String get commonNothingHereYet => 'Nothing here yet';

  @override
  String commonUnavailable(String subject) {
    return '$subject unavailable';
  }

  @override
  String commonPercent(String value) {
    return '$value%';
  }

  @override
  String get navHome => 'Home';

  @override
  String get navTasks => 'Tasks';

  @override
  String get navMyTasks => 'My Tasks';

  @override
  String get navReports => 'Reports';

  @override
  String get navMessages => 'Messages';

  @override
  String get navProfile => 'Profile';

  @override
  String get navReviews => 'Reviews';

  @override
  String get navDocuments => 'Documents';

  @override
  String get navIssues => 'Issues';

  @override
  String get navProjects => 'Projects';

  @override
  String get navEvidence => 'Evidence';

  @override
  String get navMyActions => 'My Actions';

  @override
  String get navIfcModels => 'IFC Models';

  @override
  String get navFieldEvidence => 'Field Evidence';

  @override
  String get navRecordUpdate => 'Record Update';

  @override
  String get navRecordFieldUpdate => 'Record field update';

  @override
  String get errorGeneric => 'Something went wrong. Please try again.';

  @override
  String get errorTimeout =>
      'The server took too long to respond. Please retry.';

  @override
  String get errorNetwork =>
      'Cannot reach the project server. Check that the server is running and that this device is on the correct network.';

  @override
  String get errorUnauthorized => 'You are not signed in.';

  @override
  String get errorForbidden => 'You do not have permission to do this.';

  @override
  String get errorNotFound => 'That record could not be found.';

  @override
  String get errorConflict => 'This conflicts with an existing record.';

  @override
  String get errorValidation => 'Please correct the highlighted fields.';

  @override
  String get errorLoadFailed => 'This information could not be loaded.';

  @override
  String get errorSaveFailed => 'Your changes could not be saved.';

  @override
  String get errorActionFailed => 'The action could not be completed.';

  @override
  String get validationRequired => 'This field is required.';

  @override
  String get validationEnterEmailOrUsername => 'Enter your email or username.';

  @override
  String get validationEnterPassword => 'Enter your password.';

  @override
  String get validationEnterIssueTitle => 'Enter an issue title.';

  @override
  String get validationDescribeIssue => 'Describe the issue.';

  @override
  String get validationAddReportSummary => 'Add the report summary.';

  @override
  String get validationCompleteRequiredFields =>
      'Complete all required fields.';

  @override
  String get validationEnterClarificationQuestion =>
      'Enter a clarification question.';

  @override
  String get brandDescriptor => 'Smart Construction Management';

  @override
  String get loginSignIn => 'Sign in';

  @override
  String get loginSubtitle => 'Use your organization account to continue.';

  @override
  String get loginEmailLabel => 'Email or username';

  @override
  String get loginEmailHint => 'name@company.com';

  @override
  String get loginPasswordLabel => 'Password';

  @override
  String get loginPasswordHint => 'Enter your password';

  @override
  String get loginShowPassword => 'Show password';

  @override
  String get loginHidePassword => 'Hide password';

  @override
  String get loginSubmit => 'Sign in securely';

  @override
  String get loginNeedHelp => 'Need help? Contact Administrator';

  @override
  String get loginSecureAccess =>
      'Secure access · Authorized project members only';

  @override
  String get loginInvalidCredentials => 'Incorrect email/username or password.';

  @override
  String get loginAccountDeactivated =>
      'Your account has been deactivated. Contact your administrator.';

  @override
  String get loginTooManyAttempts =>
      'Too many failed sign-in attempts. Try again later.';

  @override
  String get loginWelcomeBack => 'Welcome Back';

  @override
  String get loginWelcomeBody =>
      'Manage projects, field activities, and team collaboration from anywhere.';

  @override
  String get projectsLoading => 'Loading assigned projects';

  @override
  String get projectsTitle => 'Projects';

  @override
  String get projectsNoneAssigned => 'No projects assigned';

  @override
  String get projectsNoneAssignedBody =>
      'Contact your administrator or project manager for access, or switch to another account.';

  @override
  String get projectsSwitchAccount => 'Switch account';

  @override
  String get projectsSwitchAccountQuestion => 'Switch account?';

  @override
  String get projectsSwitchAccountBody =>
      'You will be signed out and returned to the sign-in screen.';

  @override
  String get projectsMyProjects => 'My Projects';

  @override
  String get projectsSelectWorkspace => 'Select a workspace to continue';

  @override
  String get projectsProgress => 'Project progress';

  @override
  String projectsOpenIssues(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count open issues',
      one: '$count open issue',
    );
    return '$_temp0';
  }

  @override
  String get projectsCurrentProject => 'Current project';

  @override
  String get projectsOpenWorkspace => 'Open workspace';

  @override
  String get statusBacklog => 'Backlog';

  @override
  String get statusTodo => 'To do';

  @override
  String get statusInProgress => 'In progress';

  @override
  String get statusUnderReview => 'Under review';

  @override
  String get statusReworkRequired => 'Rework required';

  @override
  String get statusDone => 'Done';

  @override
  String get statusBlocked => 'Blocked';

  @override
  String get statusCancelled => 'Cancelled';

  @override
  String get statusOpen => 'Open';

  @override
  String get statusResolved => 'Resolved';

  @override
  String get statusClosed => 'Closed';

  @override
  String get statusPending => 'Pending';

  @override
  String get statusInReview => 'In review';

  @override
  String get statusApproved => 'Approved';

  @override
  String get statusRejected => 'Rejected';

  @override
  String get statusClarificationRequested => 'Clarification requested';

  @override
  String get statusDraft => 'Draft';

  @override
  String get statusSubmitted => 'Submitted';

  @override
  String get statusProposed => 'Proposed';

  @override
  String get statusImplemented => 'Implemented';

  @override
  String get statusPlanning => 'Planning';

  @override
  String get statusActive => 'Active';

  @override
  String get statusOnHold => 'On hold';

  @override
  String get statusDelayed => 'Delayed';

  @override
  String get statusCompleted => 'Completed';

  @override
  String get statusVerified => 'Verified';

  @override
  String get statusOnTrack => 'On track';

  @override
  String get statusAtRisk => 'At risk';

  @override
  String get priorityLow => 'Low';

  @override
  String get priorityMedium => 'Medium';

  @override
  String get priorityHigh => 'High';

  @override
  String get priorityCritical => 'Critical';

  @override
  String get priorityNormal => 'Normal';

  @override
  String get priorityImportant => 'Important';

  @override
  String get priorityInfo => 'Info';

  @override
  String get disciplineCivil => 'Civil';

  @override
  String get disciplineArchitectural => 'Architectural';

  @override
  String get disciplineElectrical => 'Electrical';

  @override
  String get disciplineMechanical => 'Mechanical';

  @override
  String get disciplineStructural => 'Structural';

  @override
  String get disciplinePlumbing => 'Plumbing';

  @override
  String get disciplineHvac => 'HVAC';

  @override
  String get disciplineFireProtection => 'Fire protection';

  @override
  String get disciplineGeneral => 'General';

  @override
  String get disciplineUnclassified => 'Unclassified';

  @override
  String get disciplineUnassigned => 'Unassigned';

  @override
  String get roleAdmin => 'Administrator';

  @override
  String get roleOwner => 'Owner';

  @override
  String get roleProjectManager => 'Project manager';

  @override
  String get roleEngineer => 'Engineer';

  @override
  String get roleConsultant => 'Consultant';

  @override
  String get roleWorker => 'Worker';

  @override
  String get roleCaptionSiteEngineer => 'Main Contractor · Site Engineer';

  @override
  String get roleCaptionConsultant => 'Consultant Engineer · Review & Quality';

  @override
  String get roleCaptionOwner => 'Project Owner · Executive View';

  @override
  String get roleCaptionWorker => 'Construction Worker · Field Evidence';

  @override
  String get roleCaptionProjectManager => 'Project Manager · Field Monitoring';

  @override
  String get roleCaptionConsultantShort => 'Consultant Engineer';

  @override
  String get dashboardSelectProjectBody =>
      'Choose a project to see its dashboard.';

  @override
  String get dashboardLoading => 'Loading project dashboard';

  @override
  String get dashboardTitle => 'Dashboard';

  @override
  String get dashboardGreetingMorning => 'Good morning';

  @override
  String get dashboardGreetingAfternoon => 'Good afternoon';

  @override
  String get dashboardGreetingEvening => 'Good evening';

  @override
  String dashboardGreeting(String greeting, String name) {
    return '$greeting, $name';
  }

  @override
  String get dashboardChangeProject => 'Change project';

  @override
  String get dashboardFastFieldUpdate => 'Fast field update';

  @override
  String get dashboardFastFieldUpdateBody =>
      'Capture work without stopping your workflow';

  @override
  String get dashboardExecutiveIntelligence => 'Executive intelligence';

  @override
  String get dashboardExecutiveIntelligenceBody =>
      'Current status and future smart insights';

  @override
  String get dashboardNeedsAttention => 'Needs your attention';

  @override
  String get dashboardProjectSnapshot => 'Project snapshot';

  @override
  String get dashboardQuickAccess => 'Quick access';

  @override
  String get dashboardQuickAccessBody => 'Role-appropriate project tools';

  @override
  String get dashboardRecentActivity => 'Recent activity';

  @override
  String get dashboardRecentActivityBody =>
      'Latest information from this project';

  @override
  String get dashboardSnapshotEngineer =>
      'Tasks, blockers, and reviews that need action';

  @override
  String get dashboardSnapshotConsultant =>
      'Review workload and submitted work';

  @override
  String get dashboardSnapshotOwner =>
      'High-level progress, risk, and decisions';

  @override
  String get dashboardSnapshotManager => 'Execution health and team priorities';

  @override
  String get dashboardPendingReviews => 'Pending reviews';

  @override
  String get dashboardOverdueReviews => 'Overdue reviews';

  @override
  String get dashboardApprovedWork => 'Approved work';

  @override
  String get dashboardAwaitingRework => 'Awaiting rework';

  @override
  String get dashboardDelayedTasks => 'Delayed tasks';

  @override
  String get dashboardOpenRisks => 'Open risks';

  @override
  String get dashboardDecisions => 'Decisions';

  @override
  String get dashboardMilestones => 'Milestones';

  @override
  String get dashboardAssignedTasks => 'Assigned tasks';

  @override
  String get dashboardSubmitted => 'Submitted';

  @override
  String get dashboardVerified => 'Verified';

  @override
  String get dashboardNeedsCorrection => 'Needs correction';

  @override
  String get dashboardTodaysTasks => 'Today’s tasks';

  @override
  String get dashboardOverdue => 'Overdue';

  @override
  String get dashboardBlocked => 'Blocked';

  @override
  String get dashboardWaitingReview => 'Waiting review';

  @override
  String get dashboardReworkRequired => 'Rework required';

  @override
  String get dashboardOpenIssues => 'Open issues';

  @override
  String get dashboardOverallProgress => 'Overall progress';

  @override
  String get dashboardLiveProjectData => 'Live project data';

  @override
  String dashboardProgressSemantics(String progress, String health) {
    return 'Overall progress is $progress%. Project health is $health.';
  }

  @override
  String dashboardExecutiveSummary(
    String progress,
    String health,
    int delayed,
    int risks,
  ) {
    return 'Overall progress is $progress%. Project health is $health. There are $delayed delayed tasks and $risks open risks requiring visibility.';
  }

  @override
  String get dashboardSummaryTitle => 'Smart Project Summary';

  @override
  String get dashboardSummarySubtitle => 'Executive project intelligence';

  @override
  String get dashboardLiveData => 'LIVE DATA';

  @override
  String get dashboardAiReady => 'AI READY';

  @override
  String get dashboardAiPlaceholder =>
      'AI-generated insights will appear here when the summary service is connected. Current project metrics remain available below.';

  @override
  String get dashboardGeneratedFrom =>
      'Generated from current backend metrics · No external AI';

  @override
  String get dashboardFutureIntegration =>
      'Future integration placeholder · No fabricated insights';

  @override
  String get dashboardNoActivity =>
      'New project activity will appear here as your team works.';

  @override
  String get dashboardProjectActivity => 'Project activity';

  @override
  String get tasksMyTasks => 'My Tasks';

  @override
  String get tasksProjectTasks => 'Project Tasks';

  @override
  String get tasksLoading => 'Loading tasks';

  @override
  String get tasksTitle => 'Tasks';

  @override
  String get tasksTotal => 'Total';

  @override
  String get tasksOverdue => 'Overdue';

  @override
  String get tasksBlocked => 'Blocked';

  @override
  String get tasksNoMatching => 'No matching tasks';

  @override
  String get tasksNoAssigned => 'There are no assigned tasks in this view.';

  @override
  String get tasksFilterRework => 'Rework';

  @override
  String get taskDetailTitle => 'Task Details';

  @override
  String get taskTitle => 'Task';

  @override
  String taskPercentComplete(String percent) {
    return '$percent% complete';
  }

  @override
  String get taskCannotStartYet => 'Cannot start yet';

  @override
  String get taskQuickActions => 'Quick actions';

  @override
  String get taskDiscussion => 'Task Discussion';

  @override
  String get taskVoiceUpdate => 'AI Voice Field Update';

  @override
  String get taskStart => 'Start Task';

  @override
  String get taskUpdateProgress => 'Update Progress';

  @override
  String get taskAddComment => 'Add Comment';

  @override
  String get taskSubmitForReview => 'Submit for Review';

  @override
  String get taskCreateFieldUpdate => 'Create Field Update';

  @override
  String get taskEvidenceHistory => 'My Evidence History';

  @override
  String get taskNoPermission =>
      'You do not have permission to update this task.';

  @override
  String get taskUpdated => 'Task updated.';

  @override
  String get taskWorkNote => 'Work note (optional)';

  @override
  String get taskDependencyBlocked => 'Dependency blocked';

  @override
  String taskDueOn(String date) {
    return 'Due $date';
  }

  @override
  String taskDaysOverdue(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count days overdue',
      one: '$count day overdue',
    );
    return '$_temp0';
  }

  @override
  String taskDependencyLine(String name, String status) {
    return '· $name ($status)';
  }

  @override
  String get taskBlockingTask => 'Blocking task';

  @override
  String get issuesTitle => 'Issues & Blockers';

  @override
  String get issuesEmpty => 'No issues have been reported.';

  @override
  String get issueReport => 'Report Issue';

  @override
  String get issueTitleLabel => 'Issue title';

  @override
  String get issueSeverity => 'Severity';

  @override
  String get issueAffectsSchedule => 'Affects project schedule';

  @override
  String get issueAffectsScheduleBody =>
      'Flag this issue for schedule attention.';

  @override
  String get issueSubmit => 'Submit Issue';

  @override
  String get issueReported => 'Issue reported successfully.';

  @override
  String get issueCategoryMaterialUnavailable => 'Material unavailable';

  @override
  String get issueCategoryPreviousTaskIncomplete => 'Previous task incomplete';

  @override
  String get issueCategoryDrawingUnavailable => 'Drawing unavailable';

  @override
  String get issueCategoryEquipmentUnavailable => 'Equipment unavailable';

  @override
  String get issueCategoryLaborShortage => 'Labor shortage';

  @override
  String get issueCategorySiteAccess => 'Site access issue';

  @override
  String get issueCategoryConsultantClarification =>
      'Consultant clarification required';

  @override
  String get issueCategoryTechnicalConflict => 'Technical conflict';

  @override
  String get issueCategorySafetyRestriction => 'Safety restriction';

  @override
  String get issueCategoryOther => 'Other';

  @override
  String get siteReportsTitle => 'Site Reports';

  @override
  String get siteReportsEmpty => 'No site reports have been submitted.';

  @override
  String get siteReportCreate => 'Create Site Report';

  @override
  String get siteReportDate => 'Report date';

  @override
  String get siteReportWorkSummary => 'Work summary';

  @override
  String get siteReportWorkCompleted => 'Work completed';

  @override
  String get siteReportWeather => 'Weather conditions';

  @override
  String get siteReportWorkersCount => 'Workers count';

  @override
  String get siteReportEquipment => 'Equipment used';

  @override
  String get siteReportDelays => 'Delays or constraints';

  @override
  String get siteReportSubmit => 'Submit Report';

  @override
  String get siteReportDraftSaved => 'Report draft saved.';

  @override
  String get siteReportSubmitted => 'Site report submitted.';

  @override
  String get documentsTitle => 'Documents';

  @override
  String get documentsEmpty => 'No documents are available.';

  @override
  String get messagesTitle => 'Messages';

  @override
  String messagesTitleWithProject(String project) {
    return 'Messages · $project';
  }

  @override
  String get messagesNew => 'New';

  @override
  String get messagesLoading => 'Loading conversations';

  @override
  String get messagesEmptyTitle => 'No conversations yet';

  @override
  String get messagesEmptyBody =>
      'Messages you send or receive on this project will appear here.';

  @override
  String get messagesNoMessages => 'No messages';

  @override
  String get messagesNewConversation => 'New Project Conversation';

  @override
  String get messagesAnnouncement => 'Project/team announcement';

  @override
  String get messagesPeople => 'People';

  @override
  String get messagesTeamGroup => 'Team / Group';

  @override
  String get messagesRecipientGroup => 'Recipient group';

  @override
  String messagesGroupWithCount(String label, int count) {
    return '$label ($count)';
  }

  @override
  String get messagesTitleOptional => 'Title (optional)';

  @override
  String get messagesMessage => 'Message';

  @override
  String get messagesSend => 'Send';

  @override
  String get messagesProjectDiscussion => 'Project discussion';

  @override
  String get conversationTitle => 'Project Conversation';

  @override
  String conversationContextTitle(String context) {
    return '$context Discussion';
  }

  @override
  String get conversationWriteMessage => 'Write a project message…';

  @override
  String get conversationLoading => 'Loading conversation';

  @override
  String get conversationTitleShort => 'Conversation';

  @override
  String get conversationStartTitle => 'Start the discussion';

  @override
  String get conversationStartBody =>
      'Send the first contextual project message.';

  @override
  String communicationForwardedFrom(String sender) {
    return 'Forwarded from $sender';
  }

  @override
  String get entityIssue => 'Issue';

  @override
  String get entityTask => 'Task';

  @override
  String get entitySiteReport => 'Site report';

  @override
  String get entityDesignChange => 'Design change';

  @override
  String get entityDocument => 'Document';

  @override
  String get notificationsTitle => 'Notifications';

  @override
  String notificationsUnreadCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count unread',
      one: '$count unread',
    );
    return '$_temp0';
  }

  @override
  String get notificationsReadAll => 'Read all';

  @override
  String get notificationsFilterUnread => 'Unread';

  @override
  String get notificationsLoading => 'Loading notifications';

  @override
  String get notificationsEmptyUnreadTitle => 'No unread notifications';

  @override
  String get notificationsEmptyUnreadBody =>
      'New unread notifications will appear here.';

  @override
  String get notificationsEmptyTitle => 'You are all caught up';

  @override
  String get notificationsEmptyBody =>
      'Project updates and team activity will appear here.';

  @override
  String get notificationReminder => 'Reminder';

  @override
  String get notificationFallbackTitle => 'Notification';

  @override
  String get notificationDetailTitle => 'Notification Details';

  @override
  String get notificationDetailMustOpen =>
      'This notification must be opened from the notification list.';

  @override
  String get notificationOpenTask => 'Open Task';

  @override
  String get notificationOpenMessages => 'Open Messages';

  @override
  String get notificationOpenIssues => 'Open Issues';

  @override
  String get notificationOpenReviews => 'Open Reviews';

  @override
  String get notificationOpenReports => 'Open Reports';

  @override
  String get notificationOpenProject => 'Open Project';

  @override
  String get notifTaskDueTomorrowTitle => 'Task due tomorrow';

  @override
  String notifTaskDueTomorrowBody(String name) {
    return '$name is due tomorrow.';
  }

  @override
  String get notifTaskDueTodayTitle => 'Task due today';

  @override
  String notifTaskDueTodayBody(String name) {
    return '$name is due today.';
  }

  @override
  String get notifTaskOverdueTitle => 'Task overdue';

  @override
  String notifTaskOverdueBody(String name) {
    return '$name is overdue.';
  }

  @override
  String notifTaskOverdueSeveralBody(String name) {
    return '$name has been overdue for several days.';
  }

  @override
  String notifTaskOverdueWeekBody(String name) {
    return '$name has been overdue for more than a week.';
  }

  @override
  String get notifSiteReportAwaitingTitle =>
      'Site report awaiting your verification';

  @override
  String notifSiteReportAwaitingBody(String project) {
    return 'A site report was submitted for $project.';
  }

  @override
  String get notifSiteReportVerifiedTitle => 'Site report verified';

  @override
  String notifSiteReportVerifiedBody(String date, String reviewer) {
    return 'Your site report for $date was verified by $reviewer.';
  }

  @override
  String get notifSiteReportRejectedTitle => 'Site report rejected';

  @override
  String notifSiteReportRejectedBody(
    String date,
    String reviewer,
    String reason,
  ) {
    return 'Your site report for $date was rejected by $reviewer: $reason';
  }

  @override
  String notifReminderWaitingTitle(String label) {
    return 'Response reminder: $label';
  }

  @override
  String notifReminderWaitingBody(String target, String sequence) {
    return 'This $target is still waiting for action. Reminder $sequence.';
  }

  @override
  String notifReminderEscalationTitle(String label) {
    return 'Escalation: $label';
  }

  @override
  String notifReminderEscalationBody(String target) {
    return 'This $target has been waiting too long and has been escalated.';
  }

  @override
  String get notifStepUpRequestedTitle => 'Verification code requested';

  @override
  String notifStepUpRequestedBody(String action) {
    return 'A verification code was requested to confirm: $action. If this was not you, change your password immediately.';
  }

  @override
  String get profileAccountInformation => 'Account information';

  @override
  String get profileEmail => 'Email';

  @override
  String get profilePhone => 'Phone';

  @override
  String get profileOrganization => 'Organization';

  @override
  String get profileAccountStatus => 'Account status';

  @override
  String get profileLanguage => 'Language';

  @override
  String get profileLanguageBody =>
      'Choose the app language, or follow your device.';

  @override
  String get languageSystem => 'Device language';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageArabic => 'العربية';

  @override
  String get profileSecurity => 'Security';

  @override
  String get profileSecureSession => 'Secure mobile session';

  @override
  String get profileSecureSessionBody =>
      'Authentication tokens are stored in encrypted device storage.';

  @override
  String get reviewsPendingTitle => 'Pending Reviews';

  @override
  String get reviewsTitle => 'Reviews';

  @override
  String get reviewsSelectProjectBody =>
      'Choose a project before opening consultant reviews.';

  @override
  String get reviewsLoading => 'Loading review submissions';

  @override
  String get reviewsEmptyTitle => 'Nothing waiting for review';

  @override
  String get reviewsEmptyBody =>
      'New submissions matching your discipline will appear here.';

  @override
  String get reviewCritical => 'Critical';

  @override
  String get reviewOverdue => 'Overdue';

  @override
  String reviewAttempt(String number) {
    return 'Attempt $number';
  }

  @override
  String reviewSubmittedAt(String date) {
    return 'Submitted $date';
  }

  @override
  String reviewEvidenceCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count evidence items',
      one: '$count evidence item',
    );
    return '$_temp0';
  }

  @override
  String get reviewSubmissionFallback => 'Review submission';

  @override
  String get reviewSubmissionTitle => 'Review Submission';

  @override
  String get reviewLoadingSubmission => 'Loading submission and evidence';

  @override
  String get reviewUnableToOpen => 'Unable to open review';

  @override
  String get reviewNotFound => 'Review submission not found.';

  @override
  String get reviewTaskReview => 'Task review';

  @override
  String get reviewTaskAndSubmission => 'Task and submission';

  @override
  String get reviewSubmission => 'Submission';

  @override
  String get reviewCompletionNote => 'Completion note';

  @override
  String reviewSubmittedEvidence(int count) {
    return 'Submitted evidence ($count)';
  }

  @override
  String get reviewNoEvidence => 'No evidence was attached to this submission.';

  @override
  String get reviewAttachment => 'Attachment';

  @override
  String get reviewDependencyImpact => 'Dependency impact';

  @override
  String reviewPredecessors(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count predecessors',
      one: '$count predecessor',
    );
    return '$_temp0';
  }

  @override
  String reviewDependentTasks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count dependent tasks',
      one: '$count dependent task',
    );
    return '$_temp0';
  }

  @override
  String get reviewGatingWork =>
      'Approval is currently gating downstream work.';

  @override
  String get reviewStart => 'Start Review';

  @override
  String get reviewApproveSubmission => 'Approve Submission';

  @override
  String get reviewRequestClarification => 'Request Clarification';

  @override
  String get reviewRequestRework => 'Request Rework';

  @override
  String get reviewStarted => 'Review started.';

  @override
  String get reviewApprovalHint =>
      'Approval marks this task complete and may unlock dependent work.';

  @override
  String get reviewRejectionReasonRequired => 'Rejection reason *';

  @override
  String get reviewRequiredCorrections => 'Required corrections *';

  @override
  String get reviewClarificationQuestion => 'Clarification question *';

  @override
  String get reviewComments => 'Review comments *';

  @override
  String get reviewNoteOptional => 'Review note (optional)';

  @override
  String get reviewApproved => 'Submission approved successfully.';

  @override
  String get reviewReworkRecorded => 'Rework request recorded.';

  @override
  String get reviewClarificationRequested => 'Clarification requested.';

  @override
  String get collabMyActions => 'My Actions';

  @override
  String get collabSelectProjectBody =>
      'Choose a project to see accountable actions.';

  @override
  String get collabTabActions => 'Actions';

  @override
  String get collabTabRequests => 'Requests';

  @override
  String get collabTabVisits => 'Visits';

  @override
  String get collabNewRequest => 'New request';

  @override
  String get collabSchedule => 'Schedule';

  @override
  String get collabOwnerRequest => 'Client / Owner Request';

  @override
  String get collabRequestHint =>
      'This request does not modify the official design.';

  @override
  String get collabSubmitForReview => 'Submit for engineering review';

  @override
  String get collabRequestSubmitted =>
      'Request submitted for human engineering review.';

  @override
  String get collabScheduleVisit => 'Schedule site visit';

  @override
  String get collabSiteLocation => 'Site / location';

  @override
  String get collabStart => 'Start';

  @override
  String get collabEnd => 'End';

  @override
  String get collabReviewAndSchedule => 'Review and schedule';

  @override
  String get collabVisitScheduled => 'Site visit scheduled.';

  @override
  String get collabActionCenter => 'Action center';

  @override
  String get collabWhatNeedsAttention => 'What needs my attention right now?';

  @override
  String get collabAiAdvisory => 'AI is advisory';

  @override
  String get collabAiAdvisoryBody =>
      'AI alerts require human review and retain their project sources.';

  @override
  String get collabRequestsTitle => 'Requests';

  @override
  String get collabNoRequests => 'No active owner requests';

  @override
  String get collabNoRequestsBody =>
      'New client requests and engineering responses will appear here.';

  @override
  String get collabScheduleTitle => 'Schedule';

  @override
  String get collabNoVisits => 'No site visits scheduled';

  @override
  String get collabNoVisitsBody =>
      'Visits across assigned projects will appear here.';

  @override
  String get collabAcknowledge => 'Acknowledge action';

  @override
  String get collabNeedsMyResponse => 'Needs my response';

  @override
  String get collabOwnerRequests => 'Client requests';

  @override
  String get collabRequiresActionNotifications =>
      'Notifications requiring action';

  @override
  String get collabUpcomingSiteVisits => 'Upcoming site visits';

  @override
  String get collabAiAlertsRequiringReview => 'AI alerts to review';

  @override
  String get collabTasksUnderReview => 'Tasks under review';

  @override
  String get collabVisitTypeRoutine => 'Routine inspection';

  @override
  String get collabVisitTypeQuality => 'Quality audit';

  @override
  String get collabVisitTypeSafety => 'Safety inspection';

  @override
  String get collabVisitTypeProgress => 'Progress review';

  @override
  String get collabProjectSite => 'Project site';

  @override
  String get evidenceMyTitle => 'My Field Evidence';

  @override
  String get evidenceTitle => 'Evidence';

  @override
  String get evidenceLoading => 'Loading field evidence';

  @override
  String get evidenceEmpty => 'No field evidence submitted yet.';

  @override
  String get evidenceNewTitle => 'New Field Update';

  @override
  String get evidenceCorrectedTitle => 'Corrected Evidence';

  @override
  String get evidenceDocumentWork => 'Document completed site work';

  @override
  String get evidenceVerifyHint =>
      'Your Engineer will verify this evidence. It does not change official task progress.';

  @override
  String get evidenceWhatWork => 'What work was completed?';

  @override
  String get evidenceHint => 'Short, practical site note…';

  @override
  String get evidenceTakePhoto => 'Take Photo';

  @override
  String get evidenceAddPhotos => 'Add Photos';

  @override
  String get evidenceCategoryOptional => 'Category (optional)';

  @override
  String get evidenceCategoryHint =>
      'Choose any tags that apply. Your Engineer can correct them.';

  @override
  String get evidenceViewOptional => 'View (optional)';

  @override
  String get viewFront => 'front';

  @override
  String get viewBack => 'back';

  @override
  String get viewLeft => 'left';

  @override
  String get viewRight => 'right';

  @override
  String get viewTop => 'top';

  @override
  String get viewDetail => 'detail';

  @override
  String get viewOther => 'other';

  @override
  String get evidenceRemovePhoto => 'Remove photo';

  @override
  String get evidenceSubmit => 'Submit Evidence';

  @override
  String get evidenceSent => 'Field evidence sent to your Engineer.';

  @override
  String evidencePhotoCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count photos',
      one: '$count photo',
    );
    return '$_temp0';
  }

  @override
  String get evidenceSubmitCorrected => 'Submit Corrected Evidence';

  @override
  String get evidencePhotoFallback => 'Field photo';

  @override
  String get ifcTitle => 'IFC Intelligence';

  @override
  String get ifcSelectProjectBody =>
      'Choose a project before opening IFC Intelligence.';

  @override
  String get ifcLoading => 'Loading IFC models';

  @override
  String get ifcModelsTitle => 'IFC models';

  @override
  String get ifcEmptyTitle => 'No IFC models';

  @override
  String get ifcEmptyBody =>
      'A project manager can create a model group and upload the first IFC version from the web workspace.';

  @override
  String get ifcReadOnlyHint =>
      'Read-only field view of approved model facts and processing status.';

  @override
  String get ifcFederatedModel => 'Federated model';

  @override
  String get ifcNoVersions => 'No versions uploaded';

  @override
  String ifcVersionLine(String number, String title) {
    return 'v$number · $title';
  }

  @override
  String ifcElementCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count elements',
      one: '$count element',
    );
    return '$_temp0';
  }

  @override
  String get ifcActive => 'Active';

  @override
  String get ifcUntitled => 'Untitled';

  @override
  String get contactAdminTitle => 'Contact Administrator';

  @override
  String get contactAdminUnavailable => 'Support details unavailable';

  @override
  String get contactAdminUnavailableBody =>
      'Please contact your project office or try again when connected.';

  @override
  String get contactAdminCompanySupport => 'Company support';

  @override
  String get contactAdminBody =>
      'Contact the administrator for account access and support.';

  @override
  String get contactAdminPhone => 'Support phone';

  @override
  String get contactAdminEmail => 'Support email';

  @override
  String get contactAdminOffice => 'Office';

  @override
  String get recordStop => 'Stop recording';

  @override
  String get recordResume => 'Resume recording';

  @override
  String get recordProcessing => 'Processing…';

  @override
  String get recordPlay => 'Play recording';

  @override
  String get recordPausePlayback => 'Pause playback';

  @override
  String get recordTryAgain => 'Try again';

  @override
  String get recordCapture => 'Capture a hands-free field update';

  @override
  String get recordReviewHint => 'You review every proposal before submission';

  @override
  String get diagnosticsDisabled =>
      'AI diagnostics are disabled in this build.';

  @override
  String get diagnosticsTitle => 'AI diagnostics (development)';

  @override
  String get diagnosticsBody =>
      'This screen checks configuration and permissions only. It never fakes a recording, upload, transcription, or AI result.';

  @override
  String get diagnosticsRerun => 'Run checks again';

  @override
  String get voiceTitle => 'Construction Voice Assistant';

  @override
  String get voiceSpeakNaturally =>
      'Speak naturally about work, issues, or project updates.';

  @override
  String get voiceTaskContext => 'Task context (recommended)';

  @override
  String get voiceLetAiSuggest => 'Let AI suggest an assigned task';

  @override
  String get voiceSubmitForAnalysis => 'Submit for AI analysis';

  @override
  String get voicePrivacyNote =>
      'Your recording is used to prepare this project action and is stored according to the project data policy.';

  @override
  String get voiceRetryAudio => 'Retry retained audio';

  @override
  String get voiceReportSent => 'Report sent';

  @override
  String get voiceActionCompleted => 'Action completed';

  @override
  String get voiceReportSentBody =>
      'Your report was sent to the responsible engineer for review.';

  @override
  String voiceActionsSucceeded(int succeeded, int total) {
    return '$succeeded of $total selected actions succeeded.';
  }

  @override
  String get voicePause => 'Pause';

  @override
  String get voiceDelete => 'Delete';

  @override
  String get voiceRecordAgain => 'Record again';

  @override
  String get voiceUploading => 'Uploading recording securely…';

  @override
  String get voiceTranscribing => 'Transcribing speech…';

  @override
  String get voiceLiveWaveform => 'Live recording waveform';

  @override
  String get voiceRecordedWaveform => 'Recorded audio waveform';

  @override
  String get voiceReviewUnderstood => 'Review what I understood';

  @override
  String get voiceChooseActions =>
      'Choose and edit the actions you want to confirm.';

  @override
  String get voiceAiSummary => 'AI SUMMARY';

  @override
  String get voiceSelectTask => 'Select a task';

  @override
  String get voiceWorkCompleted => 'WORK COMPLETED';

  @override
  String get voiceProblems => 'PROBLEMS / BLOCKERS';

  @override
  String get voiceSuggestedActions => 'SUGGESTED ACTIONS';

  @override
  String get voiceTranscript => 'TRANSCRIPT';

  @override
  String get voiceTask => 'TASK';

  @override
  String get voiceProgressLabel => 'PROGRESS';

  @override
  String voiceProgressMentioned(String percent) {
    return '$percent% mentioned — not yet official';
  }

  @override
  String get voiceIntentUpdateProgress => 'Update task progress';

  @override
  String get voiceIntentReportIssue => 'Report issue';

  @override
  String get voiceIntentSendMessage => 'Send message';

  @override
  String get voiceIntentSubmitReport => 'Submit site report';

  @override
  String get voiceIntentRequestClarification => 'Request clarification';

  @override
  String get voiceNoSafeAction => 'No safe executable action was suggested.';

  @override
  String voiceConfidence(int percent) {
    return '$percent% confidence';
  }

  @override
  String get voiceConfirmedProgress => 'Confirmed progress (0–100)';

  @override
  String get voiceReviewEditValue => 'Review/edit value';

  @override
  String get voiceReviewedAffected =>
      'I reviewed the affected task, recipients, and workflow impact.';

  @override
  String get voiceDiscard => 'Discard';

  @override
  String get voiceConfirmSelected => 'Confirm selected';

  @override
  String get voiceMicPermissionRequired => 'Microphone permission is required.';

  @override
  String get voiceRecordBeforeTranscribe => 'Record audio before transcribing.';

  @override
  String get voiceRecordBeforeAnalysis => 'Record audio before analysis.';

  @override
  String get voiceNoAnalysisRetry => 'No analysis to retry.';

  @override
  String get voiceNoAnalysisConfirm => 'No analysis to confirm.';

  @override
  String get voiceNoAnalysisClarify => 'No analysis to clarify.';

  @override
  String get voiceActionUnavailable => 'Voice action is no longer available.';

  @override
  String get navVoiceAssistant => 'Voice Assistant';

  @override
  String get shareActionsTitle => 'Actions';

  @override
  String get shareForward => 'Forward';

  @override
  String get shareForwardHint => 'Send this on to someone else.';

  @override
  String get shareAskOpinion => 'Ask for Opinion';

  @override
  String get shareAskOpinionHint =>
      'Ask a colleague to advise. Nothing is reassigned.';

  @override
  String get shareShare => 'Share';

  @override
  String get shareShareHint => 'Send a copy into a conversation.';

  @override
  String get shareRecipients => 'Recipients';

  @override
  String get shareNoteLabel => 'Note (optional)';

  @override
  String get shareSend => 'Send';

  @override
  String get shareSending => 'Sending';

  @override
  String get shareLoadingRecipients => 'Loading recipients';

  @override
  String get shareNoRecipientsTitle => 'No one to send to';

  @override
  String get shareNoRecipientsBody =>
      'There is nobody on this project you can send this to.';

  @override
  String get shareSelectRecipient => 'Select at least one recipient.';

  @override
  String get shareSentForward => 'Message forwarded.';

  @override
  String get shareSentOpinion => 'Opinion requested.';

  @override
  String get shareSentShare => 'Shared.';

  @override
  String shareSelectedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count selected',
      one: '$count selected',
      zero: 'No one selected',
    );
    return '$_temp0';
  }

  @override
  String get shareOpinionPrefill => 'Could you give me your opinion on this?';

  @override
  String get shareOpen => 'Open';

  @override
  String get dashboardTodayTitle => 'Today';

  @override
  String get dashboardTodayBody => 'What needs you on site right now.';

  @override
  String get dashboardAllClearTitle => 'Nothing needs you right now';

  @override
  String get dashboardAllClearBody =>
      'No overdue, blocked or waiting work on this project.';

  @override
  String get dashboardOpenProfile => 'Your profile';

  @override
  String get dashboardActivityUnavailable => 'Recent activity is unavailable.';

  @override
  String get voiceClarificationTitle => 'More information needed';

  @override
  String get voiceClarificationAnswerLabel => 'Answer';

  @override
  String get voiceClarificationAnswerHint => 'Write a short, specific answer';

  @override
  String get voiceContinue => 'Continue';

  @override
  String get voiceUnavailableTitle => 'Voice is not available';

  @override
  String get voiceUnavailableBody =>
      'The voice assistant is for project and field roles. Administration is done on the web application.';

  @override
  String get activityGeneric => 'Project activity';

  @override
  String get activityTaskCreated => 'Task created';

  @override
  String get activityTaskStarted => 'Task started';

  @override
  String get activityTaskResumed => 'Task resumed';

  @override
  String get activityProgressUpdated => 'Progress updated';

  @override
  String get activitySubmitted => 'Submitted for review';

  @override
  String get activityApproved => 'Approved';

  @override
  String get activityReviewStarted => 'Review started';

  @override
  String get activityReworkRequested => 'Rework requested';

  @override
  String get activityReworkStarted => 'Rework started';

  @override
  String get activityClarificationRequested => 'Clarification requested';

  @override
  String get activityClarificationResponded => 'Clarification answered';

  @override
  String get activityCommentAdded => 'Comment added';

  @override
  String get activityWorkUpdateAdded => 'Work update added';

  @override
  String get activityBlockerReported => 'Blocker reported';

  @override
  String get activityDocumentUploaded => 'Document uploaded';

  @override
  String get activityAttachmentUploaded => 'Attachment uploaded';

  @override
  String get activitySiteReportVerified => 'Site report verified';

  @override
  String get activitySiteVisitScheduled => 'Site visit scheduled';

  @override
  String get activityOwnerRequestSubmitted => 'Owner request submitted';

  @override
  String get activityScheduleRecalculated => 'Schedule recalculated';

  @override
  String get activityRemindersDispatched => 'Reminders sent';

  @override
  String get activityMemberAssigned => 'Team member assigned';

  @override
  String get activityModelVersionUploaded => 'Model version uploaded';

  @override
  String get activityVoiceUpdate => 'Voice update recorded';

  @override
  String get activityEvidenceVerified => 'Field evidence verified';

  @override
  String get activityEvidenceRejected => 'Field evidence returned';

  @override
  String get activityEvidenceSubmitted => 'Field evidence submitted';

  @override
  String get activityCreated => 'Created';

  @override
  String get activityUpdated => 'Updated';

  @override
  String get commonSeverity => 'Severity';

  @override
  String get commonCreated => 'Created';

  @override
  String get commonDue => 'Due';

  @override
  String get commonNoDescription => 'No description provided.';

  @override
  String get commonMoreActions => 'More actions';

  @override
  String get navDesignChanges => 'Design Changes';

  @override
  String get designChangesEmpty =>
      'No design changes have been raised on this project.';

  @override
  String get taskDependencyUnnamed => 'Blocking task';

  @override
  String get voiceOutcomeSuccessTitle => 'Actions completed';

  @override
  String get voiceOutcomePartialTitle => 'Some actions completed';

  @override
  String get voiceOutcomeFailureTitle => 'No action was carried out';

  @override
  String get voiceOutcomeNothingTitle => 'Nothing to carry out';

  @override
  String get voiceOutcomeNothingBody =>
      'The note was understood, but it did not require any change in the system.';

  @override
  String get voiceOutcomeReason => 'Reason';

  @override
  String get voiceOutcomeNotExecuted => 'Not carried out';

  @override
  String get voiceOutcomeExecuted => 'Done';

  @override
  String get voiceOutcomeRejectedFields =>
      'The system refused some of the details the assistant produced for this action.';

  @override
  String get voiceOutcomeGenericFailure =>
      'This action could not be carried out.';
}
