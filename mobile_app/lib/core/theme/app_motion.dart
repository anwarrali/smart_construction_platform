import 'package:flutter/animation.dart';

/// Motion tokens.
///
/// One scale for the whole app, so a transition cannot be 180ms on one screen
/// and 400ms on the next. The rule the product follows: animation exists to
/// explain a change of state, never to decorate. Anything a person waits on
/// is [fast]; anything that merely acknowledges a touch is [instant].
abstract final class AppMotion {
  /// Touch feedback, chip selection — perceptible but never a delay.
  static const Duration instant = Duration(milliseconds: 120);

  /// The default: navigation indicator travel, expand/collapse, sheet content.
  static const Duration fast = Duration(milliseconds: 220);

  /// Page-level transitions only.
  static const Duration page = Duration(milliseconds: 280);

  /// Decelerating ease. Used for anything that moves to a new resting place;
  /// it arrives without the overshoot that reads as playful.
  static const Curve standard = Curves.easeOutCubic;

  /// For things that fade rather than travel.
  static const Curve fade = Curves.easeOut;
}
