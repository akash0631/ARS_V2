"""
pend_alc_service.py
Manages the ARS_PEND_ALC table — tracks allocation quantities that are approved
but not yet Delivery-Order'd in SAP.

Lifecycle:
    approve_parked      → write_pend_alc      → PENDING rows created (IS_CLOSED=0)
    SAP DO daily upload → apply_do_deductions  → DO_QTY incremented; IS_CLOSED=1 when covered
    MSA run             → _load_ars_pending    → PEND_QTY deducted from available stock

The table grain is (SESSION_ID, RDC, ARTICLE_NUMBER) — one row per approved session
× warehouse × variant article. PEND_QTY is a persisted computed column (ALLOC_QTY - DO_QTY).
"""
from __future__ import annotations

import uuid
from typing import Dict, List

from loguru import logger
from sqlalchemy import text


PEND_ALC_TABLE = "ARS_PEND_ALC"

_DDL = f"""
IF OBJECT_ID('dbo.{PEND_ALC_TABLE}','U') IS NULL
CREATE TABLE dbo.{PEND_ALC_TABLE} (
    ID             BIGINT IDENTITY(1,1),
    SESSION_ID     NVARCHAR(50)  NOT NULL,
    RDC            NVARCHAR(20)  NOT NULL,
    ARTICLE_NUMBER NVARCHAR(30)  NOT NULL,
    MAJ_CAT        NVARCHAR(50)  NULL,
    ALLOC_QTY      FLOAT         NOT NULL DEFAULT 0,
    DO_QTY         FLOAT         NOT NULL DEFAULT 0,
    PEND_QTY       AS (ALLOC_QTY - DO_QTY)  PERSISTED,
    APPROVED_AT    DATETIME      NOT NULL DEFAULT GETDATE(),
    LAST_DO_AT     DATETIME      NULL,
    IS_CLOSED      BIT           NOT NULL DEFAULT 0,
    CONSTRAINT PK_ARS_PEND_ALC PRIMARY KEY (ID)
)
"""

_INDEXES = [
    ("IX_ARS_PEND_ALC_lookup",  f"ON dbo.{PEND_ALC_TABLE} (RDC, ARTICLE_NUMBER, IS_CLOSED)"),
    ("IX_ARS_PEND_ALC_session", f"ON dbo.{PEND_ALC_TABLE} (SESSION_ID)"),
]


def ensure_pend_alc_table(conn) -> None:
    """Idempotent: create ARS_PEND_ALC and its indexes if missing."""
    conn.execute(text(_DDL))
    for idx_name, idx_def in _INDEXES:
        try:
            conn.execute(text(
                f"IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name='{idx_name}') "
                f"CREATE INDEX {idx_name} {idx_def}"
            ))
        except Exception as e:
            logger.warning(f"[pend_alc] index {idx_name}: {e}")
    conn.commit()


def write_pend_alc(conn, session_id: str) -> int:
    """
    Aggregate ALLOC_QTY from ARS_ALLOC_HISTORY for this session and insert
    into ARS_PEND_ALC. One row per (SESSION_ID, WERKS, VAR_ART).
    Idempotent via NOT EXISTS guard — safe to call twice on re-approve.
    Returns count of rows inserted.
    """
    ensure_pend_alc_table(conn)
    res = conn.execute(text(f"""
        INSERT INTO {PEND_ALC_TABLE} (SESSION_ID, RDC, ARTICLE_NUMBER, MAJ_CAT, ALLOC_QTY)
        SELECT :sid,
               H.[WERKS]   AS RDC,
               H.[VAR_ART] AS ARTICLE_NUMBER,
               MAX(H.[MAJ_CAT]),
               SUM(ISNULL(TRY_CAST(H.[ALLOC_QTY] AS FLOAT), 0))
        FROM [ARS_ALLOC_HISTORY] H
        WHERE H.[SESSION_ID] = :sid
          AND ISNULL(TRY_CAST(H.[ALLOC_QTY] AS FLOAT), 0) > 0
          AND NOT EXISTS (
              SELECT 1 FROM {PEND_ALC_TABLE} P
              WHERE P.SESSION_ID = :sid
                AND P.RDC        = H.[WERKS]
                AND P.ARTICLE_NUMBER = H.[VAR_ART]
          )
        GROUP BY H.[WERKS], H.[VAR_ART]
    """), {"sid": session_id})
    conn.commit()
    return int(res.rowcount or 0)


def apply_do_deductions(conn, rows: List[Dict]) -> int:
    """
    For each DO row, increment DO_QTY in ARS_PEND_ALC and decrement
    HOLD_REM in ARS_NL_TBL_HOLD_TRACKING. Closes rows fully covered.

    rows: list of dicts with keys: rdc, article_number, do_qty
    Returns count of ARS_PEND_ALC rows updated.
    """
    valid = [r for r in rows if float(r.get("do_qty", 0) or 0) > 0]
    if not valid:
        return 0

    ensure_pend_alc_table(conn)
    tmp = f"#pa_do_{uuid.uuid4().hex[:8]}"

    conn.execute(text(
        f"CREATE TABLE {tmp} (rdc NVARCHAR(20), art NVARCHAR(30), qty FLOAT)"
    ))
    conn.execute(
        text(f"INSERT INTO {tmp} VALUES (:r, :a, :q)"),
        [{"r": str(r["rdc"]), "a": str(r["article_number"]), "q": float(r["do_qty"])}
         for r in valid]
    )

    res = conn.execute(text(f"""
        UPDATE P
           SET P.DO_QTY     = P.DO_QTY + u.qty,
               P.LAST_DO_AT = GETDATE(),
               P.IS_CLOSED  = CASE WHEN P.DO_QTY + u.qty >= P.ALLOC_QTY THEN 1 ELSE 0 END
        FROM {PEND_ALC_TABLE} P
        JOIN {tmp} u ON P.RDC = u.rdc AND P.ARTICLE_NUMBER = u.art
        WHERE P.IS_CLOSED = 0
    """))

    try:
        conn.execute(text(f"""
            UPDATE H
               SET H.HOLD_REM  = CASE WHEN H.HOLD_REM - u.qty < 0 THEN 0
                                       ELSE H.HOLD_REM - u.qty END,
                   H.IS_CLOSED = CASE WHEN H.HOLD_REM - u.qty <= 0 THEN 1 ELSE 0 END
            FROM ARS_NL_TBL_HOLD_TRACKING H
            JOIN {tmp} u ON H.WERKS = u.rdc AND H.VAR_ART = u.art
            WHERE H.IS_CLOSED = 0
        """))
    except Exception as he:
        logger.warning(f"[pend_alc] hold tracking update skipped: {he}")

    try:
        conn.execute(text(
            f"IF OBJECT_ID('tempdb..{tmp}') IS NOT NULL DROP TABLE {tmp}"
        ))
    except Exception:
        pass

    conn.commit()
    return int(res.rowcount or 0)
