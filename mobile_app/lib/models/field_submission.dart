class PhotoCategory {
  const PhotoCategory({
    required this.id,
    required this.name,
    required this.code,
    required this.isSystem,
    required this.active,
  });
  final String id;
  final String name;
  final String code;
  final bool isSystem;
  final bool active;

  factory PhotoCategory.fromJson(Map<String, dynamic> json) => PhotoCategory(
    id: '${json['id']}',
    name: json['name'] as String? ?? '',
    code: json['code'] as String? ?? '',
    isSystem: json['isSystem'] as bool? ?? false,
    active: json['active'] as bool? ?? true,
  );
}

class FieldEvidencePhoto {
  const FieldEvidencePhoto({
    required this.id,
    required this.fileUrl,
    required this.filename,
    this.direction,
    this.categories = const [],
  });
  final String id;
  final String fileUrl;
  final String filename;
  final String? direction;
  final List<PhotoCategory> categories;

  factory FieldEvidencePhoto.fromJson(Map<String, dynamic> json) {
    final attachment = json['attachment'] as Map<String, dynamic>? ?? const {};
    return FieldEvidencePhoto(
      id: '${json['id']}',
      fileUrl: attachment['fileUrl'] as String? ?? '',
      // See the note in `TaskDependency`: a model must not carry copy.
      filename: attachment['originalFilename'] as String? ?? '',
      direction: json['direction'] as String?,
      categories: (json['categories'] as List? ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(PhotoCategory.fromJson)
          .toList(),
    );
  }
}

class FieldSubmission {
  const FieldSubmission({
    required this.id,
    required this.taskId,
    required this.status,
    required this.createdAt,
    required this.photos,
    this.description,
    this.reviewComment,
    this.resubmissionOfId,
  });
  final String id;
  final String taskId;
  final String status;
  final DateTime createdAt;
  final List<FieldEvidencePhoto> photos;
  final String? description;
  final String? reviewComment;
  final String? resubmissionOfId;

  factory FieldSubmission.fromJson(Map<String, dynamic> json) => FieldSubmission(
    id: '${json['id']}',
    taskId: '${json['taskId']}',
    status: json['status'] as String? ?? 'SUBMITTED',
    createdAt: DateTime.tryParse(json['createdAt'] as String? ?? '') ?? DateTime.now(),
    photos: (json['photos'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(FieldEvidencePhoto.fromJson)
        .toList(),
    description: json['description'] as String?,
    reviewComment: json['reviewComment'] as String?,
    resubmissionOfId: json['resubmissionOfId'] as String?,
  );
}
