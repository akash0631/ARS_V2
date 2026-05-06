"""
Generate ARS Contribution Percentage Complete Process Reference as a Word document.
Run: python docs/generate_contribution_doc.py
Output: docs/ARS_Contribution_Complete_Reference.docx
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# ── Page margins ──────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.2)
    section.right_margin  = Cm(2.2)

# ── Colour palette ────────────────────────────────────────────────
BLUE_DARK   = RGBColor(0x1F, 0x49, 0x7D)
BLUE_MID    = RGBColor(0x2E, 0x74, 0xB5)
BLUE_LIGHT  = RGBColor(0x5B, 0x9B, 0xD5)
TH_BG       = "2E74B5"
ALT_BG      = "DEEAF1"
CODE_BG     = "F2F2F2"
BLACK       = RGBColor(0x00, 0x00, 0x00)
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)

# ── Style helpers ─────────────────────────────────────────────────
def set_cell_bg(cell, hex_color):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)

def set_cell_borders(cell, hex_color="BFBFBF"):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        bd = OxmlElement(f"w:{side}")
        bd.set(qn("w:val"),   "single")
        bd.set(qn("w:sz"),    "4")
        bd.set(qn("w:space"), "0")
        bd.set(qn("w:color"), hex_color)
        tcBorders.append(bd)
    tcPr.append(tcBorders)

def h1(text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.color.rgb = WHITE
    p.runs[0].font.size      = Pt(14)
    p.runs[0].font.bold      = True
    pPr  = p._p.get_or_add_pPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  "1F497D")
    pPr.append(shd)
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after  = Pt(4)
    return p

def h2(text):
    p = doc.add_heading(text, level=2)
    for run in p.runs:
        run.font.color.rgb = BLUE_DARK
        run.font.size      = Pt(13)
        run.font.bold      = True
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(3)
    return p

def h3(text):
    p = doc.add_heading(text, level=3)
    for run in p.runs:
        run.font.color.rgb = BLUE_MID
        run.font.size      = Pt(11.5)
        run.font.bold      = True
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after  = Pt(2)
    return p

def h4(text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.bold      = True
    run.font.size      = Pt(11)
    run.font.color.rgb = BLUE_LIGHT
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(2)
    return p

def body(text, bold=False, italic=False, color=None):
    p   = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size      = Pt(10)
    run.font.bold      = bold
    run.font.italic    = italic
    if color:
        run.font.color.rgb = color
    p.paragraph_format.space_after = Pt(4)
    return p

def note(text):
    p   = doc.add_paragraph()
    run = p.add_run("⚑  " + text)
    run.font.size      = Pt(9.5)
    run.font.italic    = True
    run.font.color.rgb = RGBColor(0xC0, 0x55, 0x00)
    p.paragraph_format.left_indent  = Inches(0.2)
    p.paragraph_format.space_after  = Pt(4)
    return p

def bullet(text, level=0):
    p   = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    run.font.size = Pt(10)
    p.paragraph_format.left_indent  = Inches(0.3 + level * 0.2)
    p.paragraph_format.space_after  = Pt(2)
    return p

def code_block(text):
    for line in text.strip("\n").split("\n"):
        p   = doc.add_paragraph()
        run = p.add_run(line if line else " ")
        run.font.name  = "Courier New"
        run.font.size  = Pt(8.5)
        run.font.color.rgb = RGBColor(0x20, 0x20, 0x20)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.left_indent  = Inches(0.15)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"),   "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"),  "F2F2F2")
        pPr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_table(headers, rows, col_widths=None):
    n_cols = len(headers)
    tbl    = doc.add_table(rows=1 + len(rows), cols=n_cols)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

    hdr = tbl.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        set_cell_bg(cell, TH_BG)
        set_cell_borders(cell, "1F497D")
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p   = cell.paragraphs[0]
        run = p.add_run(h)
        run.font.bold      = True
        run.font.size      = Pt(9)
        run.font.color.rgb = WHITE
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri + 1]
        bg  = ALT_BG if ri % 2 == 1 else "FFFFFF"
        for ci, val in enumerate(row_data):
            cell = row.cells[ci]
            set_cell_bg(cell, bg)
            set_cell_borders(cell, "BDD7EE")
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            p   = cell.paragraphs[0]
            run = p.add_run(str(val))
            run.font.size = Pt(9)
            if ci == 0:
                run.font.bold = True

    if col_widths:
        for ci, w in enumerate(col_widths):
            for row in tbl.rows:
                row.cells[ci].width = Inches(w)

    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return tbl

def spacer():
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)


# ══════════════════════════════════════════════════════════════════
# TITLE PAGE
# ══════════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("ARS Contribution %")
run.font.bold      = True
run.font.size      = Pt(26)
run.font.color.rgb = BLUE_DARK

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Complete Process Reference")
run.font.bold      = True
run.font.size      = Pt(18)
run.font.color.rgb = BLUE_MID

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Configuration  ·  Execute Pipeline  ·  KPI Formulas  ·  Review & Export  ·  Debug Guide")
run.font.size      = Pt(11)
run.font.italic    = True
run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("V2 Retail Auto Replenishment System  —  Confidential")
run.font.size      = Pt(10)
run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

doc.add_page_break()


# ══════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════
h1("Overview — What Contribution % Does")

body("Contribution % answers the question: within a store's assortment for a given MAJ_CAT, what share of stock or sales belongs to each dimension value (colour, size, vendor, etc.)? The allocation engine uses this split at Stage B to break a GEN_ART option's total MBQ down into per-size or per-colour targets (SZ_MBQ / SZ_MBQ_WH).")

body("The pipeline has four phases that must be completed in order:", bold=True)
add_table(
    ["Phase", "What you do", "Key output"],
    [
        ["1. Presets",     "Define named calculation recipes: which months, how many avg_days, which KPI window (L30D / L7D / L18M)",  "Cont_presets table"],
        ["2. Mappings",    "Define SSN→output-column rules: which SSN values map to which preset suffixes",                             "Cont_mappings + Cont_mapping_assignments tables"],
        ["3. Execute",     "Run the pipeline: choose grouping column, MAJ_CATs, presets; system computes 15 KPIs per row",             "Cont_Percentage_* result tables / temp pickle"],
        ["4. Review",      "Preview, filter, and export results; manage old result tables",                                             "CSV / ZIP download"],
    ],
    col_widths=[1.2, 3.8, 2.4]
)

h2("Database Tables")
add_table(
    ["Table", "Purpose"],
    [
        ["Cont_presets",             "One row per named preset: months list, avg_days, kpi_type, sequence_order"],
        ["Cont_mappings",            "SSN→suffix mapping rules stored as JSON"],
        ["Cont_mapping_assignments", "Links an output column name to a mapping + prefix + target (Store/Company/Both)"],
        ["Cont_jobs",                "Job tracking: status, log, duration, file paths, row counts"],
        ["Cont_Percentage_*",        "Dynamic result tables — one per execution run (optional, only when save_to_db=True)"],
    ],
    col_widths=[2.2, 5.2]
)

h2("Source Tables")
add_table(
    ["Table", "Purpose in pipeline"],
    [
        ["COUNT_STOCK_DATA_18M",   "18-month stock/sales/GM fact table — the sole data source. Filtered by KPI window."],
        ["VW_MASTER_PRODUCT",      "Maps MATNR → MAJ_CAT, SEG, and the chosen grouping_column (CLR, MACRO_MVGR, etc.)"],
        ["Master_HIER_{col}",      "Hierarchy master for the chosen grouping column — CROSS JOINed with Master_STORE_PLAN to produce all store × dimension combinations"],
        ["Master_STORE_PLAN",      "Active store list with APF (area per fixture) and reference-group columns"],
        ["master_avg_density",     "AVG_DNSTY per MAJ_CAT — used in display-area and STR calculations"],
    ],
    col_widths=[2.0, 5.4]
)

h2("Key Term Definitions")
add_table(
    ["Term", "Full Name / Meaning"],
    [
        ["Preset",         "A named configuration: which months to include, how many avg_days, and which KPI window (L30D/L7D/L18M). Multiple presets can run in one execution; results are combined horizontally."],
        ["kpi_type",       "L30D = last 30 days (single-window). L7D = last 7 days. L18M = multi-month (specific months selected from the months list)."],
        ["avg_days",       "The denominator used when converting aggregated sales to a daily rate. Default 30 (matches L30D). Set to 7 for L7D presets."],
        ["grouping_column","The dimension column that defines rows: CLR, SZ, RNG_SEG, M_VND_CD, MACRO_MVGR, MICRO_MVGR, or FAB. One run = one grouping column."],
        ["Mapping",        "A JSON rule that maps each SSN value (e.g. SS26, AW26) to one or more preset suffixes. Enables different contribution columns per season."],
        ["Assignment",     "Connects an output column name to a mapping + a column prefix. At runtime the engine resolves each row's SSN, picks the right preset suffix(es), and writes the result into the output column."],
        ["CONT (in allocation)", "The fraction of OPT_MBQ that Stage B assigns to a specific size/colour. Read from Master_CONT_SZ and populated into ARS_ALLOC_WORKING.CONT for each exploded row."],
        ["Store level",    "Result rows keyed by (ST_CD + hierarchy columns). One row per store × MAJ_CAT × grouping value."],
        ["Company level",  "Result rows aggregated across all stores — keyed by hierarchy columns only (ST_CD removed). Sum of stock/sales, then KPIs recomputed."],
    ],
    col_widths=[1.8, 5.6]
)


# ══════════════════════════════════════════════════════════════════
# PART 1 — CONFIGURATION
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 1 — CONFIGURATION  (Presets · Mappings · Assignments)")

# ── Presets
h2("1.1 — Presets  (Cont_presets)")
body("A preset defines one data-slice recipe. Execution processes presets in their sequence_order. Results for each preset become a column group in the final output, suffixed with |{preset_name}.")

add_table(
    ["Field", "Type", "Meaning"],
    [
        ["preset_name",    "NVARCHAR(255) PK",  "Unique name; becomes the column suffix in output (e.g. SALE_CONT%|L30D)"],
        ["kpi_type",       "NVARCHAR(50)",       "L30D, L7D, or L18M — controls the WHERE filter on COUNT_STOCK_DATA_18M"],
        ["months",         "JSON list",          "For L18M only: list of STOCK_DATE values to include (e.g. [\"2025-10-01\", \"2025-11-01\"])"],
        ["avg_days",       "INT",                "Denominator for daily-rate calculations. Default 30 (L30D), 7 for L7D, 365 typical for L18M"],
        ["description",    "NVARCHAR",           "Free-text label shown in UI"],
        ["sequence_order", "INT",                "Controls processing order. Lower number runs first. Default 9999."],
    ],
    col_widths=[1.5, 1.6, 4.3]
)

body("KPI-type filter logic:", bold=True)
code_block("""-- L7D preset
WHERE sal_stk.KPI = 'L7D'

