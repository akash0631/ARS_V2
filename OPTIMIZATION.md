# ARS — Optimization & Improvement Guide

A code-level review of the V2 Retail ARS application (`backend/` FastAPI + `frontend/` Vite/React) with concrete, file-anchored recommendations.

> Review scope: ~18k LOC backend (Python/FastAPI/SQLAlchemy/pandas) + Vite/React frontend + docker-compose + Azure deploy script. Findings cite `file:line` so each recommendation is actionable.

---

## 0. TL;DR — Top 10 Fixes (in priority order)

| # | Issue | Location | Severity |
|---|---|---|---|
| 1 | Production DB password committed in source | `backend/app/core/config.py:25` | **CRITICAL** |
| 2 | Super-admin password committed in source | `backend/app/core/config.py:81` | **CRITICAL** |
| 3 | Weak default JWT secret | `backend/app/core/config.py:52` | **CRITICAL** |
| 4 | SQL/admin passwords committed in deploy script | `deploy-azure.sh:34, 39` | **CRITICAL** |
| 5 | F-string SQL with table/column names from input | `contrib.py:114-137`, `trends.py:392, 642`, `file_upload_service.py:342` | **HIGH** |
| 6 | RBAC missing on heavy endpoints | `listing.py:173, 313`, `contrib.py`, `grid_builder.py` | **HIGH** |
| 7 | Long jobs run synchronously, block HTTP worker | `listing.py:348-379`, `contrib.py` execute, `allocation_engine.py:82-100` | **HIGH** |
| 8 | Row-by-row `iterrows()` in hot paths | `allocation_engine.py:230-251`, `upsert_engine.py:538`, `msa_service.py:414-420` | **HIGH** |
| 9 | 1700-line and 2100-line monoliths | `listing.py:313-2070`, `services/listing_allocator.py` | MEDIUM |
| 10 | Tokens in `localStorage` (XSS exposure) | `frontend/src/store/authStore.js:18-20`, `services/api.js:18` | **HIGH** |

