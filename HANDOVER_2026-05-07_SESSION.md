# Session Handover — 2026-05-07

Status: **prod app `ars-v2retail-api` is currently 503**. Migrations + LTR succeeded; deploy from `tests/e2e-majcat` tip caused a startup failure. Rollback zip is built locally but could not be uploaded to GitHub before the gh auth token in the local keyring went stale.

This document is everything that changed in this session, in priority order for the developer picking it up.

---

## 1. URGENT — restore prod

The deployed app is returning 503 "Application Error". Two equally good rollback paths:

### Option A — Azure portal (browser)
1. Portal → `ars-v2retail-api` → Deployment Center → Logs (or Deployments)
2. Find the most recent deployment **before** `deploy-prod-20260507-101742` (it had author "akash" and note mentioning "tests/e2e-majcat tip")
3. Click "Redeploy" on the prior entry

### Option B — re-deploy Aakash_sir tip via V2 MCP
The rollback zip already exists locally:
```
C:\Users\akash.agarwal\ars-rollback.zip       (3,734,604 bytes)
C:\Users\akash.agarwal\ars-deploy.zip         (the broken zip — for reference, do NOT redeploy)
```
Steps:
1. Re-authenticate: `gh auth login -h github.com -p https`
2. Upload the rollback zip as a release asset:
   ```
   gh release create rollback-aakash-sir-v1 \
     C:\Users\akash.agarwal\ars-rollback.zip \
     --repo akash0631/ARS_V2 \
     --target master \
     --title "ROLLBACK to Aakash_sir tip"
   ```
3. Get the asset URL:
   ```
   gh release view rollback-aakash-sir-v1 \
     --repo akash0631/ARS_V2 \
     --json assets --jq '.assets[0].url'
   ```
4. Call V2 MCP `azure_deploy_zip` with that URL (or use the curl ZIP-deploy path in the repo `CLAUDE.md`).
5. Verify: `curl https://ars-v2retail-api.azurewebsites.net/health` returns 200 with `{"status":"healthy"}`

---

## 2. What was deployed (and broke)

**Source**: `tests/e2e-majcat` tip on `harshalanand/ARS_V2` — 22 commits ahead of `Aakash_sir`. This was the umbrella of an extensive review + functional pass that has **206/206 tests passing locally in 24s**.

**Not yet diagnosed**: why startup fails on Azure. Possibilities to check (logs not retrievable from this machine due to local proxy issues):
- New `slowapi>=0.1.9` dependency in `requirements.txt` may have a transitive incompatibility with the Python version on App Service
- Pipeline hook in `/listing/generate` Part 8.3 (MAJ_CAT fallback) imports something that fails on cold start
- `app.middleware.rate_limit` instantiation
- Static file references that no longer exist after the Snowflake decommission removed `static/allocation.html`

Suggested first step after rollback: `az webapp log tail --name ars-v2retail-api --resource-group rg-ars-prod` to see the actual stack trace, OR Kudu's `/api/logs/docker` endpoint.

---

## 3. What succeeded in prod

These are **already live** on `ars-v2retail-sql.database.windows.net`, database `Rep_Data`. They are additive (CREATE TABLE IF NOT EXISTS / set policy) — safe to leave in place even with the rollback. They will work once the new code is re-deployed correctly.

| Action | Verified |
|---|---|
| `Master_FOCUS_LIST` table created (migration 021) | Yes (`SELECT 1 FROM sys.objects WHERE name='Master_FOCUS_LIST'` returned 1) |
| `ARS_ALLOC_HEALTH_HISTORY` table created (migration 022) | Yes |
| `Master_ST_SPECIFIC` table created (migration 023) | Yes |
| LTR policy: 12W weekly / 12M monthly / 1Y yearly, week-of-year=1 | Yes (`az sql db ltr-policy show`) |
| Firewall rule `AllowAllWindowsAzureIps` (`0.0.0.0`–`0.0.0.0`) | Yes (added during this session for GH-runner connectivity) |

---

## 4. GitHub repos and branches

