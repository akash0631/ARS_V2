"""
Tests for focus_list validation + normalisation.

The DB writers (bulk_upsert, apply_focus_flags, list_entries, delete_entry)
need a live SQL Server connection so they live in integration tests
elsewhere. This file pins the pure logic — what an upload CSV must
look like and how rows get normalised before they hit MERGE.
"""
import pandas as pd
import pytest

from app.services.focus_list import (
    REQUIRED_COLS,
    VALID_FOCUS_TYPES,
    validate_dataframe,
    _coerce_positive_int,
    _coerce_bool,
    _strip_or_none,
)


# ─── Dataframe-level validation ─────────────────────────────────────

class TestValidateDataframe:
    def test_empty_input(self):
        result = validate_dataframe(pd.DataFrame())
        assert result.summary == {"input": 0, "valid": 0, "errors": 0}
        assert result.valid.empty
        assert result.errors.empty

    def test_missing_required_columns(self):
        df = pd.DataFrame([{"WERKS": "HN10"}])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 0
        assert result.summary["errors"] == 1
        assert "Missing required columns" in result.errors.iloc[0]["error"]

    def test_clean_minimal_input(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "W_CAP"},
            {"MAJ_CAT": "L_KURTI",   "GEN_ART_NUMBER": 2003, "FOCUS_TYPE": "WO_CAP"},
        ])
        result = validate_dataframe(df)
        assert result.summary == {"input": 2, "valid": 2, "errors": 0}
        # Optional columns get filled with sensible defaults.
        assert (result.valid["WERKS"].isna()).all()
        assert (result.valid["CLR"].isna()).all()
        assert (result.valid["IS_ACTIVE"] == 1).all()

    def test_focus_type_normalised_to_upper(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "w_cap"},
        ])
        result = validate_dataframe(df)
        assert result.valid.iloc[0]["FOCUS_TYPE"] == "W_CAP"

    def test_invalid_focus_type_rejected(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "HERO"},
        ])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 0
        assert "FOCUS_TYPE must be one of" in result.errors.iloc[0]["error"]

    def test_blank_majcat_rejected(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "  ", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "W_CAP"},
        ])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 0
        assert "MAJ_CAT" in result.errors.iloc[0]["error"]

    def test_non_numeric_gen_art_rejected(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": "abc", "FOCUS_TYPE": "W_CAP"},
        ])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 0
        assert "GEN_ART_NUMBER" in result.errors.iloc[0]["error"]

    def test_zero_or_negative_gen_art_rejected(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 0,  "FOCUS_TYPE": "W_CAP"},
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": -5, "FOCUS_TYPE": "W_CAP"},
        ])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 0
        assert result.summary["errors"] == 2

    def test_partial_failure_keeps_valid_rows(self):
        # Two good, one bad — valid frame must contain the two good ones,
        # errors frame must contain the one bad one.
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "W_CAP"},
            {"MAJ_CAT": "L_KURTI",   "GEN_ART_NUMBER": "x",  "FOCUS_TYPE": "W_CAP"},
            {"MAJ_CAT": "L_KURTI",   "GEN_ART_NUMBER": 2003, "FOCUS_TYPE": "WO_CAP"},
        ])
        result = validate_dataframe(df)
        assert result.summary == {"input": 3, "valid": 2, "errors": 1}
        assert set(result.valid["GEN_ART_NUMBER"].tolist()) == {1001, 2003}

    def test_werks_uppercased_and_blank_to_none(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001,
             "FOCUS_TYPE": "W_CAP", "WERKS": "hn10"},
            {"MAJ_CAT": "L_KURTI",   "GEN_ART_NUMBER": 2003,
             "FOCUS_TYPE": "WO_CAP", "WERKS": "  "},
        ])
        result = validate_dataframe(df)
        assert result.valid.iloc[0]["WERKS"] == "HN10"
        # Blank WERKS becomes None (= wildcard "all stores").
        assert pd.isna(result.valid.iloc[1]["WERKS"])

    def test_clr_uppercased_and_blank_to_none(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001,
             "FOCUS_TYPE": "W_CAP", "CLR": "blk"},
        ])
        result = validate_dataframe(df)
        assert result.valid.iloc[0]["CLR"] == "BLK"

    def test_is_active_truthiness(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M",  "GEN_ART_NUMBER": 1, "FOCUS_TYPE": "W_CAP", "IS_ACTIVE": "1"},
            {"MAJ_CAT": "M",  "GEN_ART_NUMBER": 2, "FOCUS_TYPE": "W_CAP", "IS_ACTIVE": "true"},
            {"MAJ_CAT": "M",  "GEN_ART_NUMBER": 3, "FOCUS_TYPE": "W_CAP", "IS_ACTIVE": "0"},
            {"MAJ_CAT": "M",  "GEN_ART_NUMBER": 4, "FOCUS_TYPE": "W_CAP", "IS_ACTIVE": "no"},
        ])
        result = validate_dataframe(df)
        assert list(result.valid["IS_ACTIVE"]) == [1, 1, 0, 0]

    def test_extra_columns_silently_dropped(self):
        # Operators sometimes paste an extra column ("planner_notes" etc.)
        # We don't fail the row — we just drop the extra.
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001,
             "FOCUS_TYPE": "W_CAP", "planner_notes": "fast-mover"},
        ])
        result = validate_dataframe(df)
        assert result.summary["valid"] == 1
        assert "planner_notes" not in result.valid.columns

    def test_normalised_output_shape(self):
        df = pd.DataFrame([
            {"MAJ_CAT": "M_TEES_HS", "GEN_ART_NUMBER": 1001, "FOCUS_TYPE": "W_CAP"},
        ])
        result = validate_dataframe(df)
        # bulk_upsert downstream expects exactly these columns in order.
        assert list(result.valid.columns) == [
            "WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "CLR",
            "FOCUS_TYPE", "TIER", "IS_ACTIVE", "NOTE",
        ]


# ─── Coercion helpers ───────────────────────────────────────────────

class TestCoercionHelpers:
    @pytest.mark.parametrize("v,expected", [
        (1, 1), (10, 10), ("42", 42), (3.0, 3),
        (0, None), (-1, None), ("abc", None),
        (None, None), (float("nan"), None),
    ])
    def test_coerce_positive_int(self, v, expected):
        assert _coerce_positive_int(v) == expected

    @pytest.mark.parametrize("v,expected", [
        (True, True), (False, False),
        (1, True), (0, False),
        ("1", True), ("0", False),
        ("true", True), ("True", True), ("YES", True), ("y", True), ("t", True),
        ("no", False), ("false", False), ("", False), (None, False),
    ])
    def test_coerce_bool(self, v, expected):
        assert _coerce_bool(v) == expected

    @pytest.mark.parametrize("v,expected", [
        ("HN10", "HN10"), ("  HN10  ", "HN10"), ("", None), ("   ", None),
        (None, None), (123, "123"),
    ])
    def test_strip_or_none(self, v, expected):
        assert _strip_or_none(v) == expected


# ─── Module-level constants ─────────────────────────────────────────

class TestConstants:
    def test_required_cols(self):
        assert set(REQUIRED_COLS) == {"MAJ_CAT", "GEN_ART_NUMBER", "FOCUS_TYPE"}

    def test_valid_focus_types(self):
        # Only two valid values — anything else (HERO/CORE/etc) is metadata
        # that goes in the optional TIER column, not FOCUS_TYPE.
        assert VALID_FOCUS_TYPES == {"W_CAP", "WO_CAP"}
