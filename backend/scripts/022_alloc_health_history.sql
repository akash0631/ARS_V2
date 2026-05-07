-- ============================================================================
-- 022_alloc_health_history.sql
-- ARS_ALLOC_HEALTH_HISTORY — per-run snapshot of allocation correctness
-- metrics. Lets planners and ops see at-a-glance whether today's run is
-- structurally OK before approving it for dispatch.
--
-- Run on Rep_data. Idempotent.
--
-- Captured by app/services/alloc_health.py at the end of /listing/generate
-- (Part 8.7) and queryable via /api/v1/listing/health-snapshots.
-- ============================================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'dbo.ARS_ALLOC_HEALTH_HISTORY') AND type = 'U'
)
BEGIN
    CREATE TABLE dbo.ARS_ALLOC_HEALTH_HISTORY (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        SESSION_ID          NVARCHAR(100) NOT NULL,
        RUN_AT              DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),

        -- Top-line totals
        TOTAL_OPTS          INT      NULL,
        TOTAL_SHIP_QTY      FLOAT    NULL,
        TOTAL_HOLD_QTY      FLOAT    NULL,
        STORES_TOUCHED      INT      NULL,
        MAJCATS_TOUCHED     INT      NULL,

        -- Mix by classification (% of total OPTs)
        PCT_RL              FLOAT    NULL,  -- expect 50-70% in steady state
        PCT_TBC              FLOAT    NULL,  -- expect 10-25%
        PCT_TBL             FLOAT    NULL,  -- expect 5-15%
        PCT_MIX             FLOAT    NULL,  -- alert if > 30%

        -- Fill rate (avg ALLOC_QTY / OPT_REQ for non-MIX rows)
        AVG_FILL_RATE_PCT   FLOAT    NULL,  -- alert if < 60%

        -- Fallback usage
        FALLBACK_FILLS      INT      NULL,  -- count of MAJ_CAT_FALLBACK rows
        FALLBACK_QTY        FLOAT    NULL,
        FALLBACK_PCT        FLOAT    NULL,  -- alert if > 30% of total ship

        -- Pool consumption (per-RDC, JSON for flexibility)
        RDC_POOL_CONSUMED_PCT_JSON  NVARCHAR(MAX) NULL,

        -- Budget cap pressure: % of stores hitting MJ_REQ cap below 50% of base need
        STORES_BUDGET_BROKEN_PCT    FLOAT    NULL,

        -- Alert flags — populated at write time so the UI can highlight
        -- without re-applying thresholds. Bit field for readability.
        ALERT_HIGH_MIX        BIT NOT NULL DEFAULT 0,
        ALERT_LOW_FILL        BIT NOT NULL DEFAULT 0,
        ALERT_HIGH_FALLBACK   BIT NOT NULL DEFAULT 0,
        ALERT_BUDGET_PRESSURE BIT NOT NULL DEFAULT 0,

        CREATED_BY          NVARCHAR(100) NULL,
        CONSTRAINT UX_alloc_health_session UNIQUE (SESSION_ID)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_alloc_health_run_at'
      AND object_id = OBJECT_ID(N'dbo.ARS_ALLOC_HEALTH_HISTORY')
)
CREATE NONCLUSTERED INDEX IX_alloc_health_run_at
    ON dbo.ARS_ALLOC_HEALTH_HISTORY (RUN_AT DESC);
GO
