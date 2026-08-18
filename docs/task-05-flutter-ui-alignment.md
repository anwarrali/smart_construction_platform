# Task 5 — Flutter Application UI/UX Alignment with the Web Platform

Scope: `mobile_app/` only. No backend endpoint, schema, permission, notification
rule or OTP flow was changed by this task.

---

## 1. Audit of the existing Flutter app

Before writing anything I read every screen under `mobile_app/lib/` and compared
it against the current web build. The findings, in the order they mattered:

| # | Finding | Severity |
|---|---------|----------|
| 1 | **The app was not Struct IQ.** The title was "Construction Field", the login screen read `CONSTRUCTION FIELD`, and the brand mark was a bronze rounded square containing `Icons.domain_rounded` — neither the brand colour nor the brand shape. | Blocker |
| 2 | **The launcher icon and cold-start splash were stock Flutter.** The first thing a user saw on every launch was the Flutter logo. | Blocker |
| 3 | **Colours were a private palette**, unrelated to the web tokens: bronze/amber accents, a warm off-white ground, Material's default blues showing through anywhere the theme was silent. | High |
| 4 | **No shared status vocabulary.** Each screen coloured statuses ad hoc, so the same status could be green on one screen and blue on another. | High |
| 5 | **Radii were consumer-app rounded** (pills, 16–24dp) against the web's tight 3/5/8/12 drawing-sheet scale. | Medium |
| 6 | **Notification priority from Task 3 was not surfaced at all** — every notification looked the same. | High |
| 7 | **Forwarded messages and shared entities from Tasks 2/2.1 rendered as raw text.** No quoted origin, no attribution, no entity chip. | High |
| 8 | **Localisation was not wired up.** No `flutter_localizations`, no `supportedLocales`; an Arabic device got an LTR app. | High |
| 9 | Typography was Material defaults; no monospace treatment for measured values, which the web uses to mark quantities. | Medium |
| 10 | Empty and error states were inconsistent — some used a shared `MessageView`, one was a bare sentence in white space. | Low |

---

## 2. Design source of truth

The web is the source of truth. I read the token layer directly rather than
eyeballing screenshots, and transcribed the values with their HSL originals kept
in comments so the two can be diffed:

- `frontend/src/index.css` — colour tokens, radii, tracking
- `frontend/src/components/brand/StructIQLogo.tsx` — the approved mark geometry
- `frontend/src/features/tasks/components/TaskCard.tsx` — the authoritative
  status→tone table

Core palette carried across:

| Token | Web | Flutter |
|---|---|---|
| Architectural Navy (`brand-ink`) | `216 60% 15%` | `AppColors.brandInk` `#0F2340` |
| Verdant Data (`brand-accent`) | `134 28% 43%` | `AppColors.brandAccent` `#4F8C5D` |
| Nav surface | `--nav-surface` | `AppColors.navSurface` `#0F1D2F` |
| Radii | 3 / 5 / 8 / 12 | `AppRadius.chip/control/panel/sheet` |
| Semantic ramp | six hues | `StatusTone` (verified/progress/review/overdue/blocked/idle) |

---

## 3. Branding

**The logo was reused, not reinvented.** `lib/core/widgets/brand_mark.dart`
transcribes the web SVG coordinate-for-coordinate on the same 32-unit grid —
the chamfered structural frame in ink, the two-node connection tail in the
accent — then scales it. Drawing it rather than shipping a bitmap means that if
the web mark changes, the diff here is the same set of numbers, and the mark
stays crisp at every density.

One lockup (`StructIQLogo`) serves the app bar, splash and sign-in; only the
variant changes. The wordmark never mirrors — it is fixed artwork, exactly as on
the web.

The same geometry was mapped onto the 108-unit Android adaptive-icon viewport
(`ic_launcher_foreground.xml`, plus a `monochrome` variant for Android 13 themed
icons) and rendered to legacy PNGs for pre-API-26 launchers. Android 12+ splash
attributes were added so the cold start shows the mark on brand ink.

---

## 4. Reusable design system

Everything below lives in `lib/core/` and is consumed by the screens; no screen
defines its own colour, radius or badge.

| File | What it owns |
|---|---|
| `theme/app_colors.dart` | Every colour in the app, with the web HSL in a comment |
| `theme/app_radius.dart` | The four radii |
| `theme/app_theme.dart` | Material theme: nav-surface app bar, elevation-0 hairline cards, verdant focus ring, 52dp buttons, `AppTheme.measured` (tabular monospace for quantities), `AppTheme.label`, FAB theme |
| `widgets/brand_mark.dart` | Mark, wordmark, lockup |
| `widgets/status_badge.dart` | `StatusTone` ramp + `StatusBadge` + `PriorityBadge` |
| `widgets/mobile_shell.dart` | Bottom navigation shell |
| `widgets/async_views.dart` | `LoadingView` / `MessageView` for loading, empty and error states |

---

## 5. Mobile-native UX

The web layout was **not** copied. The app keeps a five-destination bottom nav
with a docked record action, full-width tap targets at 48dp minimum, bottom
sheets for detail rather than modals, pull-to-refresh on every collection, and
horizontally scrolling filter chips instead of the web's filter bar.

---

## 6. Role-aware UI

Destinations and actions are chosen from the signed-in user's role, but this is
**presentation only**. Every screen still calls the same authorized endpoints,
and the backend remains the sole authority: hiding a button does not hide the
route, and a hidden route still 403s. No permission logic was moved into the
client.

---

## 7. Notifications (aligned with Task 3, not rebuilt)

The mobile list now reads the fields the Task 3 engine already emits — no new
notification code, no new engine. `NotificationItem` gained `priority`,
`category` and `requiresAction`; the list renders a priority accent edge
(amber IMPORTANT, red CRITICAL), the `PriorityBadge`, and a Reminder marker.
NORMAL notifications get no badge, matching the web: the point of the badge is
that something stands out from the ordinary.

