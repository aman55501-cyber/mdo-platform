num? _n(v) => v == null ? null : (v is num ? v : num.tryParse(v.toString()));
int _i(v, int d) => v == null ? d : (v is int ? v : int.tryParse(v.toString()) ?? d);

class OrgProfile {
  final String name;
  final String? railwayCode;
  final double lat;
  final double lng;
  final String? address;
  final num? avgTurnoverInr;
  final num? netWorthInr;
  final num? paidUpCapitalInr;
  final num? maxExperienceMt;
  final int? experienceWindowMonths;
  final num? maxSingleMonthMt;
  final num? largestWorkOrderInr;
  final num? largestWorkOrderMt;
  final num? solvencyInr;
  final num? pbgCapacityInr;
  final bool isMsme;
  final bool isClass1;
  final bool isGem;
  final bool hasGst;
  final bool blacklisted;
  final int operatingRadiusKm;

  OrgProfile({
    required this.name,
    this.railwayCode,
    required this.lat,
    required this.lng,
    this.address,
    this.avgTurnoverInr,
    this.netWorthInr,
    this.paidUpCapitalInr,
    this.maxExperienceMt,
    this.experienceWindowMonths,
    this.maxSingleMonthMt,
    this.largestWorkOrderInr,
    this.largestWorkOrderMt,
    this.solvencyInr,
    this.pbgCapacityInr,
    this.isMsme = true,
    this.isClass1 = true,
    this.isGem = true,
    this.hasGst = true,
    this.blacklisted = false,
    this.operatingRadiusKm = 300,
  });

  factory OrgProfile.fromMap(Map<String, dynamic> m) => OrgProfile(
        name: m['name'] ?? 'VWLR',
        railwayCode: m['railway_code'],
        lat: (m['lat'] as num).toDouble(),
        lng: (m['lng'] as num).toDouble(),
        address: m['address'],
        avgTurnoverInr: _n(m['avg_turnover_inr']),
        netWorthInr: _n(m['net_worth_inr']),
        paidUpCapitalInr: _n(m['paid_up_capital_inr']),
        maxExperienceMt: _n(m['max_experience_mt']),
        experienceWindowMonths: m['experience_window_months'] == null ? null : _i(m['experience_window_months'], 0),
        maxSingleMonthMt: _n(m['max_single_month_mt']),
        largestWorkOrderInr: _n(m['largest_work_order_inr']),
        largestWorkOrderMt: _n(m['largest_work_order_mt']),
        solvencyInr: _n(m['solvency_inr']),
        pbgCapacityInr: _n(m['pbg_capacity_inr']),
        isMsme: m['is_msme'] ?? true,
        isClass1: m['is_class1'] ?? true,
        isGem: m['is_gem'] ?? true,
        hasGst: m['has_gst'] ?? true,
        blacklisted: m['blacklisted'] ?? false,
        operatingRadiusKm: _i(m['operating_radius_km'], 300),
      );
}
