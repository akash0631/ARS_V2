# ARS — Future Optimizations & Improvements

**Companion to** `OPTIMIZATION.md` (already in repo). That file lists ~30 file-anchored issues from an earlier review and a 30-day roadmap. This file:

1. Cross-references that work and marks what's **DONE** on `review/cleanup-and-tests`
2. Adds findings that **were missed**, in particular:
   - A committed-to-git production-credentials file (worse than the `config.py` defaults already flagged)
   - The whole `services/allocation/*` Snowflake stack
   - Allocation-correctness observability (separate from infrastructure observability)
   - The 30 % of the original 29-step ARS spec that was never built
3. Corrects stale findings in `OPTIMIZATION.md` (rule-engine layout, CI workflow status)
4. Provides a **90-day roadmap** that builds on top of the 30-day plan

Read `OPTIMIZATION.md` first; this file is a delta.

---

## 0. What's already done on `review/cleanup-and-tests`

| OPTIMIZATION.md item | Status on this branch | Where |
|---|---|---|
| §3.1 "Pick one of `rule_engine.py` / `rule_engine_new.py`; delete the other" | **DONE** — `rule_engine.py` and `listing_allocator.py` quarantined to `app/services/_legacy/` (kept for reference, not imported) | `4c6d308`, `_legacy/README.md` |
| Dashboard `else_` SQLAlchemy bug (not in OPTIMIZATION.md) | **DONE** | `4c6d308`, `dashboard.py:39-49` |
| Pure-Python formula spec + 38 regression tests (mentioned only as "add pytest" in §5.3) | **DONE** | `a1734b0`, `backend/tests/`, `backend/app/services/allocation_formulas.py` |
| Excel reconciliation harness (not in OPTIMIZATION.md — but should have been) | **DONE** | `9a492a7`, `backend/scripts/excel_reconciliation.py` |

Verify locally:
```bash
cd backend && python -m pytest tests/ -v   # 38 passed in 0.12s
```

---

## 1. Findings missed by `OPTIMIZATION.md`

### 1.1 CRITICAL — `app_settings.json` is a committed credentials file

`OPTIMIZATION.md` only flagged the **defaults in `config.py`**. It missed `backend/app_settings.json`, which is **checked into git on a public repo** (`harshalanand/ARS_V2`) and contains live production credentials:

```jsonc
// backend/app_settings.json — IN THE PUBLIC REPO
{
  "database": { "username": "sa", "password": "vrl@55555", ... },
  "email":    { "smtp_username": "santosh@v2kart.com",
                "smtp_password": "vrl@1234",
                "from_address":  "santosh@v2kart.com", ... }
}
```

**Severity beyond `config.py` defaults**: anyone who clones this repo can:
- Connect to V2 Retail's SQL Server with `sa` privileges (every table, all data, RCE via xp_cmdshell if enabled)
- Sign in to Santosh's Office 365 mailbox (`santosh@v2kart.com`)

**Fix priority — TODAY**:
1. Rotate `sa` password and `santosh@v2kart.com` mailbox password.
2. `git rm` the file, add to `.gitignore`, commit, and force-push the history rewrite (or accept the leak is permanent).
3. The Settings UI that writes this file (`/settings/database/apply` per `frontend/src/services/api.js:248`) should write to a path **outside** the repo — `~/.ars/app_settings.json` or Azure Key Vault.
4. `config.py:25-35` `load_db_overrides()` reads `APP_SETTINGS_FILE` (resolved to `backend/app_settings.json`) — change the resolution to `os.environ.get("ARS_SETTINGS_FILE", "/etc/ars/app_settings.json")` and ensure the file is mounted as a secret in production.

Run `git log --all -- backend/app_settings.json` and assume every commit has been read by an adversary.

### 1.2 CRITICAL — `backend/.env.example` ships with real-looking passwords

```
DB_PASSWORD=vrl@55555
SUPER_ADMIN_PASSWORD=Admin@12345
```

`.env.example` should contain placeholders (`<set in production>`, or empty). The current file is indistinguishable from a real `.env` and copy-paste-deployed instances inherit the live password.

**Fix**: replace values with `<set in production>` or empty. Add a startup check in `main.py` that refuses to boot if `DB_PASSWORD == "vrl@55555"` or `SUPER_ADMIN_PASSWORD == "Admin@12345"` and `APP_ENV == "production"`.

