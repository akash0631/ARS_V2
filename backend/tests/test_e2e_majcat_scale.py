"""
End-to-end scale test for M_TEES_HS — realistic V2 Retail cardinality.

Where test_e2e_majcat.py uses 5 stores × 4 articles to spot-check the
pipeline, this test runs the same pure-Python pieces on production-shape
data: 320 stores, 20 generic articles in 3 colours, 4 sizes, with a
realistic ~70% per-store coverage and a believable RL/TBC/TBL/MIX mix.

Why scale matters
-----------------
The unit and small-e2e tests catch logic bugs. They miss:
  - Per-store reconciliation drift across the DO sheets when row counts
    cross 50 K (where pandas groupby ordering / mergesort tie-breaks
    can disagree subtly).
  - Health snapshot percentages going out of [0, 100] range due to
    rounding when classifications have hundreds of OPTs.
  - Fallback per-store cap leaking when many stores compete for shared
    pool (the greedy planner's per-store accounting must not drift).
  - The Run_Meta sheet collapsing on long lists (>20 K dispatch rows).
  - openpyxl write performance — a 5-min DO build is unacceptable.

Determinism
-----------
Seeded with random.seed(42) so the same fixture rebuilds bit-identical
across CI runs. If anyone tweaks the fixture, every assertion needs
review.

Scale of generated data (after seeding):
  - ~320 × 20 × 3 colours × 4 sizes × ~70% coverage = ~50K alloc rows
  - ~60 OPTs at the (article × colour) level
  - Mix: ~60% RL, 20% TBC, 10% TBL, 10% MIX
  - ~10% of RL/TBC OPTs intentionally under-fill (creates fallback work)

This test runs in seconds on a laptop. If it crosses 30 seconds, that's
a regression in the pure-Python performance of one of the modules and
the build perf section below should fire.
"""
import io
import random
import time

import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")

from app.services.alloc_health import (
    apply_alert_thresholds,
    compute_metrics,
)
from app.services.delivery_order import build_delivery_order_workbook
from app.services.majcat_fallback import (
    FALLBACK_TAG,
    plan_fallback_fills,
)


# ─────────────────────────────────────────────────────────────────────
# Scale parameters — realistic V2 Retail cardinality
# ─────────────────────────────────────────────────────────────────────

MAJ            = "M_TEES_HS"
N_STORES       = 320          # actual store count
N_ARTICLES     = 20           # ~20 generic articles in M_TEES_HS for one cycle
COLORS         = ["BLK", "RED", "BLU"]
SIZES          = ["S", "M", "L", "XL"]
COVERAGE_PCT   = 0.70         # ~70% of stores carry each OPT
RDCS           = ["DH24", "DW01"]


