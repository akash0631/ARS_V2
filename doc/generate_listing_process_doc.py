"""
Generates LISTING_PROCESS_Lifecycle.docx — layman-language end-to-end
walkthrough of the COMPLETE ARS V2 listing process: from a planner clicking
Generate to a permanently approved alloc-history row, covering every Part
(1, 2, 2.5, 3.5a-c, 3.55, 3.6, 3.7, 4 pre-resolve, 4a-e, 5, 6, 7, 8, 8.4,
8.5, 8.6) plus session capture, the post-run tables-affected sweep, the
park-then-promote validation gate, and TTL purge.

Includes:
  - TL;DR cheat sheet
  - 17-stage narrative with a worked numerical example
  - end-to-end flowchart (boxes + arrows in native Word shapes/tables)
  - state-of-each-table cheat-sheet across stages
  - per-Part process-step checklists
  - configuration variables reference
  - common confusions Q&A
  - troubleshooting matrix
  - implementation references (file:line)

Style mirrors doc/generate_hold_qty_doc.py and doc/generate_parked_alloc_doc.py.
Run:    python doc/generate_listing_process_doc.py
Output: doc/LISTING_PROCESS_Lifecycle.docx
"""
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ─── Style helpers ──────────────────────────────────────────────────────────
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY_TEXT = RGBColor(0x55, 0x55, 0x55)


def shade_cell(cell, hex_fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def set_cell_borders(cell, color="BFBFBF", sz="4"):
    tc_pr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), sz)
        b.set(qn("w:color"), color)
        tcBorders.append(b)
    tc_pr.append(tcBorders)


def add_hr(doc):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:color"), "808080")
    pBdr.append(bottom)
    pPr.append(pBdr)


def add_para(doc, text, *, bold=False, italic=False, size=11, color=None,
             align=None, space_after=4, mono=False):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    if mono:
        run.font.name = "Consolas"
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p


