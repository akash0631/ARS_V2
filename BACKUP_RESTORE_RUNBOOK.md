# ARS Backup & Restore Runbook

**Audience:** ops + DBA. Tells you exactly what to enable so we never lose `Rep_data`, and exactly what to do at 2 AM when something goes sideways.

**Owner:** the person whose pager goes off if a store can't be replenished tomorrow.

---

## Why this exists

ARS drives physical stock movement to 320+ stores. If `Rep_data` is corrupted or accidentally dropped:

- Today's allocation is unrecoverable → planners revert to Excel for ~24-48h
- All allocation history (`ARS_ALLOC_HISTORY`, `ARS_LISTING_WORKING_HISTORY`) is lost → no audit trail for already-dispatched DOs
- Master tables (`Master_ALC_INPUT_*`, `Master_FOCUS_LIST`, `Master_ST_SPECIFIC`, `Master_CONT_*`) need rebuilding from upstream sources or last upload

The repo has no documented backup story until now. `deploy-azure.sh` provisions the databases but never schedules backups. The Settings UI has `createBackup` / `listBackups` / `deleteBackup` endpoints but those run against the **same** SQL instance — a "backup" inside the same instance is not a backup.

This runbook closes that gap.

---

## Recovery objectives

| Metric | Target | Rationale |
|---|---|---|
| **RPO** (max acceptable data loss) | ≤ 1 hour | An allocation run takes ~10 min; losing more than the last hour means redoing today's work |
| **RTO** (max acceptable downtime) | ≤ 4 hours | One business day of allocation has Rs 50L+ of dispatch hanging on it |
| **Retention** | 12 months | Audit + planner trend-comparison need at least one full season cycle |

If you can't hit these, you don't have a backup — you have a hope.

---

## Setup checklist (one-time, do this BEFORE going live)

### 1. Enable Azure SQL Long-Term Retention (LTR) on `Rep_data`

```bash
RG=rg-ars-prod
SERVER=$(az sql server list -g $RG --query "[0].name" -o tsv)

# Weekly backups, kept 12 weeks; monthly backups kept 12 months;
# yearly backup kept 1 year. Change to your retention policy.
az sql db ltr-policy set \
  --resource-group $RG \
  --server $SERVER \
  --name Rep_data \
  --weekly-retention P12W \
  --monthly-retention P12M \
  --yearly-retention P1Y \
  --week-of-year 1
```

Same for `Claude` (RBAC + audit). If you cheap out anywhere it's here, but do not.

### 2. Configure short-term Point-In-Time Restore (PITR)

PITR is enabled by default on Azure SQL but **default retention is 7 days**. Bump to 35 days so a "we noticed yesterday's run was bad on Monday" rollback is survivable.

```bash
az sql db update \
  --resource-group $RG --server $SERVER --name Rep_data \
  --backup-storage-redundancy Geo \
  --read-scale Disabled

az sql db ltr-policy show -g $RG -s $SERVER -n Rep_data
```

`backup-storage-redundancy=Geo` means the backups themselves replicate to the paired region (Central India → South India). If Mumbai DC catches fire, your backups survive.

### 3. Schedule cross-region BACPAC export (paranoia tier)

LTR + PITR live inside Azure. If your subscription gets compromised or someone runs `az sql server delete`, LTR goes with it. A weekly BACPAC to a separate Storage Account in a separate subscription is the answer.

```bash
# Run weekly via Azure Automation / GitHub Actions cron / your scheduler.
ts=$(date +%Y%m%d)
az sql db export \
  --resource-group $RG \
  --server $SERVER \
  --name Rep_data \
  --admin-user "$SQL_ADMIN_USER" \
  --admin-password "$SQL_ADMIN_PASS" \
  --storage-key-type StorageAccessKey \
  --storage-key "$BACKUP_SA_KEY" \
  --storage-uri "https://$BACKUP_SA.blob.core.windows.net/ars-backups/Rep_data_${ts}.bacpac"
```

`$BACKUP_SA` should be in a different resource group, ideally a different subscription. The point is to be airgapped from anything `az ... --resource-group rg-ars-prod` can damage.

### 4. Test the restore — every quarter

A backup you've never restored is not a backup. Schedule:

```
Q1: full restore drill — restore last week's BACPAC into a sandbox DB,
    spot-check a known allocation run, time the whole thing
Q2: PITR drill — restore Rep_data to T-2 hours into a sandbox, query a
    known table, time it
Q3: LTR drill — restore from monthly LTR copy
Q4: cross-region failover drill (if applicable)
```

Document the actual minutes each drill takes. That's your real RTO. If it doesn't fit the target above, fix the gap before the next quarter.

### 5. Document what's NOT backed up

Things that live outside `Rep_data`:

