import '../core/constants/role_constants.dart';

/// Who is signed in.
///
/// `orgRole` and `disciplines` are the configurable model the consulting
/// office actually maintains; `role` is the retired enum, still sent by the
/// server while the column exists and kept here only so a screen has something
/// to render for an account the backfill has not reached.
///
/// Nothing on this class decides authorization. What somebody may do is
/// [Capabilities], resolved by the server; the getters below survive for
/// presentation — a heading, a caption, which tab opens first.
class User {
  const User({
    required this.id,
    required this.fullName,
    required this.email,
    required this.role,
    required this.status,
    this.phoneNumber,
    this.avatarUrl,
    this.organization,
    this.engineerAffiliation,
    this.discipline,
    this.orgRoleId,
    this.orgRoleName,
    this.disciplines = const <String>[],
    this.isInternal = true,
  });

  final String id;
  final String fullName;
  final String email;
  final String role;
  final String status;
  final String? phoneNumber;
  final String? avatarUrl;
  final String? organization;
  final String? engineerAffiliation;
  final String? discipline;

  /// The office's own role for this person, and its display name.
  final String? orgRoleId;
  final String? orgRoleName;

  /// Every discipline they practise. Several is normal — an office may combine
  /// Mechanical and Electrical — which the single `discipline` above could not
  /// express.
  final List<String> disciplines;

  /// Consulting-office staff, as opposed to somebody taking part from outside.
  final bool isInternal;

  bool get isActive => status == 'active';

  /// What the office calls this person, falling back to the retired role.
  String get roleLabel => orgRoleName ?? role;

  bool get isProjectManager => role == RoleConstants.projectManager;
  bool get isOwner => role == RoleConstants.owner;

  factory User.fromJson(Map<String, dynamic> json) {
    final profile = json['engineerProfile'] as Map<String, dynamic>?;
    final orgRole = json['orgRole'] as Map<String, dynamic>?;
    final rawDisciplines = json['disciplines'] as List<dynamic>?;
    return User(
      id: '${json['id']}',
      fullName: json['fullName'] as String? ?? '',
      email: json['email'] as String? ?? '',
      role: json['role'] as String? ?? '',
      status: json['status'] as String? ?? '',
      phoneNumber: json['phoneNumber'] as String?,
      avatarUrl: json['avatarUrl'] as String?,
      organization: json['organization'] as String?,
      engineerAffiliation: json['engineerAffiliation'] as String?,
      discipline: profile?['discipline'] as String?,
      orgRoleId: orgRole?['id'] as String?,
      orgRoleName: orgRole?['nameEn'] as String?,
      disciplines: rawDisciplines
              ?.whereType<Map<String, dynamic>>()
              .map((item) => '${item['code']}')
              .toList() ??
          const <String>[],
      isInternal: json['isInternal'] as bool? ?? true,
    );
  }
}
