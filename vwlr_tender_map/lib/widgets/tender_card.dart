import 'package:flutter/material.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../services/appetite.dart';
import '../services/eligibility.dart';
import '../services/format.dart';
import '../theme.dart';
import 'status_chip.dart';

class TenderCard extends StatelessWidget {
  final Tender tender;
  final OrgProfile org;
  final VoidCallback onTap;
  final VoidCallback onHeart;
  const TenderCard(
      {super.key,
      required this.tender,
      required this.org,
      required this.onTap,
      required this.onHeart});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final d = tender.daysLeft;
    final elig = assess(tender, org);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  StatusChip(tender.status),
                  const SizedBox(width: 6),
                  _eligBadge(context, elig),
                  if (Appetite.isPreferred(tender)) ...[
                    const SizedBox(width: 6),
                    const Icon(Icons.star, size: 14, color: Color(0xFFC67D10)),
                  ],
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(tender.authority ?? '',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontWeight: FontWeight.w600, color: c.muted)),
                  ),
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                    onPressed: onHeart,
                    icon: Icon(
                        tender.hearted
                            ? Icons.favorite
                            : Icons.favorite_border,
                        size: 20,
                        color: tender.hearted ? c.danger : c.faint),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(tender.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 15.5,
                      fontWeight: FontWeight.w700,
                      height: 1.25)),
              const SizedBox(height: 10),
              Row(
                children: [
                  _pill(context, Icons.currency_rupee, inr(tender.valueInr),
                      strong: true),
                  const SizedBox(width: 8),
                  if (tender.plant != null)
                    Flexible(
                      child: _pill(context, Icons.factory_outlined,
                          tender.plant!.state ?? tender.plant!.name),
                    ),
                ],
              ),
              if (Appetite.bgShort(tender)) ...[
                const SizedBox(height: 8),
                Row(children: [
                  const Icon(Icons.account_balance_outlined,
                      size: 14, color: Color(0xFFD5342B)),
                  const SizedBox(width: 5),
                  Text('BG shortfall · needs > ₹8 Cr PBG',
                      style: TextStyle(
                          color: c.danger,
                          fontWeight: FontWeight.w600,
                          fontSize: 12)),
                ]),
              ],
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.schedule, size: 15, color: urgencyColor(context, d)),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(
                      tender.deadline == null
                          ? 'Deadline not published'
                          : d! < 0
                              ? 'Closed ${dateFmt(tender.deadline)}'
                              : '$d days left · ${dateFmt(tender.deadline)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: urgencyColor(context, d),
                          fontWeight: FontWeight.w600,
                          fontSize: 12.5,
                          fontFeatures: kNumStyle.fontFeatures),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _eligBadge(BuildContext context, Eligibility e) {
    final c = context.colors;
    final (label, fg, bg) = e.noPublishedCriteria
        ? ('NO PQC', c.closed, c.closedBg)
        : e.eligible
            ? ('ELIGIBLE', c.ok, c.okBg)
            : ('GAPS', c.danger, c.dangerBg);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text(label,
          style: TextStyle(
              color: fg,
              fontWeight: FontWeight.w700,
              fontSize: 10,
              letterSpacing: .4)),
    );
  }

  Widget _pill(BuildContext context, IconData i, String s,
      {bool strong = false}) {
    final c = context.colors;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
          color: c.surfaceAlt, borderRadius: BorderRadius.circular(9)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(i, size: 14, color: c.muted),
        const SizedBox(width: 5),
        Flexible(
          child: Text(s,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: strong ? FontWeight.w700 : FontWeight.w500,
                  fontFeatures: strong ? kNumStyle.fontFeatures : null)),
        ),
      ]),
    );
  }
}