| Thing | Where | How to recover |
|---|---|---|
| `app_settings.json` (creds) | App Service config | Re-enter from password vault |
| `.env` overrides | Azure Key Vault (after security branch merges) | Re-pull from Key Vault |
| Frontend build | ACR / Static Web Apps | Re-deploy from `main` |
| Cloudflare Workers (replen.v2retail.net etc.) | Cloudflare account | `wrangler deploy` from repo |
| GitHub repo itself | GitHub | Mirror to GitLab or self-hosted Gitea (cheap insurance) |

---

## Restore playbooks

### Playbook 1: "Yesterday's allocation was wrong, roll back to T-N hours"

**Trigger:** planner or stores notice today's dispatch has weird numbers.

```
1. STOP the running listing pipeline if any:
     POST /api/v1/listing/cancel-batch  body: {batch_id}
   or kill via Sessions page.

2. Identify the bad time window:
     - Look at ARS_ALLOC_HEALTH_HISTORY (the new health snapshot table).
       Any ALERT_HIGH_MIX / ALERT_HIGH_FALLBACK / ALERT_LOW_FILL row from
       a past run is a candidate.
     - Look at /api/v1/listing/alloc-history for what was approved when.

3. Determine restore target time T (e.g. "before the bad run started").

4. Restore Rep_data to a SANDBOX DB at T:
     az sql db restore \
       --dest-name Rep_data_restore_$ts \
       --edition Standard --service-objective S1 \
       --resource-group $RG --server $SERVER \
       --time "$T" \
       --name Rep_data

5. Spot-check the sandbox. Use SSMS or the API pointed at the sandbox
   to confirm the data looks right.

6. Cut over:
     - Rename current Rep_data → Rep_data_corrupted_$ts
     - Rename Rep_data_restore_$ts → Rep_data
     - Bounce the App Service so connections re-pin.

7. Re-run any critical allocation that was lost.

Total time: 30-60 min if you've practiced.
```

### Playbook 2: "Rep_data is corrupted / dropped / unavailable"

**Trigger:** `/health` returns `data_db: disconnected`, or queries return `Object name 'ARS_LISTING' is invalid`.

```
1. Confirm the database is actually gone vs just unreachable:
     az sql db show -g $RG -s $SERVER -n Rep_data
   If you get a NotFound, it's dropped. If you get a ServiceObjective
   listing, it's reachable but the schema is wrong inside.

2. If schema-corrupted: see Playbook 1.

3. If dropped: restore from LTR.
     # List available LTR backups
     az sql db ltr-backup list \
       -g $RG -l centralindia -s $SERVER --database Rep_data

     # Restore the latest into a NEW database
     az sql db ltr-backup restore \
       -g $RG -s $SERVER --dest-database Rep_data \
       --backup-id "<id from list above>"

4. Repoint App Service if needed (DB name didn't change → no repoint).
   Bounce App Service for a clean reconnect.

5. Lost data window: from the time of the latest LTR backup to T-now
   (could be days). The MSA / Grid / Listing tables get rebuilt from
   the next /listing/generate run. The HISTORY tables (ARS_ALLOC_HISTORY,
   ARS_LISTING_WORKING_HISTORY) are the irrecoverable bits — those are
   why we keep the LTR retention long.

Total time: 1-3 hours depending on DB size.
```

### Playbook 3: "Need to roll back ONE table, not the whole DB"

**Trigger:** an upload mangled `Master_ALC_INPUT_ST_MAJ_CAT` or someone DELETE'd `Master_FOCUS_LIST` rows by accident.

```
1. Restore Rep_data into a sandbox at T-before-mistake (Playbook 1 step 4).

2. Use sqlcmd / SSMS to copy the one table back:
     INSERT [target].dbo.<TABLE>
     SELECT * FROM [sandbox].dbo.<TABLE>
   or
     SELECT * INTO [target].dbo.<TABLE>_restored
     FROM [sandbox].dbo.<TABLE>
   then swap.

3. Drop the sandbox.

Total time: 15-30 min.
```

---

## What you should set up THIS WEEK

In priority order:

1. **Run the LTR command in §1** — 5 minutes, biggest single risk reduction.
2. **Bump PITR retention to 35 days (§2)** — 2 minutes.
3. **Set up the BACPAC cron (§3)** — 30 minutes; airgaps you against subscription-level disaster.
4. **Run a sandbox restore drill (§4 Q1)** — 1 hour; this is the moment you find out whether everything above actually works.
5. **Tell the rest of the team where this runbook lives** so it's not just in the lead's head.

Anything you don't do this week is an unhedged bet. Make sure you're aware which bets you're taking.

---

## Telemetry that should accompany this

When the system is live, the `ARS_ALLOC_HEALTH_HISTORY` snapshot (added in `feat(health-snapshot)`) gives you the per-run "is today broken?" signal — it's the early warning that you might need this runbook. Ensure ops have:

- `/api/v1/listing/health-snapshots` page bookmarked
- Alert routing for any row with `ALERT_HIGH_MIX = 1` or `ALERT_LOW_FILL = 1`
- Weekly review of the trend (mix% creeping up over weeks signals data quality drift before stores notice)

If you find yourself in this runbook, that monitoring failed to warn upstream — capture why in the post-mortem.