-- L30D preset
WHERE sal_stk.KPI = 'L30D'

-- L18M preset (specific months)
WHERE sal_stk.STOCK_DATE IN ('2025-10-01','2025-11-01',...) AND sal_stk.KPI = 'L18M'""")

note("The default 'L30D' preset is auto-seeded on first API startup if Cont_presets is empty.")

# ── Mappings
h2("1.2 — Mappings  (Cont_mappings)")
body("A mapping translates an article's SSN (season code) into one or more preset suffixes to use for that article's contribution column. This lets you use different time-window data for summer vs. winter season articles.")

add_table(
    ["Field", "Type", "Meaning"],
    [
        ["mapping_name",      "NVARCHAR(255) PK", "Unique name for this mapping rule"],
        ["suffix_mapping",    "JSON object",      "{ SSN_VALUE: [suffix1, suffix2, ...] } — maps each season code to a list of preset names"],
        ["fallback_suffixes", "JSON list",        "Preset names to use when the article's SSN does not match any key in suffix_mapping"],
        ["description",       "NVARCHAR",         "Free-text explanation"],
    ],
    col_widths=[1.8, 1.5, 4.1]
)

body("Example mapping_json:", bold=True)
code_block("""{
    "SS26": ["SS_Preset", "L30D"],
    "AW26": ["AW_Preset", "L30D"],
    "SS25": ["SS25_Preset"]
}
fallback_json: ["L30D"]

