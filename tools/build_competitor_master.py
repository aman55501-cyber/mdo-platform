"""Build briefs/COMPETITOR_TENDER_MASTER_<date>.xlsx from the Tender247 Missed Opportunities export.
EDGE rule (Aman, 2026-10-12): VWLR has a PFT siding with 3 rail lines; a tender is an edge only if the MINE or the PLANT is within 150 km of VWLR.
Locations come from mdo_edge.classify (rules, no guessing: an end with no match is left blank / Unknown). Costs are live formulas in Settings.
Usage: python tools/build_competitor_master.py <tender247_export.xlsx> <out.xlsx>"""
import sys, os, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdo_freight, mdo_edge  # noqa: E402

ROAD_QUOTE = 5.0   # Rs per tonne-km, Aman 2026-10-12 ("approx")


def read(path):
    sys.path.insert(0, "/tmp/claude-0")
    from readx import read as r
    return r(path)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def xl_date(v):
    n = num(v)
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(n))) if n and n > 30000 else v


def main(export_path, out_path):
    exp = read(export_path)
    wb = Workbook()
    H = Font(bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F3A5F"); IN = PatternFill("solid", fgColor="FFF2CC")
    GREEN = PatternFill("solid", fgColor="D9EAD3"); AMBER = PatternFill("solid", fgColor="FCE5CD")
    ws = wb.active; ws.title = "Read me"
    lines = [
        ("Competitor tender master: edge, road and rail cost", True),
        ("EDGE RULE (yours): VWLR has a PFT siding with 3 rail lines. A tender is an edge only if the MINE or the PLANT is within 150 km of VWLR. Everything else is context on rivals.", False),
        ("Edge = Yes (an end within 150 km straight-line) | Borderline (150-180 km, about 150 km by road) | No (known ends all far) | Unknown (an end could not be identified from the title).", False),
        ("Locations: mine and plant are matched from the tender title to the nearest listed town. Town coordinates were geocoded on 2026-10-12; the exact mine site is approximate [UNVERIFIED]. Reference point is Chaple, Kharsia block (your VWLR siding).", False),
        ("Costs per tonne: ROAD = near-end km x road factor x your road rate (+GST, +handling). RAIL = FOIS class 145A base tariff for the far-end km when that end is known, plus GST. FOIS excludes surcharges and siding charges. No tonnage is in the export, so no per-contract figures.", False),
        ("Winner's own cost is unknown: this sheet shows where freight could have been your lever, not who would have won.", False),
        ("Yellow cells are inputs. Everything else is a formula.", False),
    ]
    for i, (t, b) in enumerate(lines, 1):
        c = ws.cell(i, 1, t); c.font = Font(bold=b, size=14 if b else 11); c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 150

    st = wb.create_sheet("Settings")
    rows = [
        ("Setting", "Value", "Note"),
        ("Road rate Rs per tonne-km (YOUR NUMBER)", ROAD_QUOTE, "Aman, chat 2026-10-12: approx Rs 5 per tonne per km (approximate, not a written quote). Clear to use the illustrative rate."),
        ("Illustrative road Rs per tonne-km", 2.75, "Indicative general-truck range Rs 2.0-3.5. NOT a coal quote."),
        ("Road rate used", '=IF(ISNUMBER(B3),B3,B4)', None),
        ("Rate status", '=IF(ISNUMBER(B3),"Your quote","ILLUSTRATIVE - replace with your quote")', None),
        ("Road km = straight-line x", 1.3, "Typical road winding factor [UNVERIFIED]."),
        ("Rail km = straight-line x", 1.2, "Typical rail winding factor [UNVERIFIED]. FOIS charges on railway chargeable distance."),
        ("Loading + unloading Rs per tonne (per handling)", None, "Blank counts as 0."),
        ("GST on freight %", 5, "Per the FOIS calculator note."),
        ("Take GST credit? (Y/N)", "N", "Y removes GST from the cost."),
        ("Minimum road Rs per tonne", None, "Blank = no minimum."),
        ("Minimum haul km", 25, "Floor for a same-town haul [UNVERIFIED]."),
        ("Edge radius km", mdo_edge.EDGE_KM, "Your rule: 150 km."),
        ("Reference point", mdo_edge.REF[2], "Chaple, Kharsia (VWLR). Town-centre geocode; siding is within about 1-2 km of it."),
    ]
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            cell = st.cell(r, c, v)
            if r == 2: cell.font = H; cell.fill = HF
    for ref in ("B3", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "B13"): st[ref].fill = IN
    st.column_dimensions["A"].width = 48; st.column_dimensions["B"].width = 34; st.column_dimensions["C"].width = 95

    fo = wb.create_sheet("FOIS 145A")
    for c, h in enumerate(["From km", "To km", "Rs per tonne (base, train load)"], 1):
        x = fo.cell(1, c, h); x.font = H; x.fill = HF
    for r, (lo, hi, rate) in enumerate(mdo_freight.RAIL_145A, 2):
        fo.cell(r, 1, lo); fo.cell(r, 2, hi); fo.cell(r, 3, rate)
    n = len(mdo_freight.RAIL_145A) + 1
    fo.cell(n + 2, 1, mdo_freight.RAIL_145A_SOURCE); fo.column_dimensions["C"].width = 32

    ms = wb.create_sheet("Master", 1)
    heads = ["Edge", "Basis", "Mine (matched)", "Mine km", "Plant / siding (matched)", "Plant km", "Nearest end km", "TR247 ID", "Tender ref", "Title", "Category", "Buyer", "State",
             "Tender city", "Close date", "Stage", "Winner", "Tracked rivals bidding", "Bidders", "Contract Rs Cr",
             "Road leg Rs/t (near end to your siding)", "Far-end km", "Rail leg Rs/t (your siding to far end, FOIS 145A)", "Indicative total Rs/t", "Rate status"]
    for c, h in enumerate(heads, 1):
        x = ms.cell(1, c, h); x.font = H; x.fill = HF; x.alignment = Alignment(wrap_text=True, vertical="top")
    order = {"Yes": 0, "Borderline": 1, "Unknown": 2, "No": 3}
    recs = []
    for row in exp["Approve list"][1:]:
        if not row.get("A"): continue
        x = mdo_edge.classify(row.get("C", ""), row.get("E", ""), row.get("F", ""), row.get("G", ""), row.get("R") or "", row.get("S") or "")
        recs.append((x, row))
    recs.sort(key=lambda t: (order[t[0]["edge"]], min([k for k in (t[0]["mine_km"], t[0]["plant_km"]) if k is not None], default=9999)))
    r = 2
    for x, row in recs:
        mk, pk = x["mine_km"], x["plant_km"]
        known = [k for k in (mk, pk) if k is not None]
        near = min(known) if known else None
        far = max(known) if len(known) == 2 and max(known) != near else None
        vals = [x["edge"], x["basis"], x["mine"], mk, x["plant"], pk, near, row.get("A"), row.get("B"), row.get("C"), row.get("D"), row.get("E"), row.get("F"),
                row.get("G"), xl_date(row.get("I")), row.get("L"), row.get("M"), row.get("N"), row.get("O"), num(row.get("P"))]
        for c, v in enumerate(vals, 1): ms.cell(r, c, v)
        ms.cell(r, 15).number_format = "yyyy-mm-dd"
        ms.cell(r, 21, f'=IF(ISNUMBER(G{r}),MAX(MAX(G{r},Settings!$B$13)*Settings!$B$7*Settings!$B$5,IF(ISNUMBER(Settings!$B$12),Settings!$B$12,0))*(1+IF(Settings!$B$11="Y",0,Settings!$B$10/100))+N(Settings!$B$9),"")')
        ms.cell(r, 22, far)
        ms.cell(r, 23, f'=IF(ISNUMBER(V{r}),IF(V{r}*Settings!$B$8>1000,"beyond table",IFERROR(LOOKUP(V{r}*Settings!$B$8,\'FOIS 145A\'!$A$2:$A${n},\'FOIS 145A\'!$C$2:$C${n})*(1+IF(Settings!$B$11="Y",0,Settings!$B$10/100)),"")),"")')
        ms.cell(r, 24, f'=IF(AND(ISNUMBER(U{r}),ISNUMBER(W{r})),U{r}+W{r},"")')
        ms.cell(r, 25, "=Settings!$B$6")
        ms.cell(r, 1).fill = GREEN if x["edge"] == "Yes" else (AMBER if x["edge"] == "Borderline" else PatternFill())
        r += 1
    last = r - 1
    for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVWXY", [11, 34, 30, 8, 30, 8, 9, 10, 18, 60, 22, 30, 14, 14, 11, 10, 26, 34, 12, 10, 14, 9, 16, 14, 30]):
        ms.column_dimensions[col].width = w
    ms.freeze_panes = "K2"; ms.auto_filter.ref = f"A1:Y{last}"
    for rr in range(2, last + 1):
        for cc in (21, 23, 24): ms.cell(rr, cc).number_format = "#,##0"

    sm = wb.create_sheet("Edge summary", 2)
    cats = sorted({row.get("D") for _, row in recs if row.get("D")})
    for c, h in enumerate(["Category", "Edge: Yes", "Borderline", "Unknown", "No", "Edge Yes awarded Rs Cr (sum)"], 1):
        x = sm.cell(1, c, h); x.font = H; x.fill = HF
    for i, cat in enumerate(cats, 2):
        sm.cell(i, 1, cat)
        for j, e in enumerate(("Yes", "Borderline", "Unknown", "No"), 2):
            sm.cell(i, j, f'=COUNTIFS(Master!$K$2:$K${last},$A{i},Master!$A$2:$A${last},"{e}")')
        sm.cell(i, 6, f'=SUMIFS(Master!$T$2:$T${last},Master!$K$2:$K${last},$A{i},Master!$A$2:$A${last},"Yes")')
    t = len(cats) + 2
    sm.cell(t, 1, "Total").font = Font(bold=True)
    for j in range(2, 7):
        col = chr(64 + j); sm.cell(t, j, f"=SUM({col}2:{col}{t-1})")
    sm.column_dimensions["A"].width = 38
    for col in "BCDEF": sm.column_dimensions[col].width = 18

    cp = wb.create_sheet("Competitors")
    for c, h in enumerate(["Group", "Competitor", "Tenders bid (export)", "Wins (export)", "Won Rs Cr (export)", "Wins in this sheet", "Wins on EDGE tenders (Yes)", "Edge tenders they won, Rs Cr"], 1):
        x = cp.cell(1, c, h); x.font = H; x.fill = HF; x.alignment = Alignment(wrap_text=True, vertical="top")
    rr = 2
    for row in exp.get("Competitor summary", [])[1:]:
        nm = row.get("B")
        if not nm: continue
        cp.cell(rr, 1, row.get("A")); cp.cell(rr, 2, nm); cp.cell(rr, 3, num(row.get("C"))); cp.cell(rr, 4, num(row.get("D"))); cp.cell(rr, 5, num(row.get("E")))
        pat = f'"*"&IFERROR(LEFT(B{rr},FIND(" /",B{rr})-1),B{rr})&"*"'
        cp.cell(rr, 6, f'=COUNTIF(Master!$Q$2:$Q${last},{pat})')
        cp.cell(rr, 7, f'=COUNTIFS(Master!$Q$2:$Q${last},{pat},Master!$A$2:$A${last},"Yes")')
        cp.cell(rr, 8, f'=SUMIFS(Master!$T$2:$T${last},Master!$Q$2:$Q${last},{pat},Master!$A$2:$A${last},"Yes")')
        rr += 1
    cp.cell(rr + 1, 1, "Names match the Tender247 winner spelling; counts can differ from the export when spellings differ.")
    cp.column_dimensions["B"].width = 34
    for col in "CDEFGH": cp.column_dimensions[col].width = 18
    wb.save(out_path)
    from collections import Counter
    print(Counter(x["edge"] for x, _ in recs), "->", out_path)


if __name__ == "__main__":
    main(*sys.argv[1:3])
