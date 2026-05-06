"""
Generate ARS Pipeline Complete Process Reference as a Word document.
Run: python docs/generate_pipeline_doc.py
Output: docs/ARS_Pipeline_Complete_Reference.docx
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# ── Page margins ──────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.2)
    section.right_margin  = Cm(2.2)

# ── Colour palette ────────────────────────────────────────────────
BLUE_DARK   = RGBColor(0x1F, 0x49, 0x7D)   # heading 1
BLUE_MID    = RGBColor(0x2E, 0x74, 0xB5)   # heading 2
BLUE_LIGHT  = RGBColor(0x5B, 0x9B, 0xD5)   # heading 3
TH_BG       = "2E74B5"                      # table header background
ALT_BG      = "DEEAF1"                      # alternating row tint
CODE_BG     = "F2F2F2"                      # code block background
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

def set_paragraph_borders(para, hex_color="5B9BD5"):
    pPr  = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    for side in ("top", "bottom", "left", "right"):
        bd = OxmlElement(f"w:{side}")
        bd.set(qn("w:val"),   "single")
        bd.set(qn("w:sz"),    "6")
        bd.set(qn("w:space"), "4")
        bd.set(qn("w:color"), hex_color)
        pBdr.append(bd)
    pPr.append(pBdr)

def h1(text):
    p = doc.add_heading(text, level=1)
    p.runs[0].font.color.rgb = WHITE
    p.runs[0].font.size      = Pt(14)
    p.runs[0].font.bold      = True
    # Blue background via paragraph shading
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
    """Add a shaded code block (monospace, grey background)."""
    for line in text.strip("\n").split("\n"):
        p   = doc.add_paragraph()
        run = p.add_run(line if line else " ")
        run.font.name  = "Courier New"
        run.font.size  = Pt(8.5)
        run.font.color.rgb = RGBColor(0x20, 0x20, 0x20)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.left_indent  = Inches(0.15)
        # grey background
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"),   "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"),  "F2F2F2")
        pPr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def add_table(headers, rows, col_widths=None):
    """Add a styled table with coloured header row and alternating tints."""
    n_cols = len(headers)
    tbl    = doc.add_table(rows=1 + len(rows), cols=n_cols)
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

    # Header row
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

    # Data rows
    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri + 1]
        bg  = ALT_BG if ri % 2 == 1 else "FFFFFF"
        for ci, val in enumerate(row_data):
            cell = row.cells[ci]
            set_cell_bg(cell, bg)
            set_cell_borders(cell, "BDD7EE")
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            p   = cell.paragraphs[0]
            # Bold first column
            run = p.add_run(str(val))
            run.font.size = Pt(9)
            if ci == 0:
                run.font.bold = True

    # Column widths
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
run = p.add_run("ARS Pipeline")
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
run = p.add_run("Listing Pipeline  ·  Allocation Pipeline  ·  Debug Guide")
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
h1("Overview — Tables in the Pipeline")

body("The ARS pipeline runs in two major phases: (1) Listing — builds ARS_LISTING with every store × OPT combination; (2) Allocation — runs the rule engine across Stages A–D to decide what to ship. Each phase writes to a dedicated table.")

add_table(
    ["Table", "Created by", "Purpose"],
    [
        ["ARS_LISTING",         "listing.py Parts 1–7",          "Full raw listing: every store × OPT combination with all metadata"],
        ["ARS_STORE_RANKING",   "listing.py Part 6",             "Per-(MAJ_CAT, WERKS) store rank (ST_RANK)"],
        ["ARS_LISTING_WORKING", "listing.py Part 7",             "Filtered copy of ARS_LISTING — only rows eligible for allocation"],
        ["ARS_NL",              "Post-allocation update (Part 7)","Holds HOLD_QTY per (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR) — updated after allocation completes. HOLD_QTY is joined back onto ARS_LISTING_WORKING before MSA_FNL_Q so the working table carries pending-hold stock for the next run."],
        ["ARS_LISTED_OPT",      "rule_engine Stage A",           "Listed OPTs (LISTED_FLAG=1 rows) with priority tier/rank"],
        ["ARS_ALLOC_WORKING",   "rule_engine Stage B",           "Exploded to VAR_ART × SZ grain — one row per store × size"],
        ["#nre_pool (temp)",    "rule_engine Stage C",           "Available pool: FNL_Q per (RDC, MAJ_CAT, GEN_ART, CLR, VAR_ART, SZ)"],
    ],
    col_widths=[1.8, 1.9, 3.7]
)

h2("Key Term Definitions")
add_table(
    ["Term", "Full Name", "Meaning / Usage"],
    [
        ["MBQ",    "Minimum Based Qty",        "The minimum quantity the store must hold for an option to maintain display coverage and cover allocation days. Drives OPT_MBQ, SZ_MBQ, and the pool need calculation."],
        ["ACS_D",  "Accessories Display Qty",  "Number of units required on the sales floor for display. Equals the I_ROD capacity. Used ONLY in the OPT_MBQ formula: OPT_MBQ = ACS_D + rate × ALC_D."],
        ["ALC_D",  "Allocation Days",          "Number of days to cover after the display quantity (ACS_D). Represents the replenishment cycle — how many days' worth of stock to send on top of the display floor fill."],
        ["I_ROD",  "Rounds of Demand",         "How many allocation rounds the option participates in. I_ROD=1 → 1 round (normal). I_ROD=2 → 2 rounds (double the monthly target). Source: ARS_CALC_ST_ART or ARS_CALC_ST_MAJ_CAT."],
        ["ALLOC_FLAG", "Allocation Override Flag", "When ALLOC_FLAG=1 on an option, Stage A Rule R06 (PRI_CT% < 100 gate) is bypassed for that row — the option is force-listed regardless of primary-grid coverage. Set in master data to manually override the listing gate."],
        ["MSA_FNL_Q", "MSA Final Quantity",    "Available pool quantity from the RDC for this option+size. Sourced from ARS_MSA_GEN_ART / ARS_MSA_VAR_ART. Must be > 0 for an option to enter allocation. If both MSA_FNL_Q=0 AND HOLD_QTY=0, the row is excluded from ARS_LISTING_WORKING."],
        ["HOLD_QTY",  "Hold Quantity",         "Stock already allocated in a previous run but sitting in transit / hold (not yet received at store). Sourced from ARS_NL table. Added to ARS_LISTING_WORKING before MSA_FNL_Q column so the engine knows what is already en-route and avoids double-ordering."],
        ["PRI_CT%",   "Primary Coverage %",    "What % of the store's primary display grid positions are covered by this option. Computed as Σ(H_grid_REM) / Σ(GH_grid) × 100. Must be ≥ 100 for the option to pass R06 (unless ALLOC_FLAG=1 or the PRI gate is turned off in the UI)."],
    ],
    col_widths=[1.1, 1.8, 4.5]
)


# ══════════════════════════════════════════════════════════════════
# PART 1 — LISTING PIPELINE
# ══════════════════════════════════════════════════════════════════
h1("PART 1 — LISTING PIPELINE  (listing.py)")

# ── Part 1
h2("Part 1 — Insert Grid Rows  (IS_NEW = 0)")
body("Pull every existing grid option (store's current range) from ARS_GRID_MJ_GEN_ART. These are options the store already carries and need replenishment.")
code_block("""INSERT INTO ARS_LISTING (WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, CLR,
                       <SLOC_cols>, STK_TTL, STR, IS_NEW, OPT_TYPE)
