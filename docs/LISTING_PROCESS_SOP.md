# Listing Generation — Standard Operating Procedure (SOP)

**Project:** ARS — Auto Replenishment System
**Module:** `/listing/generate` (POST)
**Owner:** V2 Retail planners
**Last updated:** 2026-04-27

This document is the authoritative end-to-end process spec for the Listing
Generation pipeline. Every parameter the UI sends, every stage the backend runs,
every table touched, every output written.

Use it to:
- Review behavior before changing any parameter or rule.
- Plan changes safely (know exactly what each toggle affects).
- Train new planners on what each control on the UI does.

---

## 0. Quick Reference

| Item | Value |
|---|---|
| Endpoint | `POST /api/v1/listing/generate` |
| Auth | JWT (any logged-in user) |
| Sync/Async | **Async** — returns within ms, work runs in a background thread |
| Tracking | `session_id` (returned) → poll `/listing/sessions/{id}` |
| Stages | A (List) → B (Explode) → C (Allocate) → D (Reflect) |
| Default mode | `python_parallel`, 8 workers |
| Source code | [listing.py](backend/app/api/v1/endpoints/listing.py), [rule_engine_new.py](backend/app/services/rule_engine_new.py) |

---

## 1. Process Flow (high level)

```
┌─────────────────────┐
│  UI: Listing Page   │  user picks RDC/stores/MAJ_CATs, mode,
│  /listing page      │  variables → click "Generate"
└──────────┬──────────┘
           │ POST /listing/generate (sync HTTP < 1 s)
           ▼
┌─────────────────────────────────────────────┐
│  start_session(session_id, user, request)   │  inserts ARS_LISTING_SESSIONS row
│  + attach loguru sink to                    │  + creates per-session log file
│    backend/logs/listing_sessions/<id>.log   │
└──────────────┬──────────────────────────────┘
               │ spawn daemon Thread
               ▼
┌─────────────────────────────────────────────────────────────┐
│  _run_generate_in_thread → _generate_listing_impl           │
│                                                             │
│   Part 1: Save settings to AppSettings                      │
│   Part 2: (run_mode=full only) MSA calc + Grid build        │
│   Part 3: Resolve target stores from ST_MASTER              │
│   Part 4: Build ARS_LISTING_WORKING (raw input)             │
│   Part 5: Compute MJ_REQ / GH / H per Primary grid          │
│   Part 6: ST_RANK (per-MAJ_CAT store rank)                  │
│   Part 7: Apply OPT_TYPE classification                     │
│   Part 8: Listing + Allocation (rule_engine_new)            │
│           ┌───────────────────────────────────────────┐     │
│           │ Stage A — List OPTs (R01-R09)             │     │
│           │ Stage B — Explode to VAR_ART × SZ         │     │
│           │ Stage C — Allocate (RL → TBC → TBL)       │     │
│           │           per round × per rank × bands    │     │
│           │ Stage D — Reflect back into WORKING       │     │
│           └───────────────────────────────────────────┘     │
│   Part 9: Materialize ARS_LISTING                           │
└──────────────┬──────────────────────────────────────────────┘
               │ end_session(SUCCESS|FAILED, summary)
               ▼
┌─────────────────────────────────────────────┐
│  UI: poll /listing/sessions/{id} every 3 s  │
│  + /listing/alloc-progress?batch_id=…       │  parallel modes only
│  → toast on completion, refresh KPIs        │
└─────────────────────────────────────────────┘
```

---

## 2. Request Parameters — ALL fields

