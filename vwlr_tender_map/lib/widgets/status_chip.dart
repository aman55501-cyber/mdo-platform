import 'package:flutter/material.dart';
import '../models/tender.dart';

class StatusChip extends StatelessWidget {
  final TenderStatus status;
  const StatusChip(this.status, {super.key});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status) {
      TenderStatus.live => ('LIVE', const Color(0xFF2FA84F)),
      TenderStatus.bidding => ('BIDDING', const Color(0xFF1F6FEB)),
      TenderStatus.won => ('WON', const Color(0xFF7B61FF)),
      TenderStatus.lost => ('LOST', const Color(0xFFE5484D)),
      TenderStatus.closed => ('CLOSED', const Color(0xFF8A94A6)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(6)),
      child: Text(label,
          style: TextStyle(
              color: color, fontWeight: FontWeight.w700, fontSize: 11)),
    );
  }
}
