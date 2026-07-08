import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../models/tender_location.dart';
import '../services/format.dart';

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

  @override
  Widget build(BuildContext context) {
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
          myLocationButtonEnabled: false,
          onMapCreated: (c) => _c = c,
        ),
        Positioned(
          top: 12,
          left: 12,
          right: 12,
          child: _legend(),
        ),
        Positioned(
          bottom: 20,
          right: 12,
          child: Column(children: [
            FloatingActionButton.small(
              heroTag: 'radius',
              backgroundColor: Colors.white,
              foregroundColor: _showRadius ? Colors.blue : Colors.black45,
              onPressed: () => setState(() => _showRadius = !_showRadius),
              child: const Icon(Icons.radar),
            ),
            const SizedBox(height: 8),
            FloatingActionButton.small(
              heroTag: 'recenter',
              backgroundColor: Colors.white,
              foregroundColor: Colors.black87,
              onPressed: () => _c?.animateCamera(
                  CameraUpdate.newLatLngZoom(base, 7)),
              child: const Icon(Icons.my_location),
            ),
          ]),
        ),
      ],
    );
  }

  Widget _legend() => const Card(
        color: Colors.white,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Wrap(spacing: 14, runSpacing: 4, children: [
            _Dot(Colors.blue, 'VWLR base'),
            _Dot(Colors.orange, 'Mine'),
            _Dot(Color(0xFF7B61FF), 'Plant'),
          ]),
        ),
      );
}

class _Dot extends StatelessWidget {
  final Color color;
  final String label;
  const _Dot(this.color, this.label);
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.location_on, color: color, size: 16),
        const SizedBox(width: 3),
        Text(label, style: const TextStyle(fontSize: 12)),
      ]);
}
