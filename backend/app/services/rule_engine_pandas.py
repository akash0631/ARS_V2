"""
rule_engine_pandas.py

In-memory pandas/numpy port of Stage C (the allocation waterfall).
Same Stage A + Stage B as the other engines (they run once in SQL); the hot
loop — RL → TBC → TBL × rounds × ranks × bands — runs entirely in pandas
on per-MAJ_CAT slices, then results are bulk-written back to the DB at the
end. A single MAJ_CAT that took 23 minutes in python_parallel finishes in
seconds because every "UPDATE" becomes a numpy vector op.

Concurrency: thread-fanned by MAJ_CAT against the same DB queue table
(ARS_ALLOC_MAJCAT_QUEUE) used by python_parallel / sql_parallel, so the UI
progress endpoint and retry endpoint work unchanged. Each worker takes a
disjoint MAJ_CAT slice — no shared mutable DataFrame state, no locks on
the hot path.

Correctness: the pandas waterfall mirrors rule_engine_new._stage_c_run_band
and _revalidate_after_band statement-by-statement. Stable mergesort
reproduces SQL ROW_NUMBER() tie-breaking on (OPT_PRIORITY_RANK, ST_RANK).
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from app.database.session import get_data_engine
from app.services import alloc_cancellation as ac
from app.services import rule_engine_new as rne
from app.services.alloc_queue import (
    claim_next,
    get_done_summary,
    get_progress,
    make_batch_id,
    mark_done,
    mark_failed,
    mark_in_progress,
    seed_queue,
)
from app.utils.db_helpers import run_sql, retry_on_deadlock


# Default 4 (was 8). Pandas operations are CPU-bound and hold Python's GIL,
# so spawning 8 ThreadPoolExecutor workers in a single uvicorn process
# saturates the GIL — /auth/login, /listing/active-job and any other
# unrelated endpoint sharing this process get starved and the upstream
# proxy hits its 120s read-timeout window before the response makes it
# back. With 4 workers the process retains CPU headroom for foreground
# requests. Override with the ARS_PARALLEL_WORKERS env var if you're
# running uvicorn with --workers N (each uvicorn worker is a separate
# process => own GIL => safe to fan out wider per process).
DEFAULT_WORKERS = int(os.getenv("ARS_PARALLEL_WORKERS", "4"))
MIN_WORKERS = 2
MAX_WORKERS = 8   # was 16; capped lower for the same GIL-saturation reason

# Below this many MAJ_CATs we don't bother spawning a process pool — the
# subprocess startup cost (~1–2s per child on Windows spawn) dwarfs the
# work itself. Tiny inputs run inline on a single thread.
PROCESS_POOL_MIN_MAJCATS = 3

OPT_TYPE_ORDER = ["RL", "TBC", "TBL"]
POOL_KEYS = ["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ"]
OPT_KEYS  = ["WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "CLR"]


# ---------------------------------------------------------------------------
# Per-MAJ_CAT worker — top-level so ProcessPoolExecutor can pickle it
# ---------------------------------------------------------------------------
def _pandas_run_one_majcat(args: Tuple[Any, ...]) -> Dict[str, Any]:
    """
    One MAJ_CAT, one process. Runs the in-memory waterfall, writes results
    back, marks the queue row DONE. Returns a small dict the parent uses
    for progress logging.

    Pickleable contract: every argument and the return value must be
    picklable so the pool can ship them across the process boundary.
    DataFrames are picklable; the slices we pass are typically a few MB.
    """
    (mc, a_slice, w_slice, grids, batch_id, alloc_table, working_table,
     pri_ct_check_rl, pri_ct_check_tbc) = args

    t_mc = time.time()
    worker_id = os.getpid()  # surfaced in QUEUE_TABLE.WORKER_ID for diagnostics

    # Stamp the row IN_PROGRESS so /listing/alloc-progress reflects active
    # workers in real time. Best-effort — if this fails the run still works,
    # just won't show in the live counter.
    try:
        eng = get_data_engine()
        with eng.connect() as upd:
            mark_in_progress(upd, batch_id, mc, worker_id)
    except Exception:
        pass

    try:
        # Empty slice — mark done and bail.
        if a_slice is None or a_slice.empty:
            try:
                eng = get_data_engine()
                with eng.connect() as upd:
                    mark_done(upd, batch_id, mc, 0.0, 0.0, 0, time.time() - t_mc)
            except Exception:
                pass
            return {"mc": mc, "ship": 0.0, "hold": 0.0, "rows": 0,
                    "dur": time.time() - t_mc, "wb_secs": 0.0}

        a_in = a_slice.copy()
        w_in = w_slice.copy() if w_slice is not None else pd.DataFrame()

        a_out, w_out = _run_majcat_waterfall(
            a_in, w_in, grids,
            pri_ct_check_rl=pri_ct_check_rl,
            pri_ct_check_tbc=pri_ct_check_tbc,
        )
        ship_mc = float(a_out['SHIP_QTY'].fillna(0).sum())
        hold_mc = float(a_out['HOLD_QTY'].fillna(0).sum())
        rows_mc = int(len(a_out))

        # Live write-back for THIS MAJ_CAT — disjoint slices, safe to run
        # concurrently across processes (different rows in alloc/working).
        # Wrapped in retry_on_deadlock: even with ROWLOCK/UPDLOCK hints,
        # 8 concurrent workers can occasionally race on shared pages, so
        # we let SQL Server pick a victim and rerun cleanly (each call
        # opens its own raw_connection() so a retry gets a fresh tx).
        eng = get_data_engine()
        t_wb = time.time()
        retry_on_deadlock(
            lambda: _write_back_alloc(eng, alloc_table, a_out),
            label=f"write_back_alloc[{mc}]",
        )
        if not w_out.empty:
            retry_on_deadlock(
                lambda: _write_back_working(eng, working_table, w_out, grids),
                label=f"write_back_working[{mc}]",
            )
        wb_secs = time.time() - t_wb

        dur = time.time() - t_mc
        with eng.connect() as upd:
            mark_done(upd, batch_id, mc, ship_mc, hold_mc, rows_mc, dur)

        return {"mc": mc, "ship": ship_mc, "hold": hold_mc, "rows": rows_mc,
                "dur": dur, "wb_secs": wb_secs}

    except Exception as e:
        err = str(e)[:2000]
        dur = time.time() - t_mc
        try:
            eng = get_data_engine()
            with eng.connect() as upd:
                mark_failed(upd, batch_id, mc, err, dur)
        except Exception:
            pass
        return {"mc": mc, "error": err, "dur": dur}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def run_listing_and_allocation_pandas(
    working_table:  str = "ARS_LISTING_WORKING",
    listed_table:   str = "ARS_LISTED_OPT",
    alloc_table:    str = "ARS_ALLOC_WORKING",
    msa_var_table:  str = "ARS_MSA_VAR_ART",
    var_grid_table: str = "ARS_GRID_MJ_VAR_ART",
    cont_table:     str = "Master_CONT_SZ",
    n_workers:      int = DEFAULT_WORKERS,
    batch_id:       Optional[str] = None,
    only_majcats:   Optional[List[str]] = None,
    size_threshold: float = 0.6,
    min_size_count: int = 3,
    tbl_trivial_factor: float = 0.5,
    pri_ct_check_rl:  bool = True,
    pri_ct_check_tbc: bool = True,
) -> Dict:
    """
    Drop-in replacement for rule_engine_new.run_listing_and_allocation,
    with Stage C ported to pandas + thread-fanned by MAJ_CAT.
    """
    t0 = time.time()
    n_workers = max(MIN_WORKERS, min(MAX_WORKERS, int(n_workers or DEFAULT_WORKERS)))
    batch_id = batch_id or make_batch_id()
    engine = get_data_engine()

    result: Dict = {
        "batch_id":       batch_id,
        "listed_opts":    0,
        "alloc_rows":     0,
        "ship_qty_total": 0.0,
        "hold_qty_total": 0.0,
        "errors":         [],
        "duration_sec":   0.0,
    }

    # ── Stage A + Stage B (SQL, single thread; skipped on retry) ──
    if only_majcats is None:
        with engine.connect() as conn:
            if not rne._exists(conn, working_table) or not rne._exists(conn, msa_var_table):
                logger.warning(
                    f"[C-pd] missing {working_table} or {msa_var_table} — skipping"
                )
                result["duration_sec"] = round(time.time() - t0, 1)
                return result

            rne._stage_a_add_columns(conn, working_table)
            rne._stage_a_apply_rules(
                conn, working_table, size_threshold, min_size_count,
                tbl_trivial_factor,
                pri_ct_check_rl=pri_ct_check_rl,
                pri_ct_check_tbc=pri_ct_check_tbc,
            )
            rne._stage_a_assign_tier(conn, working_table)
            rne._stage_a_assign_rank(conn, working_table)
            listed_count = rne._stage_a_materialize_listed(
                conn, working_table, listed_table
            )
            logger.info(f"[A] listed={listed_count}")
            result["listed_opts"] = listed_count
            if listed_count == 0:
                result["duration_sec"] = round(time.time() - t0, 1)
                return result

            base_rows = rne._stage_b_explode(
                conn, listed_table, alloc_table, msa_var_table
            )
            logger.info(f"[B] alloc rows = {base_rows}")
            if base_rows == 0:
                result["duration_sec"] = round(time.time() - t0, 1)
                return result
            rne._stage_b_fill_cont(conn, alloc_table, cont_table)
            rne._stage_b_fill_targets(conn, alloc_table, var_grid_table)
            rne._stage_b_indexes(conn, alloc_table)

            grids = rne._discover_primary_grids(conn)
            logger.info(f"[C-pd] primary grids = {list(grids.keys())}")
            if rne.ENABLE_PER_OPT_REVALIDATION:
                rne._init_rem_columns(conn, working_table, grids)

            total = seed_queue(conn, batch_id, alloc_table,
                               "pandas", only_majcats=None)
    else:
        with engine.connect() as conn:
            grids = rne._discover_primary_grids(conn)
            total = seed_queue(conn, batch_id, alloc_table,
                               "pandas", only_majcats=only_majcats)

    if total == 0:
        logger.warning(f"[C-pd] queue empty for batch_id={batch_id} — nothing to do")
        result["duration_sec"] = round(time.time() - t0, 1)
        return result

    logger.info(
        f"[C-pd] batch_id={batch_id} total_majcats={total} workers={n_workers}"
    )

    # ── Load tables once into pandas ──
    t_load = time.time()
    alloc_df, working_df, working_cols = _load_tables(
        engine, alloc_table, working_table, grids, only_majcats
    )
    logger.info(
        f"[C-pd] loaded alloc={len(alloc_df)} working={len(working_df)} "
        f"cols={len(working_cols)} in {time.time()-t_load:.1f}s"
    )

    # Per-MAJ_CAT slices — disjoint, so workers can take them by reference.
    alloc_groups   = {mc: g for mc, g in alloc_df.groupby('MAJ_CAT', sort=False)}
    working_groups = {mc: g for mc, g in working_df.groupby('MAJ_CAT', sort=False)}

    # ── Stage C — process-fanned by MAJ_CAT ──
    # Each MAJ_CAT runs in its own subprocess (ProcessPoolExecutor). The
    # in-memory waterfall is pandas/numpy → almost entirely GIL-bound, so
    # threads serialise (8 threads = 1 effective worker). Subprocesses each
    # have their own GIL → real parallelism. Each worker writes its own
    # MAJ_CAT slice back the moment the waterfall finishes, so the dashboard
    # ticks up live as MAJ_CATs complete.
    wb_total_secs = 0.0

    pool_args = [
        (
            mc,
            alloc_groups[mc],
            working_groups.get(mc, pd.DataFrame()),
            grids,
            batch_id,
            alloc_table,
            working_table,
            bool(pri_ct_check_rl),
            bool(pri_ct_check_tbc),
        )
        for mc in alloc_groups
    ]

    use_pool = (len(pool_args) >= PROCESS_POOL_MIN_MAJCATS and n_workers > 1)

    if use_pool:
        logger.info(
            f"[C-pd] dispatching {len(pool_args)} MAJ_CATs to "
            f"ProcessPoolExecutor(max_workers={n_workers})"
        )
        # max_workers can't exceed the # of tasks meaningfully — clamp it.
        actual_workers = min(n_workers, len(pool_args))
        with ProcessPoolExecutor(max_workers=actual_workers) as ex:
            futures = {ex.submit(_pandas_run_one_majcat, args): args[0]
                       for args in pool_args}
            for f in as_completed(futures):
                mc = futures[f]
                try:
                    r = f.result()
                except Exception as e:
                    err = str(e)[:2000]
                    logger.error(f"[C-pd-pool] MAJ_CAT={mc} subprocess raised: {err}")
                    result["errors"].append({"maj_cat": mc, "error": err})
                    continue

                if r.get("error"):
                    result["errors"].append({"maj_cat": mc, "error": r["error"]})
                    logger.error(
                        f"[C-pd-pool] MAJ_CAT={mc} FAILED in {r.get('dur', 0):.1f}s: "
                        f"{r['error']}"
                    )
                else:
                    wb_total_secs += float(r.get("wb_secs", 0.0))
                    # Cheap progress query — one row from the queue table.
                    try:
                        with engine.connect() as conn:
                            prog = get_progress(conn, batch_id)
                        prog_str = f"{prog['done']}/{prog['total']} ({prog['pct']}%)"
                    except Exception:
                        prog_str = "?"
                    logger.info(
                        f"[C-pd-pool] {prog_str} — MAJ_CAT={mc} "
                        f"ship={r.get('ship', 0):.0f} hold={r.get('hold', 0):.0f} "
                        f"rows={r.get('rows', 0)} in {r.get('dur', 0):.1f}s "
                        f"(wb={r.get('wb_secs', 0):.1f}s)"
                    )
    else:
        # Inline fallback: tiny inputs (or n_workers=1) skip subprocess overhead.
        logger.info(
            f"[C-pd] inline run for {len(pool_args)} MAJ_CAT(s) "
            f"(below process-pool threshold or single worker)"
        )
        for args in pool_args:
            mc = args[0]
            r = _pandas_run_one_majcat(args)
            if r.get("error"):
                result["errors"].append({"maj_cat": mc, "error": r["error"]})
            else:
                wb_total_secs += float(r.get("wb_secs", 0.0))

    logger.info(
        f"[C-pd] live write-back done — total wb time across workers "
        f"{wb_total_secs:.1f}s"
    )

    # ── Finalise + Stage D (SQL) ──
    with engine.connect() as conn:
        run_sql(conn, f"UPDATE [{alloc_table}] SET ALLOC_QTY = SHIP_QTY")
        run_sql(conn, f"""
            UPDATE [{alloc_table}] SET
                ALLOC_STATUS = CASE
                    WHEN SHIP_QTY + HOLD_QTY > 0
                         AND SHIP_QTY + HOLD_QTY
                             >= CASE WHEN ISNULL(SZ_MBQ_WH,0) * ISNULL(I_ROD,1)
                                          - ISNULL(SZ_STK,0) > 0
                                     THEN ISNULL(SZ_MBQ_WH,0) * ISNULL(I_ROD,1)
                                          - ISNULL(SZ_STK,0)
                                     ELSE 0 END
                         THEN 'ALLOCATED'
                    WHEN SHIP_QTY > 0                 THEN 'PARTIAL'
                    ELSE 'SKIPPED' END,
                SKIP_REASON = CASE
                    WHEN SHIP_QTY = 0 AND HOLD_QTY = 0
                         AND ISNULL(SZ_MBQ_WH,0) * ISNULL(I_ROD,1)
                             - ISNULL(SZ_STK,0) <= 0
                         THEN 'ALREADY_STOCKED'
                    WHEN SHIP_QTY = 0 AND HOLD_QTY = 0 THEN 'NO_POOL_OR_DEMAND'
                    ELSE SKIP_REASON END
        """)
        rne._stage_d_reflect(conn, working_table, alloc_table)

        totals = conn.execute(text(f"""
            SELECT COUNT(*), ISNULL(SUM(SHIP_QTY),0), ISNULL(SUM(HOLD_QTY),0)
            FROM [{alloc_table}]
            WHERE ISNULL(SHIP_QTY,0) > 0 OR ISNULL(HOLD_QTY,0) > 0
        """)).fetchone()
        result["alloc_rows"]     = int(totals[0] or 0)
        result["ship_qty_total"] = float(totals[1] or 0)
        result["hold_qty_total"] = float(totals[2] or 0)

        prog = get_progress(conn, batch_id)
        summary = get_done_summary(conn, batch_id)
        result["done"]   = prog["done"]
        result["failed"] = prog["failed"]
        result["queue_summary"] = summary

    result["duration_sec"] = round(time.time() - t0, 1)
    logger.info(
        f"[C-pd] DONE batch={batch_id} listed={result['listed_opts']} "
        f"alloc_rows={result['alloc_rows']} ship={result['ship_qty_total']:.0f} "
        f"hold={result['hold_qty_total']:.0f} "
        f"done={result.get('done',0)} failed={result.get('failed',0)} "
        f"in {result['duration_sec']}s"
    )
    return result


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_tables(engine, alloc_table, working_table, grids, only_majcats):
    """Read alloc + working tables into DataFrames. Coerce types up-front."""
    where_a = ""
    where_w = "WHERE LISTED_FLAG = 1"
    params: Dict[str, str] = {}
    if only_majcats:
        keys = ", ".join(f":mc_{i}" for i in range(len(only_majcats)))
        where_a = f"WHERE MAJ_CAT IN ({keys})"
        where_w += f" AND MAJ_CAT IN ({keys})"
        for i, mc in enumerate(only_majcats):
            params[f"mc_{i}"] = mc

    with engine.connect() as conn:
        working_cols = _select_working_cols(conn, working_table, grids)
        col_sql = ", ".join(f"[{c}]" for c in working_cols)
        # Deterministic ORDER BY — without this, SQL Server can return rows in
        # any order (especially under parallel scan), which makes mergesort's
        # tie-break in _run_band non-deterministic and gives slightly different
        # alloc/hold totals from run to run on the same input.
        alloc_order = (
            "ORDER BY [MAJ_CAT], [RDC], [GEN_ART_NUMBER], "
            "ISNULL([CLR],''), [VAR_ART], [SZ], "
            "[OPT_PRIORITY_RANK], ISNULL([ST_RANK], 999999), [WERKS]"
        )
        working_order = (
            "ORDER BY [MAJ_CAT], [WERKS], [GEN_ART_NUMBER], ISNULL([CLR],'')"
        )
        alloc_df = pd.read_sql(
            text(f"SELECT * FROM [{alloc_table}] {where_a} {alloc_order}"),
            conn, params=params,
        )
        working_df = pd.read_sql(
            text(f"SELECT {col_sql} FROM [{working_table}] {where_w} {working_order}"),
            conn, params=params,
        )

    # ── alloc_df type coercion ──
    num_cols = [
        "OPT_PRIORITY_RANK", "ST_RANK", "IS_NEW", "I_ROD",
        "SZ_MBQ", "SZ_MBQ_WH", "SZ_STK", "FNL_Q",
        "POOL_CONSUMED", "SHIP_QTY", "HOLD_QTY",
        "ROUND_SHIP", "ROUND_HOLD", "ALLOC_ROUND", "ALLOC_QTY",
    ]
    for c in num_cols:
        if c in alloc_df.columns:
            alloc_df[c] = pd.to_numeric(alloc_df[c], errors='coerce').fillna(0).astype('float64')
    for c in ['POOL_CONSUMED', 'SHIP_QTY', 'HOLD_QTY', 'ROUND_SHIP', 'ROUND_HOLD']:
        if c not in alloc_df.columns:
            alloc_df[c] = 0.0
    if 'ALLOC_STATUS' not in alloc_df.columns:
        alloc_df['ALLOC_STATUS'] = 'PENDING'
    else:
        alloc_df['ALLOC_STATUS'] = alloc_df['ALLOC_STATUS'].fillna('PENDING').astype(str)
    if 'SKIP_REASON' not in alloc_df.columns:
        alloc_df['SKIP_REASON'] = ''
    else:
        alloc_df['SKIP_REASON'] = alloc_df['SKIP_REASON'].fillna('').astype(str)
    if 'ALLOC_WAVE' not in alloc_df.columns:
        alloc_df['ALLOC_WAVE'] = ''
    if 'OPT_TYPE' in alloc_df.columns:
        alloc_df['OPT_TYPE'] = alloc_df['OPT_TYPE'].fillna('').astype(str)

    # Pool key strings — pad nulls to '' for stable hashing.
    for c in POOL_KEYS:
        if c in alloc_df.columns:
            alloc_df[c] = alloc_df[c].fillna('').astype(str)

    # ── working_df type coercion ──
    if 'MSA_FNL_Q_REM' in working_df.columns:
        working_df['MSA_FNL_Q_REM'] = pd.to_numeric(
            working_df['MSA_FNL_Q_REM'], errors='coerce'
        ).fillna(0).astype('float64')
    if 'PRI_CT_REM' in working_df.columns:
        working_df['PRI_CT_REM'] = pd.to_numeric(
            working_df['PRI_CT_REM'], errors='coerce'
        ).fillna(0).astype('float64')
    if 'ACS_D' in working_df.columns:
        working_df['ACS_D'] = pd.to_numeric(
            working_df['ACS_D'], errors='coerce'
        ).fillna(0).astype('float64')
    for meta in grids.values():
        for col in (meta['req_rem'], meta['h_rem'], meta['gh_col']):
            if col in working_df.columns:
                working_df[col] = pd.to_numeric(
                    working_df[col], errors='coerce'
                ).fillna(0).astype('float64')
    for c in OPT_KEYS:
        if c in working_df.columns:
            working_df[c] = working_df[c].fillna('').astype(str)
    # Grid extras (RNG_SEG, MACRO_MVGR, FAB, …) are used as dict-key components
    # for REQ_REM decrements. Normalize to string so str/numeric mismatches
    # don't cause silent lookup misses.
    for meta in grids.values():
        for ex in meta.get('extras', []):
            if ex in working_df.columns:
                working_df[ex] = working_df[ex].fillna('').astype(str)
    if 'ALLOC_STATUS' in working_df.columns:
        working_df['ALLOC_STATUS'] = (
            working_df['ALLOC_STATUS'].fillna('PENDING').astype(str)
        )
    else:
        working_df['ALLOC_STATUS'] = 'PENDING'
    if 'ALLOC_REMARKS' in working_df.columns:
        working_df['ALLOC_REMARKS'] = (
            working_df['ALLOC_REMARKS'].fillna('').astype(str)
        )
    else:
        working_df['ALLOC_REMARKS'] = ''
    if 'OPT_TYPE' in working_df.columns:
        working_df['OPT_TYPE'] = working_df['OPT_TYPE'].fillna('').astype(str)

    return alloc_df, working_df, working_cols


def _select_working_cols(conn, working_table, grids) -> List[str]:
    """Return the working_table columns we need to load — base + per-grid."""
    base = [
        'WERKS', 'MAJ_CAT', 'GEN_ART_NUMBER', 'CLR',
        'OPT_TYPE', 'OPT_PRIORITY_RANK', 'LISTED_FLAG',
        'ALLOC_STATUS', 'ALLOC_REMARKS', 'ACS_D',
        'MSA_FNL_Q_REM', 'PRI_CT_REM',
    ]
    existing = {c.upper() for c in rne._cols(conn, working_table)}
    cols = [c for c in base if c.upper() in existing]
    for meta in grids.values():
        for col in (meta['req_rem'], meta['h_rem'], meta['gh_col']):
            if col.upper() in existing and col not in cols:
                cols.append(col)
        for ex in meta.get('extras', []):
            if ex.upper() in existing and ex not in cols:
                cols.append(ex)
    return cols


# ---------------------------------------------------------------------------
# Per-MAJ_CAT waterfall (pandas)
# ---------------------------------------------------------------------------
def _run_majcat_waterfall(
    alloc_df: pd.DataFrame,
    working_df: pd.DataFrame,
    grids: Dict[str, Dict],
    pri_ct_check_rl: bool = True,
    pri_ct_check_tbc: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run RL → TBC → TBL waterfall in pandas for one MAJ_CAT slice.
    `alloc_df` and `working_df` are pre-sliced to one MAJ_CAT and copies —
    safe to mutate in place. Returns the same frames after mutation.
    """
    # Build the per-MAJ_CAT pool dict: max(FNL_Q) per pool key.
    if alloc_df.empty:
        return alloc_df, working_df
    pool_grp = (
        alloc_df.groupby(POOL_KEYS, sort=False, observed=True)['FNL_Q']
        .max()
        .fillna(0)
        .astype('float64')
    )
    pool_dict: Dict[Tuple, float] = pool_grp.to_dict()

    has_working = (working_df is not None) and (not working_df.empty)
    revalidate_enabled = bool(rne.ENABLE_PER_OPT_REVALIDATION) and has_working

    # Pre-extract numpy views for hot fields once per MAJ_CAT.
    for ot in OPT_TYPE_ORDER:
        ot_mask = (alloc_df['OPT_TYPE'] == ot)
        if not ot_mask.any():
            continue
        max_round = int(alloc_df.loc[ot_mask, 'I_ROD'].max() or 0)
        if max_round == 0:
            continue

        for r in range(1, max_round + 1):
            # Reset round deltas across the whole opt_type once per round.
            alloc_df.loc[ot_mask, 'ROUND_SHIP'] = 0.0
            alloc_df.loc[ot_mask, 'ROUND_HOLD'] = 0.0

            elig_mask = ot_mask & (alloc_df['I_ROD'] >= r)
            if not elig_mask.any():
                continue
            ranks = (
                alloc_df.loc[elig_mask, 'OPT_PRIORITY_RANK']
                .dropna().astype(int).unique()
            )
            ranks.sort()
            if ranks.size == 0:
                continue

            for rank in ranks:
                _run_band(alloc_df, pool_dict, ot, int(r), int(rank))
                if revalidate_enabled:
                    _revalidate_after_band(
                        alloc_df, working_df, grids,
                        ot, int(rank),
                        pri_ct_check_rl=pri_ct_check_rl,
                        pri_ct_check_tbc=pri_ct_check_tbc,
                    )

    return alloc_df, working_df


