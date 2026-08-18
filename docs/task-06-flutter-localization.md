# Task 6 — Flutter Arabic Localization & Bilingual UX

Scope: `mobile_app/` only. No backend endpoint, schema, permission, notification
rule, OTP flow or business workflow was changed.

---

## 1. Implemented work

### 1.1 Audit (Phase 1)

I scanned all 74 Dart files / 11,088 lines under `lib/`, collecting **every**
string literal rather than grepping for `Text('…')`, then classifying it. That
surfaced copy hiding in places a naive search misses:

- enum-to-label helpers (`_label`, `_title`, `_labelIntent`, `_filterLabel`)
- status/priority/discipline humanisers scattered across four screens
- the issue-category and photo-direction dropdown lists
- error messages built inside `NetworkException`
- `StateError('Record audio before analysis.')` in the voice view-model
- **navigation destination labels used as routing keys** — `MobileShell`
  recovered a route by switching on the destination's English label
  (`'Tasks' -> '/tasks'`). Translating a label would have sent that tab to the
  fallback route. This had to be fixed before anything else could be localized.

### 1.2 Localization architecture (Phases 3–5)

Flutter's own `gen-l10n`, not a bespoke system:

```
mobile_app/
  l10n.yaml                     # arb-dir, template, output class AppL10n
  lib/l10n/app_en.arb           # 547 messages + descriptions + placeholders
  lib/l10n/app_ar.arb           # 547 messages
  lib/l10n/app_localizations*.dart  (generated, committed)
```

English is **not** the hardcoded baseline: both languages come from the same
ARB pair, and `commonCancel` resolves through the catalogue in both.

Supporting layer, all in `lib/core/l10n/`:

| File | Responsibility |
|---|---|
| `l10n_labels.dart` | `context.l10n` shorthand, plus the tables that turn API enum values into words: `statusLabel`, `priorityLabel`, `disciplineLabel`, `roleLabel`, `entityLabel`, `issueCategoryLabel`, `photoViewLabel`, `visitTypeLabel`, `actionCountLabel`, `voiceIntentLabel`, and the error mappers `describeError` / `describeLoginError` |
| `notification_text.dart` | Resolves a notification's `messageKey` + params, exactly as the web does |
| `l10n_formats.dart` | Locale-bound dates, times, integers and percentages |

**No language conditionals in widgets.** A test enforces this (§2).

### 1.3 Terminology from the web (Phase 2)

`frontend/src/i18n/locales/{en,ar}/translation.json` (2,167 keys) was the source
of truth. Where the web already fixed a term, mobile reuses it verbatim:

| Value | Arabic (web = mobile) |
|---|---|
| `under_review` | قيد المراجعة |
| `rework_required` | تتطلب إعادة عمل |
| `blocked` | متوقفة |
| `project_manager` | مدير المشروع |
| `consultant` | الاستشاري |
| `critical` | حرجة |
| Forward | إعادة توجيه |
| Site report | تقرير موقع |

### 1.4 Notifications (Phase 13)

**No second notification system.** The Task 3 engine already stores
`message_key` + `message_params_json` and the API already exposes them; the web
resolves `notification.<messageKey>.title`. Mobile now does the same against the
ARB. `NotificationItem` gained `messageKey` and `messageParams`; the 11 keys the
backend emits (`taskDeadline.*`, `siteReport.*`, `reminder.*`,
`stepUp.codeRequested`) each have an English and Arabic message.

A notification with **no** key, or a key this build does not know, falls back to
the server's own rendered text rather than guessing — the unreliable
client-side translation Phase 13 rules out. Both cases are covered by tests.

### 1.5 Errors (Phase 15)

`NetworkException` used to carry a rendered English sentence. It now carries
structured facts (`statusCode`, a `NetworkFailure` enum) and the server's
`detail` is kept for logs only. `describeError` maps offline/timeout/401/403/
404/409/422 to translated sentences and everything else to a generic one, so
backend English prose never reaches an Arabic screen. Sign-in has its own
mapping (`describeLoginError`) because "You are not signed in" is useless on the
sign-in screen; 429 gets the throttle message.

The voice flow's `StateError`s became a `VoiceFailure` enum for the same reason.

### 1.6 Language selection

Device locale decides by default. A three-option chooser on Profile
(Device language / English / العربية) persists an override in
`SharedPreferences`; "follow the device" is a real third state, so a user who
never chose keeps tracking their phone.

### 1.7 Data that is never translated

Stored values are untouched — only their display changes:

- issue categories keep their **English** wire values (`'Material unavailable'`),
  so an issue raised in an Arabic session is indistinguishable in the database
  from one raised in English;
- photo view directions keep their upper-case codes;
- task titles, message bodies, project names, user names, rejection reasons,
  transcripts, filenames, IFC schema names and task codes are interpolated
  exactly as received.

---

## 2. Tests

`flutter analyze`: **No issues found.** Full suite: **69/69 pass.**

**`test/localization_coverage_test.dart`** — 10 static checks:
EN/AR key parity both ways · no empty translation · every message has a
translator description · placeholders identical across languages · no duplicate
top-level key · generated Dart in step with the ARB · **no hardcoded
user-facing English anywhere in `lib/`** · no locale conditionals in widgets.

The hardcoded-English scanner caught a real miss during development (a `Cancel`
in the review-rejection dialog) after I believed the conversion was finished.

**`test/localization_test.dart`** — 21 behavioural tests: locale resolution
(en/ar/rtl/unsupported-fallback), web terminology pinned for statuses, roles and
priorities, unknown values humanised not blanked, user-generated content
preserved inside translated frames, the Task 3 fallback paths, error mapping in
both languages, locale-specific date and percentage formatting, and rendering
under RTL, a narrow button and a 1.5× accessibility text scale.