### Parent: `harshalanand/ARS_V2`
- **Untouched at the branch level.** `Aakash_sir` and `master` are unchanged.
- One **draft PR** open: [#1](https://github.com/harshalanand/ARS_V2/pull/1) — `tests/e2e-majcat` (akash0631 fork) → `Aakash_sir`. Cannot merge in draft state.

### Fork: `akash0631/ARS_V2` (new this session)
- 11 stacked feature branches pushed
- 1 infra branch (`infra/gh-actions-runbook`) — not part of the umbrella PR
- 1 rollback branch (`infra/rollback-zip`) — **created locally only, push failed.** The zip is at `~/ars-rollback.zip` if needed.
- `master` has the infra-runbook workflow file (pushed via Contents API)
- 1 release: `deploy-prod-20260507-101742` — contains the **bad** zip; do not redeploy

### Branch tree (commits)
```
Aakash_sir (Harshal's review base — UNTOUCHED)
└─ review/cleanup-and-tests                   (6 commits)
   ├─ security/credential-hardening           (5 commits) — PARKED
   └─ functionality/delivery-order-output     (3 commits)
      └─ functionality/focus-list-ingest      (4 commits)
         └─ cleanup/snowflake-decommission    (2 commits)
            └─ functionality/majcat-fallback           (1 commit)
               └─ functionality/health-snapshot         (1 commit)
                  └─ functionality/st-specific-overrides (1 commit)
                     └─ functionality/rate-limit-idempotency (1 commit)
                        └─ functionality/react-error-boundaries (1 commit)
                           └─ docs/backup-restore-runbook (1 commit)
                              └─ tests/e2e-majcat       (2 commits)  ← the deploy source
```

Detailed per-branch breakdown is in `v2retail/ARS Review Handover 2026-05-07.md` in the Obsidian vault.

---

## 5. GitHub Actions workflows added (fork only)

`.github/workflows/infra-runbook.yml` (on fork's `master`):
- Manual-trigger only (`workflow_dispatch`)
- `prod` environment with required reviewer (akash0631)
- Two modes: `dry_run` (read-only verify) and `migrate` (applies 021/022/023)
- Uses `pymssql` (no ODBC driver install)
- Reads `SQL_ADMIN_PASSWORD` secret
- Run history:
  - run 25489306518 — `dry_run` — succeeded — verified connection to Rep_Data, 7 Master_ALC_INPUT_* present, 0 target tables
  - run 25489492172 — `migrate` — succeeded — all three tables created and verified

`.github/workflows/deploy.yml` is **untouched** (Harshal's existing Deploy ARS workflow).

---

## 6. Secrets and env on `akash0631/ARS_V2` fork

| Type | Name | Purpose | Notes |
|---|---|---|---|
| Secret | `SQL_ADMIN_PASSWORD` | Azure SQL admin password for `arsadmin` | Set this session. Value is the same as the deployed app's `DB_PASSWORD` env var. |
| Environment | `prod` | Approval gate on infra-runbook jobs | Required reviewer: akash0631 |

`AZURE_WEBAPP_PUBLISH_PROFILE` was attempted but the local Azure CLI was blocked by a TLS proxy when fetching it. **Not set.** Setting it is the prerequisite for using the existing `deploy.yml` workflow.

---

## 7. Files added this session in the repo

```
.github/workflows/
  infra-runbook.yml             (NEW, on infra/gh-actions-runbook branch + fork master)

INFRA_RUNBOOK_SETUP.md          (NEW, on infra/gh-actions-runbook branch + fork master)
HANDOVER_2026-05-07_SESSION.md  (NEW, this file)
ars-rollback.zip                (LOCAL ONLY, 3.7MB, on infra/rollback-zip branch — push failed)
```

Local-only artifacts (not in any repo):
```
C:\Users\akash.agarwal\ars-deploy.zip     (broken deploy bytes — for forensics)
C:\Users\akash.agarwal\ars-rollback.zip   (Aakash_sir tip — deploy this to restore)
```

---

## 8. Network gotchas hit this session

- Local machine is behind a TLS-intercepting proxy on some endpoints. Symptoms: `[SSL: WRONG_VERSION_NUMBER]` for Azure mgmt API on some calls, `schannel: SEC_E_INVALID_TOKEN` for git push intermittently, `http: server gave HTTP response to HTTPS client` for GitHub API calls. Endpoints unaffected: GitHub via gh CLI most of the time, V2 universal MCP worker on Cloudflare, Azure CLI for some calls (LTR policy worked, publish profile didn't).
- HOPC560 LAN (192.168.149.248:1433) was unreachable throughout the session — likely VPN-dependent and the dev VPN was off.
- The gh auth token in keyring went stale near end of session. Fix: `gh auth login -h github.com -p https`.

---

## 9. Pending — same priority order as the original handover

1. **Restore prod (above).**
2. **Push `security/credential-hardening`** — 5 commits, parked. Includes startup guard refusing prod boot with default secrets, gitleaks pre-commit. Branch is on the fork already.
3. **Frontend wiring** — endpoints all live (after rollback is fixed): "Download DO" button, Focus List page, ST-Specific page, Health snapshot dashboard panel. Code in `frontend/src/services/api.js` already exposes `focusListAPI`, `stSpecificAPI`, `healthSnapshots`, `downloadDeliveryOrder`.
4. **Excel reconciliation on M_TEES_HS** — needs HOPC560 access + 89MB `.xlsb` saved as `.xlsx`. Harness exists at `backend/scripts/excel_reconciliation.py` since 2026-05-06.
5. **Rotate `sa@HOPC560` SQL password** and **`santosh@v2kart.com` mailbox** — security parking lot.

Deferred features (still-unbuilt, deferred until reconciliation passes):
- Two-DC routing (1 wk) — `RDC` field exists, `majcat_fallback.run_fallback_for_session` already accepts a `store_rdc_map` parameter
- Multi-option tagging (2-3 wk)
- Pipeline inventory (2 wk + SAP RFC)
- 12-month planning view (2 wk)

---

## 10. How the developer should verify the umbrella PR

```bash
git clone https://github.com/akash0631/ARS_V2.git
cd ARS_V2
git checkout tests/e2e-majcat
cd backend
python -m pytest tests/ -v
```
Expect: **206 passed in ~24s**. Three layers: unit (×8 files) / e2e small / e2e production-scale (320 stores × 20 articles × 3 colors × 4 sizes ≈ 50K alloc rows, runs in 20s).

Live-DB integration tests are at `scripts/test_alloc_determinism.py` and need HOPC560.
