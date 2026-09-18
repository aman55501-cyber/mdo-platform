"""Frontier panels — the not-yet-connected surfaces, rendered as honest empty
states (rule 1: never a blank div; say what's missing and what would fill it).

Each returns BLOCKED with a summary naming the missing source and its owner, so the
Growth tab is truthful about what LIFEOS cannot yet see. As a real source lands,
its fetcher is replaced with a live one.
"""

from __future__ import annotations

from . import BLOCKED, Result


def _blocked(name: str, what: str, fills: str) -> Result:
    return Result(
        name=name,
        status=BLOCKED,
        summary=f"{what}",
        reason="no source connected yet",
        extra={"rows": [{"gutter": "NEED", "severity": "warning", "text": what, "meta": f"would fill it: {fills}"}]},
    )


def fetch_rnd() -> Result:
    return _blocked(
        "rnd",
        "R&D — no source connected (aspirational).",
        "a Notion R&D pipeline or project tracker; today this is a placeholder by your call.",
    )


def fetch_hiring() -> Result:
    return _blocked(
        "hiring",
        "Hiring — no source connected.",
        "an ATS / a Notion roles DB (open roles, stage, owner) or GM Satya's hiring sheet.",
    )


def fetch_expansion() -> Result:
    return _blocked(
        "expansion",
        "Expansion — no source connected.",
        "a Notion pipeline of new-site / new-brand opportunities with stage and owner.",
    )


def fetch_usa() -> Result:
    return _blocked(
        "usa",
        "USA — no source connected.",
        "whatever the US track becomes (entity, bank, or deal tracker) — name it and I wire it.",
    )


def fetch_hotel_pms() -> Result:
    return _blocked(
        "hotel_ans_pms",
        "Hotel ANS rooms & banquet — blocked: IDS Next PMS exports do not exist yet.",
        "the IDS Next PMS export (occupancy, ADR, segment mix, banquet) — owed by GM Satya.",
    )
