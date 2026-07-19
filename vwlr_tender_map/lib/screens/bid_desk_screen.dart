import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../services/bid_workflow.dart';
import '../services/eligibility.dart';
import '../services/format.dart';
import '../theme.dart';

class BidDeskScreen extends StatelessWidget {
  final OrgProfile org;
  final List<Tender> tenders;
  final void Function(Tender) onOpen;
  final void Function(Tender, String stage) onStage;
  final void Function(Tender, String key, bool value) onToggle;
  final void Function(Tender) onUnpursue;
  const BidDeskScreen({
    super.key,
    required this.org,
    required this.tenders,
    required this.onOpen,
    required this.onStage,
    required this.onToggle,
    required this.onUnpursue,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final bids = tenders.where((t) => t.pursued).toList()
      ..sort((a, b) {
        final ad = a.deadline, bd = b.deadline;
        if (ad == null && bd == null) return 0;
        if (ad == null) return 1;
        if (bd == null) return -1;
        return ad.compareTo(bd);
      });

    if (bids.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                  color: c.brandBg, borderRadius: BorderRadius.circular(16)),
              child: Icon(Icons.gavel_outlined, size: 30, color: c.brand),
            ),
            const SizedBox(height: 14),
            const Text('No bids in progress',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(
                'Open a tender you’re eligible for and tap "Pursue this bid". '
                'It shows up here with a step-by-step action plan.',
                textAlign: TextAlign.center,
                style: TextStyle(color: c.muted, height: 1.4, fontSize: 13)),
          ]),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(12),
      children: bids.map((t) => _bidCard(context, t)).toList(),
    );
  }

  Widget _bidCard(BuildContext context, Tender t) {
    final c = context.colors;
    final e = assess(t, org);
    final done = bidDone(t);
    final total = bidSteps.length;
    final d = t.daysLeft;
    final (vLabel, vColor) = e.eligible
        ? ('Eligible', c.ok)
        : e.ineligible
            ? ('Gaps vs profile', c.danger)
            : ('Needs review', const Color(0xFFC67D10));

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          // Title + open
          Row(children: [
            Expanded(
              child: GestureDetector(
                onTap: () => onOpen(t),
                child: Text(t.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w700,
                        height: 1.25)),
              ),
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              onPressed: () => onUnpursue(t),
              icon: Icon(Icons.close, size: 18, color: c.faint),
              tooltip: 'Remove from Bid Desk',
            ),
          ]),
          Text(
              '${t.authority ?? ''} · ${inr(t.valueInr)}'
              '${t.deadline != null ? ' · closes ${dateFmt(t.deadline)}${d != null && d >= 0 ? ' ($d d)' : ''}' : ''}',
              style: TextStyle(fontSize: 12.5, color: c.muted)),
          const SizedBox(height: 8),

          // Eligibility verdict + progress
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                  color: vColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(7)),
              child: Text(vLabel,
                  style: TextStyle(
                      color: vColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 11.5)),
            ),
            const Spacer(),
            Text('$done / $total steps',
                style: TextStyle(fontSize: 12, color: c.muted)),
          ]),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: total == 0 ? 0 : done / total,
              minHeight: 6,
              backgroundColor: c.surfaceAlt,
              color: c.brand,
            ),
          ),
          const SizedBox(height: 12),

          // Stage selector
          Wrap(
            spacing: 6,
            runSpacing: 2,
            children: bidStages.map((s) {
              return ChoiceChip(
                label: Text(bidStageLabel(s),
                    style: const TextStyle(fontSize: 11)),
                selected: t.bidStage == s,
                visualDensity: VisualDensity.compact,
                onSelected: (_) => onStage(t, s),
              );
            }).toList(),
          ),
          const SizedBox(height: 6),
          const Divider(height: 16),

          // Checklist
          ...bidSteps.map((step) {
            final checked = t.bidChecklist[step.key] == true;
            return InkWell(
              onTap: () => onToggle(t, step.key, !checked),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                        checked
                            ? Icons.check_circle
                            : Icons.radio_button_unchecked,
                        size: 19,
                        color: checked ? c.ok : c.faint),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(step.label,
                              style: TextStyle(
                                  fontSize: 13.5,
                                  fontWeight: FontWeight.w600,
                                  decoration: checked
                                      ? TextDecoration.lineThrough
                                      : null,
                                  color: checked ? c.faint : null)),
                          Text(step.detail(t, org),
                              style: TextStyle(
                                  fontSize: 12, color: c.muted, height: 1.3)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          if (t.pdfUrl != null)
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(42)),
              onPressed: () => launchUrl(Uri.parse(t.pdfUrl!),
                  mode: LaunchMode.externalApplication),
              icon: const Icon(Icons.open_in_new, size: 17),
              label: const Text('Open tender document'),
            ),
        ]),
      ),
    );
  }
}