SELECT G.WERKS, S.RDC,
       G.MAJ_CAT, G.GEN_ART_NUMBER, G.CLR,
       <SLOC sums>,
       SUM(stock_cols)  AS STK_TTL,   -- only non-sale columns
       SUM(sale_cols)   AS STR,        -- L-7 DAYS SALE-Q etc.
       0 AS IS_NEW,
       NULL AS OPT_TYPE
FROM ARS_GRID_MJ_GEN_ART G
INNER JOIN (active stores) S ON G.WERKS = S.ST_CD
WHERE MAJ_CAT filter, SSN filter""")

add_table(
    ["Column", "Value", "Note"],
    [
        ["IS_NEW",   "0",    "Existing option — store already carries it"],
        ["STK_TTL",  "Sum of SLOC stock columns", "Sale/L-7 columns are excluded from this sum"],
        ["STR",      "Sum of sale/L-7 columns",   "Kept for reference, not used in OPT_MBQ"],
        ["OPT_TYPE", "NULL", "Tagged in Part 3.6"],
    ],
    col_widths=[1.5, 2.5, 3.4]
)

# ── Part 2
h2("Part 2 — Insert MSA New Options  (IS_NEW = 1)")
body("Pull options from ARS_MSA_GEN_ART that are not already in Part 1 for that store. These are MSA-recommended options the store does not yet carry.")
code_block("""INSERT INTO ARS_LISTING (WERKS, RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, <zeros>, STK_TTL=0, IS_NEW=1)
SELECT S.ST_CD AS WERKS, S.RDC, M.MAJ_CAT, M.GEN_ART_NUMBER, M.CLR, <zeros>
FROM ARS_MSA_GEN_ART M
INNER JOIN (active stores) S ON 1=1
WHERE NOT EXISTS (
    SELECT 1 FROM ARS_LISTING E
    WHERE E.WERKS=S.ST_CD AND E.MAJ_CAT=M.MAJ_CAT
      AND E.GEN_ART_NUMBER=M.GEN_ART_NUMBER AND E.CLR=M.CLR
)""")
note("Example: MAJ_CAT=JB_JEANS, GEN_ART=1234567, CLR=BLU is in MSA but store HB05 does not carry it → Part 2 creates a row with STK_TTL=0, IS_NEW=1.")

# ── Part 3.5
h2("Part 2.5 — Update HOLD_QTY from ARS_NL  (after allocation completes)")
body("After the allocation run finishes, ARS_NL is updated with HOLD_QTY per option per store. This column is then joined onto ARS_LISTING_WORKING and inserted BEFORE MSA_FNL_Q so the next listing run sees pending-hold stock and does not double-order it.")
code_block("""-- Post-allocation step: read HOLD_QTY from ARS_NL and stamp it onto ARS_LISTING_WORKING
UPDATE L
   SET L.HOLD_QTY = N.HOLD_QTY
FROM ARS_LISTING_WORKING L
INNER JOIN ARS_NL N
    ON  L.WERKS          = N.WERKS
    AND L.MAJ_CAT        = N.MAJ_CAT
    AND L.GEN_ART_NUMBER = N.GEN_ART_NUMBER
    AND L.CLR            = N.CLR
WHERE ISNULL(N.HOLD_QTY, 0) > 0