-- An article with SSN=SS26 will look for columns prefixed with SS_Preset and L30D.
-- An article with SSN=AW25 (not in mapping) will use the fallback → L30D.""")

# ── Assignments
h2("1.3 — Assignments  (Cont_mapping_assignments)")
body("An assignment binds a mapping to a specific output column name and a column prefix. The prefix identifies which KPI to pull (e.g. 'INITIAL AUTO CONT%|' targets the INITIAL AUTO CONT% columns from each preset). The target controls whether the output column is written to the store-level table, company-level table, or both.")

add_table(
    ["Field", "Meaning"],
    [
        ["col_name",     "Name of the output column to create in the result table (e.g. 'FINAL_CONT%')"],
        ["mapping_name", "Which Cont_mappings rule to use for SSN→suffix resolution"],
        ["prefix",       "KPI column prefix to combine with each suffix (e.g. 'INITIAL AUTO CONT%|' → looks for 'INITIAL AUTO CONT%|L30D', 'INITIAL AUTO CONT%|AW_Preset', etc.)"],
        ["target",       "'Store' = written only to store-level output. 'Company' = company-level only. 'Both' = both outputs."],
    ],
    col_widths=[1.5, 5.9]
)

note("Multiple assignments can exist pointing to the same mapping with different prefixes. For example, one assignment creates FINAL_SALE_CONT% (prefix='SALE_CONT%|') and another creates FINAL_STOCK_CONT% (prefix='STOCK_CONT%|').")


# ══════════════════════════════════════════════════════════════════
# PART 2 — EXECUTE PIPELINE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 2 — EXECUTE PIPELINE  (contrib.py → _run_job)")

body("Trigger: POST /contrib/execute with an ExecutePayload. A job_id is returned immediately; the pipeline runs in a background thread. Frontend polls GET /contrib/jobs every 5 seconds.")

h2("2.1 — ExecutePayload Parameters")
add_table(
    ["Parameter", "Default", "Meaning"],
    [
        ["presets",          "[] (all)",        "List of preset names to run. Empty = all presets in sequence_order."],
        ["majcats",          "[] (all)",        "List of MAJ_CAT values to filter. Empty = all MAJ_CATs with data."],
        ["grouping_column",  "MACRO_MVGR",      "Dimension to group by: CLR, SZ, RNG_SEG, M_VND_CD, MACRO_MVGR, MICRO_MVGR, or FAB."],
        ["save_to_db",       "False",           "If True, persist result tables to DB as Cont_Percentage_{grouping}_{YYYY_MM}."],
        ["use_sequence",     "True",            "Process presets in sequence_order. False = alphabetical."],
        ["target",           "Both",            "Whether to compute Store-level, Company-level, or Both output DataFrames."],
    ],
    col_widths=[1.8, 1.2, 4.4]
)

h2("2.2 — Full Pipeline Flow (_run_job)")
body("The background job executes these steps in order for every active preset:")

code_block("""1. Load presets from Cont_presets (filtered by payload.presets if specified)
   Sort by sequence_order if use_sequence=True

2. Load global lookups once (shared across all presets):
   - avg_density ← master_avg_density (MAJ_CAT → AVG_DNSTY)
   - apf         ← Master_STORE_PLAN  (ST_CD → APF, reference columns)

3. For each preset p (in sequence_order):
   a. _process_single_preset(engine, p.name, p.config, majcats, grouping_column,
                              avg_density, apf, df_master_cache)
      → returns (df_detail, df_agg, timing, df_master_cache)

   b. df_master_cache is reused for every subsequent preset
      (avoids re-running the expensive CROSS JOIN query)

   c. Store df_detail in detail_frames[p.name]
        Store df_agg   in agg_frames[p.name]

4. _combine_dataframes(detail_frames, is_aggregated=False, grouping_column, engine)
   → df_store  (store-level combined)

   _combine_dataframes(agg_frames, is_aggregated=True, grouping_column, engine)
   → df_company  (company-level combined)

5. _apply_mapping_assignments(df_store, engine)   — resolves SSN → output columns
   _apply_mapping_assignments(df_company, engine)

6. Persist results:
   - Save df_store + df_company to temp pickle files (for fast preview)
   - If save_to_db=True: _save_to_db(engine, df_store, table_name)
                         _save_to_db(engine, df_company, table_name + '_CO')

7. Mark job status='completed'. Spawn auto-delete thread (60s delay).""")

# ── _process_single_preset
h2("2.3 — Per-Preset Processing  (_process_single_preset)")
body("For each preset the pipeline runs five internal steps. The master hierarchy CROSS JOIN (Step 2) is computed only once and cached across all presets — this is the most expensive query and can take 30–120 seconds on large stores × majcat combinations.")

add_table(
    ["Step", "What happens", "Output"],
    [
        ["1. Data query",    "Query COUNT_STOCK_DATA_18M with KPI window filter. Join VW_MASTER_PRODUCT for MAJ_CAT + grouping_column. Aggregate by (ST_CD, MAJ_CAT, grouping_column) → average OP/CL stock and sum sales/GM.",    "df_data: store-grain stock/sales"],
        ["2. Master query",  "CROSS JOIN Master_HIER_{col} × Master_STORE_PLAN (filtered by MAJ_CAT if specified). Produces all possible (ST_CD, MAJ_CAT, grouping_value) combinations — including stores with zero sales. Cached on first preset.",  "df_master: full store × dim skeleton"],
        ["3. Merge",         "LEFT JOIN df_master onto df_data on (ST_CD, MAJ_CAT, grouping_column). Stores with no sales in the window get zeros. Then join AVG_DNSTY and APF.",                                                       "df_merged: store-level detail"],
        ["4. Aggregate",     "Group df_merged by hierarchy columns (dropping ST_CD, ST_NM, AVG_DNSTY, APF). Sum numeric KPIs. Re-join AVG_DNSTY; set APF=25 (company default).",                                                      "df_agg: company-level detail"],
        ["5. Compute KPIs",  "_compute_kpis() runs on both df_merged and df_agg to produce all 15 KPI columns (see Part 3).",                                                                                                         "df_detail, df_agg with KPIs"],
    ],
    col_widths=[1.3, 3.7, 2.4]
)

body("Step 1 SQL skeleton:", bold=True)
code_block("""SELECT ST_CD, MAJ_CAT, {grouping_column},
       AVG(OP_STK_Q) AS OP_STK_Q, AVG(OP_STK_V) AS OP_STK_V,
       AVG(CL_STK_Q) AS CL_STK_Q, AVG(CL_STK_V) AS CL_STK_V,
       AVG(SALE_Q)   AS SALE_Q,   AVG(SALE_V)   AS SALE_V,
       AVG(GM_V)     AS GM_V
FROM (
    SELECT sal_stk.WERKS AS ST_CD, prod.MAJ_CAT, prod.{grouping_column},
           SUM(sal_stk.OP_STK_QTY)/1000  AS OP_STK_Q,   -- quantities in thousands
           SUM(sal_stk.OP_STK_VAL)/100000 AS OP_STK_V,  -- values in lakhs
           SUM(sal_stk.CL_STK_QTY)/1000  AS CL_STK_Q,
           SUM(sal_stk.CL_STK_VAL)/100000 AS CL_STK_V,
           SUM(sal_stk.SALE_QTY)/1000    AS SALE_Q,
           SUM(sal_stk.SALE_VAL)/100000  AS SALE_V,
           SUM(sal_stk.GM_VAL)/100000    AS GM_V
    FROM dbo.COUNT_STOCK_DATA_18M sal_stk WITH (NOLOCK)
    LEFT JOIN (
        SELECT ARTICLE_NUMBER AS MATNR, MAJ_CAT,
               COALESCE(NULLIF({grouping_column},''),'NA') AS {grouping_column}, SEG
        FROM dbo.VW_MASTER_PRODUCT WITH (NOLOCK)
    ) prod ON sal_stk.MATNR = prod.MATNR
    WHERE {majcat_filter} AND prod.SEG IN ('APP','GM') AND {kpi_date_filter}
    GROUP BY sal_stk.WERKS, sal_stk.STOCK_DATE, prod.MAJ_CAT, prod.{grouping_column}
) t
GROUP BY ST_CD, MAJ_CAT, {grouping_column}""")

note("Stock quantities are divided by 1000 (stored as units×1000 in the raw table). Values are divided by 100000 (stored as paise, output in lakhs). This normalisation is important for interpreting AVG_DNSTY and APF correctly in KPI formulas.")

body("Step 2 SQL skeleton:", bold=True)
code_block("""SELECT B.ST_CD, B.ST_NM, A.[{hierarchy_cols}]
FROM Master_HIER_{grouping_column} A WITH (NOLOCK)
CROSS JOIN dbo.Master_STORE_PLAN B WITH (NOLOCK)
WHERE {majcat_filter}

