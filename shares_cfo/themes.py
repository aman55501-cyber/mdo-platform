"""Themed sector overlay for the holdings view.

The broker gives each holding a broad sector (Banking, IT, Energy…). On top of that
this adds the *thematic* buckets Aman asked for — Defence, Railways, Renewables, PSU —
which cut across broad sectors (e.g. BEL is both "Capital Goods" and Defence). When a
symbol matches a theme it's shown under that theme; otherwise it keeps its broad sector.

This is a curated starter map of well-known NSE names — deliberately explicit so it's
easy to correct. Priority is most-specific first (Defence > Railways > Renewables > PSU)
so a stock that fits several lands in the sharpest one. Add/adjust symbols freely.
"""

from __future__ import annotations

# Most-specific themes first — the first list a symbol appears in wins.
DEFENCE = {
    "HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "GRSE", "BEML", "DATAPATTNS",
    "MTARTECH", "PARAS", "ZENTEC", "IDEAFORGE", "DYNAMATECH", "ASTRAMICRO",
    "SOLARINDS", "APOLLO", "UNIMECH", "DCXINDIA", "AVANTEL", "TARIL",
}
RAILWAYS = {
    "IRCTC", "IRFC", "RVNL", "IRCON", "RITES", "TITAGARH", "TEXMACO", "JWL",
    "RAILTEL", "CONCOR", "JUPITER", "ORIENTTECH",
}
RENEWABLES = {
    "ADANIGREEN", "TATAPOWER", "JSWENERGY", "INOXWIND", "SUZLON", "WEBSOL",
    "ORIENTGREEN", "KPIGREEN", "SWSOLAR", "WAAREE", "PREMIERENE", "BOROSIL",
    "NHPC", "SJVN", "GENSOL", "ACMESOLAR", "NTPCGREEN",
}
# PSU is broad — public-sector undertakings across banks/energy/finance/PSE.
PSU = {
    "SBIN", "BANKBARODA", "PNB", "CANBK", "UNIONBANK", "IOB", "CENTRALBK", "PSB",
    "MAHABANK", "INDIANB", "UCOBANK", "BANKINDIA",
    "ONGC", "COALINDIA", "NTPC", "POWERGRID", "GAIL", "IOC", "BPCL", "HPCL",
    "OIL", "NLCINDIA", "RECLTD", "PFC", "IRFC", "NBCC", "HUDCO", "SAIL", "NMDC",
    "GMDC", "BHEL", "MOIL", "SJVN", "NHPC", "IREDA", "MRPL", "GSPL", "OFSS",
    "CONCOR", "RITES", "IRCON", "RVNL", "RAILTEL", "MAZDOCK", "COCHINSHIP",
    "GRSE", "BEML", "HAL", "BEL", "BDL",
}

_THEMES = (
    ("Defence", DEFENCE),
    ("Railways", RAILWAYS),
    ("Renewables", RENEWABLES),
    ("PSU", PSU),
)


# Sector labels that must stay upper-case (title() would mangle them to "It", "Fmcg").
_ACRONYMS = {"IT", "FMCG", "PSU", "NBFC", "FMCD", "IT-ENABLED", "BFSI"}


def _pretty(sector: str) -> str:
    s = sector.strip()
    return s.upper() if s.upper() in _ACRONYMS else s.title()


def theme_of(symbol: str, base_sector: str | None = None) -> str:
    """Return the thematic bucket for a symbol, else its broad sector, else 'Other'."""
    s = (symbol or "").upper().split("-")[0]
    for name, members in _THEMES:
        if s in members:
            return name
    bs = (base_sector or "").strip()
    return _pretty(bs) if bs and bs.upper() not in ("UNKNOWN", "NA", "") else "Other"
