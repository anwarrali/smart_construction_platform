import 'capabilities.dart';

/// Who may use the Voice Assistant.
///
/// Voice is a *general system interaction layer*, not a feature of one
/// engineering discipline. An early build gated it on `isSiteEngineer ||
/// isWorker`, which meant a Project Manager, an Architect, an Electrical
/// Engineer, a Consultant and an Owner all lost the fastest way to record
/// something from site — a product decision nobody made. It was then widened
/// to "every role except Admin", which was right in spirit and still a role
/// name: an office that creates a role the list has never heard of gets an
/// arbitrary answer.
///
/// The rule is now what it always meant: **offer Voice to somebody who can
/// actually do something with it.** Every code below is one the assistant can
/// ultimately act on, and each is checked again on the server when the action
/// is confirmed. Somebody holding none of them would be shown a microphone
/// that could only ever answer questions, so it is not shown.
///
/// This decides *visibility only*. Every action Voice proposes is executed
/// through the same authorized endpoints as the equivalent manual action, so
/// somebody who may not update a task still cannot update it by speaking — the
/// backend refuses it exactly as it refuses the button.
const _voiceActionable = <String>[
  'task.update_progress',
  'task.add_note',
  'task.comment',
  'field_evidence.submit',
  'site_report.submit',
  'issue.create',
  'message.send',
];

bool canUseVoice(Capabilities capabilities) =>
    capabilities.hasAny(_voiceActionable);
