# AI command and consistency test matrix

This matrix defines the backend decision expected after authenticated context,
strict interpretation, editable draft, confirmation, deterministic rules, and
domain execution. “Proposal” never means the LLM may write data directly.

| Feature / intent | Role | Representative input | Expected intent / action | Approval / clarification | Expected persisted result | Notification / audit / finding | Automated evidence |
|---|---|---|---|---|---|---|---|
| Task creation | Project Manager | “Create a task to inspect basement waterproofing.” | `CREATE_TASK` | Detailed confirmation | Backlog/To Do task through normal task service | Task audit + domain event | Strict schema/risk test; normal task RBAC suite |
| Unauthorized task creation | Engineer/Worker | Same | Rejected | N/A | No task | Failed execution log | Voice RBAC tests |
| Task start | Assigned Engineer | “We started foundation reinforcement.” | `START_TASK` | Confirmation | To Do → In Progress | Task audit/notification/action version | Voice action tests |
| Task progress | Assigned Engineer | “Foundation reinforcement reached 75%.” | `UPDATE_TASK_PROGRESS` | Confirmation; consultant workflow unchanged | Progress 75; official state only if rules allow | Action version + audit + event validation | Voice schema/rules tests |
| Ambiguous task | Engineer | “Update the column progress to 70%.” with many matches | `NEEDS_CLARIFICATION` | Task selection required | No mutation | Clarification persisted | Task-matching/voice workflow tests |
| Vague progress | Engineer | “We are almost finished.” | `NEEDS_CLARIFICATION` | Percentage required | No mutation | Clarification persisted | Voice workflow tests |
| Measurement guard | Engineer | “Installed 70 meters of cable.” | Quantity, not progress | Clarify if action needed | No 70% mutation | Structured result/audit | Measurement tests |
| Completion requiring review | Engineer | “Rebar installation is finished.” | Progress 100 + submit review | Confirmation | Under Review; not Done | Consultant notification/audit | Voice + consultant policy tests |
| Worker completion claim | Worker | “We finished the reinforcement.” | `CREATE_FIELD_SUBMISSION` | Confirmation/evidence policy | Submitted unverified claim; task unchanged | Engineer notification + suspicious finding if task not started | Worker policy tests |
| Task reopening/rework | Engineer | “Start the required rework.” | Existing deterministic rework workflow | Task must be Rework Required | In Progress only through rework endpoint | Audit/notifications | Consultant rejection and policy tests |
| Issue creation | Engineer | “There is a crack in the wall in room 204.” | `CREATE_ISSUE` | Confirmation; task/location clarification when ambiguous | Open issue | Responsible user/PM notification + audit/action version | Voice issue tests |
| Safety observation | Engineer | “Unsafe opening on the second floor.” | Safety `CREATE_ISSUE` | Confirmation | High/critical open issue | PM notification; persistent safety evidence | Strict issue handler tests |
| Worker safety report | Worker | Same | `CREATE_FIELD_SUBMISSION` | Engineer verification | Unverified report only | Engineer notification; event finding where conflicting | Worker boundary tests |
| Design change | Engineer | “Move the partition between rooms 201 and 202.” | `CREATE_DESIGN_CHANGE_REPORT` | Confirmation | `PROPOSED`, never approved | Discipline/PM notifications + audit | Design-change voice tests |
| Spoken approved design change | Engineer | “Move it and mark approved.” | Rejected | Formal workflow required | No approved change | Rejection execution log | Design-change schema tests |
| Site report | Site Engineer | “Concrete arrived late today.” | `CREATE_SITE_REPORT_DRAFT` | Confirmation | Draft report | Audit/action version | Site-report voice tests |
| Message/discussion | Authorized Engineer | “Tell the electrical engineer…” | Controlled message action | Exact recipient + confirmation | Conversation/message through normal policy | Message audit | Messaging policy + recipient scope tests |
| Consultant approval | Assigned Consultant | “Approve the latest concrete inspection.” | `PREPARE_CONSULTANT_REVIEW` | Unique pending task + detailed confirmation | Task/review/notifications atomically committed | Review audit + action version | Centralized/discipline policy tests |
| Consultant rejection | Assigned Consultant | Explicit rejection and correction | Review rejection | Reason/comments/correction required | Prior verified state retained; Rework Required | Assignee/PM notifications + audit | Consultant workflow tests |
| Duplicate approval | Consultant | Repeat approval | Conflict/idempotent prior result | N/A | No second state transition | Existing audit retained | Row-lock/state policy tests |
| Unauthorized approval | Worker/other project | “Approved.” | 403/rejected | N/A | No mutation | Failed execution record | Voice RBAC/consultant scope tests |
| Unsupported command | Any | Non-project arbitrary instruction | `UNSUPPORTED_REQUEST` | None or clarification | No mutation | Original input retained | Strict enum/schema tests |
| Duplicate mobile command | Any allowed role | Same idempotency key | Existing command returned | Existing state | One command/action only | Same correlation ID | DB unique constraint + endpoint path |
| AI provider timeout/failure | Any allowed role | Valid transcript | Safe `FAILED` command | Retry allowed | Original transcript/audio preserved; no domain mutation | Metric + safe audit/error | Provider exception tests; JSON endpoint failure path |
| Progress revert | Original actor/PM/Admin | “Undo my last AI update.” | Compensating progress revert | Eligible latest action only | New action restores prior task state | Revert audit/event; history preserved | Revert policy tests |
| Unsafe revert | Any | Revert old/dependent/non-progress action | Manual review/conflict | Manual review | No data change | Reason exposed | Revert policy tests |
| Unrelated IFC upload | IFC uploader | Model names unrelated to project | Compatibility finding | Human review | Model `READY_WITH_WARNINGS` | Persistent Critical/High insight + notification context | IFC compatibility tests |
| Missing IFC floor/room | IFC uploader | Tasks use Floor 5 / Room 204; model lacks them | Task/model mismatch | Human review | Model retained with warnings | Persistent High insight with names/evidence | IFC compatibility tests |
| Missing modeled class | IFC uploader | Window tasks; no `IfcWindow` | Task/model mismatch | Human review | No task mutation | Persistent High insight | IFC compatibility tests |
| Major revision drift | IFC uploader | 4→11 storeys or large element delta | Revision mismatch | Human review | Revision retained, activation requires review decision | Persistent High insight | IFC revision-drift test |
| Approved wall removal | IFC uploader | New revision removes wall after approved removal change | Potentially expected change | Engineering confirmation | No automatic task/model mutation | Informational correlated insight | Deterministic intelligence rule |
| Cross-system task/model conflict | Any task update | Task says windows complete; model has no windows | Event rule | Human review | Command rules still authoritative | Persistent `TASK_MODEL_MISMATCH` | Event dispatcher + compatibility tests |

## Test data rules

- Automated tests use mocked provider responses; no live model is required.
- Authenticated identity, role, company/project membership, assignments, and
  consultant authority always come from the backend database.
- JSON simulation accepts transcript and client context only. Extra fields such
  as a client-supplied role or extracted entity set are rejected by the strict
  schema.
- Critical mutations require confirmation and are revalidated against locked
  current records at execution time.
