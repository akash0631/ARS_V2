"""
Tests for the Delivery Order workbook builder.

Uses an in-memory pandas fixture + openpyxl reader so no DB is required.
The point of these tests is correctness contracts the dispatch team
relies on:
  - HOLD never appears as dispatch (only SHIP_QTY > 0 reaches detail)
  - Per-store totals reconcile to the detail rows
  - The BDC sheet has only the columns SAP needs, in the right names
  - Sheet count and order are stable
"""
import io

import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")  # skip cleanly if not installed

from app.services.delivery_order import (
    REQUIRED_COLS,
    build_delivery_order_workbook,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _sample_alloc() -> pd.DataFrame:
    """5 rows across 2 RDCs, 3 stores, 2 MAJ_CATs.
    One row has SHIP_QTY=0 + HOLD_QTY>0 (must NOT appear in detail)."""
    return pd.DataFrame([
        {"WERKS": "HN10", "RDC": "DH24", "MAJ_CAT": "M_TEES_HS",
         "GEN_ART_NUMBER": 1001, "GEN_ART_DESC": "Black Tee",
         "CLR": "BLK", "VAR_ART": 100101, "VAR_DESC": "Tee S",
         "SZ": "S", "MRP": 599.0, "PAK_SZ": 1,
         "OPT_TYPE": "RL", "FINAL_OPT_TYPE": "RL",
         "SHIP_QTY": 4.0, "HOLD_QTY": 0.0,
         "ALLOC_STATUS": "ALLOCATED", "ALLOC_BATCH_ID": "B1"},
        {"WERKS": "HN10", "RDC": "DH24", "MAJ_CAT": "M_TEES_HS",
         "GEN_ART_NUMBER": 1001, "GEN_ART_DESC": "Black Tee",
         "CLR": "BLK", "VAR_ART": 100102, "VAR_DESC": "Tee M",
         "SZ": "M", "MRP": 599.0, "PAK_SZ": 1,
         "OPT_TYPE": "RL", "FINAL_OPT_TYPE": "RL",
         "SHIP_QTY": 8.0, "HOLD_QTY": 0.0,
         "ALLOC_STATUS": "ALLOCATED", "ALLOC_BATCH_ID": "B1"},
        {"WERKS": "HN14", "RDC": "DH24", "MAJ_CAT": "M_TEES_HS",
         "GEN_ART_NUMBER": 1001, "GEN_ART_DESC": "Black Tee",
         "CLR": "BLK", "VAR_ART": 100101, "VAR_DESC": "Tee S",
         "SZ": "S", "MRP": 599.0, "PAK_SZ": 1,
         "OPT_TYPE": "RL", "FINAL_OPT_TYPE": "RL",
         "SHIP_QTY": 3.0, "HOLD_QTY": 0.0,
         "ALLOC_STATUS": "ALLOCATED", "ALLOC_BATCH_ID": "B1"},
        # TBL row with hold buffer — both SHIP and HOLD positive
        {"WERKS": "HN22", "RDC": "DW01", "MAJ_CAT": "L_KURTI",
         "GEN_ART_NUMBER": 2003, "GEN_ART_DESC": "Blue Kurti",
         "CLR": "BLU", "VAR_ART": 200301, "VAR_DESC": "Kurti M",
         "SZ": "M", "MRP": 1299.0, "PAK_SZ": 1,
         "OPT_TYPE": "TBL", "FINAL_OPT_TYPE": "NL",
         "SHIP_QTY": 14.0, "HOLD_QTY": 4.0,
         "ALLOC_STATUS": "ALLOCATED", "ALLOC_BATCH_ID": "B1"},
        # Pure hold — must NOT appear in dispatch detail or BDC sheet
        {"WERKS": "HN22", "RDC": "DW01", "MAJ_CAT": "L_KURTI",
         "GEN_ART_NUMBER": 2003, "GEN_ART_DESC": "Blue Kurti",
         "CLR": "BLU", "VAR_ART": 200302, "VAR_DESC": "Kurti L",
         "SZ": "L", "MRP": 1299.0, "PAK_SZ": 1,
         "OPT_TYPE": "TBL", "FINAL_OPT_TYPE": "NL",
         "SHIP_QTY": 0.0, "HOLD_QTY": 5.0,
         "ALLOC_STATUS": "PARTIAL", "ALLOC_BATCH_ID": "B1"},
    ])


def _read_sheets(xlsx_bytes: bytes) -> dict:
    return pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=None, engine="openpyxl")


# ─────────────────────────────────────────────────────────────────────
# Required columns
# ─────────────────────────────────────────────────────────────────────

class TestRequiredColumns:
    def test_missing_required_column_raises(self):
        df = _sample_alloc().drop(columns=["RDC"])
        with pytest.raises(ValueError, match="missing required columns"):
            build_delivery_order_workbook(df)

    def test_required_cols_constant_is_complete(self):
        # Defends the contract — if anyone changes REQUIRED_COLS, they must
        # also update both the docstring and load_alloc_for_session SQL.
        assert set(REQUIRED_COLS) == {
            "WERKS", "RDC", "MAJ_CAT", "GEN_ART_NUMBER",
            "CLR", "VAR_ART", "SZ", "SHIP_QTY",
        }


# ─────────────────────────────────────────────────────────────────────
# Workbook structure
# ─────────────────────────────────────────────────────────────────────

