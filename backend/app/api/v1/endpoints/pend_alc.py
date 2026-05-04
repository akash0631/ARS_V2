"""
pend_alc.py
Endpoints for managing ARS_PEND_ALC — the ARS-sourced pending allocation table.

Routes:
    GET  /pend-alc/summary     — totals by MAJ_CAT
    GET  /pend-alc/sessions    — sessions with open pending qty
    GET  /pend-alc/detail      — row-level data (paginated)
    GET  /pend-alc/do-history  — recent DO deduction events
    POST /pend-alc/do-update   — daily DO entry (JSON list)
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from loguru import logger

from app.database.session import get_data_engine
from app.security.dependencies import get_current_user
from app.models.rbac import User
from app.services.pend_alc_service import apply_do_deductions, ensure_pend_alc_table

router = APIRouter(prefix="/pend-alc", tags=["Pending Allocation"])


def _engine():
    return get_data_engine()


# ---------------------------------------------------------------------------
# GET /pend-alc/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def pend_alc_summary(current_user: User = Depends(get_current_user)):
    """Aggregated PEND_QTY totals — tiles for the overview page."""
    try:
        with _engine().connect() as conn:
            ensure_pend_alc_table(conn)
            row = conn.execute(text("""
                SELECT
                    COUNT(*)                              AS total_rows,
                    SUM(ALLOC_QTY)                        AS total_alloc,
                    SUM(DO_QTY)                           AS total_do,
                    SUM(PEND_QTY)                         AS total_pend,
                    SUM(CASE WHEN IS_CLOSED=1 THEN 1 ELSE 0 END) AS closed_rows,
                    SUM(CASE WHEN IS_CLOSED=0 THEN 1 ELSE 0 END) AS open_rows
                FROM ARS_PEND_ALC WITH (NOLOCK)
            """)).fetchone()

            by_majcat = conn.execute(text("""
                SELECT MAJ_CAT,
                       SUM(ALLOC_QTY) AS alloc_qty,
                       SUM(DO_QTY)    AS do_qty,
                       SUM(PEND_QTY)  AS pend_qty,
                       COUNT(*)       AS rows
                FROM ARS_PEND_ALC WITH (NOLOCK)
                WHERE IS_CLOSED = 0
                GROUP BY MAJ_CAT
                ORDER BY SUM(PEND_QTY) DESC
            """)).fetchall()

        return {
            "success": True,
            "data": {
                "totals": {
                    "total_rows":   int(row[0] or 0),
                    "total_alloc":  float(row[1] or 0),
                    "total_do":     float(row[2] or 0),
                    "total_pend":   float(row[3] or 0),
                    "closed_rows":  int(row[4] or 0),
                    "open_rows":    int(row[5] or 0),
                    "pct_closed":   round(100 * int(row[4] or 0) / max(int(row[0] or 1), 1), 1),
                },
                "by_majcat": [
                    {"maj_cat": r[0], "alloc_qty": float(r[1] or 0),
                     "do_qty": float(r[2] or 0), "pend_qty": float(r[3] or 0),
                     "rows": int(r[4] or 0)}
                    for r in by_majcat
                ],
            },
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# GET /pend-alc/sessions
# ---------------------------------------------------------------------------
@router.get("/sessions")
def pend_alc_sessions(current_user: User = Depends(get_current_user)):
    """Sessions that still have open pending quantities."""
    try:
        with _engine().connect() as conn:
            ensure_pend_alc_table(conn)
            rows = conn.execute(text("""
                SELECT SESSION_ID,
                       MIN(APPROVED_AT)  AS approved_at,
                       SUM(ALLOC_QTY)    AS alloc_qty,
                       SUM(DO_QTY)       AS do_qty,
                       SUM(PEND_QTY)     AS pend_qty,
                       COUNT(*)          AS article_count
                FROM ARS_PEND_ALC WITH (NOLOCK)
                WHERE IS_CLOSED = 0
                GROUP BY SESSION_ID
                ORDER BY MIN(APPROVED_AT) DESC
            """)).fetchall()
        return {
            "success": True,
            "data": [
                {
                    "session_id":    r[0],
                    "approved_at":   r[1].isoformat() if r[1] else None,
                    "alloc_qty":     float(r[2] or 0),
                    "do_qty":        float(r[3] or 0),
                    "pend_qty":      float(r[4] or 0),
                    "article_count": int(r[5] or 0),
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# GET /pend-alc/detail
# ---------------------------------------------------------------------------
@router.get("/detail")
def pend_alc_detail(
    session_id: Optional[str] = Query(None),
    maj_cat:    Optional[str] = Query(None),
    closed:     Optional[bool] = Query(None),
    limit:      int = Query(2000, ge=1, le=10000),
    current_user: User = Depends(get_current_user),
):
    """Row-level ARS_PEND_ALC data."""
    try:
        filters = []
        params: dict = {"lim": limit}
        if session_id:
            filters.append("SESSION_ID = :sid")
            params["sid"] = session_id
        if maj_cat:
            filters.append("MAJ_CAT = :mc")
            params["mc"] = maj_cat
        if closed is not None:
            filters.append("IS_CLOSED = :cl")
            params["cl"] = 1 if closed else 0
        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        with _engine().connect() as conn:
            ensure_pend_alc_table(conn)
            rows = conn.execute(text(f"""
                SELECT TOP (:lim)
                    ID, SESSION_ID, RDC, ARTICLE_NUMBER, MAJ_CAT,
                    ALLOC_QTY, DO_QTY, PEND_QTY,
                    APPROVED_AT, LAST_DO_AT, IS_CLOSED
                FROM ARS_PEND_ALC WITH (NOLOCK)
                {where}
                ORDER BY APPROVED_AT DESC, ID
            """), params).fetchall()

        return {
            "success": True,
            "count":   len(rows),
            "data": [
                {
                    "id":             int(r[0]),
                    "session_id":     r[1],
                    "rdc":            r[2],
                    "article_number": r[3],
                    "maj_cat":        r[4],
                    "alloc_qty":      float(r[5] or 0),
                    "do_qty":         float(r[6] or 0),
                    "pend_qty":       float(r[7] or 0),
                    "approved_at":    r[8].isoformat() if r[8] else None,
                    "last_do_at":     r[9].isoformat() if r[9] else None,
                    "is_closed":      bool(r[10]),
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# GET /pend-alc/do-history
# ---------------------------------------------------------------------------
@router.get("/do-history")
def pend_alc_do_history(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    """Recent DO deduction events — rows where LAST_DO_AT is set."""
    try:
        with _engine().connect() as conn:
            ensure_pend_alc_table(conn)
            rows = conn.execute(text("""
                SELECT TOP (:lim)
                    SESSION_ID, RDC, ARTICLE_NUMBER, MAJ_CAT,
                    ALLOC_QTY, DO_QTY, PEND_QTY, IS_CLOSED, LAST_DO_AT
                FROM ARS_PEND_ALC WITH (NOLOCK)
                WHERE LAST_DO_AT IS NOT NULL
                ORDER BY LAST_DO_AT DESC
            """), {"lim": limit}).fetchall()
        return {
            "success": True,
            "data": [
                {
                    "session_id":     r[0],
                    "rdc":            r[1],
                    "article_number": r[2],
                    "maj_cat":        r[3],
                    "alloc_qty":      float(r[4] or 0),
                    "do_qty":         float(r[5] or 0),
                    "pend_qty":       float(r[6] or 0),
                    "is_closed":      bool(r[7]),
                    "last_do_at":     r[8].isoformat() if r[8] else None,
                }
                for r in rows
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# POST /pend-alc/do-update
# ---------------------------------------------------------------------------
class DoUpdateRow(BaseModel):
    rdc:            str
    article_number: str
    do_qty:         float


class DoUpdateRequest(BaseModel):
    rows: List[DoUpdateRow]


@router.post("/do-update")
def pend_alc_do_update(
    body: DoUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Daily DO entry: mark quantities as Delivery-Order'd in SAP.
    Increments DO_QTY, closes fully-covered rows, and reduces
    HOLD_REM in ARS_NL_TBL_HOLD_TRACKING for the same articles.
    """
    if not body.rows:
        raise HTTPException(400, "No rows provided")
    try:
        rows = [{"rdc": r.rdc, "article_number": r.article_number, "do_qty": r.do_qty}
                for r in body.rows]
        with _engine().connect() as conn:
            updated = apply_do_deductions(conn, rows)
        logger.info(
            f"[pend_alc] do-update by {getattr(current_user, 'username', '?')}: "
            f"{len(rows)} input rows → {updated} ARS_PEND_ALC rows updated"
        )
        return {"success": True, "updated_rows": updated}
    except Exception as e:
        raise HTTPException(500, str(e))