def add_h(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = NAVY
    return h


def add_bullets(doc, items, *, style="List Bullet", size=11):
    for it in items:
        p = doc.add_paragraph(style=style)
        run = p.add_run(it)
        run.font.size = Pt(size)
        p.paragraph_format.space_after = Pt(2)


def add_numbered(doc, items, size=11):
    for it in items:
        p = doc.add_paragraph(style="List Number")
        run = p.add_run(it)
        run.font.size = Pt(size)
        p.paragraph_format.space_after = Pt(2)


def add_callout(doc, label, body, fill_hex):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.autofit = True
    cell = tbl.cell(0, 0)
    shade_cell(cell, fill_hex)
    set_cell_borders(cell)
    p1 = cell.paragraphs[0]
    r1 = p1.add_run(label + "  ")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = NAVY
    r2 = p1.add_run(body)
    r2.font.size = Pt(11)
    doc.add_paragraph()


def info_box(doc, body):
    add_callout(doc, "IN PLAIN ENGLISH →", body, "DDEBF7")


def warn_box(doc, body):
    add_callout(doc, "WATCH OUT →", body, "FCE4D6")


def tip_box(doc, body):
    add_callout(doc, "TIP →", body, "E2EFDA")


def code_block(doc, text, lang_label=""):
    """Monospace shaded block for SQL / Python / DDL snippets."""
    tbl = doc.add_table(rows=1, cols=1)
    cell = tbl.cell(0, 0)
    shade_cell(cell, "F2F2F2")
    set_cell_borders(cell, color="DCDCDC")
    if lang_label:
        p = cell.paragraphs[0]
        r = p.add_run(lang_label)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = GREY_TEXT
        cell.add_paragraph()
    code_p = cell.add_paragraph()
    code_p.paragraph_format.space_after = Pt(0)
    for line in text.splitlines():
        r = code_p.add_run(line + "\n")
        r.font.name = "Consolas"
        r.font.size = Pt(9)
    doc.add_paragraph()


def make_table(doc, headers, rows, col_widths_in=None,
               header_fill="1F3A5F", header_color=(255, 255, 255), zebra=True):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.autofit = True
    if col_widths_in:
        for i, w in enumerate(col_widths_in):
            for c in tbl.columns[i].cells:
                c.width = Inches(w)
    # Header
    for i, h in enumerate(headers):
        c = tbl.cell(0, i)
        shade_cell(c, header_fill)
        set_cell_borders(c)
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(*header_color)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    # Body
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            c = tbl.cell(ri + 1, ci)
            if zebra and (ri % 2 == 1):
                shade_cell(c, "F7F7F7")
            set_cell_borders(c)
            p = c.paragraphs[0]
            r = p.add_run(str(val))
            r.font.size = Pt(10)
            c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    doc.add_paragraph()


# ─── Flowchart helpers ──────────────────────────────────────────────────────
def flow_node(doc, title, subtitle=None, fill="DDEBF7", border="4F81BD"):
    """A single-cell shaded box used as a flowchart node."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cell = tbl.cell(0, 0)
    cell.width = Inches(5.2)
    shade_cell(cell, fill)
    set_cell_borders(cell, color=border, sz="8")
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(title)
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = NAVY
    if subtitle:
        sp = cell.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sp.paragraph_format.space_after = Pt(0)
        sr = sp.add_run(subtitle)
        sr.italic = True
        sr.font.size = Pt(9)
        sr.font.color.rgb = GREY_TEXT


def flow_arrow(doc, label="▼"):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(label)
    r.font.size = Pt(14)
    r.bold = True
    r.font.color.rgb = NAVY


def flow_branch(doc, left_title, left_subtitle, right_title, right_subtitle,
                left_fill="E2EFDA", right_fill="FCE4D6",
                left_border="70AD47", right_border="C00000"):
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for ci, (title, subtitle, fill, border) in enumerate([
        (left_title, left_subtitle, left_fill, left_border),
        (right_title, right_subtitle, right_fill, right_border),
    ]):
        cell = tbl.cell(0, ci)
        cell.width = Inches(2.8)
        shade_cell(cell, fill)
        set_cell_borders(cell, color=border, sz="8")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(11)
        r.font.color.rgb = NAVY
        sp = cell.add_paragraph()
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sp.paragraph_format.space_after = Pt(0)
        sr = sp.add_run(subtitle)
        sr.italic = True
        sr.font.size = Pt(9)
        sr.font.color.rgb = GREY_TEXT


# ─── Document body ──────────────────────────────────────────────────────────
def build_doc(out_path: Path):
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    # ── Title block ────────────────────────────────────────────────────────
    title = doc.add_heading(
        "Listing Process — Complete End-to-End Lifecycle", level=0)
    for r in title.runs:
        r.font.color.rgb = NAVY

    add_para(doc,
             "Click Generate → Parts 1–8 → Park → Validate → Approve / Reject; "
             "the complete walkthrough",
             italic=True, size=12, color=(0x55, 0x55, 0x55),
             align=WD_ALIGN_PARAGRAPH.LEFT)
    add_para(doc,
             "ARS V2 Retail Auto Replenishment System  |  generated 2026-05-01",
             italic=True, size=9, color=(0x80, 0x80, 0x80))
    add_hr(doc)

    # ── TL;DR ──────────────────────────────────────────────────────────────
    add_h(doc, "TL;DR (one-page cheat sheet)", level=1)
    add_bullets(doc, [
        "Listing Generation = one button = 17 stages = 1–10 minutes for a typical run.",
        "Stage 0 mints a SESSION_ID and inserts a RUNNING row in ARS_LISTING_SESSIONS. The HTTP call returns immediately; work runs in a background thread.",
        "Stages 1–9 build ARS_LISTING (full result) and ARS_LISTING_WORKING (rows the allocator will touch).",
        "Stage 10 runs the rule engine (Part 8) which writes ARS_ALLOC_WORKING — the allocation plan at WERKS×MAJ_CAT×GEN_ART×CLR×SZ grain.",
        "Stage 11 (Part 8.4) snapshots ARS_ALLOC_WORKING into ARS_ALLOC_PARKED with PARK_STATUS='PARKED' so the result can be validated before it enters permanent history.",
        "Stages 12–13 (Parts 8.5 / 8.6) finalize OPT_STATUS and maintain the NL/TBL hold tracker (warehouse-side reservation; see HOLD_QTY_Lifecycle.docx).",
        "Stage 14 sweeps the 7 tracked tables, classifies each as CREATED / RECREATED / TRUNCATED, and writes the JSON onto ARS_LISTING_SESSIONS.TABLES_AFFECTED. STATUS flips to SUCCESS.",
        "Stage 15 — UI poll detects SUCCESS → toast + Tables-Affected panel + Parked Runs queue refresh.",
        "Stage 16 — planner reviews. Approve → ARS_ALLOC_HISTORY (permanent). Reject → ARS_ALLOC_PARKED with PARK_STATUS='REJECTED' for audit.",
        "Stage 17 — TTL purge: PARKED >14d and REJECTED >30d are deleted; approved history is forever.",
        "Concurrency: a second /listing/generate while one is RUNNING returns HTTP 409. One run at a time.",
        "Failure of the parking step does NOT fail the run — STATUS=SUCCESS, PARKED_STATUS='SKIPPED_ERROR', yellow warning toast.",
    ])

    # ── Section 1 ──────────────────────────────────────────────────────────
    add_h(doc, "1. What is the Listing Process?", level=1)
    info_box(doc,
             "Clicking Generate is the heart of ARS. It takes everything the "
             "planner prepared — store stock, sales, master data, MSA pool, "
             "grids — and produces a row for every (store, article, colour) "
             "combination the system thinks should be considered for "
             "replenishment, then attaches a concrete number of units to "
             "ship for each one. The output (ARS_LISTING + ARS_ALLOC_WORKING) "
             "feeds BDC export and the warehouse pick list.")
    add_para(doc,
             "Behind the scenes one click runs a sequence of named Parts. "
             "Each Part has a single, focused job and writes its result to "
             "a known set of columns or tables. When something looks off in "
             "the result, you trace it back to the Part that owns that "
             "column. This document walks the entire pipeline end-to-end "
             "with one continuous worked example so you can see what "
             "changes at each step.")

    # ── Section 2 — narrative ─────────────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "2. The Whole Story — one continuous worked example",
          level=1)
    add_para(doc,
             "Planner Akash kicks off /listing/generate at 09:30 on "
             "2026-05-01. Scope: 5 stores (HN05–HN09) × 80 MAJ_CATs, "
             "run_mode=listing, allocation_mode=python_parallel, workers=4. "
             "We follow one concrete (store, article) row through every "
             "Part: WERKS=HN05, MAJ_CAT=WMN_FORMAL_TROUSER, "
             "GEN_ART_NUMBER=1116111940, CLR=LT_PST. We'll call it 'our row' "
             "for short.")

    # Stage 0
    add_h(doc, "Stage 0 — Click Generate (concurrency check + session start)",
          level=2)
    add_bullets(doc, [
        "Frontend posts to /listing/generate. The endpoint runs has_running_session() — SELECT COUNT(*) FROM ARS_LISTING_SESSIONS WHERE STATUS='RUNNING'.",
        "If non-zero → HTTP 409 ('Another listing run is already in progress'). Closes the back-to-back-DROP race.",
        "Otherwise: make_session_id() returns 20260501_093000_142.",
        "INSERT into ARS_LISTING_SESSIONS with USER_NAME='akash', STARTED_AT=GETDATE(), STATUS='RUNNING', request body in REQUEST_JSON.",
        "loguru sink attached to logs/listing_sessions/20260501_093000_142.log so every log line during this run lands in one file.",
        "HTTP returns 200 with {session_id, allocation_mode, parallel_workers}. UI starts polling /listing/sessions/{sid} every 3 seconds.",
        "A daemon thread is spawned; _generate_listing_impl runs in it.",
    ])

    # Stage 1 — full pipeline opt-in
    add_h(doc, "Stage 1 — (optional) Full Pipeline: MSA + Grids re-run",
          level=2)
    add_para(doc,
             "If req.run_mode='full' the orchestrator first re-runs the "
             "upstream stages itself: calculate_per_day_sale() refreshes "
             "the per-day-sale columns, then every active grid in "
             "ARS_GRID_BUILDER (status='ACTIVE') runs in a 4-thread pool. "
             "For our run, run_mode='listing' so this stage is skipped; "
             "MSA and grids must already be fresh.")

    # Stage 2 — pre-existence
    add_h(doc, "Stage 2 — Pre-existence snapshot (groundwork)", level=2)
    add_para(doc,
             "Before any DROP fires, parked_history.capture_pre_existence() "
             "records OBJECT_ID(...) IS NOT NULL for the 7 tracked tables. "
             "This boolean map is what lets the post-run sweep label each "
             "one CREATED vs. RECREATED / TRUNCATED.")
    code_block(doc,
               "pre_existence = {\n"
               "  'ARS_LISTING':         True,\n"
               "  'ARS_LISTING_WORKING': True,\n"
               "  'ARS_LISTED_OPT':      True,\n"
               "  'ARS_ALLOC_WORKING':   True,\n"
               "  'ARS_MSA_TOTAL':       True,\n"
               "  'ARS_MSA_GEN_ART':     True,\n"
               "  'ARS_MSA_VAR_ART':     True,\n"
               "}",
               lang_label="listing.py :: _generate_listing_impl")

    # Stage 3 — Parts 1, 2, 2.5
    add_h(doc, "Stage 3 — Parts 1 / 2 / 2.5 — Build ARS_LISTING base",
          level=2)
    add_para(doc, "Three sub-steps:", bold=True)
    add_numbered(doc, [
        "Part 1 — DROP and CREATE ARS_LISTING (listing.py:629). INSERT every row from the variant grid table (req.grid_table) where the (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR) keys exist. These are existing-stock options. IS_NEW=0. SLOC stock columns from the grid become V01_*, V02_* etc. Row count after Part 1: ~156K.",
        "Part 2 — INSERT additional rows for MSA-only options (warehouse stock, no store stock). The (WERKS, MAJ_CAT, GEN_ART_NUMBER, CLR) doesn't exist in the grid yet. IS_NEW=1. STK_TTL=0 because nothing physical at the store yet. Row count after Part 2: +43K → ~199K total.",
        "Part 2.5 — Build database indexes on ARS_LISTING (only if row count > 5K). Speeds up the next 6 stages which all UPDATE the same table.",
    ])
    add_para(doc,
             "Our row: HN05 + 1116111940 + LT_PST exists in the grid (the "
             "store had this article last cycle), so Part 1 inserts it with "
             "IS_NEW=0, STK_TTL=12, V01_FRESH=12.")

    # Stage 4 — 3.5a/b/c, 3.55
    add_h(doc, "Stage 4 — Parts 3.5a / 3.5b / 3.5c / 3.55 — Enrich each row",
          level=2)
    add_para(doc,
             "Adds calculated and master-data columns to every row of "
             "ARS_LISTING via UPDATE … FROM JOIN against the calc tables.")
    make_table(doc,
               ["Part", "Source table", "Columns added"],
               [
                   ["3.5a", "calculation tables (per-store)",
                    "LISTING (1/0), I_ROD (impulse-rod flag), CLR_MIN/CLR_MAX, "
                    "FOCUS_W_CAP, FOCUS_WO_CAP"],
                   ["3.5",  "ARS_GEN_ART_AGE / ARS_PER_DAY_SALE",
                    "ACS_D, ALC_D, AGE, AUTO_GEN_ART_SALE, PER_OPT_SALE seed"],
                   ["3.5b", "MASTER_GEN_ART_SALE",
                    "AUTO_GEN_ART_SALE (overrides if master has a value)"],
                   ["3.5c", "MASTER_GEN_ART_AGE",
                    "AGE (overrides if master has a value)"],
                   ["3.55", "ARS_MSA_VAR_ART (aggregated)",
                    "MSA_FNL_Q (warehouse pool), VAR_COUNT (variants in MSA), "
                    "VAR_FNL_COUNT (variants with FNL_Q>0)"],
               ],
               col_widths_in=[0.7, 2.0, 4.0])
    add_para(doc,
             "After Stage 4 our row carries: STK_TTL=12, ACS_D=2 units/day, "
             "ALC_D=7 days, AGE=180 days (existing article), MSA_FNL_Q=200 "
             "(pool at the RDC), VAR_COUNT=4, VAR_FNL_COUNT=4.")

    # Stage 5 — Part 3.6
    add_h(doc, "Stage 5 — Part 3.6 — OPT_TYPE classification "
                "(MIX / RL / TBC / TBL)", level=2)
    info_box(doc,
             "This is the most consequential single Part. It decides what "
             "each row 'is' for the rest of the pipeline. The rules are in "
             "their own doc (OPT_TYPE Classification) — here's the short "
             "version of how each row gets its tag.")
    add_bullets(doc, [
        "RL  — store has enough stock (STK_TTL ≥ stock_threshold_pct × ACS_D × ALC_D) → 'replenish-light'. Just top up.",
        "TBC — store has some stock but below threshold → 'top-up B-class'. Allocate to bring it up.",
        "TBL — store has no stock (STK_TTL=0 or extremely low) AND article has warehouse stock → 'to-be-listed'. New listing.",
        "MIX — fallback when classification can't decide (missing inputs or below the per-MAJ_CAT min-size threshold).",
    ])
    add_para(doc,
             "Our row: STK_TTL=12, ACS_D=2, ALC_D=7, threshold=0.6 → "
             "0.6×2×7 = 8.4. 12 ≥ 8.4 → OPT_TYPE='RL'. The article is "
             "already adequately stocked.")
    add_para(doc,
             "Counts after Part 3.6: MIX=123K, TBL=42K, TBC=2K, RL=33K. "
             "If 'untagged' > 0 in the log, classification inputs are "
             "missing — usually a stale calc table.")

    # Stage 6 — Part 3.7
    add_h(doc, "Stage 6 — Part 3.7 — MIX consolidation", level=2)
    add_para(doc,
             "MIX rows are not actionable individually — they're rolled up "
             "to one row per (WERKS, MAJ_CAT, RNG_SEG) by default "
             "(mix_mode='st_maj_rng'), or one per (WERKS, MAJ_CAT) "
             "(mix_mode='st_maj'), or kept as-is (mix_mode='each'). The "
             "rolled-up row carries summed quantities and a synthetic "
             "GEN_ART_NUMBER so downstream stages don't choke. Our RL row "
             "is unaffected.")

    # Stage 7 — Part 4 pre-resolve, 4a
    add_h(doc, "Stage 7 — Part 4 pre-resolve + 4a — Master + grid joins",
          level=2)
    add_numbered(doc, [
        "Part 4 pre-resolve — UPDATE every row with M_VND_CD, RNG_SEG, MACRO_MVGR, MICRO_MVGR, FAB pulled from vw_master_product (the canonical product master view). These become the keys for the next stage's grid joins.",
        "Part 4a — Join every active grid in ARS_GRID_BUILDER and bring its level-specific stock / sale / MBQ / contribution into ARS_LISTING as <PREFIX>_<col> columns. Example: GRID_MJ adds MJ_STK, MJ_SAL, MJ_MBQ, MJ_CONT_PCT; GRID_MJ_RNG_SEG adds MRS_STK, MRS_SAL, MRS_MBQ, etc. The orchestrator skips inactive grids; check the log for 'skipping grid X' messages.",
    ])
    add_para(doc,
             "Our row gets RNG_SEG='WMN_FORMAL', MACRO_MVGR='OFFICE', "
             "FAB='POLY_BLEND', plus MJ_MBQ=240, MRS_MBQ=180, "
             "MRS_CONT_PCT=22%, etc.")

    # Stage 8 — Parts 4b, 4c, 4d, 4e
    add_h(doc, "Stage 8 — Parts 4b–4e — Compute demand", level=2)
    add_para(doc, "The math that turns store data into 'units needed':",
             bold=True)
    code_block(doc,
               "Part 4b — PER_OPT_SALE\n"
               "    PER_OPT_SALE = <use_for_opt_sale grid>.SAL ÷ active_options_in_segment\n"
               "    (the per-option share of segment sale velocity)\n\n"
               "Part 4c — Core demand math (per row)\n"
               "    rate       = max(PER_OPT_SALE, AUTO_GEN_ART_SALE)\n"
               "    OPT_MBQ    = ACS_D + rate × ALC_D            # cycle stock\n"
               "    OPT_MBQ_WH = ACS_D + rate × (ALC_D + hold_days)  # cycle + warehouse buffer\n"
               "    OPT_REQ    = max(OPT_MBQ    - STK_TTL, 0)    # ship requirement\n"
               "    OPT_REQ_WH = max(OPT_MBQ_WH - STK_TTL, 0)    # pool requirement (incl. hold)\n"
               "    MAX_DAILY_SALE = max sale on any day in the lookback window\n\n"
               "Part 4d — ART_EXCESS\n"
               "    EXCESS_STK = max(STK_TTL - excess_multiplier × OPT_MBQ, 0)\n"
               "    aggregated to gen-art level → ART_EXCESS\n"
               "    (MIX rows excluded — they don't have a single OPT_MBQ)\n\n"
               "Part 4e — Per-grid REQ\n"
               "    For every grid level (MJ, MRS, MJF, ...), compute\n"
               "        <LVL>_REQ = max(<LVL>_MBQ - <LVL>_STK + <LVL>_excess, 0)\n"
               "    These flow into the allocator's 'is the level still hungry?' check.",
               lang_label="Part 4b–4e demand math")
    add_para(doc,
             "Our row: rate=2 units/day, ACS_D=2, ALC_D=7, hold_days=15 → "
             "OPT_MBQ = 2 + 2×7 = 16; OPT_MBQ_WH = 2 + 2×22 = 46; "
             "OPT_REQ = 16-12 = 4; OPT_REQ_WH = 46-12 = 34. "
             "EXCESS_STK = max(12 - 2×16, 0) = 0 (no excess). "
             "ART_EXCESS sums excess across colours of the same gen-art "
             "(0 here).")

    # Stage 9 — Parts 5, 6
    add_h(doc, "Stage 9 — Parts 5 / 6 — Indexes + Store Ranking", level=2)
    add_bullets(doc, [
        "Part 5 — Final indexes on ARS_LISTING. Speeds up Part 7 / Part 8 lookups.",
        "Part 6 — Build ARS_STORE_RANKING. For each (MAJ_CAT, WERKS), compute MJ_REQ (sum of OPT_REQ across all the store's rows in that MAJ_CAT) and FILL_RATE (current STK_TTL ÷ target). W_SCORE = req_weight × normalized(MJ_REQ) + fill_weight × (1 - normalized(FILL_RATE)). Higher W_SCORE → store ranks earlier in the allocator's waterfall. ST_RANK = rank position within MAJ_CAT.",
    ])
    add_para(doc,
             "Our row's MAJ_CAT is WMN_FORMAL_TROUSER. Across HN05's rows "
             "in that MAJ_CAT, MJ_REQ sums to 320 units; FILL_RATE = 76%. "
             "After ranking against HN06–HN09, HN05 lands at ST_RANK=2.")

    # Stage 10 — Part 7
    add_h(doc, "Stage 10 — Part 7 — Build ARS_LISTING_WORKING", level=2)
    add_para(doc,
             "DROP+CREATE ARS_LISTING_WORKING (listing.py:1698). INSERT a "
             "filtered subset of ARS_LISTING:")
    code_block(doc,
               "INSERT INTO ARS_LISTING_WORKING\n"
               "SELECT <_FINAL_KEEP_COLS + columns ending _REQ>\n"
               "  FROM ARS_LISTING\n"
               " WHERE MSA_FNL_Q  > 0      -- pool exists at the RDC\n"
               "   AND OPT_REQ_WH >= 1     -- demand exists at the store\n"
               "   AND OPT_TYPE  IS NOT NULL",
               lang_label="Part 7 — Working table filter")
    add_para(doc,
             "Then ALTER TABLE ADD the dynamic coverage columns: PRI_CT% "
             "(primary-grid coverage %), SEC_CT% (secondary-grid coverage), "
             "ALLOC_FLAG (eligible for strict allocation wave), and the "
             "H_*/GH_* hierarchy / grid-house flags Part 8 needs.")
    add_para(doc,
             "Our row qualifies (MSA_FNL_Q=200, OPT_REQ_WH=34) and lands "
             "in ARS_LISTING_WORKING. Working-row count: 47K out of 199K.")

    # Stage 11 — Part 8 (allocator)
    add_h(doc, "Stage 11 — Part 8 — Rule engine allocator (Stages A–D)",
          level=2)
    add_para(doc,
             "The new rule engine (rule_engine_new.py / "
             "rule_engine_parallel_python.py) does the heavy lifting. "
             "Internally Part 8 has four sub-stages:")
    add_numbered(doc, [
        "Stage A — Rule pass on ARS_LISTING_WORKING. Apply the listing rules (PRI_CT% threshold, min-size, IS_NEW flag, ALLOC_FLAG=1 strict-wave eligibility). Materialize successful options into ARS_LISTED_OPT.",
        "Stage B — Explode each ARS_LISTED_OPT row to its variant×size grain by joining ARS_MSA_VAR_ART (the per-VAR_ART pool) and Master_CONT_SZ (size contribution). Materialize rows into ARS_ALLOC_WORKING with FNL_Q_REM (pool remaining) initialized.",
        "Stage C — Waterfall allocation per MAJ_CAT, in parallel across n_workers (default 4) workers. For each (MAJ_CAT, WERKS) ordered by ST_RANK, take pool_taken = min(SZ_POOL_REQ, FNL_Q_REM). Split into SHIP_QTY (capped at SZ_SHIP_REQ) and HOLD_QTY (the residual, only for TBL options — see HOLD_QTY_Lifecycle.docx). Decrement FNL_Q_REM.",
        "Stage D — Reflect totals back into ARS_LISTING_WORKING (ALLOC_QTY = sum of SHIP_QTY across sizes), set FINAL_OPT_TYPE based on ship outcome.",
    ])
    add_para(doc,
             "Our row's outcome: 4 size rows in ARS_ALLOC_WORKING "
             "(S/M/L/XL of LT_PST × HN05). SHIP_QTY across them sums to 4. "
             "HOLD_QTY=0 (RL options never hold). ALLOC_QTY=4 reflected "
             "back to ARS_LISTING_WORKING. FINAL_OPT_TYPE='RL'. The 4 "
             "units come out of the 200-unit pool, leaving 196 for the "
             "next store / next row.")

    # Stage 12 — Part 8.4 — snapshot both working tables to parked
    add_h(doc, "Stage 12 — Part 8.4 — Snapshot to "
                "ARS_ALLOC_PARKED + ARS_LISTING_WORKING_PARKED", level=2)
    add_para(doc,
             "parked_history.snapshot_session_to_parked(session_id) — runs "
             "in its own try/except, never fails the parent run. Iterates "
             "over the configured (source, parked, history) triples — "
             "currently 'alloc' (ARS_ALLOC_WORKING → ARS_ALLOC_PARKED) and "
             "'listing' (ARS_LISTING_WORKING → ARS_LISTING_WORKING_PARKED) "
             "— and parks each. See PARKED_ALLOC_Lifecycle.docx for full "
             "details. Per-target steps:")
    add_numbered(doc, [
        "Idempotency — IF NOT EXISTS (SELECT 1 FROM <parked> WHERE SESSION_ID=:sid).",
        "Schema reconcile — for every column on <source> that <parked> is missing, ALTER TABLE ADD as NULLABLE. Handles dynamic columns: H_*/GH_*/ALLOC_FLAG on alloc; PRI_CT%/SEC_CT%/H_*/GH_* on listing-working.",
        "Explicit-column-list INSERT INTO <parked> (cols…,SESSION_ID,PARKED_AT,PARK_STATUS) SELECT cols…,:sid,GETDATE(),'PARKED' FROM <source>.",
    ])
    add_para(doc,
             "Aggregate result drives summary['parked_status']: 'PARKED' "
             "if at least one target parked rows; 'SKIPPED_ERROR' if any "
             "target raised; 'SKIPPED_EMPTY' if all targets were empty.")
    add_para(doc,
             "Result: 12,500 alloc rows in ARS_ALLOC_PARKED + 41,300 "
             "listing-working rows in ARS_LISTING_WORKING_PARKED, all "
             "tagged SESSION_ID=20260501_093000_142, PARK_STATUS='PARKED'. "
             "summary['parked_status']='PARKED'.")

    # Stage 13 — Part 8.5
    add_h(doc, "Stage 13 — Part 8.5 — OPT_STATUS post-alloc + "
                "TBL_LISTED_DATE", level=2)
    add_para(doc,
             "After allocation, every row in ARS_LISTING_WORKING gets a "
             "post-alloc OPT_STATUS based on (STK_TTL + ALLOC_QTY) vs. the "
             "threshold:")
    code_block(doc,
               "OPT_STATUS = CASE\n"
               "  WHEN OPT_TYPE='RL'  THEN 'RL'\n"
               "  WHEN OPT_TYPE='TBC' AND ALLOC_QTY>0\n"
               "       AND STK+ALLOC >= thr × eff_ACS_D THEN 'RL'\n"
               "  WHEN OPT_TYPE='TBC' AND ALLOC_QTY>0  THEN 'MIX'\n"
               "  WHEN OPT_TYPE='TBC'                  THEN 'MIX'\n"
               "  WHEN OPT_TYPE='TBL' AND ALLOC_QTY>0\n"
               "       AND STK+ALLOC >= thr × eff_ACS_D THEN 'NL'\n"
               "  WHEN OPT_TYPE='TBL' AND ALLOC_QTY>0  THEN 'TBL'\n"
               "  WHEN OPT_TYPE='TBL'                  THEN 'TBL'\n"
               "END\n\n"
               "TBL_LISTED_DATE = CASE\n"
               "  WHEN OPT_TYPE='TBL' AND ALLOC_QTY>0 AND TBL_LISTED_DATE IS NULL\n"
               "       THEN GETDATE()\n"
               "  ELSE TBL_LISTED_DATE\n"
               "END",
               lang_label="Part 8.5 — listing.py:2010")
    add_para(doc,
             "Our row: OPT_TYPE='RL' → OPT_STATUS='RL', TBL_LISTED_DATE "
             "NULL (it's not a new listing).")

    # Stage 14 — Part 8.6
    add_h(doc, "Stage 14 — Part 8.6 — NL/TBL hold tracking", level=2)
    add_para(doc,
             "Maintains ARS_NL_TBL_HOLD_TRACKING — the persistent "
             "warehouse-side reservation for new-listing options. Three "
             "sub-steps:")
    add_bullets(doc, [
        "STEP A — Decrement HOLD_REM on open rows whose (WERKS, VAR_ART, SZ) saw an ALLOC_QTY this run (HOLD_REM = MAX(0, HOLD_REM − ALLOC_QTY); IS_CLOSED=1 when HOLD_REM hits 0).",
        "STEP A.5 — Refresh HOLD_QTY_INITIAL / HOLD_REM for SKUs already tracked AND showing up again with a NEW hold qty in this run.",
        "STEP B — INSERT new rows for NL/TBL SKUs first appearing in this run (HOLD_QTY > 0 AND OPT_STATUS in ('NL','TBL') AND no existing tracker row).",
    ])
    add_para(doc,
             "Our row is RL → no entry in the tracker. (Full HOLD_QTY "
             "lifecycle is in the companion HOLD_QTY_Lifecycle.docx.)")

    # Stage 15 — tables_affected sweep + end_session
    add_h(doc, "Stage 15 — Tables-affected sweep + end_session", level=2)
    add_para(doc,
             "The orchestrator calls tables_affected_summary(pre_existence) "
             "— SELECT COUNT(*) on each of the 7 tracked tables, classified "
             "vs. the pre-existence map captured in Stage 2:")
    code_block(doc,
               "tables_affected = [\n"
               "  {'table': 'ARS_LISTING',         'action': 'RECREATED', 'rows':  98_750},\n"
               "  {'table': 'ARS_LISTING_WORKING', 'action': 'RECREATED', 'rows':  41_300},\n"
               "  {'table': 'ARS_LISTED_OPT',      'action': 'RECREATED', 'rows':   5_120},\n"
               "  {'table': 'ARS_ALLOC_WORKING',   'action': 'RECREATED', 'rows':  12_500},\n"
               "  {'table': 'ARS_MSA_TOTAL',       'action': 'TRUNCATED', 'rows':   3_240},\n"
               "  {'table': 'ARS_MSA_GEN_ART',     'action': 'TRUNCATED', 'rows':   1_580},\n"
               "  {'table': 'ARS_MSA_VAR_ART',     'action': 'TRUNCATED', 'rows':  19_800},\n"
               "]",
               lang_label="parked_history.py :: tables_affected_summary")
    add_para(doc,
             "end_session() then UPDATEs the ARS_LISTING_SESSIONS row with "
             "STATUS='SUCCESS', DURATION_SEC, ALLOC_ROWS, SHIP_QTY_TOTAL, "
             "HOLD_QTY_TOTAL, FAILED_MAJCATS, STEP_TIMINGS (JSON), "
             "TABLES_AFFECTED (JSON of the array above), PARKED_STATUS "
             "('PARKED' for our run). Loguru sink is detached so the log "
             "file is closed cleanly.")

    # Stage 16 — UI
    add_h(doc, "Stage 16 — UI completion + Parked Runs queue", level=2)
    add_bullets(doc, [
        "Frontend session-poll (3s interval) sees STATUS flip RUNNING → SUCCESS.",
        "Toast: 'Listing complete: 12,500 rows in 87.3s — parked for review'. (Yellow warning toast if PARKED_STATUS='SKIPPED_ERROR'.)",
        "Tables-Affected inline panel renders below the KPI tiles: 7 cards, each showing table name, action pill (CREATED / RECREATED / TRUNCATED / UPSERTED / MISSING), and row count.",
        "loadConfig + loadSummary + loadPreview reload the main grids with fresh data.",
        "loadParkedRuns() refreshes the Parked Runs section. Akash sees session 20260501_093000_142 with parked_rows=12,500, ready for review.",
    ])

    # Stage 17 — Approve / Reject
    add_h(doc, "Stage 17 — Approve / Reject decision (validation gate)",
          level=2)
    add_para(doc,
             "Akash clicks Review. The drawer fetches the paginated detail. "
             "He spot-checks 5 stores × 3 MAJ_CATs and the totals match "
             "expectations.")
    add_para(doc, "Approve path (atomic across BOTH targets in one transaction):",
             bold=True)
    code_block(doc,
               "POST /listing/parked-runs/20260501_093000_142/approve\n\n"
               "-- 1) Idempotency: check BOTH history tables\n"
               "SELECT COUNT(*) FROM ARS_ALLOC_HISTORY\n"
               " WHERE SESSION_ID='20260501_093000_142';            -- 0\n"
               "SELECT COUNT(*) FROM ARS_LISTING_WORKING_HISTORY\n"
               " WHERE SESSION_ID='20260501_093000_142';            -- 0\n"
               "-- both 0 → proceed for both targets\n\n"
               "-- 2) Per-target schema reconcile (idempotent ALTERs)\n"
               "ALTER TABLE ARS_ALLOC_HISTORY            ADD <missing cols> NULL;\n"
               "ALTER TABLE ARS_LISTING_WORKING_HISTORY  ADD <missing cols> NULL;\n\n"
               "-- 3) Promote target 1: alloc\n"
               "INSERT INTO ARS_ALLOC_HISTORY (cols…,SESSION_ID,PARKED_AT,\n"
               "                               PARK_STATUS,APPROVED_AT,APPROVED_BY)\n"
               "SELECT cols…,SESSION_ID,PARKED_AT,'PARKED',GETDATE(),'akash'\n"
               "  FROM ARS_ALLOC_PARKED P\n"
               " WHERE P.SESSION_ID='20260501_093000_142'\n"
               "   AND P.PARK_STATUS='PARKED'\n"
               "   AND NOT EXISTS (SELECT 1 FROM ARS_ALLOC_HISTORY H\n"
               "                    WHERE H.SESSION_ID='20260501_093000_142');\n"
               "DELETE FROM ARS_ALLOC_PARKED\n"
               " WHERE SESSION_ID='20260501_093000_142'\n"
               "   AND PARK_STATUS='PARKED';\n\n"
               "-- 4) Promote target 2: listing-working\n"
               "INSERT INTO ARS_LISTING_WORKING_HISTORY (cols…,SESSION_ID,PARKED_AT,\n"
               "                               PARK_STATUS,APPROVED_AT,APPROVED_BY)\n"
               "SELECT cols…,SESSION_ID,PARKED_AT,'PARKED',GETDATE(),'akash'\n"
               "  FROM ARS_LISTING_WORKING_PARKED P\n"
               " WHERE P.SESSION_ID='20260501_093000_142'\n"
               "   AND P.PARK_STATUS='PARKED'\n"
               "   AND NOT EXISTS (SELECT 1 FROM ARS_LISTING_WORKING_HISTORY H\n"
               "                    WHERE H.SESSION_ID='20260501_093000_142');\n"
               "DELETE FROM ARS_LISTING_WORKING_PARKED\n"
               " WHERE SESSION_ID='20260501_093000_142'\n"
               "   AND PARK_STATUS='PARKED';\n\n"
               "-- 5) Single COMMIT — both targets together or neither.\n"
               "COMMIT;",
               lang_label="parked_history.py :: approve_parked")
    add_para(doc, "Reject path (atomic across BOTH parked tables):",
             bold=True)
    code_block(doc,
               "POST /listing/parked-runs/{sid}/reject  body={note: '...'}\n\n"
               "UPDATE ARS_ALLOC_PARKED\n"
               "   SET PARK_STATUS = 'REJECTED'\n"
               " WHERE SESSION_ID = :sid\n"
               "   AND PARK_STATUS = 'PARKED';\n\n"
               "UPDATE ARS_LISTING_WORKING_PARKED\n"
               "   SET PARK_STATUS = 'REJECTED'\n"
               " WHERE SESSION_ID = :sid\n"
               "   AND PARK_STATUS = 'PARKED';\n\n"
               "COMMIT;\n\n"
               "INSERT INTO audit_log (username, action, resource_type,\n"
               "                       resource_id, notes, created_at)\n"
               "VALUES (:user, 'REJECT_PARKED_ALLOC', 'parked_session',\n"
               "        :sid, :note, GETDATE());",
               lang_label="parked_history.py :: reject_parked")
    info_box(doc,
             "Approve is idempotent — a duplicate POST returns "
             "{already_approved: true, approved_rows: 12500} without "
             "inserting again. ARS_ALLOC_HISTORY is row-grain (one row per "
             "allocation), so it cannot have a UNIQUE constraint on "
             "SESSION_ID — a single approved session contributes thousands "
             "of rows that all share the same SESSION_ID. Duplicate-approval "
             "protection lives in approve_parked itself (early SELECT COUNT "
             "+ a NOT EXISTS guard inside the INSERT, both keyed on "
             "SESSION_ID). A non-unique IX_ARS_ALLOC_HISTORY_session "
             "supports the lookup; IX_ARS_ALLOC_HISTORY_approved_at speeds "
             "history queries.")

    # ── Section 3: flowchart ─────────────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "3. End-to-End Flowchart", level=1)
    add_para(doc,
             "Every node maps to a stage in Section 2. Read top to bottom. "
             "The branch at Stage 17 is the validation gate.",
             italic=True, size=10)
    doc.add_paragraph()

    flow_node(doc, "STAGE 0 · POST /listing/generate",
              "409 if any session is STATUS='RUNNING'  ·  start_session()")
    flow_arrow(doc)
    flow_node(doc, "STAGE 1 · (optional) Full Pipeline",
              "MSA recalc + grid rebuild  (if run_mode='full')")
    flow_arrow(doc)
    flow_node(doc, "STAGE 2 · capture_pre_existence()",
              "snapshot OBJECT_ID for the 7 tracked tables")
    flow_arrow(doc)
    flow_node(doc, "STAGE 3 · Parts 1 / 2 / 2.5",
              "DROP+CREATE ARS_LISTING; INSERT grid + MSA-only options; build indexes",
              fill="FFF2CC", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 4 · Parts 3.5a / 3.5b / 3.5c / 3.55",
              "Enrich rows: ACS_D, ALC_D, AGE, MSA_FNL_Q, FOCUS flags",
              fill="FFF2CC", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 5 · Part 3.6",
              "Classify each row → OPT_TYPE in {MIX, RL, TBC, TBL}",
              fill="FFF2CC", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 6 · Part 3.7",
              "Consolidate MIX rows by mix_mode")
    flow_arrow(doc)
    flow_node(doc, "STAGE 7 · Part 4 pre-resolve + 4a",
              "Master joins (vw_master_product) + active grid joins",
              fill="FFF2CC", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 8 · Parts 4b / 4c / 4d / 4e",
              "Demand math: PER_OPT_SALE → OPT_MBQ → OPT_REQ → ART_EXCESS → <LVL>_REQ",
              fill="FFF2CC", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 9 · Parts 5 / 6",
              "Final indexes  +  ARS_STORE_RANKING (per-MAJ_CAT W_SCORE / ST_RANK)")
    flow_arrow(doc)
    flow_node(doc, "STAGE 10 · Part 7",
              "DROP+CREATE ARS_LISTING_WORKING (MSA>0 AND OPT_REQ_WH≥1)",
              fill="FFE699", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 11 · Part 8 (Stages A–D)",
              "Rule engine → ARS_LISTED_OPT → explode → waterfall → reflect ALLOC_QTY",
              fill="FFE699", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 12 · Part 8.4 · snapshot_session_to_parked",
              "ARS_ALLOC_WORKING ⇒ ARS_ALLOC_PARKED  +  "
              "ARS_LISTING_WORKING ⇒ ARS_LISTING_WORKING_PARKED  "
              "(PARK_STATUS='PARKED')",
              fill="DDEBF7", border="2E75B6")
    flow_arrow(doc)
    flow_node(doc, "STAGE 13 · Part 8.5",
              "Set OPT_STATUS + TBL_LISTED_DATE on ARS_LISTING_WORKING")
    flow_arrow(doc)
    flow_node(doc, "STAGE 14 · Part 8.6",
              "Maintain ARS_NL_TBL_HOLD_TRACKING (NL/TBL warehouse reservation)")
    flow_arrow(doc)
    flow_node(doc, "STAGE 15 · tables_affected_summary + end_session",
              "STATUS=SUCCESS, TABLES_AFFECTED, PARKED_STATUS, STEP_TIMINGS",
              fill="DDEBF7", border="2E75B6")
    flow_arrow(doc)
    flow_node(doc, "STAGE 16 · UI completion",
              "toast + Tables-Affected panel + Parked Runs queue refresh")
    flow_arrow(doc, "▼  user reviews  ▼")

    flow_branch(doc,
                "STAGE 17a · Approve",
                "INSERT → ARS_ALLOC_HISTORY  +  DELETE from PARKED",
                "STAGE 17b · Reject",
                "UPDATE PARK_STATUS='REJECTED'  +  audit_log row")
    flow_arrow(doc)
    flow_node(doc, "TTL purge (later, automated)",
              "PARKED >14d & REJECTED >30d deleted; HISTORY untouched",
              fill="E2EFDA", border="548235")

    # ── Section 4: table-state cheat sheet ───────────────────────────────
    doc.add_page_break()
    add_h(doc, "4. What each table holds at each stage", level=1)
    add_para(doc,
             "Following the worked example in Section 2 (single SUCCESS run, "
             "Approve path).", italic=True, size=10)
    make_table(doc,
               ["Stage", "ARS_LISTING_SESSIONS", "ARS_LISTING / WORKING",
                "ARS_LISTED_OPT", "ARS_ALLOC_WORKING",
                "ARS_ALLOC_PARKED / HISTORY"],
               [
                   ["0  generate kicked off",
                    "+1 row STATUS=RUNNING",
                    "(prior run, untouched yet)", "(prior)",
                    "(prior)", "(any prior parked/history)"],
                   ["3  Parts 1/2/2.5 done",
                    "STATUS=RUNNING", "ARS_LISTING ~199K rows",
                    "(empty)", "(prior, still)", "—"],
                   ["5  Part 3.6 done",
                    "STATUS=RUNNING",
                    "ARS_LISTING with OPT_TYPE filled",
                    "—", "—", "—"],
                   ["8  Parts 4b–4e done",
                    "STATUS=RUNNING",
                    "ARS_LISTING with OPT_MBQ/OPT_REQ filled",
                    "—", "—", "—"],
                   ["9  Part 6 done",
                    "STATUS=RUNNING", "ARS_STORE_RANKING populated",
                    "—", "—", "—"],
                   ["10 Part 7 done",
                    "STATUS=RUNNING", "ARS_LISTING_WORKING ~47K rows",
                    "—", "—", "—"],
                   ["11 Part 8 done",
                    "STATUS=RUNNING", "ALLOC_QTY reflected back",
                    "+5,120 rows", "+12,500 rows", "—"],
                   ["12 Part 8.4 done",
                    "STATUS=RUNNING", "—", "5,120 rows",
                    "12,500 rows (live)",
                    "ARS_ALLOC_PARKED +12,500 PARKED"],
                   ["13 Part 8.5 done",
                    "STATUS=RUNNING",
                    "OPT_STATUS / TBL_LISTED_DATE filled",
                    "—", "—", "—"],
                   ["14 Part 8.6 done",
                    "STATUS=RUNNING",
                    "—", "—", "—",
                    "ARS_NL_TBL_HOLD_TRACKING updated"],
                   ["15 end_session done",
                    "STATUS=SUCCESS, TABLES_AFFECTED set, PARKED_STATUS=PARKED",
                    "—", "—", "—", "—"],
                   ["17a Approve",
                    "(unchanged)", "(live)",
                    "(live)", "(live)",
                    "PARKED row deleted; +12,500 in HISTORY"],
                   ["17b Reject",
                    "(unchanged)", "(live)",
                    "(live)", "(live)",
                    "PARKED row → PARK_STATUS='REJECTED' + audit_log"],
               ],
               col_widths_in=[1.5, 1.8, 1.6, 1.0, 1.2, 1.7])

    # ── Section 5: process-step checklists ───────────────────────────────
    doc.add_page_break()
    add_h(doc, "5. Process Steps — per-Part checklists", level=1)

    add_h(doc, "5.A  Pipeline Parts (in execution order)", level=2)
    make_table(doc,
               ["Part", "What it does", "Reads from", "Writes to / changes"],
               [
                   ["1",     "INSERT existing-stock options from variant grid",
                    "req.grid_table", "ARS_LISTING (DROP+CREATE)"],
                   ["2",     "INSERT MSA-only options (IS_NEW=1)",
                    "ARS_MSA_VAR_ART, ARS_LISTING", "ARS_LISTING"],
                   ["2.5",   "Build indexes (only if >5K rows)",
                    "ARS_LISTING", "ARS_LISTING (indexes)"],
                   ["3.5a",  "LISTING/I_ROD/CLR/FOCUS columns",
                    "calc tables", "ARS_LISTING (UPDATE)"],
                   ["3.5",   "ACS_D / ALC_D / AGE",
                    "ARS_GEN_ART_AGE, ARS_PER_DAY_SALE",
                    "ARS_LISTING (UPDATE)"],
                   ["3.5b",  "AUTO_GEN_ART_SALE override",
                    "MASTER_GEN_ART_SALE", "ARS_LISTING (UPDATE)"],
                   ["3.5c",  "AGE override",
                    "MASTER_GEN_ART_AGE", "ARS_LISTING (UPDATE)"],
                   ["3.55",  "MSA_FNL_Q / VAR_COUNT / VAR_FNL_COUNT",
                    "ARS_MSA_VAR_ART", "ARS_LISTING (UPDATE)"],
                   ["3.6",   "OPT_TYPE classification (MIX/RL/TBC/TBL)",
                    "ARS_LISTING (current state)", "ARS_LISTING.OPT_TYPE"],
                   ["3.7",   "MIX consolidation (per mix_mode)",
                    "ARS_LISTING", "ARS_LISTING (DELETE/INSERT)"],
                   ["4 pre", "M_VND_CD / RNG_SEG / MACRO_MVGR / MICRO_MVGR / FAB",
                    "vw_master_product", "ARS_LISTING (UPDATE)"],
                   ["4a",    "Per-grid columns (MJ_*, MRS_*, MJF_*, …)",
                    "every grid table where status='ACTIVE'",
                    "ARS_LISTING (ALTER ADD + UPDATE)"],
                   ["4b",    "PER_OPT_SALE",
                    "use_for_opt_sale grid", "ARS_LISTING.PER_OPT_SALE"],
                   ["4c",    "OPT_MBQ / OPT_REQ / OPT_MBQ_WH / MAX_DAILY_SALE",
                    "ARS_LISTING (current state)",
                    "ARS_LISTING.OPT_MBQ etc."],
                   ["4d",    "ART_EXCESS (gen-art level)",
                    "ARS_LISTING", "ARS_LISTING.ART_EXCESS, EXCESS_STK"],
                   ["4e",    "<LVL>_REQ for every grid level",
                    "ARS_LISTING", "ARS_LISTING.<LVL>_REQ columns"],
                   ["5",     "Final indexes",
                    "ARS_LISTING", "ARS_LISTING (indexes)"],
                   ["6",     "ARS_STORE_RANKING (W_SCORE, ST_RANK)",
                    "ARS_LISTING", "ARS_STORE_RANKING (TRUNCATE+INSERT)"],
                   ["7",     "ARS_LISTING_WORKING (filtered subset)",
                    "ARS_LISTING (MSA>0, OPT_REQ_WH≥1)",
                    "ARS_LISTING_WORKING (DROP+CREATE)"],
                   ["8",     "Rule engine waterfall (Stages A–D)",
                    "ARS_LISTING_WORKING + ARS_MSA_VAR_ART + Master_CONT_SZ",
                    "ARS_LISTED_OPT + ARS_ALLOC_WORKING + ARS_LISTING_WORKING.ALLOC_QTY"],
                   ["8.4",   "Snapshot alloc to parked",
                    "ARS_ALLOC_WORKING",
                    "ARS_ALLOC_PARKED (+12,500 rows tagged sid)"],
                   ["8.5",   "Post-alloc OPT_STATUS + TBL_LISTED_DATE",
                    "ARS_LISTING_WORKING (post-alloc)",
                    "ARS_LISTING_WORKING.OPT_STATUS, TBL_LISTED_DATE"],
                   ["8.6",   "NL/TBL hold tracking",
                    "ARS_ALLOC_WORKING + ARS_LISTING_WORKING",
                    "ARS_NL_TBL_HOLD_TRACKING (UPDATE/INSERT)"],
               ],
               col_widths_in=[0.6, 2.5, 2.0, 2.4])

    add_h(doc, "5.B  Backend wrap-up steps", level=2)
    add_numbered(doc, [
        "tables_affected_summary(pre_existence) → list of {table, action, rows} for the 7 tracked tables.",
        "summary['tables_affected'] and summary['parked_status'] populated.",
        "end_session(session_id, status, summary) → UPDATE ARS_LISTING_SESSIONS row with final fields, detach loguru sink.",
        "Background thread exits cleanly.",
    ])

    add_h(doc, "5.C  UI completion steps (frontend ListingPage.jsx)",
          level=2)
    add_numbered(doc, [
        "Session-poll detects STATUS flip RUNNING → SUCCESS / FAILED.",
        "On SUCCESS: green toast (yellow if PARKED_STATUS='SKIPPED_ERROR'), with row count + duration + parked-status suffix.",
        "Tables-Affected inline panel renders below the KPI tiles, reading session.tables_affected.",
        "loadConfig + loadSummary + loadPreview reload the main grids.",
        "loadParkedRuns refreshes the Parked Runs collapsible queue.",
        "User opens drawer for a parked session, reviews, clicks Approve or Reject.",
    ])

    add_h(doc, "5.D  Approve / Reject endpoints", level=2)
    add_numbered(doc, [
        "POST /listing/parked-runs/{sid}/approve — guarded INSERT INTO ARS_ALLOC_HISTORY + DELETE from ARS_ALLOC_PARKED. Returns {approved_rows, already_approved}.",
        "POST /listing/parked-runs/{sid}/reject — UPDATE PARK_STATUS='REJECTED' + audit_log INSERT.",
        "POST /listing/parked-runs/purge — TTL: PARKED >14d, REJECTED >30d.",
    ])

    # ── Section 6: configuration variables ───────────────────────────────
    doc.add_page_break()
    add_h(doc, "6. Configuration variables — what each one tunes", level=1)
    make_table(doc,
               ["Variable", "Default", "Tunes", "Direction"],
               [
                   ["stock_threshold_pct", "0.6",
                    "Part 3.6 RL/TBC boundary; Part 8.5 promotion to RL/NL",
                    "Higher → more TBC/TBL"],
                   ["excess_multiplier",   "2.0",
                    "Part 4d EXCESS_STK = max(STK − X×OPT_MBQ, 0)",
                    "Higher → less excess flagged"],
                   ["hold_days",           "0 (UI default 15)",
                    "Part 4c OPT_MBQ_WH buffer days",
                    "Higher → more held at warehouse"],
                   ["age_threshold",       "15",
                    "Part 4c switch from PER_OPT_SALE to AUTO sale for new articles",
                    "Higher → more articles use PER_OPT_SALE"],
                   ["req_weight",          "0.4",
                    "Part 6 store ranking", "Higher → 'needier' stores win"],
                   ["fill_weight",         "0.6",
                    "Part 6 store ranking", "Higher → 'emptier' stores win"],
                   ["enable_fallback",     "false",
                    "Part 8 fallback wave",
                    "true → demote grids one by one when primary wave under-allocates"],
                   ["fallback_boost_mode", "full_mbq",
                    "Part 8 fallback boost", "full_mbq | sales_only | str"],
                   ["static_growth_pct",   "130",
                    "Part 8 fallback growth multiplier",
                    "Higher → larger fallback bump"],
                   ["str_tiers",           "30:150,45:130,60:120,90:110",
                    "Part 8 STR-based dynamic boost", "days:pct,..."],
                   ["default_acs_d",       "18",
                    "Part 3.6 / Part 8.5 fallback when ACS_D is NULL/0",
                    "Lower → conservative on slow stores"],
                   ["min_size_count",      "3",
                    "Part 3.6 TBL eligibility (alternative to 60% ratio)",
                    "Higher → more rows fall to MIX"],
                   ["pri_ct_check_rl",     "true",
                    "Part 8 R06 + revalidation gate for RL",
                    "false → skip primary-grid coverage check for RL"],
                   ["pri_ct_check_tbc",    "true",
                    "Same gate for TBC",
                    "false → skip for TBC (TBL always enforces)"],
                   ["allocation_mode",     "python_parallel",
                    "Part 8 orchestrator",
                    "sequential | python_parallel | sql_parallel | pandas"],
                   ["parallel_workers",    "4 (max 8)",
                    "Part 8 worker count",
                    "Higher → faster but more deadlock risk on small SKUs"],
                   ["mix_mode",            "st_maj_rng",
                    "Part 3.7 MIX rollup grain",
                    "st_maj_rng | st_maj | each"],
                   ["rdc_mode",            "all",
                    "Source RDC policy",
                    "all | own | cross"],
                   ["run_mode",            "listing",
                    "Stage 1 opt-in",
                    "listing | full (full re-runs MSA + grids first)"],
               ],
               col_widths_in=[1.7, 1.0, 2.6, 2.2])

    # ── Section 7: confusions ─────────────────────────────────────────────
    add_h(doc, "7. Common confusions, answered", level=1)

    add_h(doc, "Q1. Why does Part 8 take 90% of the runtime?", level=3)
    add_para(doc,
             "Part 8 is the only stage that does row-level decision-making "
             "(per (WERKS, MAJ_CAT, GEN_ART, CLR, SZ) — millions of "
             "decisions on a typical run). Stages 3–7 are vectorised UPDATEs "
             "or single SELECTs, which SQL Server runs in seconds. The "
             "allocator's waterfall is intrinsically sequential within each "
             "MAJ_CAT (you can't allocate to store 5 until you know what's "
             "left after stores 1–4), but parallelism is at the MAJ_CAT "
             "level — that's what allocation_mode + parallel_workers tunes.")

    add_h(doc, "Q2. ARS_LISTING vs ARS_LISTING_WORKING — which one do I "
                "look at?", level=3)
    add_para(doc,
             "ARS_LISTING is the full result with every classified row "
             "(MIX/RL/TBC/TBL). It's the system of record — every column "
             "Parts 3–4 compute lives here. ARS_LISTING_WORKING is just "
             "the subset Part 8 will actually touch (MSA>0 AND "
             "OPT_REQ_WH≥1). For QA / spot-checks you usually want "
             "WORKING because it shows the rows with allocations; for "
             "investigating why some option got tagged MIX, you need "
             "ARS_LISTING.")

    add_h(doc, "Q3. The Generate button does nothing — what's wrong?",
          level=3)
    add_para(doc,
             "First check: HTTP 409 ('Another listing run is already in "
             "progress')? If yes, an earlier run is RUNNING — go to the "
             "Sessions page and either wait or kill it. Otherwise the "
             "session probably did start; the page is async, so the actual "
             "work runs in a thread. Look at the Live Run dashboard or "
             "/listing/sessions/{sid} for the latest status.")

    add_h(doc, "Q4. Why is OPT_TYPE 'MIX' for 60% of my rows?",
          level=3)
    add_para(doc,
             "Either (a) one of the classification inputs is missing — "
             "most often STK_TTL (grid not built), MSA_FNL_Q (MSA not "
             "calculated), or ACS_D (per-day-sale calc not run) — or "
             "(b) the row genuinely doesn't qualify for any of RL/TBC/TBL "
             "and the system correctly rolls it into MIX. Check the log "
             "for 'Part 3.6 untagged = N'; if untagged > 0, the inputs "
             "are stale.")

    add_h(doc, "Q5. What is the relationship between MSA_FNL_Q and "
                "ARS_ALLOC_WORKING.SHIP_QTY?", level=3)
    add_para(doc,
             "MSA_FNL_Q (computed in MSA_Step_7 = max(STK − PEND − HOLD, 0)) "
             "is the **pool ceiling** at the RDC for an article. The "
             "allocator can never ship more than MSA_FNL_Q across all "
             "stores combined. SHIP_QTY (per (WERKS, VAR_ART, SZ) row in "
             "ARS_ALLOC_WORKING) is the **per-row decision** for that one "
             "store / size. SUM(SHIP_QTY) per (RDC, VAR_ART, SZ) is "
             "guaranteed ≤ ARS_MSA_VAR_ART.FNL_Q for that key.")

    add_h(doc, "Q6. Can I undo a run?", level=3)
    add_para(doc,
             "Not after Approve. Before Approve, click Reject in the "
             "Parked Runs panel — the rows stay in ARS_ALLOC_PARKED with "
             "PARK_STATUS='REJECTED' (audit-kept for 30 days, then TTL'd). "
             "After Approve, ARS_ALLOC_HISTORY treats the row as "
             "permanent. To 'undo' an approved run you'd need a separate "
             "DELETE — that's a deliberate, manual operation.")

    add_h(doc, "Q7. What's the difference between OPT_TYPE and OPT_STATUS?",
          level=3)
    add_para(doc,
             "OPT_TYPE is set in Part 3.6 BEFORE allocation — it answers "
             "'what kind of option is this?'. OPT_STATUS is set in Part "
             "8.5 AFTER allocation — it answers 'what's this option's "
             "outcome?'. A TBC option can finish as RL (alloc was enough "
             "to bring it above threshold) or as MIX (couldn't be "
             "allocated). A TBL option can finish as NL (newly-listed, "
             "fully covered) or stay as TBL (still partial).")

    add_h(doc, "Q8. Same SESSION_ID can appear twice in ARS_LISTING_SESSIONS?",
          level=3)
    add_para(doc,
             "No — SESSION_ID is the primary key. The format "
             "YYYYMMDD_HHMMSS_mmm includes milliseconds, and the 409 "
             "concurrency guard prevents two simultaneous runs from "
             "racing for the same timestamp. Each run gets exactly one "
             "row in ARS_LISTING_SESSIONS.")

    # ── Section 8: troubleshooting ───────────────────────────────────────
    add_h(doc, "8. Troubleshooting matrix — symptom → likely cause → fix",
          level=1)
    make_table(doc,
               ["Symptom", "Likely cause", "Fix"],
               [
                   ["HTTP 409 from /listing/generate",
                    "Another session is STATUS='RUNNING'",
                    "Wait, or kill it from Sessions page"],
                   ["'Part 1: 0 rows' in log",
                    "Variant grid empty",
                    "Run Grid Builder → Run All"],
                   ["'Part 2: 0 rows'",
                    "No new MSA options to add",
                    "Normal if MSA hasn't changed"],
                   ["'Part 3.6 untagged = N' (N>0)",
                    "Classification input missing",
                    "Re-run MSA + grids, then re-Generate"],
                   ["'Part 7: 0 rows (MSA>0 AND OPT_REQ_WH≥1)'",
                    "No demand anywhere — all stores adequately stocked",
                    "Spot-check stocks; usually not a bug"],
                   ["'Part 8 → 0 alloc rows' + warning in log",
                    "Allocator errored",
                    "See Allocation Rule Engine doc §9"],
                   ["'Part 8 took 30+ minutes'",
                    "Single MAJ_CAT contention or worker deadlock",
                    "Drop parallel_workers from 8 → 4; deadlock-retry "
                    "absorbs them but per-op cost grows"],
                   ["Generate succeeded but TABLES_AFFECTED = NULL",
                    "Pre-deploy session — feature didn't exist yet",
                    "Show 'not captured for this run' in UI"],
                   ["Yellow 'parking skipped' warning toast",
                    "PARKED_STATUS='SKIPPED_ERROR'",
                    "Snapshot failed; check logs. Listing succeeded "
                    "anyway — re-run to get parking"],
                   ["Approve returns {already_approved: true}",
                    "Idempotency hit — second click or retry",
                    "Normal; not an error"],
                   ["Duplicate rows in ARS_ALLOC_HISTORY for one SESSION_ID",
                    "Two Approves slipped past approve_parked's NOT EXISTS "
                    "guard (only possible with a true race against a "
                    "long-running INSERT; the early SELECT COUNT closes the "
                    "common case)",
                    "Tighten the guard with SERIALIZABLE / app-lock; "
                    "back-fill DELETE for the redundant SESSION_ID"],
                   ["ARS_ALLOC_PARKED keeps growing",
                    "Planner not actioning parked runs",
                    "Run /listing/parked-runs/purge or wait for TTL"],
                   ["500 error on /listing/summary",
                    "Column rename in ARS_LISTING_WORKING",
                    "Check recent commits; usually a stale frontend"],
               ],
               col_widths_in=[2.4, 2.4, 2.6])

    # ── Section 9: implementation references ─────────────────────────────
    doc.add_page_break()
    add_h(doc, "9. Implementation references", level=1)

    add_para(doc, "Backend — pipeline orchestration", bold=True)
    make_table(doc,
               ["File", "Symbol / line", "Role"],
               [
                   ["backend/app/api/v1/endpoints/listing.py",
                    "generate_listing  (line 318)",
                    "Public endpoint: 409 guard + spawn background thread"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "_run_generate_in_thread",
                    "Thread entry point; calls _generate_listing_impl + end_session"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "_generate_listing_impl",
                    "All 17 stages, sequential UPDATEs and Part 8 dispatch"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "_time_step (line ~530)",
                    "Per-Part timing logger + cancel checkpoint"],
                   ["backend/app/services/grid_calculations.py",
                    "calculate_per_day_sale",
                    "Stage 1 (full pipeline) MSA pre-grid calc"],
                   ["backend/app/api/v1/endpoints/grid_builder.py",
                    "_build_and_run_grid",
                    "Stage 1 (full pipeline) grid rebuild"],
               ],
               col_widths_in=[3.0, 2.0, 2.4])

    add_para(doc, "Backend — Part 8 allocators (one per mode)", bold=True)
    make_table(doc,
               ["File", "Mode", "Notes"],
               [
                   ["rule_engine_new.py",
                    "sequential",
                    "Single-thread reference impl"],
                   ["rule_engine_parallel_python.py",
                    "python_parallel",
                    "Default mode; thread pool, MAJ_CAT-level parallelism"],
                   ["rule_engine_parallel_sql.py",
                    "sql_parallel",
                    "MAJ_CAT-level parallelism with SQL Server agent"],
                   ["rule_engine_pandas.py",
                    "pandas",
                    "In-memory DataFrame implementation; small SKUs"],
               ],
               col_widths_in=[3.0, 1.5, 3.0])

    add_para(doc, "Backend — supporting services", bold=True)
    make_table(doc,
               ["File", "Symbol", "Role"],
               [
                   ["backend/app/services/listing_sessions.py",
                    "make_session_id / start_session / end_session",
                    "Per-run audit row + per-session log file"],
                   ["backend/app/services/listing_sessions.py",
                    "kill_session / delete_session",
                    "Force-stop a RUNNING session; delete a finished one"],
                   ["backend/app/services/parked_history.py",
                    "_SNAPSHOT_TARGETS",
                    "List of (label, source, parked, history) triples — currently 'alloc' and 'listing'"],
                   ["backend/app/services/parked_history.py",
                    "snapshot_session_to_parked",
                    "Part 8.4 — parks BOTH ARS_ALLOC_WORKING and ARS_LISTING_WORKING with schema reconcile"],
                   ["backend/app/services/parked_history.py",
                    "approve_parked / reject_parked",
                    "Validation gate — atomic across both targets in single transaction"],
                   ["backend/app/services/parked_history.py",
                    "list_alloc_history / list_listing_history",
                    "Read-side: separate queries per history table"],
                   ["backend/app/services/parked_history.py",
                    "tables_affected_summary",
                    "Single-sweep post-run classifier"],
                   ["backend/app/services/parked_history.py",
                    "has_running_session",
                    "Powers the 409 guard"],
                   ["backend/app/services/parked_history.py",
                    "purge_old_parked",
                    "TTL maintenance"],
                   ["backend/app/services/alloc_queue.py",
                    "QUEUE_TABLE + helpers",
                    "Per-MAJ_CAT progress tracking for parallel modes"],
                   ["backend/app/services/alloc_cancellation.py",
                    "hard_cancel / register_spid",
                    "Force-stop infrastructure"],
                   ["backend/app/utils/db_helpers.py",
                    "run_sql / retry_on_deadlock / SchemaCache",
                    "Lower-level SQL utilities"],
               ],
               col_widths_in=[2.7, 2.0, 2.7])

    add_para(doc, "Frontend", bold=True)
    make_table(doc,
               ["File", "Area", "Role"],
               [
                   ["frontend/src/services/api.js",
                    "listingAPI.* (lines 318–365)",
                    "All HTTP wrappers: generate / sessions / parkedRuns / "
                    "approveParked / rejectParked / allocHistory"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Generate button + handleGenerate",
                    "POST /listing/generate, set activeSessionId, start polling"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Session-status poll useEffect",
                    "Detects SUCCESS/FAILED, fires toast, refreshes everything"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Tables-Affected inline panel",
                    "Renders below KPI tiles, reads session.tables_affected"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Parked Runs section + drawer",
                    "Collapsible queue + paginated detail + Approve/Reject"],
                   ["frontend/src/pages/ListingLogsPage.jsx",
                    "Past sessions browser",
                    "Lists ARS_LISTING_SESSIONS; per-session log viewer"],
               ],
               col_widths_in=[3.0, 2.0, 2.4])

    add_para(doc, "Companion docs", bold=True)
    add_bullets(doc, [
        "doc/HOLD_QTY_Lifecycle.docx — what Part 8.6 maintains (warehouse-side reservation; FNL_Q deduction in MSA Step 6.5).",
        "doc/PARKED_ALLOC_Lifecycle.docx — what Part 8.4 / approve / reject do (validation gate detail).",
        "backend/app/docs/processes/listing_generation_pipeline.md — short version, served at /process in the UI.",
        "backend/app/docs/processes/allocation_rule_engine.md — Part 8 internals (Stages A–D, waterfall math).",
        "backend/app/docs/processes/opt_type_classification.md — Part 3.6 details.",
        "backend/app/docs/processes/store_ranking.md — Part 6 W_SCORE math.",
        "backend/app/docs/processes/grid_builder.md — what Part 4a joins.",
        "backend/app/docs/processes/msa_stock_calculation.md — what Part 3.55 reads.",
    ])

    # ── Footer ───────────────────────────────────────────────────────────
    add_hr(doc)
    add_para(doc,
             "Source files referenced (line numbers approximate, may drift "
             "as code evolves): "
             "listing.py:318 (generate_listing), :629 (Part 1 DROP+CREATE), "
             ":1698 (Part 7 DROP+CREATE), :1900 (Part 8 dispatch), "
             ":1990 (Part 8.4 hook), :2010 (Part 8.5), :2046 (Part 8.6); "
             "listing_sessions.py:39-100 (schema + start/end_session); "
             "parked_history.py (entire service, ~470 lines).",
             italic=True, size=9, color=(0x80, 0x80, 0x80))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    print(f"Wrote {out_path}  ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    import sys
    out = Path(__file__).parent / "LISTING_PROCESS_Lifecycle.docx"
    try:
        build_doc(out)
    except PermissionError:
        fallback = out.with_name("LISTING_PROCESS_Lifecycle_v2.docx")
        build_doc(fallback)
        print(
            f"NOTE: original was locked (open in Word). Wrote {fallback} instead.",
            file=sys.stderr,
        )
