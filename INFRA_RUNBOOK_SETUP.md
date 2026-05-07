# Infra Runbook — GitHub Actions setup

One-time setup for the manual `Infra Runbook (manual)` workflow at `.github/workflows/infra-runbook.yml`. Use this when the operator's local machine cannot reach Azure / the prod SQL server.

The workflow does **only** what you tell it via the dropdown — `dry_run` is the default and is read-only.

## What needs to be configured (on the fork: `akash0631/ARS_V2`)

### Repository secrets (Settings → Secrets and variables → Actions → Secrets)

| Name | Value | Where it comes from |
|---|---|---|
| `AZURE_CREDENTIALS` | Service Principal JSON (see format below) | `az ad sp create-for-rbac` output |
| `SQL_ADMIN_PASSWORD` | Azure SQL admin password | Repo CLAUDE.md (`SQL_PASS_IN_ENV`) or Azure portal |

`AZURE_CREDENTIALS` format (one line in the secret value):
```json
{"clientId":"<sp-app-id>","clientSecret":"<sp-secret>","subscriptionId":"7c2e7784-61b3-4aa7-9967-f41b381406dd","tenantId":"3eb968d0-bf19-40f9-b191-f3186ac38f02"}
```

The SP needs `Contributor` (or narrower: `SQL Server Contributor` + `SQL DB Contributor`) on `rg-ars-prod`.

### Repository variables (Settings → Secrets and variables → Actions → Variables)

| Name | Value |
|---|---|
| `SQL_RG` | `rg-ars-prod` |
| `SQL_SERVER` | `ars-v2retail-sql` |
| `SQL_USER` | `arsadmin` |

### Environment (recommended — Settings → Environments → New environment)

Create an environment named **`prod`** and add at least one required reviewer. Every job in `infra-runbook.yml` uses `environment: prod`, so each dispatch will pause for explicit approval before any prod action runs.

## How to use it

1. Go to **Actions** tab on `akash0631/ARS_V2`
2. Pick **Infra Runbook (manual)** in the left sidebar
3. Click **Run workflow**
4. Branch: `infra/gh-actions-runbook`
5. Mode: choose one
   - `dry_run` — connects, lists target tables and master inputs, no writes
   - `migrate` — applies 021/022/023 (idempotent `CREATE TABLE IF NOT EXISTS`)
   - `ltr` — sets Long-Term Retention to 12W / 12M / 1Y
   - `migrate_and_ltr` — both, in order
6. SQL DB: defaults to `Rep_data`. Override if the deployed app's database name differs.
7. Click **Run workflow**. Approve at the `prod` environment gate.

## Safety guarantees

- All firewall rules are scoped to the runner IP and named `ghrun-<run_id>`. Removed in `if: always()` cleanup steps so a failed run doesn't leave the rule behind.
- Migrations are idempotent — re-running is a no-op.
- LTR policy is also a set-and-show — no destructive change.
- Workflow only runs on `workflow_dispatch`. No automatic triggers.
- Existing `deploy.yml` is untouched.
- Lives on its own branch (`infra/gh-actions-runbook`) on the fork. Not part of the umbrella review PR.

## What this does NOT do

- Does not run on HOPC560 (the on-prem SAP-fed server). Those tables exist there separately; this workflow targets the deployed Azure SQL only.
- Does not deploy code. Use the existing `Deploy ARS` workflow (`deploy.yml`) for that.
- Does not modify any `.env`, `app_settings.json`, or other config files.
