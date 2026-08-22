# Notifications

In-app notifications, mobile push and browser push, all from one backend
service.

---

## 1. Architecture

```
                         Application event
                    (task assigned, report submitted, …)
                                  │
                                  ▼
                        NotificationService
                     app/services/notification_service.py
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
        PostgreSQL row                      push queue
      (inside the caller's                (flushed AFTER that
        transaction)                       transaction commits)
                 │                                 │
                 ▼                                 ▼
      GET /notifications                   FCM HTTP v1 API
                 │                        app/services/push/fcm.py
                 │                                 │
                 │                    ┌────────────┴────────────┐
                 ▼                    ▼                         ▼
     Notification centre        Flutter app                Web browser
      (web bell + page,        (Android / iOS)            (service worker)
       mobile screen)
```

### The rule this design exists to enforce

**The database row is the notification. Push is a doorbell for it.**

A push that fails costs the user a buzz, never the record. Concretely:

- `notify()` writes the row inside the caller's existing transaction and
  **never commits** — a notification cannot half-commit somebody else's
  business write.
- The push is *queued on the SQLAlchemy session*, not sent. An `after_commit`
  listener flushes the queue; an `after_rollback` listener discards it. A
  rolled-back transaction therefore never rings a doorbell for something that
  did not happen.
- Delivery runs on a background thread with its own session, so an FCM timeout
  cannot stall the HTTP response.

### Adding a channel later

`_fan_out()` in `notification_service.py` is the single place a channel is
attached. A new channel (Telegram, SMS) means one more provider class under
`app/services/push/` implementing `PushProvider`, and one more line in
`_fan_out`. **No call site changes.** Telegram is deliberately not implemented.

### Why the server does not send a URL

The web app's project routes are role-prefixed (`/engineer/projects/…`,
`/project-manager/projects/…`, `/consultant-engineer/projects/…`); the mobile
app's are not. A server-chosen path could only ever be correct for one client
and one role. So the push payload names the **subject** — `projectId`,
`entityType`, `entityId` — and each client resolves it with the routing it
already owns (`utils/projectRoutes.ts`, `routeForEntity` in
`push_controller.dart`).

---

## 2. Database models

### `notifications` (existing table, one column added)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, `ON DELETE CASCADE` |
| `project_id` | UUID? | FK → `projects.id`, `ON DELETE SET NULL` |
| `task_id` | UUID? | FK → `tasks.id`, `ON DELETE SET NULL` |
| `type` | enum | `notification_type` |
| `status` | enum | `notification_status` |
| `title`, `message` | str / text | English fallback text |
| `is_read` | bool | |
| **`read_at`** | timestamptz? | **new** — when it was actually read |
| `category` | str | `DIRECT` / `WORKFLOW` / `REMINDERS` / `DEADLINE` / `SYSTEM` |
| `priority` | str | `INFO` / `NORMAL` / `IMPORTANT` / `CRITICAL` |
| `requires_action` | bool | |
| `related_entity_type` / `_id` | str? / UUID? | the subject |
| `dedupe_key` | str? | idempotency for repeatable evaluations |
| `message_key` / `message_params_json` | str? / JSONB | localization |
| `created_at`, `updated_at` | timestamptz | |

Indexes: `(user_id, created_at)`, `(user_id, is_read)`, `(user_id, dedupe_key)`,
plus single-column indexes on `user_id`, `status`, `category`,
`requires_action`, `priority`, `related_entity_type`, `related_entity_id`.

`read_at` is distinct from `updated_at` because any write touches the latter.
Existing rows keep `NULL` — back-dating a read time we never recorded would be
inventing history.

### `device_tokens` (new table)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id`, `ON DELETE CASCADE` |
| `token` | varchar(512) | FCM registration token — **unique** |
| `platform` | enum `device_platform` | `ANDROID` / `IOS` / `WEB` |
| `device_id` | varchar(200)? | stable per-installation id |
| `device_name` | varchar(200)? | e.g. "Chrome on Windows" |
| `app_version` | varchar(50)? | |
| `is_active` | bool | |
| `last_used_at` | timestamptz? | refreshed on register and on a successful send |
| `deactivated_reason` | varchar(200)? | why it was retired; `NULL` while active |
| `created_at`, `updated_at` | timestamptz | |

