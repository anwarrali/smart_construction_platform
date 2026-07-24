import '../core/constants/role_constants.dart';

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

  bool get isActive => status == 'active';
  bool get isSiteEngineer =>
      role == RoleConstants.engineer &&
      engineerAffiliation == RoleConstants.mainContractor;
  bool get isConsultant =>
      role == RoleConstants.consultant ||
      (role == RoleConstants.engineer &&
          engineerAffiliation == RoleConstants.externalConsultant);
  bool get isProjectManager => role == RoleConstants.projectManager;
  bool get isOwner => role == RoleConstants.owner;
  bool get isWorker => role == RoleConstants.worker;

  factory User.fromJson(Map<String, dynamic> json) {
    final profile = json['engineerProfile'] as Map<String, dynamic>?;
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
    );
  }
}
