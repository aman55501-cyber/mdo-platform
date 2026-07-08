import 'dart:math';

/// Great-circle distance in km between two lat/lng points.
double haversineKm(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371.0;
  double d(double x) => x * pi / 180.0;
  final dLat = d(lat2 - lat1);
  final dLng = d(lng2 - lng1);
  final a = sin(dLat / 2) * sin(dLat / 2) +
      cos(d(lat1)) * cos(d(lat2)) * sin(dLng / 2) * sin(dLng / 2);
  return r * 2 * atan2(sqrt(a), sqrt(1 - a));
}
