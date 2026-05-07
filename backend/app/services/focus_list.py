"""
Focus / Hero list ingest + apply.

Master_FOCUS_LIST is a planner-curated set of articles that must be
included in allocation regardless of demand signal. Two flavours:

  W_CAP   — force-include, BUT respect MJ_REQ budget for the store.
  WO_CAP  — force-include, AND uncap MJ_REQ for the (store, MAJ_CAT).

The allocator already reads `FOCUS_W_CAP` / `FOCUS_WO_CAP` columns from
ARS_LISTING_WORKING (see listing_allocator.py:172, _create_store_budget,
_mark_initial_eligibility). Until this module shipped there was no way
to populate them — both flags defaulted to 0 and planners had no
mechanism to assert "always allocate this article."

Module structure:

  validate_dataframe(df)
      Pure validation. Returns (valid_df, errors_df) so the upload
      endpoint can surface a row-by-row error report without aborting
      the whole upload.

  bulk_upsert(conn, df, user)
      DB writer. MERGE on (COALESCE(WERKS,''), MAJ_CAT, GEN_ART_NUMBER,
      COALESCE(CLR,'')) so re-uploads update in place.

  apply_focus_flags(conn, working_table)
      Run during listing generation, AFTER ARS_LISTING_WORKING is built
      and BEFORE allocation runs. Sets FOCUS_W_CAP / FOCUS_WO_CAP on
      every matching row using a per-store > all-stores precedence rule.

  list_entries(conn, **filters)
      Read for the UI review page.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# `text` is imported lazily inside each DB function so unit tests for the
# pure validation logic do not need sqlalchemy installed.

VALID_FOCUS_TYPES = {"W_CAP", "WO_CAP"}
TABLE = "Master_FOCUS_LIST"

# Columns the upload CSV must carry. WERKS and CLR are optional (NULL = wildcard).
REQUIRED_COLS = ("MAJ_CAT", "GEN_ART_NUMBER", "FOCUS_TYPE")
OPTIONAL_COLS = ("WERKS", "CLR", "TIER", "NOTE", "IS_ACTIVE")


# ─────────────────────────────────────────────────────────────────────
# Validation — pure, testable without a DB
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    valid:   pd.DataFrame   # ready for bulk_upsert
    errors:  pd.DataFrame   # original rows with an extra `error` column
    summary: Dict[str, int]


def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """
    Validate a focus-list upload row-by-row.

    Rules (in order, first failure wins per row):
      - All REQUIRED_COLS present (else: blanket failure, valid=empty)
      - MAJ_CAT not blank
      - GEN_ART_NUMBER coerces to a positive integer
      - FOCUS_TYPE in VALID_FOCUS_TYPES (case-insensitive, normalised to upper)
      - WERKS optional; if present, stripped + uppercased; blank → None
      - CLR optional; if present, stripped + uppercased; blank → None
      - IS_ACTIVE optional; truthy values ('1','true','yes','y') → 1, else 0

    Returns valid rows ready to merge, plus a parallel errors frame
    with the offending input + a human-readable `error` message.
    """
    if df is None or df.empty:
        empty = pd.DataFrame()
        return ValidationResult(valid=empty, errors=empty,
                                summary={"input": 0, "valid": 0, "errors": 0})

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        err = df.copy()
        err["error"] = f"Missing required columns: {missing}"
        return ValidationResult(
            valid=pd.DataFrame(),
            errors=err,
            summary={"input": len(df), "valid": 0, "errors": len(df)},
        )

    work = df.copy()
    # Coerce per-column. Capture the first error per row.
    errors: List[str] = []
    for idx, row in work.iterrows():
        e = _row_errors(row)
        errors.append(e or "")
    work["error"] = errors

    err_df = work[work["error"] != ""].copy()
    valid_df = work[work["error"] == ""].copy()
    if not valid_df.empty:
        # _normalise_valid restricts to the 8 canonical columns, so the
        # `error` column is dropped implicitly.
        valid_df = _normalise_valid(valid_df)

    return ValidationResult(
        valid=valid_df.reset_index(drop=True),
        errors=err_df.reset_index(drop=True),
        summary={
            "input":  len(df),
            "valid":  len(valid_df),
            "errors": len(err_df),
        },
    )


def _row_errors(row: pd.Series) -> Optional[str]:
    """First failing rule for one row, or None if it passes all."""
    maj_cat = _strip_or_none(row.get("MAJ_CAT"))
    if not maj_cat:
        return "MAJ_CAT is required and cannot be blank"

    gen_art = _coerce_positive_int(row.get("GEN_ART_NUMBER"))
    if gen_art is None:
        return f"GEN_ART_NUMBER must be a positive integer, got {row.get('GEN_ART_NUMBER')!r}"

    raw_ft = _strip_or_none(row.get("FOCUS_TYPE"))
    if not raw_ft or raw_ft.upper() not in VALID_FOCUS_TYPES:
        return (f"FOCUS_TYPE must be one of {sorted(VALID_FOCUS_TYPES)}, "
                f"got {row.get('FOCUS_TYPE')!r}")

    return None


def _normalise_valid(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MAJ_CAT"] = out["MAJ_CAT"].apply(lambda v: _strip_or_none(v))
    out["GEN_ART_NUMBER"] = out["GEN_ART_NUMBER"].apply(_coerce_positive_int).astype("Int64")
    out["FOCUS_TYPE"] = out["FOCUS_TYPE"].apply(lambda v: _strip_or_none(v).upper())
    if "WERKS" in out.columns:
        out["WERKS"] = out["WERKS"].apply(lambda v: (_strip_or_none(v) or None))
        out["WERKS"] = out["WERKS"].apply(lambda v: v.upper() if isinstance(v, str) else v)
    else:
        out["WERKS"] = None
    if "CLR" in out.columns:
        out["CLR"] = out["CLR"].apply(lambda v: (_strip_or_none(v) or None))
        out["CLR"] = out["CLR"].apply(lambda v: v.upper() if isinstance(v, str) else v)
    else:
        out["CLR"] = None
    if "TIER" in out.columns:
        out["TIER"] = out["TIER"].apply(lambda v: (_strip_or_none(v) or None))
    else:
        out["TIER"] = None
    if "NOTE" in out.columns:
        out["NOTE"] = out["NOTE"].apply(lambda v: (_strip_or_none(v) or None))
    else:
        out["NOTE"] = None
    if "IS_ACTIVE" in out.columns:
        out["IS_ACTIVE"] = out["IS_ACTIVE"].apply(_coerce_bool).astype(int)
    else:
        out["IS_ACTIVE"] = 1
    return out[["WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "CLR",
                "FOCUS_TYPE", "TIER", "IS_ACTIVE", "NOTE"]]


def _strip_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip()
    return s if s else None


def _coerce_positive_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        n = int(float(v))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not pd.isna(v):
        return bool(int(v))
    s = _strip_or_none(v)
    if s is None:
        return False
    return s.lower() in ("1", "true", "yes", "y", "t")


# ─────────────────────────────────────────────────────────────────────
# DB writer — bulk MERGE upsert
# ─────────────────────────────────────────────────────────────────────

def bulk_upsert(conn, df: pd.DataFrame, user: Optional[str] = None) -> Dict[str, int]:
    """
    MERGE the given (already-validated) frame into Master_FOCUS_LIST.

    Match key: (COALESCE(WERKS,''), MAJ_CAT, GEN_ART_NUMBER, COALESCE(CLR,'')).
    Re-uploads update FOCUS_TYPE / TIER / IS_ACTIVE / NOTE in place.

    Returns {"inserted": n, "updated": n, "total": n}.
    """
    from sqlalchemy import text  # lazy
    if df is None or df.empty:
        return {"inserted": 0, "updated": 0, "total": 0}

    # Stage in a temp table — MERGE handles insert vs update atomically.
    tmp = "#focus_list_stage"
    conn.execute(text(f"IF OBJECT_ID('tempdb..{tmp}') IS NOT NULL DROP TABLE {tmp}"))
    conn.execute(text(f"""
        CREATE TABLE {tmp} (
            WERKS NVARCHAR(50) NULL,
            MAJ_CAT NVARCHAR(200) NOT NULL,
            GEN_ART_NUMBER BIGINT NOT NULL,
            CLR NVARCHAR(200) NULL,
            FOCUS_TYPE NVARCHAR(20) NOT NULL,
            TIER NVARCHAR(50) NULL,
            IS_ACTIVE BIT NOT NULL,
            NOTE NVARCHAR(500) NULL
        )
    """))
    rows = df.to_dict("records")
    if rows:
        conn.execute(text(f"""
            INSERT INTO {tmp}
                (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, FOCUS_TYPE, TIER, IS_ACTIVE, NOTE)
            VALUES
                (:WERKS, :MAJ_CAT, :GEN_ART_NUMBER, :CLR,
                 :FOCUS_TYPE, :TIER, :IS_ACTIVE, :NOTE)
        """), [{
            "WERKS": r.get("WERKS"),
            "MAJ_CAT": r.get("MAJ_CAT"),
            "GEN_ART_NUMBER": int(r.get("GEN_ART_NUMBER")) if r.get("GEN_ART_NUMBER") is not None else None,
            "CLR": r.get("CLR"),
            "FOCUS_TYPE": r.get("FOCUS_TYPE"),
            "TIER": r.get("TIER"),
            "IS_ACTIVE": int(r.get("IS_ACTIVE", 1)),
            "NOTE": r.get("NOTE"),
        } for r in rows])

    merge_sql = f"""
        MERGE [{TABLE}] WITH (HOLDLOCK) AS T
        USING {tmp} AS S
            ON  COALESCE(T.WERKS, N'') = COALESCE(S.WERKS, N'')
            AND T.MAJ_CAT = S.MAJ_CAT
            AND T.GEN_ART_NUMBER = S.GEN_ART_NUMBER
            AND COALESCE(T.CLR, N'') = COALESCE(S.CLR, N'')
        WHEN MATCHED THEN UPDATE SET
            T.FOCUS_TYPE = S.FOCUS_TYPE,
            T.TIER       = S.TIER,
            T.IS_ACTIVE  = S.IS_ACTIVE,
            T.NOTE       = S.NOTE,
            T.UPDATED_AT = SYSUTCDATETIME(),
            T.UPDATED_BY = :user
        WHEN NOT MATCHED THEN INSERT
            (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR,
             FOCUS_TYPE, TIER, IS_ACTIVE, NOTE,
             CREATED_BY, UPDATED_BY)
            VALUES (S.WERKS, S.MAJ_CAT, S.GEN_ART_NUMBER, S.CLR,
                    S.FOCUS_TYPE, S.TIER, S.IS_ACTIVE, S.NOTE,
                    :user, :user)
        OUTPUT $action AS act;
    """
    result = conn.execute(text(merge_sql), {"user": user or "system"})
    actions = [r[0] for r in result]
    conn.commit()

    return {
        "inserted": sum(1 for a in actions if a == "INSERT"),
        "updated":  sum(1 for a in actions if a == "UPDATE"),
        "total":    len(actions),
    }


# ─────────────────────────────────────────────────────────────────────
# Allocation hook — call from listing.py before allocation runs
# ─────────────────────────────────────────────────────────────────────

def apply_focus_flags(conn, working_table: str = "ARS_LISTING_WORKING") -> Dict[str, int]:
    """
    Set FOCUS_W_CAP / FOCUS_WO_CAP on every matching row in working_table.

    Precedence (most-specific wins):
      1. (WERKS, MAJ_CAT, GEN_ART, CLR)        — store + color exact
      2. (WERKS, MAJ_CAT, GEN_ART, CLR=NULL)   — store + all colors
      3. (WERKS=NULL, MAJ_CAT, GEN_ART, CLR)   — all stores + color exact
      4. (WERKS=NULL, MAJ_CAT, GEN_ART, CLR=NULL)  — all stores + all colors

    Inactive rows (IS_ACTIVE=0) are ignored. Returns counts per flag for
    the operator log.
    """
    from sqlalchemy import text  # lazy
    # Reset flags first so a focus list shrinkage actually reduces forced
    # articles in the next run; leaving stale 1s in place would silently
    # keep yesterday's focus list active.
    conn.execute(text(f"""
        UPDATE [{working_table}]
        SET FOCUS_W_CAP = 0, FOCUS_WO_CAP = 0
        WHERE ISNULL(FOCUS_W_CAP, 0) <> 0 OR ISNULL(FOCUS_WO_CAP, 0) <> 0
    """))

    apply_sql = f"""
        ;WITH ranked AS (
            SELECT
                W.WERKS, W.MAJ_CAT, W.GEN_ART_NUMBER, ISNULL(W.CLR,'') AS CLR_KEY,
                F.FOCUS_TYPE,
                ROW_NUMBER() OVER (
                    PARTITION BY W.WERKS, W.MAJ_CAT, W.GEN_ART_NUMBER, ISNULL(W.CLR,'')
                    ORDER BY
                        CASE WHEN F.WERKS IS NOT NULL AND F.CLR IS NOT NULL THEN 1
                             WHEN F.WERKS IS NOT NULL AND F.CLR IS NULL     THEN 2
                             WHEN F.WERKS IS NULL     AND F.CLR IS NOT NULL THEN 3
                             ELSE 4 END,
                        F.UPDATED_AT DESC
                ) AS rk
            FROM [{working_table}] W
            INNER JOIN [{TABLE}] F WITH (NOLOCK)
                ON  F.IS_ACTIVE = 1
                AND F.MAJ_CAT = W.MAJ_CAT
                AND F.GEN_ART_NUMBER = W.GEN_ART_NUMBER
                AND (F.WERKS IS NULL OR F.WERKS = W.WERKS)
                AND (F.CLR   IS NULL OR F.CLR   = W.CLR)
        )
        UPDATE W
            SET FOCUS_W_CAP  = CASE WHEN R.FOCUS_TYPE = 'W_CAP'  THEN 1 ELSE ISNULL(W.FOCUS_W_CAP,  0) END,
                FOCUS_WO_CAP = CASE WHEN R.FOCUS_TYPE = 'WO_CAP' THEN 1 ELSE ISNULL(W.FOCUS_WO_CAP, 0) END
        FROM [{working_table}] W
        INNER JOIN ranked R
            ON  W.WERKS = R.WERKS
            AND W.MAJ_CAT = R.MAJ_CAT
            AND W.GEN_ART_NUMBER = R.GEN_ART_NUMBER
            AND ISNULL(W.CLR,'') = R.CLR_KEY
        WHERE R.rk = 1;
    """
    conn.execute(text(apply_sql))
    conn.commit()

    counts = conn.execute(text(f"""
        SELECT
            SUM(CASE WHEN FOCUS_W_CAP  = 1 THEN 1 ELSE 0 END) AS w_cap,
            SUM(CASE WHEN FOCUS_WO_CAP = 1 THEN 1 ELSE 0 END) AS wo_cap
        FROM [{working_table}]
    """)).fetchone()
    return {"w_cap": int(counts[0] or 0), "wo_cap": int(counts[1] or 0)}


# ─────────────────────────────────────────────────────────────────────
# Read for UI
# ─────────────────────────────────────────────────────────────────────

def list_entries(
    conn,
    *,
    werks: Optional[str] = None,
    maj_cat: Optional[str] = None,
    focus_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    from sqlalchemy import text  # lazy
    where: List[str] = []
    params: Dict[str, Any] = {"lim": int(limit)}
    if werks is not None:
        where.append("(WERKS IS NULL OR WERKS = :werks)")
        params["werks"] = werks
    if maj_cat is not None:
        where.append("MAJ_CAT = :mc")
        params["mc"] = maj_cat
    if focus_type is not None:
        where.append("FOCUS_TYPE = :ft")
        params["ft"] = focus_type
    if is_active is not None:
        where.append("IS_ACTIVE = :ia")
        params["ia"] = 1 if is_active else 0

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(text(f"""
        SELECT TOP (:lim)
            id, WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR,
            FOCUS_TYPE, TIER, IS_ACTIVE, NOTE,
            CREATED_AT, CREATED_BY, UPDATED_AT, UPDATED_BY
        FROM [{TABLE}] WITH (NOLOCK)
        {where_sql}
        ORDER BY UPDATED_AT DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]


def delete_entry(conn, entry_id: int) -> bool:
    from sqlalchemy import text  # lazy
    result = conn.execute(text(f"DELETE FROM [{TABLE}] WHERE id = :i"),
                          {"i": int(entry_id)})
    conn.commit()
    return (result.rowcount or 0) > 0
