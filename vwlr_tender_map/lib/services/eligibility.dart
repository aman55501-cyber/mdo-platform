import '../models/tender.dart';
import '../models/org_profile.dart';

class Check {
  final String label;
  final bool? pass; // null = not applicable / no published requirement
  final String detail;
  Check(this.label, this.pass, this.detail);
}

class Eligibility {
  final List<Check> checks;
  Eligibility(this.checks);

  /// eligible = every applicable check passes.
  bool get eligible =>
      checks.where((c) => c.pass != null).every((c) => c.pass == true) &&
      checks.any((c) => c.pass != null);

  bool get noPublishedCriteria => checks.every((c) => c.pass == null);
}

Eligibility assess(Tender t, OrgProfile o) {
  final checks = <Check>[];

  if (t.qrMinTurnoverInr != null && o.avgTurnoverInr != null) {
    final ok = o.avgTurnoverInr! >= t.qrMinTurnoverInr!;
    checks.add(Check('Avg. turnover', ok,
        'Need ${_cr(t.qrMinTurnoverInr!)} · you have ${_cr(o.avgTurnoverInr!)}'));
  }

  if (t.qrExperienceMt != null && o.maxExperienceMt != null) {
    final ok = o.maxExperienceMt! >= t.qrExperienceMt!;
    checks.add(Check('Past experience', ok,
        'Need ${_mt(t.qrExperienceMt!)} in ${t.qrExperienceWindowMonths ?? '?'} mo · your best ${_mt(o.maxExperienceMt!)}'));
  }

  if (t.qrNetworthPct != null &&
      o.netWorthInr != null &&
      o.paidUpCapitalInr != null) {
    final need = (t.qrNetworthPct! / 100.0) * o.paidUpCapitalInr!;
    final ok = o.netWorthInr! >= need;
    checks.add(Check('Net worth', ok,
        'Need ≥ ${t.qrNetworthPct}% of paid-up capital (${_cr(need)})'));
  }

  return Eligibility(checks);
}

String _cr(num v) => '₹${(v / 10000000).toStringAsFixed(2)} Cr';
String _mt(num v) => '${(v / 1000).toStringAsFixed(0)}k MT';
