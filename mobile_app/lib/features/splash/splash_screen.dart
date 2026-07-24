import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/brand_mark.dart';

class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: AppColors.navyDeep,
    body: Stack(
      fit: StackFit.expand,
      children: [
        const ColoredBox(color: AppColors.navy),
        SafeArea(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const BrandMark(),
                const SizedBox(height: 22),
                const Text(
                  'Construction Field',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -.3,
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Projects connected. Field work simplified.',
                  style: TextStyle(color: Colors.white60, fontSize: 12),
                ),
                const SizedBox(height: 36),
                const SizedBox.square(
                  dimension: 28,
                  child: CircularProgressIndicator(
                    color: AppColors.bronze,
                    strokeWidth: 2.5,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    ),
  );
}
