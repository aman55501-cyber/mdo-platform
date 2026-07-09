import 'package:flutter/material.dart';
import '../models/tender.dart';
import '../models/org_profile.dart';
import '../services/format.dart';
import '../theme.dart';

class DashboardScreen extends StatelessWidget {
  final OrgProfile org;
  final List<Tender> tenders;
  final Set<String> eligibleIds;
  const DashboardScreen(
      {super.key,
      required this.org,
      required this.tenders,
      required this.eligibleIds});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final live = tenders.where((t) => t.status == TenderStatus.live).toList();
    final pipelineValue = tenders
        .where((t) =>
            t.status == TenderStatus.live || t.status == TenderStatus.bidding)
        .fold<num>(0, (a, t) => a + (t.valueInr ?? 0));
    final nextDeadline = tenders
        .where((t) =>
            t.deadline != null && t.daysLeft != null && t.daysLeft! >= 0)
        .toList()
      ..sort((a, b) => a.deadline!.compareTo(b.deadline!));

    final counts = <TenderStatus, int>{};
    for (final t in tenders) {
      counts[t.status] = (counts[t.status] ?? 0) + 1;
    }

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        Text(org.name,
            style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
        const SizedBox(height: 2),
        Text('${org.railwayCode} · ${org.address ?? ''}',
            style: TextStyle(color: c.muted, fontSize: 12.5)),
        const SizedBox(height: 16),
        Row(children: [
          _stat(context, 'Live', '${live.length}', c.ok),
          const SizedBox(width: 10),
          _stat(context, 'Eligible', '${eligibleIds.length}', c.brand),
          const SizedBox(width: 10),
          _stat(context, 'Pipeline', inr(pipelineValue), c.violet),
        ]),
        const SizedBox(height: 20),
        _sectionLabel(context, 'Next deadline'),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: nextDeadline.isEmpty
                ? Row(children: [
                    Icon(Icons.event_available, color: c.faint, size: 20),
                    const SizedBox(width: 10),
                    Text('No upcoming deadlines',
                        style: TextStyle(color: c.muted)),
                  ])
                : Row(children: [
                    CircleAvatar(
                      backgroundColor:
                          urgencyColor(context, nextDeadline.first.daysLeft)
                              .withValues(alpha: 0.15),
                      child: Text('${nextDeadline.first.daysLeft}',
                          style: TextStyle(
                              color: urgencyColor(
                                  context, nextDeadline.first.daysLeft),
                              fontWeight: FontWeight.w800,
                              fontFeatures: kNumStyle.fontFeatures)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(nextDeadline.first.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w600)),
                          const SizedBox(height: 2),
                          Text(dateFmt(nextDeadline.first.deadline),
                              style: TextStyle(color: c.muted, fontSize: 12)),
                        ],
                      ),
                    ),
                  ]),
          ),
        ),
        const SizedBox(height: 20),
        _sectionLabel(context, 'Pipeline'),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Column(
              children: [
                for (final s in TenderStatus.values)
                  _pipelineRow(context, s, counts[s] ?? 0),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Color _statusColor(BuildContext context, TenderStatus s) {
    final c = context.colors;
    return switch (s) {
      TenderStatus.live => c.ok,
      TenderStatus.bidding => c.brand,
      TenderStatus.won => c.violet,
      TenderStatus.lost => c.danger,
      TenderStatus.closed => c.closed,
    };
  }

  Widget _pipelineRow(BuildContext context, TenderStatus s, int count) {
    final color = _statusColor(context, s);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
      child: Row(
        children: [
          Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 10),
          Text(s.name.toUpperCase(),
              style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  letterSpacing: .3)),
          const Spacer(),
          Text('$count',
              style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontFeatures: kNumStyle.fontFeatures,
                  color: count > 0 ? null : context.colors.faint)),
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

  Widget _stat(
          BuildContext context, String label, String value, Color color) =>
      Expanded(
        child: Card(
          child: Stack(
            children: [
              Positioned(
                  left: 0, top: 0, bottom: 0, child: Container(width: 3, color: color)),
              Padding(
                padding:
                    const EdgeInsets.fromLTRB(14, 15, 10, 15),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -.3,
                            fontFeatures: kNumStyle.fontFeatures,
                            color: color)),
                    const SizedBox(height: 3),
                    Text(label,
                        style: TextStyle(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w600,
                            color: context.colors.muted)),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
}
