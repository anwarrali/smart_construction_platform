import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppL10n
/// returned by `AppL10n.of(context)`.
///
/// Applications need to include `AppL10n.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppL10n.localizationsDelegates,
///   supportedLocales: AppL10n.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppL10n.supportedLocales
/// property.
abstract class AppL10n {
  AppL10n(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppL10n of(BuildContext context) {
    return Localizations.of<AppL10n>(context, AppL10n)!;
  }

  static const LocalizationsDelegate<AppL10n> delegate = _AppL10nDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('ar'),
    Locale('en'),
  ];

  /// Generic loading label
  ///
  /// In en, this message translates to:
  /// **'Loading…'**
  String get commonLoading;

  /// Retry a failed action
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get commonRetry;

  /// Cancel button
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get commonCancel;

  /// Confirm button
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get commonConfirm;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit'**
  String get commonSubmit;

  /// Submit button while in flight
  ///
  /// In en, this message translates to:
  /// **'Submitting…'**
  String get commonSubmitting;

  /// Save a draft record
  ///
  /// In en, this message translates to:
  /// **'Save Draft'**
  String get commonSaveDraft;

  /// Create button
  ///
  /// In en, this message translates to:
  /// **'Create'**
  String get commonCreate;

  /// Delete button
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get commonDelete;

  /// Update button
  ///
  /// In en, this message translates to:
  /// **'Update'**
  String get commonUpdate;

  /// Approve button
  ///
  /// In en, this message translates to:
  /// **'Approve'**
  String get commonApprove;

  /// Dismiss a completed flow
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get commonDone;

  /// Filter chip showing everything
  ///
  /// In en, this message translates to:
  /// **'All'**
  String get commonAll;

  /// Suffix marking an optional field
  ///
  /// In en, this message translates to:
  /// **'(optional)'**
  String get commonOptional;

  /// Status field label
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get commonStatus;

  /// Priority field label
  ///
  /// In en, this message translates to:
  /// **'Priority'**
  String get commonPriority;

  /// Engineering discipline field label
  ///
  /// In en, this message translates to:
  /// **'Discipline'**
  String get commonDiscipline;

  /// Description field label
  ///
  /// In en, this message translates to:
  /// **'Description'**
  String get commonDescription;

  /// Title field label
  ///
  /// In en, this message translates to:
  /// **'Title'**
  String get commonTitle;

  /// Category field label
  ///
  /// In en, this message translates to:
  /// **'Category'**
  String get commonCategory;

  /// Single note field label
  ///
  /// In en, this message translates to:
  /// **'Note'**
  String get commonNote;

  /// Project field label
  ///
  /// In en, this message translates to:
  /// **'Project'**
  String get commonProject;

  /// Progress field label
  ///
  /// In en, this message translates to:
  /// **'Progress'**
  String get commonProgress;

  /// Notifications
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get commonNotifications;

  /// Date group header
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get commonToday;

  /// Date group header
  ///
  /// In en, this message translates to:
  /// **'Yesterday'**
  String get commonYesterday;

  /// Open the full list
  ///
  /// In en, this message translates to:
  /// **'View all'**
  String get commonViewAll;

  /// Sign out button
  ///
  /// In en, this message translates to:
  /// **'Sign out'**
  String get commonSignOut;

  /// Log out button
  ///
  /// In en, this message translates to:
  /// **'Log out'**
  String get commonLogOut;

  /// Empty state title when no project is active
  ///
  /// In en, this message translates to:
  /// **'Select a project'**
  String get commonSelectProject;

  /// Body shown when a screen needs an active project
  ///
  /// In en, this message translates to:
  /// **'Select a project first.'**
  String get commonSelectProjectFirst;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No project selected'**
  String get commonNoProjectSelected;

  /// Generic empty state title
  ///
  /// In en, this message translates to:
  /// **'Nothing here yet'**
  String get commonNothingHereYet;

  /// Error title; subject is a screen name
  ///
  /// In en, this message translates to:
  /// **'{subject} unavailable'**
  String commonUnavailable(String subject);

  /// A percentage value
  ///
  /// In en, this message translates to:
  /// **'{value}%'**
  String commonPercent(String value);

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Home'**
  String get navHome;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get navTasks;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'My Tasks'**
  String get navMyTasks;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Reports'**
  String get navReports;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Messages'**
  String get navMessages;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get navProfile;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Reviews'**
  String get navReviews;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Documents'**
  String get navDocuments;

  /// Bottom navigation destination. The Arabic is deliberately shorter than the web sidebar's "الملاحظات والمشكلات": a five-destination bar on a phone cannot fit the full term, which wrapped and clipped on device. The screen title keeps the full wording.
  ///
  /// In en, this message translates to:
  /// **'Issues'**
  String get navIssues;

  /// Bottom navigation destination
  ///
  /// In en, this message translates to:
  /// **'Projects'**
  String get navProjects;

  /// Bottom navigation destination for field evidence
  ///
  /// In en, this message translates to:
  /// **'Evidence'**
  String get navEvidence;

  /// Quick-access destination
  ///
  /// In en, this message translates to:
  /// **'My Actions'**
  String get navMyActions;

  /// Quick-access destination; IFC is a format name and stays Latin
  ///
  /// In en, this message translates to:
  /// **'IFC Models'**
  String get navIfcModels;

  /// Quick-access destination
  ///
  /// In en, this message translates to:
  /// **'Field Evidence'**
  String get navFieldEvidence;

  /// Floating action to record a spoken field update
  ///
  /// In en, this message translates to:
  /// **'Record Update'**
  String get navRecordUpdate;

  /// Accessibility label for the record action
  ///
  /// In en, this message translates to:
  /// **'Record field update'**
  String get navRecordFieldUpdate;

  /// Fallback error
  ///
  /// In en, this message translates to:
  /// **'Something went wrong. Please try again.'**
  String get errorGeneric;

  /// Request timed out
  ///
  /// In en, this message translates to:
  /// **'The server took too long to respond. Please retry.'**
  String get errorTimeout;

  /// Connection failure
  ///
  /// In en, this message translates to:
  /// **'Cannot reach the project server. Check that the server is running and that this device is on the correct network.'**
  String get errorNetwork;

  /// HTTP 401
  ///
  /// In en, this message translates to:
  /// **'You are not signed in.'**
  String get errorUnauthorized;

  /// HTTP 403
  ///
  /// In en, this message translates to:
  /// **'You do not have permission to do this.'**
  String get errorForbidden;

  /// HTTP 404
  ///
  /// In en, this message translates to:
  /// **'That record could not be found.'**
  String get errorNotFound;

  /// HTTP 409
  ///
  /// In en, this message translates to:
  /// **'This conflicts with an existing record.'**
  String get errorConflict;

  /// HTTP 422
  ///
  /// In en, this message translates to:
  /// **'Please correct the highlighted fields.'**
  String get errorValidation;

  /// A read failed
  ///
  /// In en, this message translates to:
  /// **'This information could not be loaded.'**
  String get errorLoadFailed;

  /// A write failed
  ///
  /// In en, this message translates to:
  /// **'Your changes could not be saved.'**
  String get errorSaveFailed;

  /// An action failed
  ///
  /// In en, this message translates to:
  /// **'The action could not be completed.'**
  String get errorActionFailed;

  /// Empty required field
  ///
  /// In en, this message translates to:
  /// **'This field is required.'**
  String get validationRequired;

  /// Login validation
  ///
  /// In en, this message translates to:
  /// **'Enter your email or username.'**
  String get validationEnterEmailOrUsername;

  /// Login validation
  ///
  /// In en, this message translates to:
  /// **'Enter your password.'**
  String get validationEnterPassword;

  /// Issue form validation
  ///
  /// In en, this message translates to:
  /// **'Enter an issue title.'**
  String get validationEnterIssueTitle;

  /// Issue form validation
  ///
  /// In en, this message translates to:
  /// **'Describe the issue.'**
  String get validationDescribeIssue;

  /// Site report validation
  ///
  /// In en, this message translates to:
  /// **'Add the report summary.'**
  String get validationAddReportSummary;

  /// Review form validation
  ///
  /// In en, this message translates to:
  /// **'Complete all required fields.'**
  String get validationCompleteRequiredFields;

  /// Review form validation
  ///
  /// In en, this message translates to:
  /// **'Enter a clarification question.'**
  String get validationEnterClarificationQuestion;

  /// Brand descriptor under the logo
  ///
  /// In en, this message translates to:
  /// **'Smart Construction Management'**
  String get brandDescriptor;

  /// Sign-in heading
  ///
  /// In en, this message translates to:
  /// **'Sign in'**
  String get loginSignIn;

  /// Sign-in subtitle
  ///
  /// In en, this message translates to:
  /// **'Use your organization account to continue.'**
  String get loginSubtitle;

  /// Login field label
  ///
  /// In en, this message translates to:
  /// **'Email or username'**
  String get loginEmailLabel;

