"""The entities whose sales LIFEOS tracks — the Sales-first surface.

Each entity has a Drive subfolder (where its ERP export lands) and who owes that
export (drives the "chase the missing export" nudge in the evolving loop). Sales
for the *other* entities is the majority focus, so all of them appear from day one:
an entity with no file renders NO EXPORT — <entity> — owed by <who>, never blank.

``owed_by`` values are a first pass — correct them freely; they only shape the
draft nudge, never anything that transacts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    slug: str          # Drive subfolder + mapping filename
    label: str         # display name
    owed_by: str       # who provides the export (for the chase nudge)
    focus: bool = True  # part of the "other entities" sales focus


# Order here is display order in the Sales tab. Each entity's sales shape (confirmed
# with Aman): VWLR = coal supply agreements/offtake (committed quantity); the Dadu /
# Raigarh entities = real-estate bookings / agreements-to-sell (value); Rukmani =
# infra work contracts; Hotel ANS = IDS Next PMS, not an ERP export. Aditi Investments
# is a portfolio (broker side), NOT a sales entity, so it is intentionally absent.
ENTITIES: list[Entity] = [
    Entity("vwlr", "VWLR", "site ERP — VWLR (coal supply agreements)"),
    Entity("dadu_developers", "Dadu Developers", "site ERP — Dadu Developers (bookings)"),
    Entity("dadu_builders", "Dadu Builders", "site ERP — Dadu Builders (bookings)"),
    Entity("raigarh_land", "Raigarh Land Venture", "site ERP — Raigarh Land Venture (bookings)"),
    Entity("rukmani_infra", "Rukmani Infrastructure", "site ERP — Rukmani Infrastructure (work contracts)"),
    Entity("hotel_ans", "Hotel ANS", "IDS Next PMS export (GM Satya)", focus=False),
]


def by_slug(slug: str) -> Entity | None:
    for e in ENTITIES:
        if e.slug == slug:
            return e
    return None
