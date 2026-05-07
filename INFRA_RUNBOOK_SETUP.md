# Infra Runbook — GitHub Actions setup

One-time setup for the manual `Infra Runbook (manual)` workflow at `.github/workflows/infra-runbook.yml`. Use this when the operator's local machine cannot reach Azure / the prod SQL server.

The workflow does **only** what you tell it via the dropdown — `dry_run` is the default and is read-only.

## What needs to be configured (on the fork: `akash0631/ARS_V2`)

### Repository secret (Settings → Secrets and variables → Actions → Secrets)

| Name | Value | Source |
|---|---|---|
| `SQL_ADMIN_PASSWORD` | Azure SQL admin password for `arsadmin` | The `DB_PASSWORD` app setting on `ars-v2retail-api` |

### Azure SQL firewall

The runner connects from a GitHub-hosted IP, so Azure SQL must accept it. Either:
- **(Recommended)** Toggle ON: Azure portal → `ars-v2retail-sql` → Networking → "Allow Azure services and resources to access this server"
- OR add a permanent firewall rule for the runner's static range (less common for hosted runners)

### Environment (recommended — Settings → Environments → New environment)

Create an environment named **`prod`** and add at least one required reviewer. Every job in `infra-runbook.yml` uses `environment: prod`, so each dispatch will pause for explicit approval before any prod action runs.

## How to use it

1. Go to **Actions** tab on `akash0631/ARS_V2`
2. Pick **Infra Runbook (manual)** in the left sidebar
3. Click **Run workflow**
4. Branch: `infra/gh-actions-runbook`
5. Mode:
   - `dry_run` — connects, lists target tables and master inputs, no writes
   - `migrate` — applies 021/022/023 (idempotent `CREATE TABLE IF NOT EXISTS`)
6. SQL DB: defaults to `Rep_Data` (capital D, matches the prod DB on `ars-v2retail-sql`).
7. Click **Run workflow**. Approve at the `prod` environment gate.

LTR: do this once via Azure portal → `ars-v2retail-sql/Rep_Data` → Backups → Retention policies → set Weekly=12W, Monthly=12M, Yearly=1Y, Week-of-year=1.

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