### 1.3 HIGH — `scripts/test_alloc_determinism.py` hardcodes prod creds

Lines 17-23:
```python
os.environ['DB_USERNAME'] = 'sa'
os.environ['DB_PASSWORD'] = 'vrl@55555'
os.environ['DB_NAME']     = 'rep_data'
```

**Fix**: read from environment, fail fast if missing. The Excel reconciliation script I added (`backend/scripts/excel_reconciliation.py`) already follows this pattern — copy it.

### 1.4 HIGH — Snowflake stack is dead but still wired to 8 API endpoints

`backend/app/services/allocation/` (2,236 LOC: `engine.py`, `option_filler.py`, `snowflake_loader.py`, `article_scorer.py`, `budget_cascade.py`, `size_allocator.py`, `snowflake_client.py`) is the **original** Snowflake-based engine (the one Akash's Obsidian spec describes). It depends on `RESULTS.ARTICLE_SCORES` (576M scored pairs in Snowflake).

The Snowflake account `iafphkw-hh80816` was suspended for non-payment; every call to `/api/v1/allocation-engine/*` (8 endpoints, declared in `endpoints/allocation_engine.py`) currently returns `500 — Snowflake connection failed: 000666 (57014): Your account is suspended due to lack of payment method.`

**Decision needed (capture in NEXT_STEPS.md)**:
- (a) Reactivate Snowflake. Pay the bill, restore scores. Costs ongoing money to maintain a fallback engine.
- (b) Decommission. Delete `app/services/allocation/`, the 8 endpoints in `endpoints/allocation_engine.py`, and the dashboard at `static/allocation.html`. Net: −5K LOC and one less moving part. The SQL-Server pipeline (`/listing/generate`) is the production path anyway.

`OPTIMIZATION.md` doesn't address this directory at all.

### 1.5 HIGH — No rate limiting on long-running endpoints

`POST /api/v1/listing/generate` runs the full pipeline (5-10 minutes typical). The endpoint has no rate limiting, no concurrency limit per user, no idempotency key. Two consequences:

- **DoS surface**: a single misbehaving client (or attacker with a valid JWT) can fire 10 generates in parallel and the gunicorn worker pool is saturated (4 workers per process, B2 tier = 1 process). `frontend/src/services/api.js:328` sets a 600s timeout — clients will retry on perceived hang.
- **Duplicate work**: no idempotency means the same generate request from the same user/MAJ_CAT can run twice if the network blips. Pipeline writes to shared tables — concurrent writes are the source of the deadlocks `rule_engine_pandas.py` carefully retries.

**Fix**:
1. Add `slowapi` (`pip install slowapi`) and rate-limit `/listing/generate` to 1 in flight per user, 5 per hour.
2. Require an `Idempotency-Key` header. Reject duplicate keys with the in-flight job's status.
3. Use the existing `ARS_ALLOC_MAJCAT_QUEUE` table to detect "already running" — refuse to start a second `generate` while a previous one is `IN_PROGRESS`.

### 1.6 HIGH — Frontend has no React error boundaries

`frontend/src/App.jsx` lazy-loads 50+ pages. A single page crash (uncaught render error) takes down the whole app: white screen of death, user has to refresh and lose state.

**Fix**: wrap each route in an `ErrorBoundary` (or use `react-error-boundary`). Show a "Something broke. Refresh or contact admin. Error ID: <id>" panel that logs the error to a `/api/v1/frontend-errors` endpoint.

### 1.7 MEDIUM — Duplicate SQL migration numbers

```
backend/scripts/014_create_ars_msa_tables.sql
backend/scripts/014_create_contribution_tables.sql

backend/scripts/015_add_category_rls.sql
backend/scripts/015_create_sloc_settings.sql
```

Two scripts share each of `014` and `015`. Whoever runs them in lexicographic order gets one of them; whoever runs them by name picks arbitrarily. Migrations should be strictly monotonic. Renumber to `014a/014b/015a/015b` or merge them.

**Better**: adopt Alembic. The repo has SQLAlchemy already; Alembic generates from model changes. Add it as the next step after fixing the existing duplicates.

### 1.8 MEDIUM — Allocation-correctness observability is missing

`OPTIMIZATION.md §5.5` covers infrastructure observability (DB pool, pipeline duration, log aggregation). It says **nothing** about whether the allocation output is *correct*.

A planner running this in production has no way to know if today's run produced wrong numbers until either Santosh notices the dispatch list looks weird, or stores complain a week later.

**Add three monitoring artifacts:**

1. **Per-run health snapshot** (write to `ARS_ALLOC_HEALTH_HISTORY`):
   - Total OPTs, by `OPT_TYPE` (RL/TBC/TBL/MIX) — alert if MIX % > 30 % or TBL % > 50 %.
   - Per-MAJ_CAT fill rate (avg `ALLOC_QTY / OPT_REQ` for `OPT_TYPE != 'MIX'`) — alert if < 60 %.
   - DC pool consumption % per RDC — alert if any RDC < 20 % consumed (over-stocked) or > 95 % consumed (under-supplied).
   - Distribution of stores hitting `MJ_REQ` cap — alert if > 20 % of stores cap at < 50 % of base need.

2. **Reconciliation against last week**: per-MAJ_CAT, week-over-week shift in average `ALLOC_QTY` per store. Alert when shift > ±25 %.

3. **Excel-reference baseline**: keep one reference run per MAJ_CAT in a baselines table; the new `scripts/excel_reconciliation.py` becomes a recurring CI/CD job that compares the latest production run against the Excel ground truth and fails the deploy if drift exceeds tolerance.

### 1.9 MEDIUM — No backup / restore runbook

For a system that drives **physical stock movement to 320 stores**, there is no documented backup story. `deploy-azure.sh` creates the databases but never schedules backups. `frontend/src/services/api.js:251-254` exposes `createBackup` / `listBackups` / `deleteBackup` — but these run against the live DB instance, not a separate vault. If `Rep_data` is lost, you lose every allocation history.

**Fix**:
1. Enable Azure SQL Long-Term Retention (LTR) for `Rep_data` — weekly backups, 12-week retention, 1-month archive.
2. Schedule a weekly BACPAC export to a different region (`Azure Backup Vault`).
3. Document recovery time objective (RTO): how long until ARS is back if Azure SQL goes down? If > 8 hours, that's an outage during which planners revert to Excel.

### 1.10 MEDIUM — Missing 29-step ARS features (carry forward from `NEXT_STEPS.md`)

These are features in Akash's original Obsidian spec (`ARS 29-Step Algorithm.md`) that were never built. `OPTIMIZATION.md` doesn't address them because it's a code-quality review, not a spec review:

| Feature | Effort | Recommendation |
|---|---|---|
| Hero / Focus / Assorted list ingest | 1 wk | Build — `FOCUS_W_CAP` / `FOCUS_WO_CAP` columns already exist, just need data |
| Store-specific listing overrides (`ST_SPECIFIC=9999`) | 3-5 d | Build — high planner-value |
| Delivery Order output (Fresh Lorry-style file) | 1 wk | Build — this is the **literal output** the replenishment head uses |
| Two-DC routing (DH24/DW01) | 1 wk | Build — `RDC` field exists but no serving rules |
| Multi-option tagging (4-level cascade) | 2-3 wk | Defer — requires per-store article scoring; vestigial without §1.4 decision |
| Pipeline inventory (INT/PRD/STO via SAP) | 2 wk + SAP RFC | Defer |
| 12-month planning view | 2 wk | Defer |

---

## 2. Findings in `OPTIMIZATION.md` that are now stale

### 2.1 Rule-engine inventory is wrong

`OPTIMIZATION.md §3.1` lists `rule_engine.py (1808) + rule_engine_new.py (1086)` as the two competing engines. Reality on this branch:

- **Live default**: `rule_engine_pandas.py` (1,896 lines) — runs by default for `mode="pandas"` per `listing.py:2072`. Uses `ProcessPoolExecutor` per MAJ_CAT (correctly bypassing GIL since the hot loop is numpy/pandas).
- **Live fallback**: `rule_engine_new.py` (2,142 lines, not 1,086) — used when `mode="sequential"` per `listing.py:2090`.
- **Quarantined**: `rule_engine.py` and `listing_allocator.py` — moved to `_legacy/` on this branch.
- **Validation tools**: `rule_engine_parallel_python.py` (459) + `rule_engine_parallel_sql.py` (481) — used by `scripts/validate_alloc_modes.py` for benchmarking, **not** dead.
- **Server-side parallel SP**: `backend/sql/usp_ars_allocate_majcat.sql` (673) — orchestrated by `rule_engine_parallel_sql.py`. Sophisticated dynamic-SQL waterfall using `OPENJSON` and per-session `#nre_pool` temp tables.

The pandas engine is **better than `OPTIMIZATION.md` gives it credit for**. Its design notes at `rule_engine_pandas.py:50-58` correctly identify that pandas operations hold the GIL and that `ThreadPoolExecutor` would serialise them; it switches to `ProcessPoolExecutor` and pickles `DataFrame` slices to subprocesses. This is the right call for a CPU-bound numerical workload on Windows (no fork; spawn is mandatory). Future optimization should **layer on this**, not replace it.

### 2.2 CI workflow exists

`OPTIMIZATION.md §5.3` says ".github/ contains no workflows. Add a baseline." Reality:

`.github/workflows/deploy.yml` exists. It does:
1. `actions/setup-python@v5` with pip cache
2. `pip install -r requirements.txt`
3. **Smoke-validate imports**: `python -c "from app.core.config import get_settings; print('Config OK')"`
4. Deploy to Azure App Service
5. Build frontend with `npm ci && npm run build`
6. Deploy to Azure Static Web Apps

What's still missing (validity of the original recommendation stands):
- **No tests run.** The "Validate imports" step proves the module loads, not that the math is right. Add `python -m pytest backend/tests/` after the import smoke-check.
- **No lint.** Add `ruff check backend/`, `eslint frontend/src/`.
- **No security scan.** Add `gitleaks detect --source . --no-git`, `pip-audit`, `npm audit --omit=dev`.
- **No staging gate.** A push to `main` deploys straight to production. Add a manual approval gate after staging deploy.

### 2.3 Several listed file LOCs are outdated

| File | OPTIMIZATION.md | Actual now |
|---|---|---|
| `endpoints/listing.py` | 2,494 | **3,849** |
| `endpoints/contrib.py` | 1,706 | 1,706 (unchanged) |
| `endpoints/grid_builder.py` | 1,516 | 1,676 |
| `services/listing_allocator.py` | 2,134 | (moved to `_legacy/`) |
| `services/upsert_engine.py` | 1,251 | 1,314 |
| `services/rule_engine.py` | 1,808 | (moved to `_legacy/`) |
| `services/rule_engine_new.py` | 1,086 | **2,142** |

`listing.py` grew **~1,400 lines** since `OPTIMIZATION.md` was written — mostly Parts 8.4 (parked-history snapshot), 8.5 (final OPT_TYPE), and the parallel allocation orchestration. The file-split recommendation is now **more urgent**, not less.

---

## 3. Prioritised 90-day roadmap (builds on `OPTIMIZATION.md`'s 30-day plan)

### Days 1-7 — Stop the bleeding (additions to OPTIMIZATION.md Week 1)

1. **`git rm backend/app_settings.json`**, rotate every secret in it (sa password, Santosh email password). Force-push history rewrite or accept permanent leak.
2. **Replace passwords in `backend/.env.example` with placeholders.**
3. **Replace hardcoded creds in `scripts/test_alloc_determinism.py`** with env-var reads.
4. **Add startup guard** in `main.py` that refuses to boot if defaults are still in place AND `APP_ENV=production`.
5. **Pre-commit `gitleaks` hook** so this can't happen again.

### Days 8-21 — Correctness & decisions (parallel with OPTIMIZATION.md Week 2-3)

1. **Run Excel reconciliation for M_TEES_HS** (one MAJ_CAT, against the legacy 22-sheet xlsb). Use `backend/scripts/excel_reconciliation.py`. Decision gate: if drift > 5 units per OPT for > 5 % of OPTs, halt rollout and debug.
2. **Decide Snowflake** (§1.4). If decommissioning, that's a single PR — delete `app/services/allocation/` + 8 routes in `endpoints/allocation_engine.py` + the `static/allocation.html` dashboard tab.
3. **Add allocation-health snapshot** (§1.8 #1). One scheduled query, one alert table.
4. **Standardise long-job pattern** (`OPTIMIZATION.md §2.6`) — every long-running endpoint returns `{job_id, status}` immediately, frontend polls. Use existing `ARS_ALLOC_MAJCAT_QUEUE` as the model.
5. **Rate-limit `/listing/generate`** with `slowapi` (§1.5).

### Days 22-45 — Structure & coverage

1. **Split `endpoints/listing.py`** (now 3,849 LOC). Move the whole `generate()` body to `services/listing_pipeline/` with one module per Part. Endpoint becomes a 200-line orchestrator.
2. **Stand up `app/repositories/`** (`OPTIMIZATION.md §3.2`) — start with `ListingRepository`. Removes the f-string SQL flagged in §1.2.
3. **Migrate to Alembic** (cleans up the duplicate-numbered scripts in §1.7).
4. **Add CI test step** + ruff + gitleaks + pip-audit.
5. **Build the missing 29-step features** (§1.10): Hero/Focus ingest, store-specific overrides, Delivery Order output. These are the planner-visible gaps.

### Days 46-90 — Scale & ops

1. **Allocation-correctness CI gate** (§1.8 #3): the reconciliation harness becomes an integration test that runs nightly against the latest production run.
2. **React error boundaries** (§1.6).
3. **Backup/restore runbook** (§1.9): LTR enabled, BACPAC weekly cross-region.
4. **Async frontend with TanStack Query** (`OPTIMIZATION.md §4.3`).
5. **Move JWTs to `httpOnly` cookies** (`OPTIMIZATION.md §1.6`).
6. **Pin all dependencies** (`OPTIMIZATION.md §5.2`) and split prod/dev requirements.
7. **Deprecate the `vrl@55555` infrastructure entirely.** The on-prem `HOPC560` SQL Server with `sa` access is the historical permission model. Migrate to Azure SQL with managed identity + AAD auth, retire `sa`.

---

## 4. What I would NOT do (anti-recommendations)

A few things look like good ideas but aren't:

- **Don't rewrite the pandas engine** to async-IO or sync-SQL. The ProcessPool design at `rule_engine_pandas.py:50-58` is correct; the operations are CPU-bound on numpy. Async I/O wouldn't help.
- **Don't merge `rule_engine_pandas.py` and `rule_engine_new.py` into one.** They serve different deploy environments — pandas needs the workload to fit in memory per MAJ_CAT (works for V2 Retail's scale); sequential is the safe fallback for environments without enough RAM. Keeping both as named modes is correct.
- **Don't migrate to a microservice.** This is one logical workflow; a microservice split would just move complexity to the network. The right cut is service-layer extraction inside the monolith (`OPTIMIZATION.md §3.2`), not network boundaries.
- **Don't adopt `agrid-community` over `ag-grid-enterprise`** without confirming whether server-side row model and Excel export are actually used. `OPTIMIZATION.md §4.1` suggests this; verify usage before saving the licence cost — if `TableDataPage.jsx` uses Master/Detail or Server-Side Row Model, community can't replace it.

---

## 5. Reference: file:line index of additions in this file

| Severity | Category | File:Line |
|---|---|---|
| **CRITICAL** | Secrets in committed JSON | `backend/app_settings.json:7,17` |
| **CRITICAL** | `.env.example` ships real-looking creds | `backend/.env.example:13,45` |
| HIGH | Determinism test hardcodes prod creds | `backend/scripts/test_alloc_determinism.py:18-23` |
| HIGH | Snowflake stack dead but wired to live API | `backend/app/services/allocation/*` + `endpoints/allocation_engine.py` |
| HIGH | No rate limiting on long-job endpoints | `endpoints/listing.py:413` (`/listing/generate`) |
| HIGH | No React error boundaries | `frontend/src/App.jsx` |
| MEDIUM | Duplicate migration numbers | `backend/scripts/014_*.sql` (×2), `backend/scripts/015_*.sql` (×2) |
| MEDIUM | Allocation-correctness observability missing | (no file — needs to be built) |
| MEDIUM | Backup/restore runbook missing | (no file — needs to be built) |
| MEDIUM | 29-step features unbuilt: Hero/Focus, ST_SPECIFIC, DO output, two-DC | (carry forward from `NEXT_STEPS.md`) |