-- Column order in ARS_LISTING_WORKING:
--   ... | HOLD_QTY | MSA_FNL_Q | OPT_REQ_WH | ...""")
note("HOLD_QTY represents stock already dispatched but not yet received at the store. Knowing this prevents the engine from re-allocating the same stock in the next run. The column must be populated before the working table filter (MSA_FNL_Q > 0 OR HOLD_QTY > 0) is applied in Part 7.")

add_table(
    ["Column", "Source", "Meaning"],
    [
        ["HOLD_QTY",   "ARS_NL",           "Units already allocated in a prior run — in transit / hold state at store level"],
        ["MSA_FNL_Q",  "ARS_MSA_GEN_ART",  "Fresh pool available from RDC for allocation in this run"],
    ],
    col_widths=[1.5, 1.8, 4.1]
)

h2("Part 3.5 — Enrich ACS_D, ALC_D, AGE, LISTING, I_ROD, FOCUS flags")
body("Join metadata tables to populate calculated columns in three sub-steps. ART-level values from ARS_CALC_ST_ART override MAJ_CAT-level values where non-null and non-zero.")

add_table(
    ["Sub-step", "Source Table", "Columns Populated"],
    [
        ["3.5",  "ARS_CALC_ST_MAJ_CAT",  "ACS_D (display days), ALC_D (allocation days)"],
        ["3.5a", "ARS_CALC_ST_MAJ_CAT → ARS_CALC_ST_ART (override)", "LISTING (0/1 active), I_ROD (rounds of demand), CLR_MIN/MAX, FOCUS_W_CAP, FOCUS_WO_CAP"],
        ["3.5b", "MASTER_GEN_ART_SALE.SAL_PD", "AUTO_GEN_ART_SALE (planned daily sale rate)"],
        ["3.5c", "MASTER_GEN_ART_AGE",    "AGE (option age in days)"],
    ],
    col_widths=[1.2, 2.6, 3.6]
)

note("I_ROD is critical: if I_ROD=2, the option is allocated for 2 rounds (2× the monthly target). This is the root cause of over-allocation when master data contains incorrect I_ROD=2 values.")

# ── Part 3.55
h2("Part 3.55 — Pre-populate MSA_FNL_Q and VAR Counts")
body("Join ARS_MSA_GEN_ART.FNL_Q to get MSA_FNL_Q per option. Join ARS_MSA_VAR_ART to count VAR_COUNT (total sizes in MSA) and VAR_FNL_COUNT (sizes where FNL_Q > 0). Both are needed before Part 3.6 OPT_TYPE classification.")
code_block("""UPDATE L SET L.MSA_FNL_Q = M.FNL_Q
FROM ARS_LISTING L
INNER JOIN (
    SELECT MAJ_CAT, GEN_ART_NUMBER, CLR, SUM(FNL_Q) AS FNL_Q
    FROM ARS_MSA_GEN_ART
    GROUP BY MAJ_CAT, GEN_ART_NUMBER, CLR
) M ON L.MAJ_CAT=M.MAJ_CAT
   AND L.GEN_ART_NUMBER=M.GEN_ART_NUMBER
   AND L.CLR=M.CLR""")

# ── Part 3.6
h2("Part 3.6 — OPT_TYPE Classification  (4-way)")
body("Tag each row as one of MIX / RL / TBC / TBL. Evaluated top-to-bottom — first match wins. Uses configurable stock_threshold_pct (default 60%) and default_acs_d (default 18 when ACS_D is NULL or 0).")

body("Note on HOLD_QTY: HOLD_QTY (pending stock in transit from ARS_NL) is treated the same as MSA_FNL_Q for the RL rule. A store with adequate STK_TTL, OR with HOLD_QTY > 0 from a prior allocation, qualifies as RL — the system already ordered stock for it.")

add_table(
    ["Priority", "Condition", "OPT_TYPE", "Meaning"],
    [
        ["1", "STK_TTL < threshold × ACS_D  AND  MSA_FNL_Q = 0  AND  HOLD_QTY = 0",           "MIX", "Low stock, no MSA pool, no pending hold — nothing to send"],
        ["2", "VAR_COUNT > 0  AND  (VAR_FNL_COUNT / VAR_COUNT < threshold  OR  VAR_FNL_COUNT < min_size_count)", "MIX", "Poor size coverage across the option's colors"],
        ["3", "STK_TTL >= threshold × ACS_D  OR  HOLD_QTY > 0",                                "RL",  "Adequate stock, OR prior allocation already in transit — replenishment mode"],
        ["4", "STK_TTL > 0  AND  STK_TTL < threshold × ACS_D  AND  (MSA_FNL_Q > 0 OR HOLD_QTY > 0)", "TBC", "Low stock but MSA pool or hold available"],
        ["5", "STK_TTL <= 0  AND  (MSA_FNL_Q > 0 OR HOLD_QTY > 0)",                           "TBL", "Zero stock — new listing needed; MSA or prior hold exists"],
    ],
    col_widths=[1.0, 3.6, 0.7, 2.1]
)

body("Example (threshold=60%, ACS_D=20, MSA_FNL_Q=50, HOLD_QTY shown):", bold=True)
add_table(
    ["STK_TTL", "Threshold", "MSA_FNL_Q", "HOLD_QTY", "Result"],
    [
        ["15", "12", "50", "0",  "RL  (15 >= 12)"],
        ["0",  "12", "0",  "10", "RL  (HOLD_QTY > 0 — stock already en route)"],
        ["8",  "12", "50", "0",  "TBC (8 < 12, MSA > 0)"],
        ["0",  "12", "50", "0",  "TBL (0 <= 0, MSA > 0)"],
        ["8",  "12", "0",  "0",  "MIX (no MSA, no hold, low stock)"],
    ],
    col_widths=[1.0, 1.1, 1.2, 1.2, 2.9]
)

# ── Part 3.7
h2("Part 3.7 — MIX Aggregation")
body("Collapse all MIX-tagged rows per (WERKS, MAJ_CAT) into a single synthetic row: GEN_ART_NUMBER=0, CLR='MIX'. All numeric columns are summed. ACS_D and ALC_D are taken from ARS_CALC_ST_MAJ_CAT (not summed).")
note("MIX rows are excluded from Stage A listing rules (R02_NOT_MIX), so they never enter the allocation waterfall. They represent articles that cannot be cleanly allocated and are handled separately.")

# ── Part 4a
h2("Part 4a — Grid Column Joins")
body("For each active grid in ARS_GRID_BUILDER, join the grid output table onto ARS_LISTING using the hierarchy columns. Adds prefixed columns: MJ_CONT, MJ_MBQ, MJ_OPT_CNT, RNG_SEG_MBQ, etc.")
note("Optimization: hierarchy columns like MACRO_MVGR, RNG_SEG are pre-joined from vw_master_product onto listing ONCE before the grid loop. Each subsequent grid join becomes a direct key lookup, avoiding repeated 5M-row vw_master_product scans.")

add_table(
    ["Grid Name", "Hierarchy", "Columns Added (examples)"],
    [
        ["MJ",         "[WERKS, MAJ_CAT]",             "MJ_CONT, MJ_MBQ, MJ_STK_TTL, MJ_OPT_CNT, MJ_DISP_Q"],
        ["MJ_RNG_SEG", "[WERKS, MAJ_CAT, RNG_SEG]",   "RNG_SEG_CONT, RNG_SEG_MBQ, RNG_SEG_STK_TTL"],
        ["MJ_CLR",     "[WERKS, MAJ_CAT, CLR]",        "CLR_CONT, CLR_MBQ, CLR_STK_TTL"],
    ],
    col_widths=[1.5, 2.5, 3.4]
)

# ── Part 4b
h2("Part 4b — PER_OPT_SALE")
body("Computes per-option planned daily sale rate from the grid flagged use_for_opt_sale=1.")
code_block("""PER_OPT_SALE = ROUND(
    (MJ_MBQ - MJ_DISP_Q) / MJ_DISP_Q × ACS_D / ALC_D
, 2)

-- Implied velocity: how fast the option should sell based on planned buy vs display""")

# ── Part 4c
h2("Part 4c — OPT_MBQ, OPT_REQ, OPT_MBQ_WH, OPT_REQ_WH, MAX_DAILY_SALE")
body("The key financial quantities. These drive how much to allocate per option. Daily rate is selected based on article age:")

add_table(
    ["Rate", "Formula", "Used When"],
    [
        ["L7_DAILY",    "L-7 DAYS SALE-Q ÷ 7",                               "Always available"],
        ["AUTO_DAILY",  "AUTO_GEN_ART_SALE",                                  "Always available"],
        ["DEFAULT_RATE","MAX(L7_DAILY, AUTO_DAILY)",                          "Established articles: AGE >= threshold (default 15 days)"],
        ["NEW_RATE",    "MAX(PER_OPT_SALE, L7_DAILY, AUTO_DAILY)",            "New/young articles: AGE < threshold, IS_NEW=1, or AGE=NULL"],
    ],
    col_widths=[1.5, 2.8, 3.1]
)

add_table(
    ["Column", "Formula", "Purpose"],
    [
        ["OPT_MBQ",    "ROUND(ACS_D + rate × ALC_D, 0)",                              "Base monthly buying quota"],
        ["OPT_REQ",    "MAX(0, OPT_MBQ − STK_TTL)",                                   "Net requirement without hold buffer"],
        ["OPT_MBQ_WH", "ROUND(ACS_D + rate × (ALC_D + HOLD_DAYS if IS_NEW=1), 0)",   "With-hold quota — HOLD_DAYS only for new options"],
        ["OPT_REQ_WH", "MAX(0, OPT_MBQ_WH − STK_TTL)",                               "Net requirement WITH hold buffer — this is the allocation target"],
        ["MAX_DAILY_SALE", "MAX(L7_DAILY, AUTO_DAILY)",                                "Used in OPT_PRIORITY_RANK (higher velocity → higher priority)"],
    ],
    col_widths=[1.5, 3.0, 2.9]
)

body("Example (IS_NEW=1, ACS_D=20, ALC_D=30, HOLD_DAYS=7, rate=0.5, STK_TTL=0):", bold=True)
add_table(
    ["Column", "Calculation", "Value"],
    [
        ["OPT_MBQ",    "20 + 0.5×30 = 35",              "35"],
        ["OPT_REQ",    "MAX(0, 35−0)",                   "35"],
        ["OPT_MBQ_WH", "20 + 0.5×(30+7) = 38.5 → 39",  "39"],
        ["OPT_REQ_WH", "MAX(0, 39−0)",                   "39"],
    ],
    col_widths=[2.0, 3.5, 1.9]
)
note("CRITICAL: OPT_REQ_WH must be >= 1 for the row to pass into ARS_LISTING_WORKING (Part 7 filter). If this is 0, the option is silently dropped before any allocation happens. Check ACS_D, ALC_D, and sale rate when a row goes missing.")

# ── Part 4d
h2("Part 4d — ART_EXCESS / EXCESS_STK")
body("Flag stock that exceeds the excess multiplier (default 2×).")
code_block("""ART_EXCESS = MAX(0, STK_TTL - excess_multiplier × OPT_MBQ)

