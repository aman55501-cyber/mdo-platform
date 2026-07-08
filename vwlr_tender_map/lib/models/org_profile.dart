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
  final bool isMsme;
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
    this.isMsme = true,
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
        isMsme: m['is_msme'] ?? true,
        operatingRadiusKm: _i(m['operating_radius_km'], 300),
      );
}