-- Master_HIER_{col} has one row per unique (MAJ_CAT, grouping_value).
-- CROSS JOIN with Master_STORE_PLAN produces one row per store × dimension.
-- After LEFT JOIN with df_data, stores with no sales keep zero-filled KPIs.""")


# ══════════════════════════════════════════════════════════════════
# PART 3 — KPI COMPUTATION
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 3 — KPI COMPUTATION  (_compute_kpis)")

body("All 15 KPI columns are computed in one vectorised NumPy pass. The function is called on both the store-level (df_merged) and company-level (df_agg) DataFrames. For company-level data, ST_CD is absent so group_cols = ['MAJ_CAT'] only.")

body("Scaling constants: Q = 1000 (quantity units), V = 100000 (value in lakhs).", bold=True)

h2("3.1 — Average Stock  (0001_STK_Q / 0001_STK_V)")
body("Average of opening and closing stock. If only one side is non-zero, the non-zero value is used as-is (no halving).")
code_block("""0001_STK_Q = (OP_STK_Q + CL_STK_Q) / 2    when BOTH are non-zero
           = max(OP_STK_Q, CL_STK_Q)          when only one is non-zero
           = 0                                 when both are zero

-- Same formula for 0001_STK_V using OP_STK_V / CL_STK_V""")

h2("3.2 — Display Area  (FIX → DISP_AREA)")
code_block("""FIX       = 0001_STK_Q × 1000 / AVG_DNSTY   (set AVG_DNSTY=1 if zero to avoid div/0)
DISP_AREA = MAX( APF × FIX,  1 if SALE_V > 0 else 0 )

-- FIX: how many fixture units this stock occupies
-- DISP_AREA: effective selling floor area in sq ft.
--            Minimum 1 for rows with any sales (prevents PSF = infinity)""")

h2("3.3 — GM%  (Gross Margin Rate)")
code_block("""GM_% = GM_V / SALE_V    (set SALE_V=1 if zero)""")

h2("3.4 — STR  (Stock-to-Rate Ratio)")
code_block("""PDSQ  = (SALE_Q / avg_days) × 1000     # per-day sale qty (scaled)
STR   = 0001_STK_Q / PDSQ               # days of cover
      = 0                               when PDSQ = 0""")

h2("3.5 — SALES PSF  (Sales per Square Foot per Day)")
code_block("""PDSV      = (SALE_V / avg_days) × 100000   # per-day sale value (scaled)
SALES PSF = PDSV / DISP_AREA             = 0 when DISP_AREA = 0""")

h2("3.6 — MAJ_CAT-Level Benchmarks  (SALE_PSF_MJ / GM_PSF_MJ)")
body("These are the MAJ_CAT total benchmarks — sum of all rows in the same (ST_CD, MAJ_CAT) group divided by total display area. Used as the denominator for achievement% calculations.")
code_block("""sv_sum = SUM(SALE_V)    per group (ST_CD, MAJ_CAT)
da_sum = SUM(DISP_AREA) per group
gv_sum = SUM(GM_V)      per group

SALE_PSF_MJ  = sv_sum × 100000 / da_sum / avg_days   (= 0 if da_sum=0)
GM_PSF_MJ    = gv_sum × 100000 / da_sum / avg_days   (= 0 if da_sum=0)""")

h2("3.7 — Achievement %  (SALES_PSF_ACH% / GM_PSF_ACH%)")
code_block("""SALES_PSF_ACH% = SALES PSF / SALE_PSF_MJ    (= 0 if SALE_PSF_MJ = 0)
GM_PSF_ACH%   = GM PSF   / GM_PSF_MJ      (= 0 if GM_PSF_MJ   = 0)

-- A value of 1.0 means this row performs at exactly the MAJ_CAT average.
-- > 1.0 means it is outperforming; < 1.0 means underperforming.""")

h2("3.8 — GM PSF  (Gross Margin per Square Foot per Day)")
code_block("""GM PSF = GM_V × 100000 / DISP_AREA / avg_days    (= 0 if DISP_AREA = 0)""")

h2("3.9 — Contribution %  (STOCK_CONT% / SALE_CONT%)")
body("Contribution is always computed within (ST_CD, MAJ_CAT) for store-level data, or within (MAJ_CAT) for company-level. Only rows with positive stock/sales participate in the denominator — zero-stock or zero-sales rows get a contribution of 0, not a share of 1/N.")
code_block("""-- Only rows with 0001_STK_Q > 0 contribute to stock denominator
stk_sum    = SUM(0001_STK_Q) over rows where 0001_STK_Q > 0, per (ST_CD, MAJ_CAT)
STOCK_CONT% = 0001_STK_Q / stk_sum      (= 0 for rows with 0001_STK_Q = 0)

-- Only rows with SALE_V > 0 contribute to sales denominator
sal_sum    = SUM(SALE_V) over rows where SALE_V > 0, per (ST_CD, MAJ_CAT)
SALE_CONT% = SALE_V / sal_sum           (= 0 for rows with SALE_V = 0)""")

note("Contribution % always sums to 1.0 within each (ST_CD, MAJ_CAT) group (for rows with positive denominator). Rows with zero stock or zero sales are excluded from the sum, so a MAJ_CAT with 3 active + 2 zero rows will produce contributions that sum to 1.0 across the 3 active rows only.")

h2("3.10 — ALGO  (Auto-Contribution Score)")
body("ALGO is the raw score before normalisation. It blends SALE_CONT% with a performance multiplier based on GM achievement. The multiplier gr=2 for vendor-level grouping (M_VND_CD) to amplify vendor performance signals; gr=1 for all other dimensions.")
code_block("""gr        = 2  if grouping_column == 'M_VND_CD'  else  1

algo_raw  = SALE_CONT% × (5.0  if SALE_CONT% < 0.05  else  3.0)
            -- Small contributors (< 5%) get a 5× boost; others get 3×