Source: `class GenerateRequest(BaseModel)` in [listing.py:65-108](backend/app/api/v1/endpoints/listing.py#L65-L108)

### 2.1 Scope selection

| Field | Type | Default | Allowed | Effect |
|---|---|---|---|---|
| `rdc_mode` | str | `"all"` | `"own"` \| `"cross"` \| `"all"` | Picks which RDCs supply stock to which stores. |
| `rdc_values` | list[str] | `[]` | RDC codes | Used when `rdc_mode="own"`. The RDCs whose stock goes to *their own* mapped stores. |
| `cross_from` | list[str] | `[]` | RDC codes | Used when `rdc_mode="cross"`. RDCs that **donate** stock. |
| `cross_to` | list[str] | `[]` | RDC codes | Used when `rdc_mode="cross"`. RDCs whose stores **receive** the donated stock. |
| `store_codes` | list[str] | `[]` | ST_CD values | Specific stores to listing. Empty list = all active stores from `Master_ALC_INPUT_ST_MASTER` (LISTING flag = 1). |
| `maj_cat_values` | list[str] | `[]` | MAJ_CAT values | Limit listing to these MAJ_CATs. Empty = all MAJ_CATs in `ARS_MSA_GEN_ART`. |

> **rdc_mode behavior**
> - `all` — every active RDC's stock flows to its mapped stores (full run).
> - `own` — only the RDCs in `rdc_values` are processed; each goes to its own stores.
> - `cross` — option pool comes from `cross_from`, recipients are stores mapped to `cross_to`.

### 2.2 Pipeline mode

| Field | Type | Default | Allowed | Effect |
|---|---|---|---|---|
| `run_mode` | str | `"listing"` | `"listing"` \| `"full"` | `full` runs MSA calc + Grid Builder + Listing in sequence. `listing` skips MSA/Grid (assumes both already populated). |
| `mix_mode` | str | `"st_maj_rng"` | `"st_maj_rng"` \| `"st_maj"` \| `"each"` | How MIX rows are aggregated before listing. `st_maj_rng`=1 line per (store, maj_cat, RNG_SEG). `st_maj`=coarser. `each`=keep raw. |

### 2.3 Listing rule variables (Stage A)

These tune the rules that decide which OPTs get listed.

| Field | Type | Default | Range | What it does |
|---|---|---|---|---|
| `stock_threshold_pct` | float | `0.6` | `0.0–1.0` | Used in OPT_TYPE classification. When `STK >= X% × ACS_D × I_ROD` an option becomes `RL` (Replenishment) instead of TBC/TBL. Lower X = fewer RL classifications. |
| `excess_multiplier` | float | `2.0` | `>1.0` | Threshold for EXCESS tagging. `STK > X × OPT_MBQ` → flagged excess (kept out of replenishment). Higher = more lenient. |
| `hold_days` | int | `0` | `0–N` | Extra days added to the warehouse-side OPT_MBQ_WH for **new options only** (`IS_NEW=1`). Used to keep buffer stock at warehouse. |
| `age_threshold` | int | `15` | days | Articles whose `AGE < X` use `PER_OPT_SALE` instead of historical sale to compute OPT_MBQ — this prevents new launches from looking under-allocated. |
| `req_weight` | float | `0.4` | `0.0–1.0` | Store ranking: weight on requirement-rank component of ST_RANK. (`req_weight + fill_weight` should sum to 1.0.) |
| `fill_weight` | float | `0.6` | `0.0–1.0` | Store ranking: weight on fill-rate-rank component of ST_RANK. |
| `min_size_count` | int | `3` | `≥0` | TBL listing rule R07: option needs at least this many size variants with positive `FNL_Q` (alternative path to the 60% ratio gate). `0` disables the rule. |
| `default_acs_d` | float | `18.0` | days | Fallback ACS_D when an option has NULL/0 average-daily-sale. Used inside OPT_TYPE classification. |
| `pri_ct_check_rl` | bool | `true` | `true/false` | When **true**, RL options must have `PRI_CT% ≥ 100` (full primary-grid coverage) to list. **TBL always enforces.** |
| `pri_ct_check_tbc` | bool | `true` | `true/false` | Same as above but for TBC options. |

### 2.4 Allocation behavior (Stage C)

| Field | Type | Default | Allowed | What it does |
|---|---|---|---|---|
| `enable_fallback` | bool | `false` | true/false | Enables fallback allocation: when the strict pass leaves stock unallocated, demote grids one-by-one and try again with relaxed constraints. |
| `fallback_boost_mode` | str | `"full_mbq"` | `"full_mbq"` \| `"sales_only"` \| `"str"` | How the fallback recomputes targets: `full_mbq`=multiply OPT_MBQ by `static_growth_pct`; `sales_only`=boost only the velocity component; `str`=use STR-tiered boost (`str_tiers`). |
| `static_growth_pct` | float | `130.0` | `100–500` | Growth percentage for `full_mbq`/`sales_only` fallback. 130 = 1.3× multiplier. |
| `str_tiers` | str | `"30:150,45:130,60:120,90:110"` | `"days:pct,…"` | STR fallback tiers. Read as: ≤30 days-of-cover → 150% boost, ≤45 → 130%, ≤60 → 120%, ≤90 → 110%. |

### 2.5 Allocation engine

| Field | Type | Default | Allowed | What it does |
|---|---|---|---|---|
| `allocation_mode` | str | `"python_parallel"` | `"sequential"` \| `"python_parallel"` \| `"sql_parallel"` \| `"pandas"` | Stage C runner. See §5. |
| `parallel_workers` | int | `8` | `2–16` (clamped to 2-8 today) | Worker count for parallel modes. Sequential ignores this. |

### 2.6 Source tables (advanced — leave at defaults)

| Field | Default |
|---|---|
| `msa_table` | `ARS_MSA_GEN_ART` |
| `grid_table` | `ARS_GRID_MJ_GEN_ART` |
| `st_master_table` | `Master_ALC_INPUT_ST_MASTER` |

---

## 3. Async Lifecycle

Source: [listing.py:317-432](backend/app/api/v1/endpoints/listing.py#L317-L432)

1. **Submit** — POST `/listing/generate` with the parameters above.
2. **Immediate response** (within ~1 s):
   ```json
   {
     "success": true,
     "message": "Listing generation started in background…",
     "data": {
       "session_id": "20260427_104530_123",
       "alloc_batch_id": "20260427_104530_123",
       "allocation_mode": "python_parallel",
       "parallel_workers": 8,
       "status": "RUNNING"
     }
   }
   ```
3. **Background work** runs in a daemon thread; logs go to:
   - DB: `ARS_LISTING_SESSIONS` (header row)
   - File: `backend/logs/listing_sessions/<session_id>.log`
   - Queue: `ARS_ALLOC_MAJCAT_QUEUE` (parallel modes only)
4. **UI polls**:
   - `GET /listing/sessions/{id}` every 3 s — overall status.
   - `GET /listing/alloc-progress?batch_id=…` every 3 s — per-MAJ_CAT progress.
   - `GET /listing/active-job` every 5 s — server-wide watcher.
5. **Completion** — STATUS flips to `SUCCESS` or `FAILED`. Toast fires. KPIs refresh.

Cancel: `POST /listing/cancel-batch {batch_id}` — sets cooperative event, KILLs SQL SPIDs.

---

## 4. Pipeline Stages — what each stage actually does

### Part 1 — Save settings
The current variable values are upserted into `AppSettings` so the next user lands on the same defaults.

### Part 2 — Full pipeline (only when `run_mode="full"`)
- A. Pre-grid calc: `calculate_per_day_sale` populates derived velocity columns.
- B. Grid Builder: every active grid in `ARS_GRID_BUILDER` is rebuilt in parallel.
- C. MSA refresh + listing — see Parts 3-9 below.

### Part 3 — Resolve target stores
Pulls active stores from `Master_ALC_INPUT_ST_MASTER` (LISTING flag = 1). Filtered by `store_codes` if provided. Mapped to RDCs via the `RDC` column.

### Part 4 — Build `ARS_LISTING_WORKING`
Joins MSA + Grid + Master tables into a single row per `(WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR)`. Carries every input column the rule engine needs.

### Part 5 — Compute MJ_REQ + GH + H (per Primary grid)
For each Primary grid in `ARS_GRID_BUILDER` (status=ACTIVE, group=Primary):
- `<grid>_REQ` — daily demand at the grid grain.
- `GH_<grid>` — total generic hits = number of (article, color) pairs at that grain.
- `H_<grid>` — number of `(article, color)` rows at the grain whose `<grid>_REQ > 0`.
- `<grid>_CT% = H/GH × 100` — coverage.

The default Primary grid is `MJ_REQ` at the `(WERKS, MAJ_CAT)` grain. Discovery is in `_discover_primary_grids` ([rule_engine_new.py:473-523](backend/app/services/rule_engine_new.py#L473-L523)).

### Part 6 — ST_RANK
Per-MAJ_CAT store rank. Combines requirement-rank (weighted by `req_weight`) and fill-rate-rank (`fill_weight`). Lower = better. Used as the inner tie-breaker during allocation.

### Part 7 — OPT_TYPE classification
Each row gets one of:
- **`RL`** Replenishment Listing — `STK >= stock_threshold_pct × ACS_D × I_ROD`.
- **`TBC`** To-Be-Covered — short-stock but inside the trivial threshold.
- **`TBL`** To-Be-Listed — significantly short-stock; needs full primary-grid coverage to list.
- **`MIX`** — fed by the mix rule chain (skipped in listing per R02).
- **`NL`** Not-Listed — explicitly suppressed (skipped per R03).

### Part 8 — Stage A: Listing rules (`_stage_a_apply_rules`)

Source: [rule_engine_new.py:187-254](backend/app/services/rule_engine_new.py#L187-L254)

A row is `LISTED_FLAG=1` only if **ALL** enabled rules pass:

| Code | Rule | Default | Toggle (constant) |
|---|---|---|---|
| **R01** | `LISTING = 1` (article master flag) | ON | `RULE_R01_LISTING` |
| **R02** | `OPT_TYPE != 'MIX'` | ON | `RULE_R02_NOT_MIX` |
| **R03** | `OPT_TYPE != 'NL'` | ON | `RULE_R03_NOT_NL` |
| **R04** | `MSA_FNL_Q > 0` | ON | `RULE_R04_MSA_POS` |
| **R05** | `OPT_REQ_WH ≥ 1` | ON | `RULE_R05_REQ_POS` |
| **R06** | `PRI_CT% ≥ 100` for OPT_TYPE in {RL?, TBC?, TBL} (RL/TBC controlled by `pri_ct_check_rl`/`pri_ct_check_tbc`; TBL always enforces). Bypassed when `ALLOC_FLAG=1`. | ON | `RULE_R06_PRI_100` |
| **R07** | TBL only: `(VAR_FNL_COUNT / VAR_COUNT) >= stock_threshold_pct` OR `VAR_FNL_COUNT >= min_size_count` | ON | `RULE_R07_VAR_RATIO_TBL` |
| **R09** | TBL only: `MJ_REQ >= 0.5 × MAX_DAILY_SALE` (rejects trivial demand) | ON | `RULE_R09_TBL_TRIVIAL` |

Rejected rows have `LISTED_FLAG=0` and `LISTED_REASON='R0X_…;R0Y_…'` so a planner can see exactly which rule(s) blocked them.

Also: **OPT priority rank** — global ROW_NUMBER ordered by `OPT_TYPE (RL→TBC→TBL), OPT_PRIORITY_TIER (1=focus-uncapped, 2=focus-capped, 3=regular), ST_RANK, SEC_CT% DESC, MAX_DAILY_SALE DESC, OPT_REQ_WH DESC`. ([rule_engine_new.py:270-305](backend/app/services/rule_engine_new.py#L270-L305))

### Part 8 — Stage B: Explode to VAR_ART × SZ (`_stage_b_explode`)

Source: [rule_engine_new.py:338-467](backend/app/services/rule_engine_new.py#L338-L467)

For each listed `(WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR)`, **CROSS JOIN** with `ARS_MSA_VAR_ART` (where `FNL_Q > 0`) to produce one row per (variant article × size). Then:

- **`_stage_b_fill_cont`** — populate the size-mix `CONT` factor from `Master_CONT_SZ` (per `ST_CD, MAJ_CAT, SZ`); fall back to `ST_CD='CO'` corporate row; final fallback = uniform `1/sz_count`.
- **`_stage_b_fill_targets`** —
  - `SZ_MBQ    = round(OPT_MBQ × CONT, 0)`
  - `SZ_MBQ_WH = round(OPT_MBQ_WH × CONT, 0)`
  - `SZ_REQ    = max(SZ_MBQ - SZ_STK, 0)`  (store-side req)
  - `SZ_REQ_WH = max(SZ_MBQ_WH - SZ_STK, 0)` (warehouse buffer req)
- **`_stage_b_indexes`** — clustered index on the walk order + nonclustered on the pool key.

### Part 8 — Stage C: Allocation waterfall

Source: [rule_engine_new.py:1131-1397](backend/app/services/rule_engine_new.py#L1131-L1397)

This is the heart of the engine. Conceptually:

```
For each OPT_TYPE in ["RL", "TBC", "TBL"]:        # higher priority first
  For round r in 1..max(I_ROD):                   # deeper coverage each pass
    Reset ROUND_SHIP/ROUND_HOLD = 0 for opt_type
    For each rank band (BAND_SIZE=1):             # one rank at a time
      Step 1: Allocate band — cumulative window UPDATE
              honoring pool capacity, picking by (rank, ST_RANK)
      Step 2: Decrement #nre_pool by ROUND_SHIP+ROUND_HOLD
      If ENABLE_PER_OPT_REVALIDATION:
        Revalidate (9-statement batch):
          - reduce MSA_FNL_Q_REM
          - reduce <grid>_REQ_REM
          - recompute H_<grid>_REM and PRI_CT_REM
          - SKIP rows whose REM values now fail R04/R06
```

**Pool table:** `#nre_pool` (a global temp at the SQL session) keyed by `(RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ)`. `FNL_Q_REM` is decremented as each band consumes pool. **One pool per SQL session**, so each parallel worker has its own.

**SHIP vs HOLD logic:**
- `SHIP_QTY` = quantity that goes to the store this round.
- `HOLD_QTY` = quantity reserved at the warehouse for this option (the `SZ_MBQ_WH` buffer for new items, gated by `hold_days`).
- `ALLOC_QTY = SHIP_QTY` (final stored value).

**Final classification** (`ALLOC_STATUS`):
- `ALLOCATED` — `SHIP+HOLD ≥ remaining lifetime target`.
- `PARTIAL` — `SHIP > 0` but below the target.
- `SKIPPED` — `SHIP = 0 AND HOLD = 0`. `SKIP_REASON` is one of:
  - `ALREADY_STOCKED` — store already has enough.
  - `NO_POOL_OR_DEMAND` — pool exhausted before this row got picked.
  - `SKIP_MSA_EXHAUSTED` — MSA budget consumed by higher-rank rows.
  - `SKIP_PRI_BROKEN` — primary-grid coverage dropped below 100% mid-run.
  - `SKIP_STORE_BROKEN` — `MJ_REQ_REM < ACS_SKIP_FACTOR(0.5) × ACS_D` for this store.

### Part 8 — Stage D: Reflect back (`_stage_d_reflect`)

Aggregates `ARS_ALLOC_WORKING.SHIP_QTY/HOLD_QTY/ALLOC_QTY/ALLOC_STATUS` back to `ARS_LISTING_WORKING` at the OPT grain `(WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR)`. This is what downstream readers see.

### Part 9 — Materialize `ARS_LISTING`
Final user-facing table. Created from `ARS_LISTING_WORKING` filtered by `LISTED_FLAG=1`. Columns include identity + OPT_TYPE + ALLOC_QTY + HOLD_QTY + IS_NEW + RDC + MSA_FNL_Q + ALLOC_STATUS + ALLOC_REMARKS.

---

## 5. Allocation Modes — Stage C engines

All four produce **bit-identical** SHIP_QTY / HOLD_QTY (validated by `scripts/validate_alloc_modes.py`).

| Mode | File | How Stage C runs | When to use |
|---|---|---|---|
| `sequential` | [rule_engine_new.py](backend/app/services/rule_engine_new.py) | One thread, one connection, one MAJ_CAT at a time. | Debugging, smallest scope (1-2 MAJ_CATs), or as a known-safe fallback. |
| `python_parallel` | [rule_engine_parallel_python.py](backend/app/services/rule_engine_parallel_python.py) | N workers, each takes a MAJ_CAT from queue, runs the SAME Python loop as sequential but scoped to that MAJ_CAT. ~7× faster. | **DEFAULT.** Best balance of speed + resilience. |
| `sql_parallel` | [rule_engine_parallel_sql.py](backend/app/services/rule_engine_parallel_sql.py) + [usp_ars_allocate_majcat.sql](backend/sql/usp_ars_allocate_majcat.sql) | N workers, each EXECs `dbo.usp_ars_allocate_majcat` once per MAJ_CAT. The whole waterfall runs in T-SQL — ~1 round-trip per MAJ_CAT. | Fastest in absolute wall-clock. Requires the proc deployed (auto-deploys on first call). |
| `pandas` | [rule_engine_pandas.py](backend/app/services/rule_engine_pandas.py) | Loads alloc + working tables into pandas DataFrames. Does the waterfall in NumPy. Bulk-MERGEs back. | Useful when DB is the bottleneck or for in-memory profiling. **Heavier on backend RAM** — avoid if backend memory is tight. |

**Workers scope** — every parallel worker:
- holds its own engine connection (`engine.connect() as wconn`) for the full run,
- registers its SQL SPID with `alloc_cancellation` so /cancel-batch can KILL it,
- pulls one MAJ_CAT at a time via `claim_next` from `ARS_ALLOC_MAJCAT_QUEUE`,
- on success → `mark_done`; on failure → `mark_failed` with retry budget.

**Default workers** — `ARS_PARALLEL_WORKERS` env (default 4). Clamped to 2-8 today (lowered from 16 because 8 ThreadPoolExecutor threads in one uvicorn process saturate the GIL and starve unrelated requests).

---

## 6. Tables Touched

| Table | Read | Written | Notes |
|---|:---:|:---:|---|
| `Master_ALC_INPUT_ST_MASTER` | ✓ | | Store master + RDC mapping |
| `ARS_MSA_GEN_ART` | ✓ | | MSA at generic-article grain |
| `ARS_MSA_VAR_ART` | ✓ | | MSA at variant-article grain (drives Stage B explode) |
| `ARS_GRID_BUILDER` | ✓ | | Grid definitions; only ACTIVE+Primary participate |
| `ARS_GRID_MJ_GEN_ART` | ✓ | | Generic-article grid |
| `ARS_GRID_MJ_VAR_ART` | ✓ | | Variant grid (per-size stock) |
| `Master_CONT_SZ` | ✓ | | Per-store-MAJ_CAT-size mix factor |
| `AppSettings` | ✓ | ✓ | Saves last-used variables |
| `ARS_LISTING_WORKING` | ✓ | ✓ | Built fresh each run; carries all intermediate columns |
| `ARS_LISTED_OPT` | ✓ | ✓ | Stage A output (only listed OPTs) |
| `ARS_ALLOC_WORKING` | ✓ | ✓ | Stage B output (variant×size grain). Rebuilt each run. |
| `ARS_LISTING` | | ✓ | Final user-facing table (Part 9). |
| `ARS_LISTING_FINAL` | | ✓ | Filtered version created by `/listing/create-final`. |
| `ARS_ALLOC_MAJCAT_QUEUE` | ✓ | ✓ | Per-MAJ_CAT work queue for parallel modes. |
| `ARS_LISTING_SESSIONS` | ✓ | ✓ | Session header row (one per /generate call). |
| `tempdb..#nre_pool` | ✓ | ✓ | Per-session pool (decremented during waterfall). |

---

## 7. Output Snapshots

### 7.1 Endpoint return value

```json
{
  "success": true,
  "message": "Listing generation started in background (mode=python_parallel, session=20260427_104530_123)…",
  "data": {
    "session_id": "20260427_104530_123",
    "alloc_batch_id": "20260427_104530_123",
    "allocation_mode": "python_parallel",
    "parallel_workers": 8,
    "status": "RUNNING"
  }
}
```

### 7.2 Session row when complete (`/listing/sessions/{id}`)

```json
{
  "session_id": "20260427_104530_123",
  "user": "santosh",
  "started_at": "2026-04-27T10:45:30",
  "completed_at": "2026-04-27T10:51:18",
  "duration_sec": 348.4,
  "status": "SUCCESS",
  "allocation_mode": "python_parallel",
  "workers": 8,
  "rdc_mode": "all",
  "store_count": 320,
  "majcat_count": 242,
  "listed_opts": 18452,
  "alloc_rows": 1284091,
  "ship_qty_total": 521456.0,
  "hold_qty_total": 38120.0,
  "failed_majcats": 0,
  "step_timings": [ ... ],
  "log_file_path": "backend/logs/listing_sessions/20260427_104530_123.log"
}
```

### 7.3 Live alloc progress (`/listing/alloc-progress?batch_id=…`)

```json
{
  "success": true,
  "progress": {
    "total": 242, "done": 178, "failed": 0,
    "in_progress": 8, "pending": 56, "pct": 73.5
  },
  "failed": [],
  "summary": { /* per-MAJ_CAT ship/hold/rows */ }
}
```

---

## 8. Worked Example

### 8.1 Scenario

A planner wants to run a listing for:
- The two RDCs `RDC01` and `RDC02`,
- All their mapped stores,
- Only the MAJ_CATs `MENS_FW_CASUAL` and `MENS_FW_FORMAL`,
- With **default rules** but a tighter primary-grid gate on RL,
- Using `python_parallel` with 8 workers.

### 8.2 UI inputs

| Field | Value |
|---|---|
| RDC mode | Own |
| RDCs | `RDC01, RDC02` |
| Stores | (auto-detected from RDC mapping) |
| MAJ_CATs | `MENS_FW_CASUAL, MENS_FW_FORMAL` |
| Run mode | Listing |
| MIX mode | `st_maj_rng` (default) |
| Stock threshold % | `0.6` |
| Excess multiplier | `2.0` |
| Hold days | `0` |
| Age threshold | `15` |
| Req weight / Fill weight | `0.4 / 0.6` |
| Min size count (TBL) | `3` |
| Default ACS_D | `18.0` |
| PRI_CT check on RL | **TRUE** |
| PRI_CT check on TBC | TRUE |
| Enable fallback | FALSE |
| Allocation mode | `python_parallel` |
| Workers | `8` |

### 8.3 Equivalent JSON request body

```json
POST /api/v1/listing/generate
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "rdc_mode": "own",
  "rdc_values": ["RDC01", "RDC02"],
  "store_codes": [],
  "maj_cat_values": ["MENS_FW_CASUAL", "MENS_FW_FORMAL"],
  "run_mode": "listing",
  "mix_mode": "st_maj_rng",

  "stock_threshold_pct": 0.6,
  "excess_multiplier": 2.0,
  "hold_days": 0,
  "age_threshold": 15,
  "req_weight": 0.4,
  "fill_weight": 0.6,
  "min_size_count": 3,
  "default_acs_d": 18.0,
  "pri_ct_check_rl": true,
  "pri_ct_check_tbc": true,

  "enable_fallback": false,
  "fallback_boost_mode": "full_mbq",
  "static_growth_pct": 130.0,
  "str_tiers": "30:150,45:130,60:120,90:110",

  "allocation_mode": "python_parallel",
  "parallel_workers": 8
}
```

### 8.4 What happens (timeline)

| t (s) | Event |
|---|---|
| 0.0 | Request received. `start_session("20260427_…")` — session row + log file created. |
| 0.1 | Background thread launched. Endpoint returns `200 OK` with session_id. |
| 0.2 | Part 1: settings persisted to `AppSettings`. |
| 0.3 | Parts 3-7: WORKING table built, MJ_REQ/GH/H computed, ST_RANK assigned, OPT_TYPE classified. |
| 12 | Stage A: rules applied. Result `[A] listed=842 dropped=158 total=1000`. |
| 14 | Stage B: explode → 9 432 alloc rows. CONT, SZ_MBQ, SZ_REQ filled. Indexes built. |
| 15 | Primary grids discovered: `MJ_REQ, RNG_SEG_REQ`. `_REM` shadow columns initialized. |
| 16 | Queue seeded with 2 MAJ_CATs. 8 workers pick up `MENS_FW_CASUAL` and `MENS_FW_FORMAL` (the other 6 idle since only 2 MAJ_CATs). |
| 16-58 | Each worker runs RL → TBC → TBL × rounds × ranks for its MAJ_CAT. Per-band revalidate decrements `MSA_FNL_Q_REM` / `<grid>_REQ_REM` / `PRI_CT_REM`. |
| 58 | Workers exit. Main thread runs final `UPDATE … ALLOC_QTY = SHIP_QTY`, `ALLOC_STATUS` classification, Stage D reflect. |
| 60 | `end_session("SUCCESS", summary)` writes the metrics back to `ARS_LISTING_SESSIONS`. |
| 61+ | UI's poll detects `STATUS=SUCCESS`, refreshes KPIs. |

### 8.5 Sample log lines from the per-session file

```
2026-04-27 10:45:30.102 | INFO | === SESSION START id=20260427_104530_123 user=santosh mode=python_parallel workers=8 ===
2026-04-27 10:45:42.541 | INFO | [A] rules applied: listed=842 dropped=158 total=1000
2026-04-27 10:45:42.612 | INFO | [A] listed=842
2026-04-27 10:45:44.880 | INFO | [B] alloc rows = 9432
2026-04-27 10:45:45.102 | INFO | [C-py] primary grids = ['MJ_REQ', 'RNG_SEG_REQ']
2026-04-27 10:45:45.221 | INFO | [C-py] batch_id=20260427_104530_123 total_majcats=2 workers=8
2026-04-27 10:46:18.503 | INFO | [C-py-W0] 1/2 (50.0%) — MAJ_CAT=MENS_FW_CASUAL ship=42188 hold=2104 rows=4612 in 33.2s
2026-04-27 10:46:58.117 | INFO | [C-py-W1] 2/2 (100.0%) — MAJ_CAT=MENS_FW_FORMAL ship=39055 hold=1850 rows=4820 in 72.8s
2026-04-27 10:47:01.882 | INFO | [C-py] DONE batch=… listed=842 alloc_rows=9432 ship=81243 hold=3954 done=2 failed=0 in 116.7s
2026-04-27 10:47:01.991 | INFO | === SESSION END id=20260427_104530_123 status=SUCCESS duration=116.7s alloc_rows=9432 failed=0 ===
```

### 8.6 What changes if the planner flips one parameter

| Change | Effect on listed/alloc count | Risk |
|---|---|---|
| `pri_ct_check_rl: false` | More RL options listed (those with PRI_CT% < 100 now pass R06). | Allocations may go to incomplete primary grids — fragmented coverage. |
| `min_size_count: 0` | More TBL options listed (no minimum size requirement). | TBL options with very few sizes start consuming pool. |
| `stock_threshold_pct: 0.4` | Fewer RL classifications, more TBC/TBL. | More aggressive replenishment — uses more pool. |
| `enable_fallback: true` | Stage C runs a second pass with relaxed targets when stock remains. | Increases allocation but can over-stock; runtime longer. |
| `allocation_mode: "sql_parallel"` | Runtime drops by ~30-50%. SHIP/HOLD identical. | Requires `usp_ars_allocate_majcat` deployed; auto-deploys on first call. |
| `parallel_workers: 16` | (Currently capped at 8.) Hits SQL Server CPU/lock contention; doesn't help past 8 in single uvicorn process. | Starves other endpoints (auth, polling) due to GIL. |

---

## 9. Failure & Recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| Session stuck `RUNNING` 30+ min, no progress | Worker thread crashed / proxy disconnected | `POST /listing/sessions/{id}/kill` then retry. |
| `failed_majcats > 0` in result | Per-MAJ_CAT exception (often a deadlock past retry budget). Detail in `ARS_ALLOC_MAJCAT_QUEUE.ERROR_MSG`. | `POST /listing/retry-failed {batch_id, allocation_mode, parallel_workers}` — Parts 1-7 NOT re-run; only failed MAJ_CATs replayed. |
| All MAJ_CATs failed with same error | Bug in rule / missing source table | Check the per-session log file; fix root cause; restart. |
| `auto-cancelled (orphan, never claimed)` | Session errored before workers started Stage C | Look at the session log, fix, retry. |

`/listing/active-job` auto-cancels stale rows: IN_PROGRESS with no PICKED_AT update for 10 min, or PENDING with no claim ever for 5 min.

---

## 10. Constants & Feature Flags (code-side, NOT in the request)

These live in [rule_engine_new.py:31-49](backend/app/services/rule_engine_new.py#L31-L49). Changing them requires code deploy.

| Constant | Default | Effect |
|---|---|---|
| `RULE_R01_LISTING` | True | Honour the article master `LISTING` flag |
| `RULE_R02_NOT_MIX` | True | Drop MIX OPTs |
| `RULE_R03_NOT_NL` | True | Drop NL OPTs |
| `RULE_R04_MSA_POS` | True | Require `MSA_FNL_Q > 0` |
| `RULE_R05_REQ_POS` | True | Require `OPT_REQ_WH ≥ 1` |
| `RULE_R06_PRI_100` | True | Require `PRI_CT% ≥ 100` (per opt-type via request flags) |
| `RULE_R07_VAR_RATIO_TBL` | True | TBL: variant-coverage gate |
| `RULE_R09_TBL_TRIVIAL` | True | TBL: reject trivial demand |
| `ENABLE_FOCUS_TIERING` | True | Use FOCUS_W_CAP / FOCUS_WO_CAP for tier ordering |
| `ENABLE_STORE_BROKEN` | True | Skip store within opt_type when MJ_REQ_REM < 0.5 × ACS_D |
| `ENABLE_GRID_OVERFLOW` | False | (reserved) |
| `ENABLE_SIZE_COVERAGE_BREAK` | False | (reserved) |
| `ENABLE_PER_OPT_REVALIDATION` | True | After each band, re-check R04/R06 against decremented REM values |
| `ACS_SKIP_FACTOR` | 0.5 | The 0.5 in the store-broken / H_REM rules |
| `OPT_TYPE_ORDER` | `["RL","TBC","TBL"]` | Waterfall priority |
| `BAND_SIZE` | 1 | One rank per band (required for per-OPT revalidate) |
| `POOL_TABLE` | `#nre_pool` | Per-session global temp |

---

## 11. Review Checklist (use before changing anything)

Before changing **any** rule or parameter:

- [ ] Read §2 to confirm what the parameter does at the request layer.
- [ ] Read §4-5 to find the stage(s) it affects.
- [ ] Search [rule_engine_new.py](backend/app/services/rule_engine_new.py) for the constant or column name to confirm where it's used.
- [ ] If it's a feature flag (§10), grep for the constant and check every reference — flags can affect Stage A *and* Stage C revalidate.
- [ ] Run the change through `scripts/validate_alloc_modes.py` to confirm sequential / python_parallel / sql_parallel / pandas all still produce identical SHIP_QTY/HOLD_QTY.
- [ ] Pick a small scope (1-2 RDCs, 1-2 MAJ_CATs) and run with `allocation_mode: "sequential"` first — easiest to log-trace.
- [ ] Compare `step_timings` and `failed_majcats` against the previous run before promoting to the full prod run.

---

## 12. References

- Rule spec (deeper math): [docs/NEW_RULE_ENGINE_SPEC.md](docs/NEW_RULE_ENGINE_SPEC.md)
- Endpoint: [backend/app/api/v1/endpoints/listing.py](backend/app/api/v1/endpoints/listing.py)
- Sequential engine: [backend/app/services/rule_engine_new.py](backend/app/services/rule_engine_new.py)
- Python parallel: [backend/app/services/rule_engine_parallel_python.py](backend/app/services/rule_engine_parallel_python.py)
- SQL parallel: [backend/app/services/rule_engine_parallel_sql.py](backend/app/services/rule_engine_parallel_sql.py) + [backend/sql/usp_ars_allocate_majcat.sql](backend/sql/usp_ars_allocate_majcat.sql)
- Pandas engine: [backend/app/services/rule_engine_pandas.py](backend/app/services/rule_engine_pandas.py)
- Sessions: [backend/app/services/listing_sessions.py](backend/app/services/listing_sessions.py)
- Cancel registry: [backend/app/services/alloc_cancellation.py](backend/app/services/alloc_cancellation.py)
- Validation script: `scripts/validate_alloc_modes.py`