  /// Login field hint; an email example is not translated
  ///
  /// In en, this message translates to:
  /// **'name@company.com'**
  String get loginEmailHint;

  /// Login field label
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get loginPasswordLabel;

  /// Login field hint
  ///
  /// In en, this message translates to:
  /// **'Enter your password'**
  String get loginPasswordHint;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Show password'**
  String get loginShowPassword;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Hide password'**
  String get loginHidePassword;

  /// Login submit button
  ///
  /// In en, this message translates to:
  /// **'Sign in securely'**
  String get loginSubmit;

  /// Link to the support screen
  ///
  /// In en, this message translates to:
  /// **'Need help? Contact Administrator'**
  String get loginNeedHelp;

  /// Footer note on the sign-in screen
  ///
  /// In en, this message translates to:
  /// **'Secure access · Authorized project members only'**
  String get loginSecureAccess;

  /// Sign-in failed with 401
  ///
  /// In en, this message translates to:
  /// **'Incorrect email/username or password.'**
  String get loginInvalidCredentials;

  /// Sign-in refused with 403
  ///
  /// In en, this message translates to:
  /// **'Your account has been deactivated. Contact your administrator.'**
  String get loginAccountDeactivated;

  /// Sign-in throttled with 429
  ///
  /// In en, this message translates to:
  /// **'Too many failed sign-in attempts. Try again later.'**
  String get loginTooManyAttempts;

  /// Sign-in aside heading
  ///
  /// In en, this message translates to:
  /// **'Welcome Back'**
  String get loginWelcomeBack;

  /// Sign-in aside body
  ///
  /// In en, this message translates to:
  /// **'Manage projects, field activities, and team collaboration from anywhere.'**
  String get loginWelcomeBody;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading assigned projects'**
  String get projectsLoading;

  /// Projects screen title used in error states
  ///
  /// In en, this message translates to:
  /// **'Projects'**
  String get projectsTitle;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No projects assigned'**
  String get projectsNoneAssigned;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Contact your administrator or project manager for access, or switch to another account.'**
  String get projectsNoneAssignedBody;

  /// Action that signs the user out
  ///
  /// In en, this message translates to:
  /// **'Switch account'**
  String get projectsSwitchAccount;

  /// Confirmation dialog title
  ///
  /// In en, this message translates to:
  /// **'Switch account?'**
  String get projectsSwitchAccountQuestion;

  /// Confirmation dialog body
  ///
  /// In en, this message translates to:
  /// **'You will be signed out and returned to the sign-in screen.'**
  String get projectsSwitchAccountBody;

  /// Projects screen heading
  ///
  /// In en, this message translates to:
  /// **'My Projects'**
  String get projectsMyProjects;

  /// Projects screen subheading
  ///
  /// In en, this message translates to:
  /// **'Select a workspace to continue'**
  String get projectsSelectWorkspace;

  /// Progress row label on a project card
  ///
  /// In en, this message translates to:
  /// **'Project progress'**
  String get projectsProgress;

  /// Open issue count on a project card. Pluralised: English reads wrong at 1, and Arabic needs dual and few forms.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} open issue} other{{count} open issues}}'**
  String projectsOpenIssues(int count);

  /// Marker on the active project card
  ///
  /// In en, this message translates to:
  /// **'Current project'**
  String get projectsCurrentProject;

  /// Action on a non-active project card
  ///
  /// In en, this message translates to:
  /// **'Open workspace'**
  String get projectsOpenWorkspace;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'Backlog'**
  String get statusBacklog;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'To do'**
  String get statusTodo;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'In progress'**
  String get statusInProgress;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'Under review'**
  String get statusUnderReview;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'Rework required'**
  String get statusReworkRequired;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get statusDone;

  /// Task status
  ///
  /// In en, this message translates to:
  /// **'Blocked'**
  String get statusBlocked;

  /// Task or project status
  ///
  /// In en, this message translates to:
  /// **'Cancelled'**
  String get statusCancelled;

  /// Issue status
  ///
  /// In en, this message translates to:
  /// **'Open'**
  String get statusOpen;

  /// Issue status
  ///
  /// In en, this message translates to:
  /// **'Resolved'**
  String get statusResolved;

  /// Issue status
  ///
  /// In en, this message translates to:
  /// **'Closed'**
  String get statusClosed;

  /// Review status
  ///
  /// In en, this message translates to:
  /// **'Pending'**
  String get statusPending;

  /// Review status
  ///
  /// In en, this message translates to:
  /// **'In review'**
  String get statusInReview;

  /// Review status
  ///
  /// In en, this message translates to:
  /// **'Approved'**
  String get statusApproved;

  /// Review status
  ///
  /// In en, this message translates to:
  /// **'Rejected'**
  String get statusRejected;

  /// Review status
  ///
  /// In en, this message translates to:
  /// **'Clarification requested'**
  String get statusClarificationRequested;

  /// Review or report status
  ///
  /// In en, this message translates to:
  /// **'Draft'**
  String get statusDraft;

  /// Review or report status
  ///
  /// In en, this message translates to:
  /// **'Submitted'**
  String get statusSubmitted;

  /// Design change status
  ///
  /// In en, this message translates to:
  /// **'Proposed'**
  String get statusProposed;

  /// Design change status
  ///
  /// In en, this message translates to:
  /// **'Implemented'**
  String get statusImplemented;

  /// Project status
  ///
  /// In en, this message translates to:
  /// **'Planning'**
  String get statusPlanning;

  /// Project status
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get statusActive;

  /// Project status
  ///
  /// In en, this message translates to:
  /// **'On hold'**
  String get statusOnHold;

  /// Project status or health
  ///
  /// In en, this message translates to:
  /// **'Delayed'**
  String get statusDelayed;

  /// Project status
  ///
  /// In en, this message translates to:
  /// **'Completed'**
  String get statusCompleted;

  /// Site report review status
  ///
  /// In en, this message translates to:
  /// **'Verified'**
  String get statusVerified;

  /// Project health
  ///
  /// In en, this message translates to:
  /// **'On track'**
  String get statusOnTrack;

  /// Project health
  ///
  /// In en, this message translates to:
  /// **'At risk'**
  String get statusAtRisk;

  /// Priority level
  ///
  /// In en, this message translates to:
  /// **'Low'**
  String get priorityLow;

  /// Priority level
  ///
  /// In en, this message translates to:
  /// **'Medium'**
  String get priorityMedium;

  /// Priority level
  ///
  /// In en, this message translates to:
  /// **'High'**
  String get priorityHigh;

  /// Priority level
  ///
  /// In en, this message translates to:
  /// **'Critical'**
  String get priorityCritical;

  /// Notification priority
  ///
  /// In en, this message translates to:
  /// **'Normal'**
  String get priorityNormal;

  /// Notification priority badge
  ///
  /// In en, this message translates to:
  /// **'Important'**
  String get priorityImportant;

  /// Notification priority
  ///
  /// In en, this message translates to:
  /// **'Info'**
  String get priorityInfo;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Civil'**
  String get disciplineCivil;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Architectural'**
  String get disciplineArchitectural;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Electrical'**
  String get disciplineElectrical;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Mechanical'**
  String get disciplineMechanical;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Structural'**
  String get disciplineStructural;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Plumbing'**
  String get disciplinePlumbing;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'HVAC'**
  String get disciplineHvac;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Fire protection'**
  String get disciplineFireProtection;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'General'**
  String get disciplineGeneral;

  /// Engineering discipline
  ///
  /// In en, this message translates to:
  /// **'Unclassified'**
  String get disciplineUnclassified;

  /// No discipline or assignee set
  ///
  /// In en, this message translates to:
  /// **'Unassigned'**
  String get disciplineUnassigned;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Administrator'**
  String get roleAdmin;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Owner'**
  String get roleOwner;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Project manager'**
  String get roleProjectManager;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Engineer'**
  String get roleEngineer;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Consultant'**
  String get roleConsultant;

  /// User role
  ///
  /// In en, this message translates to:
  /// **'Worker'**
  String get roleWorker;

  /// Role caption under the greeting
  ///
  /// In en, this message translates to:
  /// **'Main Contractor · Site Engineer'**
  String get roleCaptionSiteEngineer;

  /// Role caption under the greeting
  ///
  /// In en, this message translates to:
  /// **'Consultant Engineer · Review & Quality'**
  String get roleCaptionConsultant;

  /// Role caption under the greeting
  ///
  /// In en, this message translates to:
  /// **'Project Owner · Executive View'**
  String get roleCaptionOwner;

  /// Role caption under the greeting
  ///
  /// In en, this message translates to:
  /// **'Construction Worker · Field Evidence'**
  String get roleCaptionWorker;

  /// Role caption under the greeting
  ///
  /// In en, this message translates to:
  /// **'Project Manager · Field Monitoring'**
  String get roleCaptionProjectManager;

