class Project {
  const Project({
    required this.id,
    required this.name,
    required this.status,
    required this.completionPercentage,
    this.location,
    this.description,
    this.openIssueCount = 0,
  });

  final String id;
  final String name;
  final String status;
  final double completionPercentage;
  final String? location;
  final String? description;
  final int openIssueCount;

  factory Project.fromJson(Map<String, dynamic> json) => Project(
    id: '${json['id']}',
    name: json['name'] as String? ?? '',
    status: json['status'] as String? ?? 'planning',
    completionPercentage:
        (json['completionPercentage'] as num?)?.toDouble() ?? 0,
    location: json['location'] as String?,
    description: json['description'] as String?,
    openIssueCount: (json['openIssueCount'] as num?)?.toInt() ?? 0,
  );
}