class TestWorkbookStructure:
    def test_returns_bytes(self):
        out = build_delivery_order_workbook(_sample_alloc())
        assert isinstance(out, (bytes, bytearray))
        assert len(out) > 0

    def test_six_sheets_in_expected_order(self):
        out = build_delivery_order_workbook(_sample_alloc())
        wb = openpyxl.load_workbook(io.BytesIO(out), read_only=True)
        # Run_Meta first so the operator opens straight to the summary.
        assert wb.sheetnames == [
            "Run_Meta",
            "Dispatch_Detail",
            "Store_Summary",
            "RDC_Summary",
            "Article_Summary",
            "BDC_Format",
        ]


# ─────────────────────────────────────────────────────────────────────
# Hold isolation (the contract that matters most)
# ─────────────────────────────────────────────────────────────────────

class TestHoldIsolation:
    def test_pure_hold_row_excluded_from_dispatch(self):
        # The (HN22, kurti L, ship=0, hold=5) row must not show up
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        detail = sheets["Dispatch_Detail"]
        assert 200302 not in set(detail["VAR_ART"])

    def test_hold_excluded_from_bdc(self):
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        bdc = sheets["BDC_Format"]
        assert (bdc["QUANTITY"] > 0).all()
        assert 200302 not in set(bdc["ARTICLE_NUMBER"])

    def test_store_summary_reports_hold_separately(self):
        # HN22 has ship=14 + hold=9 (4 + 5) → both surface in Store_Summary,
        # but the dispatch sheet only shows the ship side.
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        ss = sheets["Store_Summary"].set_index("WERKS")
        assert ss.loc["HN22", "ship_qty"] == 14
        assert ss.loc["HN22", "hold_qty"] == 9


# ─────────────────────────────────────────────────────────────────────
# Reconciliation — totals must agree across sheets
# ─────────────────────────────────────────────────────────────────────

class TestReconciliation:
    def test_detail_ship_total_matches_store_summary(self):
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        detail_total = sheets["Dispatch_Detail"]["SHIP_QTY"].sum()
        store_total  = sheets["Store_Summary"]["ship_qty"].sum()
        assert detail_total == store_total == 29  # 4+8+3+14

    def test_rdc_summary_partitions_correctly(self):
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        rdc = sheets["RDC_Summary"].set_index("RDC")
        # DH24: HN10 size S+M (4+8) + HN14 size S (3) = 15
        # DW01: HN22 ship 14
        assert rdc.loc["DH24", "ship_qty"] == 15
        assert rdc.loc["DW01", "ship_qty"] == 14

    def test_article_summary_sums_per_article(self):
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        art = sheets["Article_Summary"].set_index("GEN_ART_NUMBER")
        assert art.loc[1001, "ship_qty"] == 15  # 4 + 8 + 3
        assert art.loc[2003, "ship_qty"] == 14
        assert art.loc[1001, "stores"] == 2
        assert art.loc[2003, "stores"] == 1


# ─────────────────────────────────────────────────────────────────────
# BDC sheet — has SAP-friendly column names
# ─────────────────────────────────────────────────────────────────────

class TestBdcSheet:
    def test_bdc_columns_renamed_for_sap(self):
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        bdc = sheets["BDC_Format"]
        # SAP wants ARTICLE_NUMBER and QUANTITY, not VAR_ART and SHIP_QTY
        assert list(bdc.columns) == ["RDC", "WERKS", "ARTICLE_NUMBER", "SZ", "QUANTITY"]

    def test_bdc_quantity_is_integer(self):
        # SAP STO uploads reject decimals on apparel quantity fields.
        out = build_delivery_order_workbook(_sample_alloc())
        sheets = _read_sheets(out)
        bdc = sheets["BDC_Format"]
        assert bdc["QUANTITY"].dtype.kind in ("i", "u")  # integer family


# ─────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_all_hold_no_ship_produces_empty_dispatch(self):
        df = _sample_alloc().assign(SHIP_QTY=0)
        df["HOLD_QTY"] = [1, 2, 3, 4, 5]
        out = build_delivery_order_workbook(df)
        sheets = _read_sheets(out)
        assert len(sheets["Dispatch_Detail"]) == 0
        assert len(sheets["BDC_Format"]) == 0
        # Store_Summary still surfaces hold positions for visibility
        assert sheets["Store_Summary"]["hold_qty"].sum() == 15

    def test_missing_optional_columns_does_not_crash(self):
        df = _sample_alloc()[list(REQUIRED_COLS)]
        out = build_delivery_order_workbook(df)
        sheets = _read_sheets(out)
        # All sheets present; detail just has fewer columns
        assert "Dispatch_Detail" in sheets
        assert sheets["Dispatch_Detail"]["SHIP_QTY"].sum() == 29

    def test_run_meta_reflects_inputs(self):
        out = build_delivery_order_workbook(
            _sample_alloc(), run_meta={"session_id": "S2026-05-07-001"}
        )
        sheets = _read_sheets(out)
        meta = sheets["Run_Meta"].set_index("key")["value"].to_dict()
        assert meta["session_id"] == "S2026-05-07-001"
        assert int(meta["stores_count"]) == 3
        assert int(meta["rdcs_count"]) == 2
        assert int(meta["majcats_count"]) == 2
        # 4 rows ship, 1 row pure-hold → rows_shipping = 4
        assert int(meta["rows_shipping"]) == 4
        assert int(meta["rows_input"]) == 5