-- MIX rows always get ART_EXCESS = 0
-- Used internally for Part 4e REQ calculation, then dropped from output
-- EXCESS_STK is the same value, kept in the final output table""")

# ── Part 4e
h2("Part 4e — Per-Grid REQ Columns  (with ART_EXCESS deduction)")
body("For every active grid that has an MBQ column, compute the net requirement at that grid's hierarchy grain. ART_EXCESS (stock above the excess multiplier threshold) is deducted so over-stocked articles don't inflate the grid's apparent REQ.")

body("Formula:", bold=True)
code_block("""{prefix}_REQ = MAX(0, {prefix}_MBQ - {prefix}_STK_TTL)

-- ART_EXCESS (computed in Part 4d) is already baked into the effective
-- STK_TTL used here:  if STK_TTL > excess_multiplier × OPT_MBQ,
-- the excess portion is excluded so it does not inflate REQ negatively.

-- Grid grain examples:
--   MJ grid        → hierarchy [WERKS, MAJ_CAT]          → MJ_REQ
--   MJ_RNG_SEG     → hierarchy [WERKS, MAJ_CAT, RNG_SEG] → RNG_SEG_REQ
--   MJ_MACRO_MVGR  → hierarchy [WERKS, MAJ_CAT, MACRO_MVGR] → MACRO_MVGR_REQ""")

body("Detailed example:", bold=True)
body("Store HB05, MAJ_CAT = JB_JEANS, RNG_SEG = BASIC. The MJ_RNG_SEG grid has these values:")
add_table(
    ["Column", "Value", "Meaning"],
    [
        ["RNG_SEG_MBQ",      "200",  "Minimum Based Qty for BASIC range in JB_JEANS at HB05"],
        ["RNG_SEG_STK_TTL",  "120",  "Current stock for BASIC range at HB05"],
        ["ART_EXCESS (opt)", "0",    "No option has excess stock above 2× OPT_MBQ in this range"],
        ["RNG_SEG_REQ",      "MAX(0, 200 − 120) = 80", "Store needs 80 more units for BASIC range"],
    ],
    col_widths=[1.8, 1.2, 4.4]
)
body("The same store, MAJ_CAT = JB_JEANS, MACRO_MVGR = DENIM. If MJ_MACRO_MVGR grid has:")
add_table(
    ["Column", "Value", "Meaning"],
    [
        ["MACRO_MVGR_MBQ",     "150", "MBQ for DENIM macro group at HB05"],
        ["MACRO_MVGR_STK_TTL", "180", "Store is OVER-stocked in DENIM (180 > 150)"],
        ["MACRO_MVGR_REQ",     "MAX(0, 150 − 180) = 0", "No requirement — store already has enough DENIM"],
    ],
    col_widths=[1.8, 1.2, 4.4]
)
note("MJ_REQ is the most important REQ column: it is the MAJ_CAT-level store requirement used in ST_RANK computation (stores with smaller MJ_REQ rank higher — they are easier to top up completely). All per-grid REQ columns are also used in revalidation (PRI_CT_REM tracking) during Stage C.")
body("How REQ columns flow into allocation:", bold=True)
add_table(
    ["REQ Column", "Grid Hierarchy", "Used In"],
    [
        ["MJ_REQ",           "[WERKS, MAJ_CAT]",                  "ST_RANK (store ranking) + Stage C revalidation MJ_REQ_REM"],
        ["RNG_SEG_REQ",      "[WERKS, MAJ_CAT, RNG_SEG]",         "Stage C revalidation RNG_SEG_REQ_REM → H_RNG_SEG_REM → PRI_CT_REM"],
        ["MACRO_MVGR_REQ",   "[WERKS, MAJ_CAT, MACRO_MVGR]",      "Stage C revalidation MACRO_MVGR_REQ_REM → H_MACRO_MVGR_REM → PRI_CT_REM"],
    ],
    col_widths=[1.8, 2.4, 3.2]
)

# ── Part 6
h2("Part 6 — ST_RANK  (Store Ranking per MAJ_CAT)")
body("Rank every store within each MAJ_CAT based on how urgently it needs stock. Lower ST_RANK = higher priority in the allocation waterfall. Default weights: req_wt=0.4, fill_wt=0.6 (configurable in UI).")
code_block(""";WITH StoreAgg AS (
    SELECT MAJ_CAT, WERKS,
           MAX(MJ_REQ)                                   AS MJ_REQ,
           MAX(MJ_STK_TTL) / NULLIF(MAX(MJ_MBQ),0)      AS FILL_RATE
    FROM ARS_LISTING WHERE OPT_TYPE <> 'MIX' GROUP BY MAJ_CAT, WERKS
),
Ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY MAJ_CAT ORDER BY MJ_REQ ASC)    AS REQ_RANK,
           ROW_NUMBER() OVER (PARTITION BY MAJ_CAT ORDER BY FILL_RATE DESC) AS FILL_RANK
    FROM StoreAgg
)
SELECT *,
    ROUND(REQ_RANK * req_wt + FILL_RANK * fill_wt, 2) AS W_SCORE,
    ROW_NUMBER() OVER (PARTITION BY MAJ_CAT ORDER BY W_SCORE DESC) AS ST_RANK
