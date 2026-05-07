"""
Tests for the MAJ_CAT-level fallback planner.

Pure logic only — DB integration is exercised in the live pipeline.
The planner takes (gaps_df, pool_df) and returns a list of FallbackFill
records describing how to satisfy the gaps from unconsumed pool.
"""
import pandas as pd
import pytest

from app.services.majcat_fallback import (
    FALLBACK_TAG,
    FallbackFill,
    plan_fallback_fills,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _gaps(rows):
    return pd.DataFrame(rows, columns=["WERKS", "MAJ_CAT", "MJ_REQ", "ALREADY_FILLED", "gap"])


def _pool(rows):
    return pd.DataFrame(rows, columns=[
        "RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ", "FNL_Q_REM",
    ])


# ─────────────────────────────────────────────────────────────────────
# Empty / trivial inputs
# ─────────────────────────────────────────────────────────────────────

class TestEmptyInputs:
    def test_no_gaps_returns_empty(self):
        gaps = _gaps([])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 50)])
        assert plan_fallback_fills(gaps, pool) == []

    def test_no_pool_returns_empty(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([])
        assert plan_fallback_fills(gaps, pool) == []

    def test_zero_gap_skipped(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 100, 0)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 50)])
        assert plan_fallback_fills(gaps, pool) == []


# ─────────────────────────────────────────────────────────────────────
# The cap mechanic — fallback fills can never exceed max_fill_pct of MJ_REQ
# ─────────────────────────────────────────────────────────────────────

class TestCap:
    def test_default_cap_50_pct_of_mj_req(self):
        # MJ_REQ=100, gap=80, default max_fill_pct=0.5
        # → cap = 50, but gap is 80 → pool only fills up to 50 units.
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 20, 80)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool)
        assert len(out) == 1
        assert out[0].fill_qty == 50.0  # capped

    def test_custom_cap_25_pct(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 0, 100)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool, max_fill_pct=0.25)
        assert sum(f.fill_qty for f in out) == 25.0

    def test_full_cap_lets_pool_fill_entire_gap(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 30, 70)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool, max_fill_pct=1.0)
        assert sum(f.fill_qty for f in out) == 70.0


# ─────────────────────────────────────────────────────────────────────
# Pool consumption — first store gets first dibs, second store sees less
# ─────────────────────────────────────────────────────────────────────

class TestPoolConsumption:
    def test_first_store_consumes_pool(self):
        # Two stores compete for the same pool. HN10 alphabetically first
        # → consumes first. HN14 sees the residual.
        gaps = _gaps([
            ("HN10", "M_TEES_HS", 100, 60, 40),
            ("HN14", "M_TEES_HS", 100, 60, 40),
        ])
        pool = _pool([
            ("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 60),  # only 60 to share
        ])
        out = plan_fallback_fills(gaps, pool)
        # Each store capped at 50 (50% of 100 MJ_REQ)
        # HN10 takes 40 (= gap), 20 left in pool; HN14 takes its 40-cap-by-pool=20
        hn10 = sum(f.fill_qty for f in out if f.werks == "HN10")
        hn14 = sum(f.fill_qty for f in out if f.werks == "HN14")
        assert hn10 + hn14 == 60  # pool fully consumed
        assert hn10 == 40  # full gap (gap < cap)
        assert hn14 == 20  # what's left

    def test_pool_exhaustion_truncates(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 0, 100)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 10)])
        out = plan_fallback_fills(gaps, pool, max_fill_pct=1.0)
        assert sum(f.fill_qty for f in out) == 10.0  # only 10 in pool

    def test_largest_pool_consumed_first(self):
        # Greedy on pool size — bigger pools picked first to minimise slot fragmentation.
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([
            ("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 5),
            ("DH24", "M_TEES_HS", 1001, "BLK", 100102, "M", 100),
            ("DH24", "M_TEES_HS", 1001, "BLK", 100103, "L", 20),
        ])
        out = plan_fallback_fills(gaps, pool)
        # First fill should be from VAR_ART=100102 (the 100-unit pool).
        assert out[0].var_art == "100102"


# ─────────────────────────────────────────────────────────────────────
# Per-MAJ_CAT scoping — pool from category A doesn't help gap in category B
# ─────────────────────────────────────────────────────────────────────

class TestMajcatScoping:
    def test_pool_in_other_majcat_ignored(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([
            # Different MAJ_CAT — must not be used to fill M_TEES_HS gap
            ("DH24", "L_KURTI", 2001, "BLU", 200101, "M", 200),
        ])
        out = plan_fallback_fills(gaps, pool)
        assert out == []

    def test_pool_in_same_majcat_used(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool)
        assert len(out) == 1


# ─────────────────────────────────────────────────────────────────────
# RDC restriction — Two-DC routing hook
# ─────────────────────────────────────────────────────────────────────

class TestRdcRestriction:
    def test_store_only_pulls_from_allowed_rdcs(self):
        gaps = _gaps([
            ("HN10", "M_TEES_HS", 100, 60, 40),
            ("HN22", "M_TEES_HS", 100, 60, 40),
        ])
        pool = _pool([
            ("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200),
            ("DW01", "M_TEES_HS", 1002, "RED", 100201, "M", 200),
        ])
        rdc_map = {
            "HN10": ["DH24"],          # only DH24
            "HN22": ["DW01"],          # only DW01
        }
        out = plan_fallback_fills(gaps, pool, store_rdc_map=rdc_map)
        for f in out:
            if f.werks == "HN10":
                assert f.rdc == "DH24"
            elif f.werks == "HN22":
                assert f.rdc == "DW01"

    def test_store_with_no_allowed_rdcs_skipped(self):
        gaps = _gaps([("HN99", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool, store_rdc_map={"HN99": []})
        assert out == []


# ─────────────────────────────────────────────────────────────────────
# Output shape
# ─────────────────────────────────────────────────────────────────────

class TestOutputShape:
    def test_returns_fallback_fill_dataclass(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool)
        assert isinstance(out[0], FallbackFill)
        assert out[0].werks == "HN10"
        assert out[0].rdc == "DH24"
        assert out[0].maj_cat == "M_TEES_HS"
        assert out[0].gen_art_number == 1001
        assert out[0].var_art == "100101"
        assert out[0].sz == "S"

    def test_fill_qty_is_float(self):
        gaps = _gaps([("HN10", "M_TEES_HS", 100, 60, 40)])
        pool = _pool([("DH24", "M_TEES_HS", 1001, "BLK", 100101, "S", 200)])
        out = plan_fallback_fills(gaps, pool)
        assert isinstance(out[0].fill_qty, float)


# ─────────────────────────────────────────────────────────────────────
# Tag constant
# ─────────────────────────────────────────────────────────────────────

def test_fallback_tag_constant_pinned():
    # Pinned: changing this string requires updating the Health Snapshot
    # query that counts MAJ_CAT_FALLBACK rows separately.
    assert FALLBACK_TAG == "MAJ_CAT_FALLBACK"
