"""
Tests for st_specific validation + normalisation.
"""
import pandas as pd
import pytest

from app.services.st_specific import (
    REQUIRED_COLS,
    validate_dataframe,
    _coerce_pos_int,
    _coerce_bool,
)


# ─── Validation ─────────────────────────────────────────────────────

class TestValidateDataframe:
    def test_empty(self):
        r = validate_dataframe(pd.DataFrame())
        assert r.summary == {"input": 0, "valid": 0, "errors": 0}

    def test_missing_required(self):
        r = validate_dataframe(pd.DataFrame([{"WERKS": "HN10"}]))
        assert r.summary["valid"] == 0
        assert "Missing required" in r.errors.iloc[0]["error"]

    def test_clean_minimal(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001},
        ])
        r = validate_dataframe(df)
        assert r.summary == {"input": 1, "valid": 1, "errors": 0}
        assert r.valid.iloc[0]["WERKS"] == "HN10"
        assert pd.isna(r.valid.iloc[0]["TARGET_QTY"])  # not provided
        assert r.valid.iloc[0]["IS_ACTIVE"] == 1

    def test_blank_werks_rejected(self):
        df = pd.DataFrame([
            {"WERKS": "  ", "MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001},
        ])
        r = validate_dataframe(df)
        assert r.summary["valid"] == 0
        assert "WERKS" in r.errors.iloc[0]["error"]

    def test_invalid_target_qty_rejected(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M_TEES_HS",
             "GEN_ART_NUMBER": 1001, "TARGET_QTY": "abc"},
            {"WERKS": "HN10", "MAJ_CAT": "M_TEES_HS",
             "GEN_ART_NUMBER": 1002, "TARGET_QTY": -5},
        ])
        r = validate_dataframe(df)
        assert r.summary["valid"] == 0
        assert r.summary["errors"] == 2

    def test_target_qty_blank_is_ok(self):
        # NULL TARGET_QTY = "use OPT_MBQ" — explicitly allowed
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M_TEES_HS",
             "GEN_ART_NUMBER": 1001, "TARGET_QTY": ""},
            {"WERKS": "HN10", "MAJ_CAT": "M_TEES_HS",
             "GEN_ART_NUMBER": 1002, "TARGET_QTY": None},
        ])
        r = validate_dataframe(df)
        assert r.summary["valid"] == 2

    def test_werks_uppercased(self):
        df = pd.DataFrame([
            {"WERKS": "hn10", "MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001},
        ])
        r = validate_dataframe(df)
        assert r.valid.iloc[0]["WERKS"] == "HN10"

    def test_clr_uppercased_and_optional(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1, "CLR": "blk"},
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 2},
        ])
        r = validate_dataframe(df)
        assert r.valid.iloc[0]["CLR"] == "BLK"
        assert pd.isna(r.valid.iloc[1]["CLR"])

    def test_reversed_dates_rejected(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1,
             "EFFECTIVE_FROM": "2026-12-31", "EFFECTIVE_TO": "2026-01-01"},
        ])
        r = validate_dataframe(df)
        assert r.summary["valid"] == 0
        assert "EFFECTIVE_FROM" in r.errors.iloc[0]["error"]

    def test_unparseable_date_rejected(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1,
             "EFFECTIVE_FROM": "not-a-date", "EFFECTIVE_TO": "2026-12-31"},
        ])
        r = validate_dataframe(df)
        assert r.summary["valid"] == 0

    def test_partial_failure_keeps_valid_rows(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1001},
            {"WERKS": "",     "MAJ_CAT": "M", "GEN_ART_NUMBER": 1002},  # bad
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1003},
        ])
        r = validate_dataframe(df)
        assert r.summary == {"input": 3, "valid": 2, "errors": 1}

    def test_normalised_output_shape(self):
        df = pd.DataFrame([
            {"WERKS": "HN10", "MAJ_CAT": "M", "GEN_ART_NUMBER": 1001},
        ])
        r = validate_dataframe(df)
        # Pinned for bulk_upsert downstream
        assert list(r.valid.columns) == [
            "WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "TARGET_QTY",
            "REASON", "IS_ACTIVE", "EFFECTIVE_FROM", "EFFECTIVE_TO",
        ]


# ─── Coercion helpers ───────────────────────────────────────────────

class TestCoercionHelpers:
    @pytest.mark.parametrize("v,expected", [
        (1, 1), ("42", 42), (3.0, 3),
        (0, None), (-5, None), ("abc", None),
        (None, None), ("", None), (float("nan"), None),
    ])
    def test_coerce_pos_int(self, v, expected):
        assert _coerce_pos_int(v) == expected

    @pytest.mark.parametrize("v,expected", [
        (True, True), ("1", True), ("yes", True),
        (False, False), ("0", False), ("no", False), (None, False), ("", False),
    ])
    def test_coerce_bool(self, v, expected):
        assert _coerce_bool(v) == expected


# ─── Constants ──────────────────────────────────────────────────────

def test_required_cols_pinned():
    assert set(REQUIRED_COLS) == {"WERKS", "MAJ_CAT", "GEN_ART_NUMBER"}
