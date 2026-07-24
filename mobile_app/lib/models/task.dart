class TaskDependency {
  const TaskDependency({
    required this.id,
    required this.name,
    required this.status,
  });
  final String id;
  final String name;
  final String status;
  bool get isComplete => status == 'done';

  factory TaskDependency.fromJson(Map<String, dynamic> json) => TaskDependency(
    id: '${json['dependsOnTaskId']}',
    name: json['dependsOnTaskName'] as String? ?? 'Blocking task',
    status: json['dependsOnTaskStatus'] as String? ?? 'todo',
  );
}

class ProjectTask {
  const ProjectTask({
    required this.id,
    required this.projectId,
    required this.code,
    required this.name,
    required this.status,
    required this.priority,
    required this.progress,
    required this.assigneeIds,
    required this.dependencies,
    this.discipline,
    this.dueDate,
    this.reviewStatus,
    this.isCritical = false,
  });

  final String id;
  final String projectId;
  final String code;
  final String name;
  final String status;
  final String priority;
  final double progress;
  final List<String> assigneeIds;
  final List<TaskDependency> dependencies;
  final String? discipline;
  final DateTime? dueDate;
  final String? reviewStatus;
  final bool isCritical;

  bool get hasIncompleteDependencies =>
      dependencies.any((item) => !item.isComplete);
  bool get isOverdue =>
      dueDate != null && dueDate!.isBefore(DateTime.now()) && status != 'done';
  int get daysOverdue =>
      isOverdue ? DateTime.now().difference(dueDate!).inDays : 0;
  bool get canStart => status == 'todo' && !hasIncompleteDependencies;
  bool canEdit(String userId) =>
      assigneeIds.contains(userId) &&
      !{'done', 'under_review', 'cancelled'}.contains(status);

  factory ProjectTask.fromJson(Map<String, dynamic> json) => ProjectTask(
    id: '${json['id']}',
    projectId: '${json['projectId']}',
    code: json['taskCode'] as String? ?? '',
    name: json['name'] as String? ?? '',
    status: json['status'] as String? ?? 'todo',
    priority: json['priority'] as String? ?? 'medium',
    progress: (json['progressPercentage'] as num?)?.toDouble() ?? 0,
    assigneeIds: (json['assigneeIds'] as List? ?? const [])
        .map((e) => '$e')
        .toList(),
    dependencies: (json['dependencies'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(TaskDependency.fromJson)
        .toList(),
    discipline: json['discipline'] as String?,
    dueDate: DateTime.tryParse(json['plannedEndDate'] as String? ?? ''),
    reviewStatus: json['reviewStatus'] as String?,
    isCritical: json['isCriticalPath'] as bool? ?? false,
  );
}
