"""
Tests for the allocation-correctness health snapshot.

Pure logic only — DB upserts exercised by the /listing/health-snapshots
integration. compute_metrics() and apply_alert_thresholds() are the
contracts that matter.
"""
import json

import pandas as pd
import pytest

from app.services.alloc_health import (
    DEFAULT_THRESHOLDS,
    apply_alert_thresholds,
    compute_metrics,
)


# ─── Fixtures ───────────────────────────────────────────────────────

def _alloc_normal():
    """A run with healthy distribution: ~60% RL, ~20% TBC, ~10% TBL, ~10% MIX."""
    rows = []
    rdcs = ["DH24", "DW01"]
    # 6 RL OPTs (each 1 row in alloc)
    for i, rdc in enumerate(rdcs * 3):
        rows.append({
            "WERKS": f"ST{i:02d}", "RDC": rdc, "MAJ_CAT": "M_TEES_HS",
            "GEN_ART_NUMBER": 1000 + i, "CLR": "BLK",
            "VAR_ART": str(100100 + i), "SZ": "M",
            "OPT_TYPE": "RL", "FINAL_OPT_TYPE": "RL",
            "SHIP_QTY": 10.0, "HOLD_QTY": 0.0,
            "ALLOC_QTY": 10.0, "OPT_REQ": 12.0,
            "FNL_Q": 100.0, "POOL_CONSUMED": 30.0,
            "ALLOC_TYPE": "PRIMARY",
        })
    # 2 TBC
    for i in range(2):
        rows.append({
            "WERKS": f"ST10", "RDC": "DH24", "MAJ_CAT": "M_TEES_HS",
            "GEN_ART_NUMBER": 2000 + i, "CLR": "RED",
            "VAR_ART": str(200100 + i), "SZ": "M",
            "OPT_TYPE": "TBC", "FINAL_OPT_TYPE": "TBC",
            "SHIP_QTY": 5.0, "HOLD_QTY": 0.0,
            "ALLOC_QTY": 5.0, "OPT_REQ": 8.0,
            "FNL_Q": 50.0, "POOL_CONSUMED": 5.0,
            "ALLOC_TYPE": "PRIMARY",
        })
    # 1 TBL
    rows.append({
        "WERKS": "ST11", "RDC": "DW01", "MAJ_CAT": "M_TEES_HS",
        "GEN_ART_NUMBER": 3001, "CLR": "BLU",
        "VAR_ART": "300101", "SZ": "M",
        "OPT_TYPE": "TBL", "FINAL_OPT_TYPE": "NL",
        "SHIP_QTY": 14.0, "HOLD_QTY": 4.0,
        "ALLOC_QTY": 14.0, "OPT_REQ": 14.0,
        "FNL_Q": 30.0, "POOL_CONSUMED": 18.0,
        "ALLOC_TYPE": "PRIMARY",
    })
    # 1 MIX (dispatched 0)
    rows.append({
        "WERKS": "ST12", "RDC": "DH24", "MAJ_CAT": "M_TEES_HS",
        "GEN_ART_NUMBER": 4001, "CLR": "GRN",
        "VAR_ART": "400101", "SZ": "M",
        "OPT_TYPE": "MIX", "FINAL_OPT_TYPE": "MIX",
        "SHIP_QTY": 0.0, "HOLD_QTY": 0.0,
        "ALLOC_QTY": 0.0, "OPT_REQ": 0.0,
        "FNL_Q": 0.0, "POOL_CONSUMED": 0.0,
        "ALLOC_TYPE": "PRIMARY",
    })
    return pd.DataFrame(rows)


def _working_normal(alloc_df):
    """Working frame deduplicated to one row per OPT for type counting."""
    return alloc_df.drop_duplicates(["WERKS", "MAJ_CAT", "GEN_ART_NUMBER"]).copy()


# ─── compute_metrics ────────────────────────────────────────────────

