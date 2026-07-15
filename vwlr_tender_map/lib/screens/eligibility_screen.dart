import 'package:flutter/material.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../services/eligibility.dart';
import '../services/format.dart';
import '../theme.dart';

class EligibilityScreen extends StatelessWidget {
  final OrgProfile org;
  final List<Tender> tenders;
  final void Function(Tender) onOpen;
  const EligibilityScreen(
      {super.key,
      required this.org,
      required this.tenders,
      required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    // Judge every open tender against your eligibility profile.
    final open = tenders
        .where((t) =>
            t.status == TenderStatus.live || t.status == TenderStatus.bidding)
        .toList();
    final eligible = <Tender>[];
    final review = <Tender>[];
    var ineligible = 0;
    for (final t in open) {
      final e = assess(t, org);
      if (e.eligible) {
        eligible.add(t);
      } else if (e.ineligible) {
        ineligible++;
      } else {
        review.add(t);
      }
    }

    final items = <Widget>[
      _summary(context, eligible.length, review.length, ineligible),
      if (eligible.isNotEmpty)
        _header(context, '✅ Eligible', eligible.length,
            'You clear every published criterion'),
      ...eligible.map((t) => _card(context, t)),
      if (review.isNotEmpty)
        _header(context, '🔍 Needs review', review.length,
            'Criteria not yet parsed from the document'),
      ...review.map((t) => _card(context, t)),
      if (eligible.isEmpty && review.isEmpty)
        Padding(
          padding: const EdgeInsets.all(40),
          child: Center(
              child: Text('No open tenders to judge yet.',
                  style: TextStyle(color: c.muted))),
        ),
    ];

    return ListView(padding: const EdgeInsets.all(12), children: items);
  }

  Widget _summary(BuildContext context, int elig, int rev, int inelig) {
    final c = context.colors;
    Widget tile(String n, String label, Color col) => Expanded(
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 4),
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
                color: col.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(12)),
            child: Column(children: [
              Text(n,
                  style: TextStyle(
                      fontSize: 22, fontWeight: FontWeight.w800, color: col)),
              Text(label,
                  style: TextStyle(fontSize: 11.5, color: c.muted)),
            ]),
          ),
        );
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(children: [
        tile('$elig', 'Eligible', const Color(0xFF2E9B57)),
        tile('$rev', 'Needs review', const Color(0xFFC67D10)),
        tile('$inelig', 'Not eligible', c.muted),
      ]),
    );
  }

  Widget _header(BuildContext context, String title, int n, String sub) {
    final c = context.colors;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 16, 4, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('$title · $n',
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800)),
        Text(sub, style: TextStyle(fontSize: 12, color: c.muted)),
      ]),
    );
  }

  Widget _card(BuildContext context, Tender t) {
    final e = assess(t, org);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => onOpen(t),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(t.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 14.5, fontWeight: FontWeight.w700, height: 1.25)),
              const SizedBox(height: 4),
              Text('${t.authority ?? ''} · ${inr(t.valueInr)}',
                  style: TextStyle(
                      fontSize: 12.5, color: context.colors.muted)),
              const SizedBox(height: 10),
              ...e.checks.map((ch) => _checkRow(context, ch)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _checkRow(BuildContext context, Check ch) {
    final c = context.colors;
    final (icon, col) = switch (ch.pass) {
      true => (Icons.check_circle, const Color(0xFF2E9B57)),
      false => (Icons.cancel, c.danger),
      _ => (Icons.help_outline, c.faint),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2.5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 15, color: col),
        const SizedBox(width: 6),
        SizedBox(
          width: 116,
          child: Text(ch.label,
              style: const TextStyle(
                  fontSize: 12.5, fontWeight: FontWeight.w600)),
        ),
        Expanded(
          child: Text(ch.detail,
              style: TextStyle(fontSize: 12, color: c.muted)),
        ),
      ]),
    );
  }
}
