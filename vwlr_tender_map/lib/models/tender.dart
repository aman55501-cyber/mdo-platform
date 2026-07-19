import 'tender_location.dart';

enum TenderStatus { live, bidding, won, lost, closed }

TenderStatus statusFrom(String? s) {
  switch (s) {
    case 'bidding':
      return TenderStatus.bidding;
    case 'won':
      return TenderStatus.won;
    case 'lost':
      return TenderStatus.lost;
    case 'closed':
      return TenderStatus.closed;
    default:
      return TenderStatus.live;
  }
}

String statusName(TenderStatus s) => s.name;

num? _n(v) => v == null ? null : (v is num ? v : num.tryParse(v.toString()));
int? _i(v) => v == null ? null : (v is int ? v : int.tryParse(v.toString()));

class Tender {
  final String id;
  final String? refNo;
  final String title;
  final String? authority;
  final String? portal;
  final String? sourceField;
  final num? valueInr;
  final num? emdInr;
  final num? pbgInr;
  final DateTime? deadline;
  final DateTime? techOpen;
  final num? contractMonths;
  final num? qrMinTurnoverInr;
  final num? qrExperienceMt;
  final int? qrExperienceWindowMonths;
  final int? qrNetworthPct;
  final num? qrNetworthInr;
  final num? qrExperienceValueInr;
  final num? qrSolvencyInr;
  final int? relevanceScore;
  final String? eligibilityNotes;
  final String? pdfUrl;
  final TenderStatus status;
  final bool hearted;
  final bool pursued;
  final String bidStage;
  final Map<String, dynamic> bidChecklist;
  final List<TenderLocation> locations;

  Tender({
    required this.id,
    this.refNo,
    required this.title,
    this.authority,
    this.portal,
    this.sourceField,
    this.valueInr,
    this.emdInr,
    this.pbgInr,
    this.deadline,
    this.techOpen,
    this.contractMonths,
    this.qrMinTurnoverInr,
    this.qrExperienceMt,
    this.qrExperienceWindowMonths,
    this.qrNetworthPct,
    this.qrNetworthInr,
    this.qrExperienceValueInr,
    this.qrSolvencyInr,
    this.relevanceScore,
    this.eligibilityNotes,
    this.pdfUrl,
    this.status = TenderStatus.live,
    this.hearted = false,
    this.pursued = false,
    this.bidStage = 'interested',
    this.bidChecklist = const {},
    this.locations = const [],
  });

  factory Tender.fromMap(Map<String, dynamic> m,
      {List<TenderLocation> locations = const []}) {
    DateTime? p(v) => v == null ? null : DateTime.tryParse(v.toString());
    return Tender(
      id: m['id'],
      refNo: m['ref_no'],
      title: m['title'],
      authority: m['authority'],
      portal: m['portal'],
      sourceField: m['source_field'],
      valueInr: _n(m['value_inr']),
      emdInr: _n(m['emd_inr']),
      pbgInr: _n(m['pbg_inr']),
      deadline: p(m['deadline']),
      techOpen: p(m['tech_open']),
      contractMonths: _n(m['contract_months']),
      qrMinTurnoverInr: _n(m['qr_min_turnover_inr']),
      qrExperienceMt: _n(m['qr_experience_mt']),
      qrExperienceWindowMonths: _i(m['qr_experience_window_months']),
      qrNetworthPct: _i(m['qr_networth_pct']),
      qrNetworthInr: _n(m['qr_networth_inr']),
      qrExperienceValueInr: _n(m['qr_experience_value_inr']),
      qrSolvencyInr: _n(m['qr_solvency_inr']),
      relevanceScore: _i(m['relevance_score']),
      eligibilityNotes: m['eligibility_notes'],
      pdfUrl: m['pdf_url'],
      status: statusFrom(m['status']),
      hearted: m['hearted'] ?? false,
      pursued: m['pursued'] ?? false,
      bidStage: m['bid_stage'] ?? 'interested',
      bidChecklist: (m['bid_checklist'] as Map?)?.cast<String, dynamic>() ?? {},
      locations: locations,
    );
  }

  List<TenderLocation> get mines =>
      locations.where((l) => l.role == LocRole.mine).toList();
  TenderLocation? get plant => locations
      .cast<TenderLocation?>()
      .firstWhere((l) => l!.role == LocRole.plant, orElse: () => null);

  int? get daysLeft => deadline == null
      ? null
      : deadline!.difference(DateTime.now()).inHours ~/ 24;
}