def _run_band(
    alloc_df: pd.DataFrame,
    pool_dict: Dict[Tuple, float],
    ot: str,
    r: int,
    rank: int,
) -> None:
    """One rank-band × one round × one opt_type — pandas equivalent of
    rule_engine_new._stage_c_run_band."""
    # 1) Eligible rows
    mask = (
        (alloc_df['OPT_TYPE'] == ot)
        & (alloc_df['OPT_PRIORITY_RANK'] == rank)
        & (alloc_df['I_ROD'] >= r)
        & (~alloc_df['ALLOC_STATUS'].isin(['SKIPPED', 'INELIGIBLE']))
    )
    if not mask.any():
        return

    # Work on a copy that preserves the original index for write-back.
    sub = alloc_df.loc[mask, [
        *POOL_KEYS, 'WERKS', 'OPT_PRIORITY_RANK', 'ST_RANK', 'IS_NEW',
        'SZ_MBQ', 'SZ_MBQ_WH', 'SZ_STK',
        'POOL_CONSUMED', 'SHIP_QTY',
    ]].copy()

    sz_mbq_wh = sub['SZ_MBQ_WH'].to_numpy()
    sz_mbq    = sub['SZ_MBQ'].to_numpy()
    sz_stk    = sub['SZ_STK'].to_numpy()
    pool_cons = sub['POOL_CONSUMED'].to_numpy()
    ship_qty  = sub['SHIP_QTY'].to_numpy()

    need_pool = np.maximum(r * sz_mbq_wh - sz_stk - pool_cons, 0.0)
    need_ship = np.maximum(r * sz_mbq    - sz_stk - ship_qty,  0.0)
    sub['need_pool'] = need_pool
    sub['need_ship'] = need_ship

    sub = sub[sub['need_pool'] > 0]
    if sub.empty:
        return

    # 2) Pool lookup — vectorized via Series.map on a MultiIndex.
    pool_keys_series = pd.Series(
        list(zip(*[sub[c].to_numpy() for c in POOL_KEYS])),
        index=sub.index,
    )
    fnl_q_rem = pool_keys_series.map(pool_dict).fillna(0).astype('float64')
    sub['FNL_Q_REM'] = fnl_q_rem.to_numpy()
    sub = sub[sub['FNL_Q_REM'] > 0]
    if sub.empty:
        return

    # 3) Stable sort within pool key by (OPT_PRIORITY_RANK, ST_RANK, WERKS).
    #    The SQL equivalent is ROW_NUMBER() OVER (PARTITION BY pool_key
    #    ORDER BY OPT_PRIORITY_RANK, ST_RANK, WERKS). WERKS is the final
    #    tiebreaker — without it, two stores with identical OPT_PRIORITY_RANK
    #    and ST_RANK would race for the pool in whatever order pandas saw
    #    them, which in turn depends on SQL Server's row order. Adding
    #    WERKS makes the allocation reproducible run-to-run on the same data.
    sub['_st_rank_fill'] = sub['ST_RANK'].fillna(999999).astype('float64')
    sub.sort_values(
        POOL_KEYS + ['OPT_PRIORITY_RANK', '_st_rank_fill', 'WERKS'],
        kind='mergesort',
        inplace=True,
    )

    # 4) Cumulative demand within pool key
    sub['cum_demand'] = (
        sub.groupby(POOL_KEYS, sort=False, observed=True)['need_pool'].cumsum()
    )
    cum_prev = (sub['cum_demand'] - sub['need_pool']).to_numpy()
    fnl      = sub['FNL_Q_REM'].to_numpy()
    np_need  = sub['need_pool'].to_numpy()

    # 5) take_pool = max(0, min(need_pool, FNL_Q_REM - cum_prev))
    remaining = np.maximum(fnl - cum_prev, 0.0)
    take_pool = np.minimum(remaining, np_need)
    sub['take_pool'] = take_pool

    sub = sub[sub['take_pool'] > 0]
    if sub.empty:
        return

    # 6) SHIP / HOLD split
    is_new    = (sub['IS_NEW'].to_numpy() == 1)
    take      = sub['take_pool'].to_numpy()
    n_ship    = sub['need_ship'].to_numpy()
    round_ship = np.where(is_new, np.minimum(take, n_ship), take)
    round_hold = np.where(is_new, np.maximum(take - n_ship, 0.0), 0.0)
    sub['ROUND_SHIP_NEW'] = round_ship
    sub['ROUND_HOLD_NEW'] = round_hold

    # 7) Write back to alloc_df by preserved index
    idx = sub.index
    alloc_df.loc[idx, 'POOL_CONSUMED'] = (
        alloc_df.loc[idx, 'POOL_CONSUMED'].to_numpy() + take
    )
    alloc_df.loc[idx, 'ROUND_SHIP'] = round_ship
    alloc_df.loc[idx, 'ROUND_HOLD'] = round_hold
    alloc_df.loc[idx, 'SHIP_QTY']   = (
        alloc_df.loc[idx, 'SHIP_QTY'].to_numpy() + round_ship
    )
    alloc_df.loc[idx, 'HOLD_QTY']   = (
        alloc_df.loc[idx, 'HOLD_QTY'].to_numpy() + round_hold
    )
    alloc_df.loc[idx, 'ALLOC_WAVE']  = f"{ot}_R{r}"
    alloc_df.loc[idx, 'ALLOC_ROUND'] = float(r)

    # ALLOC_STATUS: ALLOCATED iff POOL_CONSUMED ≥ lifetime net target.
    new_pc = alloc_df.loc[idx, 'POOL_CONSUMED'].to_numpy()
    i_rod  = alloc_df.loc[idx, 'I_ROD'].to_numpy()
    smbqwh = alloc_df.loc[idx, 'SZ_MBQ_WH'].to_numpy()
    sstk   = alloc_df.loc[idx, 'SZ_STK'].to_numpy()
    target = np.maximum(i_rod * smbqwh - sstk, 0.0)
    alloc_df.loc[idx, 'ALLOC_STATUS'] = np.where(
        new_pc >= target, 'ALLOCATED', 'PARTIAL'
    )

    # 8) Decrement pool by sum(ROUND_SHIP + ROUND_HOLD) per pool key.
    sub['_taken'] = round_ship + round_hold
    band_take = (
        sub.groupby(POOL_KEYS, sort=False, observed=True)['_taken'].sum()
    )
    for key, taken in band_take.items():
        if taken <= 0:
            continue
        cur = pool_dict.get(key, 0.0)
        new = cur - float(taken)
        pool_dict[key] = new if new > 0 else 0.0