INTO ARS_STORE_RANKING FROM Ranked""")

add_table(
    ["Component", "What it rewards"],
    [
        ["REQ_RANK low (MJ_REQ small)",   "Store needs very little → easier to fulfill completely"],
        ["FILL_RANK low (FILL_RATE high)", "Store is already well-stocked relative to its MBQ target"],
        ["W_SCORE high → ST_RANK = 1",    "Small, well-stocked store is cheapest to top up — ships first"],
    ],
    col_widths=[2.8, 4.6]
)

# ── Part 7
h2("Part 7 — Create ARS_LISTING_WORKING  (Filtered Copy)")
body("Copy ARS_LISTING → ARS_LISTING_WORKING, keeping only rows that pass all filters and a controlled set of columns (_FINAL_KEEP_COLS). Raw SLOC columns are dropped here to reduce table width.")

code_block("""WHERE (ISNULL(MSA_FNL_Q, 0) > 0 OR ISNULL(HOLD_QTY, 0) > 0)  -- pool OR pending hold
  AND ISNULL(OPT_REQ_WH, 0) >= 1                                -- net requirement is positive
  AND ISNULL(TRY_CAST(LISTING AS INT), 1) = 1                   -- article is active
  AND (OPT_TYPE <> 'TBL' OR ...)                                -- TBL: size coverage check""")

add_table(
    ["Filter", "Condition", "Rows Dropped When..."],
    [
        ["Pool OR hold exists", "MSA_FNL_Q > 0  OR  HOLD_QTY > 0",           "Both MSA pool is empty AND no pending hold from prior run"],
        ["Positive requirement", "OPT_REQ_WH >= 1",                           "Store already has enough (or ACS_D/ALC_D bad data gives OPT_MBQ_WH = 0)"],
        ["Size coverage (TBL only)", "VAR_FNL_COUNT/VAR_COUNT >= threshold OR count >= min_size_count", "TBL needs sufficient size coverage — RL/TBC skip this check"],
        ["Listing active",    "LISTING = 1",                                   "Article is administratively unlisted (disabled in master data)"],
    ],
    col_widths=[1.8, 2.6, 3.0]
)
note("The OR HOLD_QTY > 0 addition in the filter ensures that options with pending hold stock (from ARS_NL) are not silently dropped even when MSA_FNL_Q is temporarily 0. Without this, a store with stock in transit would lose the option from the next run's working table and could re-order unnecessarily.")


# ══════════════════════════════════════════════════════════════════
# PART 2 — ALLOCATION PIPELINE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("PART 2 — ALLOCATION PIPELINE  (rule_engine_new.py / rule_engine_pandas.py)")
body("Entry point: run_listing_and_allocation(conn, working_table='ARS_LISTING_WORKING', ...)")
body("The allocation pipeline runs in four stages: A (list OPTs) → B (explode to sizes) → C (waterfall allocation) → D (reflect results back).")


# ── Stage A
h2("Stage A — List OPTs")

h3("A-1: Add / Reset Columns")
body("Idempotently adds columns to ARS_LISTING_WORKING if missing, then resets them to initial values on rerun.")

add_table(
    ["Column", "Type", "Purpose"],
    [
        ["LISTED_FLAG",       "INT",         "1 = passes all rules; 0 = blocked"],
        ["LISTED_REASON",     "NVARCHAR",    "Concatenated rule codes that blocked the row"],
        ["OPT_PRIORITY_TIER", "INT",         "1/2/3 focus bucket"],
        ["OPT_PRIORITY_RANK", "INT",         "Per-(WERKS, OPT_TYPE) priority position"],
        ["ALLOC_QTY",         "FLOAT",       "Final ship quantity (written by Stage D)"],
        ["HOLD_QTY",          "FLOAT",       "Hold quantity (written by Stage D)"],
        ["ALLOC_STATUS",      "NVARCHAR(50)","PENDING / ALLOCATED / PARTIAL / SKIPPED / INELIGIBLE"],
        ["ALLOC_REMARKS",     "NVARCHAR",    "Debug summary string"],
    ],
    col_widths=[1.8, 1.2, 4.4]
)

h3("A-2: Apply Rules  (R01 – R09)")
body("Rules are concatenated into a single LISTED_REASON string. LISTED_FLAG = 1 only when the reason string is empty (all rules pass).")

add_table(
    ["Rule", "Condition that BLOCKS the row", "Reason Code"],
    [
        ["R01", "LISTING <> 1",                                                                              "R01_LISTING"],
        ["R02", "OPT_TYPE = 'MIX'",                                                                         "R02_NOT_MIX"],
        ["R04", "MSA_FNL_Q <= 0  AND  HOLD_QTY <= 0   (both must be zero to block)",                        "R04_MSA_POS"],
        ["R05", "OPT_REQ_WH < 1",                                                                           "R05_REQ_POS"],
        ["R06", "PRI_CT% < 100  AND  ALLOC_FLAG <> 1  AND  OPT_TYPE in enforced set",                       "R06_PRI_100"],
        ["R07", "TBL  AND  VAR_FNL_COUNT/VAR_COUNT < threshold  AND  count < min_size",                     "R07_VAR_RATIO_TBL"],
        ["R09", "TBL  AND  MJ_REQ < 0.5 × MAX_DAILY_SALE",                                                  "R09_TBL_TRIVIAL"],
    ],
    col_widths=[0.7, 4.5, 2.2]
)
note("R04 uses OR logic: a row is only blocked when BOTH MSA_FNL_Q = 0 AND HOLD_QTY = 0. If either has a positive value, the row passes R04. This ensures that options with pending hold stock (ARS_NL) are not blocked just because the current MSA pool is temporarily empty.")
note("R06 scope: TBL always enforces PRI_CT% >= 100. RL and TBC enforce it only when pri_ct_check_rl / pri_ct_check_tbc = True (UI checkboxes). ALLOC_FLAG=1 bypasses R06 entirely for that option regardless of PRI_CT%. When the PRI gate is unchecked, RL/TBC rows pass R06, but the MBQ cap then applies.")
note("R03 (OPT_TYPE = NL) has been removed. NL-type options are handled upstream before listing; they no longer appear in ARS_LISTING_WORKING.")

h3("A-3: Assign OPT_PRIORITY_TIER")
code_block("""OPT_PRIORITY_TIER =
    CASE WHEN FOCUS_WO_CAP = 1 THEN 1   -- focus without cap  (highest priority)
         WHEN FOCUS_W_CAP  = 1 THEN 2   -- focus with cap
         ELSE 3 END                      -- regular