def _build_scale_fixture():
    """Generate a realistic single-cycle M_TEES_HS dataset."""
    rng = random.Random(42)   # local Random instance, not global state

    stores = [f"S{i:04d}" for i in range(N_STORES)]
    store_rdc = {s: rng.choice(RDCS) for s in stores}
    articles = list(range(1001, 1001 + N_ARTICLES))

    # Deterministic OPT_TYPE per (article, colour) — mix is 60/20/10/10
    def opt_type_for(art, clr):
        r = (art * 13 + len(clr) * 7 + ord(clr[0])) % 100
        if r < 60:  return "RL"
        if r < 80:  return "TBC"
        if r < 90:  return "TBL"
        return "MIX"

    # MJ_REQ is computed AFTER alloc rows are built — set it ~120% of
    # each store's actual ship total so ~20% of stores have a real gap
    # the fallback can address. Random budget would either always trip
    # the cap or never need fallback; this gives both behaviours.
    mj_req: dict = {}
    rows = []
    var_counter = 0
    for art in articles:
        for clr in COLORS:
            ot = opt_type_for(art, clr)
            # 10% of RL/TBC OPTs have intentional under-fill so fallback
            # has real work to do — pick which stores have the gap.
            under_fill = ot in ("RL", "TBC") and rng.random() < 0.10

            for werks in stores:
                if rng.random() > COVERAGE_PCT:
                    continue   # store doesn't carry this OPT

                rdc = store_rdc[werks]
                # FNL_Q is shared per (RDC, art, clr, sz) — store-agnostic.
                # Just stash the value here; the SUM at the pool grain is
                # what compute_metrics cares about.
                fnl = rng.randint(50, 200)

                for sz in SIZES:
                    var_counter += 1
                    var_art = f"V{var_counter:06d}"

                    # OPT-level demand, deterministic by store
                    opt_req = rng.randint(8, 18)
                    if ot == "MIX":
                        ship = 0
                        hold = rng.randint(0, 4)
                        alloc_status = "PARTIAL"
                    elif ot == "TBL":
                        ship = rng.randint(3, opt_req)
                        # Hold buffer on M only
                        hold = rng.randint(0, 3) if sz == "M" else 0
                        alloc_status = "ALLOCATED" if ship >= opt_req else "PARTIAL"
                    elif under_fill:
                        # Under-fill: ship significantly less than demand
                        ship = max(1, opt_req // 3)
                        hold = 0
                        alloc_status = "PARTIAL"
                    else:
                        # Normal RL/TBC: usually meets demand
                        ship = opt_req if rng.random() > 0.05 else opt_req - 1
                        hold = 0
                        alloc_status = "ALLOCATED"

                    rows.append({
                        "WERKS": werks, "RDC": rdc, "MAJ_CAT": MAJ,
                        "GEN_ART_NUMBER": art,
                        "GEN_ART_DESC":   f"Tee {art}",
                        "CLR": clr,
                        "VAR_ART": var_art,
                        "VAR_DESC": f"Tee {art} {clr} {sz}",
                        "SZ": sz,
                        "MRP": 599.0, "PAK_SZ": 1,
                        "OPT_TYPE": ot,
                        "FINAL_OPT_TYPE": "RL" if ot in ("RL", "TBC") else (
                            "NL" if ot == "TBL" and ship > 0 else ot
                        ),
                        "SHIP_QTY": float(ship),
                        "HOLD_QTY": float(hold),
                        "ALLOC_QTY": float(ship),
                        "OPT_REQ": float(opt_req),
                        "FNL_Q": float(fnl),
                        "POOL_CONSUMED": float(ship + hold),
                        "ALLOC_TYPE": "PRIMARY",
                        "ALLOC_STATUS": alloc_status,
                    })

    alloc_df = pd.DataFrame(rows)

    # Compute MJ_REQ per store: actual_ship × multiplier in [1.05, 1.40].
    # Lower multipliers → no gap, fallback skips. Higher → real gap.
    # The 1.05-1.40 spread guarantees roughly half the stores have a
    # meaningful (>5%) gap.
    actual_ship = alloc_df.groupby("WERKS")["SHIP_QTY"].sum().to_dict()
    for s in stores:
        base = actual_ship.get(s, 0)
        mult = 1.05 + rng.random() * 0.35   # uniform [1.05, 1.40]
        mj_req[s] = int(base * mult) if base > 0 else 100

    # Working frame: one row per (store, article) with MJ_REQ
    working_df = alloc_df.drop_duplicates(
        ["WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "OPT_TYPE"]
    )[["WERKS", "MAJ_CAT", "GEN_ART_NUMBER", "OPT_TYPE"]].copy()
    working_df["MJ_REQ"] = working_df["WERKS"].map(mj_req)

    # Build the unconsumed pool — articles with leftover stock that
    # fallback can tap. Take ~50% of the pool keys, give them surplus.
    pool_keys = (
        alloc_df.drop_duplicates(
            ["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ"]
        )[["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ", "FNL_Q"]]
    )
    pool_keys = pool_keys.sample(frac=0.5, random_state=42).copy()
    # Compute consumed per pool, leftover = max - consumed
    consumed = (
        alloc_df.groupby(
            ["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ"],
            as_index=False,
        )["POOL_CONSUMED"].sum()
    )
    pool_df = pool_keys.merge(
        consumed,
        on=["RDC", "MAJ_CAT", "GEN_ART_NUMBER", "CLR", "VAR_ART", "SZ"],
        how="left",
    )
    pool_df["FNL_Q_REM"] = (pool_df["FNL_Q"] - pool_df["POOL_CONSUMED"]).clip(lower=0)
    pool_df = pool_df[pool_df["FNL_Q_REM"] > 0].copy()

    return alloc_df, working_df, pool_df, store_rdc


# ─────────────────────────────────────────────────────────────────────
# The scale test — single class so setup_class runs the full pipeline
# once and individual tests assert different invariants on the result.
# ─────────────────────────────────────────────────────────────────────

class TestE2EScale:
    """320 stores × 20 articles × 3 colours × 4 sizes — production scale."""

    @classmethod
    def setup_class(cls):
        cls.t_total_start = time.perf_counter()

        # 1. Generate fixture
        t0 = time.perf_counter()
        cls.primary, cls.working, cls.pool, cls.store_rdc = _build_scale_fixture()
        cls.t_fixture = time.perf_counter() - t0

        # 2. Compute gaps and run MAJ_CAT fallback
        t0 = time.perf_counter()
        cls.gaps = _gaps_from_frames(cls.primary, cls.working)
        cls.fills = plan_fallback_fills(
            cls.gaps, cls.pool,
            max_fill_pct=0.5,
            store_rdc_map={s: [r] for s, r in cls.store_rdc.items()},
        )
        cls.t_fallback = time.perf_counter() - t0

        # 3. Append fallback rows to alloc frame
        if cls.fills:
            fb_rows = [{
                "WERKS": f.werks, "RDC": f.rdc, "MAJ_CAT": f.maj_cat,
                "GEN_ART_NUMBER": f.gen_art_number,
                "GEN_ART_DESC": f"Tee {f.gen_art_number}",
                "CLR": f.clr or "", "VAR_ART": f.var_art,
                "VAR_DESC": f"FB {f.var_art}",
                "SZ": f.sz, "MRP": 599.0, "PAK_SZ": 1,
                "OPT_TYPE": "MAJ_CAT_FB", "FINAL_OPT_TYPE": "NL",
                "SHIP_QTY": f.fill_qty, "HOLD_QTY": 0.0,
                "ALLOC_QTY": f.fill_qty, "OPT_REQ": 0.0,
                "FNL_Q": 0.0, "POOL_CONSUMED": f.fill_qty,
                "ALLOC_TYPE": FALLBACK_TAG, "ALLOC_STATUS": "ALLOCATED",
            } for f in cls.fills]
            cls.combined = pd.concat(
                [cls.primary, pd.DataFrame(fb_rows)], ignore_index=True,
            )
        else:
            cls.combined = cls.primary

        # 4. Health snapshot + alerts
        t0 = time.perf_counter()
        cls.metrics = compute_metrics(cls.combined, cls.working)
        cls.alerts = apply_alert_thresholds(cls.metrics)
        cls.t_health = time.perf_counter() - t0

        # 5. Build the Delivery Order workbook
        t0 = time.perf_counter()
        cls.xlsx = build_delivery_order_workbook(
            cls.combined,
            run_meta={
                "session_id": "S2026-05-07-SCALE",
                "source": "test_scale",
                "majcat":  MAJ,
            },
        )
        cls.t_do = time.perf_counter() - t0

        cls.t_total = time.perf_counter() - cls.t_total_start
        # The DO read-back is the slow part — only do it once,
        # cache for assertions.
        cls.sheets = pd.read_excel(io.BytesIO(cls.xlsx), sheet_name=None,
                                    engine="openpyxl")

    # ─── Cardinality + fixture sanity ───────────────────────────────

    def test_fixture_at_production_scale(self):
        # ~50K alloc rows expected (320 × 20 × 3 × 4 × 0.7).
        # Allow ±20% for the 70% sampling variance.
        n = len(self.primary)
        assert 35_000 < n < 75_000, f"alloc rows = {n} (expected ~50K)"

    def test_all_stores_appear(self):
        assert self.primary["WERKS"].nunique() == N_STORES

    def test_all_articles_appear(self):
        assert self.primary["GEN_ART_NUMBER"].nunique() == N_ARTICLES

    def test_all_opt_types_represented(self):
        types = set(self.primary["OPT_TYPE"].unique())
        assert {"RL", "TBC", "TBL", "MIX"}.issubset(types)

    # ─── Fallback at scale ──────────────────────────────────────────

    def test_fallback_produced_meaningful_fills(self):
        # With ~10% of OPTs intentionally under-filled across 320 stores,
        # there should be a non-trivial number of fallback fills.
        assert len(self.fills) > 50, \
            f"only {len(self.fills)} fills — fixture or planner regression"

    def test_fallback_respects_rdc_routing_at_scale(self):
        # Sample-check rather than full O(N) loop — pick 100 random fills.
        sample = random.Random(42).sample(self.fills, min(100, len(self.fills)))
        for f in sample:
            assert f.rdc == self.store_rdc[f.werks], \
                f"{f.werks} got {f.rdc}, expected {self.store_rdc[f.werks]}"

    def test_fallback_per_store_cap_holds_at_scale(self):
        # Per-store fallback ≤ 50% of MJ_REQ — check every store.
        per_store = {}
        for f in self.fills:
            per_store[f.werks] = per_store.get(f.werks, 0) + f.fill_qty
        mj = self.working.groupby("WERKS")["MJ_REQ"].max().to_dict()
        for werks, total in per_store.items():
            assert total <= 0.5 * mj[werks] + 0.5, \
                f"{werks}: fallback {total} > 50% of MJ_REQ {mj[werks]}"

    def test_pool_never_oversubscribed(self):
        # Sum of fallback fills per pool key ≤ original FNL_Q_REM.
        per_pool = {}
        for f in self.fills:
            k = (f.rdc, f.var_art, f.sz)
            per_pool[k] = per_pool.get(k, 0) + f.fill_qty
        pool_lookup = self.pool.set_index(["RDC", "VAR_ART", "SZ"])["FNL_Q_REM"].to_dict()
        for k, taken in per_pool.items():
            avail = pool_lookup.get(k, 0)
            assert taken <= avail + 0.01, f"pool {k} oversubscribed: {taken} > {avail}"

    # ─── Health metrics at scale ────────────────────────────────────

    def test_health_pcts_in_valid_range(self):
        for k in ("PCT_RL", "PCT_TBC", "PCT_TBL", "PCT_MIX",
                   "AVG_FILL_RATE_PCT", "FALLBACK_PCT",
                   "STORES_BUDGET_BROKEN_PCT"):
            v = self.metrics[k]
            assert 0 <= v <= 100, f"{k} = {v} out of [0, 100]"

    def test_total_ship_includes_fallback_at_scale(self):
        primary = float(self.primary["SHIP_QTY"].sum())
        fb = sum(f.fill_qty for f in self.fills)
        assert abs(self.metrics["TOTAL_SHIP_QTY"] - (primary + fb)) < 0.01

    def test_classification_pcts_sum_within_tolerance(self):
        total = (self.metrics["PCT_RL"] + self.metrics["PCT_TBC"]
                 + self.metrics["PCT_TBL"] + self.metrics["PCT_MIX"])
        # Independent rounding × 4 categories = up to ±2 drift
        assert 95 <= total <= 102

    def test_rdc_pool_consumed_present_for_both_rdcs(self):
        import json
        data = json.loads(self.metrics["RDC_POOL_CONSUMED_PCT_JSON"])
        assert "DH24" in data
        assert "DW01" in data

    # ─── DO workbook reconciliation at scale ────────────────────────

    def test_dispatch_total_matches_combined(self):
        detail = self.sheets["Dispatch_Detail"]
        combined_ship = float(
            self.combined[self.combined["SHIP_QTY"] > 0]["SHIP_QTY"].sum()
        )
        assert abs(detail["SHIP_QTY"].sum() - combined_ship) < 0.01

    def test_per_store_reconciliation_holds_for_every_store(self):
        # The big invariant: every single store's ship_qty in
        # Store_Summary must equal its sum in Dispatch_Detail.
        store = self.sheets["Store_Summary"].set_index("WERKS")["ship_qty"]
        detail = self.sheets["Dispatch_Detail"].groupby("WERKS")["SHIP_QTY"].sum()
        # detail's index ⊆ store's index (store_summary may have HOLD-only)
        for werks, qty in detail.items():
            assert abs(store.get(werks, 0) - qty) < 0.01, \
                f"store {werks}: summary={store.get(werks, 0)}, detail={qty}"

    def test_per_rdc_reconciliation(self):
        rdc = self.sheets["RDC_Summary"].set_index("RDC")["ship_qty"]
        detail = self.sheets["Dispatch_Detail"].groupby("RDC")["SHIP_QTY"].sum()
        for r, qty in detail.items():
            assert abs(rdc.get(r, 0) - qty) < 0.01

    def test_no_pure_hold_in_dispatch_detail(self):
        detail = self.sheets["Dispatch_Detail"]
        assert (detail["SHIP_QTY"] > 0).all()

    def test_no_pure_hold_in_bdc(self):
        bdc = self.sheets["BDC_Format"]
        assert (bdc["QUANTITY"] > 0).all()

    def test_bdc_quantity_integer_at_scale(self):
        bdc = self.sheets["BDC_Format"]
        assert bdc["QUANTITY"].dtype.kind in ("i", "u")

    def test_workbook_size_reasonable(self):
        # Sanity: 50K rows in xlsx should land somewhere between 1 MB
        # and 50 MB. If it's tiny, openpyxl probably wrote nothing.
        # If it's huge, something is duplicating rows.
        size_mb = len(self.xlsx) / (1024 * 1024)
        assert 0.5 < size_mb < 60, f"workbook = {size_mb:.1f} MB"

    # ─── Performance budget ─────────────────────────────────────────

    def test_fixture_build_under_5_seconds(self):
        assert self.t_fixture < 5.0, f"fixture build took {self.t_fixture:.1f}s"

    def test_fallback_planner_under_5_seconds(self):
        assert self.t_fallback < 5.0, f"fallback planner took {self.t_fallback:.1f}s"

    def test_health_snapshot_under_3_seconds(self):
        assert self.t_health < 3.0, f"health compute took {self.t_health:.1f}s"

    def test_do_workbook_under_30_seconds(self):
        # openpyxl is the slow path — 50K rows × 6 sheets is ~30s on a
        # modest box. If this regresses past 30s, the DO builder
        # picked up an O(N²) path.
        assert self.t_do < 30.0, f"DO build took {self.t_do:.1f}s"

    def test_full_pipeline_under_60_seconds(self):
        assert self.t_total < 60.0, f"full pipeline took {self.t_total:.1f}s"


# ─────────────────────────────────────────────────────────────────────
# Helper (shared with test_e2e_majcat.py shape)
# ─────────────────────────────────────────────────────────────────────

def _gaps_from_frames(alloc_df, working_df):
    primary_ship = (
        alloc_df.groupby(["WERKS", "MAJ_CAT", "GEN_ART_NUMBER"], as_index=False)
                ["SHIP_QTY"].sum()
    )
    by_werks = primary_ship.groupby(["WERKS", "MAJ_CAT"], as_index=False)["SHIP_QTY"].sum()
    by_werks = by_werks.rename(columns={"SHIP_QTY": "ALREADY_FILLED"})
    mj = working_df.groupby(["WERKS", "MAJ_CAT"], as_index=False)["MJ_REQ"].max()
    out = mj.merge(by_werks, on=["WERKS", "MAJ_CAT"], how="left")
    out["ALREADY_FILLED"] = out["ALREADY_FILLED"].fillna(0)
    out["gap"] = out["MJ_REQ"] - out["ALREADY_FILLED"]
    return out[out["gap"] > 0].copy()
