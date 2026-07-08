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
    final live = tenders.where((t) => t.status == TenderStatus.live).toList();
    final pipelineValue = tenders
        .where((t) =>
            t.status == TenderStatus.live || t.status == TenderStatus.bidding)
        .fold<num>(0, (a, t) => a + (t.valueInr ?? 0));
    final nextDeadline = tenders
        .where((t) => t.deadline != null && t.daysLeft != null && t.daysLeft! >= 0)
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
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        Text('${org.railwayCode} · ${org.address ?? ''}',
            style: const TextStyle(color: Colors.black54)),
        const SizedBox(height: 14),
        Row(children: [
          _stat('Live', '${live.length}', kOk),
          const SizedBox(width: 10),
          _stat('Eligible', '${eligibleIds.length}', kBrand),
          const SizedBox(width: 10),
          _stat('Pipeline', inr(pipelineValue), const Color(0xFF7B61FF)),
        ]),
        const SizedBox(height: 16),
        const Text('Next deadline',
            style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Card(
          color: Colors.white,
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: nextDeadline.isEmpty
                ? const Text('No upcoming deadlines')
                : Row(children: [
                    CircleAvatar(
                      backgroundColor:
                          urgencyColor(nextDeadline.first.daysLeft)
                              .withOpacity(0.15),
                      child: Text('${nextDeadline.first.daysLeft}',
                          style: TextStyle(
                              color:
                                  urgencyColor(nextDeadline.first.daysLeft),
                              fontWeight: FontWeight.w800)),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(nextDeadline.first.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600)),
                          Text(dateFmt(nextDeadline.first.deadline),
                              style: const TextStyle(
                                  color: Colors.black54, fontSize: 12)),
                        ],
                      ),
                    ),
                  ]),
          ),
        ),
        const SizedBox(height: 16),
        const Text('Pipeline', style: TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        Card(
          color: Colors.white,
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Column(
              children: TenderStatus.values.map((s) {
                return ListTile(
                  dense: true,
                  title: Text(s.name.toUpperCase(),
                      style: const TextStyle(
                          fontSize: 12.5, fontWeight: FontWeight.w600)),
                  trailing: Text('${counts[s] ?? 0}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }

  Widget _stat(String label, String value, Color color) => Expanded(
        child: Card(
          color: Colors.white,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 10),
            child: Column(children: [
              Text(value,
                  style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: color)),
              const SizedBox(height: 2),
              Text(label,
                  style: const TextStyle(fontSize: 12, color: Colors.black54)),
            ]),
          ),
        ),
      );
}
