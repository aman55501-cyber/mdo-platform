import 'package:flutter/material.dart';
import '../models/org_profile.dart';
import '../models/tender.dart';
import '../services/appetite.dart';
import '../widgets/tender_card.dart';

enum ListFilter { relevant, live, big, hearted, all }

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
  ListFilter _f = ListFilter.relevant;

  List<Tender> get _items {
    List<Tender> list;
    switch (_f) {
      case ListFilter.live:
        list = widget.tenders
            .where((t) => t.status == TenderStatus.live)
            .toList();
      case ListFilter.hearted:
        list = widget.tenders.where((t) => t.hearted).toList();
      case ListFilter.relevant:
        list = widget.tenders
            .where((t) => widget.relevantIds.contains(t.id))
            .toList();
      case ListFilter.big:
        list = widget.tenders
            .where((t) =>
                widget.relevantIds.contains(t.id) && Appetite.meetsFloor(t))
            .toList();
      case ListFilter.all:
        list = List.of(widget.tenders);
    }
    // Preferred buyers (Q27) float to the top, order otherwise preserved.
    list.sort((a, b) =>
        (Appetite.isPreferred(b) ? 1 : 0) - (Appetite.isPreferred(a) ? 1 : 0));
    return list;
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
                    ListFilter.big => 'Big ₹250Cr+',
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
