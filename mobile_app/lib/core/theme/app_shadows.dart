import 'package:flutter/material.dart';

abstract final class AppShadows {
  static const card = [
    BoxShadow(color: Color(0x0D15213A), blurRadius: 18, offset: Offset(0, 6)),
  ];
  static const elevated = [
    BoxShadow(color: Color(0x24121A2D), blurRadius: 28, offset: Offset(0, 12)),
  ];
}
