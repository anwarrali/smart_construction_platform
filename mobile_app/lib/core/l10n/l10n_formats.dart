import 'package:flutter/widgets.dart';
import 'package:intl/intl.dart';

/// Locale-aware presentation of dates, times and numbers.
///
/// Every call takes the locale from the widget tree rather than relying on
/// `Intl.defaultLocale`, which is process-global and would make a screen's
/// formatting depend on whatever ran last. Nothing here changes stored data:
/// these format values on the way to the screen only.
extension L10nFormats on BuildContext {
  String get _localeName => Localizations.localeOf(this).toLanguageTag();

  /// Forces one numbering system across the app.
  ///
  /// On device, `intl` renders Arabic *dates* with Arabic-Indic digits
  /// (١٧ أغسطس) but Arabic *numbers* with Western ones (40%), so a single
  /// screen showed two numbering systems side by side. The web renders
  /// Western digits in Arabic throughout, so that is the one to match — and
  /// matching the web is the rule this whole task follows.
  static String _westernDigits(String value) {
    const arabicIndicZero = 0x0660;
    return value.replaceAllMapped(RegExp('[٠-٩]'), (match) {
      final digit = match.group(0)!.codeUnitAt(0) - arabicIndicZero;
      return '$digit';
    });
  }

  /// A short calendar date, e.g. "Aug 17" / "17 أغسطس".
  String formatShortDate(DateTime value) =>
      _westernDigits(DateFormat.MMMd(_localeName).format(value.toLocal()));

  /// A short date with the time, used on timestamps.
  String formatDateTime(DateTime value) => _westernDigits(
    DateFormat.MMMd(_localeName).add_jm().format(value.toLocal()),
  );

  /// Time of day only.
  String formatTime(DateTime value) =>
      _westernDigits(DateFormat.jm(_localeName).format(value.toLocal()));

  /// A whole number.
  ///
  /// Normalised to Western digits like everything else. Without this,
  /// `NumberFormat` rendered Arabic counts in Arabic-Indic digits while the
  /// dates above were already forced to Western ones, so a single card could
  /// show "٤٠" next to "17 أغسطس". The policy is one numbering system across
  /// the whole product, matching the web; grouping separators still come from
  /// the locale.
  String formatInt(num value) => _westernDigits(
    NumberFormat.decimalPattern(_localeName).format(value),
  );

  /// A rounded percentage, written with the locale's own percent sign.
  String formatPercent(num value) {
    final format = NumberFormat.percentPattern(_localeName)
      ..maximumFractionDigits = 0;
    return _westernDigits(format.format(value / 100));
  }

  /// A duration as mm:ss, for audio transport read-outs.
  String formatClock(Duration value) {
    final minutes = value.inMinutes.toString().padLeft(2, '0');
    final seconds = (value.inSeconds % 60).toString().padLeft(2, '0');
    // Always LTR and always Western: a clock read-out is a technical value,
    // and mirroring "01:20" into "20:10" would be a bug, not a translation.
    return '$minutes:$seconds';
  }
}
