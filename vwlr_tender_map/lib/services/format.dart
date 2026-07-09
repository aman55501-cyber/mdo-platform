import 'package:intl/intl.dart';

/// Indian currency in Cr / Lakh, e.g. 93095746 -> "₹9.31 Cr".
String inr(num? v) {
  if (v == null) return '—';
  if (v >= 10000000) return '₹${(v / 10000000).toStringAsFixed(2)} Cr';
  if (v >= 100000) return '₹${(v / 100000).toStringAsFixed(2)} L';
  return '₹${NumberFormat.decimalPattern('en_IN').format(v)}';
}

String tonnes(num? v) =>
    v == null ? '—' : '${NumberFormat.decimalPattern('en_IN').format(v)} MT';

String dateFmt(DateTime? d) =>
    d == null ? 'Not published' : DateFormat('dd MMM yyyy, HH:mm').format(d.toLocal());

String km(num? v) => v == null ? '—' : '${v.toStringAsFixed(0)} km';
