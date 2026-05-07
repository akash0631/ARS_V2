-- ============================================================================
-- 023_st_specific_overrides.sql
-- Master_ST_SPECIFIC — store-specific override list. The original 29-step
-- spec calls these ST_SPECIFIC=9999 entries: planner-curated articles that
-- MUST go to a specific store regardless of any normal scoring.
--
-- Different from Master_FOCUS_LIST:
--   - FOCUS_LIST is broader: forces inclusion at category level, optional
--     wildcards (NULL WERKS = all stores, NULL CLR = all colors).
--   - ST_SPECIFIC is per-store: WERKS is REQUIRED, the entry pins one
--     article to one specific store with a target quantity. The allocator
--     treats it as a hard ALLOCATION (not just eligibility hint).
--
-- Run on Rep_data. Idempotent.
-- ============================================================================

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'dbo.Master_ST_SPECIFIC') AND type = 'U'
)
BEGIN
    CREATE TABLE dbo.Master_ST_SPECIFIC (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        WERKS           NVARCHAR(50)   NOT NULL,         -- required: per-store
        MAJ_CAT         NVARCHAR(200)  NOT NULL,
        GEN_ART_NUMBER  BIGINT         NOT NULL,
        CLR             NVARCHAR(200)  NULL,             -- NULL = any color of the gen-art
        TARGET_QTY      INT            NULL,             -- desired ship qty; NULL = use OPT_MBQ
        REASON          NVARCHAR(500)  NULL,             -- planner note: 'flagship store launch', etc.
        IS_ACTIVE       BIT            NOT NULL DEFAULT 1,
        CREATED_AT      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CREATED_BY      NVARCHAR(100)  NULL,
        UPDATED_AT      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        UPDATED_BY      NVARCHAR(100)  NULL,
        EFFECTIVE_FROM  DATE           NULL,             -- planner can stage future overrides
        EFFECTIVE_TO    DATE           NULL,             -- entry expires automatically
        CONSTRAINT CK_st_specific_target CHECK (TARGET_QTY IS NULL OR TARGET_QTY > 0)
    );
END
GO

-- Index for the apply pass (per-store and per-MAJ_CAT lookup)
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_st_specific_lookup'
      AND object_id = OBJECT_ID(N'dbo.Master_ST_SPECIFIC')
)
CREATE NONCLUSTERED INDEX IX_st_specific_lookup
    ON dbo.Master_ST_SPECIFIC (WERKS, MAJ_CAT, GEN_ART_NUMBER)
    INCLUDE (CLR, TARGET_QTY, IS_ACTIVE, EFFECTIVE_FROM, EFFECTIVE_TO);
GO
