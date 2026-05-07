"""
Delivery Order (DO) workbook builder.

Turns a parked or historical ARS allocation into a multi-sheet Excel file
the replenishment + logistics teams can hand directly to SAP / lorry
planning. This is the literal output the system is supposed to produce —
without it, even a perfect allocation is unusable.

The builder is split in two so it stays testable:

  build_delivery_order_workbook(alloc_df, run_meta)
      Pure function. Takes a pandas DataFrame of allocated rows
      (columns described below) plus a metadata dict; returns xlsx bytes.

  load_alloc_for_session(session, session_id, source='parked')
      Thin DB reader. Pulls the right rows from ARS_ALLOC_PARKED
      (default) or ARS_ALLOC_HISTORY into the DataFrame shape the
      builder expects.

Required columns on `alloc_df`:
  WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ, SHIP_QTY

Optional columns (used if present, otherwise dropped from output):
  GEN_ART_DESC, VAR_DESC, MRP, PAK_SZ, OPT_TYPE, FINAL_OPT_TYPE,
  HOLD_QTY, ALLOC_STATUS, ALLOC_BATCH_ID

Output sheets:
  1. Run_Meta         — session id, totals, OPT_TYPE breakdown
  2. Dispatch_Detail  — every (WERKS, RDC, ARTICLE, SZ) row with SHIP_QTY > 0
  3. Store_Summary    — per-store totals
  4. RDC_Summary      — per-RDC totals
  5. Article_Summary  — per generic article totals
  6. BDC_Format       — minimal columns ready for SAP BDC paste
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import pandas as pd


# Columns the builder *requires* on the input frame.
REQUIRED_COLS = ("WERKS", "RDC", "MAJ_CAT", "GEN_ART_NUMBER",
                 "CLR", "VAR_ART", "SZ", "SHIP_QTY")

# Columns we'll surface in Dispatch_Detail if present, in this order.
DETAIL_PREFERRED_COLS = (
    "WERKS", "RDC", "MAJ_CAT",
    "GEN_ART_NUMBER", "GEN_ART_DESC", "CLR",
    "VAR_ART", "VAR_DESC", "SZ", "MRP", "PAK_SZ",
    "OPT_TYPE", "FINAL_OPT_TYPE",
    "SHIP_QTY", "HOLD_QTY", "ALLOC_STATUS",
)


# ─────────────────────────────────────────────────────────────────────
# Pure builder — no DB
# ─────────────────────────────────────────────────────────────────────

def build_delivery_order_workbook(
    alloc_df: pd.DataFrame,
    run_meta: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Build the multi-sheet DO workbook and return the raw xlsx bytes.

    Filters to `SHIP_QTY > 0` rows only — HOLD_QTY is reserve buffer, not
    something that ships, so it must NOT appear on the dispatch sheet.
    A separate column on Store/RDC summaries reports HOLD totals so the
    operator can still see the reserve position.

    Raises ValueError if any REQUIRED_COLS are missing.
    """
    missing = [c for c in REQUIRED_COLS if c not in alloc_df.columns]
    if missing:
        raise ValueError(f"alloc_df is missing required columns: {missing}")

    # Defensive copy — we add derived columns and don't want to mutate caller.
    df = alloc_df.copy()
    df["SHIP_QTY"] = pd.to_numeric(df["SHIP_QTY"], errors="coerce").fillna(0)
    if "HOLD_QTY" in df.columns:
        df["HOLD_QTY"] = pd.to_numeric(df["HOLD_QTY"], errors="coerce").fillna(0)
    else:
        df["HOLD_QTY"] = 0.0

    shipping = df[df["SHIP_QTY"] > 0].copy()

    meta = dict(run_meta or {})
    meta.setdefault("generated_at", datetime.utcnow().isoformat(timespec="seconds") + "Z")
    meta.setdefault("rows_input",   int(len(df)))
    meta.setdefault("rows_shipping", int(len(shipping)))
    meta["ship_qty_total"] = float(shipping["SHIP_QTY"].sum())
    meta["hold_qty_total"] = float(df["HOLD_QTY"].sum())
    meta["stores_count"]   = int(shipping["WERKS"].nunique())
    meta["rdcs_count"]     = int(shipping["RDC"].nunique())
    meta["majcats_count"]  = int(shipping["MAJ_CAT"].nunique())
    meta["articles_count"] = int(shipping["GEN_ART_NUMBER"].nunique())

    # Pre-compute the auxiliary summaries while we still have all rows.
    detail        = _build_detail(shipping)
    store_summary = _build_store_summary(df)        # uses HOLD too
    rdc_summary   = _build_rdc_summary(df)
    article_sum   = _build_article_summary(shipping)
    bdc_format    = _build_bdc_format(shipping)
    optype_break  = _build_optype_breakdown(shipping)
    meta["opt_type_breakdown"] = optype_break.to_dict("records")

    # ── Write workbook ────────────────────────────────────────────
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _write_meta_sheet(writer, meta)
        detail.to_excel(writer, sheet_name="Dispatch_Detail", index=False)
        store_summary.to_excel(writer, sheet_name="Store_Summary", index=False)
        rdc_summary.to_excel(writer, sheet_name="RDC_Summary", index=False)
        article_sum.to_excel(writer, sheet_name="Article_Summary", index=False)
        bdc_format.to_excel(writer, sheet_name="BDC_Format", index=False)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────