Indexes: `(user_id, is_active)` for dispatch, `token` **unique**, `device_id`,
`user_id`.

Three decisions worth knowing:

- **Many rows per user, on purpose.** A phone, an iPhone and two browsers are
  four delivery targets. A notification that only reached whichever device
  registered last is worse than none, because the user learns to distrust it.
- **The unique index on `token` is load-bearing.** A registration token
  identifies one app installation. Two rows for one token would let a
  notification meant for one account arrive on a device now signed in as
  somebody else. Re-registering an existing token **reassigns** it to the
  caller — that is how a shared site tablet correctly follows whoever signed
  in.
- **Retired, not deleted.** Keeping the row preserves the difference between
  "never registered" and "dropped by FCM", which is the first question asked
  when a notification did not arrive.

---

## 3. API endpoints

All require a valid access token. All are scoped to the caller: the user id
comes from the token and never from a parameter or body.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/notifications` | Paginated history, newest first |
| `GET` | `/api/v1/notifications/unread-count` | Unread total (optionally per project) |
| `GET` | `/api/v1/notifications/{id}` | One notification — how a tapped push resolves |
| `PATCH` | `/api/v1/notifications/{id}/read` | Mark one read |
| `PUT` | `/api/v1/notifications/{id}/read` | Same, kept for shipped clients |
| `PATCH` | `/api/v1/notifications/read-all` | Mark all read (optionally per project) |
| `PUT` | `/api/v1/notifications/read-all` | Same, kept for shipped clients |
| `POST` | `/api/v1/notifications/devices` | Register this device for push |
| `GET` | `/api/v1/notifications/devices` | The caller's devices (never returns tokens) |
| `DELETE` | `/api/v1/notifications/devices` | Retire a device on sign-out |
| `POST` | `/api/v1/notifications/dev/test-notification` | **Dev only** — see §10 |

`PATCH` is the correct verb and what new clients should use. `PUT` is kept
because the shipped web and Flutter clients call it; breaking installed apps to
tidy a verb is a poor trade. Both share one implementation.

**List query parameters:** `page`, `limit` (max 100), `project_id`, `unread`,
`notification_type`, `category`, `requires_action`, `search`.

**Register a device**

```json
POST /api/v1/notifications/devices
{
  "token": "<fcm-registration-token>",
  "platform": "android" | "ios" | "web",
  "deviceId": "<stable per-installation id>",
  "deviceName": "Chrome on Windows",
  "appVersion": "1.0.0"
}
```

Idempotent — safe to call on every app start.

---

## 4. Environment variables

### Backend (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PUSH_ENABLED` | `false` | Master switch. With it off, notifications are still persisted and readable everywhere. |
| `FCM_PROJECT_ID` | — | Firebase project id (falls back to the one in the service account). |
| `FCM_CREDENTIALS_FILE` | — | Path to the service account JSON. **Preferred.** |
| `FCM_CREDENTIALS_JSON` | — | The same JSON inline, for PaaS hosts with env vars only. |
| `PUSH_TIMEOUT_SECONDS` | `10` | Per-request FCM timeout. |
| `PUSH_ANDROID_CHANNEL_ID` | `structiq_default` | Must match the Flutter channel and the Android manifest. |
| `PUSH_SYNCHRONOUS` | `false` | Deliver on the calling thread. Tests and scripts only. |
| `NOTIFICATION_DEV_TEST_ENABLED` | `false` | Exposes the dev test endpoint. **Keep false in production.** |

The backend **refuses to boot** if `PUSH_ENABLED=true` with neither credential
variable set. A silently unconfigured provider is indistinguishable from
"nobody has registered a device", and that ambiguity is the hardest part of
diagnosing a missing notification.

### Frontend (`frontend/.env`)

| Variable | Meaning |
|---|---|
| `VITE_FIREBASE_API_KEY` | Web app config |
| `VITE_FIREBASE_AUTH_DOMAIN` | Web app config |
| `VITE_FIREBASE_PROJECT_ID` | Web app config |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Web app config |
| `VITE_FIREBASE_APP_ID` | Web app config |
| `VITE_FIREBASE_VAPID_KEY` | Web Push certificate — public key pair |

