import '../models/org_profile.dart';
import '../models/tender.dart';
import 'format.dart';

/// The bid pipeline stages, in order.
const List<String> bidStages = [
  'interested',
  'preparing',
  'submitted',
  'won',
  'lost',
];

String bidStageLabel(String s) => switch (s) {
      'interested' => 'Interested',
      'preparing' => 'Preparing',
      'submitted' => 'Submitted',
      'won' => 'Won',
      'lost' => 'Lost',
      _ => s,
    };

class BidStep {
  final String key;
  final String label;
  final String Function(Tender t, OrgProfile o) detail;
  const BidStep(this.key, this.label, this.detail);
}

/// The action checklist shown for every pursued tender, with the tender's own
/// numbers (EMD, 5% PBG, deadline) filled in against VWLR's profile.
final List<BidStep> bidSteps = [
  BidStep('doc', 'Download the tender document',
      (t, o) => 'Open the NIT from the portal and read the full PQC & scope'),
  BidStep(
      'pqc',
      'Assemble the pre-qualification pack',
      (t, o) =>
          'Turnover & net-worth certs, work-order/experience cert, solvency ₹, '
          'GST, PAN, MSME/Udyam, Class-I, no-blacklisting affidavit, fleet proof'),
  BidStep('emd', 'Arrange EMD / bid security', (t, o) {
    if (t.emdInr != null) return 'EMD ${inr(t.emdInr)}';
    return o.isMsme
        ? 'Likely MSME-exempt — confirm the exemption clause in the NIT'
        : 'Check the EMD amount in the NIT';
  }),
  BidStep('pbg', 'Confirm performance BG capacity (5%)', (t, o) {
    if (t.valueInr == null) return 'Contract value not published';
    final pbg = 0.05 * t.valueInr!;
    final ok = o.pbgCapacityInr == null || pbg <= o.pbgCapacityInr!;
    return '5% PBG = ${inr(pbg)}'
        '${ok ? ' — within your capacity' : ' — arrange a larger BG'}';
  }),
  BidStep('prebid', 'Attend the pre-bid meeting',
      (t, o) => 'Note queries; check the NIT for the pre-bid date/venue'),
  BidStep('submit', 'Submit technical + price bid', (t, o) {
    final d = t.daysLeft;
    if (t.deadline == null) return 'Before the published deadline';
    return 'Before ${dateFmt(t.deadline)}'
        '${d != null && d >= 0 ? ' · $d day${d == 1 ? '' : 's'} left' : ''}';
  }),
  BidStep('result', 'Track opening & result',
      (t, o) => t.techOpen != null
          ? 'Technical opening ${dateFmt(t.techOpen)}'
          : 'Watch for opening & award'),
];

int bidDone(Tender t) =>
    bidSteps.where((s) => t.bidChecklist[s.key] == true).length;
