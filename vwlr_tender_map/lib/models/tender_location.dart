enum LocRole { mine, plant, siding, base }

LocRole _role(String? s) {
  switch (s) {
    case 'plant':
      return LocRole.plant;
    case 'siding':
      return LocRole.siding;
    case 'base':
      return LocRole.base;
    default:
      return LocRole.mine;
  }
}

class TenderLocation {
  final String id;
  final String? tenderId;
  final LocRole role;
  final String name;
  final double lat;
  final double lng;
  final String? district;
  final String? state;
  final String? pin;
  final num? roadKmFromBase;
  final String? notes;

  TenderLocation({
    required this.id,
    this.tenderId,
    required this.role,
    required this.name,
    required this.lat,
    required this.lng,
    this.district,
    this.state,
    this.pin,
    this.roadKmFromBase,
    this.notes,
  });

  factory TenderLocation.fromMap(Map<String, dynamic> m) => TenderLocation(
        id: m['id'],
        tenderId: m['tender_id'],
        role: _role(m['role']),
        name: m['name'],
        lat: (m['lat'] as num).toDouble(),
        lng: (m['lng'] as num).toDouble(),
        district: m['district'],
        state: m['state'],
        pin: m['pin'],
        roadKmFromBase: m['road_km_from_base'] == null ? null : (m['road_km_from_base'] is num ? m['road_km_from_base'] : num.tryParse(m['road_km_from_base'].toString())),
        notes: m['notes'],
      );
}
