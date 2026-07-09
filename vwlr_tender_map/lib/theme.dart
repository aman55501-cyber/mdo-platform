import 'package:flutter/material.dart';

/// Brand + semantic constants (kept for back-compat; prefer [AppColors] tokens
/// via `context` so both light and dark themes adapt).
const kBrand = Color(0xFF1F6FEB);
const kDanger = Color(0xFFE5484D);
const kWarn = Color(0xFFC8820A);
const kOk = Color(0xFF2FA84F);
const kViolet = Color(0xFF7B61FF);

/// Design tokens for the industrial coal / rail look, resolved per theme.
@immutable
class AppColors extends ThemeExtension<AppColors> {
  final Color brand;
  final Color ok, warn, danger, violet, closed;
  final Color okBg, warnBg, dangerBg, violetBg, closedBg, brandBg;
  final Color surface, surfaceAlt, hair, muted, faint;

  const AppColors({
    required this.brand,
    required this.ok,
    required this.warn,
    required this.danger,
    required this.violet,
    required this.closed,
    required this.okBg,
    required this.warnBg,
    required this.dangerBg,
    required this.violetBg,
    required this.closedBg,
    required this.brandBg,
    required this.surface,
    required this.surfaceAlt,
    required this.hair,
    required this.muted,
    required this.faint,
  });

  static const light = AppColors(
    brand: Color(0xFF1F6FEB),
    ok: Color(0xFF2FA84F),
    warn: Color(0xFFC8820A),
    danger: Color(0xFFE5484D),
    violet: Color(0xFF7B61FF),
    closed: Color(0xFF8A94A6),
    okBg: Color(0xFFE4F4E8),
    warnBg: Color(0xFFFBF0DA),
    dangerBg: Color(0xFFFCE7E8),
    violetBg: Color(0xFFECE8FF),
    closedBg: Color(0xFFECEFF3),
    brandBg: Color(0xFFE7F0FE),
    surface: Color(0xFFFFFFFF),
    surfaceAlt: Color(0xFFEDF1F7),
    hair: Color(0xFFE1E7F0),
    muted: Color(0xFF5B6675),
    faint: Color(0xFF8A94A6),
  );

  static const dark = AppColors(
    brand: Color(0xFF4C8DFF),
    ok: Color(0xFF46C46A),
    warn: Color(0xFFE6A93B),
    danger: Color(0xFFF26D71),
    violet: Color(0xFF9C86FF),
    closed: Color(0xFF7C8798),
    okBg: Color(0xFF12281A),
    warnBg: Color(0xFF2E2410),
    dangerBg: Color(0xFF331516),
    violetBg: Color(0xFF201B3A),
    closedBg: Color(0xFF1B2430),
    brandBg: Color(0xFF14263F),
    surface: Color(0xFF121A25),
    surfaceAlt: Color(0xFF18222F),
    hair: Color(0xFF26313F),
    muted: Color(0xFF93A0B2),
    faint: Color(0xFF6C7A8C),
  );

  @override
  AppColors copyWith() => this;

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    Color m(Color a, Color b) => Color.lerp(a, b, t)!;
    return AppColors(
      brand: m(brand, other.brand),
      ok: m(ok, other.ok),
      warn: m(warn, other.warn),
      danger: m(danger, other.danger),
      violet: m(violet, other.violet),
      closed: m(closed, other.closed),
      okBg: m(okBg, other.okBg),
      warnBg: m(warnBg, other.warnBg),
      dangerBg: m(dangerBg, other.dangerBg),
      violetBg: m(violetBg, other.violetBg),
      closedBg: m(closedBg, other.closedBg),
      brandBg: m(brandBg, other.brandBg),
      surface: m(surface, other.surface),
      surfaceAlt: m(surfaceAlt, other.surfaceAlt),
      hair: m(hair, other.hair),
      muted: m(muted, other.muted),
      faint: m(faint, other.faint),
    );
  }
}

/// Convenience accessor: `context.colors`.
extension AppColorsX on BuildContext {
  AppColors get colors => Theme.of(this).extension<AppColors>()!;
}

const _figures = [FontFeature.tabularFigures()];

/// Tabular-figure style for aligned numbers (values, counts, distances).
const TextStyle kNumStyle = TextStyle(fontFeatures: _figures);

ThemeData buildTheme([Brightness brightness = Brightness.light]) {
  final dark = brightness == Brightness.dark;
  final c = dark ? AppColors.dark : AppColors.light;
  final scheme = ColorScheme.fromSeed(
    seedColor: c.brand,
    brightness: brightness,
  ).copyWith(
    primary: c.brand,
    surface: c.surface,
    onSurface: dark ? const Color(0xFFE9F0F8) : const Color(0xFF0F1826),
  );

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor:
        dark ? const Color(0xFF0A0F16) : const Color(0xFFF4F6FA),
    extensions: [c],
    cardTheme: CardThemeData(
      color: c.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: c.hair),
      ),
      clipBehavior: Clip.antiAlias,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: dark ? const Color(0xFF0A0F16) : const Color(0xFFF4F6FA),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 18,
        fontWeight: FontWeight.w700,
        letterSpacing: -.2,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: c.surface,
      indicatorColor: c.brandBg,
      elevation: 3,
      labelTextStyle: WidgetStateProperty.all(
        TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600, color: c.muted),
      ),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
          color: s.contains(WidgetState.selected) ? c.brand : c.muted)),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: c.surface,
      selectedColor: c.brand,
      side: BorderSide(color: c.hair),
      labelStyle: TextStyle(fontWeight: FontWeight.w600, color: c.muted),
      secondaryLabelStyle: const TextStyle(
          color: Colors.white, fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
    ),
    dividerColor: c.hair,
  );
}

/// Colour for deadline urgency, adapting to the active theme.
Color urgencyColor(BuildContext context, int? daysLeft) {
  final c = context.colors;
  if (daysLeft == null || daysLeft < 0) return c.closed;
  if (daysLeft <= 3) return c.danger;
  if (daysLeft <= 10) return c.warn;
  return c.ok;
}
