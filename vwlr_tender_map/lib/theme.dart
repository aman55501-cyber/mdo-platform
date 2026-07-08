import 'package:flutter/material.dart';

const kBrand = Color(0xFF1F6FEB);
const kDanger = Color(0xFFE5484D);
const kWarn = Color(0xFFF5A623);
const kOk = Color(0xFF2FA84F);

ThemeData buildTheme() {
  return ThemeData(
    useMaterial3: true,
    colorSchemeSeed: kBrand,
    brightness: Brightness.light,
    scaffoldBackgroundColor: const Color(0xFFF6F8FB),
  );
}

/// Colour for deadline urgency.
Color urgencyColor(int? daysLeft) {
  if (daysLeft == null) return Colors.grey;
  if (daysLeft < 0) return Colors.grey;
  if (daysLeft <= 3) return kDanger;
  if (daysLeft <= 10) return kWarn;
  return kOk;
}
