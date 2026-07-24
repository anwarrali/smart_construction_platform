# Flutter Mobile Audit and Integration Map

## Reuse audit

The FastAPI backend under `backend/app` is the only server and remains the system of record. The mobile app reuses `/api/v1` authentication with access/refresh tokens, `auth/me`, assigned-project filtering, project membership checks, task workflow endpoints, engineer/consultant/owner dashboards, documents, site reports, issues, attachments, notifications, messages, profiles, and the field action-proposal validator.

Role routing uses the persisted backend role plus `engineerAffiliation`: `main_contractor` opens the Site Engineer experience; `external_consultant` opens Consultant review; `project_manager` opens monitoring; `owner` opens the deterministic executive view. Admin remains web-first.

The web HSL design tokens were converted directly for mobile: primary `#222D4E` and construction bronze `#DD922C`.

## Missing or deferred

- The backend has no transcription or AI intent service. Mobile uses a deliberately non-intelligent manual proposal builder.
- The existing field proposal API covers issue, design change, site report, project question, and general note. It does not yet accept the full task-progress voice intent contract. Consequently voice confirmation does not execute a domain mutation.
- Chat is existing direct project-member messaging rather than task/review conversation threads.
- Site reports are submitted directly; a server-persisted report draft contract is not present.
- Push, Telegram, email, SMS, external AI, audio retention, and production AI processing are deferred.

No database migration or backend endpoint was added.

## Flutter architecture and packages

Feature-first MVVM uses Riverpod only, GoRouter, Dio, flutter_secure_storage, shared_preferences, connectivity_plus, record, audioplayers, path_provider, image_picker, file_picker, and intl. Views call view models/providers, which call repositories, services, then the shared API client. Tiny related types are consolidated into domain files to avoid one-file-per-class boilerplate.

## Routes

`/splash`, `/login`, `/contact-admin`, `/projects`, `/home`, `/voice`, `/tasks`, `/tasks/:id`, `/reports`, `/reviews`, `/issues`, `/documents`, `/messages`, `/notifications`, `/profile`.

## Role navigation

- Site Engineer: Home, My Tasks, Reports, Messages, Profile; Notifications in app bar; Voice is the primary home action.
- Consultant: Home, Reviews, Documents, Messages, Profile.
- Project Manager: Home, Tasks, Issues, Messages, Profile.
- Owner: Home, Reports, Projects, Messages, Profile.

## Voice safety contract

`VoiceDraft` stores local capture metadata. `VoiceProcessingService` returns a `VoiceIntentProposal` with source text, selected intent, warnings, and validation errors. It performs no fake extraction. Future integration must send a proposal through authentication, membership, task ownership/state, dependency, permission, and numeric validation; display old/new values; require explicit confirmation; then call the existing domain endpoint. AI must never receive database credentials or directly execute changes.

## Future notifications and Telegram

Internal backend notifications remain authoritative. A later channel dispatcher may consume selected notification events and deliver Telegram summaries based on user/project rules. Telegram acknowledgements must not mutate project records without the same authenticated domain validation and confirmation workflow.
