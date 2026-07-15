import 'dart:ui' as ui;
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

  final Map<String, BitmapDescriptor> _iconCache = {};
  Set<Marker> _markers = {};
  Set<Polyline> _polylines = {};
  bool _ready = false;

  static const Color _baseColor = Color(0xFF1F6FEB);

  bool get _hasMapsKey =>
      Config.googleMapsApiKey != 'PASTE_YOUR_GOOGLE_MAPS_ANDROID_KEY';

  // Distinct symbol per site role.
  IconData _glyph(LocRole r) => switch (r) {
        LocRole.mine => Icons.terrain,
        LocRole.plant => Icons.factory,
        LocRole.siding => Icons.train,
        LocRole.base => Icons.home,
      };

  // A distinct colour shade per tender (golden-angle spacing keeps neighbours
  // far apart on the wheel, so adjacent tenders never look alike).
  Color _shade(int i) =>
      HSVColor.fromAHSV(1.0, (i * 137.508) % 360.0, 0.62, 0.86).toColor();

  @override
  void initState() {
    super.initState();
    if (_hasMapsKey) _rebuild();
  }

  @override
  void didUpdateWidget(covariant MapScreen old) {
    super.didUpdateWidget(old);
    if (_hasMapsKey && old.tenders != widget.tenders) _rebuild();
  }

  Future<void> _rebuild() async {
    final base = LatLng(widget.org.lat, widget.org.lng);
    final markers = <Marker>{
      Marker(
        markerId: const MarkerId('base'),
        position: base,
        icon: await _icon(_baseColor, Icons.home),
        infoWindow: InfoWindow(
            title: '${widget.org.name} (${widget.org.railwayCode})',
            snippet: widget.org.address),
      ),
    };
    final polylines = <Polyline>{};

    final live = widget.tenders
        .where((t) =>
            t.status == TenderStatus.live || t.status == TenderStatus.bidding)
        .toList();

    for (var i = 0; i < live.length; i++) {
      final t = live[i];
      final color = _shade(i);
      final sites = t.locations.where((l) => l.role != LocRole.base).toList();
      for (final l in sites) {
        markers.add(Marker(
          markerId: MarkerId('${t.id}_${l.id}'),
          position: LatLng(l.lat, l.lng),
          icon: await _icon(color, _glyph(l.role)),
          infoWindow: InfoWindow(
            title: '${l.role.name.toUpperCase()} · ${l.name}',
            snippet:
                '${t.authority ?? ''} · ${inr(t.valueInr)} · tap for details',
            onTap: () => widget.onOpen(t),
          ),
        ));
      }
      // Haul route mine → plant in this tender's colour.
      final mine = t.mines.isNotEmpty ? t.mines.first : null;
      final plant = t.plant;
      if (mine != null && plant != null) {
        polylines.add(Polyline(
          polylineId: PolylineId('haul_${t.id}'),
          points: [LatLng(mine.lat, mine.lng), LatLng(plant.lat, plant.lng)],
          color: color.withValues(alpha: 0.85),
          width: 4,
        ));
      }
      // Faint line from VWLR base to the site, for distance context.
      if (sites.isNotEmpty) {
        polylines.add(Polyline(
          polylineId: PolylineId('reach_${t.id}'),
          points: [base, LatLng(sites.first.lat, sites.first.lng)],
          color: color.withValues(alpha: 0.22),
          width: 2,
        ));
      }
    }

    if (!mounted) return;
    setState(() {
      _markers = markers;
      _polylines = polylines;
      _ready = true;
    });
  }

  // Draws a coloured circular pin with a white role glyph, cached by (colour, glyph).
  Future<BitmapDescriptor> _icon(Color color, IconData glyph) async {
    final key = '${color.value}_${glyph.codePoint}';
    final hit = _iconCache[key];
    if (hit != null) return hit;

    const double s = 96;
    const double r = 38;
    const Offset ctr = Offset(48, 46);
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    canvas.drawCircle(const Offset(48, 49), r,
        Paint()..color = Colors.black.withValues(alpha: 0.20));
    canvas.drawCircle(ctr, r, Paint()..color = color);
    canvas.drawCircle(
        ctr,
        r,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 5);
    final tp = TextPainter(textDirection: TextDirection.ltr)
      ..text = TextSpan(
        text: String.fromCharCode(glyph.codePoint),
        style: TextStyle(
          fontSize: 44,
          fontFamily: glyph.fontFamily,
          package: glyph.fontPackage,
          color: Colors.white,
        ),
      )
      ..layout();
    tp.paint(canvas, Offset(ctr.dx - tp.width / 2, ctr.dy - tp.height / 2));

    final img = await recorder.endRecording().toImage(s.toInt(), s.toInt());
    final data = await img.toByteData(format: ui.ImageByteFormat.png);
    final bmp = BitmapDescriptor.bytes(data!.buffer.asUint8List(),
        imagePixelRatio: 2.4);
    _iconCache[key] = bmp;
    return bmp;
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    if (!_hasMapsKey) return _needsKey(context);
    final base = LatLng(widget.org.lat, widget.org.lng);

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
          markers: _markers,
          circles: circles,
          polylines: _polylines,
          myLocationButtonEnabled: false,
          onMapCreated: (ctrl) => _c = ctrl,
        ),
        Positioned(top: 12, left: 12, right: 12, child: _legend(context)),
        if (!_ready)
          const Positioned(
            top: 70,
            left: 0,
            right: 0,
            child: Center(child: CircularProgressIndicator()),
          ),
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
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Wrap(spacing: 14, runSpacing: 4, children: [
            _Sym(Icons.home, 'VWLR base'),
            _Sym(Icons.terrain, 'Mine / source'),
            _Sym(Icons.factory, 'Plant'),
            _Sym(Icons.train, 'Siding'),
          ]),
          const SizedBox(height: 3),
          Text('Each tender has its own colour · line links its mine → plant',
              style: TextStyle(fontSize: 11, color: context.colors.muted)),
        ]),
      ),
    );
  }
}

class _Sym extends StatelessWidget {
  final IconData icon;
  final String label;
  const _Sym(this.icon, this.label);
  @override
  Widget build(BuildContext context) =>
      Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, color: context.colors.muted, size: 15),
        const SizedBox(width: 3),
        Text(label, style: const TextStyle(fontSize: 12)),
      ]);
}
