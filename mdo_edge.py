"""Where is the tender's mine and plant relative to VWLR? Aman, chat 2026-10-12: "either one of the mines or the plant must be at most 150 km of
my geographical location, those are the only tenders I have an edge on" (VWLR has a PFT siding with 3 rail lines).

Pure rules, no network. Coordinates are town centres geocoded with Open-Meteo on 2026-10-12 (verified for the towns listed with 'geo'); mine and plant
sites are matched to the nearest listed town, which is approximate [UNVERIFIED for the exact site]. Reference point = Raigarh town until Aman names the
siding station. Straight-line km. 150 km straight-line is already a longer road; the 150-180 band is flagged BORDERLINE."""
from __future__ import annotations

import math
import re

REF = (21.89764, 83.3966, "Raigarh town (siding station not yet given)")
EDGE_KM = 150.0
BORDER_KM = 180.0

# keyword regex -> (label, lat, lon).  Order matters: first match wins within a field, but all matches are kept and the nearest is used.
PLACES = [
    (r"\bmanoharpur\b|\bocpl\b|\bdarlipali\b|\bdlcmp\b|\bhemgir\b", "Hemgir / Manoharpur (Sundargarh)", 21.94754, 83.70306),
    (r"\btalabira\b|\bhirakud\b", "Talabira (near Sambalpur/Jharsuguda)", 21.7, 83.95),
    (r"\bib[\s-]?valley\b|\bib\b mine|\blakhanpur\b|\bbelpahar\b|\blilari\b|\bsamaleswari\b|\blajkura\b|\bkulda\b|\bgarjanbahal\b|\bbasundhara\b", "IB Valley (Jharsuguda)", 21.8218, 83.8458),
    (r"\bbrajrajnagar\b|\bbrajarajnagar\b|\bjharsuguda\b", "Brajrajnagar / Jharsuguda", 21.81667, 83.91667),
    (r"\bsambalpur\b|\bburla\b", "Sambalpur", 21.46527, 83.97573),
    (r"\bkharsia\b|\bbaroud\b|\bsarasmal\b|\bbhalumuda\b", "Kharsia (Raigarh)", 21.98953, 83.10476),
    (r"\bgharghoda\b|\bgare[\s-]?pelma\b|\bgare palma\b", "Gharghoda (Raigarh)", 22.17427, 83.3517),
    (r"\btamnar\b", "Tamnar (Raigarh)", 22.09006, 83.44088),
    (r"\bdharamjaigarh\b|\bdurgapur\b|\btlcmp\b|\btalaipalli\b|\bchhal\b|\bkchp\b", "Dharamjaigarh (Raigarh)", 22.46376, 83.21127),
    (r"\blara\b|\bntpc lara\b|\braigarh\b", "Raigarh", 21.89764, 83.3966),
    (r"\bpathalgaon\b", "Pathalgaon (Jashpur)", 22.55656, 83.46355),
    (r"\bkorba\b|\bgevra\b|\bdipka\b|\bkusmunda\b|\bmanikpur\b|\bsaraipali\b|\bsrk rl\b|\bkorba stps\b|\bkstps\b|\bbalco\b|\bsurakachhar\b|\bkosa\b", "Korba", 22.3458, 82.69633),
    (r"\bkatghora\b|\bkartali\b|\bkuldiha\b", "Katghora (Korba)", 22.50247, 82.54279),
    (r"\bsipat\b|\bbilaspur\b|\bseepat\b|\bnagar bilaspur\b", "Bilaspur / Sipat", 22.08005, 82.15543),
    (r"\bchampa\b|\bjanjgir\b|\bakaltara\b", "Champa", 22.03532, 82.64234),
    (r"\bbaikunthpur\b|\bchirimiri\b|\brani atari\b|\bncph\b|\bkorea\b|\bkoriya\b|\bmanendragarh\b|\bhaldibari\b|\bsonhat\b", "Baikunthpur / Chirimiri (Korea)", 23.26206, 82.56051),
    (r"\bambikapur\b|\bsurguja\b|\bbishrampur\b|\bketki\b|\bamera\b|\bamgaon\b|\bbhatgaon\b|\bmahan\b|\bjainagar\b|\bgayatri\b|\bkartala\b|\bsurajpur\b", "Ambikapur / Surguja", 23.11892, 83.19537),
    (r"\bjashpur\b", "Jashpur", 22.88783, 84.13864),
    (r"\bbargarh\b", "Bargarh", 21.33348, 83.61905),
    (r"\bsundergarh\b|\bsundargarh\b", "Sundargarh district (IB Valley / Hemgir)", 21.94754, 83.70306),
    (r"\brourkela\b|\bnspcl\b|\bnspl\b|\bsail rourkela\b", "Rourkela", 22.22496, 84.86414),
    (r"\btalcher\b|\bkaniha\b|\bananta\b|\bjagannath\b|\blingaraj\b|\bbharatpur\b|\bhingula\b|\bbalanda\b|\bnalco\b|\bangul\b|\bmcl talcher\b", "Talcher / Angul", 20.94927, 85.23354),
]
# Known to be far (> 180 km); no coordinates needed. Used only to say the OTHER end is far, never to claim an edge.
FAR = re.compile(r"\bukni\b|\bpenganga\b|\bwani\b|\bumrer\b|\bsaoner\b|\bmungoli\b|\bpakri\b|\bmagadh\b|\bamrapali\b|\bsijua\b|\bsalanpur\b|\bkaro\b|\bakk\b|\bashoka\b|\bnk area\b|\bgonda\b|"
                 r"\bunchahar\b|\bnabinagar\b|\bkudgi\b|\bsimhadri\b|\bsolapur\b|\btelangana\b|\bramagundam\b|\btanda\b|\bbarh\b|\bkoradi\b|\bbrbcl\b|\bvsps\b|\bvisakhapatnam\b|"
                 r"\bjarangdih\b|\bkonar\b|\bkuju\b|\bghonsa\b|\bsingori\b|\bkolgaon\b|\bdamanjodi\b|\bkoraput\b|\bganjam\b|\bkeonjhar\b|\bjagatsinghpur\b|\bparadip\b|\bnorth karanpura\b|\bnkstpp?\b")