**These are not secrets.** A Firebase web config and a VAPID public key are
client identifiers: they name the project to Google and grant nothing on their
own. The service account that can actually *send* is server-side only and is
git-ignored.

### Flutter

Either drop `google-services.json` / `GoogleService-Info.plist` into the
project (the usual path, both git-ignored), **or** pass `--dart-define` values:
`FIREBASE_API_KEY`, `FIREBASE_APP_ID_ANDROID`, `FIREBASE_APP_ID_IOS`,
`FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_PROJECT_ID`,
`FIREBASE_STORAGE_BUCKET`, `FIREBASE_IOS_BUNDLE_ID`. Neither is required for
the app to build and run.

---

## 5. What is already done vs. what you must configure

### Already done — no action needed

- `Notification` model, `read_at` column, `device_tokens` table, migration.
- `NotificationService` with `notify_user` / `notify_users` /
  `notify_project_users` / `mark_as_read` / `mark_all_as_read` /
  `unread_count`.
- FCM HTTP v1 provider with OAuth2, invalid-token retirement, per-platform
  payloads (Android channel, APNs alert, Web Push link).
- All notification API endpoints, including device registration.
- React: bell, dropdown, notification page, service worker, token
  registration, foreground toast, click-through routing, sign-out teardown.
- Flutter: permission, token registration and refresh, foreground banner,
  background and terminated handling, tap navigation, sign-out teardown.
- Android manifest permission and default channel; `google-services` plugin
  applied conditionally.
- Five real application events wired (see §9).
- Backend, web and mobile tests.

### You must configure manually

Nothing in this repository can create a Firebase project for you. These steps
are yours:

#### A. Firebase project (once)

1. <https://console.firebase.google.com> → **Add project**.
2. Google Analytics is optional and unrelated to messaging.

#### B. Backend service account (required for any push)

1. Firebase Console → ⚙ **Project settings** → **Service accounts**.
2. **Generate new private key** → downloads a JSON file.
3. Save it as `backend/secrets/fcm-service-account.json`
   (`mkdir backend/secrets` first — it is git-ignored except for its README).
4. In `backend/.env`:
   ```
   PUSH_ENABLED=true
   FCM_PROJECT_ID=your-project-id
   FCM_CREDENTIALS_FILE=/run/secrets/fcm-service-account.json
   ```
   Use an absolute host path instead if you run the backend outside Docker.

> ⚠️ This file is a real credential. Anyone holding it can send a notification
> to every device registered to the project. Never commit it; never put it in
> a frontend bundle.

#### C. Android (required for the Flutter app)

1. Firebase Console → **Add app** → **Android**.
2. Package name: **`com.example.mobile_app`** — this must match
   `applicationId` in `mobile_app/android/app/build.gradle.kts` exactly.
   *(If you change the application id before release, register the new one.)*
3. Download `google-services.json` → place in
   `mobile_app/android/app/google-services.json`.
4. Nothing else — the Gradle plugin is already declared and applies itself when
   that file is present.

#### D. iOS (only if you ship iOS)

1. Firebase Console → **Add app** → **iOS**, bundle id matching Xcode.
2. Download `GoogleService-Info.plist` → add to `ios/Runner/` **through Xcode**
   (drag into the Runner target so it lands in the bundle).
3. Apple Developer portal → **Keys** → create an **APNs Auth Key** (`.p8`).
4. Firebase Console → **Project settings** → **Cloud Messaging** → **Apple app
   configuration** → upload the `.p8` with its Key ID and your Team ID.
5. In Xcode → **Signing & Capabilities** → add **Push Notifications** and
   **Background Modes → Remote notifications**.

> iOS push **does not work on the Simulator**. A physical device is required.

#### E. Web push

1. Firebase Console → **Add app** → **Web** (if you have not already).
2. Copy the config values into `frontend/.env` as `VITE_FIREBASE_*`.
3. **Project settings → Cloud Messaging → Web configuration → Web Push
   certificates → Generate key pair.** Copy the key into
   `VITE_FIREBASE_VAPID_KEY`.