class TestComputeMetricsHappyPath:
    def setup_method(self):
        self.alloc = _alloc_normal()
        self.working = _working_normal(self.alloc)
        self.working["MJ_REQ"] = 100.0
        self.metrics = compute_metrics(self.alloc, self.working)

    def test_top_line_totals(self):
        assert self.metrics["TOTAL_SHIP_QTY"] == 6 * 10 + 2 * 5 + 14 + 0
        assert self.metrics["TOTAL_HOLD_QTY"] == 4
        # 6 RL stores (ST00..ST05) + 1 TBC store (ST10) + 1 TBL store (ST11)
        # ST12 (MIX) has SHIP_QTY=0 so does NOT count as 'touched'.
        assert self.metrics["STORES_TOUCHED"] == 8
        assert self.metrics["MAJCATS_TOUCHED"] == 1

    def test_classification_percentages(self):
        # 6 RL + 2 TBC + 1 TBL + 1 MIX = 10 OPTs
        assert self.metrics["TOTAL_OPTS"] == 10
        assert self.metrics["PCT_RL"]  == 60.0
        assert self.metrics["PCT_TBC"] == 20.0
        assert self.metrics["PCT_TBL"] == 10.0
        assert self.metrics["PCT_MIX"] == 10.0

    def test_fill_rate_excludes_mix(self):
        # RL: 10/12 = 0.833, TBC: 5/8 = 0.625, TBL: 14/14 = 1.0, MIX excluded
        # avg = (0.833*6 + 0.625*2 + 1.0*1) / 9
        assert 70 < self.metrics["AVG_FILL_RATE_PCT"] < 90

    def test_no_fallback(self):
        assert self.metrics["FALLBACK_FILLS"] == 0
        assert self.metrics["FALLBACK_QTY"] == 0.0
        assert self.metrics["FALLBACK_PCT"] == 0.0

    def test_rdc_pool_consumed_json(self):
        rdc_data = json.loads(self.metrics["RDC_POOL_CONSUMED_PCT_JSON"])
        assert "DH24" in rdc_data and "DW01" in rdc_data
        # Each value is a percentage in [0, 100]
        for pct in rdc_data.values():
            assert 0 <= pct <= 100


# ─── Empty / edge inputs ───────────────────────────────────────────

class TestEmptyInputs:
    def test_empty_alloc_returns_default_metrics(self):
        m = compute_metrics(pd.DataFrame())
        assert m["TOTAL_SHIP_QTY"] == 0
        assert m["TOTAL_OPTS"] is None
        assert m["FALLBACK_PCT"] == 0.0
        # The ALERT_* keys are layered later by apply_alert_thresholds —
        # bare compute_metrics just returns the raw metrics.

    def test_none_alloc_returns_default_metrics(self):
        m = compute_metrics(None)
        assert m["TOTAL_SHIP_QTY"] == 0


# ─── Fallback rows surface in their own metric ─────────────────────

class TestFallbackMetric:
    def test_majcat_fallback_counted_separately(self):
        df = _alloc_normal()
        # Tag two rows as MAJ_CAT_FALLBACK
        df.loc[0:1, "ALLOC_TYPE"] = "MAJ_CAT_FALLBACK"
        m = compute_metrics(df)
        assert m["FALLBACK_FILLS"] == 2
        assert m["FALLBACK_QTY"] == 20.0   # 2 rows × 10 ship
        assert m["FALLBACK_PCT"] > 0

    def test_fallback_pct_is_share_of_total_ship(self):
        df = _alloc_normal()
        df.loc[0:1, "ALLOC_TYPE"] = "MAJ_CAT_FALLBACK"
        m = compute_metrics(df)
        # 20 of total ship 84 → ~23.8%
        assert abs(m["FALLBACK_PCT"] - round(100 * 20 / 84, 2)) < 0.5


# ─── Budget pressure ────────────────────────────────────────────────

