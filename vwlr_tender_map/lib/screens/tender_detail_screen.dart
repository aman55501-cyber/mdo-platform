import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../models/tender_location.dart';
import '../services/eligibility.dart';
import '../services/format.dart';
import '../theme.dart';
import '../widgets/status_chip.dart';

class TenderDetailScreen extends StatelessWidget {
  final Tender tender;
  final OrgProfile org;
  final void Function(TenderStatus) onStatus;
  final VoidCallback onHeart;
  final void Function(bool) onPursue;
  const TenderDetailScreen(
      {super.key,
      required this.tender,
      required this.org,
      required this.onStatus,
      required this.onHeart,
      required this.onPursue});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final elig = assess(tender, org);
    return Scaffold(
      appBar: AppBar(
        title: Text(tender.authority ?? 'Tender'),
        actions: [
          IconButton(
            onPressed: onHeart,
            icon: Icon(tender.hearted ? Icons.favorite : Icons.favorite_border,
                color: tender.hearted ? c.danger : null),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(children: [
            StatusChip(tender.status),
            const Spacer(),
            if (tender.refNo != null)
              Text(tender.refNo!,
                  style: TextStyle(
                      color: c.faint,
                      fontSize: 12,
                      fontFeatures: kNumStyle.fontFeatures)),
          ]),
          const SizedBox(height: 10),
          Text(tender.title,
              style: const TextStyle(
                  fontSize: 20, fontWeight: FontWeight.w800, height: 1.2)),
          const SizedBox(height: 5),
          if (tender.portal != null)
            Text('${tender.portal} · ${tender.sourceField ?? ''}',
                style: TextStyle(color: c.muted, fontSize: 13)),
          const SizedBox(height: 16),
          _eligibilityCard(context, elig),
          const SizedBox(height: 14),
          _facts(context),
          const SizedBox(height: 18),
          _sectionLabel(context, 'Route & locations'),
          const SizedBox(height: 8),
          ...tender.locations
              .where((l) => l.role != LocRole.base)
              .map((l) => _locTile(context, l)),
          const SizedBox(height: 18),
          if (tender.eligibilityNotes != null) ...[
            _sectionLabel(context, 'Field notes'),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
              decoration: BoxDecoration(
                color: c.surfaceAlt,
                borderRadius: BorderRadius.circular(10),
                border: Border(left: BorderSide(color: c.brand, width: 3)),
              ),
              child: Text(tender.eligibilityNotes!,
                  style: TextStyle(color: c.muted, height: 1.4, fontSize: 13)),
            ),
            const SizedBox(height: 18),
          ],
          FilledButton.icon(
            style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(48)),
            onPressed: tender.pdfUrl == null
                ? null
                : () => launchUrl(Uri.parse(tender.pdfUrl!),
                    mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.picture_as_pdf_outlined),
            label: Text(tender.pdfUrl == null
                ? 'No document attached'
                : 'Open tender document'),
          ),
          const SizedBox(height: 10),
          // Pursue → adds the tender to the Bid Desk with its action plan.
          tender.pursued
              ? OutlinedButton.icon(
                  style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                      foregroundColor: c.ok),
                  onPressed: () => onPursue(false),
                  icon: const Icon(Icons.check_circle_outline),
                  label: const Text('In Bid Desk · tap to remove'),
                )
              : FilledButton.icon(
                  style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                      backgroundColor: c.brand),
                  onPressed: () => onPursue(true),
                  icon: const Icon(Icons.gavel_outlined),
                  label: const Text('Pursue this bid'),
                ),
          const SizedBox(height: 16),
          _statusPicker(context),
        ],
      ),
    );
  }

  Widget _sectionLabel(BuildContext context, String s) => Text(s.toUpperCase(),
      style: TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          letterSpacing: 1,
          color: context.colors.muted));

  Widget _eligibilityCard(BuildContext context, Eligibility e) {
    final c = context.colors;
    final (fg, bg) = e.noPublishedCriteria
        ? (c.closed, c.closedBg)
        : e.eligible
            ? (c.ok, c.okBg)
            : (c.danger, c.dangerBg);
    return Container(
      decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: fg.withValues(alpha: 0.25))),
      padding: const EdgeInsets.all(15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(
                e.noPublishedCriteria
                    ? Icons.info_outline
                    : e.eligible
                        ? Icons.verified_outlined
                        : Icons.report_gmailerrorred_outlined,
                color: fg,
                size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                  e.noPublishedCriteria
                      ? 'No published PQC — check the invite'
                      : e.eligible
                          ? 'You clear every published requirement'
                          : 'Gaps vs VWLR profile',
                  style: TextStyle(
                      color: fg, fontWeight: FontWeight.w800, fontSize: 15)),
            ),
          ]),
          if (e.checks.isNotEmpty) const SizedBox(height: 10),
          ...e.checks.map((ch) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                          ch.pass == true
                              ? Icons.check_circle
                              : Icons.cancel,
                          size: 16,
                          color: ch.pass == true ? c.ok : c.danger),
                      const SizedBox(width: 7),
                      Expanded(
                          child: Text('${ch.label}: ${ch.detail}',
                              style: TextStyle(
                                  fontSize: 12.5, color: c.muted, height: 1.3))),
                    ]),
              )),
          if (e.checks.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                  'Eligibility criteria not published for this tender.',
                  style: TextStyle(fontSize: 12.5, color: c.muted)),
            ),
        ],
      ),
    );
  }

  Widget _facts(BuildContext context) {
    final rows = <(String, String)>[
      ('Estimated value', inr(tender.valueInr)),
      ('EMD / Bid security', inr(tender.emdInr)),
      ('Performance BG', inr(tender.pbgInr)),
      ('Contract period',
          tender.contractMonths == null ? '—' : '${tender.contractMonths} months'),
      ('Bid deadline', dateFmt(tender.deadline)),
      ('Technical opening', dateFmt(tender.techOpen)),
      ('Req. turnover', inr(tender.qrMinTurnoverInr)),
      ('Req. experience', tonnes(tender.qrExperienceMt)),
    ];
    return Card(
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) _row(context, rows[i], i == 0),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, (String, String) kv, bool first) {
    final c = context.colors;
    return Container(
      decoration: BoxDecoration(
        border: first
            ? null
            : Border(top: BorderSide(color: c.hair.withValues(alpha: 0.7))),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      child: Row(children: [
        Expanded(
            child: Text(kv.$1,
                style: TextStyle(fontSize: 13, color: c.muted))),
        Text(kv.$2,
            style: TextStyle(
                fontSize: 13.5,
                fontWeight: FontWeight.w600,
                fontFeatures: kNumStyle.fontFeatures)),
      ]),
    );
  }

  Widget _locTile(BuildContext context, TenderLocation l) {
    final c = context.colors;
    final (icon, color) = l.role == LocRole.plant
        ? (Icons.factory_outlined, c.violet)
        : (Icons.terrain_outlined, c.warn);
    final place = [l.district, l.state].where((e) => e != null).join(', ');
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
          child: Row(children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(9)),
              child: Icon(icon, color: color, size: 19),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 14)),
                  const SizedBox(height: 1),
                  Text(
                      '${l.role.name.toUpperCase()} · $place'
                      '${l.pin != null ? ' · ${l.pin}' : ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 11.5, color: c.muted)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(km(l.roadKmFromBase),
                    style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontFeatures: kNumStyle.fontFeatures)),
                Text('from VWLR',
                    style: TextStyle(fontSize: 10, color: c.faint)),
              ],
            ),
          ]),
        ),
      ),
    );
  }

  Widget _statusPicker(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text('Set status',
                style: TextStyle(color: context.colors.muted, fontSize: 13)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Wrap(
              spacing: 6,
              runSpacing: 2,
              children: TenderStatus.values.map((s) {
                return ChoiceChip(
                  label: Text(s.name, style: const TextStyle(fontSize: 11.5)),
                  selected: s == tender.status,
                  visualDensity: VisualDensity.compact,
                  onSelected: (_) => onStatus(s),
                );
              }).toList(),
            ),
          ),
        ],
      );
}
