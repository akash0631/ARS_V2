"""
MAJ_CAT-level fallback fill.

Problem this solves
-------------------
The primary allocation matches articles to attribute-aware slots:
(WERKS, MAJ_CAT, GEN_ART, CLR) → variant×size dispatch. When the MSA
pool does not contain a variant that fits the attribute requirement
(e.g. 'store needs black cotton M from RDC DH24' but no such article
in pool), the slot stays empty and the store ships less than its
MJ_REQ target.

Until now the system had no recourse. The planner's only option was
to manually intervene or accept the under-fill. This module adds an
opt-in fallback: after the primary waterfall completes, look at every
(WERKS, MAJ_CAT) where SUM(SHIP_QTY) < MJ_REQ, then fill the gap from
any unconsumed pool in that MAJ_CAT — even if attribute matching was
imperfect.

Filled rows are tagged `ALLOC_TYPE='MAJ_CAT_FALLBACK'` and counted
separately in the health snapshot so planners can see which dispatches
were "best-effort" rather than attribute-matched.

Pure design
-----------
The hot logic (matching gap to pool, ranking, capping) is split out
as `plan_fallback_fills(gaps_df, pool_df, *, max_fill_pct, store_rdc_map)`
so unit tests can exercise it without a live DB. The DB writers
(`run_fallback_for_session`) just compose: read state, call the planner,
write the result.

Configuration
-------------
Off by default. Enable per run via `enable_majcat_fallback=True` in the
listing.GenerateRequest, or set `default_majcat_fallback=True` in
app_settings.json -> allocation. Cap the fill ratio with
`majcat_fallback_max_pct` (default 0.5 = at most fill the gap to 50%
of MJ_REQ via fallback so a run does not get dominated by best-effort
rows).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# Tag value written to ARS_ALLOC_WORKING.ALLOC_TYPE for fallback rows.
FALLBACK_TAG = "MAJ_CAT_FALLBACK"


# ─────────────────────────────────────────────────────────────────────
# Pure planner — testable without a DB
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FallbackFill:
    werks: str
    rdc: str
    maj_cat: str
    gen_art_number: int
    clr: str
    var_art: str
    sz: str
    fill_qty: float


def plan_fallback_fills(
    gaps_df: pd.DataFrame,
    pool_df: pd.DataFrame,
    *,
    max_fill_pct: float = 0.5,
    store_rdc_map: Optional[Dict[str, Iterable[str]]] = None,
) -> List[FallbackFill]:
    """
    Decide how to fill (WERKS, MAJ_CAT) gaps from unconsumed pool.

    Inputs
    ------
    gaps_df: per (WERKS, MAJ_CAT) row with columns
             WERKS, MAJ_CAT, MJ_REQ, ALREADY_FILLED, gap (= MJ_REQ - ALREADY_FILLED).
             Only rows with gap > 0 should reach this function — the caller
             filters upstream.

    pool_df: per (RDC, MAJ_CAT, GEN_ART, CLR, VAR_ART, SZ) row with columns
             RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ, FNL_Q_REM.
             Only rows with FNL_Q_REM > 0 should reach this function.

    max_fill_pct: cap the fallback fill at this fraction of MJ_REQ. The
                  fallback is best-effort by definition — letting it satisfy
                  100% of MJ_REQ would mean attribute-matched and
                  attribute-blind allocation are indistinguishable in the
                  final output. Default 0.5 (50%).

    store_rdc_map: optional restriction. {WERKS -> set of RDCs the store
                   may receive from}. If None, every store can pull from
                   every RDC (current behaviour pre-Two-DC routing).

    Output
    ------
    Ordered list of FallbackFill rows. Pool is consumed greedily —
    once an RDC×variant×size pool is empty, subsequent stores see less
    of it. Sorted by (WERKS asc, gap desc) so under-served stores get
    priority within the same alphabetical tier.
    """
    if gaps_df is None or gaps_df.empty:
        return []
    if pool_df is None or pool_df.empty:
        return []

    # Normalise + sort gaps by store, then by remaining gap (largest first
    # within a store would be greedy on huge gaps; we sort ascending across
    # stores so first-mover wins).
    g = gaps_df.copy()
    g["MAJ_CAT"] = g["MAJ_CAT"].astype(str)
    g["WERKS"] = g["WERKS"].astype(str)
    g["MJ_REQ"] = pd.to_numeric(g["MJ_REQ"], errors="coerce").fillna(0)
    g["gap"] = pd.to_numeric(g["gap"], errors="coerce").fillna(0)
    g = g[g["gap"] > 0].sort_values(["WERKS", "MAJ_CAT"], kind="mergesort")

    # Pool tracker — mutate FNL_Q_REM as we hand units out.
    p = pool_df.copy()
    p["MAJ_CAT"] = p["MAJ_CAT"].astype(str)
    p["RDC"] = p["RDC"].astype(str)
    p["FNL_Q_REM"] = pd.to_numeric(p["FNL_Q_REM"], errors="coerce").fillna(0)
    p = p[p["FNL_Q_REM"] > 0].copy()

    out: List[FallbackFill] = []

    for _, row in g.iterrows():
        werks  = row["WERKS"]
        maj    = row["MAJ_CAT"]
        gap    = float(row["gap"])
        mj_req = float(row["MJ_REQ"])
        cap_for_store = mj_req * max_fill_pct
        # Don't exceed the cap, and don't exceed the actual gap.
        room = min(gap, cap_for_store)
        if room <= 0:
            continue

        # Filter pool to this MAJ_CAT and the RDCs this store can pull from.
        cand = p[(p["MAJ_CAT"] == maj) & (p["FNL_Q_REM"] > 0)]
        if store_rdc_map is not None:
            allowed = set(store_rdc_map.get(werks, []))
            if not allowed:
                continue
            cand = cand[cand["RDC"].isin(allowed)]
        if cand.empty:
            continue

        # Greedy: largest pools first to minimise slot fragmentation.
        cand = cand.sort_values("FNL_Q_REM", ascending=False, kind="mergesort")

        for idx, prow in cand.iterrows():
            if room <= 0:
                break
            avail = float(prow["FNL_Q_REM"])
            if avail <= 0:
                continue
            take = min(room, avail)
            if take <= 0:
                continue
            out.append(FallbackFill(
                werks=werks,
                rdc=str(prow["RDC"]),
                maj_cat=maj,
                gen_art_number=int(prow["GEN_ART_NUMBER"]),
                clr=str(prow["CLR"]) if prow["CLR"] is not None else "",
                var_art=str(prow["VAR_ART"]),
                sz=str(prow["SZ"]),
                fill_qty=take,
            ))
            # Mutate the pool tracker in place so subsequent iterations see
            # the reduced availability.
            p.at[idx, "FNL_Q_REM"] = avail - take
            room -= take

    return out


# ─────────────────────────────────────────────────────────────────────
# DB driver — composes the planner with the live tables
# ─────────────────────────────────────────────────────────────────────

def run_fallback_for_session(
    conn,
    *,
    alloc_table: str = "ARS_ALLOC_WORKING",
    working_table: str = "ARS_LISTING_WORKING",
    max_fill_pct: float = 0.5,
    min_gap_qty: float = 1.0,
) -> Dict[str, Any]:
    """
    Find unfilled (WERKS, MAJ_CAT) gaps from primary allocation, fill
    them from unconsumed pool, and INSERT the fills back into
    `alloc_table` with `ALLOC_TYPE = 'MAJ_CAT_FALLBACK'`.

    Returns {"fills": n, "qty": total, "stores_helped": n, "majcats_touched": n}.

    Idempotency: re-running on the same alloc_table state will produce
    new fills only if pool / gaps still exist. The function does NOT
    deduplicate on its own — caller (listing.py Part 8.6) must run it
    once per session.
    """
    from sqlalchemy import text  # lazy

    # 1. Compute per (WERKS, MAJ_CAT) gap from primary fills.
    gaps_sql = text(f"""
        SELECT
            W.WERKS, W.MAJ_CAT,
            MAX(ISNULL(W.MJ_REQ, 0))                             AS MJ_REQ,
            ISNULL(SUM(A.SHIP_QTY), 0)                           AS ALREADY_FILLED,
            MAX(ISNULL(W.MJ_REQ, 0)) - ISNULL(SUM(A.SHIP_QTY), 0) AS gap
        FROM [{working_table}] W
        LEFT JOIN [{alloc_table}] A WITH (NOLOCK)
            ON  A.WERKS          = W.WERKS
            AND A.MAJ_CAT        = W.MAJ_CAT
            AND A.GEN_ART_NUMBER = W.GEN_ART_NUMBER
            AND ISNULL(A.CLR,'') = ISNULL(W.CLR,'')
        GROUP BY W.WERKS, W.MAJ_CAT
        HAVING MAX(ISNULL(W.MJ_REQ, 0)) > 0
           AND MAX(ISNULL(W.MJ_REQ, 0)) - ISNULL(SUM(A.SHIP_QTY), 0) >= :min_gap
    """)
    gaps_df = pd.read_sql(gaps_sql, conn, params={"min_gap": float(min_gap_qty)})
    if gaps_df.empty:
        return {"fills": 0, "qty": 0.0, "stores_helped": 0, "majcats_touched": 0}

    # 2. Compute unconsumed pool per (RDC, MAJ_CAT, VAR_ART, SZ).
    pool_sql = text(f"""
        SELECT
            RDC, MAJ_CAT, GEN_ART_NUMBER, ISNULL(CLR,'') AS CLR,
            VAR_ART, SZ,
            MAX(ISNULL(FNL_Q, 0)) - SUM(ISNULL(POOL_CONSUMED, 0)) AS FNL_Q_REM
        FROM [{alloc_table}] WITH (NOLOCK)
        GROUP BY RDC, MAJ_CAT, GEN_ART_NUMBER, ISNULL(CLR,''), VAR_ART, SZ
        HAVING MAX(ISNULL(FNL_Q, 0)) - SUM(ISNULL(POOL_CONSUMED, 0)) > 0
    """)
    pool_df = pd.read_sql(pool_sql, conn)
    if pool_df.empty:
        return {"fills": 0, "qty": 0.0, "stores_helped": 0, "majcats_touched": 0}

    # 3. Plan fills (pure function).
    fills = plan_fallback_fills(
        gaps_df, pool_df, max_fill_pct=max_fill_pct,
    )
    if not fills:
        return {"fills": 0, "qty": 0.0, "stores_helped": 0, "majcats_touched": 0}

    # 4. INSERT each fill back into alloc_table. Use minimal columns —
    # the rest default. ALLOC_TYPE='MAJ_CAT_FALLBACK' is the marker.
    insert_sql = text(f"""
        INSERT INTO [{alloc_table}]
            (WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, CLR,
             VAR_ART, SZ, SHIP_QTY, ALLOC_QTY,
             ALLOC_TYPE, ALLOC_STATUS, OPT_TYPE)
        VALUES
            (:WERKS, :RDC, :MAJ_CAT, :GEN_ART_NUMBER, :CLR,
             :VAR_ART, :SZ, :QTY, :QTY,
             :TAG, 'ALLOCATED', 'MAJ_CAT_FB')
    """)
    rows = [{
        "WERKS": f.werks, "RDC": f.rdc, "MAJ_CAT": f.maj_cat,
        "GEN_ART_NUMBER": f.gen_art_number, "CLR": f.clr or None,
        "VAR_ART": f.var_art, "SZ": f.sz, "QTY": float(f.fill_qty),
        "TAG": FALLBACK_TAG,
    } for f in fills]
    conn.execute(insert_sql, rows)

    # 5. Decrement FNL_Q_REM on the original pool keys so a subsequent
    # call (or the post-allocation pool reconciliation) sees the correct
    # remaining stock. Same MERGE pattern the primary engine uses.
    update_sql = text(f"""
        UPDATE A
        SET POOL_CONSUMED = ISNULL(A.POOL_CONSUMED, 0) + S.delta
        FROM [{alloc_table}] A
        INNER JOIN (
            SELECT
                :RDC AS RDC,
                :MAJ_CAT AS MAJ_CAT,
                :GEN_ART_NUMBER AS GEN_ART_NUMBER,
                :CLR AS CLR,
                :VAR_ART AS VAR_ART,
                :SZ AS SZ,
                :QTY AS delta
        ) S
            ON  A.RDC = S.RDC
            AND A.MAJ_CAT = S.MAJ_CAT
            AND A.GEN_ART_NUMBER = S.GEN_ART_NUMBER
            AND ISNULL(A.CLR,'') = ISNULL(S.CLR,'')
            AND A.VAR_ART = S.VAR_ART
            AND A.SZ = S.SZ
        WHERE A.ALLOC_TYPE != :TAG
    """)
    for f in fills:
        conn.execute(update_sql, {
            "RDC": f.rdc, "MAJ_CAT": f.maj_cat,
            "GEN_ART_NUMBER": f.gen_art_number, "CLR": f.clr or None,
            "VAR_ART": f.var_art, "SZ": f.sz, "QTY": float(f.fill_qty),
            "TAG": FALLBACK_TAG,
        })

    conn.commit()

    total_qty = sum(f.fill_qty for f in fills)
    stores = {f.werks for f in fills}
    cats = {f.maj_cat for f in fills}
    return {
        "fills": len(fills),
        "qty": float(total_qty),
        "stores_helped": len(stores),
        "majcats_touched": len(cats),
    }