class TestBudgetPressure:
    def test_zero_pressure_when_all_stores_above_50pct(self):
        alloc = _alloc_normal()
        working = _working_normal(alloc)
        # Drop the MIX-only store (ST12) — it has MJ_REQ but zero ship
        # by definition of MIX, so it would correctly register as
        # "under-served." For this happy-path fixture we want only the
        # stores that actually got allocated.
        working = working[working["WERKS"] != "ST12"]
        # Per-store ship: RL stores ship 10, TBC store (ST10) ships 10
        # (2 × 5), TBL store (ST11) ships 14. Set MJ_REQ small enough that
        # even the smallest ship (10) hits ≥ 50% — i.e. MJ_REQ ≤ 20.
        working["MJ_REQ"] = 15.0
        m = compute_metrics(alloc, working)
        assert m["STORES_BUDGET_BROKEN_PCT"] == 0.0

    def test_pressure_when_stores_under_filled(self):
        alloc = _alloc_normal()
        working = _working_normal(alloc)
        working["MJ_REQ"] = 1000.0  # everyone way under-served
        m = compute_metrics(alloc, working)
        # Most stores are under 50% fill ratio → high pressure
        assert m["STORES_BUDGET_BROKEN_PCT"] > 50


# ─── Alert thresholds ──────────────────────────────────────────────

class TestAlertThresholds:
    def test_default_thresholds_constant(self):
        # If anyone changes the default thresholds without notice,
        # the dashboards re-trigger alerts on yesterday's data —
        # pin the values explicitly.
        assert DEFAULT_THRESHOLDS == {
            "high_mix_pct":        30.0,
            "low_fill_pct":        60.0,
            "high_fallback_pct":   30.0,
            "budget_pressure_pct": 20.0,
        }

    def test_high_mix_alert_fires(self):
        m = {"PCT_MIX": 35, "AVG_FILL_RATE_PCT": 70,
             "FALLBACK_PCT": 0, "STORES_BUDGET_BROKEN_PCT": 0}
        out = apply_alert_thresholds(m)
        assert out["ALERT_HIGH_MIX"] is True
        assert out["ALERT_LOW_FILL"] is False
        assert out["ALERT_HIGH_FALLBACK"] is False
        assert out["ALERT_BUDGET_PRESSURE"] is False

    def test_low_fill_alert_only_fires_when_positive(self):
        # Fill rate of 0 (empty run) must NOT trip the low-fill alert —
        # it just means nothing was allocated, which is a different signal
        # (would surface as TOTAL_SHIP_QTY=0).
        m = {"PCT_MIX": 0, "AVG_FILL_RATE_PCT": 0,
             "FALLBACK_PCT": 0, "STORES_BUDGET_BROKEN_PCT": 0}
        out = apply_alert_thresholds(m)
        assert out["ALERT_LOW_FILL"] is False

    def test_low_fill_alert_fires_when_below_60(self):
        m = {"PCT_MIX": 0, "AVG_FILL_RATE_PCT": 45,
             "FALLBACK_PCT": 0, "STORES_BUDGET_BROKEN_PCT": 0}
        out = apply_alert_thresholds(m)
        assert out["ALERT_LOW_FILL"] is True

    def test_high_fallback_alert(self):
        m = {"PCT_MIX": 0, "AVG_FILL_RATE_PCT": 70,
             "FALLBACK_PCT": 35, "STORES_BUDGET_BROKEN_PCT": 0}
        out = apply_alert_thresholds(m)
        assert out["ALERT_HIGH_FALLBACK"] is True

    def test_budget_pressure_alert(self):
        m = {"PCT_MIX": 0, "AVG_FILL_RATE_PCT": 70,
             "FALLBACK_PCT": 0, "STORES_BUDGET_BROKEN_PCT": 25}
        out = apply_alert_thresholds(m)
        assert out["ALERT_BUDGET_PRESSURE"] is True

    def test_custom_thresholds_override_defaults(self):
        m = {"PCT_MIX": 25, "AVG_FILL_RATE_PCT": 70,
             "FALLBACK_PCT": 0, "STORES_BUDGET_BROKEN_PCT": 0}
        # Default high_mix_pct=30 → no alert at 25
        assert apply_alert_thresholds(m)["ALERT_HIGH_MIX"] is False
        # Custom threshold of 20 → alert at 25
        out = apply_alert_thresholds(m, thresholds={"high_mix_pct": 20})
        assert out["ALERT_HIGH_MIX"] is True

    def test_apply_does_not_mutate_input(self):
        m = {"PCT_MIX": 35}
        original = dict(m)
        apply_alert_thresholds(m)
        assert m == original  # no mutation
