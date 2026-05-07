# Review Branch — Next Steps

This branch (`review/cleanup-and-tests`) closes three of the six items from
the post-review checklist. The other three need either you (Akash) for scope
decisions, the dev for infra access, or just process discipline going
forward. They are captured here with concrete, actionable next steps.

## What this branch already does

| Item | Status | Where |
|---|---|---|
| Fix dashboard `else_` SQLAlchemy bug | DONE | `backend/app/api/v1/endpoints/dashboard.py` |
| Quarantine dead engines (`listing_allocator.py`, `rule_engine.py`) | DONE | `backend/app/services/_legacy/` |
| Pure-Python formula spec + 38-test regression suite | DONE | `backend/app/services/allocation_formulas.py` + `backend/tests/` |
| Excel reconciliation harness | DONE | `backend/scripts/excel_reconciliation.py` |
| **Delivery Order output (multi-sheet xlsx, BDC-ready)** | **DONE** *(on `functionality/delivery-order-output`)* | `backend/app/services/delivery_order.py`, `GET /listing/parked-runs/{sid}/delivery-order`, 15 tests |

Run the tests:
```bash
cd backend && python -m pytest tests/ -v
```

## Item 1 — Run M_TEES_HS end-to-end and diff vs Excel

**Owner:** dev (needs SQL Server access at HOPC560 + the Excel reference).

The harness is in place. The dev needs to:

1. Run a full ARS pipeline for a single MAJ_CAT against current data:
   - MSA stock calculation
   - Pre-grid + grid build
   - Listing generation
   - Allocation (`pandas` mode is the default)
2. Open the legacy file `DH24-MENS-M_TEES_HS-Option_Working-1-APR.xlsb`
   in Excel, save the `ST-OPTION` (or equivalent allocation-output) sheet
   as `.xlsx`. The 80MB+ xlsb files parse very slowly in Python; the
   manual save once is faster than fighting `pyxlsb`.
3. Run:
   ```bash
   python backend/scripts/excel_reconciliation.py \
     --excel ~/Downloads/DH24-MENS-M_TEES_HS-ST-OPTION.xlsx \
     --maj-cat M_TEES_HS \
     --alloc-col DISP_Q \
     --hold-col HOLD_QTY
   ```
4. Review `reconciliation_M_TEES_HS.csv`. Tolerable: drift due to rounding
   (≤ 5 units per OPT). Untolerable: systematic shifts (one side
   consistently higher), missing OPTs on either side, MIX rows on one side
   that aren't on the other.

If drift is systematic, the most likely sources (ranked):

