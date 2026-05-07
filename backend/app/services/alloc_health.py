"""
Allocation-correctness health snapshot.

Captured at the end of /listing/generate (Part 8.7) and queryable via
/api/v1/listing/health-snapshots. Gives ops a one-row "did today's run
break?" signal before they approve dispatch — without it, a structurally
broken run only surfaces a week later when stores complain.

The service is split:

  compute_metrics(alloc_df, working_df) -> Dict
      Pure function. Takes two DataFrames (snapshot of ARS_ALLOC_WORKING
      and ARS_LISTING_WORKING) and returns the metric dict. Testable
      without a DB.

  apply_alert_thresholds(metrics, thresholds) -> Dict
      Layers the boolean ALERT_* flags onto a metrics dict. Pure.

  capture_for_session(conn, session_id, ...) -> Dict
      DB driver. Reads from alloc / working tables, calls compute, calls
      alerts, INSERTs (or REPLACEs) one row in ARS_ALLOC_HEALTH_HISTORY.

  list_recent(conn, limit=20) / get_for_session(conn, session_id)
      Read for the UI.

Default alert thresholds (overridable in app_settings.json -> allocation):
  high_mix_pct          = 30  → MIX% > 30 is structurally suspicious
  low_fill_pct          = 60  → fill rate < 60% means under-stocking
  high_fallback_pct     = 30  → > 30% of dispatch from MAJ_CAT_FALLBACK
                                 is too much best-effort filling
  budget_pressure_pct   = 20  → > 20% of stores hitting MJ_REQ cap below
                                 50% of base need
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


# ─────────────────────────────────────────────────────────────────────
# Defaults — wire to app_settings.json -> allocation if you want them
# operator-tunable from the UI.
# ─────────────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "high_mix_pct":        30.0,
    "low_fill_pct":        60.0,
    "high_fallback_pct":   30.0,
    "budget_pressure_pct": 20.0,
}


# ─────────────────────────────────────────────────────────────────────
# Pure metric computer
# ─────────────────────────────────────────────────────────────────────

def compute_metrics(
    alloc_df: pd.DataFrame,
    working_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Compute the per-run snapshot metrics from in-memory DataFrames.

    `alloc_df` columns expected:
      WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, OPT_TYPE, FINAL_OPT_TYPE,
      SHIP_QTY, HOLD_QTY, ALLOC_TYPE, OPT_REQ, ALLOC_QTY, FNL_Q

    `working_df` columns expected (optional but improves accuracy of
    PCT_RL etc — without it, mix is computed on alloc only):
      WERKS, MAJ_CAT, GEN_ART_NUMBER, OPT_TYPE, MJ_REQ
    """
    metrics: Dict[str, Any] = {
        "TOTAL_OPTS":                None,
        "TOTAL_SHIP_QTY":            0.0,
        "TOTAL_HOLD_QTY":            0.0,
        "STORES_TOUCHED":            0,
        "MAJCATS_TOUCHED":           0,
        "PCT_RL":                    0.0,
        "PCT_TBC":                   0.0,
        "PCT_TBL":                   0.0,
        "PCT_MIX":                   0.0,
        "AVG_FILL_RATE_PCT":         0.0,
        "FALLBACK_FILLS":            0,
        "FALLBACK_QTY":              0.0,
        "FALLBACK_PCT":              0.0,
        "RDC_POOL_CONSUMED_PCT_JSON": "{}",
        "STORES_BUDGET_BROKEN_PCT":  0.0,
    }

    if alloc_df is None or alloc_df.empty:
        return metrics

    a = alloc_df.copy()
    a["SHIP_QTY"] = pd.to_numeric(a.get("SHIP_QTY", 0), errors="coerce").fillna(0)
    if "HOLD_QTY" not in a.columns:
        a["HOLD_QTY"] = 0
    a["HOLD_QTY"] = pd.to_numeric(a["HOLD_QTY"], errors="coerce").fillna(0)

    # Top-line totals
    shipping = a[a["SHIP_QTY"] > 0]
    metrics["TOTAL_SHIP_QTY"]  = float(a["SHIP_QTY"].sum())
    metrics["TOTAL_HOLD_QTY"]  = float(a["HOLD_QTY"].sum())
    metrics["STORES_TOUCHED"]  = int(shipping["WERKS"].nunique()) if "WERKS" in a.columns else 0
    metrics["MAJCATS_TOUCHED"] = int(shipping["MAJ_CAT"].nunique()) if "MAJ_CAT" in a.columns else 0

    # Mix by classification — prefer the working frame because it has
    # one row per OPT, vs alloc which has one row per (OPT, variant, size).
    mix_source = working_df if (working_df is not None and not working_df.empty) else a
    type_col = (
        "OPT_TYPE" if "OPT_TYPE" in mix_source.columns
        else ("FINAL_OPT_TYPE" if "FINAL_OPT_TYPE" in mix_source.columns else None)
    )
    if type_col is not None:
        # Dedup to one row per OPT — alloc_df has many rows per OPT.
        opt_keys = ["WERKS", "MAJ_CAT", "GEN_ART_NUMBER"]
        opt_keys = [k for k in opt_keys if k in mix_source.columns]
        if opt_keys:
            opts = mix_source.drop_duplicates(opt_keys + [type_col])
        else:
            opts = mix_source
        total = len(opts)
        metrics["TOTAL_OPTS"] = int(total)
        if total > 0:
            counts = opts[type_col].astype(str).str.upper().value_counts()
            metrics["PCT_RL"]  = float(round(100 * counts.get("RL", 0)  / total, 2))
            metrics["PCT_TBC"] = float(round(100 * counts.get("TBC", 0) / total, 2))
            metrics["PCT_TBL"] = float(round(100 * counts.get("TBL", 0) / total, 2))
            metrics["PCT_MIX"] = float(round(100 * counts.get("MIX", 0) / total, 2))

    # Fill rate — avg ALLOC_QTY / OPT_REQ across non-MIX OPTs
    if "OPT_REQ" in a.columns and "ALLOC_QTY" in a.columns:
        non_mix = a.copy()
        if "OPT_TYPE" in non_mix.columns:
            non_mix = non_mix[non_mix["OPT_TYPE"].astype(str).str.upper() != "MIX"]
        non_mix["OPT_REQ"]   = pd.to_numeric(non_mix["OPT_REQ"], errors="coerce").fillna(0)
        non_mix["ALLOC_QTY"] = pd.to_numeric(non_mix["ALLOC_QTY"], errors="coerce").fillna(0)
        with_demand = non_mix[non_mix["OPT_REQ"] > 0]
        if not with_demand.empty:
            ratios = (with_demand["ALLOC_QTY"] / with_demand["OPT_REQ"]).clip(0, 2)
            metrics["AVG_FILL_RATE_PCT"] = float(round(100 * ratios.mean(), 2))

    # Fallback usage — rows tagged ALLOC_TYPE='MAJ_CAT_FALLBACK'
    if "ALLOC_TYPE" in a.columns:
        fb = a[a["ALLOC_TYPE"].astype(str).str.upper() == "MAJ_CAT_FALLBACK"]
        metrics["FALLBACK_FILLS"] = int(len(fb))
        metrics["FALLBACK_QTY"]   = float(fb["SHIP_QTY"].sum())
        if metrics["TOTAL_SHIP_QTY"] > 0:
            metrics["FALLBACK_PCT"] = float(round(
                100 * metrics["FALLBACK_QTY"] / metrics["TOTAL_SHIP_QTY"], 2,
            ))

    # Per-RDC pool consumption — needs FNL_Q and POOL_CONSUMED on alloc_df
    if "RDC" in a.columns and "FNL_Q" in a.columns:
        a["FNL_Q"]         = pd.to_numeric(a["FNL_Q"], errors="coerce").fillna(0)
        if "POOL_CONSUMED" in a.columns:
            a["POOL_CONSUMED"] = pd.to_numeric(a["POOL_CONSUMED"], errors="coerce").fillna(0)
        else:
            a["POOL_CONSUMED"] = a["SHIP_QTY"] + a["HOLD_QTY"]
        # Per-pool key, max(FNL_Q) is the original pool size.
        key_cols = [c for c in ["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ"]
                    if c in a.columns]
        if key_cols:
            per_pool = a.groupby(key_cols, as_index=False).agg(
                fnl=("FNL_Q", "max"),
                consumed=("POOL_CONSUMED", "sum"),
            )
            per_rdc = per_pool.groupby("RDC", as_index=False).agg(
                fnl=("fnl", "sum"),
                consumed=("consumed", "sum"),
            )
            per_rdc["pct"] = (per_rdc["consumed"] / per_rdc["fnl"].replace(0, pd.NA) * 100).fillna(0).round(2)
            metrics["RDC_POOL_CONSUMED_PCT_JSON"] = json.dumps({
                str(r["RDC"]): float(r["pct"]) for _, r in per_rdc.iterrows()
            }, sort_keys=True)

    # Stores under budget pressure
    if (working_df is not None and not working_df.empty
            and "MJ_REQ" in working_df.columns and "WERKS" in working_df.columns):
        w = working_df.copy()
        w["MJ_REQ"] = pd.to_numeric(w["MJ_REQ"], errors="coerce").fillna(0)
        # Total ship per store from alloc
        ship_per_store = a.groupby("WERKS", as_index=False)["SHIP_QTY"].sum() \
                         .rename(columns={"SHIP_QTY": "ship"})
        per_store = w.groupby("WERKS", as_index=False)["MJ_REQ"].max().merge(
            ship_per_store, on="WERKS", how="left"
        )
        per_store["ship"] = per_store["ship"].fillna(0)
        per_store["fill_ratio"] = (per_store["ship"] /
                                   per_store["MJ_REQ"].replace(0, pd.NA)).fillna(0)
        active = per_store[per_store["MJ_REQ"] > 0]
        if not active.empty:
            broken = active[active["fill_ratio"] < 0.5]
            metrics["STORES_BUDGET_BROKEN_PCT"] = float(round(
                100 * len(broken) / len(active), 2,
            ))

    return metrics


