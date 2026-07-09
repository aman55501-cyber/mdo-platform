import 'package:flutter/material.dart';
import '../models/tender.dart';
import '../services/format.dart';
import '../theme.dart';
import 'status_chip.dart';

class TenderCard extends StatelessWidget {
  final Tender tender;
  final VoidCallback onTap;
  final VoidCallback onHeart;
  const TenderCard(
      {super.key,
      required this.tender,
      required this.onTap,
      required this.onHeart});

  @override
  Widget build(BuildContext context) {
    final d = tender.daysLeft;
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
                  const SizedBox(width: 8),
                  Text(tender.authority ?? '',
                      style: const TextStyle(
                          fontWeight: FontWeight.w600, color: Colors.black54)),
                  const Spacer(),
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    onPressed: onHeart,
                    icon: Icon(
                        tender.hearted
                            ? Icons.favorite
                            : Icons.favorite_border,
                        color: tender.hearted ? kDanger : Colors.black38),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(tender.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 15.5, fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              Row(
                children: [
                  _pill(Icons.currency_rupee, inr(tender.valueInr)),
                  const SizedBox(width: 8),
                  if (tender.plant != null)
                    _pill(Icons.factory_outlined,
                        tender.plant!.state ?? tender.plant!.name),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Icon(Icons.schedule, size: 15, color: urgencyColor(d)),
                  const SizedBox(width: 5),
                  Text(
                    tender.deadline == null
                        ? 'Deadline not published'
                        : d! < 0
                            ? 'Closed ${dateFmt(tender.deadline)}'
                            : '$d days left · ${dateFmt(tender.deadline)}',
                    style: TextStyle(
                        color: urgencyColor(d),
                        fontWeight: FontWeight.w600,
                        fontSize: 12.5),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _pill(IconData i, String s) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
            color: const Color(0xFFEEF2F7),
            borderRadius: BorderRadius.circular(8)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(i, size: 14, color: Colors.black54),
          const SizedBox(width: 4),
          Text(s,
              style: const TextStyle(fontSize: 12, color: Colors.black87)),
        ]),
      );
}