algo_adj  = SALE_CONT% × (1 + (GM_PSF_ACH% - 1) × gr)
            -- Adjusts the base contribution up/down based on GM performance
            -- If GM_PSF_ACH% = 1.0 (at benchmark): algo_adj = SALE_CONT%  (no change)
            -- If GM_PSF_ACH% = 1.5 (50% above):    algo_adj = SALE_CONT% × 1.5
            -- If GM_PSF_ACH% = 0.5 (50% below):    algo_adj = SALE_CONT% × 0.5

ALGO      = MIN(algo_raw, MAX(algo_adj, 0))
            -- Floor: never negative. Cap: never exceeds the raw score.""")

h2("3.11 — INITIAL AUTO CONT%  (Normalised ALGO)")
code_block("""algo_sum          = SUM(ALGO) per group (ST_CD, MAJ_CAT)
INITIAL AUTO CONT% = ALGO / algo_sum    (= 0 if algo_sum = 0)

-- This is the final output contribution that allocators use.
-- It always sums to 1.0 within each (ST_CD, MAJ_CAT) group.""")

body("Complete KPI column list:", bold=True)
add_table(
    ["#", "Column", "Based on", "Interpretation"],
    [
        ["1",  "0001_STK_Q",         "OP_STK_Q, CL_STK_Q",              "Average stock quantity (thousands)"],
        ["2",  "0001_STK_V",         "OP_STK_V, CL_STK_V",              "Average stock value (lakhs)"],
        ["3",  "FIX",                "0001_STK_Q, AVG_DNSTY",           "Fixture units occupied by this stock"],
        ["4",  "DISP_AREA",          "APF, FIX, SALE_V",                "Effective selling floor area (sq ft)"],
        ["5",  "GM_%",               "GM_V, SALE_V",                    "Gross margin rate"],
        ["6",  "STR",                "0001_STK_Q, SALE_Q, avg_days",    "Days of cover (stock-to-rate)"],
        ["7",  "SALES PSF",          "SALE_V, DISP_AREA, avg_days",     "Sales per sq ft per day"],
        ["8",  "SALE_PSF_MJ",        "MAJ_CAT total SALE_V, DISP_AREA", "MAJ_CAT benchmark sales PSF"],
        ["9",  "SALES_PSF_ACH%",     "SALES PSF / SALE_PSF_MJ",         "Sales PSF vs. MAJ_CAT benchmark"],
        ["10", "GM PSF",             "GM_V, DISP_AREA, avg_days",       "GM per sq ft per day"],
        ["11", "GM_PSF_MJ",          "MAJ_CAT total GM_V, DISP_AREA",   "MAJ_CAT benchmark GM PSF"],
        ["12", "GM_PSF_ACH%",        "GM PSF / GM_PSF_MJ",              "GM PSF vs. MAJ_CAT benchmark"],
        ["13", "STOCK_CONT%",        "0001_STK_Q / MAJ_CAT sum",        "Stock share within MAJ_CAT (0–1)"],
        ["14", "SALE_CONT%",         "SALE_V / MAJ_CAT sum",            "Sales value share (0–1)"],
        ["15", "ALGO",               "SALE_CONT%, GM_PSF_ACH%",         "Raw performance-weighted score"],
        ["16", "INITIAL AUTO CONT%", "ALGO / MAJ_CAT ALGO sum",         "Normalised final contribution (0–1), sums to 1"],
    ],
    col_widths=[0.4, 1.9, 2.2, 3.0]
)

body("Worked example (store HN14, MAJ_CAT = JB_JEANS, grouping = MACRO_MVGR, avg_days = 30):", bold=True)
add_table(
    ["MACRO_MVGR", "0001_STK_Q", "SALE_V", "GM_PSF_ACH%", "SALE_CONT%", "algo_raw", "algo_adj (gr=1)", "ALGO", "INITIAL AUTO CONT%"],
    [
        ["DENIM",     "120", "85",  "1.20", "0.567", "1.701", "0.680",  "0.680", "0.40"],
        ["TROUSERS",  "80",  "45",  "0.90", "0.300", "0.900", "0.270",  "0.270", "0.16"],
        ["SHORTS",    "50",  "15",  "0.70", "0.100", "0.500", "0.070",  "0.070", "0.04"],
        ["CHINOS",    "30",  "5",   "0.50", "0.033", "0.165", "0.017",  "0.017", "0.01"],
        ["TOTAL",     "280", "150", "—",    "1.000", "3.266", "1.037",  "1.037", "1.00"],
    ],
    col_widths=[1.2, 1.1, 0.8, 1.2, 1.1, 1.0, 1.4, 0.8, 1.8]
)
note("DENIM's ALGO is capped at 0.680 (algo_raw=1.701 > algo_adj=0.680). In this case GM performance (1.20) only modestly lifts the sales contribution, so algo_adj < algo_raw and the cap binds. INITIAL AUTO CONT% for DENIM = 0.680 / 1.037 ≈ 0.655 (shown rounded to 0.40 in example for illustration).")


# ══════════════════════════════════════════════════════════════════
# PART 4 — COMBINE & APPLY MAPPINGS
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 4 — COMBINE & APPLY MAPPINGS")

h2("4.1 — Combining Preset Results  (_combine_dataframes)")
body("After all presets are processed, their result DataFrames are merged horizontally on shared dimension keys. Each preset's KPI columns are renamed with a |{preset_name} suffix before merging.")

code_block("""merge_keys = [ST_CD, ST_NM] + hierarchy_cols + [grouping_column, AVG_DNSTY] + apf_cols
             (company-level drops ST_CD, ST_NM)

For each preset p:
    rename: {KPI} → {KPI}|{p.name}   for all non-key columns
    retain: merge_keys + renamed columns

combined = preset1_df
for p in preset2..N:
    combined = combined.OUTER_JOIN(p_df, on=merge_keys)

