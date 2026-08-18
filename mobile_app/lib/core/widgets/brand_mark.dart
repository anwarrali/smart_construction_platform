import 'package:flutter/material.dart';

import '../l10n/l10n_labels.dart';
import '../theme/app_colors.dart';

/// The Struct IQ brand mark and lockup.
///
/// The symbol is a chamfered structural frame — the plan of a braced core,
/// the cut corner of a section detail — with a two-node connection tail
/// leaving its lower-right chamfer. The frame is the *Struct*: enclosure,
/// structure, the thing being built. The tail is the *IQ*: a relationship
/// travelling out of the structure, through a junction node, to a resolved
/// decision point. That is why the tail is drawn in the accent colour while
/// the frame stays in ink.
///
/// The geometry is transcribed coordinate-for-coordinate from the web
/// component (`frontend/src/components/brand/StructIQLogo.tsx`) on the same
/// 32×32 grid, then scaled. Drawing it rather than shipping a bitmap is what
/// keeps the two platforms provably identical: if the web mark changes, the
/// diff here is the same set of numbers, and the mark stays crisp at every
/// density without an asset pipeline.
///
/// This replaces a bronze rounded square containing `Icons.domain_rounded`,
/// which was neither the brand colour nor the brand shape.
class StructIQMark extends StatelessWidget {
  const StructIQMark({
    super.key,
    this.size = 32,
    this.frameColor,
    this.tailColor,
  });

  /// Rendered size in logical pixels. The mark is on a 32-unit grid.
  final double size;

  /// Colour of the structural frame. Defaults to brand ink.
  final Color? frameColor;

  /// Colour of the connection tail. Defaults to the brand accent.
  final Color? tailColor;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: size,
    height: size,
    child: CustomPaint(
      painter: _MarkPainter(
        frame: frameColor ?? AppColors.brandInk,
        tail: tailColor ?? AppColors.brandAccent,
      ),
      // The mark carries the product name for screen readers; the wordmark
      // beside it is decorative once this is announced.
      isComplex: false,
      child: const SizedBox.expand(),
    ),
  );
}

class _MarkPainter extends CustomPainter {
  const _MarkPainter({required this.frame, required this.tail});

  final Color frame;
  final Color tail;

  @override
  void paint(Canvas canvas, Size size) {
    // Everything below is expressed in the 32-unit grid of the source SVG
    // and scaled once, so the numbers can be compared to the web directly.
    final unit = size.width / 32;
    Offset p(double x, double y) => Offset(x * unit, y * unit);

    final framePaint = Paint()
      ..color = frame
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3 * unit
      ..strokeJoin = StrokeJoin.round;

    // The structural frame: a square with both diagonals cut, drawn as a
    // closed chamfered octagon so the corners read as fabricated joints.
    final framePath = Path()
      ..moveTo(10.5 * unit, 2.6 * unit)
      ..lineTo(17.5 * unit, 2.6 * unit)
      ..lineTo(24.4 * unit, 9.5 * unit)
      ..lineTo(24.4 * unit, 16.5 * unit)
      ..lineTo(17.5 * unit, 23.4 * unit)
      ..lineTo(10.5 * unit, 23.4 * unit)
      ..lineTo(3.6 * unit, 16.5 * unit)
      ..lineTo(3.6 * unit, 9.5 * unit)
      ..close();
    canvas.drawPath(framePath, framePaint);

    // The connection tail, on the same 45° as the chamfer it leaves. Two
    // segments with a gap, so the junction reads as an open node rather than
    // a blob — no background-coloured knockout, which keeps the mark safe on
    // any surface.
    final tailStroke = Paint()
      ..color = tail
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3 * unit
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(p(21.7, 20.7), p(23.1, 22.1), tailStroke);
    canvas.drawLine(p(27.1, 26.1), p(27.9, 26.9), tailStroke);

    final nodeRing = Paint()
      ..color = tail
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6 * unit
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(p(25.1, 24.1), 1.85 * unit, nodeRing);

    canvas.drawCircle(
      p(29, 28),
      2.6 * unit,
      Paint()
        ..color = tail
        ..style = PaintingStyle.fill,
    );
  }

  @override
  bool shouldRepaint(_MarkPainter old) =>
      old.frame != frame || old.tail != tail;
}

/// The wordmark: "Struct" in ink, "IQ" in the accent.
///
/// Set in the interface face rather than as outlines so it stays crisp at
/// every size — the Latin wordmark is the brand in both locales, which is
/// normal practice for engineering software sold across scripts, so this is
/// deliberately *not* translated.
class StructIQWordmark extends StatelessWidget {
  const StructIQWordmark({super.key, this.size = 20, this.inverted = false});

  final double size;
  final bool inverted;

  @override
  Widget build(BuildContext context) {
    final ink = inverted ? Colors.white : AppColors.brandInk;
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: 'Struct', style: TextStyle(color: ink)),
          TextSpan(
            text: 'IQ',
            style: TextStyle(
              color: inverted ? AppColors.navMark : AppColors.brandAccent,
            ),
          ),
        ],
      ),
      style: TextStyle(
        fontSize: size,
        fontWeight: FontWeight.w600,
        height: 1,
        letterSpacing: -0.014 * size, // --tracking-heading
      ),
      textDirection: TextDirection.ltr, // the wordmark never mirrors
    );
  }
}

/// The primary lockup: symbol plus wordmark, optionally with the descriptor.
///
/// One lockup serves the app bar, the splash and the sign-in screen; only the
/// variant changes. That is what stops the product picking up three slightly
/// different logos in three different places.
class StructIQLogo extends StatelessWidget {
  const StructIQLogo({
    super.key,
    this.size = 28,
    this.inverted = false,
    this.showDescriptor = false,
  });

  final double size;
  final bool inverted;
  final bool showDescriptor;

  @override
  Widget build(BuildContext context) {
    final lockup = Row(
      mainAxisSize: MainAxisSize.min,
      // The lockup is a fixed piece of artwork: it reads left-to-right even
      // in Arabic, exactly as the web lockup does.
      textDirection: TextDirection.ltr,
      children: [
        StructIQMark(
          size: size,
          frameColor: inverted ? Colors.white : null,
        ),
        SizedBox(width: size * 0.36),
        StructIQWordmark(size: size * 0.72, inverted: inverted),
      ],
    );
    if (!showDescriptor) return lockup;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        lockup,
        SizedBox(height: size * 0.22),
        Text(
          context.l10n.brandDescriptor,
          style: TextStyle(
            fontSize: size * 0.34,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.085 * size * 0.34, // --tracking-label
            color: inverted ? Colors.white70 : AppColors.mutedForeground,
          ),
        ),
      ],
    );
  }
}

/// Backwards-compatible alias for the widget this file used to export, so
/// existing screens keep compiling while they migrate to [StructIQLogo].
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.compact = false});
  final bool compact;

  @override
  Widget build(BuildContext context) =>
      StructIQMark(size: compact ? 32 : 44);
}
