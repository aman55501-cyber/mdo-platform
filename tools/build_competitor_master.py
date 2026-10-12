"""Build briefs/COMPETITOR_TENDER_MASTER_<date>.xlsx: every missed tender with winner, rivals, distance and indicative road / rail cost.
Formulas are live: type your road quote in Settings!B3 and every row recalculates. Rail rates are the FOIS class 145A base tariff (mdo_freight.RAIL_145A).
Inputs: the by-distance workbook (distances are straight-line from Raigarh) and the Tender247 export (competitor summary).
Usage: python tools/build_competitor_master.py <distance.xlsx> <tender247_export.xlsx> <out.xlsx>"""
import sys, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mdo_freight  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def read(path):
    sys.path.insert(0, "/tmp/claude-0")
    from readx import read as r
    return r(path)


def main(dist_path, export_path, out_path):
    dist, exp = read(dist_path), read(export_path)
    wb = Workbook()
    H = Font(bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F3A5F"); IN = PatternFill("solid", fgColor="FFF2CC")
    # Read me
    ws = wb.active; ws.title = "Read me"
    lines = [
        ("Competitor tender master: road and rail cost", True),
        ("Source: Tender247 Missed Opportunities export (11 Oct 2026) via the by-distance workbook. Every row is a closed tender; winner, rivals, bidders and contract value are from Tender247.", False),
        ("DISTANCE is straight-line km from Raigarh to the tender's district headquarters [UNVERIFIED, approximate coordinates]. Road and rail km are straight-line x the factors in Settings. These are estimates for banding, not route distances.", False),
        ("RAIL cost = FOIS class 145A train-load BASE tariff (official, read 2026-10-12), plus GST. It excludes busy-season surcharge, siding and terminal charges, rebates. Valid only where a siding exists at both ends.", False),
        ("ROAD cost = estimated road km x road rate per tonne-km. Settings!B3 is YOUR tipper quote. Until you type it, an ILLUSTRATIVE rate is used and the sheet says so. Replace it before acting.", False),
        ("No tonnage is in the export, so costs are per tonne, never per contract. 'Winner's base' (the winner's own cost) is unknown: this sheet shows which tenders were near enough that freight could have decided them, not who would have won.", False),
        ("Yellow cells are inputs. Everything else is a formula.", False),
    ]
    for i, (t, b) in enumerate(lines, 1):
        c = ws.cell(i, 1, t); c.font = Font(bold=b, size=14 if b else 11); c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 140
    # Settings
    st = wb.create_sheet("Settings")
    rows = [
        ("Setting", "Value", "Note"),
        ("Road quote Rs per tonne-km (YOUR NUMBER)", None, "Type your tipper rate. Leave blank to use the illustrative rate."),
        ("Illustrative road Rs per tonne-km", 2.75, "Midpoint of an indicative Rs 2.0-3.5 range from general truck rates. NOT a coal quote."),
        ("Road rate used", '=IF(ISNUMBER(B3),B3,B4)', None),
        ("Rate status", '=IF(ISNUMBER(B3),"Your quote","ILLUSTRATIVE - replace with your quote")', None),
        ("Road km = straight-line x", 1.3, "Typical road winding factor [UNVERIFIED]."),
        ("Rail km = straight-line x", 1.2, "Typical rail winding factor [UNVERIFIED]. FOIS charges on railway chargeable distance."),
        ("Loading + unloading Rs per tonne (per handling)", None, "Blank counts as 0. Rail adds one extra handling at the plant end."),
        ("GST on freight %", 5, "Per FOIS calculator note for rail; same applied to road."),
        ("Take GST credit? (Y/N)", "N", "Y removes GST from the cost."),
        ("Minimum road Rs per tonne", None, "Blank = no minimum."),
        ("Minimum haul km", 25, "Same-district tenders show 0 km straight-line; this floor keeps the cost above zero [UNVERIFIED]."),
    ]
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            cell = st.cell(r, c, v)
            if r == 2: cell.font = H; cell.fill = HF
    for ref in ("B3", "B6", "B7", "B8", "B9", "B10", "B11", "B12", "B13"): st[ref].fill = IN
    st.column_dimensions["A"].width = 48; st.column_dimensions["B"].width = 34; st.column_dimensions["C"].width = 90
    # FOIS
    fo = wb.create_sheet("FOIS 145A")
    for c, h in enumerate(["From km", "To km", "Rs per tonne (base, train load)"], 1):
        x = fo.cell(1, c, h); x.font = H; x.fill = HF
    for r, (lo, hi, rate) in enumerate(mdo_freight.RAIL_145A, 2):
        fo.cell(r, 1, lo); fo.cell(r, 2, hi); fo.cell(r, 3, rate)
    n = len(mdo_freight.RAIL_145A) + 1
    fo.cell(n + 2, 1, mdo_freight.RAIL_145A_SOURCE)
    fo.column_dimensions["C"].width = 32
    # Master
    ms = wb.create_sheet("Master", 1)
    heads = ["Band", "TR247 ID", "Tender ref", "Title", "Category", "Buyer", "State", "District", "Close date", "Stage", "Winner", "Tracked rivals bidding",
             "Bidders", "Contract Rs Cr", "Straight km", "Est road km", "Est rail km", "Road Rs/t (all-in)", "Rail base Rs/t (FOIS 145A)", "Rail Rs/t (all-in)",
             "Cheaper mode", "Saving Rs/t", "Rail plausible?", "Rate status"]
    for c, h in enumerate(heads, 1):
        x = ms.cell(1, c, h); x.font = H; x.fill = HF; x.alignment = Alignment(wrap_text=True, vertical="top")
    r = 2
    bands = [k for k in dist if k not in ("Read me", "Band summary")]
    for sheet in bands:
        for row in dist[sheet][1:]:
            if not row.get("C"): continue
            def g(col): return row.get(col)
            def num(v):
                try: return float(v)
                except (TypeError, ValueError): return None
            vals = [g("A"), g("C"), g("D"), g("E"), g("F"), g("G"), g("H"), g("I"), g("J"), g("K"), g("L"), g("M"), g("N"), num(g("O")), num(g("B"))]
            for c, v in enumerate(vals, 1): ms.cell(r, c, v)
            ms.cell(r, 16, f"=MAX(O{r},Settings!$B$13)*Settings!$B$7")
            ms.cell(r, 17, f"=MAX(O{r},Settings!$B$13)*Settings!$B$8")
            ms.cell(r, 18, f"=MAX(P{r}*Settings!$B$5,IF(ISNUMBER(Settings!$B$12),Settings!$B$12,0))*(1+IF(Settings!$B$11=\"Y\",0,Settings!$B$10/100))+N(Settings!$B$9)")
            ms.cell(r, 19, f'=IF(Q{r}>1000,"beyond table",IFERROR(LOOKUP(Q{r},\'FOIS 145A\'!$A$2:$A${n},\'FOIS 145A\'!$C$2:$C${n}),""))')
            ms.cell(r, 20, f'=IF(ISNUMBER(S{r}),S{r}*(1+IF(Settings!$B$11="Y",0,Settings!$B$10/100))+2*N(Settings!$B$9),"")')
            ms.cell(r, 21, f'=IF(ISNUMBER(T{r}),IF(T{r}<R{r},"Rail","Road"),"")')
            ms.cell(r, 22, f'=IF(ISNUMBER(T{r}),ABS(R{r}-T{r}),"")')
            ms.cell(r, 23, f'=IF(OR(ISNUMBER(SEARCH("siding",D{r})),ISNUMBER(SEARCH("rcr",D{r})),ISNUMBER(SEARCH("rail",D{r})),ISNUMBER(SEARCH("wagon",D{r}))),"Yes - siding/rail in title","Check")')
            ms.cell(r, 24, "=Settings!$B$6")
            r += 1
    last = r - 1
    for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVWX", [12, 10, 18, 60, 22, 30, 14, 14, 11, 10, 26, 34, 12, 10, 9, 9, 9, 12, 12, 12, 9, 9, 22, 30]):
        ms.column_dimensions[col].width = w
    ms.freeze_panes = "E2"; ms.auto_filter.ref = f"A1:X{last}"
    for rr in range(2, last + 1):
        for cc in (18, 19, 20, 22): ms.cell(rr, cc).number_format = "#,##0"
    # Competitors
    cp = wb.create_sheet("Competitors")
    for c, h in enumerate(["Group", "Competitor", "Tenders bid (export)", "Wins (export)", "Won Rs Cr (export)", "Wins in this sheet", "Wins within 300 km of Raigarh"] , 1):
        x = cp.cell(1, c, h); x.font = H; x.fill = HF; x.alignment = Alignment(wrap_text=True, vertical="top")
    rr = 2
    for row in exp.get("Competitor summary", [])[1:]:
        nm = row.get("B")
        if not nm: continue
        def num(v):
            try: return float(v)
            except (TypeError, ValueError): return None
        cp.cell(rr, 1, row.get("A")); cp.cell(rr, 2, nm); cp.cell(rr, 3, num(row.get("C"))); cp.cell(rr, 4, num(row.get("D"))); cp.cell(rr, 5, num(row.get("E")))
        cp.cell(rr, 6, f'=COUNTIF(Master!$K$2:$K${last},"*"&IFERROR(LEFT(B{rr},FIND(" /",B{rr})-1),B{rr})&"*")')
        cp.cell(rr, 7, f'=COUNTIFS(Master!$K$2:$K${last},"*"&IFERROR(LEFT(B{rr},FIND(" /",B{rr})-1),B{rr})&"*",Master!$O$2:$O${last},"<=300")')
        rr += 1
    cp.cell(rr + 1, 1, "Names must match the Tender247 winner spelling; 'Wins in this sheet' matches by name; it can differ from the export when spellings differ or a tender has no district.")
    cp.column_dimensions["B"].width = 34
    for col in "CDEFG": cp.column_dimensions[col].width = 18
    wb.save(out_path)
    print(f"{last-1} tenders, {rr-2} competitors -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
