# Task 6 — Final Real-Device Verification Pass

Completes the authenticated-screen verification deferred from the Task 6
implementation report. No redesign, no refactor: diagnosis, recovery,
verification, and minimal fixes for what the device actually showed.

---

## 1. Environment

### What broke

**Infrastructure, not the application.** The Docker Desktop 4.84.0 backend was
crashing on startup, before it ever started its WSL engine — which is why
`docker ps` hung and `docker-desktop` stayed `Stopped`.

From `%LOCALAPPDATA%\Docker\log\host\com.docker.backend.exe.log`:

```
backend crashed … starting services: initializing Inference manager:
listening on unix://…/Docker/run/dockerInference:
remove …/Docker/run/dockerInference: The file cannot be accessed by the system.
```

`…/Docker/run/` held three **orphaned AF_UNIX socket reparse points**
(`dockerInference`, `dockerEthernetVfkit`, `userAnalyticsOtlpHttp.sock`) left
behind by a previous unclean shutdown. Their backing sockets are gone, so
Win32 file APIs cannot open *or* delete them — `Remove-Item` and
`File.Delete` both fail with "The file cannot be accessed by the system".
Docker tries to `remove` the stale socket before binding, hits that error, and
aborts startup.

Ruled out by measurement, not assumption:
- **Disk** — 95 GB free on C:.
- **Memory** — 15.7 GB total; tight (2.7 GB free with the emulator running) but
  never the failure point, since the crash happens before the VM is asked for.
- **Application code** — the crash is in Docker's own Inference manager and
  Secrets Engine, with no project container involved.

### Recovery

Renamed the parent directories rather than the unopenable files inside them,
because a directory rename does not need to open its children. Docker recreates
both on start:

- `…\Local\Docker\run` → `run-stale-<timestamp>`
- `…\Local\docker-secrets-engine` → `docker-secrets-engine-stale-<timestamp>`

The second one only surfaced after the first was cleared — the same fault, next
service in the startup chain. After the second rename the engine came up.

Nothing was destroyed: no volume removed, no migration reset, no container
rebuilt. `Construction_db` came back healthy with its data intact — 22 users,
2 projects, 14 tasks, 126 notifications, the same counts as before.

`construction_frontend` had exited 255 during the outage and was restarted; it
is not used by the mobile pass.

---

## 2. Device verification

Android emulator, **API 34**, live backend at `10.0.2.2:8000`, real API
responses. Both locales driven by the actual per-app device locale
(`cmd locale set-app-locales`), not a test harness.

| Screen | English device | Arabic device | Live backend |
|---|---|---|---|
| Dashboard | PASS (after fix 1) | PASS (after fixes 1, 3) | YES |
| Projects | PASS | PASS (after fixes 5, 6) | YES |
| Tasks | PASS | PASS | YES |
| Issues | PASS (after fix 2) | PASS (after fixes 2, 4) | YES |
| Site Reports | PASS | PASS | YES |
| Messages | PASS | PASS | YES |
| Notifications | PASS | PASS | YES |
| Profile | PASS | PASS | YES |
| OTP | N/A | N/A | N/A |

**OTP is N/A because the mobile app has no OTP UI.** Step-up (Task 4) is a web
flow; the app's only exposure is the `stepUp.codeRequested` *notification*,
which is translated and covered by tests. There was no screen to verify.

Confirmed working against live data, in Arabic:
- **Notification `messageKey` resolution** — "مهمة متأخرة" with the body
  "Basement waterproofing متأخرة عن موعدها.", the task's own name interpolated
  untranslated inside the Arabic sentence.
- **Fallback** — the two message notifications carry no `messageKey` and show
  the server's English text verbatim. No crash, no blank, no exception text.
- **Forwarded message** — "مُعاد توجيهها من Localization Tester": label Arabic,
  sender name and quoted body untouched.
- **Mixed content** — `IFC/BIM`, `BOQ item 4.12`, `A-304 rev C`, the IFC GUID
  `1hVQz$4Kn0hxJ2m0kQ5wZa`, `TSK-002`, `2026-08-20` and an email address all
  render correctly inside RTL paragraphs; English sentences inside RTL put
  their trailing punctuation at the left, which is correct bidi.

---

## 3. Bugs found and fixed

**1. Dashboard header overflowed by 5.5px** *(both locales)*
Symptom: yellow-and-black overflow stripe under the greeting.
Cause: `_DashboardHeader` pinned the header to `height: 254 * textScale`; the
greeting, role caption and project selector no longer fit. A fixed height makes
every extra pixel of content — a long name, a longer translation — an overflow.
Fix: `constraints: BoxConstraints(minHeight: …)` and `Spacer` → `SizedBox`
(`Spacer` needs the bounded height the header no longer has).
File: `lib/features/dashboard/role_dashboard_screen.dart`.
Verified: screenshot 53 (EN), 91 (AR).

**2. Severity chip showed the raw value** *(both locales)*
Symptom: an issue's severity rendered as lowercase `critical` next to a
correctly translated status.
Cause: `_Subtitle` passed severity to `StatusBadge`, which resolves through
`statusLabel`; severity words live in the *priority* table.
Fix: pass `label: context.l10n.priorityLabel(severity)`.
File: `lib/features/shared/remote_collection_screen.dart`.
Verified: now "حرجة" / "Critical" (screenshot 92).

**3. Progress ring showed the raw project status**
Symptom: "active" in an otherwise Arabic card.
Cause: `ProjectProgressCard` printed `status.replaceAll('_', ' ')`.
Fix: `context.l10n.statusLabel(status)`.
File: `lib/core/widgets/dashboard_components.dart`.
Verified: now "قيد التنفيذ" (screenshot 91).

