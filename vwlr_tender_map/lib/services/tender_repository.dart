import 'package:supabase_flutter/supabase_flutter.dart';
import '../models/tender.dart';
import '../models/tender_location.dart';
import '../models/org_profile.dart';

class TenderRepository {
  final _db = Supabase.instance.client;

  Future<OrgProfile> orgProfile() async {
    final m = await _db.from('org_profile').select().eq('id', 1).single();
    return OrgProfile.fromMap(m);
  }

  Future<List<Tender>> tenders() async {
    final rows = await _db.from('tenders').select().order('deadline',
        ascending: true, nullsFirst: false);
    final locs = await _db.from('locations').select();
    final byTender = <String, List<TenderLocation>>{};
    for (final l in (locs as List)) {
      final loc = TenderLocation.fromMap(l);
      if (loc.tenderId != null) {
        byTender.putIfAbsent(loc.tenderId!, () => []).add(loc);
      }
    }
    return (rows as List)
        .map((r) => Tender.fromMap(r, locations: byTender[r['id']] ?? []))
        .toList();
  }

  Future<void> setHeart(String id, bool hearted) =>
      _db.from('tenders').update({'hearted': hearted}).eq('id', id);

  Future<void> setStatus(String id, TenderStatus s) =>
      _db.from('tenders').update({'status': s.name}).eq('id', id);
}