# Sheet builders
# ─────────────────────────────────────────────────────────────────────

def _build_detail(shipping: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in DETAIL_PREFERRED_COLS if c in shipping.columns]
    out = shipping[cols].copy() if cols else shipping.copy()
    sort_cols = [c for c in ("RDC", "WERKS", "MAJ_CAT", "GEN_ART_NUMBER",
                              "CLR", "SZ") if c in out.columns]
    return out.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)


def _build_store_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["WERKS", "RDC"], as_index=False, sort=True).agg(
        ship_qty=("SHIP_QTY", "sum"),
        hold_qty=("HOLD_QTY", "sum"),
        articles=("GEN_ART_NUMBER", "nunique"),
        variants=("VAR_ART", "nunique"),
        lines=("VAR_ART", "size"),
    )
    g = g[g["ship_qty"] + g["hold_qty"] > 0]
    return g.sort_values(["RDC", "WERKS"], kind="mergesort").reset_index(drop=True)


def _build_rdc_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["RDC"], as_index=False, sort=True).agg(
        ship_qty=("SHIP_QTY", "sum"),
        hold_qty=("HOLD_QTY", "sum"),
        stores=("WERKS", "nunique"),
        articles=("GEN_ART_NUMBER", "nunique"),
        variants=("VAR_ART", "nunique"),
        lines=("VAR_ART", "size"),
    )
    return g.sort_values("RDC", kind="mergesort").reset_index(drop=True)


def _build_article_summary(shipping: pd.DataFrame) -> pd.DataFrame:
    keys = ["RDC", "MAJ_CAT", "GEN_ART_NUMBER"]
    if "GEN_ART_DESC" in shipping.columns:
        # Take any one description per article (mode-of-1).
        desc = (
            shipping.groupby(keys, as_index=False)["GEN_ART_DESC"]
                    .agg(lambda s: next((v for v in s if pd.notna(v) and v != ""), ""))
        )
    else:
        desc = pd.DataFrame(columns=keys + ["GEN_ART_DESC"])
    g = shipping.groupby(keys, as_index=False).agg(
        ship_qty=("SHIP_QTY", "sum"),
        stores=("WERKS", "nunique"),
        sizes=("SZ", "nunique"),
        lines=("VAR_ART", "size"),
    )
    if not desc.empty:
        g = g.merge(desc, on=keys, how="left")
    return g.sort_values(["RDC", "MAJ_CAT", "ship_qty"],
                         ascending=[True, True, False],
                         kind="mergesort").reset_index(drop=True)


