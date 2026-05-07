"""
Store-specific overrides (Master_ST_SPECIFIC).

The original 29-step spec calls these ST_SPECIFIC=9999 entries:
planner-curated bindings of (WERKS, MAJ_CAT, GEN_ART, CLR) that MUST be
allocated regardless of normal scoring/demand. Used for things like
flagship-store launches, regional exclusives, store-manager pet picks.

Different from Master_FOCUS_LIST:
  - FOCUS_LIST is broader: optional WERKS/CLR wildcards, controls
    inclusion via FOCUS_W_CAP / FOCUS_WO_CAP flags but does not specify
    a target quantity.
  - ST_SPECIFIC is per-store: WERKS is required, entry pins an article
    to a specific store with an OPTIONAL TARGET_QTY. The allocator
    bypasses MJ_REQ cap (like FOCUS_WO_CAP) and prefers this article
    in the dispatch.

This module exposes:

  validate_dataframe(df) -> ValidationResult
      Pure CSV validation.

  bulk_upsert(conn, df, user) -> {"inserted", "updated", "total"}
      MERGE upsert on (WERKS, MAJ_CAT, GEN_ART, COALESCE(CLR,'')).

  apply_overrides(conn, working_table) -> {"opts_overridden", "ship_target_qty"}
      Hook called from /listing/generate after focus_list. Sets
      FOCUS_WO_CAP=1 on the matching ARS_LISTING_WORKING rows and
      records the target quantity in a new ST_SPECIFIC_TARGET column.
      The allocator treats FOCUS_WO_CAP rows as 'must allocate' and
      uses ST_SPECIFIC_TARGET as a floor on SHIP_QTY when present.

  list_entries / delete_entry — read for UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


TABLE = "Master_ST_SPECIFIC"
REQUIRED_COLS = ("WERKS", "MAJ_CAT", "GEN_ART_NUMBER")
OPTIONAL_COLS = ("CLR", "TARGET_QTY", "REASON", "IS_ACTIVE",
                 "EFFECTIVE_FROM", "EFFECTIVE_TO")


# ─────────────────────────────────────────────────────────────────────
# Validation — pure
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    valid:   pd.DataFrame
    errors:  pd.DataFrame
    summary: Dict[str, int]


def validate_dataframe(df: pd.DataFrame) -> ValidationResult:
    """Row-by-row validate of the upload CSV.

    Rules (first-failure-wins per row):
      - REQUIRED_COLS present (else blanket failure)
      - WERKS, MAJ_CAT non-blank
      - GEN_ART_NUMBER coerces to positive integer
      - TARGET_QTY (optional): if present, must coerce to positive integer
      - IS_ACTIVE (optional): truthy values normalised to 1/0
      - EFFECTIVE_FROM / EFFECTIVE_TO (optional): if present, must parse
        as YYYY-MM-DD; FROM <= TO when both set.
    """
    if df is None or df.empty:
        empty = pd.DataFrame()
        return ValidationResult(empty, empty, {"input": 0, "valid": 0, "errors": 0})

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        err = df.copy()
        err["error"] = f"Missing required columns: {missing}"
        return ValidationResult(pd.DataFrame(), err,
                                {"input": len(df), "valid": 0, "errors": len(df)})

    work = df.copy()
    errors: List[str] = []
    for _, row in work.iterrows():
        errors.append(_row_errors(row) or "")
    work["error"] = errors

    err_df = work[work["error"] != ""].copy()
    valid_df = work[work["error"] == ""].copy()
    if not valid_df.empty:
        valid_df = _normalise(valid_df)

    return ValidationResult(
        valid=valid_df.reset_index(drop=True),
        errors=err_df.reset_index(drop=True),
        summary={"input": len(df), "valid": len(valid_df), "errors": len(err_df)},
    )


def _row_errors(row: pd.Series) -> Optional[str]:
    werks = _strip(row.get("WERKS"))
    if not werks:
        return "WERKS is required and cannot be blank"
    maj = _strip(row.get("MAJ_CAT"))
    if not maj:
        return "MAJ_CAT is required and cannot be blank"
    gen = _coerce_pos_int(row.get("GEN_ART_NUMBER"))
    if gen is None:
        return f"GEN_ART_NUMBER must be a positive integer, got {row.get('GEN_ART_NUMBER')!r}"
    if "TARGET_QTY" in row.index and not _is_blank(row.get("TARGET_QTY")):
        if _coerce_pos_int(row.get("TARGET_QTY")) is None:
            return f"TARGET_QTY must be a positive integer when set, got {row.get('TARGET_QTY')!r}"
    # Date sanity if both provided
    fr = _strip(row.get("EFFECTIVE_FROM"))
    to = _strip(row.get("EFFECTIVE_TO"))
    if fr and to:
        try:
            f = pd.to_datetime(fr).date()
            t = pd.to_datetime(to).date()
            if f > t:
                return f"EFFECTIVE_FROM ({fr}) is after EFFECTIVE_TO ({to})"
        except Exception:
            return f"EFFECTIVE_FROM / EFFECTIVE_TO must parse as dates (YYYY-MM-DD)"
    return None


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["WERKS"] = out["WERKS"].apply(lambda v: _strip(v).upper() if _strip(v) else None)
    out["MAJ_CAT"] = out["MAJ_CAT"].apply(_strip)
    out["GEN_ART_NUMBER"] = out["GEN_ART_NUMBER"].apply(_coerce_pos_int).astype("Int64")
    if "CLR" in out.columns:
        out["CLR"] = out["CLR"].apply(lambda v: (_strip(v).upper() if _strip(v) else None))
    else:
        out["CLR"] = None
    if "TARGET_QTY" in out.columns:
        out["TARGET_QTY"] = out["TARGET_QTY"].apply(
            lambda v: _coerce_pos_int(v) if not _is_blank(v) else None
        ).astype("Int64")
    else:
        out["TARGET_QTY"] = pd.array([None] * len(out), dtype="Int64")
    if "REASON" in out.columns:
        out["REASON"] = out["REASON"].apply(lambda v: _strip(v) or None)
    else:
        out["REASON"] = None
    if "IS_ACTIVE" in out.columns:
        out["IS_ACTIVE"] = out["IS_ACTIVE"].apply(_coerce_bool).astype(int)
    else:
        out["IS_ACTIVE"] = 1
    for col in ("EFFECTIVE_FROM", "EFFECTIVE_TO"):
        if col in out.columns:
            out[col] = out[col].apply(lambda v: _strip(v) or None)
        else:
            out[col] = None
    return out[["WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "TARGET_QTY",
                "REASON", "IS_ACTIVE", "EFFECTIVE_FROM", "EFFECTIVE_TO"]]


# ─────────────────────────────────────────────────────────────────────
# Coercion helpers (shared shape with focus_list)
# ─────────────────────────────────────────────────────────────────────

def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _strip(v: Any) -> Optional[str]:
    if _is_blank(v):
        return None
    return str(v).strip()


def _coerce_pos_int(v: Any) -> Optional[int]:
    try:
        if _is_blank(v):
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
    s = _strip(v)
    if s is None:
        return False
    return s.lower() in ("1", "true", "yes", "y", "t")


# ─────────────────────────────────────────────────────────────────────
# DB writers
# ─────────────────────────────────────────────────────────────────────

def bulk_upsert(conn, df: pd.DataFrame, user: Optional[str] = None) -> Dict[str, int]:
    from sqlalchemy import text  # lazy
    if df is None or df.empty:
        return {"inserted": 0, "updated": 0, "total": 0}

    tmp = "#st_specific_stage"
    conn.execute(text(f"IF OBJECT_ID('tempdb..{tmp}') IS NOT NULL DROP TABLE {tmp}"))
    conn.execute(text(f"""
        CREATE TABLE {tmp} (
            WERKS NVARCHAR(50) NOT NULL,
            MAJ_CAT NVARCHAR(200) NOT NULL,
            GEN_ART_NUMBER BIGINT NOT NULL,
            CLR NVARCHAR(200) NULL,
            TARGET_QTY INT NULL,
            REASON NVARCHAR(500) NULL,
            IS_ACTIVE BIT NOT NULL,
            EFFECTIVE_FROM DATE NULL,
            EFFECTIVE_TO DATE NULL
        )
    """))
    rows = df.to_dict("records")
    if rows:
        conn.execute(text(f"""
            INSERT INTO {tmp}
                (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, TARGET_QTY, REASON,
                 IS_ACTIVE, EFFECTIVE_FROM, EFFECTIVE_TO)
            VALUES (:WERKS, :MAJ_CAT, :GEN_ART_NUMBER, :CLR, :TARGET_QTY, :REASON,
                    :IS_ACTIVE, :EFFECTIVE_FROM, :EFFECTIVE_TO)
        """), [{
            "WERKS": r.get("WERKS"),
            "MAJ_CAT": r.get("MAJ_CAT"),
            "GEN_ART_NUMBER": int(r.get("GEN_ART_NUMBER")),
            "CLR": r.get("CLR"),
            "TARGET_QTY": (int(r.get("TARGET_QTY")) if r.get("TARGET_QTY") not in (None, pd.NA) else None),
            "REASON": r.get("REASON"),
            "IS_ACTIVE": int(r.get("IS_ACTIVE", 1)),
            "EFFECTIVE_FROM": r.get("EFFECTIVE_FROM"),
            "EFFECTIVE_TO": r.get("EFFECTIVE_TO"),
        } for r in rows])

    merge_sql = f"""
        MERGE [{TABLE}] WITH (HOLDLOCK) AS T
        USING {tmp} AS S
            ON  T.WERKS = S.WERKS
            AND T.MAJ_CAT = S.MAJ_CAT
            AND T.GEN_ART_NUMBER = S.GEN_ART_NUMBER
            AND COALESCE(T.CLR, N'') = COALESCE(S.CLR, N'')
        WHEN MATCHED THEN UPDATE SET
            T.TARGET_QTY     = S.TARGET_QTY,
            T.REASON         = S.REASON,
            T.IS_ACTIVE      = S.IS_ACTIVE,
            T.EFFECTIVE_FROM = S.EFFECTIVE_FROM,
            T.EFFECTIVE_TO   = S.EFFECTIVE_TO,
            T.UPDATED_AT     = SYSUTCDATETIME(),
            T.UPDATED_BY     = :user
        WHEN NOT MATCHED THEN INSERT
            (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, TARGET_QTY, REASON,
             IS_ACTIVE, EFFECTIVE_FROM, EFFECTIVE_TO, CREATED_BY, UPDATED_BY)
            VALUES (S.WERKS, S.MAJ_CAT, S.GEN_ART_NUMBER, S.CLR, S.TARGET_QTY,
                    S.REASON, S.IS_ACTIVE, S.EFFECTIVE_FROM, S.EFFECTIVE_TO,
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


def apply_overrides(
    conn,
    working_table: str = "ARS_LISTING_WORKING",
) -> Dict[str, int]:
    """Stamp FOCUS_WO_CAP=1 on every matching row in working_table.
    Also writes ST_SPECIFIC_TARGET (added if missing) so the allocator
    can use it as a floor on SHIP_QTY.

    Filters by EFFECTIVE_FROM <= today <= EFFECTIVE_TO when set, and
    IS_ACTIVE=1.
    """
    from sqlalchemy import text  # lazy

    # Ensure ST_SPECIFIC_TARGET column exists on working_table.
    try:
        conn.execute(text(f"""
            IF NOT EXISTS (
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{working_table}' AND COLUMN_NAME = 'ST_SPECIFIC_TARGET'
            )
            ALTER TABLE [{working_table}] ADD ST_SPECIFIC_TARGET INT NULL;
        """))
    except Exception:
        pass

    update_sql = text(f"""
        UPDATE W
        SET FOCUS_WO_CAP = 1,
            ST_SPECIFIC_TARGET = S.TARGET_QTY
        FROM [{working_table}] W
        INNER JOIN [{TABLE}] S WITH (NOLOCK)
            ON  S.IS_ACTIVE = 1
            AND S.WERKS = W.WERKS
            AND S.MAJ_CAT = W.MAJ_CAT
            AND S.GEN_ART_NUMBER = W.GEN_ART_NUMBER
            AND (S.CLR IS NULL OR S.CLR = W.CLR)
            AND (S.EFFECTIVE_FROM IS NULL OR S.EFFECTIVE_FROM <= CAST(GETDATE() AS DATE))
            AND (S.EFFECTIVE_TO   IS NULL OR S.EFFECTIVE_TO   >= CAST(GETDATE() AS DATE))
    """)
    conn.execute(update_sql)
    conn.commit()

    counts = conn.execute(text(f"""
        SELECT
            SUM(CASE WHEN FOCUS_WO_CAP = 1 AND ST_SPECIFIC_TARGET IS NOT NULL THEN 1 ELSE 0 END) AS opts,
            SUM(ISNULL(ST_SPECIFIC_TARGET, 0)) AS qty_target
        FROM [{working_table}]
    """)).fetchone()
    return {
        "opts_overridden":  int(counts[0] or 0),
        "ship_target_qty":  int(counts[1] or 0),
    }


def list_entries(
    conn,
    *,
    werks: Optional[str] = None,
    maj_cat: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    from sqlalchemy import text
    where: List[str] = []
    params: Dict[str, Any] = {"lim": int(limit)}
    if werks is not None:
        where.append("WERKS = :werks")
        params["werks"] = werks
    if maj_cat is not None:
        where.append("MAJ_CAT = :mc")
        params["mc"] = maj_cat
    if is_active is not None:
        where.append("IS_ACTIVE = :ia")
        params["ia"] = 1 if is_active else 0
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(text(f"""
        SELECT TOP (:lim)
            id, WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, TARGET_QTY, REASON,
            IS_ACTIVE, EFFECTIVE_FROM, EFFECTIVE_TO,
            CREATED_AT, CREATED_BY, UPDATED_AT, UPDATED_BY
        FROM [{TABLE}] WITH (NOLOCK)
        {where_sql}
        ORDER BY UPDATED_AT DESC
    """), params).mappings().all()
    return [dict(r) for r in rows]


def delete_entry(conn, entry_id: int) -> bool:
    from sqlalchemy import text
    result = conn.execute(text(f"DELETE FROM [{TABLE}] WHERE id = :i"),
                          {"i": int(entry_id)})
    conn.commit()
    return (result.rowcount or 0) > 0
