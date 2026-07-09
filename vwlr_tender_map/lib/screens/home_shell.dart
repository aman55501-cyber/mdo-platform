import 'package:flutter/material.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../services/eligibility.dart';
import '../services/notifications.dart';
import '../services/tender_repository.dart';
import 'dashboard_screen.dart';
import 'list_screen.dart';
import 'map_screen.dart';
import 'tender_detail_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  final _repo = TenderRepository();
  int _tab = 0;
  bool _loading = true;
  String? _error;
  OrgProfile? _org;
  List<Tender> _tenders = [];
  Set<String> _eligibleIds = {};
  Set<String> _relevantIds = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final org = await _repo.orgProfile();
      final tenders = await _repo.tenders();
      final eligible = <String>{};
      final relevant = <String>{};
      for (final t in tenders) {
        final e = assess(t, org);
        if (e.eligible) eligible.add(t.id);
        // Relevant = you're eligible, or there's no published PQC to rule you
        // out. Only tenders with a real gap vs your profile are excluded.
        if (e.eligible || e.noPublishedCriteria) relevant.add(t.id);
      }
      await Notifications.syncFor(tenders);
      setState(() {
        _org = org;
        _tenders = tenders;
        _eligibleIds = eligible;
        _relevantIds = relevant;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _heart(Tender t) async {
    await _repo.setHeart(t.id, !t.hearted);
    await _load();
  }

  Future<void> _status(Tender t, TenderStatus s) async {
    await _repo.setStatus(t.id, s);
    await _load();
  }

  void _open(Tender t) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => TenderDetailScreen(
        tender: t,
        org: _org!,
        onHeart: () async {
          await _heart(t);
          if (mounted) Navigator.of(context).pop();
        },
        onStatus: (s) async {
          await _status(t, s);
          if (mounted) Navigator.of(context).pop();
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.cloud_off, size: 40, color: Colors.black38),
              const SizedBox(height: 12),
              Text('Could not load tenders\n$_error',
                  textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ]),
          ),
        ),
      );
    }

    final titles = ['Map', 'Tenders', 'Dashboard'];
    final pages = [
      MapScreen(org: _org!, tenders: _tenders, onOpen: _open),
      ListScreen(
          tenders: _tenders,
          org: _org!,
          relevantIds: _relevantIds,
          onOpen: _open,
          onHeart: _heart),
      DashboardScreen(
          org: _org!, tenders: _tenders, eligibleIds: _eligibleIds),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text('VWLR Tender Map · ${titles[_tab]}'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: pages[_tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.map_outlined), label: 'Map'),
          NavigationDestination(
              icon: Icon(Icons.list_alt_outlined), label: 'Tenders'),
          NavigationDestination(
              icon: Icon(Icons.dashboard_outlined), label: 'Dashboard'),
        ],
      ),
    );
  }
}