  /// Role caption on the profile screen
  ///
  /// In en, this message translates to:
  /// **'Consultant Engineer'**
  String get roleCaptionConsultantShort;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Choose a project to see its dashboard.'**
  String get dashboardSelectProjectBody;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading project dashboard'**
  String get dashboardLoading;

  /// Dashboard name used in error states
  ///
  /// In en, this message translates to:
  /// **'Dashboard'**
  String get dashboardTitle;

  /// Time-of-day greeting
  ///
  /// In en, this message translates to:
  /// **'Good morning'**
  String get dashboardGreetingMorning;

  /// Time-of-day greeting
  ///
  /// In en, this message translates to:
  /// **'Good afternoon'**
  String get dashboardGreetingAfternoon;

  /// Time-of-day greeting
  ///
  /// In en, this message translates to:
  /// **'Good evening'**
  String get dashboardGreetingEvening;

  /// Greeting line; name is the user's own name and is never translated
  ///
  /// In en, this message translates to:
  /// **'{greeting}, {name}'**
  String dashboardGreeting(String greeting, String name);

  /// Accessibility label for the project switcher
  ///
  /// In en, this message translates to:
  /// **'Change project'**
  String get dashboardChangeProject;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Fast field update'**
  String get dashboardFastFieldUpdate;

  /// Section subheading
  ///
  /// In en, this message translates to:
  /// **'Capture work without stopping your workflow'**
  String get dashboardFastFieldUpdateBody;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Executive intelligence'**
  String get dashboardExecutiveIntelligence;

  /// Section subheading
  ///
  /// In en, this message translates to:
  /// **'Current status and future smart insights'**
  String get dashboardExecutiveIntelligenceBody;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Needs your attention'**
  String get dashboardNeedsAttention;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Project snapshot'**
  String get dashboardProjectSnapshot;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Quick access'**
  String get dashboardQuickAccess;

  /// Section subheading
  ///
  /// In en, this message translates to:
  /// **'Role-appropriate project tools'**
  String get dashboardQuickAccessBody;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Recent activity'**
  String get dashboardRecentActivity;

  /// Section subheading
  ///
  /// In en, this message translates to:
  /// **'Latest information from this project'**
  String get dashboardRecentActivityBody;

  /// Snapshot subtitle for engineers
  ///
  /// In en, this message translates to:
  /// **'Tasks, blockers, and reviews that need action'**
  String get dashboardSnapshotEngineer;

  /// Snapshot subtitle for consultants
  ///
  /// In en, this message translates to:
  /// **'Review workload and submitted work'**
  String get dashboardSnapshotConsultant;

  /// Snapshot subtitle for owners
  ///
  /// In en, this message translates to:
  /// **'High-level progress, risk, and decisions'**
  String get dashboardSnapshotOwner;

  /// Snapshot subtitle for managers
  ///
  /// In en, this message translates to:
  /// **'Execution health and team priorities'**
  String get dashboardSnapshotManager;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Pending reviews'**
  String get dashboardPendingReviews;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Overdue reviews'**
  String get dashboardOverdueReviews;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Approved work'**
  String get dashboardApprovedWork;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Awaiting rework'**
  String get dashboardAwaitingRework;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Delayed tasks'**
  String get dashboardDelayedTasks;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Open risks'**
  String get dashboardOpenRisks;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Decisions'**
  String get dashboardDecisions;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Milestones'**
  String get dashboardMilestones;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Assigned tasks'**
  String get dashboardAssignedTasks;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Submitted'**
  String get dashboardSubmitted;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Verified'**
  String get dashboardVerified;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Needs correction'**
  String get dashboardNeedsCorrection;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Today’s tasks'**
  String get dashboardTodaysTasks;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get dashboardOverdue;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Blocked'**
  String get dashboardBlocked;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Waiting review'**
  String get dashboardWaitingReview;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Rework required'**
  String get dashboardReworkRequired;

  /// KPI label
  ///
  /// In en, this message translates to:
  /// **'Open issues'**
  String get dashboardOpenIssues;

  /// Progress ring caption
  ///
  /// In en, this message translates to:
  /// **'Overall progress'**
  String get dashboardOverallProgress;

  /// Progress ring footnote
  ///
  /// In en, this message translates to:
  /// **'Live project data'**
  String get dashboardLiveProjectData;

  /// Screen-reader summary of the progress ring
  ///
  /// In en, this message translates to:
  /// **'Overall progress is {progress}%. Project health is {health}.'**
  String dashboardProgressSemantics(String progress, String health);

  /// Executive summary sentence built from the project's own metrics
  ///
  /// In en, this message translates to:
  /// **'Overall progress is {progress}%. Project health is {health}. There are {delayed} delayed tasks and {risks} open risks requiring visibility.'**
  String dashboardExecutiveSummary(
    String progress,
    String health,
    int delayed,
    int risks,
  );

  /// Executive summary card title
  ///
  /// In en, this message translates to:
  /// **'Smart Project Summary'**
  String get dashboardSummaryTitle;

  /// Executive summary card subtitle
  ///
  /// In en, this message translates to:
  /// **'Executive project intelligence'**
  String get dashboardSummarySubtitle;

  /// Badge on the summary card
  ///
  /// In en, this message translates to:
  /// **'LIVE DATA'**
  String get dashboardLiveData;

  /// Badge on the summary card
  ///
  /// In en, this message translates to:
  /// **'AI READY'**
  String get dashboardAiReady;

  /// Placeholder text on the summary card
  ///
  /// In en, this message translates to:
  /// **'AI-generated insights will appear here when the summary service is connected. Current project metrics remain available below.'**
  String get dashboardAiPlaceholder;

  /// Footnote on the summary card
  ///
  /// In en, this message translates to:
  /// **'Generated from current backend metrics · No external AI'**
  String get dashboardGeneratedFrom;

  /// Footnote on the summary card
  ///
  /// In en, this message translates to:
  /// **'Future integration placeholder · No fabricated insights'**
  String get dashboardFutureIntegration;

  /// Activity feed empty state
  ///
  /// In en, this message translates to:
  /// **'New project activity will appear here as your team works.'**
  String get dashboardNoActivity;

  /// Fallback title for an activity entry
  ///
  /// In en, this message translates to:
  /// **'Project activity'**
  String get dashboardProjectActivity;

  /// Tasks screen title for assignees
  ///
  /// In en, this message translates to:
  /// **'My Tasks'**
  String get tasksMyTasks;

  /// Tasks screen title for managers
  ///
  /// In en, this message translates to:
  /// **'Project Tasks'**
  String get tasksProjectTasks;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading tasks'**
  String get tasksLoading;

  /// Tasks screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Tasks'**
  String get tasksTitle;

  /// Task counter label
  ///
  /// In en, this message translates to:
  /// **'Total'**
  String get tasksTotal;

  /// Task counter label
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get tasksOverdue;

  /// Task counter label
  ///
  /// In en, this message translates to:
  /// **'Blocked'**
  String get tasksBlocked;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No matching tasks'**
  String get tasksNoMatching;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'There are no assigned tasks in this view.'**
  String get tasksNoAssigned;

  /// Short filter chip for rework_required
  ///
  /// In en, this message translates to:
  /// **'Rework'**
  String get tasksFilterRework;

  /// Task detail screen title
  ///
  /// In en, this message translates to:
  /// **'Task Details'**
  String get taskDetailTitle;

  /// Task screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Task'**
  String get taskTitle;

  /// Progress caption on a task
  ///
  /// In en, this message translates to:
  /// **'{percent}% complete'**
  String taskPercentComplete(String percent);

  /// Blocked-by-dependency notice
  ///
  /// In en, this message translates to:
  /// **'Cannot start yet'**
  String get taskCannotStartYet;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Quick actions'**
  String get taskQuickActions;

  /// Action opening the task conversation
  ///
  /// In en, this message translates to:
  /// **'Task Discussion'**
  String get taskDiscussion;

  /// Action opening the voice screen
  ///
  /// In en, this message translates to:
  /// **'AI Voice Field Update'**
  String get taskVoiceUpdate;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Start Task'**
  String get taskStart;

  /// Action and dialog title
  ///
  /// In en, this message translates to:
  /// **'Update Progress'**
  String get taskUpdateProgress;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Add Comment'**
  String get taskAddComment;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Submit for Review'**
  String get taskSubmitForReview;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Create Field Update'**
  String get taskCreateFieldUpdate;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'My Evidence History'**
  String get taskEvidenceHistory;

  /// Permission notice
  ///
  /// In en, this message translates to:
  /// **'You do not have permission to update this task.'**
  String get taskNoPermission;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Task updated.'**
  String get taskUpdated;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Work note (optional)'**
  String get taskWorkNote;

  /// Badge on a task card
  ///
  /// In en, this message translates to:
  /// **'Dependency blocked'**
  String get taskDependencyBlocked;

