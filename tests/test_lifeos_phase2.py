"""Phase 2 acceptance — the ERP export ingest ramp (the Sales-first surface).

Proves the three honest states (OWED / MAP? / LIVE), the report-kind inference, the
tolerant number parsing, and the mapping application — all without network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeos.ingest import (
    Table,
    apply_mapping,
    infer_report,
    read_table,
    to_number,
)


def test_infer_report():
    assert infer_report("VWLR Purchase Order Book Sep.csv") == "pipeline"
    assert infer_report("dadu_sales_register.xlsx") == "invoiced"
    assert infer_report("Outstanding Receivables.csv") == "receivables"
    assert infer_report("random.csv") == "pipeline"  # default = the funnel
    # VWLR sells offtake agreements, not orders — read as committed quantity
    assert infer_report("VWLR Supply Agreements 26-27.csv") == "agreements"
    assert infer_report("coal_offtake_contract.xlsx") == "agreements"


def test_to_number_tolerant():
    assert to_number("1,23,456") == 123456.0
    assert to_number("₹ 45,000.50") == 45000.50
    assert to_number("") == 0.0
    assert to_number("n/a") == 0.0
    assert to_number(1200) == 1200.0


def test_read_csv_and_apply_mapping(tmp_path):
    f = tmp_path / "vwlr_order_book.csv"
    f.write_text(
        "Party Name,Amount,Status\n"
        "NTPC Korba,\"12,00,000\",Open\n"
        "SAIL Bhilai,\"8,50,000\",Dispatched\n",
        encoding="utf-8",
    )
    table = read_table(f)
    assert table.report == "pipeline"
    assert table.headers == ["Party Name", "Amount", "Status"]
    mapping = {"columns": {"entity": {"literal": "VWLR"}, "party": "Party Name",
                           "amount": "Amount", "status": "Status"}}
    rows = apply_mapping(table, mapping)
    assert rows[0].get("entity") == "VWLR"
    assert rows[0].get("party") == "NTPC Korba"
    assert to_number(rows[0].get("amount")) == 1200000.0


# ── the source states ─────────────────────────────────────────────────────────
def _run_source(monkeypatch, tmp_path, mappings_dir: Path | None = None):
    monkeypatch.setenv("LIFEOS_ERP_DIR", str(tmp_path / "drop"))
    if mappings_dir:
        monkeypatch.setenv("LIFEOS_MAPPINGS_DIR", str(mappings_dir))
    else:
        monkeypatch.delenv("LIFEOS_MAPPINGS_DIR", raising=False)
    from lifeos.sources import erp_sales
    return erp_sales.fetch()


def test_all_owed_when_no_files(monkeypatch, tmp_path):
    r = _run_source(monkeypatch, tmp_path)
    assert r.status == "blocked"          # majority-focus surface says so, not blank
    assert r.data["fed"] == 0
    assert r.data["owed"] == r.data["total"]
    owed_rows = [x for x in r.extra["rows"] if x["gutter"] == "OWED"]
    assert len(owed_rows) == r.data["total"]
    assert "owed by" in owed_rows[0]["meta"]


def test_mapping_needed_when_file_but_no_mapping(monkeypatch, tmp_path):
    drop = tmp_path / "drop" / "vwlr"
    drop.mkdir(parents=True)
    (drop / "vwlr_order_book.csv").write_text("Party Name,Amount\nNTPC,100\n", encoding="utf-8")
    r = _run_source(monkeypatch, tmp_path, mappings_dir=tmp_path / "empty_maps")
    vwlr = next(x for x in r.extra["rows"] if x["text"] == "VWLR")
    assert vwlr["gutter"] == "MAP?"
    assert "mapping needed" in vwlr["meta"] and "Party Name" in vwlr["meta"]
    assert r.data["mapping_needed"] == 1


def test_agreements_summarized_by_quantity(monkeypatch, tmp_path):
    from datetime import date, timedelta
    drop = tmp_path / "drop" / "vwlr"
    drop.mkdir(parents=True)
    soon = (date.today() + timedelta(days=10)).isoformat()
    (drop / "vwlr_supply_agreements.csv").write_text(
        "Party,Qty,Delivered,PeriodEnd\n"
        f"NTPC Korba,50000,20000,{soon}\n"
        "Trader X,30000,30000,2027-01-01\n",
        encoding="utf-8",
    )
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "vwlr.yaml").write_text(
        "columns:\n  entity: {literal: VWLR}\n  party: Party\n  qty: Qty\n"
        "  delivered_qty: Delivered\n  period_end: PeriodEnd\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIFEOS_ERP_DIR", str(tmp_path / "drop"))
    monkeypatch.setenv("LIFEOS_MAPPINGS_DIR", str(maps))
    from lifeos.sources import erp_sales
    r = erp_sales.fetch()
    vwlr = next(x for x in r.extra["rows"] if x["text"] == "VWLR")
    assert vwlr["gutter"] == "LIVE"
    assert "2 agreements" in vwlr["meta"]
    assert "contracted 80,000" in vwlr["meta"]
    assert "delivered 50,000" in vwlr["meta"] and "bal 30,000" in vwlr["meta"]
    assert "1 expiring ≤30d" in vwlr["meta"]  # only NTPC's period ends within 30d


def test_live_when_file_and_mapping(monkeypatch, tmp_path):
    drop = tmp_path / "drop" / "vwlr"
    drop.mkdir(parents=True)
    (drop / "vwlr_order_book.csv").write_text(
        "Party Name,Amount\nNTPC Korba,1200000\nSAIL,850000\n", encoding="utf-8"
    )
    maps = tmp_path / "maps"
    maps.mkdir()
    (maps / "vwlr.yaml").write_text(
        "columns:\n  entity: {literal: VWLR}\n  party: Party Name\n  amount: Amount\n",
        encoding="utf-8",
    )
    r = _run_source(monkeypatch, tmp_path, mappings_dir=maps)
    assert r.status == "ok"
    assert r.data["fed"] == 1
    vwlr = next(x for x in r.extra["rows"] if x["text"] == "VWLR")
    assert vwlr["gutter"] == "LIVE"
    assert "pipeline" in vwlr["meta"] and "20.50 L" in vwlr["meta"]  # 20.5 lakh total
