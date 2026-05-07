-- ============================================================================
-- 021_focus_list_table.sql
-- Master_FOCUS_LIST — planner-curated articles forced into allocation
-- regardless of demand signal.
--
-- Run on the Rep_data database (or wherever Master_ALC_INPUT_* live).
--
-- The allocator already reads two flag columns from ARS_LISTING_WORKING:
--   FOCUS_W_CAP    — force-include but respect MJ_REQ budget
--   FOCUS_WO_CAP   — force-include AND uncap MJ_REQ for the (store,majcat)
--
-- Both default to 0 today and there is no way to populate them. This
-- table is the master source. backend/app/services/focus_list.py
-- joins it during listing generation to set the flags before allocation
-- runs.
--
-- Idempotent: only creates the table + indexes if they do not exist.
-- Safe to run on prod multiple times.
-- ============================================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'dbo.Master_FOCUS_LIST') AND type = 'U'
)
BEGIN
    CREATE TABLE dbo.Master_FOCUS_LIST (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        -- Scope: NULL WERKS = applies to every store; NULL CLR = every color of the gen-art.
        WERKS           NVARCHAR(50)   NULL,
        MAJ_CAT         NVARCHAR(200)  NOT NULL,
        GEN_ART_NUMBER  BIGINT         NOT NULL,
        CLR             NVARCHAR(200)  NULL,
        -- Behaviour: 'W_CAP' (force-include, respect budget) or 'WO_CAP' (force-include, uncap).
        FOCUS_TYPE      NVARCHAR(20)   NOT NULL,
        -- Optional taxonomy for reporting only — does not change allocator behaviour.
        TIER            NVARCHAR(50)   NULL,  -- e.g. 'NATIONAL_HERO', 'CORE_FOCUS', 'ASSORTED'
        IS_ACTIVE       BIT            NOT NULL DEFAULT 1,
        NOTE            NVARCHAR(500)  NULL,
        CREATED_AT      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CREATED_BY      NVARCHAR(100)  NULL,
        UPDATED_AT      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        UPDATED_BY      NVARCHAR(100)  NULL,
        CONSTRAINT CK_focus_type CHECK (FOCUS_TYPE IN (N'W_CAP', N'WO_CAP'))
    );
END
GO

-- Index for the join apply_focus_flags() does (per-store and per-MAJ_CAT).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_focus_list_join'
      AND object_id = OBJECT_ID(N'dbo.Master_FOCUS_LIST')
)
CREATE NONCLUSTERED INDEX IX_focus_list_join
    ON dbo.Master_FOCUS_LIST (MAJ_CAT, GEN_ART_NUMBER)
    INCLUDE (WERKS, CLR, FOCUS_TYPE, IS_ACTIVE);
GO

-- A planner can mark the same article both W_CAP for one store and
-- WO_CAP for another. NULL WERKS is the "all stores" wildcard; NULL CLR
-- is the "all colors" wildcard. SQL Server does not allow expressions
-- like ISNULL(WERKS, N'') in plain UNIQUE indexes, so duplicate-scope
-- prevention is enforced in the service layer (focus_list.bulk_upsert),
-- which uses MERGE on a COALESCE key. A persisted-computed-column
-- approach would also work but is unnecessary at this row count.
GO