Task 5's `design_system_test.dart` was updated: its host is now a localized app,
and the badge test asserts the translated label instead of the humanised raw
value.

---

## 3. Device verification

Android emulator, API 34, fresh AVD. **English LTR and Arabic RTL both driven by
the real per-app device locale**, not a test harness.

Verified on device (screenshots taken):

| Screen | English | Arabic |
|---|---|---|
| Splash / brand lockup + descriptor | ✅ | ✅ ("إدارة إنشاءات ذكية") |
| Sign-in: heading, subtitle, both field labels, submit, help link, footer, aside | ✅ | ✅ |
| Inline validation (both fields empty) | ✅ | ✅ ("أدخل بريدك الإلكتروني أو اسم المستخدم.") |
| Error state (backend unreachable) | ✅ | ✅ ("استغرق الخادم وقتًا طويلًا للاستجابة…") |
| RTL mirroring: lockup to trailing edge, icons swapped, submit arrow reversed | — | ✅ |
| Latin identifiers inside RTL fields (the email address) | — | ✅ renders LTR correctly |

The error-state check is a genuine result, not a consolation prize: it proves on
a real device that the server's English `detail` is discarded and the translated
sentence is shown instead.

### What is NOT yet verified on device

**The authenticated screens** — dashboard, projects, tasks, issues, site
reports, messages, forwarded/shared messages, notifications, OTP, profile and
its language switcher — were **not** exercised on device in this session,
because the Docker engine on this machine would not start. `docker ps` hung
indefinitely; WSL showed both distros stopped and no `docker-desktop` distro. I
tried three times, including a full `wsl --shutdown` and a clean Docker Desktop
restart, over about half an hour. Without Postgres there is no backend, and
those screens cannot render real data.

Their **copy** is covered by the widget tests, and their **layout** was verified
on device during Task 5 — but Task 6's specific risk (Arabic strings being
longer and overflowing) has only been checked in widget tests for the longest
label and a 1.5× text scale, not screen by screen on a device. **Treat this as
outstanding.** To finish it in one pass once Docker is up:

```bash
docker compose up -d && flutter build apk --debug --target-platform android-x64 --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

then seed a disposable account, walk the screens in `en`, and repeat with
`adb shell cmd locale set-app-locales com.example.mobile_app --locales ar`.

---

## 4. Remaining untranslated / unsupported areas

- **None of the app's own copy.** The scanner test fails the build if any
  reappears.
- Server-provided *content* stays as sent, by design (§1.7).
- The AI-diagnostics screen's individual check *details* (e.g. "AAC-LC in an M4A
  container") remain English. It is a development-only screen, gated off in
  release builds; its chrome is translated.
- An unrecognised backend enum value is humanised (`some_new_state` →
  "some new state") rather than shown blank. Adding the value to the catalogue
  and the lookup table is a two-line change.

---

## 5. Backend/API limitations found

1. **Server-composed message bodies.** `POST /messages/share` composes the
   shared-entity body as English plain text server-side ("Shared Issue /
   Project: … / Status: Open"). Mobile renders it verbatim and adds a
   translated entity chip, so an Arabic reader sees an English block inside an
   Arabic screen. Fixing it properly means the endpoint returning structured
   fields instead of prose — a backend change, out of scope.
2. **Error `detail` strings are prose, not codes.** Mapping is by HTTP status
   only, so two different 400s cannot be told apart. A machine-readable error
   code would let the client say something specific.
3. **Audit-log and activity-feed entries** arrive as English descriptions with
   no structured key, so the dashboard activity list shows them as sent.
4. `POST /users` and the project-member endpoints return English validation
   prose; the client maps 422 to a generic translated sentence.

---

## 6. Follow-up work

1. Finish the authenticated-screen device pass in both locales (§3).
2. Structured payload for shared-entity messages (limitation 1).
3. Error codes alongside `detail` (limitation 2).
4. `message_key` on audit/activity entries (limitation 3).

---

## 7. Final quality check

1. **User-facing strings found:** 900 candidate literals, of which 344 were in a
   UI context; after removing false positives, ~330 distinct pieces of copy
   across 25 screens.
2. **Moved to localization:** all of them — 534 `l10n.*` call sites across 31
   files, plus the lookup tables that cover the enum-valued cases.
3. **English translations:** 547.
4. **Arabic translations:** 547.
5. **Missing keys:** none — asserted in both directions by test.
6. **Untranslated UI strings:** none in `lib/`, enforced by the scanner test.
   The documented exceptions are in §4.
7. **Arabic RTL across major screens:** established in Task 5 and re-tested in
   widget tests; re-verified on device for the pre-auth screens. The
   authenticated screens are the outstanding item in §3.
8. **Mixed Arabic/English technical strings:** correct. IFC, BIM and schema
   names stay Latin; the email address renders LTR inside an RTL field
   (screenshot); task codes and IDs are interpolated untouched.
9. **User-generated messages:** never translated — asserted by test.
10. **Task 3 compatibility:** preserved. Mobile consumes the existing
    `messageKey`/`messageParamsJson`; no new notification code, and both
    fallback paths are tested.
11. **Task 4 compatibility:** preserved. No OTP behaviour changed. The mobile
    app has no OTP UI of its own — step-up is a web flow — so there was no OTP
    screen to localize; the step-up **notification** it can receive is
    translated.
12. **Backend changes:** none.
13. **Existing accounts modified:** **none.** No account was created, altered,
    or deleted, and no membership changed. The disposable-fixture script was
    written but never ran, because the database was unreachable.
14. **Limitations:** §3 (device pass), §4 and §5.
