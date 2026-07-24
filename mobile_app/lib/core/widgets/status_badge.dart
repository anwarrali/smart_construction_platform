import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.value, {super.key, this.compact = false});
  final String value;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final (color, background) = switch (value) {
      'done' ||
      'approved' ||
      'active' => (AppColors.success, AppColors.successSoft),
      'blocked' ||
      'rejected' ||
      'critical' => (AppColors.danger, AppColors.dangerSoft),
      'under_review' ||
      'rework_required' ||
      'high' ||
      'delayed' => (AppColors.warning, AppColors.warningSoft),
      'in_progress' => (AppColors.info, AppColors.infoSoft),
      _ => (AppColors.navy, AppColors.surfaceMuted),
    };
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 7 : 9,
        vertical: compact ? 4 : 5,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Text(
        value.replaceAll('_', ' '),
        maxLines: 1,
        style: TextStyle(
          color: color,
          fontSize: compact ? 10 : 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