The four CRITICAL items (#1–#4) should be fixed today; rotate every secret that has been in git history.

---

## 1. Security

### 1.1 Hardcoded production secrets in source
- **`backend/app/core/config.py:25`** — `DB_PASSWORD: str = "vrl@55555"`
- **`backend/app/core/config.py:52`** — `JWT_SECRET_KEY: str = "your-super-secret-key-change-in-production-min-32-chars"`
- **`backend/app/core/config.py:81`** — `SUPER_ADMIN_PASSWORD: str = "Admin@12345"`
- **`deploy-azure.sh:34`** — `SQL_ADMIN_PASS="ArsStr0ng@Pass2026!"`
- **`deploy-azure.sh:39`** — `SUPER_ADMIN_PASS="Admin@Ars2026!"`

**Fix**
1. Rotate every secret. Anything in git history is compromised.
2. Replace defaults with `os.environ["..."]` (raise on missing) for production-required keys; keep `.env.example` only.
3. Move runtime secrets to Azure Key Vault and bind them to App Service via managed identity.
4. Add a `.gitignore` rule for `deployment-credentials.txt` (currently written by `deploy-azure.sh:367-397`).
5. Add a pre-commit `gitleaks` / `detect-secrets` hook to block future leaks.

### 1.2 SQL injection via f-strings
SQL is composed by string formatting in several places where the interpolated value originates outside the function:

- **`backend/app/api/v1/endpoints/contrib.py:114-137`** — DDL like `f"CREATE TABLE {PRESET_TABLE} ..."` and `f"INSERT INTO {PRESET_TABLE} ..."`.
- **`backend/app/api/v1/endpoints/trends.py:392, 642, 646, 830`** — `f"CREATE TABLE [{table_name}] ..."`, `f"SELECT COUNT(*) FROM [{table_name}] ..."`.
- **`backend/app/services/file_upload_service.py:342`** — `f"SELECT * FROM [{table_name}] WHERE {where_clause}"` where `where_clause` is user-built.
- **`backend/app/services/allocation_engine.py:315-320`** — `f"WHERE sale_date >= '{cutoff_date}' ..."`.

**Fix**
- For values: switch to `text(":param")` + `{"param": value}`.
- For identifiers (table/column names that *must* be variable): validate against a whitelist or look them up in `INFORMATION_SCHEMA` before substitution, and quote with `[]` only after validation.

### 1.3 RBAC gaps
Several heavy endpoints only require `get_current_user`, not a role/permission:

- **`backend/app/api/v1/endpoints/listing.py:173`** (`get_config`)
- **`backend/app/api/v1/endpoints/listing.py:313`** (`generate_listing` — runs the full pipeline)
- **`backend/app/api/v1/endpoints/contrib.py`** — preset CRUD + execute pipeline
- **`backend/app/api/v1/endpoints/grid_builder.py`** — grid execution endpoints

**Fix**: add `Depends(RequireRoles(["ADMIN","PLANNER"]))` (or the equivalent permission) on every mutating or compute-heavy endpoint. Add a unit test that asserts every router has at least one auth dependency.

### 1.4 JWT hardening
- **`backend/app/security/jwt_handler.py:14-21`** — no `jti` claim, no revocation list.
- **`backend/app/security/jwt_handler.py:38`** — single HS256 algorithm.
- **`backend/app/core/config.py:54-55`** — 8h access tokens with 7d non-rotating refresh tokens.

**Fix**
- Add `jti` and store revoked IDs in Redis (TTL = remaining validity).
- Move to RS256 with public/private keys for multi-service verification.
- Rotate refresh tokens on every use; invalidate the old one (refresh-token reuse detection).

### 1.5 CORS + nginx security headers
- **`backend/main.py:161-162`** — `allow_methods=["*"], allow_headers=["*"]` with `allow_credentials=True`. Tighten to the methods/headers actually used.
- **`frontend/Dockerfile`** + nginx config — no `X-Frame-Options`, `Content-Security-Policy`, `X-Content-Type-Options`. Add to `frontend/nginx.conf`.

### 1.6 Token storage
- **`frontend/src/store/authStore.js:18-20`** and **`frontend/src/services/api.js:18`** — JWTs in `localStorage`.

**Fix**: switch backend to set `httpOnly; Secure; SameSite=Strict` cookies; frontend stops touching the token. Adds CSRF concerns — pair with double-submit cookie or SameSite enforcement.

---

## 2. Performance — Backend Hot Paths

### 2.1 `iterrows()` and per-row Python loops
- **`backend/app/services/allocation_engine.py:230-251`** — triple-nested `iterrows()` over warehouse × stores × variants. Replace with a single `df.merge(...)` and vectorized arithmetic.
- **`backend/app/services/allocation_engine.py:251-282`** — store-weight loop. Vectorize: `stores_df["weight"] = stores_df["grade"].map(grade_ratios) * stores_df["size_factor"]`.
- **`backend/app/services/upsert_engine.py:538`** — building ORM objects row-by-row before `bulk_save_objects` at 554. Build them with a list comprehension or skip ORM and use `engine.execute(table.insert(), rows)`.
- **`backend/app/services/msa_service.py:414-420`** — `.replace()`/`.fillna()` per column. Single call: `df.fillna({col1: v1, col2: v2, ...})`.

### 2.2 Repeated DB round-trips
- **`backend/app/services/msa_service.py:727-739`** — pending-allocation lookup re-runs per store (320+ stores). Load once, filter in memory.
- **`backend/app/services/file_upload_service.py:342`** — `SELECT *` to test row existence. Use `SELECT TOP 1 1 ...`.
- **`backend/app/services/grid_calculations.py:156, 594`** — `SELECT * INTO #t` copies all columns; explicitly project the columns the next step uses.

### 2.3 Missing indexes / index timing
- **`backend/app/services/listing_allocator.py:163-192`** — INNER JOIN on `(RDC, MAJ_CAT, GEN_ART_NUMBER, CLR)` on `ARS_MSA_VAR_ART`. Add covering index `IX_msa_var_join` on those four columns.
- **`backend/app/services/listing_allocator.py:413-418`** — index created *after* `INSERT`. Fine for one-shot loads, but if this temp table is reused, build the index in the DDL.

### 2.4 Caching wins
- **`backend/app/services/msa_service.py:33-48`** — `get_available_columns()` is called from cascading dropdowns. Add `@lru_cache` (or a TTL cache invalidated on schema change).
- **`backend/app/services/grid_calculations.py:708-764`** — `_build_grid_layout()` parses `ARS_GRID_BUILDER` + `ARS_GRID_HIERARCHY` on every run. Cache the parsed layout per `(grid_id, version)`.

### 2.5 Connection pool
- **`backend/app/core/config.py:31-35`** — `DB_POOL_SIZE=15`, `DB_MAX_OVERFLOW=25`. With 20+ concurrent planners + a 4-thread pipeline pool, you can saturate the pool quickly. Bump to ~25/50 and watch `pool.checkedout()` in metrics.
- **`backend/app/database/session.py:176-186`** — `enable_rcsi()` opens raw connections without a context manager. Use `with engine.raw_connection() as conn:`.

### 2.6 Long jobs blocking the HTTP worker
- **`backend/app/api/v1/endpoints/listing.py:348-379`** — `ThreadPoolExecutor` runs full pipeline inside the request handler.
- **`backend/app/api/v1/endpoints/contrib.py`** execute endpoint — runs synchronously.
- **`backend/app/api/v1/endpoints/allocation_engine.py:82-100`** — uses `BackgroundTasks` only for multi-MAJCAT runs.

**Fix**: standardize on a job pattern. Return `{job_id, status}` immediately, run via `BackgroundTasks` or (better) a real worker (RQ / Arq / Celery + Redis). Frontend polls `/jobs/{id}`. Add an `Idempotency-Key` header to prevent duplicate submissions.

### 2.7 Async vs sync mixing
- **`backend/main.py:68-95`** — DB checks during startup are synchronous in `async` startup. Wrap with `await loop.run_in_executor(...)`.
- Most endpoints are `def`, not `async def`, so FastAPI runs them in a thread pool — that's safe but limits concurrency to thread-pool size. Either keep them all sync or use `databases`/SQLAlchemy 2.0 async with `asyncpg`/`aioodbc`.

### 2.8 Transaction boundaries
- **`backend/app/services/msa_service.py:338-620`** — reads `MASTER_ALC_PEND` mid-calculation with no isolation level set. A concurrent writer can produce a stale merge. Wrap the calc in a single transaction with `SNAPSHOT` isolation.
- **`backend/app/services/listing_allocator.py:107-125, 127-135`** — temp tables dropped at the end without `try/finally`. On exception, stale tables leak.
- **`backend/app/services/upsert_engine.py:155-159`** — bulk fast path silently falls back to chunked MERGE on failure. If the fast path partially committed, you double-insert. Verify the staging row count matches before committing.

---

## 3. Code Structure & Maintainability

### 3.1 Files that need to be split

| File | LOC | Suggested split |
|---|---|---|
| `backend/app/api/v1/endpoints/listing.py` | 2494 | Move `generate_listing` (1700+ lines) to `services/listing_service.py`; keep endpoint as thin orchestrator. |
| `backend/app/services/listing_allocator.py` | 2134 | 8 phases — pool, budget, eligibility, primary, fallback, dirty-recalc, reflect, finalize. Make each a module under `services/listing/`. |
| `backend/app/api/v1/endpoints/contrib.py` | 1706 | Extract `ContributionService` + `ContributionRepository`. |
| `backend/app/api/v1/endpoints/grid_builder.py` | 1516 | Extract `GridService`. |
| `backend/app/services/rule_engine.py` (1808) + `rule_engine_new.py` (1086) | — | Pick one. Delete the other or move it to `legacy/`. Two parallel rule engines is a bug magnet. |
| `backend/app/services/upsert_engine.py` | 1251 | Split staging vs MERGE vs validation. |
| `backend/app/api/v1/endpoints/msa_stock.py` | 1210 | Extract MSA stock domain into a service. |
| `backend/app/services/grid_calculations.py` | 1139 | Split MAJCAT and article calculators. |

### 3.2 Empty repository layer
**`backend/app/repositories/__init__.py`** is empty. Endpoints currently issue raw SQL. Recommended target structure:

```
endpoint  → service (business rules) → repository (data access) → SQL
```

Start with `ListingRepository`, `MSARepository`, `GridRepository`, `ContribRepository`. Doing this also makes services unit-testable without a live DB.

### 3.3 Dead and debug code
- **`backend/app/services/msa_service.py:465, 487, 495, 503, 508`** — `print("====...====")` left in. Convert to `logger.debug(...)`.
- **`backend/app/services/allocation_engine.py:659`** — TODO stub `execute_allocation()`. Either implement or `raise NotImplementedError`.
- **`frontend/src/pages/TrendReviewPage.jsx.bak`** — delete from version control.

### 3.4 Pydantic validation gaps
- **`backend/app/api/v1/endpoints/listing.py:65-104`** — `GenerateRequest` has no numeric bounds (`stock_threshold_pct`, `excess_multiplier`, `age_threshold`). Add `field_validator` with sensible ranges.
- **`backend/app/api/v1/endpoints/msa_stock.py:128-132`** — `date` and `filters` are raw strings. Validate format / parse JSON into a Pydantic submodel.
- **`backend/app/api/v1/endpoints/listing.py:2077-2089`** — pagination has no `page_size` upper bound. Add `Query(..., ge=1, le=1000)`.

### 3.5 Inconsistent error handling
Raise patterns vary across `listing.py:392, 400, 402, 2062`. Define a single `APIError` schema and a global `app.add_exception_handler(APIError, ...)`. Replace ad-hoc `HTTPException(...)` calls.

---

## 4. Frontend

### 4.1 Bundle size and code splitting
- **`frontend/src/App.jsx:10-44`** — pages are lazy-loaded (good).
- Large pages still ship as single chunks: `pages/ListingPage.jsx` (1040 LOC), `pages/GridBuilderPage.jsx` (864 LOC), `pages/TableDataPage.jsx` (445 LOC).
  - Extract inline helpers (`SearchSelect`, `KpiTile`, `ChartCard` in `ListingPage.jsx:14-169`) into `components/`.
  - Lazy-load modals: `GridModal`, `RunResultsModal` in `GridBuilderPage.jsx:317-355`.
- `vite.config.js:20-29` defines manual chunks; split heavy libs (`ag-grid-enterprise`, `recharts`) into their own chunks; only import recharts where rendered.
- Verify `ag-grid-enterprise` license is actually needed; community version saves ~1 MB.

### 4.2 React perf
- **`frontend/src/pages/ListingPage.jsx:497-511`** — `optTypeChartData`, `allocChartData`, `topMajCats` rebuild on every render. Wrap in `useMemo`.
- **`frontend/src/pages/TableDataPage.jsx:54`** — `useCallback` reads `filterTimer.current` but doesn't list it in deps; risk of stale closure. Move debounce to `useRef` + `useEffect` cleanup.
- **`frontend/src/App.jsx:92-94`** — `useEffect` calls `fetchUser()` only when `isAuthenticated` is initially true. Add `[isAuthenticated]` to the dep array so it re-runs on login.

### 4.3 API layer
- **`frontend/src/services/api.js`** — no retry, no request dedup, no global cancellation.
  - Add `axios-retry` for 5xx + network errors with exponential backoff.
  - Wrap `useFetch` (`hooks/useFetch.js:19-46`) with `AbortController` cleanup on unmount.
  - For read-mostly pages, swap to TanStack Query (`@tanstack/react-query`) — gives caching, dedup, retries, refocus refetch out of the box.
- **`frontend/src/services/api.js:24-52`** — refresh interceptor relies on a refresh token in `localStorage`; combine with §1.6 fix (httpOnly cookies).

---

## 5. Infrastructure & Ops

### 5.1 Docker
- **`docker-compose.yml:25-36`** — frontend has no `healthcheck`; add one hitting nginx `/`.
- No `deploy.resources.limits` on either service — set CPU + memory limits.
- **`backend/Dockerfile`** — verify multi-stage (deps layer + slim runtime).
- **`frontend/Dockerfile`** — confirm `npm ci --omit=dev`; reference a hardened `nginx.conf` with security headers.

### 5.2 Dependencies
- **`backend/requirements.txt`** — uses `>=` everywhere except passlib/bcrypt. Pin exact versions (`pip-tools` or `uv pip compile --generate-hashes`) for reproducibility.
- Split prod vs dev: `requirements.txt` and `requirements-dev.txt` (pytest, ruff, etc.).
- Add `pip-audit` / `safety` in CI.

### 5.3 CI/CD
`.github/` contains no workflows. Add a baseline:
1. `lint`: `ruff` + `black --check` (backend), `eslint` + `tsc --noEmit` (frontend).
2. `test`: `pytest` with a SQL Server testcontainer or sqlite fallback.
3. `security`: `gitleaks`, `pip-audit`, `npm audit --omit=dev`.
4. `build`: docker build both images, push to ACR.
5. `deploy`: gated manual approval to staging then prod.

### 5.4 Deploy script
- **`deploy-azure.sh`** — uses `set -e` (good) but writes plaintext credentials to `deployment-credentials.txt` (lines 367-397). Replace with Key Vault references and remove the file write.
- Hardcoded passwords in `deploy-azure.sh:34, 39` should be required env vars: `: "${SQL_ADMIN_PASS:?must be set}"`.

### 5.5 Observability
- Add structured JSON logging (`structlog`) so Azure Log Analytics queries are useful.
- Emit metrics for: pool checkout count, pipeline phase durations, MERGE row counts, MSA calc duration per MAJCAT. Prometheus or Application Insights.
- Add a `/metrics` endpoint and an Azure Monitor alert for `db_pool_exhausted` and `pipeline_duration_p95`.

---

## 6. Suggested 30-day roadmap

**Week 1 — Stop the bleeding**
- Rotate every committed credential. Move all secrets to env / Key Vault.
- Add `gitleaks` pre-commit hook.
- Tighten CORS in `main.py:161-162`.
- Add RBAC to `listing.py:313`, `contrib.py` execute, `grid_builder.py` runs.

**Week 2 — Correctness**
- Parameterize remaining f-string SQL (`contrib.py`, `trends.py`, `file_upload_service.py`, `allocation_engine.py:315`).
- Wrap MSA calc in transaction; fix temp-table cleanup with `try/finally`.
- Validate bulk-upsert row counts before commit.

**Week 3 — Performance**
- Vectorize the four `iterrows()` hot paths.
- Convert long jobs to background pattern; add `Idempotency-Key`.
- Add the missing `IX_msa_var_join` index; cache grid layout.

**Week 4 — Structure**
- Stand up `app/repositories/` with `ListingRepository` first.
- Split `listing.py:313` and `services/listing_allocator.py` into a sub-package.
- Pick one of `rule_engine.py` / `rule_engine_new.py`; delete the other.
- Add CI workflow.

---

## Appendix A — Findings index (for quick lookup)

| Severity | Category | File:Line |
|---|---|---|
| CRITICAL | Secret in code | `backend/app/core/config.py:25` |
| CRITICAL | Secret in code | `backend/app/core/config.py:52` |
| CRITICAL | Secret in code | `backend/app/core/config.py:81` |
| CRITICAL | Secret in code | `deploy-azure.sh:34` |
| CRITICAL | Secret in code | `deploy-azure.sh:39` |
| HIGH | SQL injection | `backend/app/api/v1/endpoints/contrib.py:114-137` |
| HIGH | SQL injection | `backend/app/api/v1/endpoints/trends.py:392, 642, 646, 830` |
| HIGH | SQL injection | `backend/app/services/file_upload_service.py:342` |
| HIGH | SQL injection | `backend/app/services/allocation_engine.py:315-320` |
| HIGH | RBAC missing | `backend/app/api/v1/endpoints/listing.py:173, 313` |
| HIGH | XSS exposure | `frontend/src/store/authStore.js:18-20`, `frontend/src/services/api.js:18` |
| HIGH | Sync long-job | `backend/app/api/v1/endpoints/listing.py:348-379` |
| HIGH | iterrows hot path | `backend/app/services/allocation_engine.py:230-251` |
| HIGH | iterrows hot path | `backend/app/services/upsert_engine.py:538` |
| HIGH | Bulk fast-path silent fallback | `backend/app/services/upsert_engine.py:155-159` |
| HIGH | Missing transaction | `backend/app/services/msa_service.py:338-620` |
| MEDIUM | CORS too open | `backend/main.py:161-162` |
| MEDIUM | Pool sizing | `backend/app/core/config.py:31-35` |
| MEDIUM | Cache missing | `backend/app/services/msa_service.py:33-48` |
| MEDIUM | Cache missing | `backend/app/services/grid_calculations.py:708-764` |
| MEDIUM | SELECT * | `backend/app/services/grid_calculations.py:156, 594` |
| MEDIUM | Missing index | `backend/app/services/listing_allocator.py:163-192` |
| MEDIUM | Empty repository layer | `backend/app/repositories/__init__.py` |
| MEDIUM | Pydantic bounds | `backend/app/api/v1/endpoints/listing.py:65-104` |
| MEDIUM | Pagination cap | `backend/app/api/v1/endpoints/listing.py:2077-2089` |
| MEDIUM | Refactor | `backend/app/services/listing_allocator.py` (2134 LOC) |
| MEDIUM | Refactor | `backend/app/api/v1/endpoints/listing.py` (2494 LOC) |
| MEDIUM | Duplicated rule engines | `services/rule_engine.py` vs `services/rule_engine_new.py` |
| MEDIUM | useMemo missing | `frontend/src/pages/ListingPage.jsx:497-511` |
| MEDIUM | Stale closure | `frontend/src/pages/TableDataPage.jsx:54` |
| MEDIUM | useEffect deps | `frontend/src/App.jsx:92-94` |
| MEDIUM | No CI workflow | `.github/` |
| MEDIUM | Loose deps pinning | `backend/requirements.txt` |
| LOW | Debug prints | `backend/app/services/msa_service.py:465, 487, 495, 503, 508` |
| LOW | Stub | `backend/app/services/allocation_engine.py:659` |
| LOW | Backup file in repo | `frontend/src/pages/TrendReviewPage.jsx.bak` |
