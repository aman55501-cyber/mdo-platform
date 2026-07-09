import 'package:flutter/material.dart';
import '../models/tender.dart';
import '../theme.dart';

class StatusChip extends StatelessWidget {
  final TenderStatus status;
  const StatusChip(this.status, {super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final (label, fg, bg) = switch (status) {
      TenderStatus.live => ('LIVE', c.ok, c.okBg),
      TenderStatus.bidding => ('BIDDING', c.brand, c.brandBg),
      TenderStatus.won => ('WON', c.violet, c.violetBg),
      TenderStatus.lost => ('LOST', c.danger, c.dangerBg),
      TenderStatus.closed => ('CLOSED', c.closed, c.closedBg),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration:
          BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text(label,
          style: TextStyle(
              color: fg,
              fontWeight: FontWeight.w700,
              fontSize: 11,
              letterSpacing: .4)),
    );
  }
}