COAL_BUYERS = re.compile(r"south eastern coal|mahanadi coal|central coalfields|western coal|northern coalfields|eastern coal|bharat coking|singareni|coal india", re.I)


def km(a: tuple[float, float], b: tuple[float, float] = REF[:2]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _near(text: str) -> tuple[str, float] | None:
    """Nearest listed place named in the text, as (label, km from REF)."""
    best = None
    t = (text or "").lower()
    for pat, label, lat, lon in PLACES:
        if re.search(pat, t):
            d = km((lat, lon))
            if best is None or d < best[1]:
                best = (label, round(d))
    return best


def classify(title: str, buyer: str, state: str, city: str, mine_txt: str = "", plant_txt: str = "") -> dict:
    """-> {edge: Yes|Borderline|No|Unknown, mine, mine_km, plant, plant_km, basis}. Never invents: an end with no match stays unknown."""
    mine = _near(mine_txt) or _near(title.split(" to ")[0] if " to " in title else "")
    plant = _near(plant_txt) or (_near(title.split(" to ", 1)[1]) if " to " in title else None)
    basis = []
    if mine: basis.append("mine named in title")
    if plant: basis.append("plant/siding named in title")
    # a coal company's tender is at its own mine: the tender city is the mine district
    if not mine and COAL_BUYERS.search(buyer or ""):
        c = _near(city)
        if c:
            mine = (c[0] + " (tender city)", c[1]); basis.append("mine = coal company's tender city")
            if not plant:
                plant = mine; basis.append("siding = same area")
    if not plant and not COAL_BUYERS.search(buyer or "") and (state or "") in ("Chhattisgarh", "Orissa") and (city or "").lower() != "raipur":
        c = _near(city)      # plant company (NTPC, NALCO...) tendering at a city in the home states: the plant is there
        if c:
            plant = (c[0] + " (tender city)", c[1]); basis.append("plant = tender city")
    mf = bool(FAR.search(f"{title} {mine_txt}".lower())) and not mine
    # a coal company's own tender in a coal state far from Raigarh is at its mine there (CCL/BCCL/ECL Jharkhand-WB, WCL Maharashtra, NCL/SECL Madhya Pradesh)
    if not mine and not mf and COAL_BUYERS.search(buyer or "") and (state or "") in ("Jharkhand", "Maharashtra", "West Bengal", "Madhya Pradesh", "Uttar Pradesh", "Bihar", "Telangana", "Andhra Pradesh"):
        mf = True; basis.append("mine = coal company's tender in " + state)
    pf = bool(FAR.search(f"{title} {plant_txt}".lower())) and not plant
    # a plant company's tender city outside Chhattisgarh / Orissa is its own site (NTPC Raipur is only a regional office, so Raipur is ignored)
    if not plant and not pf and not COAL_BUYERS.search(buyer or "") and (state or "") not in ("Chhattisgarh", "Orissa", "") and (city or "").lower() != "raipur":
        pf = True; basis.append("plant = tender city in " + state)
    ends = [x for x in (mine, plant) if x]
    near_min = min((x[1] for x in ends), default=None)
    if near_min is not None and near_min <= EDGE_KM:
        edge = "Yes"
    elif near_min is not None and near_min <= BORDER_KM:
        edge = "Borderline"
    elif ends and (mf or pf or len(ends) == 2):
        edge = "No"
    elif mf and pf:
        edge = "No"
    elif ends:
        edge = "Unknown"     # one end known and far, the other not identified
    elif mf or pf:
        edge = "No" if (mf and pf) or (mf or pf) and not ends else "Unknown"
    else:
        edge = "Unknown"
    if edge == "No" and not ends:
        basis.append("named mine/plant is far")
    return {"edge": edge, "mine": mine[0] if mine else "", "mine_km": mine[1] if mine else None,
            "plant": plant[0] if plant else "", "plant_km": plant[1] if plant else None, "basis": "; ".join(basis) or "no location in title"}