> Browsers only permit push on **HTTPS** or on **`localhost`**. A LAN address
> such as `http://192.168.1.5:5173` will not work — the permission prompt
> either never appears or the token request fails.

---

## 6. Running locally

### Backend

```bash
cd backend && alembic upgrade head && uvicorn app.main:app --reload --port 8000
```

Or the whole stack:

```bash
docker compose up --build
```

The backend logs its push status at startup — `push notifications enabled (FCM
configured: True)` or `push notifications disabled`. Check this line first when
push is not arriving.

### Web app

```bash
cd frontend && npm install --legacy-peer-deps && npm run dev
```

Then open <http://localhost:5173> — not the LAN address, for the HTTPS reason
above.

### Flutter app

```bash
cd mobile_app && flutter run --dart-define=API_BASE_URL=http://<your-lan-ip>:8000/api/v1
```

`API_BASE_URL` must be a LAN address for a physical device: `127.0.0.1` points
the phone at itself, and `10.0.2.2` only means anything to the Android
emulator. It is DHCP-assigned and goes stale — check `ipconfig` if sign-in
fails to connect.

---

## 7. Triggering a development test notification

Set in `backend/.env`:

```
NOTIFICATION_DEV_TEST_ENABLED=true
```

Then, as any signed-in user:

```bash
curl -X POST http://localhost:8000/api/v1/notifications/dev/test-notification -H "Authorization: Bearer <access-token>"
```

Three things make this safe to have in the tree:

1. It is off unless the flag is explicitly `true`, and the flag defaults to
   false — a production deployment that changes nothing gets a **404**.
2. It requires a valid access token, like every other route.
3. **The recipient is `current_user.id` and there is no parameter that can
   change it.** Even with the flag on, it cannot send a notification to anybody
   else.

It returns 404 rather than 403 when disabled: an endpoint that is switched off
should not confirm its own existence.

---

## 8. Testing

### Backend

```bash
cd backend && pytest tests/test_push_notifications.py tests/test_smart_notifications.py -q
```

Provider tests run with no database and no network. Service tests need
PostgreSQL and skip cleanly without it.

Covered: creating a notification, listing, unread count, marking one read,
marking all read, user isolation, pagination, multiple devices per user,
token refresh retiring the old token, a shared device changing hands,
invalid-token deactivation, transient failures leaving tokens alone, bad
credentials never blaming a device, and a push failure never costing the
database row.

### Web

```bash
cd frontend && npm run test && npx tsc -b --force
```

Manual end-to-end:

1. Open <http://localhost:5173> and sign in — a browser permission prompt
   appears. Accept.
2. DevTools → **Application → Service Workers** shows
   `firebase-messaging-sw.js` activated.
3. `GET /notifications/devices` (or the database) shows a `web` row.
4. Trigger the dev test notification. With the tab focused, an in-app toast
   appears and the bell count increases.
5. Switch to another tab or minimise the browser, trigger again — an OS-level
   notification appears.
6. Click it: the tab focuses and navigates to the relevant page.
7. Open the bell — the notification is listed, unread; click it and it becomes
   read; **Mark all read** clears the count.

### Mobile

1. **App open (foreground):** trigger a notification → a banner appears and an
   open notifications screen refreshes itself.
2. **App backgrounded:** press Home, trigger → a system tray notification
   appears.
3. **App fully closed:** swipe it from recents, trigger → the notification
   still arrives (handled natively; no Dart runs).
4. **Tap:** from each of the three states, tapping opens the right screen —
   a task notification opens that task, an issue opens the issues list.
5. **Token registration:** after sign-in, `GET /notifications/devices` shows an
   `android` (or `ios`) row.
6. **Sign out:** the row's `is_active` becomes `false` with
   `deactivated_reason = "signed out"`.

```bash
cd mobile_app && flutter test && flutter analyze
```

---

## 9. Application events that generate notifications

Wired through `NotificationService`, so each reaches the notification centre
**and** push:

| Event | Recipients | Source |
|---|---|---|
| Task assigned | new assignees | `api/tasks.py` |
| Task submitted for review / status requiring review | reviewers, project manager | `api/tasks.py` |
| Issue created | PM, owner, discipline engineers | `api/issues.py` |
| **Issue assigned** | the assignee | `api/issues.py` — **new** |
| Design change raised / approved / rejected | reviewers, proposer, PM, owner | `api/design_changes.py` |
| Site report submitted / verified / rejected | project manager, author | `api/site_reports.py` |
| Task deadlines and reminders | assignees, PM | `services/reminder_service.py` |
| Owner requests, site visits, field submissions | per existing RBAC | `api/collaboration.py`, `api/field_submissions.py` |

### Two notes on scope

**There is no RFI entity in this platform.** The closest existing flow — one
discipline raising a request that another must review and respond to — is
**DesignChange**, so that is what carries the "RFI requiring review/response"
behaviour. Task review requests (`APPROVAL_REQUEST`, `requires_action=True`)
cover the review case.

**Some older call sites still write notifications directly** and are therefore
in-app only, not pushed: `api/projects.py`, `api/documents.py`,
`api/milestones.py`, `api/users.py`, `services/ifc_processing_service.py`,
`services/voice_action_service.py`, `services/task_progress_service.py`,
`services/domain_event_dispatcher.py`. This is deliberate — the brief was to
wire a small number of real events, not every event. Opting one in is a
one-line change: replace `db.add(Notification(...))` with a
`notification_service.notify(...)` call using the same field values.

---

## 10. Security

- **Authentication.** Every endpoint uses the existing `get_current_user`.
- **Ownership in the WHERE clause.** `mark_as_read` filters on
  `user_id` inside the `UPDATE`, so a notification belonging to somebody else
  is indistinguishable from one that does not exist. There is no "exists but is
  not yours" branch to leak from.
- **No endpoint targets an arbitrary user.** Recipients are decided
  server-side by business rules. The only user-facing notification-creating
  endpoint is the dev test one, which is hard-wired to the caller.
- **Project scoping.** `notify_project_users` reads membership from the same
  three sources `user_has_project_access` consults, so it cannot reach anyone
  who would be refused the project on a `GET`.
- **Push tokens are never returned** by the API. `DeviceTokenOut` describes the
  device, not how to reach it. A token is a delivery address, not a credential
  — but echoing it back would put it in devtools and error reports for no
  benefit.
- **A device cannot be unsubscribed by guessing.** `unregister_device` is
  scoped to `user_id` in the WHERE clause.
- **Sign-out retires the device** on both clients, *before* the session ends
  while the access token is still valid — otherwise a shared site phone keeps
  delivering the previous user's notifications.
- **Credentials.** The service account is read at runtime from a mounted file
  or an environment variable; `*service-account*.json`,
  `*firebase-adminsdk*.json`, `backend/secrets/*`, `google-services.json` and
  `GoogleService-Info.plist` are all git-ignored. Nothing secret is in the
  repository.
- **Misconfiguration never retires devices.** A 401/403 from FCM is reported as
  `NOT_CONFIGURED`, not `INVALID_TOKEN` — treating our own bad credentials as
  dead tokens would silently unsubscribe the entire estate.

---

## 11. Known limitations

- **iOS requires a physical device**; push does not work on the Simulator, and
  it additionally needs a paid Apple Developer account for the APNs key.
- **Web push needs HTTPS or `localhost`.** A LAN dev address cannot receive it.
- **Safari** supports web push only from 16.4, and on iOS only for a site the
  user has added to the Home Screen.
- **No delivery receipts.** FCM reports acceptance, not arrival; `SENT` means
  "handed to FCM". This is a platform limitation, not an implementation gap.
- **Delivery is fire-and-forget with no retry queue.** A transient failure
  leaves the token active and the next notification tries again, but that
  specific push is not re-attempted. A durable queue would be the next step if
  guaranteed delivery is ever required — the provider interface would not
  change.
- **One HTTP request per token.** FCM v1 has no multicast endpoint. Fine for
  this platform's scale; batching would need the `/batch` endpoint.
- **The Android application id is still `com.example.mobile_app`.** It must be
  changed before any store release, and the new id re-registered in Firebase.
- **Notification preferences are not implemented.** Every user receives every
  notification their role entitles them to. `ENDPOINTS.NOTIFICATIONS.PREFERENCES`
  exists in the frontend constants but has no backend behind it.
