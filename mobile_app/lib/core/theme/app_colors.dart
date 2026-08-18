import 'package:flutter/material.dart';

/// Struct IQ colour tokens, transcribed from the web design tokens in
/// `frontend/src/styles/variables.css`.
///
/// The identity is built from the logo outward: a chamfered structural frame
/// in **Architectural Navy** with a connection tail in **Verdant Data**, and
/// the interface reuses exactly that pair.
///
///   NAVY     structure, authority, the built thing. Primary actions,
///            headings, the navigation surface — the ink of the product.
///   VERDANT  intelligence, connection, the resolved decision. The active
///            mark, verified state, focus.
///
/// The three rules the web tokens state, which this file follows:
///
///   1. The ground is light. Site-office software stays bright and legible;
///      the only dark surface is the navigation, which frames the work the
///      way the mark frames its own tail.
///   2. Structure comes from line weight and space, not from a border,
///      shadow and radius on everything.
///   3. Colour is signal. Outside the two brand colours, chroma is reserved
///      for state a person must act on, and each hue means exactly one thing.
///
/// Values are the HSL tokens converted to RGB. Where a token is referenced
/// below, the comment carries the original HSL so a future drift between web
/// and mobile is a one-line diff rather than a guess.
abstract final class AppColors {
  // ── Brand constants ──────────────────────────────────────────────
  /// Architectural Navy — `--brand-ink: 216 60% 15%`.
  static const brandInk = Color(0xFF0F2340);

  /// Verdant Data — `--brand-accent: 134 28% 43%`.
  static const brandAccent = Color(0xFF4F8C5D);

  // ── Ground and panels ────────────────────────────────────────────
  /// `--background: 210 25% 98%` — a cool, bright technical ground.
  static const background = Color(0xFFF9FAFC);

  /// `--card: 0 0% 100%` — panels sit above the ground as white sheets.
  static const card = Color(0xFFFFFFFF);

  /// `--well: 210 22% 96%` — sunken wells for insets and read-outs.
  static const well = Color(0xFFF2F5F8);

  /// `--muted: 210 20% 94%`.
  static const muted = Color(0xFFEEF1F5);

  // ── Ink ──────────────────────────────────────────────────────────
  /// `--foreground: 216 38% 13%`.
  static const foreground = Color(0xFF15202E);

  /// `--muted-foreground: 215 13% 45%`.
  static const mutedForeground = Color(0xFF64707F);

  /// `--well-foreground: 216 14% 34%`.
  static const wellForeground = Color(0xFF4B5563);

  // ── Primary / accent ─────────────────────────────────────────────
  /// `--primary: 216 55% 19%` — navy lifted just enough to hold white text.
  static const primary = Color(0xFF16304B);
  static const primaryForeground = Color(0xFFF7F9FC);

  /// `--accent: 134 30% 38%` — the intelligence signal of the product.
  static const accent = Color(0xFF447E52);
  static const accentForeground = Color(0xFFFFFFFF);

  /// `--accent-wash: 134 34% 95%`.
  static const accentWash = Color(0xFFEDF7EF);

  /// `--destructive: 8 62% 48%`.
  static const destructive = Color(0xFFC63F2E);
  static const destructiveForeground = Color(0xFFFFFFFF);

  // ── Rules ────────────────────────────────────────────────────────
  /// `--border: 214 20% 90%` — a hairline that is visible but quiet.
  static const border = Color(0xFFDFE4EA);

  /// `--border-strong: 214 16% 79%` — the heavier cut rule.
  static const borderStrong = Color(0xFFC3CBD4);

  /// `--input: 214 18% 86%`.
  static const input = Color(0xFFD5DCE4);

  /// `--ring: 134 30% 38%` — focus is verdant, matching the web.
  static const ring = accent;

  // ── Status: one semantic ramp ────────────────────────────────────
  // Six hues, one meaning each, used identically in every module. This is
  // the same ramp the web uses; it replaced a scatter of colours that
  // carried no consistent meaning, so mobile must not reintroduce one.

  /// approved · signed off · on plan — `--state-verified: 140 34% 34%`.
  static const stateVerified = Color(0xFF39744F);

  /// under way · information — `--state-progress: 205 60% 42%`.
  static const stateProgress = Color(0xFF2B7CAB);

  /// at risk · awaiting a decision — `--state-review: 36 82% 44%`.
  static const stateReview = Color(0xFFCC8114);

  /// delayed · critical · past date — `--state-overdue: 8 62% 48%`.
  static const stateOverdue = Color(0xFFC63F2E);

  /// held by something else — `--state-blocked: 282 24% 48%`.
  static const stateBlocked = Color(0xFF7B5D98);

  /// not started · inactive — `--state-idle: 215 10% 60%`.
  static const stateIdle = Color(0xFF8D949E);

  // Tinted grounds for the same six, for chips and row washes.
  static const stateVerifiedWash = Color(0xFFEFF7F2);
  static const stateProgressWash = Color(0xFFEEF5FA);
  static const stateReviewWash = Color(0xFFFBF3E6);
  static const stateOverdueWash = Color(0xFFFBEFED);
  static const stateBlockedWash = Color(0xFFF6F2F8);
  static const stateIdleWash = Color(0xFFF1F3F5);

  // ── Navigation surface ───────────────────────────────────────────
  // Navy in both themes: the constant edge of the product, and the one
  // place the identity is stated without apology.
  /// `--sidebar: 216 52% 12%`.
  static const navSurface = Color(0xFF0F1D2F);

  /// `--sidebar-foreground: 212 20% 70%`.
  static const navForeground = Color(0xFFA3AFBF);

  /// `--sidebar-border: 216 40% 19%`.
  static const navBorder = Color(0xFF1D2C44);

  /// `--sidebar-mark: 134 38% 52%` — the active marker.
  static const navMark = Color(0xFF56B06B);
}
