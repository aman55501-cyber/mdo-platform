import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../config.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../models/tender_location.dart';
import '../services/format.dart';
import '../theme.dart';

class MapScreen extends StatefulWidget {
  final OrgProfile org;
  final List<Tender> tenders;
  final void Function(Tender) onOpen;
  const MapScreen(
      {super.key,
      required this.org,
      required this.tenders,
      required this.onOpen});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  GoogleMapController? _c;
  bool _showRadius = true;

  // Markers are colour-coded by each tender's priority tier (relevance score),
  // so the map reads "which of these is worth my time" at a glance.
  double _tierHue(int? score) {
    final s = score ?? 0;
    if (s >= 90) return BitmapDescriptor.hueGreen; // core RCR / washery
    if (s >= 80) return BitmapDescriptor.hueOrange; // rail-siding / rake
    if (s >= 72) return BitmapDescriptor.hueYellow; // power-plant / CHP
    return BitmapDescriptor.hueRose; // other coal transport
  }

  Color _tierColor(int? score) {
    final s = score ?? 0;
    if (s >= 90) return const Color(0xFF2E9B57);
    if (s >= 80) return const Color(0xFFD8871F);
    if (s >= 72) return const Color(0xFFC9A227);
    return const Color(0xFFD5342B);
  }

  bool _onMap(Tender t) =>
      t.status == TenderStatus.live || t.status == TenderStatus.bidding;

  bool get _hasMapsKey =>
      Config.googleMapsApiKey != 'PASTE_YOUR_GOOGLE_MAPS_ANDROID_KEY';

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (!_hasMapsKey) return _needsKey(context);
    final base = LatLng(widget.org.lat, widget.org.lng);
    final markers = <Marker>{
      Marker(
        markerId: const MarkerId('base'),
        position: base,
        icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure),
        infoWindow: InfoWindow(
            title: '${widget.org.name} (${widget.org.railwayCode})',
            snippet: widget.org.address),
      ),
    };
    final polylines = <Polyline>{};

    for (final t in widget.tenders) {
      if (!_onMap(t)) continue; // only live / bidding stay on the map
      final hue = _tierHue(t.relevanceScore);
      final col = _tierColor(t.relevanceScore);
      final sites =
          t.locations.where((l) => l.role != LocRole.base).toList();
      for (final l in sites) {
        markers.add(Marker(
          markerId: MarkerId('${t.id}_${l.id}'),
          position: LatLng(l.lat, l.lng),
          icon: BitmapDescriptor.defaultMarkerWithHue(hue),
          infoWindow: InfoWindow(
            title: '${l.role.name.toUpperCase()} · ${l.name}',
            snippet:
                '${t.authority ?? ''} · ${inr(t.valueInr)} · tap for details',
            onTap: () => widget.onOpen(t),
          ),
        ));
      }
      // Haul route mine → plant in the tender's tier colour.
      final mine = t.mines.isNotEmpty ? t.mines.first : null;
      final plant = t.plant;
      if (mine != null && plant != null) {
        polylines.add(Polyline(
          polylineId: PolylineId('haul_${t.id}'),
          points: [LatLng(mine.lat, mine.lng), LatLng(plant.lat, plant.lng)],
          color: col.withValues(alpha: 0.75),
          width: 4,
        ));
      }
      // Faint line from VWLR base to the site, for distance context.
      if (sites.isNotEmpty) {
        polylines.add(Polyline(
          polylineId: PolylineId('reach_${t.id}'),
          points: [base, LatLng(sites.first.lat, sites.first.lng)],
          color: const Color(0xFF8A94A6).withValues(alpha: 0.28),
          width: 2,
        ));
      }
    }

    final circles = <Circle>{
      if (_showRadius)
        Circle(
          circleId: const CircleId('radius'),
          center: base,
          radius: widget.org.operatingRadiusKm * 1000.0,
          fillColor: const Color(0x141F6FEB),
          strokeColor: const Color(0x551F6FEB),
          strokeWidth: 1,
        ),
    };

    return Stack(
      children: [
        GoogleMap(
          initialCameraPosition: CameraPosition(target: base, zoom: 7),
          markers: markers,
          circles: circles,
          polylines: polylines,
          myLocationButtonEnabled: false,
          onMapCreated: (ctrl) => _c = ctrl,
        ),
        Positioned(top: 12, left: 12, right: 12, child: _legend(context)),
        Positioned(
          bottom: 20,
          right: 12,
          child: Column(children: [
            FloatingActionButton.small(
              heroTag: 'radius',
              backgroundColor: c.surface,
              foregroundColor: _showRadius ? c.brand : c.faint,
              onPressed: () => setState(() => _showRadius = !_showRadius),
              child: const Icon(Icons.radar),
            ),
            const SizedBox(height: 8),
            FloatingActionButton.small(
              heroTag: 'recenter',
              backgroundColor: c.surface,
              foregroundColor: c.muted,
              onPressed: () =>
                  _c?.animateCamera(CameraUpdate.newLatLngZoom(base, 7)),
              child: const Icon(Icons.my_location),
            ),
          ]),
        ),
      ],
    );
  }

  Widget _needsKey(BuildContext context) {
    final c = context.colors;
    final sites = widget.tenders
        .expand((t) => t.locations)
        .where((l) => l.role != LocRole.base)
        .length;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                  color: c.brandBg, borderRadius: BorderRadius.circular(18)),
              child: Icon(Icons.map_outlined, size: 32, color: c.brand),
            ),
            const SizedBox(height: 16),
            const Text('Map preview',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(
              '${widget.org.name} (${widget.org.railwayCode}) · '
              '$sites tender site${sites == 1 ? '' : 's'} within '
              '${widget.org.operatingRadiusKm} km',
              textAlign: TextAlign.center,
              style: TextStyle(color: c.muted, height: 1.4),
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                  color: c.surfaceAlt, borderRadius: BorderRadius.circular(12)),
              child: Text(
                'Add a free Google Maps key to see mines, plants and haul '
                'routes on a live map. The Tenders and Dashboard tabs work now.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12.5, color: c.muted, height: 1.4),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _legend(BuildContext context) {
    final c = context.colors;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        child: Wrap(spacing: 12, runSpacing: 4, children: [
          _Dot(c.brand, 'VWLR base'),
          const _Dot(Color(0xFF2E9B57), 'Core RCR/washery'),
          const _Dot(Color(0xFFD8871F), 'Rail-siding'),
          const _Dot(Color(0xFFC9A227), 'Power-plant'),
          const _Dot(Color(0xFFD5342B), 'Other'),
        ]),
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  final Color color;
  final String label;
  const _Dot(this.color, this.label);
  @override
  Widget build(BuildContext context) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.location_on, color: color, size: 16),
        const SizedBox(width: 3),
        Text(label, style: const TextStyle(fontSize: 12)),
      ]);
}
