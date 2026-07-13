import '../models/tender.dart';

/// VWLR bid appetite (from the eligibility questionnaire, Section E).
/// These gate/annotate what surfaces in the list — mirrors the web dashboard.
class Appetite {
  /// Q25: only the "Big" filter requires clearing this value floor (₹250 Cr).
  static const num minValueInr = 2500000000;

  /// Q28: 5% performance BG up to ₹8 Cr backs a contract of ~₹160 Cr.
  static const num pbgCapacityInr = 80000000;
  static const num bgCeilingInr = pbgCapacityInr / 0.05;

  /// Q27: preferred buyers — matched as lowercase substrings of the authority.
  static const List<String> preferredBuyers = [
    'ntpc', 'nalco', 'secl', 'south eastern coalfields', 'mcl', 'mahanadi',
    'cspgcl', 'adani', 'tata power', 'tata', 'jsw', 'jindal', 'vedanta',
    'hindalco', 'ultratech', 'nuppl', 'mppgcl', 'nabha', 'mahagenco',
    'jhabua', 'dhariwal', 'cspdcl', 'apgenco', 'ppgcl', 'cesc',
  ];

  static bool isPreferred(Tender t) {
    final a = (t.authority ?? '').toLowerCase();
    return preferredBuyers.any((b) => a.contains(b));
  }

  /// Contract value would need a PBG above the ₹8 Cr capacity.
  static bool bgShort(Tender t) =>
      t.valueInr != null && t.valueInr! > bgCeilingInr;

  /// Clears the ₹250 Cr floor. Unknown value gets the benefit of the doubt.
  static bool meetsFloor(Tender t) =>
      t.valueInr == null || t.valueInr! >= minValueInr;
}