def _build_bdc_format(shipping: pd.DataFrame) -> pd.DataFrame:
    """Minimal columns SAP BDC needs to upload a Stock Transfer Order."""
    cols = ["RDC", "WERKS", "VAR_ART", "SZ", "SHIP_QTY"]
    out = shipping[cols].copy()
    out["SHIP_QTY"] = out["SHIP_QTY"].round(0).astype("Int64")
    out = out.rename(columns={"VAR_ART": "ARTICLE_NUMBER", "SHIP_QTY": "QUANTITY"})
    return out.sort_values(["RDC", "WERKS", "ARTICLE_NUMBER", "SZ"],
                           kind="mergesort").reset_index(drop=True)


def _build_optype_breakdown(shipping: pd.DataFrame) -> pd.DataFrame:
    col = ("FINAL_OPT_TYPE" if "FINAL_OPT_TYPE" in shipping.columns
           else "OPT_TYPE" if "OPT_TYPE" in shipping.columns
           else None)
    if col is None:
        return pd.DataFrame(columns=["opt_type", "ship_qty", "lines"])
    g = shipping.groupby(col, as_index=False, sort=True).agg(
        ship_qty=("SHIP_QTY", "sum"),
        lines=("VAR_ART", "size"),
    ).rename(columns={col: "opt_type"})
    return g


def _write_meta_sheet(writer, meta: Dict[str, Any]) -> None:
    """Two-column key/value sheet — easier to read than a one-row table."""
    optype_break = meta.pop("opt_type_breakdown", [])
    rows = [{"key": k, "value": v} for k, v in meta.items()]
    pd.DataFrame(rows).to_excel(writer, sheet_name="Run_Meta", index=False)
    if optype_break:
        startrow = len(rows) + 3
        pd.DataFrame([{"opt_type": "OPT_TYPE breakdown", "ship_qty": "", "lines": ""}]) \
            .to_excel(writer, sheet_name="Run_Meta", index=False,
                      startrow=startrow - 1)
        pd.DataFrame(optype_break).to_excel(
            writer, sheet_name="Run_Meta", index=False, startrow=startrow,
        )


# ─────────────────────────────────────────────────────────────────────
# DB reader — thin wrapper, kept out of the pure builder so tests don't
# need a connection.
# ─────────────────────────────────────────────────────────────────────

def load_alloc_for_session(
    conn,
    session_id: str,
    source: str = "parked",
) -> pd.DataFrame:
    """
    Load a parked or historical allocation into the DataFrame shape the
    builder expects. `source` is 'parked' (default → ARS_ALLOC_PARKED)
    or 'history' (→ ARS_ALLOC_HISTORY).

    The exact columns selected mirror DETAIL_PREFERRED_COLS plus the
    REQUIRED_COLS — anything else lives at the row grain anyway.
    """
    from sqlalchemy import text  # local import keeps module import cheap

    table = {"parked": "ARS_ALLOC_PARKED", "history": "ARS_ALLOC_HISTORY"}.get(source)
    if table is None:
        raise ValueError(f"source must be 'parked' or 'history', got {source!r}")

    sql = text(f"""
        SELECT
            WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, GEN_ART_DESC,
            CLR, VAR_ART, VAR_DESC, SZ, MRP, PAK_SZ,
            OPT_TYPE, FINAL_OPT_TYPE,
            ISNULL(SHIP_QTY, 0) AS SHIP_QTY,
            ISNULL(HOLD_QTY, 0) AS HOLD_QTY,
            ALLOC_STATUS, ALLOC_BATCH_ID
        FROM [{table}] WITH (NOLOCK)
        WHERE ALLOC_SESSION_ID = :sid
    """)
    return pd.read_sql(sql, conn, params={"sid": session_id})