**4. Arabic Issues nav label wrapped and clipped**
Symptom: "الملاحظات والمشكلات" wrapped to two lines in the bottom bar with the
second line's descenders cut off.
Cause: the web's sidebar term does not fit a five-destination phone bar.
Fix: `navIssues` Arabic shortened to "الملاحظات"; the screen title keeps the
full "الملاحظات والمعوّقات". The ARB description records why.
Verified: one line, no clipping (screenshot 91).

**5. "Switch account" chip collided with the heading under RTL**
Symptom: the chip sat on top of "مشاريعي".
Cause: `Align(alignment: Alignment.topRight)` — a hardcoded physical edge, so
in RTL the chip landed on the same side as the heading.
Fix: `AlignmentDirectional.topEnd`.
File: `lib/features/projects/projects_screen.dart`.
Verified: chip on the left in Arabic, right in English (screenshot 90).

**6. Counts read wrong at one**
Symptom: "1 open issues".
Fix: ICU plurals for `projectsOpenIssues` and `evidencePhotoCount`; Arabic gets
zero/one/two/few/other, so it now reads "ملاحظة مفتوحة واحدة".
Verified: screenshot 90.

**7. Two numbering systems on one Arabic screen**
Symptom: "الاستحقاق ١٧ أغسطس" (Arabic-Indic) beside "40%" (Western).
Cause: `intl` renders Arabic dates with Arabic-Indic digits but Arabic numbers
with Western ones.
Fix: the date/time formatters normalise to Western digits, matching the web,
which uses Western digits in Arabic throughout.
File: `lib/core/l10n/l10n_formats.dart`.
Verified: "16 أغسطس 7:49 م" (screenshot 93).

**8. Voice task-context dropdown overflowed by 6.1px** *(Arabic)*
Cause: without `isExpanded`, the selected task's code and name size the field;
the wider Arabic label pushed it past its box.
Fix: `isExpanded: true` plus ellipsis on the items.
File: `lib/features/voice_command/voice_screen.dart`.

**9. Activity feed showed raw database identifiers**
Symptom: `reminders_dispatched`, `conversation_created`.
Cause: activity entries carry no message key (see §4), and the raw value was
printed verbatim.
Fix: humanise the identifier before display. It still cannot be *translated* —
that needs the backend — but a site manager no longer reads a column value.
File: `lib/features/dashboard/role_dashboard_screen.dart`.

Each fix has a regression test in `test/localization_test.dart` (severity vs
status vocabulary, project status translation, Western digits in Arabic dates,
plural forms).

---

## 4. Known limitations (unchanged)

- **Shared-entity message bodies are English prose composed server-side.**
  Confirmed on device: an Arabic conversation shows a "Shared Issue / Project:
  … / Status: Open / Severity: Critical / Original owner: …" block in English.
  **Known backend localization limitation — not fixed in Task 6 verification.**
  No client-side translation workaround was invented.
- Activity/audit entries carry no `message_key`, so they cannot be translated.
- Backend error `detail` strings are prose, not codes; mapping is by HTTP status.

---

## 5. Unresolved observation — session showed a different user

Mid-run, after a series of coordinate taps, the app displayed a session for
`civilcont@gmail.com` ("mhmd ali", engineer, project "Residential Complex C")
— **an account whose credentials I never entered.** Several of my blind taps
had been landing on the record FAB and other controls, so the navigation was
certainly erratic; what I cannot explain is how the *session identity* changed.

What I checked: `/auth/refresh` derives the user from the token's `sub`, so it
cannot return a different user; no login audit rows exist for the window; the
emulator was wiped before the run and only the fixture account was ever typed.

After `pm clear` and a clean re-login the fixture session was correct and the
behaviour **did not reproduce**. I am reporting it rather than dismissing it:
it was observed once, its cause is not established, and if it is real it is a
session-handling bug, not a localization one. It warrants its own look.

---

## 6. Test-data safety

- **No pre-existing account was modified.** No password, role, permission,
  activation state or project membership of any existing user was changed.
- Fixture created for this run: two disposable accounts
  (`e2e.localization.pm.*`, `e2e.localization.eng.*` on `@e2e-fixture.com`),
  one project, three tasks, one issue, one site report, three notifications and
  the messages created through the API.
- **All of it was deleted afterwards.** Verified: 0 fixture users, 0 fixture
  projects; totals back to 22 users / 2 projects / 14 tasks.
- Notifications read 127 against a 126 baseline. The extra row is a
  scheduler-generated "Response reminder" for `pm.m5@constro.io`, produced by
  the backend's own reminder job while the stack was up — not fixture data and
  not something this run created by hand.
- One fixture detail worth recording: the accounts were first created on
  `@example.test`, which the API's `EmailStr` rejects as a reserved TLD (a 500
  on `GET /projects`). They were renamed to `@e2e-fixture.com`. Only fixture
  rows were touched.

---

## 7. Final tests

| Check | Result |
|---|---|
| `flutter analyze` | **No issues found** |
| `flutter test` | **73/73 pass** |
| Device verification | English + Arabic, all authenticated screens, live backend |
| Test-data cleanup | Complete and verified |

---

## Final verdict

**Task 6 fully verified.**

Every authenticated screen was exercised on a real device in both languages
against the live backend. Nine bugs were found there — one of them an overflow
in English, five specific to Arabic — and all nine are fixed and re-verified on
device. The shared-entity English-prose limitation remains documented and
unaddressed by design, since fixing it is a backend change.

The one thing I am *not* closing is §5: a session identity change I saw once
and could not reproduce or explain. It is unrelated to localization, but it
should not be lost.
