import '../../models/task.dart';
import '../../models/user.dart';

class PermissionService {
  const PermissionService();
  bool canExecuteTask(User user, ProjectTask task) =>
      user.isSiteEngineer && task.canEdit(user.id);
  bool canStartTask(User user, ProjectTask task) =>
      canExecuteTask(user, task) && task.canStart;
  bool canReview(User user) => user.isConsultant;
  bool isReadOnly(User user) => user.isOwner;
}
