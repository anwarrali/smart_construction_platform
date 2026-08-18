import '../../models/user.dart';
import '../constants/role_constants.dart';

/// Who may use the Voice Assistant.
///
/// Voice is a *general system interaction layer*, not a feature of one
/// engineering discipline. The previous build gated it on
/// `isSiteEngineer || isWorker`, which meant a Project Manager, an Architect,
/// an Electrical Engineer, a Consultant and an Owner all lost the fastest way
/// to record something from site — a product decision nobody made.
///
/// The rule is one line: **every normal system user except Admin.** Admin is
/// an administration console role; it has no site work to narrate, and the
/// mobile app is not an admin console.
///
/// This decides *visibility only*. Every action Voice ultimately proposes is
/// executed through the same authorized endpoints as the equivalent manual
/// action, so a role that may not update a task still cannot update it by
/// speaking — the backend refuses it exactly as it refuses the button.
bool canUseVoice(User? user) =>
    user != null && user.role != RoleConstants.admin;