def _revalidate_after_band(
    alloc_df: pd.DataFrame,
    working_df: pd.DataFrame,
    grids: Dict[str, Dict],
    ot: str,
    rank: int,
    pri_ct_check_rl: bool,
    pri_ct_check_tbc: bool,
) -> None:
    """pandas equivalent of rule_engine_new._revalidate_after_band, scoped
    to one MAJ_CAT (alloc_df / working_df are already MAJ_CAT slices).
    Steps mirror the SQL one-for-one."""
    band_mask = (
        (alloc_df['OPT_TYPE'] == ot)
        & (alloc_df['OPT_PRIORITY_RANK'] == rank)
    )
    if not band_mask.any():
        return
    band = alloc_df.loc[band_mask, [
        *OPT_KEYS, 'ROUND_SHIP', 'ROUND_HOLD',
    ]]
    band_take_total = float(band['ROUND_SHIP'].sum() + band['ROUND_HOLD'].sum())
    if band_take_total <= 0:
        return  # early-exit — no _REM values changed

    work_cols = set(working_df.columns)

    # (1) Reduce MSA_FNL_Q_REM per OPT (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR)
    if 'MSA_FNL_Q_REM' in work_cols:
        opt_take = (
            band.groupby(OPT_KEYS, sort=False, observed=True, dropna=False)
                .agg(_t=('ROUND_SHIP', 'sum'), _h=('ROUND_HOLD', 'sum'))
        )
        opt_take['_total'] = opt_take['_t'] + opt_take['_h']
        opt_take = opt_take[opt_take['_total'] > 0]['_total']
        if not opt_take.empty:
            opt_dict = opt_take.to_dict()
            keys = pd.Series(
                list(zip(*[working_df[c].to_numpy() for c in OPT_KEYS])),
                index=working_df.index,
            )
            decrement = keys.map(opt_dict).fillna(0).astype('float64')
            new_msa = (working_df['MSA_FNL_Q_REM'].to_numpy()
                       - decrement.to_numpy())
            working_df['MSA_FNL_Q_REM'] = np.maximum(new_msa, 0.0)

    # (2) Reduce each primary grid's REQ_REM at its grain
    band_ship = alloc_df.loc[band_mask, [*OPT_KEYS, 'ROUND_SHIP']]
    band_ship = band_ship[band_ship['ROUND_SHIP'] > 0]
    for req_col, meta in grids.items():
        req_rem = meta['req_rem']
        extras  = meta.get('extras') or []
        if req_rem not in work_cols:
            continue
        if not all(e in work_cols for e in extras):
            continue
        # Need extras values per alloc row → join through working_df by OPT_KEYS.
        if band_ship.empty:
            continue
        # Bring extras onto band rows by joining on OPT_KEYS (one row per OPT
        # in working_df, so this maps each alloc row to its extras values).
        if extras:
            opt_extras = (
                working_df[OPT_KEYS + extras]
                .drop_duplicates(subset=OPT_KEYS)
            )
            joined = band_ship.merge(opt_extras, on=OPT_KEYS, how='inner')
        else:
            joined = band_ship.copy()

        grid_keys = ['WERKS', 'MAJ_CAT'] + extras
        grid_take = (
            joined.groupby(grid_keys, sort=False, observed=True, dropna=False)
                  ['ROUND_SHIP'].sum()
        )
        grid_take = grid_take[grid_take > 0]
        if grid_take.empty:
            continue
        gt_dict = grid_take.to_dict()
        keys = pd.Series(
            list(zip(*[working_df[c].to_numpy() for c in grid_keys])),
            index=working_df.index,
        )
        decrement = keys.map(gt_dict).fillna(0).astype('float64')
        new_req = (working_df[req_rem].to_numpy() - decrement.to_numpy())
        working_df[req_rem] = np.maximum(new_req, 0.0)

    # (3) Recompute H_<grid>_REM = (REQ_REM > ACS_SKIP_FACTOR*ACS_D) AND (GH=1)
    acs = working_df['ACS_D'].to_numpy() if 'ACS_D' in work_cols else \
          np.zeros(len(working_df), dtype='float64')
    pri_h_cols: List[str] = []
    pri_gh_cols: List[str] = []
    for meta in grids.values():
        req_rem = meta['req_rem']
        gh_col  = meta['gh_col']
        h_rem   = meta['h_rem']
        if not all(c in work_cols for c in (req_rem, gh_col, h_rem)):
            continue
        req = working_df[req_rem].to_numpy()
        gh  = working_df[gh_col].to_numpy()
        new_h = ((req > rne.ACS_SKIP_FACTOR * acs) & (gh == 1)).astype('float64')
        working_df[h_rem] = new_h
        pri_h_cols.append(h_rem)
        pri_gh_cols.append(gh_col)

    # (4) PRI_CT_REM = Σ(H_REM)/Σ(GH) × 100
    if pri_h_cols and pri_gh_cols and 'PRI_CT_REM' in work_cols:
        h_sum  = sum(working_df[c].to_numpy() for c in pri_h_cols)
        gh_sum = sum(working_df[c].to_numpy() for c in pri_gh_cols)
        with np.errstate(divide='ignore', invalid='ignore'):
            pri = np.where(
                gh_sum == 0,
                0.0,
                np.round(h_sum.astype('float64') / gh_sum * 100, 1),
            )
        working_df['PRI_CT_REM'] = pri

    # (5) Skip rules on remaining OPTs (rank > current)
    enforced = {'TBL'}
    if pri_ct_check_rl:  enforced.add('RL')
    if pri_ct_check_tbc: enforced.add('TBC')

    pending_mask = (
        (working_df['LISTED_FLAG'].fillna(0) == 1)
        & (~working_df['ALLOC_STATUS'].isin(['SKIPPED', 'ALLOCATED']))
        & (working_df['OPT_PRIORITY_RANK'] > rank)
    )
    if pending_mask.any():
        msa_dead = (working_df['MSA_FNL_Q_REM'].fillna(0) <= 0)
        pri_dead = (
            (working_df['PRI_CT_REM'].fillna(0) < 100)
            & (working_df['OPT_TYPE'].isin(enforced))
        )
        # MSA_EXHAUSTED branch
        m_msa = pending_mask & msa_dead
        if m_msa.any():
            working_df.loc[m_msa, 'ALLOC_STATUS'] = 'SKIPPED'
            working_df.loc[m_msa, 'ALLOC_REMARKS'] = (
                working_df.loc[m_msa, 'ALLOC_REMARKS'].fillna('') + ' SKIP_MSA_EXHAUSTED;'
            )
        # PRI_BROKEN branch (only on OPTs not already SKIPPED above)
        m_pri = pending_mask & pri_dead & (~msa_dead)
        if m_pri.any():
            working_df.loc[m_pri, 'ALLOC_STATUS'] = 'SKIPPED'
            working_df.loc[m_pri, 'ALLOC_REMARKS'] = (
                working_df.loc[m_pri, 'ALLOC_REMARKS'].fillna('') + ' SKIP_PRI_BROKEN;'
            )

    # (5b) Store-broken: MJ_REQ_REM < factor × ACS_D → skip rest of store/OPT
    if rne.ENABLE_STORE_BROKEN and 'MJ_REQ_REM' in work_cols:
        sb_mask = (
            (working_df['LISTED_FLAG'].fillna(0) == 1)
            & (~working_df['ALLOC_STATUS'].isin(['SKIPPED', 'ALLOCATED']))
            & (working_df['OPT_TYPE'] == ot)
            & (working_df['OPT_PRIORITY_RANK'] > rank)
            & (working_df['MJ_REQ_REM'].fillna(0)
               < rne.ACS_SKIP_FACTOR * working_df['ACS_D'].fillna(0))
        )
        if sb_mask.any():
            working_df.loc[sb_mask, 'ALLOC_STATUS'] = 'SKIPPED'
            working_df.loc[sb_mask, 'ALLOC_REMARKS'] = (
                working_df.loc[sb_mask, 'ALLOC_REMARKS'].fillna('') + ' SKIP_STORE_BROKEN;'
            )

    # (6) Propagate SKIP back to alloc_df: every alloc row whose OPT was
    # just SKIPPED → mark SKIPPED + REVALIDATION_SKIP.
    skipped_opts = working_df.loc[
        working_df['ALLOC_STATUS'] == 'SKIPPED',
        OPT_KEYS,
    ].drop_duplicates()
    if not skipped_opts.empty:
        skipped_keys = set(map(tuple, skipped_opts.to_numpy()))
        keys_alloc = list(zip(*[alloc_df[c].to_numpy() for c in OPT_KEYS]))
        m_in = pd.Series(
            [k in skipped_keys for k in keys_alloc], index=alloc_df.index
        )
        prop_mask = (
            m_in
            & (~alloc_df['ALLOC_STATUS'].isin(['SKIPPED', 'ALLOCATED', 'PARTIAL']))
        )
        if prop_mask.any():
            alloc_df.loc[prop_mask, 'ALLOC_STATUS'] = 'SKIPPED'
            sr = alloc_df.loc[prop_mask, 'SKIP_REASON'].fillna('').astype(str)
            blank = (sr == '')
            alloc_df.loc[prop_mask & blank, 'SKIP_REASON'] = 'REVALIDATION_SKIP'