WHERE LISTED_FLAG = 1""")

h3("A-4: Assign OPT_PRIORITY_RANK")
body("Partition: (WERKS, OPT_TYPE) — each store gets an independent 1..N rank list per OPT_TYPE bucket. ST_RANK is NOT in this ORDER BY because it is constant within a (WERKS, OPT_TYPE) partition.")

add_table(
    ["Priority", "Column", "Direction", "Meaning"],
    [
        ["1st", "OPT_PRIORITY_TIER",  "ASC",  "Focus items (Tier 1) rank before regular (Tier 3)"],
        ["2nd", "SEC_CT%",            "DESC", "Higher secondary grid contribution % first"],
        ["3rd", "MAX_DAILY_SALE",     "DESC", "Higher sales velocity first"],
        ["4th", "OPT_REQ_WH",         "DESC", "Larger requirement first"],
    ],
    col_widths=[0.8, 2.0, 1.0, 3.6]
)

h3("A-5: Materialize ARS_LISTED_OPT")
body("Copy LISTED_FLAG=1 rows from ARS_LISTING_WORKING into ARS_LISTED_OPT. This is the clean, narrow input to Stage B containing only eligible options with priority metadata.")


# ── Stage B
h2("Stage B — Explode to VAR_ART × SZ")

h3("B-1: Explode (ARS_LISTED_OPT × ARS_MSA_VAR_ART → ARS_ALLOC_WORKING)")
body("Join ARS_LISTED_OPT × ARS_MSA_VAR_ART on (MAJ_CAT, GEN_ART_NUMBER, CLR, RDC) where FNL_Q > 0. Result: one row per (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ).")

add_table(
    ["Column", "Initial Value", "Purpose"],
    [
        ["VAR_ART",       "from ARS_MSA_VAR_ART", "Variant article number"],
        ["SZ",            "from ARS_MSA_VAR_ART", "Size code (S/M/L/XL, numeric, etc.)"],
        ["FNL_Q",         "from ARS_MSA_VAR_ART", "MSA pool available for this size from RDC"],
        ["FNL_Q_REM",     "= FNL_Q",              "Running remaining pool — decremented by Stage C"],
        ["CONT",          "NULL → filled in B-2",  "Size contribution ratio (fraction of OPT_MBQ)"],
        ["SZ_MBQ / SZ_MBQ_WH", "NULL → filled in B-3", "Per-size monthly quota"],
        ["POOL_CONSUMED", "0",                    "Total taken from pool across all rounds"],
        ["SHIP_QTY / HOLD_QTY", "0",             "Accumulated allocations — updated by Stage C"],
        ["ALLOC_STATUS",  "'PENDING'",            "Updated by Stage C"],
    ],
    col_widths=[1.8, 2.2, 3.4]
)

h3("B-2: Fill CONT  (Size Contribution Ratio)")
body("Join Master_CONT_SZ on (ST_CD=WERKS, MAJ_CAT, SZ). Fallback: 1 / count(distinct SZ) per (WERKS, MAJ_CAT) for unmatched sizes.")
body("CONT is the fraction of OPT_MBQ that belongs to this size. Example: size M in MAJ_CAT JB_JEANS might have CONT=0.25 (25% of total MBQ).")

h3("B-3: Fill Size Targets")
code_block("""SZ_MBQ    = ROUND(OPT_MBQ    × CONT, 0)
SZ_MBQ_WH = ROUND(OPT_MBQ_WH × CONT, 0)
SZ_STK    = from ARS_GRID_MJ_VAR_ART if available, else 0
SZ_REQ    = MAX(0, SZ_MBQ    - SZ_STK)
SZ_REQ_WH = MAX(0, SZ_MBQ_WH - SZ_STK)""")

body("Example (CONT=0.25, OPT_MBQ=100, OPT_MBQ_WH=110, SZ_STK=10):", bold=True)
add_table(
    ["Column", "Calculation", "Value"],
    [
        ["SZ_MBQ",    "100 × 0.25",             "25"],
        ["SZ_MBQ_WH", "110 × 0.25 = 27.5 → 28", "28"],
        ["SZ_REQ",    "25 − 10",                 "15"],
        ["SZ_REQ_WH", "28 − 10",                 "18"],
    ],
    col_widths=[2.0, 3.5, 1.9]
)


# ── Stage C
h2("Stage C — Allocate  (Pool Waterfall)")

h3("C-0: Build Pool  (#nre_pool)")
code_block("""SELECT RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ,
       MAX(ISNULL(FNL_Q,0)) AS FNL_Q_ORIG,
       MAX(ISNULL(FNL_Q,0)) AS FNL_Q_REM
INTO #nre_pool
FROM ARS_ALLOC_WORKING
GROUP BY RDC, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ

-- One row per unique physical size.
-- FNL_Q_REM is decremented as stores take from the pool.""")

h3("C-1: Waterfall Outer Loop Order")
code_block("""For opt_type in [RL, TBC, TBL]:           ← allocation type order (RL first)
  For round r in 1..MAX(I_ROD):           ← rounds of demand (most rows: 1 round)
    For band rank from min_rank to max_rank (BAND_SIZE=1, one rank at a time):
      _stage_c_run_band(opt_type, round, rank_band)
      _revalidate_after_band(...)          ← update REQ_REM, PRI_CT_REM, skip flags""")

h3("C-2: Per-Band Allocation SQL  (the waterfall core)")
body("For one band (one priority rank), the SQL runs a CTE chain that computes need → ranks by store → applies cumulative window → writes SHIP/HOLD:")
code_block(""";WITH Target AS (
    -- How much each row needs from the pool in this round:
    SELECT A.WERKS, A.RDC, A.MAJ_CAT, ...,
           -- need_pool: total requirement including hold buffer
           CASE WHEN r*SZ_MBQ_WH - SZ_STK > POOL_CONSUMED
                THEN r*SZ_MBQ_WH - SZ_STK - POOL_CONSUMED ELSE 0 END AS need_pool,
           -- need_ship: requirement without hold (display stock only)
           CASE WHEN r*SZ_MBQ - SZ_STK > SHIP_QTY
                THEN r*SZ_MBQ - SZ_STK - SHIP_QTY ELSE 0 END AS need_ship
    FROM ARS_ALLOC_WORKING A
    WHERE OPT_TYPE = ot AND OPT_PRIORITY_RANK BETWEEN band_start AND band_end
      AND ALLOC_STATUS NOT IN ('SKIPPED','INELIGIBLE') AND I_ROD >= r
),
Ranked AS (
    -- Order stores within each pool key: best ST_RANK first, then OPT_PRIORITY_RANK
    SELECT T.*, P.FNL_Q_REM,
           ROW_NUMBER() OVER (
               PARTITION BY T.RDC, T.MAJ_CAT, T.GEN_ART_NUMBER, T.CLR, T.VAR_ART, T.SZ
               ORDER BY ISNULL(T.ST_RANK,999999) ASC,   -- store rank first
                        T.OPT_PRIORITY_RANK ASC          -- then OPT priority
           ) AS ord
    FROM Target T INNER JOIN #nre_pool P ON pool_key_match
    WHERE T.need_pool > 0 AND P.FNL_Q_REM > 0
),
Cum AS (
    -- Running cumulative demand in pool-taking order
    SELECT *, SUM(need_pool) OVER (PARTITION BY pool_key ORDER BY ord) AS cum_demand
    FROM Ranked
),
Take AS (
    -- Actual take: capped at remaining pool
    SELECT *,
           CASE WHEN FNL_Q_REM-(cum_demand-need_pool) <= 0      THEN 0
                WHEN FNL_Q_REM-(cum_demand-need_pool) >= need_pool THEN need_pool
                ELSE FNL_Q_REM-(cum_demand-need_pool) END AS take_pool
    FROM Cum
)
UPDATE A SET
    POOL_CONSUMED += take_pool,
    -- IS_NEW=1: split take_pool into SHIP (display) and HOLD (transit)
    -- IS_NEW=0: all goes to SHIP
    ROUND_SHIP = CASE WHEN IS_NEW=1 THEN MIN(take_pool, need_ship) ELSE take_pool END,
    ROUND_HOLD = CASE WHEN IS_NEW=1 THEN take_pool - ROUND_SHIP   ELSE 0 END,
    SHIP_QTY  += ROUND_SHIP,
    HOLD_QTY  += ROUND_HOLD""")

h3("SHIP vs HOLD Split")
add_table(
    ["IS_NEW", "SHIP_QTY", "HOLD_QTY", "Reason"],
    [
        ["0 (existing option)", "All of take_pool",              "0",                       "Store already has display — just replenish"],
        ["1 (new option)",      "MIN(take_pool, need_ship)",     "Remainder of take_pool",  "Fill display first, then buffer for transit days"],
    ],
    col_widths=[1.6, 2.1, 1.8, 2.0]
)

h3("C-3: Pool Competition Example")
body("MAJ_CAT = JB_JEANS, size M, pool has FNL_Q_REM = 30. Three stores all want size M at OPT_PRIORITY_RANK = 1:")
add_table(
    ["Store", "OPT_PRIORITY_RANK", "ST_RANK", "need_pool", "ord", "cum_demand", "take_pool", "Result"],
    [
        ["HB07", "1", "1", "15", "1", "15", "15",        "Full"],
        ["HB05", "1", "2", "18", "2", "33", "30−15=15",  "Partial"],
        ["HB12", "5", "3", "20", "3", "53", "0",         "SKIPPED / NO_POOL"],
    ],
    col_widths=[0.8, 1.5, 0.9, 1.0, 0.5, 1.3, 1.2, 1.2]
)

h3("C-4: Revalidation After Each Band")
body("After each band allocates, shadow _REM columns on ARS_LISTING_WORKING are updated to track how much resource has been consumed:")

add_table(
    ["Step", "What happens", "Effect"],
    [
        ["(1)", "MSA_FNL_Q_REM -= ROUND_SHIP + ROUND_HOLD",              "Depletes the OPT's available pool in working table"],
        ["(2)", "{grid}_REQ_REM -= ROUND_SHIP",                           "Depletes grid-level requirement for this store"],
        ["(3)", "H_{grid}_REM = (REQ_REM > ACS_SKIP_FACTOR×ACS_D) AND GH=1", "Recomputes binary grid coverage flag"],
        ["(4)", "PRI_CT_REM = Σ(H_REM)/Σ(GH) × 100",                    "Recomputes primary grid coverage %"],
        ["(5a)","ALLOC_STATUS='SKIPPED' where MSA_FNL_Q_REM <= 0",       "Skip OPT: pool for this option exhausted"],
        ["(5b)","ALLOC_STATUS='SKIPPED' where PRI_CT_REM < 100",         "Skip OPT: primary grid coverage now broken"],
        ["(5c)","ALLOC_STATUS='SKIPPED' where MJ_REQ_REM < factor×ACS_D","Skip remaining OPTs for this store in this OPT_TYPE"],
        ["(6)", "Propagate SKIP to ARS_ALLOC_WORKING",                    "Prevents skipped rows appearing in next band's Target CTE"],
    ],
    col_widths=[0.6, 3.2, 3.6]
)

h3("MBQ Cap  (when PRI gate is OFF)")
body("After all rounds for an OPT_TYPE complete, the cap clips SHIP_QTY per store:")
code_block("""budget_per_store = MAX(0, cap_pct/100 × MJ_MBQ - MJ_STK_TTL)

-- Rows are ordered by OPT_PRIORITY_RANK ASC (highest priority ships first).
-- Cumulative SHIP_QTY is clipped at budget.
-- Rows beyond the budget: SHIP_QTY=0, ALLOC_STATUS=SKIPPED, SKIP_REASON='MBQ_CAP'""")

h3("C-5: Final Status Classification")
add_table(
    ["Condition", "ALLOC_STATUS"],
    [
        ["SHIP_QTY + HOLD_QTY >= I_ROD × SZ_MBQ_WH − SZ_STK", "ALLOCATED (fully filled)"],
        ["SHIP_QTY > 0  (but not fully filled)",                 "PARTIAL"],
        ["SHIP_QTY = 0  AND  I_ROD × SZ_MBQ_WH <= SZ_STK",     "SKIPPED / ALREADY_STOCKED"],
        ["SHIP_QTY = 0  (all other cases)",                      "SKIPPED / NO_POOL_OR_DEMAND"],
    ],
    col_widths=[4.0, 3.4]
)


# ── Stage D
h2("Stage D — Reflect Results Back to Working Table")
body("Aggregate ARS_ALLOC_WORKING by (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR) and write totals back to ARS_LISTING_WORKING:")
code_block("""ALLOC_QTY    = SUM(SHIP_QTY)
HOLD_QTY     = SUM(HOLD_QTY)
ALLOC_STATUS = 'ALLOCATED' if all sizes filled
             = 'PARTIAL'   if some sizes filled
             = 'NOT_ALLOCATED' if none filled
ALLOC_REMARKS = 'ship=X; hold=Y; sizes=A/B'

-- Rows with LISTED_FLAG=0 get ALLOC_STATUS='INELIGIBLE'""")


# ══════════════════════════════════════════════════════════════════
# DEBUG GUIDE
# ══════════════════════════════════════════════════════════════════
doc.add_page_break()
h1("DEBUG GUIDE — SQL Queries to Diagnose Wrong Results")

h2("1. Check Row Counts at Each Stage")
code_block("""SELECT 'ARS_LISTING'         AS tbl, COUNT(*) AS rows FROM ARS_LISTING         UNION ALL
SELECT 'ARS_LISTING_WORKING' AS tbl, COUNT(*) AS rows FROM ARS_LISTING_WORKING UNION ALL
SELECT 'ARS_LISTED_OPT'      AS tbl, COUNT(*) AS rows FROM ARS_LISTED_OPT      UNION ALL
SELECT 'ARS_ALLOC_WORKING'   AS tbl, COUNT(*) AS rows FROM ARS_ALLOC_WORKING""")

h2("2. OPT_TYPE Distribution  (after Part 3.6)")
code_block("""SELECT OPT_TYPE, IS_NEW, COUNT(*) AS cnt
FROM ARS_LISTING
GROUP BY OPT_TYPE, IS_NEW
ORDER BY OPT_TYPE, IS_NEW""")

h2("3. Why is an OPT Showing Wrong OPT_TYPE?")
code_block("""SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, OPT_TYPE,
       STK_TTL, ACS_D, MSA_FNL_Q, VAR_COUNT, VAR_FNL_COUNT,
       0.6 * ISNULL(ACS_D, 18) AS threshold_60pct
FROM ARS_LISTING
WHERE GEN_ART_NUMBER = <your_art> AND WERKS = '<store>'

