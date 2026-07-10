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

  double _hue(LocRole r) => switch (r) {
        LocRole.base => BitmapDescriptor.hueAzure,
        LocRole.mine => BitmapDescriptor.hueOrange,
        LocRole.plant => BitmapDescriptor.hueViolet,
        LocRole.siding => BitmapDescriptor.hueYellow,
      };

  Color _routeColor(LocRole r) => switch (r) {
        LocRole.plant => const Color(0xFF7B61FF),
        LocRole.mine => const Color(0xFFD8871F),
        _ => const Color(0xFF1F6FEB),
      };

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
      for (final l in t.locations) {
        if (l.role == LocRole.base) continue;
        markers.add(Marker(
          markerId: MarkerId('${t.id}_${l.id}'),
          position: LatLng(l.lat, l.lng),
          icon: BitmapDescriptor.defaultMarkerWithHue(_hue(l.role)),
          infoWindow: InfoWindow(
            title: '${l.role.name.toUpperCase()} · ${l.name}',
            snippet:
                '${t.authority ?? ''} · ${inr(t.valueInr)} · tap for details',
            onTap: () => widget.onOpen(t),
          ),
        ));
        polylines.add(Polyline(
          polylineId: PolylineId('route_${t.id}_${l.id}'),
          points: [base, LatLng(l.lat, l.lng)],
          color: _routeColor(l.role).withValues(alpha: 0.55),
          width: 3,
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
        child: Wrap(spacing: 14, runSpacing: 4, children: [
          _Dot(c.brand, 'VWLR base'),
          const _Dot(Color(0xFFD8871F), 'Mine'),
          _Dot(c.violet, 'Plant'),
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
