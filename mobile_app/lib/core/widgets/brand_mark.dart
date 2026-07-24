import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.compact = false});
  final bool compact;

  @override
  Widget build(BuildContext context) => Container(
    width: compact ? 42 : 54,
    height: compact ? 42 : 54,
    decoration: BoxDecoration(
      color: AppColors.bronze,
      borderRadius: BorderRadius.circular(compact ? 13 : 17),
      boxShadow: [
        BoxShadow(
          color: AppColors.bronze.withValues(alpha: .28),
          blurRadius: 18,
          offset: const Offset(0, 8),
        ),
      ],
    ),
    child: Icon(
      Icons.domain_rounded,
      color: Colors.white,
      size: compact ? 24 : 30,
    ),
  );
}