| Suspect | How to check |
|---|---|
| `CONT` from `Master_CONT_SZ` does not sum to 1.0 per OPT | Run diagnostic A in `ARS_Allocation_Engine_SOP.md` §14 |
| `OPT_REQ_ORIG` snapshot taken after post-sync (zeros) | Check `_add_tracking_columns` runs before any post-sync update |
| `MJ_REQ` cap clipping unevenly | Run diagnostic D in the SOP |
| Rounding-direction mismatch (Python `round` vs SQL `ROUND` use banker's vs half-up) | Pick worst delta, recompute manually |

## Item 2 — Snowflake stack quarantine

**Owner:** decision is yours; dev executes.

Why deferred from this branch: `app/services/allocation/` is still wired
into eight `/api/v1/allocation-engine/*` endpoints. Removing the directory
without removing those routes leaves a 500-prone API surface. The current
state is no worse — those endpoints already 500 because the Snowflake
account is suspended.

**Two options:**

**(a) Reactivate Snowflake.** Pay the bill, restore `RESULTS.ARTICLE_SCORES`
(576M scored pairs), and run the original Snowflake-then-Azure design
alongside the current SQL-Server-only path. This was the architecture in
your original Obsidian spec.
- Pro: restores the per-(store, article) scoring with 6 CONT_* tables that
  the spec describes.
- Con: ongoing cost, separate maintenance, and the SQL-Server design works.

**(b) Decommission the Snowflake stack.** Delete `app/services/allocation/`
and all eight `/api/v1/allocation-engine/*` endpoints + dashboard tab. Make
the SQL-Server pipeline (`/listing/generate`) the sole path.
- Pro: one engine, simpler ops, no dependency on suspended account.
- Con: per-store scoring is no longer attribute-weighted; you rely on the
  grid-hierarchy approach (PRI_CT% gating) instead.

Recommendation: **(b)** unless you have a concrete reason the grid approach
underperforms attribute-weighted scoring on one of the tested MAJ_CATs.
Decide after Item 1 produces a real diff — if the Excel reference matches
ARS within tolerance using the SQL pipeline, you do not need Snowflake.

## Item 3 — Missing pieces from the original 29-step spec

These are listed in `Obsidian/v2retail/ARS 29-Step Algorithm.md` but not
implemented in code. Decide for each: build / cut / defer.

| Feature | Spec source | Likely effort | Recommendation |
|---|---|---|---|
| Multi-option tagging (article scoring ≥ 150 takes 2-3 slots, 4-level cascade) | 29-step §9 | 2-3 weeks | Defer until reconciliation passes — without scoring it's vestigial |
| Hero / Focus / Assorted lists population | Handover doc | 1 week | Build — `FOCUS_W_CAP`/`FOCUS_WO_CAP` columns already exist, need ingest |
| Store-specific listing overrides (`ST_SPECIFIC=9999`) | Allocation Terminology | 3-5 days | Build — high business value (planner overrides) |
| Two-DC routing (DH24/DW01 each serves its own stores) | Handover doc | 1 week | Build — the `RDC` field exists but no serving rules |
| Pipeline inventory (INT/PRD/STO from SAP) | Handover doc | 2 weeks (SAP RFC) | Defer — separate SAP integration |
| ~~Delivery order output (Fresh Lorry-style file)~~ | Handover doc | ~~1 week~~ | **DONE** on `functionality/delivery-order-output` (2026-05-07). Multi-sheet xlsx with Dispatch_Detail / Store / RDC / Article summaries + BDC-ready sheet. Hold isolated from dispatch. 15 unit tests. |
| 12-month planning view | 29-step §3 | 2 weeks | Defer — separate planning module |

## Item 4 — Re-deploy to Azure with real data

**Owner:** dev.

State right now: `ars-v2retail-api.azurewebsites.net/health` returns
healthy but every read endpoint (`/allocations/`, `/listing/sessions`,
`/msa/sequences`, `/grid_builder/grids`, `/checklist/`, `/audit/`,
`/tables/registered`) returns `null`. The dashboard reports 0 tables, 0
rows, 0 audit logs. The actual production system runs on the dev's
on-prem `HOPC560` SQL Server.

Two fixes needed:

1. **Decide which DB is canonical.** Either:
   - Keep on-prem `HOPC560` and stop pretending Azure is live. Take the
     Azure URL down, or relabel it as a "demo / dev sandbox."
   - Move production to Azure SQL. Migrate the data, re-point the dev's
     toolchain at Azure, retire on-prem.
2. **Fix the deploy.** With the dashboard `else_` bug fixed in this
     branch, the next zip-deploy to Azure will at least show a non-error
     dashboard. After deploy, hit `/api/v1/dashboard/stats` with a valid
     token and confirm no `error` key in the response.

## Item 5 — Stop squash-merging

**Owner:** dev.

The entire `Aakash_sir` branch (~85K LOC across 331 files) is one commit:
```
c492f7d chore: bundle pending allocation, listing, MSA, and frontend updates
```

This makes review impossible — there's no way to see what changed when, or
to revert one change without reverting everything. Going forward:

1. **One commit per logical change.** Bug fix, refactor, new feature,
   schema migration — each separate.
2. **PRs from feature branches**, not direct pushes to long-lived ones.
3. **Commit messages explain why**, not just what. The body should mention
   the reasoning, the files touched, and any follow-up needed.
4. **Never squash a multi-week branch.** If history is messy, fix it with
   `rebase -i` before merge — but keep the meaningful commits.

This branch (`review/cleanup-and-tests`) is structured this way as a
template:
```
9a492a7 scripts: add excel_reconciliation.py for ground-truth diff vs ARS
a1734b0 test: add formula regression suite (38 tests, 0.12s)
[quarantine commit] refactor(services): quarantine listing_allocator and rule_engine
4c6d308 fix(dashboard): use sqlalchemy.case not func.case for stats query
```

Each commit stands alone, has a message that explains the reasoning, and
can be reverted independently.
