import '../../models/task.dart';
import '../../models/user.dart';
import 'capabilities.dart';

/// What the interface should offer, asked as capability rather than job title.
///
/// Every method used to read a role name — `user.isSiteEngineer`,
/// `user.isConsultant`, `user.isOwner`. That cannot survive a consulting
/// office configuring its own roles: an office that creates "Resident
/// Engineer" matches none of those getters, and two offices may give the same
/// title different authority.
///
/// Each answer now pairs a permission the server actually checks with the
/// data relationship that narrows it — being the assignee, in the task's case.
/// Permission first, relationship second, which is the same order
/// `app.services.work_scope` uses on the server.
///
/// **Presentation only.** These decide which controls to draw. The server
/// re-checks every operation when it is attempted, so a too-generous answer
/// here costs a wasted tap and a 403, never access.
class PermissionService {
  const PermissionService();

  /// May this person record progress on this task?
  ///
  /// `task.update_progress` is the capability; being the assignee is the
  /// narrowing. The retired version asked whether the account was a
  /// contractor-side engineer, which excluded every other kind of person an
  /// office might put on site.
  bool canExecuteTask(Capabilities capabilities, User user, ProjectTask task) =>
      capabilities.has('task.update_progress') && task.canEdit(user.id);

  bool canStartTask(Capabilities capabilities, User user, ProjectTask task) =>
      canExecuteTask(capabilities, user, task) && task.canStart;

  /// May this person review submitted work? Office authority, and
  /// `task.review` is `never_external`, so no external participant reaches it
  /// however their role is configured.
  bool canReview(Capabilities capabilities) => capabilities.has('task.review');

  /// Somebody who can look but not act. Expressed as the absence of the two
  /// capabilities that do anything on a task, rather than as "is the owner".
  bool isReadOnly(Capabilities capabilities) => !capabilities.hasAny(
        const ['task.update_progress', 'task.review', 'field_evidence.submit'],
      );

  /// May this person file field evidence? The Site Engineer's core act, held
  /// by whoever the office gave it to rather than by one job title.
  bool canSubmitFieldEvidence(Capabilities capabilities) =>
      capabilities.has('field_evidence.submit');
}
