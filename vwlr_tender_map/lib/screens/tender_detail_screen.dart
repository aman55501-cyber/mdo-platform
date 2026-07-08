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
  const TenderDetailScreen(
      {super.key,
      required this.tender,
      required this.org,
      required this.onStatus,
      required this.onHeart});

  @override
  Widget build(BuildContext context) {
    final elig = assess(tender, org);
    return Scaffold(
      appBar: AppBar(
        title: Text(tender.authority ?? 'Tender'),
        actions: [
          IconButton(
            onPressed: onHeart,
            icon: Icon(tender.hearted ? Icons.favorite : Icons.favorite_border,
                color: tender.hearted ? kDanger : null),
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
                  style: const TextStyle(color: Colors.black45, fontSize: 12)),
          ]),
          const SizedBox(height: 8),
          Text(tender.title,
              style:
                  const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          if (tender.portal != null)
            Text('${tender.portal} · ${tender.sourceField ?? ''}',
                style: const TextStyle(color: Colors.black54)),
          const SizedBox(height: 16),

          _eligibilityCard(elig),
          const SizedBox(height: 14),

          _facts(),
          const SizedBox(height: 14),

          const Text('Route & locations',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          ...tender.locations
              .where((l) => l.role != LocRole.base)
              .map(_locTile),
          const SizedBox(height: 14),

          if (tender.eligibilityNotes != null) ...[
            const Text('Notes', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(tender.eligibilityNotes!,
                style: const TextStyle(color: Colors.black87, height: 1.35)),
            const SizedBox(height: 14),
          ],

          FilledButton.icon(
            onPressed: tender.pdfUrl == null
                ? null
                : () => launchUrl(Uri.parse(tender.pdfUrl!),
                    mode: LaunchMode.externalApplication),
            icon: const Icon(Icons.picture_as_pdf),
            label: Text(tender.pdfUrl == null
                ? 'No document attached'
                : 'Open tender document'),
          ),
          const SizedBox(height: 10),
          _statusPicker(context),
        ],
      ),
    );
  }

  Widget _eligibilityCard(Eligibility e) {
    final color = e.noPublishedCriteria
        ? Colors.blueGrey
        : e.eligible
            ? kOk
            : kDanger;
    return Card(
      color: color.withOpacity(0.08),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(
                  e.noPublishedCriteria
                      ? Icons.info_outline
                      : e.eligible
                          ? Icons.verified
                          : Icons.report_gmailerrorred,
                  color: color),
              const SizedBox(width: 8),
              Text(
                  e.noPublishedCriteria
                      ? 'No published PQC — check invite'
                      : e.eligible
                          ? 'You appear ELIGIBLE'
                          : 'Gaps vs VWLR profile',
                  style: TextStyle(
                      color: color, fontWeight: FontWeight.w800, fontSize: 15)),
            ]),
            const SizedBox(height: 8),
            ...e.checks.map((c) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    Icon(c.pass == true ? Icons.check_circle : Icons.cancel,
                        size: 16,
                        color: c.pass == true ? kOk : kDanger),
                    const SizedBox(width: 6),
                    Expanded(
                        child: Text('${c.label}: ${c.detail}',
                            style: const TextStyle(fontSize: 12.5))),
                  ]),
                )),
            if (e.checks.isEmpty)
              const Text('Eligibility criteria not published for this tender.',
                  style: TextStyle(fontSize: 12.5)),
          ],
        ),
      ),
    );
  }

  Widget _facts() => Card(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Column(children: [
            _row('Estimated value', inr(tender.valueInr)),
            _row('EMD / Bid security', inr(tender.emdInr)),
            _row('Performance BG', inr(tender.pbgInr)),
            _row('Contract period',
                tender.contractMonths == null ? '—' : '${tender.contractMonths} months'),
            _row('Bid deadline', dateFmt(tender.deadline)),
            _row('Technical opening', dateFmt(tender.techOpen)),
            _row('Req. turnover', inr(tender.qrMinTurnoverInr)),
            _row('Req. experience', tonnes(tender.qrExperienceMt)),
          ]),
        ),
      );

  Widget _row(String k, String v) => ListTile(
        dense: true,
        visualDensity: const VisualDensity(vertical: -3),
        title: Text(k, style: const TextStyle(fontSize: 13, color: Colors.black54)),
        trailing: Text(v,
            style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
      );

  Widget _locTile(TenderLocation l) {
    final icon = l.role == LocRole.plant
        ? Icons.factory_outlined
        : Icons.terrain_outlined;
    return Card(
      color: Colors.white,
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon, color: kBrand),
        title: Text(l.name,
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
        subtitle: Text(
            '${l.role.name.toUpperCase()} · ${[l.district, l.state].where((e) => e != null).join(', ')}'
            '${l.pin != null ? ' · ${l.pin}' : ''}'),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(km(l.roadKmFromBase),
                style: const TextStyle(fontWeight: FontWeight.w700)),
            const Text('from VWLR',
                style: TextStyle(fontSize: 10, color: Colors.black45)),
          ],
        ),
      ),
    );
  }

  Widget _statusPicker(BuildContext context) => Row(
        children: [
          const Text('Set status: ',
              style: TextStyle(color: Colors.black54, fontSize: 13)),
          const SizedBox(width: 6),
          Expanded(
            child: Wrap(
              spacing: 6,
              children: TenderStatus.values.map((s) {
                final sel = s == tender.status;
                return ChoiceChip(
                  label: Text(s.name, style: const TextStyle(fontSize: 11)),
                  selected: sel,
                  onSelected: (_) => onStatus(s),
                );
              }).toList(),
            ),
          ),
        ],
      );
}
