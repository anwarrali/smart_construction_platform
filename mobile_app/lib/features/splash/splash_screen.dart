import 'package:flutter/material.dart';

import '../../core/l10n/l10n_labels.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/brand_mark.dart';

/// The first thing a user sees, and the first statement of the brand.
///
/// Navy ground with the lockup inverted, matching the web's navigation rail —
/// the one dark surface in the product.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: AppColors.navSurface,
    body: SafeArea(
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const StructIQLogo(size: 44, inverted: true),
            const SizedBox(height: 10),
            Text(
              context.l10n.brandDescriptor,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.62),
                fontSize: 12,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.02, // --tracking-label
              ),
            ),
            const SizedBox(height: 40),
            const SizedBox.square(
              dimension: 24,
              child: CircularProgressIndicator(
                // Verdant: the product signalling that it is working.
                color: AppColors.navMark,
                strokeWidth: 2.5,
              ),
            ),
          ],
        ),
      ),
    ),
  );
}
