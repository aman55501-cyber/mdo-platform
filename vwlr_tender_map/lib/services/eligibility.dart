import '../models/tender.dart';
import '../models/org_profile.dart';

class Check {
  final String label;
  final bool? pass; // null = requirement not published / can't verify yet
  final String detail;
  final bool hard; // hard checks gate eligibility; soft ones only inform
  Check(this.label, this.pass, this.detail, {this.hard = true});
}

class Eligibility {
  final List<Check> checks;
  Eligibility(this.checks);

  // A tender is judged only once its core gates (turnover / experience) are
  // known. Hard checks decide eligibility; soft ones (BG capacity, registrations)
  // only annotate.
  bool get _coreParsed => checks.any((c) =>
      (c.label == 'Avg. turnover' || c.label == 'Past experience') &&
      c.pass != null);
  bool get _hardFail => checks.any((c) => c.hard && c.pass == false);

  bool get eligible => _coreParsed && !_hardFail;
  bool get ineligible => _coreParsed && _hardFail;

  /// Criteria not yet parsed from the document — sits in the "Needs review" bucket.
  bool get needsReview => !_coreParsed;
  bool get noPublishedCriteria => !_coreParsed;
}

Eligibility assess(Tender t, OrgProfile o) {
  final checks = <Check>[];

  // 1) Turnover & net worth ------------------------------------------------
  if (t.qrMinTurnoverInr != null && o.avgTurnoverInr != null) {
    final ok = o.avgTurnoverInr! >= t.qrMinTurnoverInr!;
    checks.add(Check('Avg. turnover', ok,
        'Need ${_cr(t.qrMinTurnoverInr!)} · you have ${_cr(o.avgTurnoverInr!)}'));
  }
  // Net worth: absolute requirement, else % of the ESTIMATED CONTRACT VALUE
  // (never % of paid-up capital), else a simple positive-net-worth test.
  if (o.netWorthInr != null) {
    if (t.qrNetworthInr != null) {
      final ok = o.netWorthInr! >= t.qrNetworthInr!;
      checks.add(Check('Net worth', ok,
          'Need ${_cr(t.qrNetworthInr!)} · you have ${_cr(o.netWorthInr!)}'));
    } else if (t.qrNetworthPct != null && t.valueInr != null) {
      final need = (t.qrNetworthPct! / 100.0) * t.valueInr!;
      final ok = o.netWorthInr! >= need;
      checks.add(Check('Net worth', ok,
          'Need ≥ ${t.qrNetworthPct}% of contract value (${_cr(need)}) · you have ${_cr(o.netWorthInr!)}'));
    } else if (t.qrNetworthPct != null) {
      checks.add(Check('Net worth', null,
          'Need ≥ ${t.qrNetworthPct}% of contract value · value not published'));
    }
  }

  // 2) Experience (tonnage & work-order value) -----------------------------
  if (t.qrExperienceMt != null && o.maxExperienceMt != null) {
    final ok = o.maxExperienceMt! >= t.qrExperienceMt!;
    checks.add(Check('Past experience', ok,
        'Need ${_mt(t.qrExperienceMt!)} in ${t.qrExperienceWindowMonths ?? '?'} mo · your best ${_mt(o.maxExperienceMt!)}'));
  }
  if (t.qrExperienceValueInr != null) {
    if (o.largestWorkOrderInr != null) {
      final ok = o.largestWorkOrderInr! >= t.qrExperienceValueInr!;
      checks.add(Check('Similar-work value', ok,
          'Need ${_cr(t.qrExperienceValueInr!)} · your largest ${_cr(o.largestWorkOrderInr!)}'));
    } else {
      checks.add(Check('Similar-work value', null,
          'Need ${_cr(t.qrExperienceValueInr!)} · add your largest work order'));
    }
  }

  // 3) Solvency, EMD & PBG capacity ----------------------------------------
  if (t.qrSolvencyInr != null) {
    if (o.solvencyInr != null) {
      final ok = o.solvencyInr! >= t.qrSolvencyInr!;
      checks.add(Check('Bank solvency', ok,
          'Need ${_cr(t.qrSolvencyInr!)} · you have ${_cr(o.solvencyInr!)}'));
    } else {
      checks.add(Check('Bank solvency', null,
          'Need ${_cr(t.qrSolvencyInr!)} · solvency not on file'));
    }
  }
  if (t.valueInr != null && o.pbgCapacityInr != null) {
    final pbg = 0.05 * t.valueInr!;
    final ok = pbg <= o.pbgCapacityInr!;
    checks.add(Check('BG capacity', ok,
        '5% PBG ${_cr(pbg)} vs your ${_cr(o.pbgCapacityInr!)} capacity${ok ? '' : ' — arrange larger BG'}',
        hard: false));
  }

  // 4) Registrations, fleet & blacklisting ---------------------------------
  final regOk = o.hasGst && o.isMsme && !o.blacklisted;
  final regBits = <String>[
    if (o.hasGst) 'GST',
    if (o.isMsme) 'MSME',
    if (o.isClass1) 'Class-I',
    if (o.isGem) 'GeM',
  ].join(' · ');
  checks.add(Check(
      'Registrations & fleet',
      regOk ? true : false,
      o.blacklisted
          ? 'Blacklisting on record'
          : '$regBits · owned fleet · no blacklisting',
      hard: false));

  return Eligibility(checks);
}

String _cr(num v) => '₹${(v / 10000000).toStringAsFixed(2)} Cr';
String _mt(num v) => '${(v / 1000).toStringAsFixed(0)}k MT';