  /// Due-date chip
  ///
  /// In en, this message translates to:
  /// **'Due {date}'**
  String taskDueOn(String date);

  /// Overdue chip
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} day overdue} other{{count} days overdue}}'**
  String taskDaysOverdue(int count);

  /// One blocking dependency
  ///
  /// In en, this message translates to:
  /// **'· {name} ({status})'**
  String taskDependencyLine(String name, String status);

  /// Fallback name for a dependency
  ///
  /// In en, this message translates to:
  /// **'Blocking task'**
  String get taskBlockingTask;

  /// Issues screen title
  ///
  /// In en, this message translates to:
  /// **'Issues & Blockers'**
  String get issuesTitle;

  /// Issues empty state
  ///
  /// In en, this message translates to:
  /// **'No issues have been reported.'**
  String get issuesEmpty;

  /// Create-issue screen title
  ///
  /// In en, this message translates to:
  /// **'Report Issue'**
  String get issueReport;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Issue title'**
  String get issueTitleLabel;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Severity'**
  String get issueSeverity;

  /// Switch label
  ///
  /// In en, this message translates to:
  /// **'Affects project schedule'**
  String get issueAffectsSchedule;

  /// Switch subtitle
  ///
  /// In en, this message translates to:
  /// **'Flag this issue for schedule attention.'**
  String get issueAffectsScheduleBody;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit Issue'**
  String get issueSubmit;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Issue reported successfully.'**
  String get issueReported;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Material unavailable'**
  String get issueCategoryMaterialUnavailable;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Previous task incomplete'**
  String get issueCategoryPreviousTaskIncomplete;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Drawing unavailable'**
  String get issueCategoryDrawingUnavailable;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Equipment unavailable'**
  String get issueCategoryEquipmentUnavailable;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Labor shortage'**
  String get issueCategoryLaborShortage;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Site access issue'**
  String get issueCategorySiteAccess;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Consultant clarification required'**
  String get issueCategoryConsultantClarification;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Technical conflict'**
  String get issueCategoryTechnicalConflict;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Safety restriction'**
  String get issueCategorySafetyRestriction;

  /// Issue category
  ///
  /// In en, this message translates to:
  /// **'Other'**
  String get issueCategoryOther;

  /// Site reports screen title
  ///
  /// In en, this message translates to:
  /// **'Site Reports'**
  String get siteReportsTitle;

  /// Empty state
  ///
  /// In en, this message translates to:
  /// **'No site reports have been submitted.'**
  String get siteReportsEmpty;

  /// Create screen title
  ///
  /// In en, this message translates to:
  /// **'Create Site Report'**
  String get siteReportCreate;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Report date'**
  String get siteReportDate;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Work summary'**
  String get siteReportWorkSummary;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Work completed'**
  String get siteReportWorkCompleted;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Weather conditions'**
  String get siteReportWeather;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Workers count'**
  String get siteReportWorkersCount;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Equipment used'**
  String get siteReportEquipment;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Delays or constraints'**
  String get siteReportDelays;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit Report'**
  String get siteReportSubmit;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Report draft saved.'**
  String get siteReportDraftSaved;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Site report submitted.'**
  String get siteReportSubmitted;

  /// Documents screen title
  ///
  /// In en, this message translates to:
  /// **'Documents'**
  String get documentsTitle;

  /// Empty state
  ///
  /// In en, this message translates to:
  /// **'No documents are available.'**
  String get documentsEmpty;

  /// Messages screen title
  ///
  /// In en, this message translates to:
  /// **'Messages'**
  String get messagesTitle;

  /// Messages title with the active project name, which is never translated
  ///
  /// In en, this message translates to:
  /// **'Messages · {project}'**
  String messagesTitleWithProject(String project);

  /// Compose action
  ///
  /// In en, this message translates to:
  /// **'New'**
  String get messagesNew;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading conversations'**
  String get messagesLoading;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No conversations yet'**
  String get messagesEmptyTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Messages you send or receive on this project will appear here.'**
  String get messagesEmptyBody;

  /// Conversation row with no last message
  ///
  /// In en, this message translates to:
  /// **'No messages'**
  String get messagesNoMessages;

  /// Compose sheet title
  ///
  /// In en, this message translates to:
  /// **'New Project Conversation'**
  String get messagesNewConversation;

  /// Compose sheet subtitle
  ///
  /// In en, this message translates to:
  /// **'Project/team announcement'**
  String get messagesAnnouncement;

  /// Recipient mode
  ///
  /// In en, this message translates to:
  /// **'People'**
  String get messagesPeople;

  /// Recipient mode
  ///
  /// In en, this message translates to:
  /// **'Team / Group'**
  String get messagesTeamGroup;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Recipient group'**
  String get messagesRecipientGroup;

  /// Recipient group option; label comes from the server
  ///
  /// In en, this message translates to:
  /// **'{label} ({count})'**
  String messagesGroupWithCount(String label, int count);

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Title (optional)'**
  String get messagesTitleOptional;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Message'**
  String get messagesMessage;

  /// Send button
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get messagesSend;

  /// Fallback conversation name
  ///
  /// In en, this message translates to:
  /// **'Project discussion'**
  String get messagesProjectDiscussion;

  /// Conversation screen title
  ///
  /// In en, this message translates to:
  /// **'Project Conversation'**
  String get conversationTitle;

  /// Conversation title for an entity thread
  ///
  /// In en, this message translates to:
  /// **'{context} Discussion'**
  String conversationContextTitle(String context);

  /// Composer hint
  ///
  /// In en, this message translates to:
  /// **'Write a project message…'**
  String get conversationWriteMessage;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading conversation'**
  String get conversationLoading;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Conversation'**
  String get conversationTitleShort;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'Start the discussion'**
  String get conversationStartTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Send the first contextual project message.'**
  String get conversationStartBody;

  /// Header of a quoted forwarded message; the sender's name is never translated
  ///
  /// In en, this message translates to:
  /// **'Forwarded from {sender}'**
  String communicationForwardedFrom(String sender);

  /// Shared entity type
  ///
  /// In en, this message translates to:
  /// **'Issue'**
  String get entityIssue;

  /// Shared entity type
  ///
  /// In en, this message translates to:
  /// **'Task'**
  String get entityTask;

  /// Shared entity type
  ///
  /// In en, this message translates to:
  /// **'Site report'**
  String get entitySiteReport;

  /// Shared entity type
  ///
  /// In en, this message translates to:
  /// **'Design change'**
  String get entityDesignChange;

  /// Shared entity type
  ///
  /// In en, this message translates to:
  /// **'Document'**
  String get entityDocument;

  /// Notifications screen title
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get notificationsTitle;

  /// Unread counter in the app bar
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} unread} other{{count} unread}}'**
  String notificationsUnreadCount(int count);

  /// Mark every notification read
  ///
  /// In en, this message translates to:
  /// **'Read all'**
  String get notificationsReadAll;

  /// Filter chip
  ///
  /// In en, this message translates to:
  /// **'Unread'**
  String get notificationsFilterUnread;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading notifications'**
  String get notificationsLoading;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No unread notifications'**
  String get notificationsEmptyUnreadTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'New unread notifications will appear here.'**
  String get notificationsEmptyUnreadBody;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'You are all caught up'**
  String get notificationsEmptyTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Project updates and team activity will appear here.'**
  String get notificationsEmptyBody;

  /// Badge marking a chase notification
  ///
  /// In en, this message translates to:
  /// **'Reminder'**
  String get notificationReminder;

  /// Title for a notification the server sent without one
  ///
  /// In en, this message translates to:
  /// **'Notification'**
  String get notificationFallbackTitle;

  /// Detail screen title
  ///
  /// In en, this message translates to:
  /// **'Notification Details'**
  String get notificationDetailTitle;

  /// Detail screen empty state
  ///
  /// In en, this message translates to:
  /// **'This notification must be opened from the notification list.'**
  String get notificationDetailMustOpen;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Task'**
  String get notificationOpenTask;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Messages'**
  String get notificationOpenMessages;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Issues'**
  String get notificationOpenIssues;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Reviews'**
  String get notificationOpenReviews;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Reports'**
  String get notificationOpenReports;

  /// Deep-link action
  ///
  /// In en, this message translates to:
  /// **'Open Project'**
  String get notificationOpenProject;

  /// messageKey taskDeadline.DUE_TOMORROW
  ///
  /// In en, this message translates to:
  /// **'Task due tomorrow'**
  String get notifTaskDueTomorrowTitle;

  /// messageKey taskDeadline.DUE_TOMORROW; name is the task title
  ///
  /// In en, this message translates to:
  /// **'{name} is due tomorrow.'**
  String notifTaskDueTomorrowBody(String name);

  /// messageKey taskDeadline.DUE_TODAY
  ///
  /// In en, this message translates to:
  /// **'Task due today'**
  String get notifTaskDueTodayTitle;

  /// messageKey taskDeadline.DUE_TODAY
  ///
  /// In en, this message translates to:
  /// **'{name} is due today.'**
  String notifTaskDueTodayBody(String name);

  /// messageKey taskDeadline.OVERDUE
  ///
  /// In en, this message translates to:
  /// **'Task overdue'**
  String get notifTaskOverdueTitle;

  /// messageKey taskDeadline.OVERDUE
  ///
  /// In en, this message translates to:
  /// **'{name} is overdue.'**
  String notifTaskOverdueBody(String name);

  /// messageKey taskDeadline.OVERDUE_SEVERAL
  ///
  /// In en, this message translates to:
  /// **'{name} has been overdue for several days.'**
  String notifTaskOverdueSeveralBody(String name);

  /// messageKey taskDeadline.OVERDUE_WEEK
  ///
  /// In en, this message translates to:
  /// **'{name} has been overdue for more than a week.'**
  String notifTaskOverdueWeekBody(String name);

  /// messageKey siteReport.awaitingVerification
  ///
  /// In en, this message translates to:
  /// **'Site report awaiting your verification'**
  String get notifSiteReportAwaitingTitle;

  /// messageKey siteReport.awaitingVerification
  ///
  /// In en, this message translates to:
  /// **'A site report was submitted for {project}.'**
  String notifSiteReportAwaitingBody(String project);

  /// messageKey siteReport.verified
  ///
  /// In en, this message translates to:
  /// **'Site report verified'**
  String get notifSiteReportVerifiedTitle;

  /// messageKey siteReport.verified
  ///
  /// In en, this message translates to:
  /// **'Your site report for {date} was verified by {reviewer}.'**
  String notifSiteReportVerifiedBody(String date, String reviewer);

  /// messageKey siteReport.rejected
  ///
  /// In en, this message translates to:
  /// **'Site report rejected'**
  String get notifSiteReportRejectedTitle;

  /// messageKey siteReport.rejected; the reason is written by the reviewer and is not translated
  ///
  /// In en, this message translates to:
  /// **'Your site report for {date} was rejected by {reviewer}: {reason}'**
  String notifSiteReportRejectedBody(
    String date,
    String reviewer,
    String reason,
  );

  /// messageKey reminder.waiting
  ///
  /// In en, this message translates to:
  /// **'Response reminder: {label}'**
  String notifReminderWaitingTitle(String label);

  /// messageKey reminder.waiting
  ///
  /// In en, this message translates to:
  /// **'This {target} is still waiting for action. Reminder {sequence}.'**
  String notifReminderWaitingBody(String target, String sequence);

  /// messageKey reminder.escalation
  ///
  /// In en, this message translates to:
  /// **'Escalation: {label}'**
  String notifReminderEscalationTitle(String label);

  /// messageKey reminder.escalation
  ///
  /// In en, this message translates to:
  /// **'This {target} has been waiting too long and has been escalated.'**
  String notifReminderEscalationBody(String target);

  /// messageKey stepUp.codeRequested
  ///
  /// In en, this message translates to:
  /// **'Verification code requested'**
  String get notifStepUpRequestedTitle;

  /// messageKey stepUp.codeRequested
  ///
  /// In en, this message translates to:
  /// **'A verification code was requested to confirm: {action}. If this was not you, change your password immediately.'**
  String notifStepUpRequestedBody(String action);

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Account information'**
  String get profileAccountInformation;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Email'**
  String get profileEmail;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Phone'**
  String get profilePhone;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Organization'**
  String get profileOrganization;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Account status'**
  String get profileAccountStatus;

  /// Section heading for the language chooser
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get profileLanguage;

  /// Section subtitle for the language chooser
  ///
  /// In en, this message translates to:
  /// **'Choose the app language, or follow your device.'**
  String get profileLanguageBody;

  /// Follow the device locale
  ///
  /// In en, this message translates to:
  /// **'Device language'**
  String get languageSystem;

  /// A language is named in its own script in both locales, which is standard practice for a language picker
  ///
  /// In en, this message translates to:
  /// **'English'**
  String get languageEnglish;

  /// A language is named in its own script in both locales
  ///
  /// In en, this message translates to:
  /// **'العربية'**
  String get languageArabic;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Security'**
  String get profileSecurity;

  /// Security row title
  ///
  /// In en, this message translates to:
  /// **'Secure mobile session'**
  String get profileSecureSession;

  /// Security row body
  ///
  /// In en, this message translates to:
  /// **'Authentication tokens are stored in encrypted device storage.'**
  String get profileSecureSessionBody;

  /// Reviews list screen title
  ///
  /// In en, this message translates to:
  /// **'Pending Reviews'**
  String get reviewsPendingTitle;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Reviews'**
  String get reviewsTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Choose a project before opening consultant reviews.'**
  String get reviewsSelectProjectBody;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading review submissions'**
  String get reviewsLoading;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'Nothing waiting for review'**
  String get reviewsEmptyTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'New submissions matching your discipline will appear here.'**
  String get reviewsEmptyBody;

  /// Badge on a review row
  ///
  /// In en, this message translates to:
  /// **'Critical'**
  String get reviewCritical;

  /// Badge on a review row
  ///
  /// In en, this message translates to:
  /// **'Overdue'**
  String get reviewOverdue;

  /// Resubmission counter
  ///
  /// In en, this message translates to:
  /// **'Attempt {number}'**
  String reviewAttempt(String number);

  /// Submission timestamp
  ///
  /// In en, this message translates to:
  /// **'Submitted {date}'**
  String reviewSubmittedAt(String date);

  /// Evidence counter tag on a review row
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} evidence item} other{{count} evidence items}}'**
  String reviewEvidenceCount(int count);

  /// Fallback title for a review row
  ///
  /// In en, this message translates to:
  /// **'Review submission'**
  String get reviewSubmissionFallback;

  /// Review detail screen title
  ///
  /// In en, this message translates to:
  /// **'Review Submission'**
  String get reviewSubmissionTitle;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading submission and evidence'**
  String get reviewLoadingSubmission;

  /// Error title
  ///
  /// In en, this message translates to:
  /// **'Unable to open review'**
  String get reviewUnableToOpen;

  /// Error body
  ///
  /// In en, this message translates to:
  /// **'Review submission not found.'**
  String get reviewNotFound;

  /// Fallback heading
  ///
  /// In en, this message translates to:
  /// **'Task review'**
  String get reviewTaskReview;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Task and submission'**
  String get reviewTaskAndSubmission;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Submission'**
  String get reviewSubmission;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Completion note'**
  String get reviewCompletionNote;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Submitted evidence ({count})'**
  String reviewSubmittedEvidence(int count);

  /// Empty state
  ///
  /// In en, this message translates to:
  /// **'No evidence was attached to this submission.'**
  String get reviewNoEvidence;

  /// Fallback name for an attachment
  ///
  /// In en, this message translates to:
  /// **'Attachment'**
  String get reviewAttachment;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Dependency impact'**
  String get reviewDependencyImpact;

  /// Dependency counter
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} predecessor} other{{count} predecessors}}'**
  String reviewPredecessors(int count);

  /// Dependency counter
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} dependent task} other{{count} dependent tasks}}'**
  String reviewDependentTasks(int count);

  /// Dependency warning
  ///
  /// In en, this message translates to:
  /// **'Approval is currently gating downstream work.'**
  String get reviewGatingWork;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Start Review'**
  String get reviewStart;

  /// Action and dialog title
  ///
  /// In en, this message translates to:
  /// **'Approve Submission'**
  String get reviewApproveSubmission;

  /// Action and dialog title
  ///
  /// In en, this message translates to:
  /// **'Request Clarification'**
  String get reviewRequestClarification;

  /// Action and dialog title
  ///
  /// In en, this message translates to:
  /// **'Request Rework'**
  String get reviewRequestRework;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Review started.'**
  String get reviewStarted;

  /// Dialog hint
  ///
  /// In en, this message translates to:
  /// **'Approval marks this task complete and may unlock dependent work.'**
  String get reviewApprovalHint;

  /// Required field label
  ///
  /// In en, this message translates to:
  /// **'Rejection reason *'**
  String get reviewRejectionReasonRequired;

  /// Required field label
  ///
  /// In en, this message translates to:
  /// **'Required corrections *'**
  String get reviewRequiredCorrections;

  /// Required field label
  ///
  /// In en, this message translates to:
  /// **'Clarification question *'**
  String get reviewClarificationQuestion;

  /// Required field label
  ///
  /// In en, this message translates to:
  /// **'Review comments *'**
  String get reviewComments;

  /// Optional field label
  ///
  /// In en, this message translates to:
  /// **'Review note (optional)'**
  String get reviewNoteOptional;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Submission approved successfully.'**
  String get reviewApproved;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Rework request recorded.'**
  String get reviewReworkRecorded;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Clarification requested.'**
  String get reviewClarificationRequested;

  /// Collaboration screen title
  ///
  /// In en, this message translates to:
  /// **'My Actions'**
  String get collabMyActions;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Choose a project to see accountable actions.'**
  String get collabSelectProjectBody;

  /// Tab label
  ///
  /// In en, this message translates to:
  /// **'Actions'**
  String get collabTabActions;

  /// Tab label
  ///
  /// In en, this message translates to:
  /// **'Requests'**
  String get collabTabRequests;

  /// Tab label
  ///
  /// In en, this message translates to:
  /// **'Visits'**
  String get collabTabVisits;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'New request'**
  String get collabNewRequest;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Schedule'**
  String get collabSchedule;

  /// Sheet title
  ///
  /// In en, this message translates to:
  /// **'Client / Owner Request'**
  String get collabOwnerRequest;

  /// Sheet hint
  ///
  /// In en, this message translates to:
  /// **'This request does not modify the official design.'**
  String get collabRequestHint;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit for engineering review'**
  String get collabSubmitForReview;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Request submitted for human engineering review.'**
  String get collabRequestSubmitted;

  /// Sheet title
  ///
  /// In en, this message translates to:
  /// **'Schedule site visit'**
  String get collabScheduleVisit;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Site / location'**
  String get collabSiteLocation;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Start'**
  String get collabStart;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'End'**
  String get collabEnd;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Review and schedule'**
  String get collabReviewAndSchedule;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Site visit scheduled.'**
  String get collabVisitScheduled;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Action center'**
  String get collabActionCenter;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'What needs my attention right now?'**
  String get collabWhatNeedsAttention;

  /// Notice title
  ///
  /// In en, this message translates to:
  /// **'AI is advisory'**
  String get collabAiAdvisory;

  /// Notice body
  ///
  /// In en, this message translates to:
  /// **'AI alerts require human review and retain their project sources.'**
  String get collabAiAdvisoryBody;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Requests'**
  String get collabRequestsTitle;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No active owner requests'**
  String get collabNoRequests;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'New client requests and engineering responses will appear here.'**
  String get collabNoRequestsBody;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Schedule'**
  String get collabScheduleTitle;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No site visits scheduled'**
  String get collabNoVisits;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Visits across assigned projects will appear here.'**
  String get collabNoVisitsBody;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Acknowledge action'**
  String get collabAcknowledge;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'Needs my response'**
  String get collabNeedsMyResponse;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'Client requests'**
  String get collabOwnerRequests;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'Notifications requiring action'**
  String get collabRequiresActionNotifications;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'Upcoming site visits'**
  String get collabUpcomingSiteVisits;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'AI alerts to review'**
  String get collabAiAlertsRequiringReview;

  /// Action-centre counter
  ///
  /// In en, this message translates to:
  /// **'Tasks under review'**
  String get collabTasksUnderReview;

  /// Site visit type
  ///
  /// In en, this message translates to:
  /// **'Routine inspection'**
  String get collabVisitTypeRoutine;

  /// Site visit type
  ///
  /// In en, this message translates to:
  /// **'Quality audit'**
  String get collabVisitTypeQuality;

  /// Site visit type
  ///
  /// In en, this message translates to:
  /// **'Safety inspection'**
  String get collabVisitTypeSafety;

  /// Site visit type
  ///
  /// In en, this message translates to:
  /// **'Progress review'**
  String get collabVisitTypeProgress;

  /// Fallback visit location
  ///
  /// In en, this message translates to:
  /// **'Project site'**
  String get collabProjectSite;

  /// Screen title
  ///
  /// In en, this message translates to:
  /// **'My Field Evidence'**
  String get evidenceMyTitle;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'Evidence'**
  String get evidenceTitle;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading field evidence'**
  String get evidenceLoading;

  /// Empty state
  ///
  /// In en, this message translates to:
  /// **'No field evidence submitted yet.'**
  String get evidenceEmpty;

  /// Screen title
  ///
  /// In en, this message translates to:
  /// **'New Field Update'**
  String get evidenceNewTitle;

  /// Screen title for a resubmission
  ///
  /// In en, this message translates to:
  /// **'Corrected Evidence'**
  String get evidenceCorrectedTitle;

  /// Screen subtitle
  ///
  /// In en, this message translates to:
  /// **'Document completed site work'**
  String get evidenceDocumentWork;

  /// Screen hint
  ///
  /// In en, this message translates to:
  /// **'Your Engineer will verify this evidence. It does not change official task progress.'**
  String get evidenceVerifyHint;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'What work was completed?'**
  String get evidenceWhatWork;

  /// Field hint
  ///
  /// In en, this message translates to:
  /// **'Short, practical site note…'**
  String get evidenceHint;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Take Photo'**
  String get evidenceTakePhoto;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Add Photos'**
  String get evidenceAddPhotos;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Category (optional)'**
  String get evidenceCategoryOptional;

  /// Section hint
  ///
  /// In en, this message translates to:
  /// **'Choose any tags that apply. Your Engineer can correct them.'**
  String get evidenceCategoryHint;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'View (optional)'**
  String get evidenceViewOptional;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'front'**
  String get viewFront;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'back'**
  String get viewBack;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'left'**
  String get viewLeft;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'right'**
  String get viewRight;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'top'**
  String get viewTop;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'detail'**
  String get viewDetail;

  /// Photo view direction
  ///
  /// In en, this message translates to:
  /// **'other'**
  String get viewOther;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Remove photo'**
  String get evidenceRemovePhoto;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit Evidence'**
  String get evidenceSubmit;

  /// Success message
  ///
  /// In en, this message translates to:
  /// **'Field evidence sent to your Engineer.'**
  String get evidenceSent;

  /// Photo counter on a field-evidence card, pluralised.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} photo} other{{count} photos}}'**
  String evidencePhotoCount(int count);

  /// Action on a rejected submission
  ///
  /// In en, this message translates to:
  /// **'Submit Corrected Evidence'**
  String get evidenceSubmitCorrected;

  /// Fallback attachment name
  ///
  /// In en, this message translates to:
  /// **'Field photo'**
  String get evidencePhotoFallback;

  /// Screen title; IFC is a format name and stays Latin
  ///
  /// In en, this message translates to:
  /// **'IFC Intelligence'**
  String get ifcTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'Choose a project before opening IFC Intelligence.'**
  String get ifcSelectProjectBody;

  /// Loading label
  ///
  /// In en, this message translates to:
  /// **'Loading IFC models'**
  String get ifcLoading;

  /// Screen name used in error states
  ///
  /// In en, this message translates to:
  /// **'IFC models'**
  String get ifcModelsTitle;

  /// Empty state title
  ///
  /// In en, this message translates to:
  /// **'No IFC models'**
  String get ifcEmptyTitle;

  /// Empty state body
  ///
  /// In en, this message translates to:
  /// **'A project manager can create a model group and upload the first IFC version from the web workspace.'**
  String get ifcEmptyBody;

  /// Screen hint
  ///
  /// In en, this message translates to:
  /// **'Read-only field view of approved model facts and processing status.'**
  String get ifcReadOnlyHint;

  /// Fallback model group name
  ///
  /// In en, this message translates to:
  /// **'Federated model'**
  String get ifcFederatedModel;

  /// Empty state for a model group
  ///
  /// In en, this message translates to:
  /// **'No versions uploaded'**
  String get ifcNoVersions;

  /// Model version row; the title comes from the file
  ///
  /// In en, this message translates to:
  /// **'v{number} · {title}'**
  String ifcVersionLine(String number, String title);

  /// Element counter on an IFC version
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =1{{count} element} other{{count} elements}}'**
  String ifcElementCount(int count);

  /// Badge on the active model version
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get ifcActive;

  /// Fallback model version title
  ///
  /// In en, this message translates to:
  /// **'Untitled'**
  String get ifcUntitled;

  /// Screen title
  ///
  /// In en, this message translates to:
  /// **'Contact Administrator'**
  String get contactAdminTitle;

  /// Error title
  ///
  /// In en, this message translates to:
  /// **'Support details unavailable'**
  String get contactAdminUnavailable;

  /// Error body
  ///
  /// In en, this message translates to:
  /// **'Please contact your project office or try again when connected.'**
  String get contactAdminUnavailableBody;

  /// Card title
  ///
  /// In en, this message translates to:
  /// **'Company support'**
  String get contactAdminCompanySupport;

  /// Card body
  ///
  /// In en, this message translates to:
  /// **'Contact the administrator for account access and support.'**
  String get contactAdminBody;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Support phone'**
  String get contactAdminPhone;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Support email'**
  String get contactAdminEmail;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Office'**
  String get contactAdminOffice;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Stop recording'**
  String get recordStop;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Resume recording'**
  String get recordResume;

  /// Recorder state
  ///
  /// In en, this message translates to:
  /// **'Processing…'**
  String get recordProcessing;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Play recording'**
  String get recordPlay;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Pause playback'**
  String get recordPausePlayback;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Try again'**
  String get recordTryAgain;

  /// Recorder hint
  ///
  /// In en, this message translates to:
  /// **'Capture a hands-free field update'**
  String get recordCapture;

  /// Recorder hint
  ///
  /// In en, this message translates to:
  /// **'You review every proposal before submission'**
  String get recordReviewHint;

  /// Developer diagnostics screen, gated off in release builds
  ///
  /// In en, this message translates to:
  /// **'AI diagnostics are disabled in this build.'**
  String get diagnosticsDisabled;

  /// Developer diagnostics screen title
  ///
  /// In en, this message translates to:
  /// **'AI diagnostics (development)'**
  String get diagnosticsTitle;

  /// Developer diagnostics screen body
  ///
  /// In en, this message translates to:
  /// **'This screen checks configuration and permissions only. It never fakes a recording, upload, transcription, or AI result.'**
  String get diagnosticsBody;

  /// Developer diagnostics action
  ///
  /// In en, this message translates to:
  /// **'Run checks again'**
  String get diagnosticsRerun;

  /// Voice screen title
  ///
  /// In en, this message translates to:
  /// **'Construction Voice Assistant'**
  String get voiceTitle;

  /// Voice screen hint
  ///
  /// In en, this message translates to:
  /// **'Speak naturally about work, issues, or project updates.'**
  String get voiceSpeakNaturally;

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Task context (recommended)'**
  String get voiceTaskContext;

  /// Dropdown placeholder
  ///
  /// In en, this message translates to:
  /// **'Let AI suggest an assigned task'**
  String get voiceLetAiSuggest;

  /// Submit button
  ///
  /// In en, this message translates to:
  /// **'Submit for AI analysis'**
  String get voiceSubmitForAnalysis;

  /// Privacy footnote
  ///
  /// In en, this message translates to:
  /// **'Your recording is used to prepare this project action and is stored according to the project data policy.'**
  String get voicePrivacyNote;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Retry retained audio'**
  String get voiceRetryAudio;

  /// Result dialog title
  ///
  /// In en, this message translates to:
  /// **'Report sent'**
  String get voiceReportSent;

  /// Result dialog title
  ///
  /// In en, this message translates to:
  /// **'Action completed'**
  String get voiceActionCompleted;

  /// Result dialog body
  ///
  /// In en, this message translates to:
  /// **'Your report was sent to the responsible engineer for review.'**
  String get voiceReportSentBody;

  /// Result dialog body
  ///
  /// In en, this message translates to:
  /// **'{succeeded} of {total} selected actions succeeded.'**
  String voiceActionsSucceeded(int succeeded, int total);

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Pause'**
  String get voicePause;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Delete'**
  String get voiceDelete;

  /// Recorder control
  ///
  /// In en, this message translates to:
  /// **'Record again'**
  String get voiceRecordAgain;

  /// Progress label
  ///
  /// In en, this message translates to:
  /// **'Uploading recording securely…'**
  String get voiceUploading;

  /// Progress label
  ///
  /// In en, this message translates to:
  /// **'Transcribing speech…'**
  String get voiceTranscribing;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Live recording waveform'**
  String get voiceLiveWaveform;

  /// Accessibility label
  ///
  /// In en, this message translates to:
  /// **'Recorded audio waveform'**
  String get voiceRecordedWaveform;

  /// Section heading
  ///
  /// In en, this message translates to:
  /// **'Review what I understood'**
  String get voiceReviewUnderstood;

  /// Section subheading
  ///
  /// In en, this message translates to:
  /// **'Choose and edit the actions you want to confirm.'**
  String get voiceChooseActions;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'AI SUMMARY'**
  String get voiceAiSummary;

  /// Placeholder when no task was detected
  ///
  /// In en, this message translates to:
  /// **'Select a task'**
  String get voiceSelectTask;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'WORK COMPLETED'**
  String get voiceWorkCompleted;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'PROBLEMS / BLOCKERS'**
  String get voiceProblems;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'SUGGESTED ACTIONS'**
  String get voiceSuggestedActions;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'TRANSCRIPT'**
  String get voiceTranscript;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'TASK'**
  String get voiceTask;

  /// Section label
  ///
  /// In en, this message translates to:
  /// **'PROGRESS'**
  String get voiceProgressLabel;

  /// Progress detected in speech but not yet applied
  ///
  /// In en, this message translates to:
  /// **'{percent}% mentioned — not yet official'**
  String voiceProgressMentioned(String percent);

  /// Suggested voice action
  ///
  /// In en, this message translates to:
  /// **'Update task progress'**
  String get voiceIntentUpdateProgress;

  /// Suggested voice action
  ///
  /// In en, this message translates to:
  /// **'Report issue'**
  String get voiceIntentReportIssue;

  /// Suggested voice action
  ///
  /// In en, this message translates to:
  /// **'Send message'**
  String get voiceIntentSendMessage;

  /// Suggested voice action
  ///
  /// In en, this message translates to:
  /// **'Submit site report'**
  String get voiceIntentSubmitReport;

  /// Suggested voice action
  ///
  /// In en, this message translates to:
  /// **'Request clarification'**
  String get voiceIntentRequestClarification;

  /// Empty state
  ///
  /// In en, this message translates to:
  /// **'No safe executable action was suggested.'**
  String get voiceNoSafeAction;

  /// Confidence caption on a suggested action
  ///
  /// In en, this message translates to:
  /// **'{percent}% confidence'**
  String voiceConfidence(int percent);

  /// Field label
  ///
  /// In en, this message translates to:
  /// **'Confirmed progress (0–100)'**
  String get voiceConfirmedProgress;

  /// Field hint
  ///
  /// In en, this message translates to:
  /// **'Review/edit value'**
  String get voiceReviewEditValue;

  /// Confirmation checkbox
  ///
  /// In en, this message translates to:
  /// **'I reviewed the affected task, recipients, and workflow impact.'**
  String get voiceReviewedAffected;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Discard'**
  String get voiceDiscard;

  /// Action
  ///
  /// In en, this message translates to:
  /// **'Confirm selected'**
  String get voiceConfirmSelected;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Microphone permission is required.'**
  String get voiceMicPermissionRequired;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Record audio before transcribing.'**
  String get voiceRecordBeforeTranscribe;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Record audio before analysis.'**
  String get voiceRecordBeforeAnalysis;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'No analysis to retry.'**
  String get voiceNoAnalysisRetry;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'No analysis to confirm.'**
  String get voiceNoAnalysisConfirm;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'No analysis to clarify.'**
  String get voiceNoAnalysisClarify;

  /// Error message
  ///
  /// In en, this message translates to:
  /// **'Voice action is no longer available.'**
  String get voiceActionUnavailable;

  /// Label for the raised voice-capture action in the centre of the bottom navigation.
  ///
  /// In en, this message translates to:
  /// **'Voice Assistant'**
  String get navVoiceAssistant;

  /// Title of the contextual action sheet opened from a record.
  ///
  /// In en, this message translates to:
  /// **'Actions'**
  String get shareActionsTitle;

  /// Action: send this record or message on to someone else.
  ///
  /// In en, this message translates to:
  /// **'Forward'**
  String get shareForward;

  /// One-line explanation under the Forward action.
  ///
  /// In en, this message translates to:
  /// **'Send this on to someone else.'**
  String get shareForwardHint;

  /// Action: ask a colleague to advise on a record. Deliberately not called Forward, because nothing is handed over.
  ///
  /// In en, this message translates to:
  /// **'Ask for Opinion'**
  String get shareAskOpinion;

  /// One-line explanation under the Ask for Opinion action, stating that it does not change ownership.
  ///
  /// In en, this message translates to:
  /// **'Ask a colleague to advise. Nothing is reassigned.'**
  String get shareAskOpinionHint;

  /// Action: send a copy of a record into a conversation.
  ///
  /// In en, this message translates to:
  /// **'Share'**
  String get shareShare;

  /// One-line explanation under the Share action.
  ///
  /// In en, this message translates to:
  /// **'Send a copy into a conversation.'**
  String get shareShareHint;

  /// Section label above the recipient picker in the share sheet.
  ///
  /// In en, this message translates to:
  /// **'Recipients'**
  String get shareRecipients;

  /// Label of the free-text note field in the share sheet.
  ///
  /// In en, this message translates to:
  /// **'Note (optional)'**
  String get shareNoteLabel;

  /// Primary button of the share sheet.
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get shareSend;

  /// Progress label while a share or forward is in flight.
  ///
  /// In en, this message translates to:
  /// **'Sending'**
  String get shareSending;

  /// Loading label while the authorized recipient list is fetched.
  ///
  /// In en, this message translates to:
  /// **'Loading recipients'**
  String get shareLoadingRecipients;

  /// Empty state when the project has no other authorized recipients.
  ///
  /// In en, this message translates to:
  /// **'No one to send to'**
  String get shareNoRecipientsTitle;

  /// Body of the empty recipient state.
  ///
  /// In en, this message translates to:
  /// **'There is nobody on this project you can send this to.'**
  String get shareNoRecipientsBody;

  /// Validation message when the send button is pressed with nobody selected.
  ///
  /// In en, this message translates to:
  /// **'Select at least one recipient.'**
  String get shareSelectRecipient;

  /// Confirmation after a message is forwarded.
  ///
  /// In en, this message translates to:
  /// **'Message forwarded.'**
  String get shareSentForward;

  /// Confirmation after a consultation request is sent.
  ///
  /// In en, this message translates to:
  /// **'Opinion requested.'**
  String get shareSentOpinion;

  /// Confirmation after a record is shared.
  ///
  /// In en, this message translates to:
  /// **'Shared.'**
  String get shareSentShare;

  /// Counter under the recipient list, pluralised.
  ///
  /// In en, this message translates to:
  /// **'{count, plural, =0{No one selected} =1{{count} selected} other{{count} selected}}'**
  String shareSelectedCount(int count);

  /// Prefilled note when asking a colleague for an opinion.
  ///
  /// In en, this message translates to:
  /// **'Could you give me your opinion on this?'**
  String get shareOpinionPrefill;

  /// Snack-bar action that opens the conversation a share just created.
  ///
  /// In en, this message translates to:
  /// **'Open'**
  String get shareOpen;

  /// Heading of the field-first section listing what the user must act on now.
  ///
  /// In en, this message translates to:
  /// **'Today'**
  String get dashboardTodayTitle;

  /// Subtitle of the Today section.
  ///
  /// In en, this message translates to:
  /// **'What needs you on site right now.'**
  String get dashboardTodayBody;

  /// Empty state when a role has no outstanding exceptions.
  ///
  /// In en, this message translates to:
  /// **'Nothing needs you right now'**
  String get dashboardAllClearTitle;

  /// Body of the all-clear empty state.
  ///
  /// In en, this message translates to:
  /// **'No overdue, blocked or waiting work on this project.'**
  String get dashboardAllClearBody;

  /// Tooltip of the avatar button in the dashboard header, which opens the profile.
  ///
  /// In en, this message translates to:
  /// **'Your profile'**
  String get dashboardOpenProfile;

  /// Shown when the activity feed cannot be resolved into readable entries.
  ///
  /// In en, this message translates to:
  /// **'Recent activity is unavailable.'**
  String get dashboardActivityUnavailable;

  /// Heading of the card asking the speaker a follow-up question.
  ///
  /// In en, this message translates to:
  /// **'More information needed'**
  String get voiceClarificationTitle;

  /// Label of the answer field in the clarification card.
  ///
  /// In en, this message translates to:
  /// **'Answer'**
  String get voiceClarificationAnswerLabel;

  /// Hint text of the answer field in the clarification card.
  ///
  /// In en, this message translates to:
  /// **'Write a short, specific answer'**
  String get voiceClarificationAnswerHint;

  /// Button that submits a clarification answer.
  ///
  /// In en, this message translates to:
  /// **'Continue'**
  String get voiceContinue;

  /// Permission-denied state shown when a role may not use the voice assistant.
  ///
  /// In en, this message translates to:
  /// **'Voice is not available'**
  String get voiceUnavailableTitle;

  /// Body of the voice permission-denied state.
  ///
  /// In en, this message translates to:
  /// **'The voice assistant is for project and field roles. Administration is done on the web application.'**
  String get voiceUnavailableBody;

  /// Fallback description for an activity entry the app has no wording for. Shown instead of the raw database identifier.
  ///
  /// In en, this message translates to:
  /// **'Project activity'**
  String get activityGeneric;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Task created'**
  String get activityTaskCreated;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Task started'**
  String get activityTaskStarted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Task resumed'**
  String get activityTaskResumed;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Progress updated'**
  String get activityProgressUpdated;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Submitted for review'**
  String get activitySubmitted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Approved'**
  String get activityApproved;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Review started'**
  String get activityReviewStarted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Rework requested'**
  String get activityReworkRequested;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Rework started'**
  String get activityReworkStarted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Clarification requested'**
  String get activityClarificationRequested;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Clarification answered'**
  String get activityClarificationResponded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Comment added'**
  String get activityCommentAdded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Work update added'**
  String get activityWorkUpdateAdded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Blocker reported'**
  String get activityBlockerReported;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Document uploaded'**
  String get activityDocumentUploaded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Attachment uploaded'**
  String get activityAttachmentUploaded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Site report verified'**
  String get activitySiteReportVerified;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Site visit scheduled'**
  String get activitySiteVisitScheduled;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Owner request submitted'**
  String get activityOwnerRequestSubmitted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Schedule recalculated'**
  String get activityScheduleRecalculated;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Reminders sent'**
  String get activityRemindersDispatched;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Team member assigned'**
  String get activityMemberAssigned;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Model version uploaded'**
  String get activityModelVersionUploaded;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Voice update recorded'**
  String get activityVoiceUpdate;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Field evidence verified'**
  String get activityEvidenceVerified;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Field evidence returned'**
  String get activityEvidenceRejected;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Field evidence submitted'**
  String get activityEvidenceSubmitted;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Created'**
  String get activityCreated;

  /// Activity entry.
  ///
  /// In en, this message translates to:
  /// **'Updated'**
  String get activityUpdated;

  /// Field label for an issue's severity.
  ///
  /// In en, this message translates to:
  /// **'Severity'**
  String get commonSeverity;

  /// Field label for a record's creation date.
  ///
  /// In en, this message translates to:
  /// **'Created'**
  String get commonCreated;

  /// Field label for a due date.
  ///
  /// In en, this message translates to:
  /// **'Due'**
  String get commonDue;

  /// Shown in a record's detail sheet when it carries no description.
  ///
  /// In en, this message translates to:
  /// **'No description provided.'**
  String get commonNoDescription;

  /// Tooltip of the overflow button that opens a record's contextual actions.
  ///
  /// In en, this message translates to:
  /// **'More actions'**
  String get commonMoreActions;

  /// Navigation label for the design-changes list.
  ///
  /// In en, this message translates to:
  /// **'Design Changes'**
  String get navDesignChanges;

  /// Empty state of the design-changes list.
  ///
  /// In en, this message translates to:
  /// **'No design changes have been raised on this project.'**
  String get designChangesEmpty;

  /// Stand-in name for a dependency the API returned without a title.
  ///
  /// In en, this message translates to:
  /// **'Blocking task'**
  String get taskDependencyUnnamed;

  /// Heading shown when every confirmed voice action executed successfully.
  ///
  /// In en, this message translates to:
  /// **'Actions completed'**
  String get voiceOutcomeSuccessTitle;

  /// Heading shown when some confirmed voice actions succeeded and others failed.
  ///
  /// In en, this message translates to:
  /// **'Some actions completed'**
  String get voiceOutcomePartialTitle;

  /// Heading shown when no confirmed voice action succeeded. Must never look like success.
  ///
  /// In en, this message translates to:
  /// **'No action was carried out'**
  String get voiceOutcomeFailureTitle;

  /// Heading when the assistant understood the note but no executable action was required.
  ///
  /// In en, this message translates to:
  /// **'Nothing to carry out'**
  String get voiceOutcomeNothingTitle;

  /// Body for the nothing-to-execute outcome.
  ///
  /// In en, this message translates to:
  /// **'The note was understood, but it did not require any change in the system.'**
  String get voiceOutcomeNothingBody;

  /// Label before the explanation of why one action failed.
  ///
  /// In en, this message translates to:
  /// **'Reason'**
  String get voiceOutcomeReason;

  /// Status shown beside a single failed action in the outcome list.
  ///
  /// In en, this message translates to:
  /// **'Not carried out'**
  String get voiceOutcomeNotExecuted;

  /// Status shown beside a single successful action in the outcome list.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get voiceOutcomeExecuted;

  /// User-facing explanation for a payload validation rejection, shown instead of the raw backend message.
  ///
  /// In en, this message translates to:
  /// **'The system refused some of the details the assistant produced for this action.'**
  String get voiceOutcomeRejectedFields;

  /// Fallback explanation for a failed action when no specific reason is recognised.
  ///
  /// In en, this message translates to:
  /// **'This action could not be carried out.'**
  String get voiceOutcomeGenericFailure;
}

class _AppL10nDelegate extends LocalizationsDelegate<AppL10n> {
  const _AppL10nDelegate();

  @override
  Future<AppL10n> load(Locale locale) {
    return SynchronousFuture<AppL10n>(lookupAppL10n(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppL10nDelegate old) => false;
}

AppL10n lookupAppL10n(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppL10nAr();
    case 'en':
      return AppL10nEn();
  }

  throw FlutterError(
    'AppL10n.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
