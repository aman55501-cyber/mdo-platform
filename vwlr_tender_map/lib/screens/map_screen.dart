import 'dart:math' as math;
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

  // Marker bitmap geometry: a circular pin up top, a name label pill below.
  // Anchor sits on the circle centre so the pin points at the coordinate.
  static const double _r = 32;
  static const double _circleCY = 38; // 6 top pad + r
  static const double _pillTop = 77; // 6 + 2r + 7 gap
  static const double _labelH = 40;
  static const double _totalH = 122; // pillTop + labelH + 5 bottom pad
  static const Offset _pinAnchor = Offset(0.5, _circleCY / _totalH);

  String _shortName(String n) {
    var s = n;
    final i = s.indexOf(' (');
    if (i > 0) s = s.substring(0, i);
    return s.length > 22 ? '${s.substring(0, 21)}…' : s;
  }

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
        anchor: _pinAnchor,
        icon: await _icon(_baseColor, Icons.home, 'VWLR base'),
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

    // Fan out pins that share the same district centroid so labels don't stack.
    final coordCount = <String, int>{};
    LatLng spread(double lat, double lng) {
      final k = '${lat.toStringAsFixed(3)},${lng.toStringAsFixed(3)}';
      final n = coordCount[k] ?? 0;
      coordCount[k] = n + 1;
      if (n == 0) return LatLng(lat, lng);
      final ang = n * 2.399; // golden angle → even fan-out
      return LatLng(lat + 0.05 * math.cos(ang), lng + 0.05 * math.sin(ang));
    }

    for (var i = 0; i < live.length; i++) {
      final t = live[i];
      final color = _shade(i);
      final sites = t.locations.where((l) => l.role != LocRole.base).toList();
      LatLng? firstPos;
      for (final l in sites) {
        final pos = spread(l.lat, l.lng);
        firstPos ??= pos;
        markers.add(Marker(
          markerId: MarkerId('${t.id}_${l.id}'),
          position: pos,
          anchor: _pinAnchor,
          icon: await _icon(color, _glyph(l.role), _shortName(l.name)),
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
      if (firstPos != null) {
        polylines.add(Polyline(
          polylineId: PolylineId('reach_${t.id}'),
          points: [base, firstPos],
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

  // Draws a coloured circular pin (white role glyph) with a small name label
  // pill below it. Cached by (colour, glyph, label).
  Future<BitmapDescriptor> _icon(
      Color color, IconData glyph, String label) async {
    final key = '${color.value}_${glyph.codePoint}_$label';
    final hit = _iconCache[key];
    if (hit != null) return hit;

    final tpLabel = TextPainter(
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    )
      ..text = TextSpan(
          text: label,
          style: const TextStyle(
              fontSize: 25,
              fontWeight: FontWeight.w700,
              color: Color(0xFF15233B)))
      ..layout(maxWidth: 340);

    final double w =
        (2 * _r + 16) > (tpLabel.width + 22) ? (2 * _r + 16) : tpLabel.width + 22;
    final double cx = w / 2;

    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);

    // Pin.
    canvas.drawCircle(Offset(cx, _circleCY + 2), _r,
        Paint()..color = Colors.black.withValues(alpha: 0.18));
    canvas.drawCircle(Offset(cx, _circleCY), _r, Paint()..color = color);
    canvas.drawCircle(
        Offset(cx, _circleCY),
        _r,
        Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 4);
    final tpIcon = TextPainter(textDirection: TextDirection.ltr)
      ..text = TextSpan(
        text: String.fromCharCode(glyph.codePoint),
        style: TextStyle(
          fontSize: 38,
          fontFamily: glyph.fontFamily,
          package: glyph.fontPackage,
          color: Colors.white,
        ),
      )
      ..layout();
    tpIcon.paint(
        canvas, Offset(cx - tpIcon.width / 2, _circleCY - tpIcon.height / 2));

    // Label pill.
    final rr = RRect.fromLTRBR(cx - tpLabel.width / 2 - 9, _pillTop,
        cx + tpLabel.width / 2 + 9, _pillTop + _labelH, const Radius.circular(9));
    canvas.drawRRect(rr, Paint()..color = const Color(0xF7FFFFFF));
    canvas.drawRRect(
        rr,
        Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5);
    tpLabel.paint(
        canvas, Offset(cx - tpLabel.width / 2, _pillTop + (_labelH - tpLabel.height) / 2));

    final img =
        await recorder.endRecording().toImage(w.ceil(), _totalH.ceil());
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