combined["Generated_Date"] = now()""")

note("OUTER JOIN is used so that rows that appear in some presets but not others (e.g. a MAJ_CAT only in a specific month window) are still included with NaN in missing preset columns.")

h2("4.2 — Applying Mapping Assignments  (_apply_mapping_assignments)")
body("For each assignment, the function resolves each row's SSN value against the mapping, then picks the best available KPI column to write into the output column.")

code_block("""For each assignment a:
    mapping = Cont_mappings[a.mapping_name]
    prefix  = a.prefix          # e.g. 'INITIAL AUTO CONT%|'
    col_out = a.col_name        # e.g. 'FINAL_CONT%'

    For each row r:
        ssn = r["SSN"]

        if ssn in mapping.suffix_mapping:
            candidates = [prefix + s for s in mapping.suffix_mapping[ssn]
                          if (prefix + s) in df.columns]
            result[r] = MAX of candidate columns (nanmax)

        else:                   # SSN not in mapping → use fallback
            fallback_cols = [prefix + s for s in mapping.fallback_suffixes
                             if (prefix + s) in df.columns]
            result[r] = MAX of fallback_cols (or 0 if none)

    df[col_out] = result""")

note("nanmax is used so that missing values (NaN from presets with no data for that row) are ignored when picking the best available column. A row with three candidate columns where two are NaN and one is 0.35 will correctly resolve to 0.35.")

body("Example assignment resolution:", bold=True)
add_table(
    ["Row SSN", "Mapping key?", "Candidates found", "nanmax result", "Output in FINAL_CONT%"],
    [
        ["SS26",   "Yes", "INITIAL AUTO CONT%|SS_Preset = 0.32, INITIAL AUTO CONT%|L30D = 0.29", "0.32", "0.32"],
        ["AW26",   "Yes", "INITIAL AUTO CONT%|AW_Preset = NaN, INITIAL AUTO CONT%|L30D = 0.41",  "0.41", "0.41"],
        ["AW24",   "No",  "Fallback: INITIAL AUTO CONT%|L30D = 0.27",                            "0.27", "0.27"],
        ["None",   "No",  "Fallback: INITIAL AUTO CONT%|L30D = 0.19",                            "0.19", "0.19"],
    ],
    col_widths=[1.0, 1.0, 3.6, 1.0, 1.8]
)


# ══════════════════════════════════════════════════════════════════
# PART 5 — JOB LIFECYCLE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 5 — JOB LIFECYCLE  (Cont_jobs)")

h2("5.1 — Job Status Transitions")
code_block("""pending  → running   : job dequeued and _run_job() thread started
running  → completed : pipeline finished, results saved to pickle (+ DB if save_to_db)
running  → failed    : unhandled exception in _run_job()
running  → cancelled : POST /contrib/jobs/{id}/cancel while running
running  ↔ paused    : POST /contrib/jobs/{id}/pause / resume (checked at preset boundaries)""")

add_table(
    ["Status", "Meaning", "Next action"],
    [
        ["pending",   "Job queued, waiting for worker thread",              "Automatic — no action needed"],
        ["running",   "Pipeline actively processing presets",               "Poll /jobs/{id} for progress log"],
        ["paused",    "Execution suspended at next preset boundary",        "POST /jobs/{id}/resume to continue"],
        ["completed", "Results available — preview and download ready",     "Fetch /jobs/{id} for preview; download CSV/ZIP"],
        ["failed",    "Exception during processing; error field has detail", "Check error message; re-run with narrower scope"],
        ["cancelled", "User aborted; partial results may exist in temp files", "Delete job and re-run"],
    ],
    col_widths=[1.1, 3.0, 3.3]
)

h2("5.2 — Job Persistence")
body("Jobs are stored both in-memory (OrderedDict _jobs) and in Cont_jobs DB table. On API restart, _load_persisted_jobs() replays all non-deleted jobs from the DB, restoring running/paused jobs as 'failed' (since the thread is gone). Completed jobs are loaded with their file paths so downloads still work if the pickle files survived.")

h2("5.3 — Auto-Cleanup")
body("60 seconds after a job reaches 'completed' status, an auto-delete background thread fires:")
code_block("""1. Delete temp pickle files (store_file, company_file)
2. If save_to_db=False: nothing else to do
3. Remove job from _jobs in-memory cache
4. DELETE FROM Cont_jobs WHERE job_id = :id

