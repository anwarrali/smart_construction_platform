// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppL10nAr extends AppL10n {
  AppL10nAr([String locale = 'ar']) : super(locale);

  @override
  String get commonLoading => 'جارٍ التحميل…';

  @override
  String get commonRetry => 'إعادة المحاولة';

  @override
  String get commonCancel => 'إلغاء';

  @override
  String get commonConfirm => 'تأكيد';

  @override
  String get commonSubmit => 'إرسال';

  @override
  String get commonSubmitting => 'جارٍ الإرسال…';

  @override
  String get commonSaveDraft => 'حفظ كمسودة';

  @override
  String get commonCreate => 'إنشاء';

  @override
  String get commonDelete => 'حذف';

  @override
  String get commonUpdate => 'تحديث';

  @override
  String get commonApprove => 'اعتماد';

  @override
  String get commonDone => 'تم';

  @override
  String get commonAll => 'الكل';

  @override
  String get commonOptional => '(اختياري)';

  @override
  String get commonStatus => 'الحالة';

  @override
  String get commonPriority => 'الأولوية';

  @override
  String get commonDiscipline => 'التخصص';

  @override
  String get commonDescription => 'الوصف';

  @override
  String get commonTitle => 'العنوان';

  @override
  String get commonCategory => 'التصنيف';

  @override
  String get commonNote => 'ملاحظة';

  @override
  String get commonProject => 'المشروع';

  @override
  String get commonProgress => 'نسبة الإنجاز';

  @override
  String get commonNotifications => 'الإشعارات';

  @override
  String get commonToday => 'اليوم';

  @override
  String get commonYesterday => 'أمس';

  @override
  String get commonViewAll => 'عرض الكل';

  @override
  String get commonSignOut => 'تسجيل الخروج';

  @override
  String get commonLogOut => 'تسجيل الخروج';

  @override
  String get commonSelectProject => 'اختر مشروعًا';

  @override
  String get commonSelectProjectFirst => 'اختر مشروعًا أولًا.';

  @override
  String get commonNoProjectSelected => 'لم يتم اختيار مشروع';

  @override
  String get commonNothingHereYet => 'لا يوجد شيء هنا بعد';

  @override
  String commonUnavailable(String subject) {
    return 'تعذّر تحميل $subject';
  }

  @override
  String commonPercent(String value) {
    return '$value٪';
  }

  @override
  String get navHome => 'الرئيسية';

  @override
  String get navTasks => 'المهام';

  @override
  String get navMyTasks => 'مهامي';

  @override
  String get navReports => 'التقارير';

  @override
  String get navMessages => 'الرسائل';

  @override
  String get navProfile => 'الملف الشخصي';

  @override
  String get navReviews => 'المراجعات';

  @override
  String get navDocuments => 'المستندات';

  @override
  String get navIssues => 'الملاحظات';

  @override
  String get navProjects => 'المشاريع';

  @override
  String get navEvidence => 'الإثباتات';

  @override
  String get navMyActions => 'الإجراءات المطلوبة مني';

  @override
  String get navIfcModels => 'نماذج IFC';

  @override
  String get navFieldEvidence => 'إثباتات الموقع';

  @override
  String get navRecordUpdate => 'تسجيل تحديث';

  @override
  String get navRecordFieldUpdate => 'تسجيل تحديث ميداني';

  @override
  String get errorGeneric => 'حدث خطأ ما. يُرجى المحاولة مرة أخرى.';

  @override
  String get errorTimeout =>
      'استغرق الخادم وقتًا طويلًا للاستجابة. يُرجى إعادة المحاولة.';

  @override
  String get errorNetwork =>
      'تعذّر الوصول إلى خادم المشروع. تحقق من أن الخادم يعمل وأن هذا الجهاز على الشبكة الصحيحة.';

  @override
  String get errorUnauthorized => 'لم يتم تسجيل الدخول.';

  @override
  String get errorForbidden => 'لا تملك صلاحية تنفيذ هذا الإجراء.';

  @override
  String get errorNotFound => 'تعذّر العثور على هذا السجل.';

  @override
  String get errorConflict => 'يتعارض هذا مع سجل قائم بالفعل.';

  @override
  String get errorValidation => 'يُرجى تصحيح الحقول المُحدَّدة.';

  @override
  String get errorLoadFailed => 'تعذّر تحميل هذه المعلومات.';

  @override
  String get errorSaveFailed => 'تعذّر حفظ التعديلات.';

  @override
  String get errorActionFailed => 'تعذّر إتمام الإجراء.';

  @override
  String get validationRequired => 'هذا الحقل مطلوب.';

  @override
  String get validationEnterEmailOrUsername =>
      'أدخل بريدك الإلكتروني أو اسم المستخدم.';

  @override
  String get validationEnterPassword => 'أدخل كلمة المرور.';

  @override
  String get validationEnterIssueTitle => 'أدخل عنوان الملاحظة.';

  @override
  String get validationDescribeIssue => 'اكتب وصف الملاحظة.';

  @override
  String get validationAddReportSummary => 'أضف ملخص التقرير.';

  @override
  String get validationCompleteRequiredFields => 'أكمل جميع الحقول المطلوبة.';

  @override
  String get validationEnterClarificationQuestion => 'أدخل سؤال التوضيح.';

  @override
  String get brandDescriptor => 'إدارة إنشاءات ذكية';

  @override
  String get loginSignIn => 'تسجيل الدخول';

  @override
  String get loginSubtitle => 'استخدم حساب مؤسستك للمتابعة.';

  @override
  String get loginEmailLabel => 'البريد الإلكتروني أو اسم المستخدم';

  @override
  String get loginEmailHint => 'name@company.com';

  @override
  String get loginPasswordLabel => 'كلمة المرور';

  @override
  String get loginPasswordHint => 'أدخل كلمة المرور';

  @override
  String get loginShowPassword => 'إظهار كلمة المرور';

  @override
  String get loginHidePassword => 'إخفاء كلمة المرور';

  @override
  String get loginSubmit => 'تسجيل دخول آمن';

  @override
  String get loginNeedHelp => 'تحتاج مساعدة؟ تواصل مع مدير النظام';

  @override
  String get loginSecureAccess => 'وصول آمن · لأعضاء المشروع المصرّح لهم فقط';

  @override
  String get loginInvalidCredentials =>
      'البريد الإلكتروني أو اسم المستخدم أو كلمة المرور غير صحيحة.';

  @override
  String get loginAccountDeactivated => 'تم تعطيل حسابك. تواصل مع مدير النظام.';

  @override
  String get loginTooManyAttempts =>
      'محاولات تسجيل دخول فاشلة كثيرة. حاول مرة أخرى لاحقًا.';

  @override
  String get loginWelcomeBack => 'مرحبًا بعودتك';

  @override
  String get loginWelcomeBody =>
      'أدر المشاريع وأعمال الموقع وتعاون الفريق من أي مكان.';

  @override
  String get projectsLoading => 'جارٍ تحميل المشاريع المُسندة';

  @override
  String get projectsTitle => 'المشاريع';

  @override
  String get projectsNoneAssigned => 'لا توجد مشاريع مُسندة';

  @override
  String get projectsNoneAssignedBody =>
      'تواصل مع مدير النظام أو مدير المشروع للحصول على صلاحية، أو بدّل إلى حساب آخر.';

  @override
  String get projectsSwitchAccount => 'تبديل الحساب';

  @override
  String get projectsSwitchAccountQuestion => 'تبديل الحساب؟';

  @override
  String get projectsSwitchAccountBody =>
      'سيتم تسجيل خروجك وإعادتك إلى شاشة تسجيل الدخول.';

  @override
  String get projectsMyProjects => 'مشاريعي';

  @override
  String get projectsSelectWorkspace => 'اختر مساحة عمل للمتابعة';

  @override
  String get projectsProgress => 'نسبة إنجاز المشروع';

  @override
  String projectsOpenIssues(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count ملاحظة مفتوحة',
      few: '$count ملاحظات مفتوحة',
      two: 'ملاحظتان مفتوحتان',
      one: 'ملاحظة مفتوحة واحدة',
      zero: 'لا توجد ملاحظات مفتوحة',
    );
    return '$_temp0';
  }

  @override
  String get projectsCurrentProject => 'المشروع الحالي';

  @override
  String get projectsOpenWorkspace => 'فتح مساحة العمل';

  @override
  String get statusBacklog => 'قائمة الانتظار';

  @override
  String get statusTodo => 'لم تبدأ';

  @override
  String get statusInProgress => 'قيد التنفيذ';

  @override
  String get statusUnderReview => 'قيد المراجعة';

  @override
  String get statusReworkRequired => 'تتطلب إعادة عمل';

  @override
  String get statusDone => 'مكتملة';

  @override
  String get statusBlocked => 'متوقفة';

  @override
  String get statusCancelled => 'ملغى';

  @override
  String get statusOpen => 'مفتوحة';

  @override
  String get statusResolved => 'تمت المعالجة';

  @override
  String get statusClosed => 'مغلقة';

  @override
  String get statusPending => 'قيد الانتظار';

  @override
  String get statusInReview => 'قيد المراجعة';

  @override
  String get statusApproved => 'معتمد';

  @override
  String get statusRejected => 'مرفوض';

  @override
  String get statusClarificationRequested => 'مطلوب توضيح';

  @override
  String get statusDraft => 'مسودة';

  @override
  String get statusSubmitted => 'مُرسل';

  @override
  String get statusProposed => 'مقترح';

  @override
  String get statusImplemented => 'مُنفَّذ';

  @override
  String get statusPlanning => 'قيد التخطيط';

  @override
  String get statusActive => 'قيد التنفيذ';

  @override
  String get statusOnHold => 'متوقف مؤقتًا';

  @override
  String get statusDelayed => 'متأخر';

  @override
  String get statusCompleted => 'مكتمل';

  @override
  String get statusVerified => 'تم التحقق';

  @override
  String get statusOnTrack => 'ضمن الخطة';

  @override
  String get statusAtRisk => 'معرض للخطر';

  @override
  String get priorityLow => 'منخفضة';

  @override
  String get priorityMedium => 'متوسطة';

  @override
  String get priorityHigh => 'عالية';

  @override
  String get priorityCritical => 'حرجة';

  @override
  String get priorityNormal => 'عادية';

  @override
  String get priorityImportant => 'مهم';

  @override
  String get priorityInfo => 'معلومة';

  @override
  String get disciplineCivil => 'مدني';

  @override
  String get disciplineArchitectural => 'معماري';

  @override
  String get disciplineElectrical => 'كهربائي';

  @override
  String get disciplineMechanical => 'ميكانيكي';

  @override
  String get disciplineStructural => 'إنشائي';

  @override
  String get disciplinePlumbing => 'صحي';

  @override
  String get disciplineHvac => 'تكييف وتهوية';

  @override
  String get disciplineFireProtection => 'مكافحة الحريق';

  @override
  String get disciplineGeneral => 'عام';

  @override
  String get disciplineUnclassified => 'غير مصنّف';

  @override
  String get disciplineUnassigned => 'غير مُسند';

  @override
  String get roleAdmin => 'مدير النظام';

  @override
  String get roleOwner => 'المالك';

  @override
  String get roleProjectManager => 'مدير المشروع';

  @override
  String get roleEngineer => 'مهندس';

  @override
  String get roleConsultant => 'الاستشاري';

  @override
  String get roleWorker => 'عامل';

  @override
  String get roleCaptionSiteEngineer => 'المقاول الرئيسي · مهندس موقع';

  @override
  String get roleCaptionConsultant => 'المهندس الاستشاري · المراجعة والجودة';

  @override
  String get roleCaptionOwner => 'مالك المشروع · العرض التنفيذي';

  @override
  String get roleCaptionWorker => 'عامل بناء · إثباتات الموقع';

  @override
  String get roleCaptionProjectManager => 'مدير المشروع · متابعة الموقع';

  @override
  String get roleCaptionConsultantShort => 'المهندس الاستشاري';

  @override
  String get dashboardSelectProjectBody => 'اختر مشروعًا لعرض لوحته.';

  @override
  String get dashboardLoading => 'جارٍ تحميل لوحة المشروع';

  @override
  String get dashboardTitle => 'لوحة التحكم';

  @override
  String get dashboardGreetingMorning => 'صباح الخير';

  @override
  String get dashboardGreetingAfternoon => 'مساء الخير';

  @override
  String get dashboardGreetingEvening => 'مساء الخير';

  @override
  String dashboardGreeting(String greeting, String name) {
    return '$greeting، $name';
  }

  @override
  String get dashboardChangeProject => 'تغيير المشروع';

  @override
  String get dashboardFastFieldUpdate => 'تحديث ميداني سريع';

  @override
  String get dashboardFastFieldUpdateBody => 'سجّل العمل دون إيقاف سير عملك';

  @override
  String get dashboardExecutiveIntelligence => 'التحليلات التنفيذية';

  @override
  String get dashboardExecutiveIntelligenceBody =>
      'الحالة الحالية والتحليلات الذكية المستقبلية';

  @override
  String get dashboardNeedsAttention => 'يتطلب انتباهك';

  @override
  String get dashboardProjectSnapshot => 'لمحة عن المشروع';

  @override
  String get dashboardQuickAccess => 'وصول سريع';

  @override
  String get dashboardQuickAccessBody => 'أدوات المشروع المناسبة لدورك';

  @override
  String get dashboardRecentActivity => 'النشاط الأخير';

  @override
  String get dashboardRecentActivityBody => 'أحدث المعلومات من هذا المشروع';

  @override
  String get dashboardSnapshotEngineer =>
      'المهام والمعوّقات والمراجعات التي تتطلب إجراءً';

  @override
  String get dashboardSnapshotConsultant => 'حجم المراجعات والأعمال المُرسلة';

  @override
  String get dashboardSnapshotOwner =>
      'التقدّم والمخاطر والقرارات على المستوى العام';

  @override
  String get dashboardSnapshotManager => 'صحة التنفيذ وأولويات الفريق';

  @override
  String get dashboardPendingReviews => 'مراجعات معلقة';

  @override
  String get dashboardOverdueReviews => 'مراجعات متأخرة';

  @override
  String get dashboardApprovedWork => 'أعمال معتمدة';

  @override
  String get dashboardAwaitingRework => 'بانتظار إعادة العمل';

  @override
  String get dashboardDelayedTasks => 'مهام متأخرة';

  @override
  String get dashboardOpenRisks => 'مخاطر مفتوحة';

  @override
  String get dashboardDecisions => 'قرارات';

  @override
  String get dashboardMilestones => 'مراحل رئيسية';

  @override
  String get dashboardAssignedTasks => 'مهام مُسندة';

  @override
  String get dashboardSubmitted => 'مُرسلة';

  @override
  String get dashboardVerified => 'تم التحقق منها';

  @override
  String get dashboardNeedsCorrection => 'تحتاج تصحيحًا';

  @override
  String get dashboardTodaysTasks => 'مهام اليوم';

  @override
  String get dashboardOverdue => 'متأخرة';

  @override
  String get dashboardBlocked => 'متوقفة';

  @override
  String get dashboardWaitingReview => 'بانتظار المراجعة';

  @override
  String get dashboardReworkRequired => 'تتطلب إعادة عمل';

  @override
  String get dashboardOpenIssues => 'ملاحظات مفتوحة';

  @override
  String get dashboardOverallProgress => 'التقدّم الإجمالي';

  @override
  String get dashboardLiveProjectData => 'بيانات المشروع الحيّة';

  @override
  String dashboardProgressSemantics(String progress, String health) {
    return 'التقدّم الإجمالي $progress٪. حالة المشروع $health.';
  }

  @override
  String dashboardExecutiveSummary(
    String progress,
    String health,
    int delayed,
    int risks,
  ) {
    return 'التقدّم الإجمالي $progress٪. حالة المشروع $health. هناك $delayed مهمة متأخرة و$risks من المخاطر المفتوحة التي تتطلب متابعة.';
  }

  @override
  String get dashboardSummaryTitle => 'ملخص المشروع الذكي';

  @override
  String get dashboardSummarySubtitle => 'تحليلات تنفيذية للمشروع';

  @override
  String get dashboardLiveData => 'بيانات حيّة';

  @override
  String get dashboardAiReady => 'جاهز للذكاء الاصطناعي';

  @override
  String get dashboardAiPlaceholder =>
      'ستظهر هنا التحليلات المولّدة بالذكاء الاصطناعي عند ربط خدمة الملخص. تبقى مؤشرات المشروع الحالية متاحة أدناه.';

  @override
  String get dashboardGeneratedFrom =>
      'مولّدة من مؤشرات الخادم الحالية · بدون ذكاء اصطناعي خارجي';

  @override
  String get dashboardFutureIntegration =>
      'عنصر نائب لتكامل مستقبلي · بدون تحليلات ملفّقة';

  @override
  String get dashboardNoActivity =>
      'سيظهر هنا نشاط المشروع الجديد مع عمل فريقك.';

  @override
  String get dashboardProjectActivity => 'نشاط المشروع';

  @override
  String get tasksMyTasks => 'مهامي';

  @override
  String get tasksProjectTasks => 'مهام المشروع';

  @override
  String get tasksLoading => 'جارٍ تحميل المهام';

  @override
  String get tasksTitle => 'المهام';

  @override
  String get tasksTotal => 'الإجمالي';

  @override
  String get tasksOverdue => 'متأخرة';

  @override
  String get tasksBlocked => 'متوقفة';

  @override
  String get tasksNoMatching => 'لا توجد مهام مطابقة';

  @override
  String get tasksNoAssigned => 'لا توجد مهام مُسندة في هذا العرض.';

  @override
  String get tasksFilterRework => 'إعادة عمل';

  @override
  String get taskDetailTitle => 'تفاصيل المهمة';

  @override
  String get taskTitle => 'المهمة';

  @override
  String taskPercentComplete(String percent) {
    return 'مكتملة $percent٪';
  }

  @override
  String get taskCannotStartYet => 'لا يمكن البدء بعد';

  @override
  String get taskQuickActions => 'إجراءات سريعة';

  @override
  String get taskDiscussion => 'نقاش المهمة';

  @override
  String get taskVoiceUpdate => 'تحديث ميداني صوتي بالذكاء الاصطناعي';

  @override
  String get taskStart => 'بدء المهمة';

  @override
  String get taskUpdateProgress => 'تحديث نسبة الإنجاز';

  @override
  String get taskAddComment => 'إضافة تعليق';

  @override
  String get taskSubmitForReview => 'تقديم للمراجعة';

  @override
  String get taskCreateFieldUpdate => 'إنشاء تحديث ميداني';

  @override
  String get taskEvidenceHistory => 'سجل إثباتاتي';

  @override
  String get taskNoPermission => 'لا تملك صلاحية تحديث هذه المهمة.';

  @override
  String get taskUpdated => 'تم تحديث المهمة.';

  @override
  String get taskWorkNote => 'ملاحظة عمل (اختياري)';

  @override
  String get taskDependencyBlocked => 'متوقفة بسبب اعتمادية';

  @override
  String taskDueOn(String date) {
    return 'الاستحقاق $date';
  }

  @override
  String taskDaysOverdue(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'متأخرة $count يومًا',
      few: 'متأخرة $count أيام',
      two: 'متأخرة يومين',
      one: 'متأخرة يومًا واحدًا',
    );
    return '$_temp0';
  }

  @override
  String taskDependencyLine(String name, String status) {
    return '· $name ($status)';
  }

  @override
  String get taskBlockingTask => 'مهمة معيقة';

  @override
  String get issuesTitle => 'الملاحظات والمعوّقات';

  @override
  String get issuesEmpty => 'لم يتم تسجيل أي ملاحظات.';

  @override
  String get issueReport => 'تسجيل ملاحظة';

  @override
  String get issueTitleLabel => 'عنوان الملاحظة';

  @override
  String get issueSeverity => 'درجة الخطورة';

  @override
  String get issueAffectsSchedule => 'يؤثر على الجدول الزمني للمشروع';

  @override
  String get issueAffectsScheduleBody =>
      'ضع علامة على هذه الملاحظة للانتباه للجدول الزمني.';

  @override
  String get issueSubmit => 'إرسال الملاحظة';

  @override
  String get issueReported => 'تم تسجيل الملاحظة بنجاح.';

  @override
  String get issueCategoryMaterialUnavailable => 'المواد غير متوفرة';

  @override
  String get issueCategoryPreviousTaskIncomplete => 'المهمة السابقة غير مكتملة';

  @override
  String get issueCategoryDrawingUnavailable => 'المخطط غير متوفر';

  @override
  String get issueCategoryEquipmentUnavailable => 'المعدات غير متوفرة';

  @override
  String get issueCategoryLaborShortage => 'نقص في العمالة';

  @override
  String get issueCategorySiteAccess => 'مشكلة في الوصول للموقع';

  @override
  String get issueCategoryConsultantClarification => 'مطلوب توضيح من الاستشاري';

  @override
  String get issueCategoryTechnicalConflict => 'تعارض فني';

  @override
  String get issueCategorySafetyRestriction => 'قيد يتعلق بالسلامة';

  @override
  String get issueCategoryOther => 'أخرى';

  @override
  String get siteReportsTitle => 'تقارير الموقع';

  @override
  String get siteReportsEmpty => 'لم يتم إرسال أي تقارير موقع.';

  @override
  String get siteReportCreate => 'إنشاء تقرير موقع';

  @override
  String get siteReportDate => 'تاريخ التقرير';

  @override
  String get siteReportWorkSummary => 'ملخص الأعمال المنفذة';

  @override
  String get siteReportWorkCompleted => 'الأعمال المنجزة';

  @override
  String get siteReportWeather => 'حالة الطقس';

  @override
  String get siteReportWorkersCount => 'عدد العمال';

  @override
  String get siteReportEquipment => 'المعدات المستخدمة';

  @override
  String get siteReportDelays => 'التأخيرات أو القيود';

  @override
  String get siteReportSubmit => 'إرسال التقرير';

  @override
  String get siteReportDraftSaved => 'تم حفظ مسودة التقرير.';

  @override
  String get siteReportSubmitted => 'تم إرسال تقرير الموقع.';

  @override
  String get documentsTitle => 'المستندات';

  @override
  String get documentsEmpty => 'لا توجد مستندات متاحة.';

  @override
  String get messagesTitle => 'الرسائل';

  @override
  String messagesTitleWithProject(String project) {
    return 'الرسائل · $project';
  }

  @override
  String get messagesNew => 'جديدة';

  @override
  String get messagesLoading => 'جارٍ تحميل المحادثات';

  @override
  String get messagesEmptyTitle => 'لا توجد محادثات بعد';

  @override
  String get messagesEmptyBody =>
      'ستظهر هنا الرسائل التي ترسلها أو تستقبلها في هذا المشروع.';

  @override
  String get messagesNoMessages => 'لا توجد رسائل';

  @override
  String get messagesNewConversation => 'محادثة مشروع جديدة';

  @override
  String get messagesAnnouncement => 'إعلان للمشروع أو الفريق';

  @override
  String get messagesPeople => 'أشخاص';

  @override
  String get messagesTeamGroup => 'فريق / مجموعة';

  @override
  String get messagesRecipientGroup => 'مجموعة المستلمين';

  @override
  String messagesGroupWithCount(String label, int count) {
    return '$label ($count)';
  }

  @override
  String get messagesTitleOptional => 'العنوان (اختياري)';

  @override
  String get messagesMessage => 'الرسالة';

  @override
  String get messagesSend => 'إرسال';

  @override
  String get messagesProjectDiscussion => 'نقاش المشروع';

  @override
  String get conversationTitle => 'محادثة المشروع';

  @override
  String conversationContextTitle(String context) {
    return 'نقاش $context';
  }

  @override
  String get conversationWriteMessage => 'اكتب رسالة للمشروع…';

  @override
  String get conversationLoading => 'جارٍ تحميل المحادثة';

  @override
  String get conversationTitleShort => 'المحادثة';

  @override
  String get conversationStartTitle => 'ابدأ النقاش';

  @override
  String get conversationStartBody => 'أرسل أول رسالة في سياق المشروع.';

  @override
  String communicationForwardedFrom(String sender) {
    return 'مُعاد توجيهها من $sender';
  }

  @override
  String get entityIssue => 'ملاحظة';

  @override
  String get entityTask => 'مهمة';

  @override
  String get entitySiteReport => 'تقرير موقع';

  @override
  String get entityDesignChange => 'تعديل تصميمي';

  @override
  String get entityDocument => 'مستند';

  @override
  String get notificationsTitle => 'الإشعارات';

  @override
  String notificationsUnreadCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count رسالة غير مقروءة',
      few: '$count رسائل غير مقروءة',
      two: 'رسالتان غير مقروءتين',
      one: 'رسالة واحدة غير مقروءة',
    );
    return '$_temp0';
  }

  @override
  String get notificationsReadAll => 'تعليم الكل كمقروء';

  @override
  String get notificationsFilterUnread => 'غير المقروءة';

  @override
  String get notificationsLoading => 'جارٍ تحميل الإشعارات';

  @override
  String get notificationsEmptyUnreadTitle => 'لا توجد إشعارات غير مقروءة';

  @override
  String get notificationsEmptyUnreadBody =>
      'ستظهر هنا الإشعارات الجديدة غير المقروءة.';

  @override
  String get notificationsEmptyTitle => 'لا يوجد جديد';

  @override
  String get notificationsEmptyBody =>
      'ستظهر هنا تحديثات المشروع ونشاط الفريق.';

  @override
  String get notificationReminder => 'تذكير';

  @override
  String get notificationFallbackTitle => 'إشعار';

  @override
  String get notificationDetailTitle => 'تفاصيل الإشعار';

  @override
  String get notificationDetailMustOpen =>
      'يجب فتح هذا الإشعار من قائمة الإشعارات.';

  @override
  String get notificationOpenTask => 'فتح المهمة';

  @override
  String get notificationOpenMessages => 'فتح الرسائل';

  @override
  String get notificationOpenIssues => 'فتح الملاحظات';

  @override
  String get notificationOpenReviews => 'فتح المراجعات';

  @override
  String get notificationOpenReports => 'فتح التقارير';

  @override
  String get notificationOpenProject => 'فتح المشروع';

  @override
  String get notifTaskDueTomorrowTitle => 'مهمة مستحقة غدًا';

  @override
  String notifTaskDueTomorrowBody(String name) {
    return '$name مستحقة غدًا.';
  }

  @override
  String get notifTaskDueTodayTitle => 'مهمة مستحقة اليوم';

  @override
  String notifTaskDueTodayBody(String name) {
    return '$name مستحقة اليوم.';
  }

  @override
  String get notifTaskOverdueTitle => 'مهمة متأخرة';

  @override
  String notifTaskOverdueBody(String name) {
    return '$name متأخرة عن موعدها.';
  }

  @override
  String notifTaskOverdueSeveralBody(String name) {
    return '$name متأخرة منذ عدة أيام.';
  }

  @override
  String notifTaskOverdueWeekBody(String name) {
    return '$name متأخرة منذ أكثر من أسبوع.';
  }

  @override
  String get notifSiteReportAwaitingTitle => 'تقرير موقع بانتظار تحققك';

  @override
  String notifSiteReportAwaitingBody(String project) {
    return 'تم تقديم تقرير موقع لمشروع $project.';
  }

  @override
  String get notifSiteReportVerifiedTitle => 'تم التحقق من تقرير الموقع';

  @override
  String notifSiteReportVerifiedBody(String date, String reviewer) {
    return 'تم التحقق من تقرير الموقع بتاريخ $date بواسطة $reviewer.';
  }

  @override
  String get notifSiteReportRejectedTitle => 'تم رفض تقرير الموقع';

  @override
  String notifSiteReportRejectedBody(
    String date,
    String reviewer,
    String reason,
  ) {
    return 'تم رفض تقرير الموقع بتاريخ $date بواسطة $reviewer: $reason';
  }

  @override
  String notifReminderWaitingTitle(String label) {
    return 'تذكير بالرد: $label';
  }

  @override
  String notifReminderWaitingBody(String target, String sequence) {
    return 'لا يزال هذا العنصر ($target) بانتظار إجراء. التذكير $sequence.';
  }

  @override
  String notifReminderEscalationTitle(String label) {
    return 'تصعيد: $label';
  }

  @override
  String notifReminderEscalationBody(String target) {
    return 'انتظر هذا العنصر ($target) وقتًا طويلًا وتم تصعيده.';
  }

  @override
  String get notifStepUpRequestedTitle => 'تم طلب رمز تحقق';

  @override
  String notifStepUpRequestedBody(String action) {
    return 'تم طلب رمز تحقق لتأكيد: $action. إذا لم تكن أنت، غيّر كلمة المرور فورًا.';
  }

  @override
  String get profileAccountInformation => 'معلومات الحساب';

  @override
  String get profileEmail => 'البريد الإلكتروني';

  @override
  String get profilePhone => 'الهاتف';

  @override
  String get profileOrganization => 'الجهة';

  @override
  String get profileAccountStatus => 'حالة الحساب';

  @override
  String get profileLanguage => 'اللغة';

  @override
  String get profileLanguageBody => 'اختر لغة التطبيق أو اتبع إعدادات جهازك.';

  @override
  String get languageSystem => 'لغة الجهاز';

  @override
  String get languageEnglish => 'English';

  @override
  String get languageArabic => 'العربية';

  @override
  String get profileSecurity => 'الأمان';

  @override
  String get profileSecureSession => 'جلسة جوال آمنة';

  @override
  String get profileSecureSessionBody =>
      'تُحفظ رموز المصادقة في تخزين مشفَّر على الجهاز.';

  @override
  String get reviewsPendingTitle => 'المراجعات المعلقة';

  @override
  String get reviewsTitle => 'المراجعات';

  @override
  String get reviewsSelectProjectBody =>
      'اختر مشروعًا قبل فتح مراجعات الاستشاري.';

  @override
  String get reviewsLoading => 'جارٍ تحميل طلبات المراجعة';

  @override
  String get reviewsEmptyTitle => 'لا يوجد ما ينتظر المراجعة';

  @override
  String get reviewsEmptyBody => 'ستظهر هنا الطلبات الجديدة المطابقة لتخصصك.';

  @override
  String get reviewCritical => 'حرجة';

  @override
  String get reviewOverdue => 'متأخرة';

  @override
  String reviewAttempt(String number) {
    return 'المحاولة $number';
  }

  @override
  String reviewSubmittedAt(String date) {
    return 'أُرسلت $date';
  }

  @override
  String reviewEvidenceCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count إثباتًا',
      few: '$count إثباتات',
      two: 'إثباتان',
      one: 'إثبات واحد',
    );
    return '$_temp0';
  }

  @override
  String get reviewSubmissionFallback => 'طلب مراجعة';

  @override
  String get reviewSubmissionTitle => 'مراجعة الطلب';

  @override
  String get reviewLoadingSubmission => 'جارٍ تحميل الطلب والإثباتات';

  @override
  String get reviewUnableToOpen => 'تعذّر فتح المراجعة';

  @override
  String get reviewNotFound => 'لم يتم العثور على طلب المراجعة.';

  @override
  String get reviewTaskReview => 'مراجعة مهمة';

  @override
  String get reviewTaskAndSubmission => 'المهمة والطلب';

  @override
  String get reviewSubmission => 'الطلب';

  @override
  String get reviewCompletionNote => 'ملاحظة الإنجاز';

  @override
  String reviewSubmittedEvidence(int count) {
    return 'الإثباتات المُرسلة ($count)';
  }

  @override
  String get reviewNoEvidence => 'لم تُرفق أي إثباتات بهذا الطلب.';

  @override
  String get reviewAttachment => 'مرفق';

  @override
  String get reviewDependencyImpact => 'أثر الاعتماديات';

  @override
  String reviewPredecessors(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count مهمة سابقة',
      few: '$count مهام سابقة',
      two: 'مهمتان سابقتان',
      one: 'مهمة سابقة واحدة',
    );
    return '$_temp0';
  }

  @override
  String reviewDependentTasks(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count مهمة تابعة',
      few: '$count مهام تابعة',
      two: 'مهمتان تابعتان',
      one: 'مهمة تابعة واحدة',
    );
    return '$_temp0';
  }

  @override
  String get reviewGatingWork => 'الاعتماد يحجب حاليًا الأعمال اللاحقة.';

  @override
  String get reviewStart => 'بدء المراجعة';

  @override
  String get reviewApproveSubmission => 'اعتماد الطلب';

  @override
  String get reviewRequestClarification => 'طلب توضيح';

  @override
  String get reviewRequestRework => 'طلب إعادة عمل';

  @override
  String get reviewStarted => 'بدأت المراجعة.';

  @override
  String get reviewApprovalHint =>
      'الاعتماد يجعل هذه المهمة مكتملة وقد يفتح الأعمال التابعة.';

  @override
  String get reviewRejectionReasonRequired => 'سبب الرفض *';

  @override
  String get reviewRequiredCorrections => 'التصحيحات المطلوبة *';

  @override
  String get reviewClarificationQuestion => 'سؤال التوضيح *';

  @override
  String get reviewComments => 'تعليقات المراجعة *';

  @override
  String get reviewNoteOptional => 'ملاحظة المراجعة (اختياري)';

  @override
  String get reviewApproved => 'تم اعتماد الطلب بنجاح.';

  @override
  String get reviewReworkRecorded => 'تم تسجيل طلب إعادة العمل.';

  @override
  String get reviewClarificationRequested => 'تم طلب التوضيح.';

  @override
  String get collabMyActions => 'الإجراءات المطلوبة مني';

  @override
  String get collabSelectProjectBody =>
      'اختر مشروعًا لعرض الإجراءات المسؤول عنها.';

  @override
  String get collabTabActions => 'الإجراءات';

  @override
  String get collabTabRequests => 'الطلبات';

  @override
  String get collabTabVisits => 'الزيارات';

  @override
  String get collabNewRequest => 'طلب جديد';

  @override
  String get collabSchedule => 'جدولة';

  @override
  String get collabOwnerRequest => 'طلب العميل / المالك';

  @override
  String get collabRequestHint => 'هذا الطلب لا يعدّل التصميم المعتمد.';

  @override
  String get collabSubmitForReview => 'إرسال للمراجعة الهندسية';

  @override
  String get collabRequestSubmitted =>
      'تم إرسال الطلب للمراجعة الهندسية البشرية.';

  @override
  String get collabScheduleVisit => 'جدولة زيارة موقع';

  @override
  String get collabSiteLocation => 'الموقع';

  @override
  String get collabStart => 'البداية';

  @override
  String get collabEnd => 'النهاية';

  @override
  String get collabReviewAndSchedule => 'مراجعة وجدولة';

  @override
  String get collabVisitScheduled => 'تمت جدولة زيارة الموقع.';

  @override
  String get collabActionCenter => 'مركز الإجراءات';

  @override
  String get collabWhatNeedsAttention => 'ما الذي يتطلب انتباهي الآن؟';

  @override
  String get collabAiAdvisory => 'الذكاء الاصطناعي استشاري';

  @override
  String get collabAiAdvisoryBody =>
      'تنبيهات الذكاء الاصطناعي تتطلب مراجعة بشرية وتحتفظ بمصادرها من المشروع.';

  @override
  String get collabRequestsTitle => 'الطلبات';

  @override
  String get collabNoRequests => 'لا توجد طلبات مالك نشطة';

  @override
  String get collabNoRequestsBody =>
      'ستظهر هنا طلبات العميل الجديدة والردود الهندسية.';

  @override
  String get collabScheduleTitle => 'الجدول';

  @override
  String get collabNoVisits => 'لا توجد زيارات موقع مجدولة';

  @override
  String get collabNoVisitsBody =>
      'ستظهر هنا الزيارات في المشاريع المُسندة إليك.';

  @override
  String get collabAcknowledge => 'الإقرار بالإجراء';

  @override
  String get collabNeedsMyResponse => 'يتطلب ردي';

  @override
  String get collabOwnerRequests => 'طلبات العميل';

  @override
  String get collabRequiresActionNotifications => 'إشعارات تتطلب إجراءً';

  @override
  String get collabUpcomingSiteVisits => 'زيارات الموقع القادمة';

  @override
  String get collabAiAlertsRequiringReview => 'تنبيهات ذكاء اصطناعي للمراجعة';

  @override
  String get collabTasksUnderReview => 'مهام قيد المراجعة';

  @override
  String get collabVisitTypeRoutine => 'تفتيش دوري';

  @override
  String get collabVisitTypeQuality => 'تدقيق جودة';

  @override
  String get collabVisitTypeSafety => 'تفتيش سلامة';

  @override
  String get collabVisitTypeProgress => 'مراجعة تقدّم';

  @override
  String get collabProjectSite => 'موقع المشروع';

  @override
  String get evidenceMyTitle => 'إثباتاتي الميدانية';

  @override
  String get evidenceTitle => 'الإثباتات';

  @override
  String get evidenceLoading => 'جارٍ تحميل الإثباتات الميدانية';

  @override
  String get evidenceEmpty => 'لم يتم إرسال أي إثباتات ميدانية بعد.';

  @override
  String get evidenceNewTitle => 'تحديث ميداني جديد';

  @override
  String get evidenceCorrectedTitle => 'إثبات مُصحَّح';

  @override
  String get evidenceDocumentWork => 'وثّق الأعمال المنجزة في الموقع';

  @override
  String get evidenceVerifyHint =>
      'سيتحقق مهندسك من هذا الإثبات. وهو لا يغيّر نسبة الإنجاز الرسمية للمهمة.';

  @override
  String get evidenceWhatWork => 'ما العمل الذي تم إنجازه؟';

  @override
  String get evidenceHint => 'ملاحظة موقع قصيرة وعملية…';

  @override
  String get evidenceTakePhoto => 'التقاط صورة';

  @override
  String get evidenceAddPhotos => 'إضافة صور';

  @override
  String get evidenceCategoryOptional => 'التصنيف (اختياري)';

  @override
  String get evidenceCategoryHint =>
      'اختر الوسوم المناسبة. يمكن لمهندسك تصحيحها.';

  @override
  String get evidenceViewOptional => 'الجهة (اختياري)';

  @override
  String get viewFront => 'أمامية';

  @override
  String get viewBack => 'خلفية';

  @override
  String get viewLeft => 'يسار';

  @override
  String get viewRight => 'يمين';

  @override
  String get viewTop => 'علوية';

  @override
  String get viewDetail => 'تفصيلية';

  @override
  String get viewOther => 'أخرى';

  @override
  String get evidenceRemovePhoto => 'إزالة الصورة';

  @override
  String get evidenceSubmit => 'إرسال الإثبات';

  @override
  String get evidenceSent => 'تم إرسال الإثبات الميداني إلى مهندسك.';

  @override
  String evidencePhotoCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count صورة',
      few: '$count صور',
      two: 'صورتان',
      one: 'صورة واحدة',
    );
    return '$_temp0';
  }

  @override
  String get evidenceSubmitCorrected => 'إرسال إثبات مُصحَّح';

  @override
  String get evidencePhotoFallback => 'صورة ميدانية';

  @override
  String get ifcTitle => 'تحليلات IFC';

  @override
  String get ifcSelectProjectBody => 'اختر مشروعًا قبل فتح تحليلات IFC.';

  @override
  String get ifcLoading => 'جارٍ تحميل نماذج IFC';

  @override
  String get ifcModelsTitle => 'نماذج IFC';

  @override
  String get ifcEmptyTitle => 'لا توجد نماذج IFC';

  @override
  String get ifcEmptyBody =>
      'يمكن لمدير المشروع إنشاء مجموعة نماذج ورفع أول إصدار IFC من مساحة العمل على الويب.';

  @override
  String get ifcReadOnlyHint =>
      'عرض ميداني للقراءة فقط لبيانات النموذج المعتمدة وحالة المعالجة.';

  @override
  String get ifcFederatedModel => 'نموذج موحّد';

  @override
  String get ifcNoVersions => 'لم يتم رفع أي إصدارات';

  @override
  String ifcVersionLine(String number, String title) {
    return 'الإصدار $number · $title';
  }

  @override
  String ifcElementCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count عنصرًا',
      few: '$count عناصر',
      two: 'عنصران',
      one: 'عنصر واحد',
    );
    return '$_temp0';
  }

  @override
  String get ifcActive => 'نشط';

  @override
  String get ifcUntitled => 'بدون عنوان';

  @override
  String get contactAdminTitle => 'التواصل مع مدير النظام';

  @override
  String get contactAdminUnavailable => 'تفاصيل الدعم غير متاحة';

  @override
  String get contactAdminUnavailableBody =>
      'يُرجى التواصل مع مكتب المشروع أو المحاولة مجددًا عند توفر الاتصال.';

  @override
  String get contactAdminCompanySupport => 'دعم الشركة';

  @override
  String get contactAdminBody =>
      'تواصل مع مدير النظام للحصول على صلاحية الحساب والدعم.';

  @override
  String get contactAdminPhone => 'هاتف الدعم';

  @override
  String get contactAdminEmail => 'بريد الدعم';

  @override
  String get contactAdminOffice => 'المكتب';

  @override
  String get recordStop => 'إيقاف التسجيل';

  @override
  String get recordResume => 'استئناف التسجيل';

  @override
  String get recordProcessing => 'جارٍ المعالجة…';

  @override
  String get recordPlay => 'تشغيل التسجيل';

  @override
  String get recordPausePlayback => 'إيقاف التشغيل مؤقتًا';

  @override
  String get recordTryAgain => 'حاول مرة أخرى';

  @override
  String get recordCapture => 'سجّل تحديثًا ميدانيًا دون استخدام اليدين';

  @override
  String get recordReviewHint => 'تراجع كل اقتراح قبل الإرسال';

  @override
  String get diagnosticsDisabled =>
      'أدوات تشخيص الذكاء الاصطناعي معطّلة في هذه النسخة.';

  @override
  String get diagnosticsTitle => 'تشخيص الذكاء الاصطناعي (تطوير)';

  @override
  String get diagnosticsBody =>
      'تفحص هذه الشاشة الإعدادات والأذونات فقط. ولا تختلق أبدًا تسجيلًا أو رفعًا أو تفريغًا أو نتيجة ذكاء اصطناعي.';

  @override
  String get diagnosticsRerun => 'إعادة تشغيل الفحوصات';

  @override
  String get voiceTitle => 'المساعد الصوتي للإنشاءات';

  @override
  String get voiceSpeakNaturally =>
      'تحدث بشكل طبيعي عن الأعمال أو الملاحظات أو تحديثات المشروع.';

  @override
  String get voiceTaskContext => 'سياق المهمة (مستحسن)';

  @override
  String get voiceLetAiSuggest => 'دع الذكاء الاصطناعي يقترح مهمة مُسندة';

  @override
  String get voiceSubmitForAnalysis => 'إرسال للتحليل بالذكاء الاصطناعي';

  @override
  String get voicePrivacyNote =>
      'يُستخدم تسجيلك لإعداد إجراء المشروع هذا ويُحفظ وفق سياسة بيانات المشروع.';

  @override
  String get voiceRetryAudio => 'إعادة محاولة التسجيل المحفوظ';

  @override
  String get voiceReportSent => 'تم إرسال التقرير';

  @override
  String get voiceActionCompleted => 'تم تنفيذ الإجراء';

  @override
  String get voiceReportSentBody =>
      'تم إرسال تقريرك إلى المهندس المسؤول للمراجعة.';

  @override
  String voiceActionsSucceeded(int succeeded, int total) {
    return 'نجح $succeeded من $total من الإجراءات المحددة.';
  }

  @override
  String get voicePause => 'إيقاف مؤقت';

  @override
  String get voiceDelete => 'حذف';

  @override
  String get voiceRecordAgain => 'تسجيل مرة أخرى';

  @override
  String get voiceUploading => 'جارٍ رفع التسجيل بشكل آمن…';

  @override
  String get voiceTranscribing => 'جارٍ تفريغ الكلام…';

  @override
  String get voiceLiveWaveform => 'الشكل الموجي للتسجيل المباشر';

  @override
  String get voiceRecordedWaveform => 'الشكل الموجي للصوت المسجَّل';

  @override
  String get voiceReviewUnderstood => 'راجع ما فهمته';

  @override
  String get voiceChooseActions => 'اختر وعدّل الإجراءات التي تريد تأكيدها.';

  @override
  String get voiceAiSummary => 'ملخص الذكاء الاصطناعي';

  @override
  String get voiceSelectTask => 'اختر مهمة';

  @override
  String get voiceWorkCompleted => 'الأعمال المنجزة';

  @override
  String get voiceProblems => 'المشكلات / المعوّقات';

  @override
  String get voiceSuggestedActions => 'الإجراءات المقترحة';

  @override
  String get voiceTranscript => 'النص المفرّغ';

  @override
  String get voiceTask => 'المهمة';

  @override
  String get voiceProgressLabel => 'نسبة الإنجاز';

  @override
  String voiceProgressMentioned(String percent) {
    return 'ذُكرت $percent٪ — غير معتمدة بعد';
  }

  @override
  String get voiceIntentUpdateProgress => 'تحديث نسبة إنجاز المهمة';

  @override
  String get voiceIntentReportIssue => 'تسجيل ملاحظة';

  @override
  String get voiceIntentSendMessage => 'إرسال رسالة';

  @override
  String get voiceIntentSubmitReport => 'إرسال تقرير موقع';

  @override
  String get voiceIntentRequestClarification => 'طلب توضيح';

  @override
  String get voiceNoSafeAction => 'لم يُقترح أي إجراء آمن قابل للتنفيذ.';

  @override
  String voiceConfidence(int percent) {
    return 'درجة الثقة $percent٪';
  }

  @override
  String get voiceConfirmedProgress => 'نسبة الإنجاز المؤكدة (٠–١٠٠)';

  @override
  String get voiceReviewEditValue => 'راجع القيمة أو عدّلها';

  @override
  String get voiceReviewedAffected =>
      'راجعت المهمة المتأثرة والمستلمين وأثر سير العمل.';

  @override
  String get voiceDiscard => 'تجاهل';

  @override
  String get voiceConfirmSelected => 'تأكيد المحدد';

  @override
  String get voiceMicPermissionRequired => 'إذن الميكروفون مطلوب.';

  @override
  String get voiceRecordBeforeTranscribe => 'سجّل صوتًا قبل التفريغ.';

  @override
  String get voiceRecordBeforeAnalysis => 'سجّل صوتًا قبل التحليل.';

  @override
  String get voiceNoAnalysisRetry => 'لا يوجد تحليل لإعادة المحاولة.';

  @override
  String get voiceNoAnalysisConfirm => 'لا يوجد تحليل للتأكيد.';

  @override
  String get voiceNoAnalysisClarify => 'لا يوجد تحليل للتوضيح.';

  @override
  String get voiceActionUnavailable => 'لم يعد الإجراء الصوتي متاحًا.';

  @override
  String get navVoiceAssistant => 'المساعد الصوتي';

  @override
  String get shareActionsTitle => 'الإجراءات';

  @override
  String get shareForward => 'إعادة توجيه';

  @override
  String get shareForwardHint => 'أرسِل هذا إلى شخص آخر.';

  @override
  String get shareAskOpinion => 'طلب رأي';

  @override
  String get shareAskOpinionHint => 'اطلب رأي زميل. لا يتم نقل المسؤولية.';

  @override
  String get shareShare => 'مشاركة';

  @override
  String get shareShareHint => 'أرسل نسخة داخل محادثة.';

  @override
  String get shareRecipients => 'المستلمون';

  @override
  String get shareNoteLabel => 'ملاحظة (اختياري)';

  @override
  String get shareSend => 'إرسال';

  @override
  String get shareSending => 'جارٍ الإرسال';

  @override
  String get shareLoadingRecipients => 'جارٍ تحميل المستلمين';

  @override
  String get shareNoRecipientsTitle => 'لا يوجد مستلمون';

  @override
  String get shareNoRecipientsBody =>
      'لا يوجد في هذا المشروع من يمكنك إرسال هذا إليه.';

  @override
  String get shareSelectRecipient => 'اختر مستلمًا واحدًا على الأقل.';

  @override
  String get shareSentForward => 'تمت إعادة توجيه الرسالة.';

  @override
  String get shareSentOpinion => 'تم طلب الرأي.';

  @override
  String get shareSentShare => 'تمت المشاركة.';

  @override
  String shareSelectedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: 'تم اختيار $count شخصًا',
      few: 'تم اختيار $count أشخاص',
      two: 'تم اختيار شخصين',
      one: 'تم اختيار شخص واحد',
      zero: 'لم يتم اختيار أحد',
    );
    return '$_temp0';
  }

  @override
  String get shareOpinionPrefill => 'هل يمكنك إبداء رأيك في هذا؟';

  @override
  String get shareOpen => 'فتح';

  @override
  String get dashboardTodayTitle => 'اليوم';

  @override
  String get dashboardTodayBody => 'ما يحتاج إليك في الموقع الآن.';

  @override
  String get dashboardAllClearTitle => 'لا شيء يحتاج إليك الآن';

  @override
  String get dashboardAllClearBody =>
      'لا يوجد عمل متأخر أو متوقف أو بانتظار مراجعة في هذا المشروع.';

  @override
  String get dashboardOpenProfile => 'ملفك الشخصي';

  @override
  String get dashboardActivityUnavailable => 'النشاط الأخير غير متاح.';

  @override
  String get voiceClarificationTitle => 'معلومة إضافية مطلوبة';

  @override
  String get voiceClarificationAnswerLabel => 'الإجابة';

  @override
  String get voiceClarificationAnswerHint => 'اكتب إجابة قصيرة ومحددة';

  @override
  String get voiceContinue => 'متابعة';

  @override
  String get voiceUnavailableTitle => 'المساعد الصوتي غير متاح';

  @override
  String get voiceUnavailableBody =>
      'المساعد الصوتي مخصص لأدوار المشروع والموقع. تتم الإدارة عبر تطبيق الويب.';

  @override
  String get activityGeneric => 'نشاط في المشروع';

  @override
  String get activityTaskCreated => 'تم إنشاء مهمة';

  @override
  String get activityTaskStarted => 'تم بدء المهمة';

  @override
  String get activityTaskResumed => 'تم استئناف المهمة';

  @override
  String get activityProgressUpdated => 'تم تحديث نسبة الإنجاز';

  @override
  String get activitySubmitted => 'تم الإرسال للمراجعة';

  @override
  String get activityApproved => 'تمت الموافقة';

  @override
  String get activityReviewStarted => 'بدأت المراجعة';

  @override
  String get activityReworkRequested => 'طُلبت إعادة العمل';

  @override
  String get activityReworkStarted => 'بدأت إعادة العمل';

  @override
  String get activityClarificationRequested => 'طُلب توضيح';

  @override
  String get activityClarificationResponded => 'تمت الإجابة على التوضيح';

  @override
  String get activityCommentAdded => 'تمت إضافة تعليق';

  @override
  String get activityWorkUpdateAdded => 'تمت إضافة تحديث عمل';

  @override
  String get activityBlockerReported => 'تم الإبلاغ عن معوّق';

  @override
  String get activityDocumentUploaded => 'تم رفع مستند';

  @override
  String get activityAttachmentUploaded => 'تم رفع مرفق';

  @override
  String get activitySiteReportVerified => 'تم اعتماد تقرير الموقع';

  @override
  String get activitySiteVisitScheduled => 'تمت جدولة زيارة موقع';

  @override
  String get activityOwnerRequestSubmitted => 'تم إرسال طلب المالك';

  @override
  String get activityScheduleRecalculated => 'تمت إعادة حساب الجدول الزمني';

  @override
  String get activityRemindersDispatched => 'تم إرسال التذكيرات';

  @override
  String get activityMemberAssigned => 'تم تعيين عضو في الفريق';

  @override
  String get activityModelVersionUploaded => 'تم رفع إصدار من النموذج';

  @override
  String get activityVoiceUpdate => 'تم تسجيل تحديث صوتي';

  @override
  String get activityEvidenceVerified => 'تم اعتماد إثبات ميداني';

  @override
  String get activityEvidenceRejected => 'تمت إعادة إثبات ميداني';

  @override
  String get activityEvidenceSubmitted => 'تم إرسال إثبات ميداني';

  @override
  String get activityCreated => 'تم الإنشاء';

  @override
  String get activityUpdated => 'تم التحديث';

  @override
  String get commonSeverity => 'الخطورة';

  @override
  String get commonCreated => 'تاريخ الإنشاء';

  @override
  String get commonDue => 'تاريخ الاستحقاق';

  @override
  String get commonNoDescription => 'لا يوجد وصف.';

  @override
  String get commonMoreActions => 'إجراءات أخرى';

  @override
  String get navDesignChanges => 'تغييرات التصميم';

  @override
  String get designChangesEmpty =>
      'لم يتم رفع أي تغييرات تصميم في هذا المشروع.';

  @override
  String get taskDependencyUnnamed => 'مهمة معيقة';

  @override
  String get voiceOutcomeSuccessTitle => 'تم تنفيذ الإجراءات بنجاح';

  @override
  String get voiceOutcomePartialTitle => 'تم تنفيذ جزء من الإجراءات';

  @override
  String get voiceOutcomeFailureTitle => 'لم يتم تنفيذ أي إجراء';

  @override
  String get voiceOutcomeNothingTitle => 'لا يوجد إجراء للتنفيذ';

  @override
  String get voiceOutcomeNothingBody =>
      'تم فهم الملاحظة، لكنها لا تتطلب أي تغيير في النظام.';

  @override
  String get voiceOutcomeReason => 'السبب';

  @override
  String get voiceOutcomeNotExecuted => 'لم يتم التنفيذ';

  @override
  String get voiceOutcomeExecuted => 'تم';

  @override
  String get voiceOutcomeRejectedFields =>
      'رفض النظام بعض البيانات التي أنتجها المساعد لهذا الإجراء.';

  @override
  String get voiceOutcomeGenericFailure => 'تعذّر تنفيذ هذا الإجراء.';
}