# ─────────────────────────────────────────────────────────────────────
# Alert flag layer
# ─────────────────────────────────────────────────────────────────────

def apply_alert_thresholds(
    metrics: Dict[str, Any],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Layer ALERT_* boolean flags onto a metrics dict (does not mutate)."""
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    out = dict(metrics)
    out["ALERT_HIGH_MIX"]        = bool(metrics.get("PCT_MIX", 0)        > t["high_mix_pct"])
    out["ALERT_LOW_FILL"]        = bool(0 < metrics.get("AVG_FILL_RATE_PCT", 0) < t["low_fill_pct"])
    out["ALERT_HIGH_FALLBACK"]   = bool(metrics.get("FALLBACK_PCT", 0)   > t["high_fallback_pct"])
    out["ALERT_BUDGET_PRESSURE"] = bool(metrics.get("STORES_BUDGET_BROKEN_PCT", 0) > t["budget_pressure_pct"])
    return out


# ─────────────────────────────────────────────────────────────────────
# DB driver
# ─────────────────────────────────────────────────────────────────────

def capture_for_session(
    conn,
    session_id: str,
    *,
    alloc_table:   str = "ARS_ALLOC_WORKING",
    working_table: str = "ARS_LISTING_WORKING",
    user:          Optional[str] = None,
    thresholds:    Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Read live tables, compute metrics + alerts, upsert one row in
    ARS_ALLOC_HEALTH_HISTORY. Returns the metrics dict for the caller to
    log."""
    from sqlalchemy import text  # lazy

    a_sql = text(f"""
        SELECT WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER,
               ISNULL(CLR,'') AS CLR, VAR_ART, SZ,
               OPT_TYPE, FINAL_OPT_TYPE,
               ISNULL(SHIP_QTY, 0)      AS SHIP_QTY,
               ISNULL(HOLD_QTY, 0)      AS HOLD_QTY,
               ISNULL(ALLOC_QTY, 0)     AS ALLOC_QTY,
               ISNULL(OPT_REQ, 0)       AS OPT_REQ,
               ISNULL(FNL_Q, 0)         AS FNL_Q,
               ISNULL(POOL_CONSUMED, 0) AS POOL_CONSUMED,
               ALLOC_TYPE
        FROM [{alloc_table}] WITH (NOLOCK)
    """)
    w_sql = text(f"""
        SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, OPT_TYPE,
               ISNULL(MJ_REQ, 0) AS MJ_REQ
        FROM [{working_table}] WITH (NOLOCK)
    """)
    a_df = pd.read_sql(a_sql, conn)
    w_df = pd.read_sql(w_sql, conn)

    metrics = compute_metrics(a_df, w_df)
    metrics_with_alerts = apply_alert_thresholds(metrics, thresholds)

    # Upsert (one row per session_id).
    conn.execute(text("""
        IF EXISTS (SELECT 1 FROM ARS_ALLOC_HEALTH_HISTORY WHERE SESSION_ID = :sid)
            DELETE FROM ARS_ALLOC_HEALTH_HISTORY WHERE SESSION_ID = :sid;
    """), {"sid": session_id})

    insert_sql = text("""
        INSERT INTO ARS_ALLOC_HEALTH_HISTORY (
            SESSION_ID,
            TOTAL_OPTS, TOTAL_SHIP_QTY, TOTAL_HOLD_QTY,
            STORES_TOUCHED, MAJCATS_TOUCHED,
            PCT_RL, PCT_TBC, PCT_TBL, PCT_MIX,
            AVG_FILL_RATE_PCT,
            FALLBACK_FILLS, FALLBACK_QTY, FALLBACK_PCT,
            RDC_POOL_CONSUMED_PCT_JSON,
            STORES_BUDGET_BROKEN_PCT,
            ALERT_HIGH_MIX, ALERT_LOW_FILL,
            ALERT_HIGH_FALLBACK, ALERT_BUDGET_PRESSURE,
            CREATED_BY
        ) VALUES (
            :SESSION_ID,
            :TOTAL_OPTS, :TOTAL_SHIP_QTY, :TOTAL_HOLD_QTY,
            :STORES_TOUCHED, :MAJCATS_TOUCHED,
            :PCT_RL, :PCT_TBC, :PCT_TBL, :PCT_MIX,
            :AVG_FILL_RATE_PCT,
            :FALLBACK_FILLS, :FALLBACK_QTY, :FALLBACK_PCT,
            :RDC_POOL_CONSUMED_PCT_JSON,
            :STORES_BUDGET_BROKEN_PCT,
            :ALERT_HIGH_MIX, :ALERT_LOW_FILL,
            :ALERT_HIGH_FALLBACK, :ALERT_BUDGET_PRESSURE,
            :CREATED_BY
        )
    """)
    conn.execute(insert_sql, {
        "SESSION_ID": session_id,
        "CREATED_BY": user,
        **metrics_with_alerts,
    })
    conn.commit()
    return metrics_with_alerts


def list_recent(conn, limit: int = 20):
    """Read for /listing/health-snapshots dashboard."""
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT TOP (:lim) *
        FROM ARS_ALLOC_HEALTH_HISTORY WITH (NOLOCK)
        ORDER BY RUN_AT DESC
    """), {"lim": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def get_for_session(conn, session_id: str):
    from sqlalchemy import text
    row = conn.execute(text("""
        SELECT * FROM ARS_ALLOC_HEALTH_HISTORY WITH (NOLOCK)
        WHERE SESSION_ID = :sid
    """), {"sid": session_id}).mappings().first()
    return dict(row) if row else None