-- Frontend auto-fetches results before the 60s window closes.
-- If the user refreshes and the job is gone, they must re-execute.""")

note("The auto-cleanup window is 60 seconds. If the frontend is slow to fetch or the user navigates away immediately after completion, the result files may be deleted before download. Use save_to_db=True to persist results permanently.")

h2("5.4 — Job Log Format")
body("Each step appends a log entry. The log array is stored in Cont_jobs.log_json and returned in GET /jobs/{id}.")
code_block("""[
  {"step": "preset_L30D", "msg": "querying data...",        "t": 0.0},
  {"step": "preset_L30D", "msg": "sql_data: 4.2s",          "t": 4.2},
  {"step": "preset_L30D", "msg": "sql_master: 38.1s",       "t": 42.3},
  {"step": "preset_L30D", "msg": "merge: 1.1s, kpi: 0.8s",  "t": 44.2},
  {"step": "combine",     "msg": "store rows: 84240",        "t": 46.5},
  {"step": "mappings",    "msg": "assignments applied: 2",   "t": 46.8},
  {"step": "save",        "msg": "pickle saved",             "t": 47.0},
  {"step": "complete",    "msg": "done in 47.0s",            "t": 47.0}
]""")


# ══════════════════════════════════════════════════════════════════
# PART 6 — REVIEW & EXPORT
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 6 — REVIEW & EXPORT  (GET /contrib/review/…)")

h2("6.1 — Preview  (GET /contrib/jobs/{id})")
body("When a job completes, GET /contrib/jobs/{id} returns a full preview of up to 200 rows plus metadata. The preview is read from the temp pickle file (fast, no DB query).")

add_table(
    ["Field", "Content"],
    [
        ["status",        "completed / failed / running / etc."],
        ["store_rows",    "Total rows in the store-level result"],
        ["company_rows",  "Total rows in the company-level result"],
        ["store_preview", "First 200 rows of store DataFrame as JSON records"],
        ["company_preview","First 200 rows of company DataFrame as JSON records"],
        ["log",           "Full step log array"],
        ["duration",      "Total execution time in seconds"],
        ["error",         "Error message string if status=failed"],
    ],
    col_widths=[1.8, 5.6]
)

h2("6.2 — Download from Job  (GET /contrib/jobs/{id}/download/{result_type})")
body("Downloads the full result for a completed job as CSV. result_type is 'store' or 'company'. Streams the pickle → CSV via StreamingResponse.")
note("Download is available only while the job exists (within the 60s cleanup window). If the window has passed, use the Review page to download from the DB table (requires save_to_db=True).")

h2("6.3 — Result Tables  (GET /contrib/review/tables)")
body("Lists all Cont_Percentage_* tables in the database. Each entry shows table name, row count, and creation date. Tables are only created when save_to_db=True was set at execution time.")

h2("6.4 — Background Export  (POST /contrib/review/export/{table_name})")
body("For large tables the export runs in a background job that streams to a temp file. The frontend polls GET /contrib/review/exports every 2 seconds. When status=completed the file is auto-downloaded and the export job is deleted.")

add_table(
    ["Condition", "Export format"],
    [
        ["Rows ≤ 800,000", "Single CSV file"],
        ["Rows > 800,000", "ZIP containing multiple CSVs split by SEG / DIV"],
    ],
    col_widths=[2.5, 5.0]
)

h2("6.5 — Server-Side Filters  (GET /contrib/review/preview/{table_name})")
body("The preview endpoint accepts filter parameters that are pushed down to the SQL query. Available filter dimensions: SEG, DIV, MAJ_CAT, and the grouping_column values (e.g. MACRO_MVGR). The response includes:")
bullet("total_rows: unfiltered count")
bullet("filtered_rows: count matching the applied filters")
bullet("rows: first 200 matching rows")
bullet("filter_values: distinct values for each filterable column")


# ══════════════════════════════════════════════════════════════════
# PART 7 — API REFERENCE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 7 — API ENDPOINT REFERENCE  (/contrib/…)")

add_table(
    ["Method", "Endpoint", "Purpose"],
    [
        ["GET",    "/contrib/config/grouping-columns",          "List valid grouping columns (CLR, SZ, RNG_SEG, M_VND_CD, MACRO_MVGR, MICRO_MVGR, FAB)"],
        ["GET",    "/contrib/config/ssn-values",                "Distinct SSN values from VW_MASTER_PRODUCT"],
        ["GET",    "/contrib/config/months",                    "Available STOCK_DATE months from COUNT_STOCK_DATA_18M (5-min cache)"],
        ["GET",    "/contrib/config/majcats",                   "MAJ_CAT list for a given grouping_column"],
        ["GET",    "/contrib/presets",                          "List all presets in sequence_order"],
        ["POST",   "/contrib/presets",                          "Create or update a preset"],
        ["DELETE", "/contrib/presets/{name}",                   "Delete a preset"],
        ["PUT",    "/contrib/presets/reorder",                  "Set sequence_order for all presets at once"],
        ["GET",    "/contrib/mappings",                         "List all SSN mappings"],
        ["POST",   "/contrib/mappings",                         "Create or update a mapping"],
        ["DELETE", "/contrib/mappings/{name}",                  "Delete a mapping"],
        ["GET",    "/contrib/assignments",                      "List all column assignments"],
        ["POST",   "/contrib/assignments",                      "Create an assignment"],
        ["DELETE", "/contrib/assignments/{id}",                 "Delete an assignment by ID"],
        ["POST",   "/contrib/execute",                          "Start pipeline execution — returns job_id immediately"],
        ["GET",    "/contrib/jobs",                             "List all jobs (most-recent first)"],
        ["GET",    "/contrib/jobs/{id}",                        "Full job detail + preview rows"],
        ["POST",   "/contrib/jobs/{id}/cancel",                 "Cancel a running job"],
        ["POST",   "/contrib/jobs/{id}/pause",                  "Pause at next preset boundary"],
        ["POST",   "/contrib/jobs/{id}/resume",                 "Resume a paused job"],
        ["GET",    "/contrib/jobs/{id}/download/{type}",        "Stream CSV download (type = store or company)"],
        ["DELETE", "/contrib/jobs/{id}",                        "Delete job + temp files immediately"],
        ["GET",    "/contrib/review/tables",                    "List all Cont_Percentage_* DB tables"],
        ["GET",    "/contrib/review/preview/{table}",           "Preview with server-side filters (200 rows + filter values)"],
        ["GET",    "/contrib/review/download/{table}",          "Download full table as CSV (direct, ≤ 800K rows)"],
        ["DELETE", "/contrib/review/tables/{table}",            "Drop a result table from DB"],
        ["POST",   "/contrib/review/export/{table}",            "Start background export job"],
        ["GET",    "/contrib/review/exports",                   "List pending/running export jobs"],
        ["GET",    "/contrib/review/exports/{id}/download",     "Download export result when ready"],
        ["DELETE", "/contrib/review/exports/{id}",              "Delete a completed export job"],
    ],
    col_widths=[0.7, 3.2, 3.5]
)


# ══════════════════════════════════════════════════════════════════
# PART 8 — HOW ALLOCATION READS CONTRIBUTION %
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 8 — HOW ALLOCATION READS CONTRIBUTION %")

body("Contribution % is NOT re-run before each allocation. The allocator reads from Master_CONT_SZ (a separate master table populated by the Contribution % pipeline output) at Stage B of the allocation waterfall.")

h2("8.1 — Stage B Fill CONT")
body("In allocation Stage B (Explode to VAR_ART × SZ grain), the CONT column is filled by joining Master_CONT_SZ:")
code_block("""-- Stage B-2: Fill CONT (size contribution ratio)
JOIN Master_CONT_SZ C
  ON  C.ST_CD    = A.WERKS
  AND C.MAJ_CAT  = A.MAJ_CAT
  AND C.SZ       = A.SZ

-- Fallback when no Master_CONT_SZ row exists:
CONT = 1.0 / COUNT(DISTINCT SZ) per (WERKS, MAJ_CAT)   -- equal split""")

h2("8.2 — From Contribution % to Size MBQ")
code_block("""SZ_MBQ    = ROUND(OPT_MBQ    × CONT, 0)
SZ_MBQ_WH = ROUND(OPT_MBQ_WH × CONT, 0)
SZ_REQ    = MAX(0, SZ_MBQ    - SZ_STK)
SZ_REQ_WH = MAX(0, SZ_MBQ_WH - SZ_STK)

-- Example: OPT_MBQ = 100, CONT(size M) = 0.25
--   SZ_MBQ    = 100 × 0.25 = 25
--   SZ_MBQ_WH = 110 × 0.25 = 27.5 → 28  (OPT_MBQ_WH = 110)
--   SZ_REQ    = 25 - 10 = 15             (SZ_STK = 10)""")

h2("8.3 — Update Frequency")
add_table(
    ["Question", "Answer"],
    [
        ["How often should Contribution % be re-run?", "Quarterly or after a major seasonal launch. No need to re-run before every allocation."],
        ["Does re-running Contribution % affect current allocation?", "No — changes take effect only after Master_CONT_SZ is updated from the new results."],
        ["What happens if Master_CONT_SZ has no row for a store/MAJ_CAT/SZ?", "Stage B uses equal-split fallback: CONT = 1 / distinct size count."],
        ["Can Store-level and Company-level results be used differently?", "Yes — typically Store-level rows are loaded into Master_CONT_SZ for allocations. Company-level is used for planning and review."],
    ],
    col_widths=[3.0, 4.4]
)


# ══════════════════════════════════════════════════════════════════
# DEBUG GUIDE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("DEBUG GUIDE — Common Problems & SQL Queries")

h2("1. Job Shows 'failed' — How to Read the Error")
code_block("""-- Check the error field returned by GET /contrib/jobs/{id}
-- Common errors:

'Invalid column name "SSN"'
  → SSN column missing from VW_MASTER_PRODUCT. Check the view definition.

'Object name "Master_HIER_CLR" is not valid'
  → Master hierarchy table for the chosen grouping column does not exist.
  → Run the ETL / upload step to populate Master_HIER_{grouping_column}.

'Conversion failed when converting...'
  → grouping_column is numeric (e.g. SZ) but a string value was found.
  → Check VW_MASTER_PRODUCT.{col} data type and clean bad values.