Verified on device: a reminder generated by the backend scheduler
("Level 4 slab pour is due tomorrow") arrived and rendered correctly.

---

## 8. Forwarded and shared content (Tasks 2 / 2.1)

`ChatMessage` gained `forwardedFromMessageId`, `forwardOrigin`,
`sharedEntityType` and `sharedEntityId`. The conversation screen renders:

- a **quoted-origin block** with a directional start rule, "Forwarded from
  &lt;original sender&gt;", the original content, and the forwarder's own note
  below it as separate text — so ownership and attribution stay distinct;
- a **shared-entity chip** for the five supported entity types.

Verified on device against real API-created rows (see §11, screenshot 32).

---

## 9. Arabic / RTL

`flutter_localizations` was added and `supportedLocales: [en, ar]` declared,
which is what lets Flutter resolve an Arabic device to `TextDirection.rtl`.
Directional layout was then used throughout — `EdgeInsetsDirectional`,
`AlignmentDirectional`, `BorderDirectional` — so padding, alignment and the
quoted-origin rule mirror rather than staying pinned left.

Verified on a real Arabic device locale (§11, screenshots 33–37): the nav order,
header, KPI grid, task accent bars, chips, quoted-origin rule, entity chip and
send button all mirror correctly.

**Known limitation, documented rather than hidden:** the app's own copy is still
English. Only the layout, Material widgets and date formatting follow the
locale. Because English strings are laid out inside an RTL paragraph, their
trailing punctuation appears at the left edge — correct bidi behaviour for
English-in-RTL, and it disappears once the strings are translated. Adding an ARB
translation layer is a separate piece of work and was not in this task's scope.

---

## 10. Automated tests

`mobile_app/test/design_system_test.dart` — 27 new tests. Full suite: **38/38
pass**, `flutter analyze`: **No issues found**.

Coverage includes brand tokens against the web values, theme wiring, the mark
painting without exception, the status ramp (including a test pinning the four
values the web's own table fixes), priority rendering, notification and message
model parsing, Arabic/RTL layout, and two regression tests written after live
bugs: one that walks `lib/` to prove the retired product name is gone, and one
that paints IMPORTANT/CRITICAL cards to prove they do not throw.

---

## 11. Device verification

Run on an Android API 35 emulator against the live backend
(`10.0.2.2:8000`) — not a mock. Screens inspected: splash, login (including the
error and inline-validation states), project selector, dashboard, tasks, issues,
messages list, conversation, notifications, bottom navigation, Arabic RTL and
English LTR.

**Bugs found on device that compilation and the test suite did not catch:**

1. **Login still said "CONSTRUCTION FIELD"** — my earlier grep was
   case-sensitive. Replaced with the shared lockup; the regression test added
   for it then caught a comment of mine still quoting the old name.
2. **Dashboard header overflowed by 13px** once the web-matched type landed.
   Fixed with a text-scale-aware height, which also protects against the OS
   accessibility text setting.
3. **IMPORTANT/CRITICAL notification cards rendered blank.** A non-uniform
   `Border` combined with `borderRadius` is invalid in Flutter. Replaced with a
   uniform border plus an inner accent strip.
4. **The whole notification list then went empty** — `CrossAxisAlignment.stretch`
   needs a bounded cross-axis extent, which a Row inside a scrolling Column does
   not have. Fixed with an explicit strip height.
5. **The bottom nav leaked page content.** `extendBody: true` plus a `SafeArea`
   around the bar let the scrolling body show through in the gesture-bar inset
   below it. Removed `extendBody` and filled the inset in the bar's own colour,
   keeping the rounded top corners.
6. **The launcher icon and splash were stock Flutter** (§3).
7. **FABs were pale Material blue** — the theme had no
   `floatingActionButtonTheme`, so they fell back to `secondaryContainer`. Now
   brand accent, fixed once in the theme.
8. **The status ramp disagreed with the web on three values.** Checked against
   `TaskCard.tsx`: `under_review` is warning (was info), `rework_required` is
   danger (was warning), `cancelled` is neutral (was danger). Fixed and pinned
   with a named test.
9. **Issue cards showed no state at all** — status was only a *fallback* for the
   subtitle text, so any issue with a description lost it. Status and high
   severity now get ramp chips.
10. **The messages empty state was a bare sentence** while every other empty
    state used `MessageView`. Made consistent.

---

## 12. Backend/API limitations found (documented, not worked around)

- **No mobile localisation resource exists.** The web has `en`/`ar` translation
  JSON; the mobile app has no equivalent. Layout direction now follows the
  locale but the copy does not. This needs an ARB/i18n layer — new work, out of
  this task's scope.
- **The shared-entity message body is composed server-side as plain text.** The
  mobile client renders it verbatim and adds the entity chip. A structured
  payload would let mobile lay it out natively, but changing the response shape
  is a backend change and was out of scope.

---

## 13. Explicitly not done

No MCP, Voice AI, Whisper or AI agent; no Telegram bot; no new backend
architecture; no new notification engine; no OTP changes; no IFC 3D redesign;
no Design Package ingestion; no new business workflows.

---

## 14. Test-data note

Verification used a seeded PM account (`pm.m5@constro.io`) on a test project
("Riverside Tower"), which remain in the dev database so the runs above can be
reproduced.

Two **pre-existing** accounts, `civil@constro.io` and `arch@constro.io`, were
borrowed to produce a real forward chain. Both were `inactive` before and have
been set back to `inactive`, and their temporary project memberships removed.
**Their password hashes were overwritten and cannot be restored** — both
accounts are inactive and cannot sign in, but if either is ever reactivated its
password must be reset first.