# ---------------------------------------------------------------------------
# Bulk write-back
# ---------------------------------------------------------------------------
_ALLOC_WRITE_COLS = [
    'WERKS', 'RDC', 'MAJ_CAT', 'GEN_ART_NUMBER', 'CLR', 'VAR_ART', 'SZ',
    'SHIP_QTY', 'HOLD_QTY', 'ALLOC_QTY', 'ALLOC_STATUS', 'SKIP_REASON',
    'POOL_CONSUMED', 'ALLOC_WAVE', 'ALLOC_ROUND',
]


def _write_back_alloc(engine, alloc_table: str, df: pd.DataFrame) -> None:
    """Bulk-MERGE the updated alloc rows back into alloc_table."""
    cols = [c for c in _ALLOC_WRITE_COLS if c in df.columns]
    out = df[cols].copy()
    if 'ALLOC_QTY' not in out.columns and 'SHIP_QTY' in out.columns:
        out['ALLOC_QTY'] = out['SHIP_QTY']
    # Pad pool-key strings so '' joins match in SQL too.
    for c in POOL_KEYS:
        if c in out.columns:
            out[c] = out[c].fillna('').astype(str)
    if out.empty:
        return

    tmp = "#alloc_pd_writeback"
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        # Use fast_executemany on the underlying pyodbc cursor.
        try:
            cur.fast_executemany = True
        except Exception:
            pass

        col_defs = []
        for c in cols:
            if c in {'SHIP_QTY', 'HOLD_QTY', 'ALLOC_QTY', 'POOL_CONSUMED', 'ALLOC_ROUND'}:
                col_defs.append(f"[{c}] FLOAT NULL")
            else:
                col_defs.append(f"[{c}] NVARCHAR(200) NULL")
        cur.execute(f"CREATE TABLE {tmp} ({', '.join(col_defs)})")

        placeholders = ", ".join("?" * len(cols))
        col_list = ", ".join(f"[{c}]" for c in cols)
        rows = [
            tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in row)
            for row in out.itertuples(index=False, name=None)
        ]
        cur.executemany(
            f"INSERT INTO {tmp} ({col_list}) VALUES ({placeholders})",
            rows,
        )

        update_pairs = ", ".join(
            f"T.[{c}] = S.[{c}]"
            for c in cols
            if c not in ('WERKS', 'RDC', 'MAJ_CAT', 'GEN_ART_NUMBER', 'CLR', 'VAR_ART', 'SZ')
        )
        cur.execute(f"""
            UPDATE T SET {update_pairs}
            FROM [{alloc_table}] T WITH (ROWLOCK, UPDLOCK)
            INNER JOIN {tmp} S
              ON T.WERKS = S.WERKS AND T.RDC = S.RDC
             AND T.MAJ_CAT = S.MAJ_CAT
             AND T.GEN_ART_NUMBER = S.GEN_ART_NUMBER
             AND ISNULL(T.CLR,'')   = ISNULL(S.CLR,'')
             AND T.VAR_ART = S.VAR_ART AND T.SZ = S.SZ
        """)
        cur.execute(f"DROP TABLE {tmp}")
        raw.commit()
    finally:
        raw.close()


