import 'package:flutter/material.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../widgets/tender_card.dart';

enum ListFilter { all, live, hearted, relevant }

class ListScreen extends StatefulWidget {
  final List<Tender> tenders;
  final OrgProfile org;
  final Set<String> relevantIds;
  final void Function(Tender) onOpen;
  final void Function(Tender) onHeart;
  const ListScreen(
      {super.key,
      required this.tenders,
      required this.org,
      required this.relevantIds,
      required this.onOpen,
      required this.onHeart});

  @override
  State<ListScreen> createState() => _ListScreenState();
}

class _ListScreenState extends State<ListScreen> {
  ListFilter _f = ListFilter.all;

  List<Tender> get _items {
    switch (_f) {
      case ListFilter.live:
        return widget.tenders
            .where((t) => t.status == TenderStatus.live)
            .toList();
      case ListFilter.hearted:
        return widget.tenders.where((t) => t.hearted).toList();
      case ListFilter.relevant:
        return widget.tenders
            .where((t) => widget.relevantIds.contains(t.id))
            .toList();
      case ListFilter.all:
        return widget.tenders;
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Column(
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
          child: Row(children: [
            for (final f in ListFilter.values)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                  label: Text(switch (f) {
                    ListFilter.all => 'All',
                    ListFilter.live => 'Live',
                    ListFilter.hearted => 'Watching',
                    ListFilter.relevant => 'Relevant',
                  }),
                  selected: _f == f,
                  onSelected: (_) => setState(() => _f = f),
                ),
              ),
          ]),
        ),
        Expanded(
          child: items.isEmpty
              ? const Center(child: Text('No tenders in this view'))
              : ListView.separated(
                  padding: const EdgeInsets.all(12),
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, i) => TenderCard(
                    tender: items[i],
                    org: widget.org,
                    onTap: () => widget.onOpen(items[i]),
                    onHeart: () => widget.onHeart(items[i]),
                  ),
                ),
        ),
      ],
    );
  }
}