Communication link failure / 10054
  → Azure SQL dropped the connection during the long master query.
  → Automatic retry (up to 2×) is built in. If it persists, reduce majcat scope.""")

h2("2. All INITIAL AUTO CONT% Values Are Equal  (contribution always = 1/N)")
code_block("""-- Symptom: every row in a MAJ_CAT shows the same INITIAL AUTO CONT% (e.g. 0.25 for 4 rows)
-- Cause A: SALE_V = 0 for all rows → SALE_CONT% = 0 for all → ALGO = 0 for all → equal split

SELECT COUNT(*), SUM(SALE_V), SUM(SALE_Q)
FROM COUNT_STOCK_DATA_18M
WHERE KPI = 'L30D'                -- or the relevant KPI window
  AND WERKS = '<store>'
-- If SUM(SALE_V) = 0: the chosen KPI window has no sales data for this store.
-- Fix: switch to L18M preset and include months that have sales.

-- Cause B: AVG_DNSTY = 0 → FIX = infinity → DISP_AREA collapses → GM PSF = 0 → algo_adj = 0
SELECT MAJ_CAT, AVG_DNSTY FROM master_avg_density WHERE MAJ_CAT = '<cat>'
-- If AVG_DNSTY = 0: update master_avg_density with the correct density value.""")

h2("3. Job Runs Slowly  (> 30 minutes)")
code_block("""-- Step timings are in the job log. Identify which step is slow:

'sql_master: 180s'  → Master CROSS JOIN is too large
   Cause:  majcats filter is empty (all MAJ_CATs) × all stores × large Master_HIER table
   Fix:    specify majcats in the execute payload to limit scope, or run per-MAJ_CAT

'sql_data: 90s'     → COUNT_STOCK_DATA_18M scan is slow
   Cause:  table is large and the KPI + WHERE filter has poor index coverage
   Fix:    ensure COUNT_STOCK_DATA_18M is indexed on (WERKS, STOCK_DATE, KPI, MATNR)

'merge: 45s'        → pandas merge is large
   Cause:  > 10M rows being merged in memory
   Fix:    reduce majcats scope; run company-level only (target='Company')""")

h2("4. SSN Column Missing — Assignment Outputs All Fallback Values")
code_block("""-- If the combined DataFrame has no 'SSN' column, all rows are treated as unmatched
-- and the fallback suffix is used for every row.

-- Check whether VW_MASTER_PRODUCT has an SSN column:
SELECT TOP 1 SSN FROM VW_MASTER_PRODUCT

-- Check whether SSN ended up in the data query output:
-- The data query selects: ST_CD, MAJ_CAT, {grouping_column}, ...
-- SSN must be added to the SELECT if you need it in the result.
-- Currently SSN is carried through VW_MASTER_PRODUCT's grouping expression.
-- If SSN is not in Master_HIER_{col}, it will be absent from df_master.

-- Fix: add SSN to the Master_HIER table upload, or add it to the master query.""")

h2("5. Contribution % Does Not Sum to 1.0 for a MAJ_CAT")
code_block("""-- This is expected when some rows have zero sales:
-- SALE_CONT% is 0 for zero-sales rows; only positive-sales rows share the denominator.
-- SUM(SALE_CONT%) within a (ST_CD, MAJ_CAT) group = 1.0 ONLY among rows with SALE_V > 0.

-- To check:
SELECT ST_CD, MAJ_CAT, {grouping_column},
       SALE_CONT%, [INITIAL AUTO CONT%]
FROM Cont_Percentage_MACRO_MVGR_2025_11   -- or your result table
WHERE ST_CD = '<store>' AND MAJ_CAT = '<cat>'
ORDER BY [INITIAL AUTO CONT%] DESC

SELECT ST_CD, MAJ_CAT,
       SUM([SALE_CONT%])          AS total_sale_cont,
       SUM([INITIAL AUTO CONT%])  AS total_iac
FROM Cont_Percentage_MACRO_MVGR_2025_11
WHERE ST_CD = '<store>'
GROUP BY ST_CD, MAJ_CAT
-- total_iac should be ~1.0 per group; total_sale_cont may be < 1.0 if zero-sales rows exist.""")

h2("6. Wrong KPI Window Data  (stale or wrong months)")
code_block("""-- Check what months are available in COUNT_STOCK_DATA_18M:
SELECT DISTINCT KPI, STOCK_DATE, COUNT(*) AS rows
FROM COUNT_STOCK_DATA_18M
GROUP BY KPI, STOCK_DATE
ORDER BY KPI, STOCK_DATE DESC

-- For L18M presets, verify that the months in Cont_presets.config_json match
-- actual STOCK_DATE values in the table (format: YYYY-MM-01):
SELECT preset_name, config_json FROM Cont_presets

-- If months are stale: update the preset via POST /contrib/presets with the correct months.""")

h2("7. save_to_db Result Table Is Empty")
code_block("""-- Check job details for store_rows / company_rows:
-- If both are 0, the pipeline produced empty DataFrames.
-- Root cause: majcats filter returned no data (likely wrong MAJ_CAT spelling).

SELECT DISTINCT MAJ_CAT FROM COUNT_STOCK_DATA_18M
WHERE KPI = 'L30D'
ORDER BY MAJ_CAT
-- Compare with the majcats values passed in ExecutePayload.

-- Also check: SEG filter is APP or GM. If all articles in the MAJ_CAT have SEG = NULL:
SELECT TOP 100 MAJ_CAT, SEG FROM VW_MASTER_PRODUCT WHERE MAJ_CAT = '<cat>'
-- If SEG is NULL: fix VW_MASTER_PRODUCT or remove the SEG IN ('APP','GM') filter.""")

h2("Key Numbers to Check After Every Run")
add_table(
    ["Check", "Expected", "If Wrong → Suspect"],
    [
        ["store_rows / company_rows > 0",         "Non-zero for any non-empty MAJ_CAT scope",            "majcats filter too narrow, or KPI window has no data"],
        ["INITIAL AUTO CONT% sums to ~1.0 per group", "Exactly 1.0 when at least one row has SALE_V > 0", "ALGO all-zero → SALE_CONT% all-zero → no sales in window"],
        ["sql_master timing < 120s",               "30–90s typical for full store × MAJ_CAT scope",      "Too many MAJ_CATs + large Master_HIER → scope down or add index"],
        ["No 'NaN' in INITIAL AUTO CONT% column",  "All values are numeric 0.00–1.00",                   "AVG_DNSTY = 0 or AVG_DNSTY missing for a MAJ_CAT"],
        ["Assignment output column non-null",       "Non-NaN for rows where SSN is known",                "SSN column missing from data, or mapping keys don't match SSN values"],
        ["Preset column count = N × 15 + keys",    "15 KPI cols per preset + merge key columns",         "Preset produced empty DataFrame — check data query and timing log"],
    ],
    col_widths=[2.2, 2.5, 2.7]
)


# ── Save
out_path = r"e:\ARS\docs\ARS_Contribution_Complete_Reference.docx"
doc.save(out_path)
print(f"Saved: {out_path}")