def _write_back_working(engine, working_table: str, df: pd.DataFrame,
                        grids: Dict[str, Dict]) -> None:
    """Bulk-MERGE the updated working rows back into working_table.
    Writes the _REM family + ALLOC_STATUS/REMARKS only (other columns
    untouched)."""
    write_cols = [
        'WERKS', 'MAJ_CAT', 'GEN_ART_NUMBER', 'CLR',
        'ALLOC_STATUS', 'ALLOC_REMARKS',
        'MSA_FNL_Q_REM', 'PRI_CT_REM',
    ]
    for meta in grids.values():
        for col in (meta['req_rem'], meta['h_rem']):
            if col in df.columns and col not in write_cols:
                write_cols.append(col)

    cols = [c for c in write_cols if c in df.columns]
    out = df[cols].copy()
    for c in OPT_KEYS:
        if c in out.columns:
            out[c] = out[c].fillna('').astype(str)
    if out.empty:
        return

    tmp = "#working_pd_writeback"
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        try:
            cur.fast_executemany = True
        except Exception:
            pass

        col_defs = []
        for c in cols:
            if c in OPT_KEYS or c in ('ALLOC_STATUS', 'ALLOC_REMARKS'):
                col_defs.append(f"[{c}] NVARCHAR(400) NULL")
            else:
                col_defs.append(f"[{c}] FLOAT NULL")
        cur.execute(f"CREATE TABLE {tmp} ({', '.join(col_defs)})")

        placeholders = ", ".join("?" * len(cols))
        col_list = ", ".join(f"[{c}]" for c in cols)
        rows = [
            tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in row)
            for row in out.itertuples(index=False, name=None)
        ]
        cur.executemany(
            f"INSERT INTO {tmp} ({col_list}) VALUES ({placeholders})",
            rows,
        )

        update_pairs = ", ".join(
            f"T.[{c}] = S.[{c}]" for c in cols if c not in OPT_KEYS
        )
        cur.execute(f"""
            UPDATE T SET {update_pairs}
            FROM [{working_table}] T WITH (ROWLOCK, UPDLOCK)
            INNER JOIN {tmp} S
              ON T.WERKS = S.WERKS
             AND T.MAJ_CAT = S.MAJ_CAT
             AND T.GEN_ART_NUMBER = S.GEN_ART_NUMBER
             AND ISNULL(T.CLR,'') = ISNULL(S.CLR,'')
        """)
        cur.execute(f"DROP TABLE {tmp}")
        raw.commit()
    finally:
        raw.close()
