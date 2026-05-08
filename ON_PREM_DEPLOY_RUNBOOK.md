# On-prem deploy runbook for Santosh

**Pivot decision (2026-05-08, Akash)**: Skip Azure for now. Run the new ARS code on V2's on-prem servers (HOPC560 / Rep_data) — the same path Santosh already maintains. The 503 on `ars-v2retail-api` will be cleaned up separately and is no longer urgent.

This runbook is everything Santosh needs to roll the umbrella PR work onto his on-prem instance.

---

## Step 1 — apply migrations on HOPC560

Run these on **HOPC560**, database **Rep_data**, as a user with `db_ddladmin` (or `sa`). All three are idempotent (`CREATE TABLE IF NOT EXISTS` semantics) — safe to re-run.

### Option A — SSMS
1. Open SSMS → connect to HOPC560 → expand `Rep_data`
2. File → Open → these three files in order, F5 each:
   ```
   backend/scripts/021_focus_list_table.sql
   backend/scripts/022_alloc_health_history.sql
   backend/scripts/023_st_specific_overrides.sql
   ```

### Option B — sqlcmd one-liner
From a machine that can reach HOPC560:
```cmd
cd backend\scripts
sqlcmd -S hopc560 -d Rep_data -U sa -P %SQL_SA_PASS% -i 021_focus_list_table.sql
sqlcmd -S hopc560 -d Rep_data -U sa -P %SQL_SA_PASS% -i 022_alloc_health_history.sql
sqlcmd -S hopc560 -d Rep_data -U sa -P %SQL_SA_PASS% -i 023_st_specific_overrides.sql
```

### Option C — V2 universal MCP
From any Claude session with V2 MCP enabled (`universal-mcp.akash-bab.workers.dev`):
```
v2_sql_query(db="Rep_data", sql="<paste contents of 021_*.sql>")
v2_sql_query(db="Rep_data", sql="<paste contents of 022_*.sql>")
v2_sql_query(db="Rep_data", sql="<paste contents of 023_*.sql>")
```
The tool runs on a Cloudflare Worker that already has HOPC560 access. No firewall manipulation needed.

### Verify (run after all three)
```sql
SELECT name FROM sys.objects
WHERE type='U' AND name IN
  ('Master_FOCUS_LIST','ARS_ALLOC_HEALTH_HISTORY','Master_ST_SPECIFIC')
ORDER BY name;
```
Expect 3 rows. If you see all three, migrations are applied.

---

## Step 2 — pull the new code

The umbrella branch is `tests/e2e-majcat` on `https://github.com/akash0631/ARS_V2.git` (public fork, no auth needed).

### From the existing on-prem deploy directory
```cmd
cd <wherever the on-prem ARS lives>
git remote add akash https://github.com/akash0631/ARS_V2.git
git fetch akash tests/e2e-majcat
git checkout akash/tests/e2e-majcat -- backend/
```

(If the on-prem repo doesn't track via git: clone fresh, then copy `backend/` over the existing install.)

### Install new dep
The umbrella adds **one** new pip package: `slowapi>=0.1.9`.
```cmd
cd backend
pip install -r requirements.txt
```
If `slowapi` install fails, the rate-limiter is soft-failing — the app still runs; it just won't enforce per-user rate limits on `/listing/generate`.

---

## Step 3 — restart the on-prem service

Whatever Santosh normally does. Likely one of:
- Windows Service: `Restart-Service ars-api` (or service name)
- Task scheduler: kill the python process, let it relaunch
- IIS: `iisreset` or recycle the app pool
- Manual: kill the running uvicorn / gunicorn, restart it

### Verify
```cmd
curl http://<on-prem-host>:<port>/health
```
Expect `{"status":"healthy"}` with `system_db: connected, data_db: connected`.

Then exercise one new endpoint to confirm the migrations + new code line up:
```cmd
curl http://<on-prem-host>:<port>/api/v1/focus-list
```
Should return `[]` (empty list, not 500).

---

## What's new in this code (so Santosh knows what to expect)

- **Delivery Order workbook** at `GET /api/v1/listing/parked-runs/{sid}/delivery-order?source=parked|history` — 6-sheet xlsx including SAP-friendly BDC_Format
- **Focus list** (Master_FOCUS_LIST) — 5 endpoints under `/api/v1/focus-list/*` for managing planner-curated articles forced into allocation
- **ST_SPECIFIC overrides** (Master_ST_SPECIFIC) — 5 endpoints under `/api/v1/st-specific/*` to pin articles to specific stores
- **MAJ_CAT fallback** — pipeline hook in `/listing/generate` (off by default, opt-in via `enable_majcat_fallback=True`)
- **Health snapshot** — per-run alert metrics at `/api/v1/listing/health-snapshots`
- **Rate limit** on `/listing/generate` (5/hr per user, env-tunable `ARS_GENERATE_RATE_PER_HOUR`)
- **Frontend ErrorBoundary** at top level
- **Removed** 8 always-500 Snowflake-backed `/allocation-engine/*` endpoints (3,800 LOC dead code)

Full per-feature breakdown: `HANDOVER_2026-05-07_SESSION.md` on this same branch.

---

## If something breaks

The repo `Aakash_sir` branch is the safe rollback point. From the on-prem deploy:
```cmd
git checkout akash/Aakash_sir -- backend/
pip install -r backend/requirements.txt
<restart service>
```
You can also rebuild a deploy zip from `Aakash_sir` using the script at `dev/rebuild_rollback_zip.py` (already on this branch) — produces a 3.7 MB zip in 5 seconds.

---

## What's still pending after this is done

- Frontend wiring for the new pages (Download DO button, Focus List, ST-Specific, Health snapshot dashboard) — endpoints all exist, just needs UI
- Excel reconciliation on M_TEES_HS — needs Harshal: HOPC560 access + 89 MB `.xlsb` saved as `.xlsx`
- Two-DC routing (deferred, ~1 wk)
- Multi-option tagging (deferred, 2-3 wk)
- Security: rotate `sa@HOPC560` and `santosh@v2kart.com` mailbox passwords (parking lot)

---

## Don't worry about

- The Azure app `ars-v2retail-api` returning 503. We're not using it. Roll back later when convenient (V2 MCP `azure_deploy_zip` with the rollback zip URL on this branch).
- The Azure SQL migrations (we already applied them on `ars-v2retail-sql/Rep_Data` during the failed Azure deploy attempt). They're harmless.
- The Azure SQL LTR policy we set yesterday. Harmless.
