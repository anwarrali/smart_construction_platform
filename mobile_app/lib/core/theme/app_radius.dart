/// Corner radii, matching the web tokens exactly.
///
/// The previous mobile scale (10/14/20/28) was markedly rounder than the web
/// and made the app read as a consumer product rather than as engineering
/// software. These are the web's `--radius-*` values unchanged: softer than
/// legacy enterprise, tighter than consumer.
abstract final class AppRadius {
  /// `--radius-chip: 3px`.
  static const double chip = 3;

  /// `--radius-control: 5px` — buttons, inputs, the default.
  static const double control = 5;

  /// `--radius-panel: 8px` — cards and panels.
  static const double panel = 8;

  /// `--radius-sheet: 12px` — bottom sheets and dialogs.
  static const double sheet = 12;
}