-- Check: Is ACS_D NULL or 0? → falls back to 18
-- Check: Is MSA_FNL_Q NULL or 0? → forces MIX or RL path""")

h2("4. Why Was an OPT Dropped  (LISTED_FLAG = 0)?")
code_block("""SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, OPT_TYPE,
       OPT_REQ_WH, MSA_FNL_Q, [PRI_CT%], LISTED_REASON
FROM ARS_LISTING_WORKING
WHERE LISTED_FLAG = 0 AND WERKS = '<store>'
ORDER BY LISTED_REASON""")

add_table(
    ["Reason Code", "Root Cause to Check"],
    [
        ["R04_MSA_POS",     "MSA_FNL_Q = 0 — check ARS_MSA_GEN_ART for this option"],
        ["R05_REQ_POS",     "OPT_REQ_WH < 1 — check ACS_D, ALC_D, daily rate, hold_days"],
        ["R06_PRI_100",     "PRI_CT% < 100 — check H_MJ / GH_MJ columns on working table"],
        ["R07_VAR_RATIO_TBL","VAR_FNL_COUNT low — check ARS_MSA_VAR_ART size coverage"],
        ["R01_LISTING",     "LISTING flag is 0 — check ARS_CALC_ST_MAJ_CAT or ARS_CALC_ST_ART"],
    ],
    col_widths=[2.0, 5.4]
)

h2("5. Why is Allocation Showing 0 for a Listed OPT?")
code_block("""SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, VAR_ART, SZ,
       FNL_Q, SHIP_QTY, HOLD_QTY, ALLOC_STATUS, SKIP_REASON,
       SZ_MBQ_WH, SZ_STK, POOL_CONSUMED
FROM ARS_ALLOC_WORKING
WHERE GEN_ART_NUMBER = <your_art> AND WERKS = '<store>'
ORDER BY SZ""")

add_table(
    ["SKIP_REASON", "What it Means"],
    [
        ["NO_POOL_OR_DEMAND",  "FNL_Q was 0, or pool was exhausted by higher-priority stores before this store's turn"],
        ["ALREADY_STOCKED",    "SZ_STK >= I_ROD × SZ_MBQ_WH — store already has this size over-stocked"],
        ["REVALIDATION_SKIP",  "PRI_CT_REM dropped below 100 after a previous OPT was allocated"],
        ["MBQ_CAP",            "Store hit its MBQ budget (cap feature) — total SHIP_QTY would exceed cap_pct% of MJ_MBQ"],
    ],
    col_widths=[2.0, 5.4]
)

h2("6. Who Consumed the Pool for an OPT?")
code_block("""-- Which stores took stock from a specific size pool (and in what order)?
SELECT WERKS, ST_RANK, OPT_PRIORITY_RANK,
       SHIP_QTY, HOLD_QTY, ALLOC_STATUS, SKIP_REASON
FROM ARS_ALLOC_WORKING
WHERE GEN_ART_NUMBER = <your_art>
  AND CLR = '<color>'
  AND VAR_ART = <var_art>
  AND SZ = '<size>'
ORDER BY ISNULL(ST_RANK, 999999), OPT_PRIORITY_RANK""")

h2("7. Check Over-Allocation  (I_ROD Issue)")
code_block("""-- Stores and OPTs where I_ROD > 1 (these get 2× monthly allocation)
SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, I_ROD, OPT_MBQ, OPT_REQ_WH,
       ALLOC_QTY, ALLOC_QTY / NULLIF(OPT_REQ_WH, 0) AS alloc_ratio
FROM ARS_LISTING_WORKING
WHERE LISTED_FLAG = 1 AND I_ROD > 1
ORDER BY ALLOC_QTY DESC""")

h2("8. Check ST_RANK Distribution  (Store Ranking Sanity)")
code_block("""SELECT TOP 20 WERKS, MJ_REQ, FILL_RATE, REQ_RANK, FILL_RANK, W_SCORE, ST_RANK
FROM ARS_STORE_RANKING
WHERE MAJ_CAT = '<your_majcat>'
ORDER BY ST_RANK""")

h2("9. Check PRI_CT% for a Store")
code_block("""SELECT WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR, OPT_TYPE,
       [PRI_CT%], H_MJ, GH_MJ, PRI_CT_REM, LISTED_FLAG, LISTED_REASON
FROM ARS_LISTING_WORKING
WHERE WERKS = '<store>' AND MAJ_CAT = '<cat>'
ORDER BY OPT_PRIORITY_RANK""")

h2("10. Final Summary by MAJ_CAT")
code_block("""SELECT MAJ_CAT,
       SUM(CASE WHEN LISTED_FLAG=1 THEN 1 ELSE 0 END)                AS listed,
       SUM(CASE WHEN ALLOC_STATUS='ALLOCATED'     THEN 1 ELSE 0 END) AS allocated,
       SUM(CASE WHEN ALLOC_STATUS='PARTIAL'       THEN 1 ELSE 0 END) AS partial,
       SUM(CASE WHEN ALLOC_STATUS='NOT_ALLOCATED' THEN 1 ELSE 0 END) AS not_alloc,
       SUM(CASE WHEN ALLOC_STATUS='INELIGIBLE'    THEN 1 ELSE 0 END) AS ineligible,
       SUM(ISNULL(ALLOC_QTY, 0)) AS total_ship,
       SUM(ISNULL(HOLD_QTY, 0))  AS total_hold
FROM ARS_LISTING_WORKING
GROUP BY MAJ_CAT
ORDER BY total_ship DESC""")


# ── Final sanity table
h2("Key Numbers to Sanity-Check After Every Run")
add_table(
    ["Check", "Expected", "If Wrong → Suspect"],
    [
        ["ARS_LISTING rows",         "Grid rows + MSA-new rows (shown in session logs)",     "SSN/MAJ_CAT filter in Part 1/2"],
        ["ARS_LISTING_WORKING <= ARS_LISTING", "Filtered by MSA_FNL_Q>0 and OPT_REQ_WH>=1", "NULL ACS_D or ALC_D data — OPT_MBQ_WH comes out 0"],
        ["ARS_LISTED_OPT <= ARS_LISTING_WORKING", "Only LISTED_FLAG=1 rows",                "Rules R01–R09 — run query #4 above"],
        ["ARS_ALLOC_WORKING >> ARS_LISTED_OPT", "5–20× (one row per size)",                  "Stage B explode join missing — check ARS_MSA_VAR_ART"],
        ["ALLOC_QTY ≈ OPT_REQ_WH",  "Deviations = pool shortage or cap triggered",          "Pool availability in ARS_MSA_GEN_ART / ARS_MSA_VAR_ART"],
        ["No ALLOC_QTY > 2 × OPT_REQ_WH", "No row should exceed 2× the requirement",       "I_ROD=2 in master data — check ARS_CALC_ST_ART"],
    ],
    col_widths=[2.2, 2.5, 2.7]
)

# ── Save
out_path = r"e:\ARS\docs\ARS_Pipeline_Complete_Reference_v2.docx"
doc.save(out_path)
print(f"Saved: {out_path}")
