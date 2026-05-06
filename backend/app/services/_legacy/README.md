# Quarantined Legacy Modules

Files here were superseded but kept in-tree because the dev team flagged them
as "reference." They are NOT imported from any live API endpoint and should
not grow new callers. Delete them once nothing in the open repo points at them.

## What lives here and what replaced it

### `listing_allocator.py` — superseded
- **Was:** Multi-level waterfall allocator entrypoint
  (`run_multilevel_allocation`).
- **Now:** Replaced by the rule engine family
  (`rule_engine_pandas.py` for the default `pandas` mode,
  `rule_engine_new.py` for the `sequential` fallback).
- **Confirmation that it's dead:**
  - Only call site in `app/api/v1/endpoints/listing.py` was already
    behind `if False:` (still removed in this branch).
  - `app/docs/processes/listing_generation_pipeline.md` notes:
    "legacy allocator (still in repo, swapped out in favour of rule_engine)."

### `rule_engine.py` — superseded
- **Was:** First-pass refactor of the multi-level allocator.
- **Now:** Replaced by `rule_engine_new.py`. The module's own header comment
  says: "Drop-in replacement for listing_allocator.run_multilevel_allocation."
- **Confirmation that it's dead:** the only import in `listing.py` is inside
  an `if False:` documentation block (also removed in this branch).

## What is NOT here (intentionally)

- `rule_engine_pandas.py`, `rule_engine_new.py` — **live**. Default and
  sequential modes wired to `POST /api/v1/listing/generate`.
- `rule_engine_parallel_python.py`, `rule_engine_parallel_sql.py` — kept in
  `services/`. Used by `scripts/validate_alloc_modes.py` for performance
  benchmarking; not on the API path but still useful.
- `app/services/allocation/*` (Snowflake-based engine, ~2,200 lines) — kept
  in place. Still wired to `/api/v1/allocation-engine/*` endpoints, even
  though Snowflake itself is currently suspended. Quarantining requires
  also disabling those eight endpoints; punted to a follow-up. See
  `NEXT_STEPS.md`.
