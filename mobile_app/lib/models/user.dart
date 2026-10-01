/// Who is signed in.
///
/// `orgRole` and `disciplines` are the configurable model the consulting
/// office maintains. Nothing on this class decides authorization: what
/// somebody may do is [Capabilities], resolved by the server.
class User {
  const User({
    required this.id,
    required this.fullName,
    required this.email,
    required this.status,
    this.phoneNumber,
    this.avatarUrl,
    this.organization,
    this.discipline,
    this.orgRoleId,
    this.orgRoleName,
    this.disciplines = const <String>[],
    this.isInternal = true,
  });

  final String id;
  final String fullName;
  final String email;
  final String status;
  final String? phoneNumber;
  final String? avatarUrl;
  final String? organization;
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

  /// What the office calls this person's role.
  String get roleLabel => orgRoleName ?? '';

  factory User.fromJson(Map<String, dynamic> json) {
    final profile = json['engineerProfile'] as Map<String, dynamic>?;
    final orgRole = json['orgRole'] as Map<String, dynamic>?;
    final rawDisciplines = json['disciplines'] as List<dynamic>?;
    return User(
      id: '${json['id']}',
      fullName: json['fullName'] as String? ?? '',
      email: json['email'] as String? ?? '',
      status: json['status'] as String? ?? '',
      phoneNumber: json['phoneNumber'] as String?,
      avatarUrl: json['avatarUrl'] as String?,
      organization: json['organization'] as String?,
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
