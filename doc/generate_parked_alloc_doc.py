"""
Generates PARKED_ALLOC_Lifecycle.docx — layman-language walkthrough of the
end-to-end park-then-promote process introduced for ARS V2.

Both ARS_ALLOC_WORKING and ARS_LISTING_WORKING are parked + promoted in
lock-step on the same SESSION_ID; Approve/Reject act on both atomically.

Includes:
  - TL;DR cheat-sheet
  - 10-stage narrative with a worked numerical example
  - end-to-end flowchart (boxes + arrows in native Word shapes/tables)
  - state-of-each-table cheat-sheet across stages
  - common-confusions Q&A
  - implementation references (file:line)

Style mirrors doc/generate_hold_qty_doc.py.
Run:  python doc/generate_parked_alloc_doc.py
Output: doc/PARKED_ALLOC_Lifecycle.docx
"""
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ─── Style helpers (cribbed from generate_hold_qty_doc.py) ──────────────────
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
    # Header row
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
    # Body rows
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
    cell.width = Inches(4.8)
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
    """A two-column branch in the flowchart (Approve vs Reject)."""
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for ci, (title, subtitle, fill, border) in enumerate([
        (left_title, left_subtitle, left_fill, left_border),
        (right_title, right_subtitle, right_fill, right_border),
    ]):
        cell = tbl.cell(0, ci)
        cell.width = Inches(2.7)
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

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # Default font
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)

    # ── Title block ────────────────────────────────────────────────────────
    title = doc.add_heading(
        "Parked Snapshots — End-to-End Lifecycle (alloc + listing-working)",
        level=0)
    for r in title.runs:
        r.font.color.rgb = NAVY

    add_para(doc,
             "Listing run → Park (alloc + listing-working) → Validate → "
             "Promote / Reject; the complete walkthrough",
             italic=True, size=12, color=(0x55, 0x55, 0x55),
             align=WD_ALIGN_PARAGRAPH.LEFT)
    add_para(doc,
             "ARS V2 Retail Auto Replenishment System  |  generated 2026-05-01",
             italic=True, size=9, color=(0x80, 0x80, 0x80))
    add_hr(doc)

    # ── TL;DR ──────────────────────────────────────────────────────────────
    add_h(doc, "TL;DR (one-page cheat sheet)", level=1)
    add_bullets(doc, [
        "Every successful /listing/generate run snapshots TWO tables in lock-step: ARS_ALLOC_WORKING → ARS_ALLOC_PARKED, and ARS_LISTING_WORKING → ARS_LISTING_WORKING_PARKED. Both rows tagged with the same SESSION_ID and PARK_STATUS='PARKED'.",
        "Both source tables are dropped+recreated on the next run — the parked snapshots are the only durable copy until the user decides what to do.",
        "User reviews on the Listing page (\"Parked Runs\" panel). Approve → both snapshots move to history (ARS_ALLOC_HISTORY + ARS_LISTING_WORKING_HISTORY) atomically and the parked rows are deleted. Reject → both stay in their parked tables with PARK_STATUS='REJECTED' for audit.",
        "Atomic across both targets: a single connection + single commit. If the second target's INSERT fails, the rollback unwinds the first. No half-promoted sessions.",
        "Approve is idempotent: approve_parked's IF NOT EXISTS guard against EACH history table makes a second call on the same session a no-op that returns {already_approved: true}. The history tables are row-grain (many rows per session) so they cannot have UNIQUE constraints on SESSION_ID; the application-level guard is the single source of idempotency.",
        "/listing/generate refuses with HTTP 409 if any session is still STATUS='RUNNING'. One run at a time.",
        "Schema drift is handled on BOTH source tables: each one gains dynamic columns (alloc → H_*, GH_*, ALLOC_FLAG; listing-working → PRI_CT%, SEC_CT%, etc.). At every snapshot the service reads INFORMATION_SCHEMA, ALTERs the parked table to add any missing columns as NULL, then does an explicit column-list INSERT. Same dance runs again at Approve time on the history tables.",
        "ARS_LISTING_SESSIONS carries TABLES_AFFECTED (JSON of [{table, action, rows}]) and PARKED_STATUS ('PARKED' / 'SKIPPED_ERROR' / 'SKIPPED_EMPTY'). Aggregate status: PARKED if at least one target succeeded; SKIPPED_ERROR if any target failed; SKIPPED_EMPTY if all empty.",
        "TTL purge: PARKED >14d and REJECTED >30d are deleted from BOTH parked tables by purge_old_parked(). Approved history is never auto-purged.",
        "Snapshot failure does NOT fail the listing run — the run is marked SUCCESS with PARKED_STATUS='SKIPPED_ERROR' and the UI surfaces a yellow warning toast.",
        "UI: drawer has [Alloc rows | Listing rows] tab toggle. The Parked Runs queue table shows both row counts side by side. Approve/Reject buttons act on both tables.",
    ])

    # ── Section 1 ──────────────────────────────────────────────────────────
    add_h(doc, "1. Why two tables?", level=1)
    info_box(doc,
             "Before this change, allocation results were live the moment a "
             "listing run flipped to SUCCESS — and the next run's "
             "DROP+RECREATE on ARS_ALLOC_WORKING wiped them with no permanent "
             "trace. There was no validation gate and no queryable history of "
             "past runs. We now snapshot the result into a 'parking' table the "
             "moment Part 8 finishes, and only after the planner reviews and "
             "approves does it go to a clean, immutable history table.")
    add_para(doc,
             "Think of it like a customs hold area at an airport: every "
             "shipment lands in the bonded warehouse first. An inspector "
             "(the planner) checks it. Approved shipments cross into "
             "country (ARS_*_HISTORY); flagged shipments stay tagged "
             "in the hold area (ARS_*_PARKED with PARK_STATUS='REJECTED') "
             "until the audit team decides what to do. The 14-day TTL is the "
             "limit on how long any shipment can sit unreviewed.")
    add_para(doc,
             "Two snapshots ride together for every session: the size-grain "
             "allocation plan (ARS_ALLOC_WORKING → ARS_ALLOC_PARKED → "
             "ARS_ALLOC_HISTORY) and the option-grain working listing "
             "(ARS_LISTING_WORKING → ARS_LISTING_WORKING_PARKED → "
             "ARS_LISTING_WORKING_HISTORY). Approve and Reject act on both "
             "in a single transaction — half-promoted sessions are "
             "structurally impossible.")

    # ── Section 2: the worked example ──────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "2. The Whole Story — Run → Park → Promote",
          level=1)
    add_para(doc,
             "We follow one listing run end-to-end: planner Akash kicks off a "
             "generate at 09:30 on 2026-05-01 covering 5 stores (HN05–HN09) "
             "and 80 MAJ_CATs. The run produces 12,500 alloc rows. Akash "
             "reviews them, spots a problem with one MAJ_CAT, rejects the run, "
             "and re-runs at 10:15. The second run looks clean and is "
             "approved. We trace the data movement at every stage.")

    # Stage 0
    add_h(doc, "Stage 0 — Click Generate (concurrency check)", level=2)
    add_bullets(doc, [
        "Frontend posts to /listing/generate with the request body.",
        "Endpoint checks parked_history.has_running_session() — a SELECT COUNT(*) FROM ARS_LISTING_SESSIONS WHERE STATUS='RUNNING'. If non-zero, returns HTTP 409 'Another listing run is already in progress'. UI surfaces an error toast.",
        "Otherwise: a fresh SESSION_ID is minted (format YYYYMMDD_HHMMSS_mmm), e.g. 20260501_093000_142.",
        "ARS_LISTING_SESSIONS gets an INSERT with STATUS='RUNNING' so the next call sees this run as in-flight.",
        "The HTTP request returns within milliseconds; the heavy work runs in a background daemon thread.",
    ])

    # Stage 1
    add_h(doc, "Stage 1 — Pre-existence snapshot", level=2)
    add_para(doc,
             "Inside _generate_listing_impl, before any DROP fires, the "
             "service captures which of the seven tracked tables already exist:")
    code_block(doc,
               "pre_existence = parked_history.capture_pre_existence()\n"
               "# returns: {\n"
               "#   'ARS_LISTING':         True,   # left over from prior run\n"
               "#   'ARS_LISTING_WORKING': True,\n"
               "#   'ARS_LISTED_OPT':      True,\n"
               "#   'ARS_ALLOC_WORKING':   True,\n"
               "#   'ARS_MSA_TOTAL':       True,\n"
               "#   'ARS_MSA_GEN_ART':     True,\n"
               "#   'ARS_MSA_VAR_ART':     True,\n"
               "# }",
               lang_label="listing.py :: _generate_listing_impl")
    add_para(doc,
             "This boolean map is what lets the post-run sweep label each "
             "table CREATED (didn't exist before) vs. RECREATED / TRUNCATED.")

    # Stage 2
    add_h(doc, "Stage 2 — Pipeline runs Parts 1–8", level=2)
    add_bullets(doc, [
        "Parts 1–3: build ARS_LISTING (DROP + recreate at listing.py:629).",
        "Part 7: build ARS_LISTING_WORKING (DROP + recreate at listing.py:1698) — filtered to MSA_FNL_Q>0, OPT_REQ_WH>=1.",
        "Part 8: rule_engine_new.run_listing_and_allocation() materializes ARS_LISTED_OPT and ARS_ALLOC_WORKING. End state: 12,500 rows in ARS_ALLOC_WORKING at the (WERKS × MAJ_CAT × GEN_ART × COLOR × SIZE) grain with SHIP_QTY, HOLD_QTY, ALLOC_QTY columns plus dynamic H_*/GH_*/ALLOC_FLAG columns.",
    ])

    # Stage 3
    add_h(doc, "Stage 3 — Part 8.4 → snapshot to parked (both tables)",
          level=2)
    add_para(doc,
             "Right after Part 8 finishes (and before Part 8.5), the orchestrator "
             "calls parked_history.snapshot_session_to_parked(session_id). It "
             "iterates over the configured (source, parked, history) triples — "
             "currently 'alloc' and 'listing' — and parks each. Runs in its "
             "own try/except so a failure here never fails the run.")
    add_para(doc,
             "Inside, for EACH target the work is:", bold=True)
    add_numbered(doc, [
        "Ensure the parked table exists (idempotent CREATE TABLE with the three control columns: SESSION_ID, PARKED_AT, PARK_STATUS).",
        "Idempotency check: if any rows already exist for this SESSION_ID in this parked table, return {parked_rows, skipped: true}.",
        "Read INFORMATION_SCHEMA.COLUMNS for the source. For every column not yet on the parked table, ALTER TABLE ADD it as NULLABLE — handles dynamic columns (H_*/GH_*/ALLOC_FLAG on alloc; PRI_CT%/SEC_CT% on listing-working).",
        "Build an explicit column-list INSERT INTO <parked> (cols…, SESSION_ID, PARKED_AT, PARK_STATUS) SELECT cols…, :sid, GETDATE(), 'PARKED' FROM <source>. Explicit columns (no SELECT *) so order changes don't corrupt the copy.",
    ])
    add_para(doc,
             "After both targets run, the aggregate result drives "
             "summary['parked_status']: 'PARKED' if at least one target "
             "parked rows; 'SKIPPED_ERROR' if any target raised; "
             "'SKIPPED_EMPTY' if all targets were empty / already parked.")
    code_block(doc,
               "-- Target 1: alloc (column list shortened for readability)\n"
               "INSERT INTO [ARS_ALLOC_PARKED]\n"
               "  ([WERKS],[MAJ_CAT],[GEN_ART_NUMBER],[CLR],[VAR_ART],[SZ],\n"
               "   [SHIP_QTY],[HOLD_QTY],[ALLOC_QTY],[ALLOC_FLAG],\n"
               "   [H_RNG_SEG],[GH_RNG_SEG], ... ,\n"
               "   [SESSION_ID],[PARKED_AT],[PARK_STATUS])\n"
               "SELECT\n"
               "   [WERKS],[MAJ_CAT],[GEN_ART_NUMBER],[CLR],[VAR_ART],[SZ],\n"
               "   [SHIP_QTY],[HOLD_QTY],[ALLOC_QTY],[ALLOC_FLAG],\n"
               "   [H_RNG_SEG],[GH_RNG_SEG], ... ,\n"
               "   '20260501_093000_142', GETDATE(), 'PARKED'\n"
               "FROM [ARS_ALLOC_WORKING];\n\n"
               "-- Target 2: listing-working (column list shortened)\n"
               "INSERT INTO [ARS_LISTING_WORKING_PARKED]\n"
               "  ([WERKS],[MAJ_CAT],[GEN_ART_NUMBER],[CLR],\n"
               "   [STK_TTL],[OPT_TYPE],[OPT_MBQ],[OPT_REQ],[ALLOC_QTY],\n"
               "   [PRI_CT_PCT],[SEC_CT_PCT], ... ,\n"
               "   [SESSION_ID],[PARKED_AT],[PARK_STATUS])\n"
               "SELECT\n"
               "   [WERKS],[MAJ_CAT],[GEN_ART_NUMBER],[CLR],\n"
               "   [STK_TTL],[OPT_TYPE],[OPT_MBQ],[OPT_REQ],[ALLOC_QTY],\n"
               "   [PRI_CT_PCT],[SEC_CT_PCT], ... ,\n"
               "   '20260501_093000_142', GETDATE(), 'PARKED'\n"
               "FROM [ARS_LISTING_WORKING];",
               lang_label="parked_history.py :: snapshot_session_to_parked")
    add_para(doc,
             "Result: 12,500 alloc rows in ARS_ALLOC_PARKED + 41,300 "
             "working-listing rows in ARS_LISTING_WORKING_PARKED, all "
             "tagged SESSION_ID = 20260501_093000_142, PARKED_AT = "
             "'2026-05-01 09:31:14', PARK_STATUS = 'PARKED'. Aggregate "
             "summary['parked_status'] = 'PARKED'.")

    # Stage 4
    add_h(doc, "Stage 4 — Parts 8.5–8.6 + tables-affected sweep",
          level=2)
    add_bullets(doc, [
        "Part 8.5 sets OPT_STATUS and TBL_LISTED_DATE on ARS_LISTING_WORKING based on post-alloc stock. Doesn't touch parked rows.",
        "Part 8.6 maintains ARS_NL_TBL_HOLD_TRACKING (see HOLD_QTY_Lifecycle.docx). Independent of parking.",
        "Just before end_session, parked_history.tables_affected_summary(pre_existence) is called. It runs SELECT COUNT(*) on each of the seven tracked tables and classifies the action vs. the pre_existence snapshot.",
    ])
    code_block(doc,
               "# Single chokepoint — no per-stage instrumentation needed.\n"
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
             "Action labels:")
    add_bullets(doc, [
        "CREATED   — didn't exist before this run, exists now (fresh DB).",
        "RECREATED — existed AND is owned by a DROP+CREATE pattern (ARS_LISTING family + ARS_ALLOC_WORKING).",
        "TRUNCATED — existed AND is owned by a TRUNCATE+INSERT pattern (the three ARS_MSA_* tables).",
        "UPSERTED  — fallback for any future table where rows are merged in place.",
        "MISSING   — doesn't exist post-run (a stage crashed before recreating it). Surfaced cleanly in the UI.",
    ])

    # Stage 5
    add_h(doc, "Stage 5 — end_session writes the summary", level=2)
    add_para(doc,
             "The background thread's finally block calls listing_sessions."
             "end_session(session_id, status, summary). The new fields "
             "TABLES_AFFECTED and PARKED_STATUS on ARS_LISTING_SESSIONS get "
             "populated:")
    code_block(doc,
               "UPDATE ARS_LISTING_SESSIONS SET\n"
               "  COMPLETED_AT     = GETDATE(),\n"
               "  STATUS           = 'SUCCESS',\n"
               "  DURATION_SEC     = 87.3,\n"
               "  ALLOC_ROWS       = 12500,\n"
               "  TABLES_AFFECTED  = '[ {\"table\":\"ARS_LISTING\", \"action\":\"RECREATED\", \"rows\":98750}, ... ]',\n"
               "  PARKED_STATUS    = 'PARKED'\n"
               "WHERE SESSION_ID  = '20260501_093000_142';",
               lang_label="listing_sessions.py :: end_session")

    # Stage 6
    add_h(doc, "Stage 6 — UI shows completion + parked queue", level=2)
    add_bullets(doc, [
        "Frontend session-poll (3s interval) sees STATUS flip from RUNNING → SUCCESS.",
        "Toast: 'Listing complete: 12,500 rows in 87.3s — parked for review'.",
        "Tables-affected inline panel renders below the KPI tiles, listing each of the 7 tables with its action pill and row count. Read directly from session.tables_affected.",
        "The Parked Runs section auto-refreshes via listingAPI.parkedRuns(). Akash sees a new row: SESSION_ID 20260501_093000_142, parked_rows 12500, run_status SUCCESS, with Review / Approve / Reject buttons.",
    ])

    # Stage 7
    add_h(doc, "Stage 7 — Akash reviews and rejects the first run",
          level=2)
    add_para(doc,
             "Akash clicks Review. The drawer fetches "
             "/listing/parked-runs/20260501_093000_142 (paginated, 200 rows "
             "per page). He spots that MAJ_CAT 'WMN_KIDS_TOPS' has zero "
             "ALLOC_QTY across all stores — a config issue. Clicks "
             "Reject, types the note 'kids tops grid mis-tagged'.")
    code_block(doc,
               "-- Reject is a status flip, NOT a delete:\n"
               "UPDATE ARS_ALLOC_PARKED\n"
               "   SET PARK_STATUS = 'REJECTED'\n"
               " WHERE SESSION_ID = '20260501_093000_142'\n"
               "   AND PARK_STATUS = 'PARKED';\n\n"
               "-- Plus an audit_log row in the System DB:\n"
               "INSERT INTO audit_log (username, action, resource_type,\n"
               "                       resource_id, notes, created_at)\n"
               "VALUES ('akash', 'REJECT_PARKED_ALLOC', 'parked_session',\n"
               "        '20260501_093000_142', 'kids tops grid mis-tagged',\n"
               "        GETDATE());",
               lang_label="parked_history.py :: reject_parked")
    add_para(doc,
             "12,500 rows now sit in ARS_ALLOC_PARKED with PARK_STATUS = "
             "'REJECTED'. ARS_ALLOC_HISTORY is untouched. The Parked Runs "
             "panel removes this session (default filter shows only PARKED).")

    # Stage 8
    add_h(doc, "Stage 8 — Akash fixes the grid and re-runs", level=2)
    add_bullets(doc, [
        "Akash fixes ARS_GRID_MJ_VAR_ART for the kids tops MAJ_CAT, then clicks Generate again at 10:15.",
        "Stage 0–5 repeat. New SESSION_ID 20260501_101500_071. Both ARS_ALLOC_WORKING (12,800 alloc rows) and ARS_LISTING_WORKING (42,100 listing rows) are dropped+recreated.",
        "snapshot_session_to_parked inserts 12,800 rows into ARS_ALLOC_PARKED + 42,100 rows into ARS_LISTING_WORKING_PARKED, all tagged with the new session_id, PARK_STATUS='PARKED'. The previous 09:30 rejected rows are NOT touched — different SESSION_ID.",
        "ARS_ALLOC_PARKED now contains 25,300 rows total (12,500 REJECTED + 12,800 PARKED). ARS_LISTING_WORKING_PARKED contains 83,400 (41,300 REJECTED + 42,100 PARKED).",
    ])

    # Stage 9
    add_h(doc, "Stage 9 — Akash approves the second run "
                "(atomic across both tables)", level=2)
    add_para(doc,
             "Akash reviews the 10:15 run on both tabs (Alloc rows and "
             "Listing rows) of the drawer. Numbers look right. Clicks "
             "Approve. The endpoint opens ONE connection and commits "
             "after both targets are promoted:")
    code_block(doc,
               "-- Idempotency check across BOTH history tables\n"
               "SELECT COUNT(*) FROM ARS_ALLOC_HISTORY\n"
               " WHERE SESSION_ID = '20260501_101500_071';   -- = 0\n"
               "SELECT COUNT(*) FROM ARS_LISTING_WORKING_HISTORY\n"
               " WHERE SESSION_ID = '20260501_101500_071';   -- = 0\n"
               "-- both 0 → proceed for both targets\n\n"
               "-- ── Target 1: alloc ──────────────────────────────────────\n"
               "-- Reconcile history columns from parked schema (idempotent)\n"
               "ALTER TABLE ARS_ALLOC_HISTORY ADD <missing cols> NULL;\n\n"
               "-- Promote\n"
               "INSERT INTO ARS_ALLOC_HISTORY\n"
               "  (cols..., SESSION_ID, PARKED_AT, PARK_STATUS,\n"
               "   APPROVED_AT, APPROVED_BY)\n"
               "SELECT cols..., SESSION_ID, PARKED_AT, 'PARKED',\n"
               "       GETDATE(), 'akash'\n"
               "  FROM ARS_ALLOC_PARKED P\n"
               " WHERE P.SESSION_ID = '20260501_101500_071'\n"
               "   AND P.PARK_STATUS = 'PARKED'\n"
               "   AND NOT EXISTS (\n"
               "     SELECT 1 FROM ARS_ALLOC_HISTORY H\n"
               "      WHERE H.SESSION_ID = '20260501_101500_071'\n"
               "   );\n\n"
               "DELETE FROM ARS_ALLOC_PARKED\n"
               " WHERE SESSION_ID = '20260501_101500_071'\n"
               "   AND PARK_STATUS = 'PARKED';\n\n"
               "-- ── Target 2: listing-working ────────────────────────────\n"
               "ALTER TABLE ARS_LISTING_WORKING_HISTORY ADD <missing cols> NULL;\n\n"
               "INSERT INTO ARS_LISTING_WORKING_HISTORY\n"
               "  (cols..., SESSION_ID, PARKED_AT, PARK_STATUS,\n"
               "   APPROVED_AT, APPROVED_BY)\n"
               "SELECT cols..., SESSION_ID, PARKED_AT, 'PARKED',\n"
               "       GETDATE(), 'akash'\n"
               "  FROM ARS_LISTING_WORKING_PARKED P\n"
               " WHERE P.SESSION_ID = '20260501_101500_071'\n"
               "   AND P.PARK_STATUS = 'PARKED'\n"
               "   AND NOT EXISTS (\n"
               "     SELECT 1 FROM ARS_LISTING_WORKING_HISTORY H\n"
               "      WHERE H.SESSION_ID = '20260501_101500_071'\n"
               "   );\n\n"
               "DELETE FROM ARS_LISTING_WORKING_PARKED\n"
               " WHERE SESSION_ID = '20260501_101500_071'\n"
               "   AND PARK_STATUS = 'PARKED';\n\n"
               "-- Single COMMIT — either both move or neither does.\n"
               "COMMIT;",
               lang_label="parked_history.py :: approve_parked")
    add_para(doc,
             "End state across the six tables (after 10:15 approve):",
             bold=True)
    add_bullets(doc, [
        "ARS_ALLOC_WORKING / ARS_LISTING_WORKING:  12,800 + 42,100 rows from 10:15 (live; both will be dropped on next /generate).",
        "ARS_ALLOC_PARKED:           12,500 rows from 09:30 with PARK_STATUS='REJECTED' (audit; purged after 30 days).",
        "ARS_LISTING_WORKING_PARKED: 41,300 rows from 09:30 with PARK_STATUS='REJECTED' (audit; purged after 30 days).",
        "ARS_ALLOC_HISTORY:           12,800 rows from 10:15, APPROVED_AT 10:18, APPROVED_BY 'akash'. Permanent.",
        "ARS_LISTING_WORKING_HISTORY: 42,100 rows from 10:15, APPROVED_AT 10:18, APPROVED_BY 'akash'. Permanent.",
    ])
    info_box(doc,
             "If Akash double-clicks Approve, or the network retries the POST: "
             "the second call's SELECT COUNT(*) FROM ARS_ALLOC_HISTORY WHERE "
             "SESSION_ID=:sid sees the existing rows and returns "
             "{already_approved: true, approved_rows: 12800} without doing "
             "the INSERT — no duplicates, no error. ARS_ALLOC_HISTORY is "
             "row-grain (many rows per session) so it intentionally has NO "
             "UNIQUE constraint on SESSION_ID; idempotency is enforced by "
             "the application guard alone. Two truly simultaneous Approves "
             "are rare in practice (the UI disables the button while the "
             "request is in flight) but if you need stronger protection, "
             "wrap approve_parked in a SERIALIZABLE transaction or take "
             "an sp_getapplock keyed on SESSION_ID.")

    # Stage 10 (TTL purge)
    add_h(doc, "Stage 10 — TTL purge (later, automated)", level=2)
    add_para(doc,
             "Two weeks later, a maintenance call to /listing/parked-runs/purge "
             "(or the equivalent scheduled job) runs:")
    code_block(doc,
               "-- For each parked target (alloc + listing-working):\n"
               "-- PARKED rows older than 14 days — forgotten reviews\n"
               "DELETE FROM ARS_ALLOC_PARKED\n"
               " WHERE PARK_STATUS = 'PARKED'\n"
               "   AND PARKED_AT  < DATEADD(day, -14, GETDATE());\n"
               "DELETE FROM ARS_LISTING_WORKING_PARKED\n"
               " WHERE PARK_STATUS = 'PARKED'\n"
               "   AND PARKED_AT  < DATEADD(day, -14, GETDATE());\n\n"
               "-- REJECTED rows older than 30 days — audit window expired\n"
               "DELETE FROM ARS_ALLOC_PARKED\n"
               " WHERE PARK_STATUS = 'REJECTED'\n"
               "   AND PARKED_AT  < DATEADD(day, -30, GETDATE());\n"
               "DELETE FROM ARS_LISTING_WORKING_PARKED\n"
               " WHERE PARK_STATUS = 'REJECTED'\n"
               "   AND PARKED_AT  < DATEADD(day, -30, GETDATE());",
               lang_label="parked_history.py :: purge_old_parked")
    tip_box(doc,
            "Neither ARS_ALLOC_HISTORY nor ARS_LISTING_WORKING_HISTORY is "
            "touched by the TTL job. Approved history on both sides is the "
            "system of record. If you really need to purge approved rows, "
            "do it deliberately — not on a schedule.")

    # ── Section 3: Flowchart ───────────────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "3. Flowchart", level=1)
    add_para(doc,
             "End-to-end flow from /listing/generate to permanent history. "
             "The branch at Stage 7 (Approve vs Reject) is the validation gate.",
             italic=True, size=10)
    doc.add_paragraph()

    flow_node(doc, "STAGE 0 · POST /listing/generate",
              "409 if any session is STATUS='RUNNING'")
    flow_arrow(doc)
    flow_node(doc, "STAGE 1 · capture_pre_existence()",
              "snapshot OBJECT_ID for 7 tracked tables")
    flow_arrow(doc)
    flow_node(doc, "STAGE 2 · Parts 1–8",
              "ARS_LISTING / WORKING / LISTED_OPT / ALLOC_WORKING built")
    flow_arrow(doc)
    flow_node(doc, "STAGE 3 · Part 8.4 · snapshot_session_to_parked",
              "schema reconcile + explicit-col INSERT INTO ARS_ALLOC_PARKED",
              fill="FFE699", border="BF8F00")
    flow_arrow(doc)
    flow_node(doc, "STAGE 4 · tables_affected_summary",
              "single sweep → [{table, action, rows}]")
    flow_arrow(doc)
    flow_node(doc, "STAGE 5 · end_session",
              "ARS_LISTING_SESSIONS ← STATUS, TABLES_AFFECTED, PARKED_STATUS")
    flow_arrow(doc)
    flow_node(doc, "STAGE 6 · UI completion",
              "tables-affected panel + Parked Runs queue refresh")
    flow_arrow(doc, "▼  user reviews  ▼")

    flow_branch(doc,
                "STAGE 7a · Approve",
                "INSERT → ARS_ALLOC_HISTORY  +  DELETE from PARKED",
                "STAGE 7b · Reject",
                "UPDATE PARK_STATUS='REJECTED'  +  audit_log row")
    flow_arrow(doc)
    flow_branch(doc,
                "STAGE 8a · ARS_ALLOC_HISTORY",
                "permanent record, indexed on SESSION_ID",
                "STAGE 8b · ARS_ALLOC_PARKED (REJECTED)",
                "kept for audit until 30-day TTL")
    flow_arrow(doc)
    flow_node(doc,
              "STAGE 9 · TTL purge",
              "PARKED >14d & REJECTED >30d deleted; HISTORY untouched",
              fill="E2EFDA", border="548235")

    # ── Section 4: state cheat-sheet ──────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "4. What each table holds at each stage", level=1)
    add_para(doc,
             "Following the worked example in Section 2: 09:30 run rejected, "
             "10:15 run approved.", italic=True, size=10)
    add_para(doc,
             "Two source-table pairs share the same lifecycle. The 'rows' "
             "for each parked/history table cell are shown as "
             "alloc / listing-working.", italic=True, size=10)
    make_table(doc,
               ["Stage",
                "ARS_LISTING_SESSIONS",
                "ARS_*_WORKING (alloc / listing)",
                "ARS_*_PARKED (alloc / listing)",
                "ARS_*_HISTORY (alloc / listing)"],
               [
                   ["0. After /generate (09:30)",
                    "1 row, STATUS=RUNNING",
                    "(prior run, ~12k / ~41k)",
                    "(empty or prior)", "(empty or prior)"],
                   ["3. After Part 8.4 (09:31)",
                    "STATUS=RUNNING",
                    "12,500 / 41,300 (live)",
                    "+12,500 / +41,300  PARKED, sid=09:30",
                    "unchanged"],
                   ["5. After end_session (09:31)",
                    "STATUS=SUCCESS, TABLES_AFFECTED + PARKED_STATUS=PARKED",
                    "12,500 / 41,300 (live)",
                    "12,500 / 41,300  sid=09:30 PARKED",
                    "unchanged"],
                   ["7b. After Reject (09:35)",
                    "unchanged", "12,500 / 41,300 (live)",
                    "12,500 / 41,300  sid=09:30 REJECTED",
                    "unchanged"],
                   ["8. After /generate (10:15)",
                    "+1 row sid=10:15 STATUS=RUNNING",
                    "(dropped+recreated) 12,800 / 42,100",
                    "12,500 / 41,300  sid=09:30 REJECTED (untouched)",
                    "unchanged"],
                   ["8 cont. After Part 8.4 (10:16)",
                    "STATUS=RUNNING for 10:15",
                    "12,800 / 42,100 (live)",
                    "+12,800 / +42,100  sid=10:15 PARKED   (alongside 09:30 REJECTED)",
                    "unchanged"],
                   ["8 cont. After end_session (10:16)",
                    "STATUS=SUCCESS for 10:15",
                    "12,800 / 42,100 (live)",
                    "25,300 / 83,400 total (REJECTED + PARKED)",
                    "unchanged"],
                   ["9. After Approve (10:18)",
                    "unchanged", "12,800 / 42,100 (live)",
                    "12,500 / 41,300  sid=09:30 REJECTED only (10:15 deleted)",
                    "+12,800 / +42,100  sid=10:15 APPROVED_BY=akash"],
                   ["10. After 30-day TTL purge",
                    "unchanged", "(later run's data)",
                    "(REJECTED >30d gone)",
                    "12,800 / 42,100  sid=10:15 (still here)"],
               ],
               col_widths_in=[1.5, 1.7, 1.5, 2.0, 1.5])

    # ── Section 5: process steps (numbered checklist) ─────────────────────
    add_h(doc, "5. Process Steps — numbered checklist", level=1)

    add_h(doc, "A. Backend — inside /listing/generate", level=2)
    add_numbered(doc, [
        "Refuse with 409 if has_running_session() returns True.",
        "make_session_id() → INSERT into ARS_LISTING_SESSIONS with STATUS='RUNNING'.",
        "Spawn background thread; return 200 to the client immediately.",
        "Inside the thread: capture_pre_existence() before any DROP fires.",
        "Run Parts 1–3 → ARS_LISTING.",
        "Run Part 7 → ARS_LISTING_WORKING.",
        "Run Part 8 → ARS_LISTED_OPT + ARS_ALLOC_WORKING.",
        "Run Part 8.4 → snapshot_session_to_parked(session_id). Snapshots BOTH ARS_ALLOC_WORKING and ARS_LISTING_WORKING in lock-step. Set summary['parked_status'] from the aggregate result.",
        "Run Part 8.5 → OPT_STATUS / TBL_LISTED_DATE on ARS_LISTING_WORKING.",
        "Run Part 8.6 → ARS_NL_TBL_HOLD_TRACKING maintenance.",
        "Run tables_affected_summary(pre_existence) → attach to summary['tables_affected'].",
        "end_session() with status SUCCESS or FAILED → persists TABLES_AFFECTED + PARKED_STATUS.",
    ])

    add_h(doc, "B. Backend — review / promote endpoints", level=2)
    add_numbered(doc, [
        "GET /listing/parked-runs — list parked sessions joined with ARS_LISTING_SESSIONS metadata. Returns both alloc_parked_rows and listing_parked_rows per session. Default filter PARK_STATUS='PARKED'.",
        "GET /listing/parked-runs/{sid}?which=alloc|listing — paginated detail rows from the chosen parked table. Default which=alloc.",
        "POST /listing/parked-runs/{sid}/approve — atomic across BOTH targets in one connection: IF NOT EXISTS guard against each history table, INSERT INTO each history, DELETE from each parked, single COMMIT. Returns {approved_rows, by_table: {alloc, listing}, already_approved}.",
        "POST /listing/parked-runs/{sid}/reject — UPDATE PARK_STATUS='REJECTED' on BOTH parked tables (single transaction) + audit_log INSERT.",
        "GET /listing/alloc-history — approved rows from ARS_ALLOC_HISTORY.",
        "GET /listing/listing-history — approved rows from ARS_LISTING_WORKING_HISTORY.",
        "POST /listing/parked-runs/purge — maintenance: 14-day PARKED + 30-day REJECTED purge, across BOTH parked tables. Returns by_table breakdown.",
    ])

    add_h(doc, "C. Frontend — ListingPage", level=2)
    add_numbered(doc, [
        "Existing 3-second session poll detects STATUS → SUCCESS.",
        "Toast message includes parked status suffix ('parked for review' / yellow warning if SKIPPED_ERROR).",
        "Tables-affected inline panel renders below KPI tiles, reading session.tables_affected.",
        "loadParkedRuns() refreshes the Parked Runs queue.",
        "User clicks Review on a parked session → drawer opens with paginated detail rows.",
        "User clicks Approve → confirm → listingAPI.approveParked(sid) → toast → list refresh.",
        "User clicks Reject → prompt for note → listingAPI.rejectParked(sid, note) → toast → list refresh.",
    ])

    # ── Section 6: confusion points ───────────────────────────────────────
    doc.add_page_break()
    add_h(doc, "6. Common confusions, answered", level=1)

    add_h(doc, "Q1. Why two tables instead of one with a status column?",
          level=3)
    add_para(doc,
             "Two reasons. (1) Mental model: 'park → validate → shift "
             "to history folder' is exactly what physically happens, and an "
             "approver's brain doesn't have to filter status flags to ask "
             "'what's actually in history?'. (2) Query simplicity: every "
             "downstream consumer (BDC export, analytics) reads "
             "ARS_ALLOC_HISTORY without a status filter. There's no risk of "
             "a forgotten WHERE clause leaking REJECTED data into a report.")

    add_h(doc, "Q2. What if the snapshot fails (e.g. permission error)?",
          level=3)
    add_para(doc,
             "The listing run still completes SUCCESS — parking is "
             "bookkeeping, not the primary result. ARS_LISTING_SESSIONS gets "
             "PARKED_STATUS='SKIPPED_ERROR'. The UI surfaces a yellow warning "
             "toast and the Tables Affected panel still renders. Akash can "
             "look at ARS_ALLOC_WORKING directly until he kicks off the next "
             "run; the snapshot for that next run will succeed if the cause "
             "(usually a permissions hiccup or transient lock) clears.")

    add_h(doc, "Q3. Is there a race if two people click Generate at the "
                "same time?", level=3)
    add_para(doc,
             "The 409 guard makes this safe: each /listing/generate call does "
             "SELECT COUNT(*) FROM ARS_LISTING_SESSIONS WHERE STATUS='RUNNING' "
             "as its first action and refuses with HTTP 409 if it sees an "
             "in-flight run. Without this, two runs could race on the DROP+"
             "CREATE of ARS_ALLOC_WORKING with unpredictable interleaving. "
             "If a run truly hangs, kill it from the Sessions page (sets "
             "STATUS='FAILED') and retry.")

    add_h(doc, "Q4. What if ARS_ALLOC_WORKING gains a new column between "
                "two runs?", level=3)
    add_para(doc,
             "Handled — and on BOTH source tables (alloc + listing-working). "
             "Before each snapshot, snapshot_session_to_parked reads "
             "INFORMATION_SCHEMA.COLUMNS for the source and ALTERs "
             "ARS_ALLOC_PARKED to add anything missing as NULLABLE. The "
             "INSERT uses an explicit column list so order changes never "
             "corrupt the copy. ARS_ALLOC_HISTORY is reconciled the same way "
             "at Approve time — the column merge is idempotent and "
             "tolerates concurrent ALTER attempts.")

    add_h(doc, "Q5. Can two simultaneous Approves create duplicates?",
          level=3)
    add_para(doc,
             "approve_parked guards with IF NOT EXISTS (SELECT 1 FROM "
             "ARS_ALLOC_HISTORY WHERE SESSION_ID=:sid). If rows already "
             "exist for this session, it returns {already_approved: true} "
             "without inserting. ARS_ALLOC_HISTORY is row-grain (one row "
             "per allocation), so it intentionally has NO UNIQUE constraint "
             "on SESSION_ID — that would reject every row past the first "
             "and break the very first Approve. Two truly simultaneous "
             "POSTs are rare (the UI disables the button while the request "
             "is in flight); if you need stronger protection wrap "
             "approve_parked in a SERIALIZABLE transaction or take an "
             "sp_getapplock keyed on SESSION_ID.")

    add_h(doc, "Q6. Why not promote automatically on SUCCESS?",
          level=3)
    add_para(doc,
             "Bad runs happen — stale upstream data, mis-configured grid, "
             "a planner kicks off Generate before MSA recalc finishes. Auto-"
             "promotion would mean every bad run pollutes ARS_ALLOC_HISTORY "
             "forever. The validation gate is the whole point. If you want "
             "auto-promotion for a specific use case, build a separate "
             "endpoint that calls approve_parked() right after end_session "
             "— don't change the default.")

    add_h(doc, "Q7. How is 'tables_affected' captured without per-stage "
                "instrumentation?", level=3)
    add_para(doc,
             "Two-step pattern: (a) at run start, capture_pre_existence() "
             "snapshots OBJECT_ID('table','U') IS NOT NULL for the 7 tracked "
             "tables; (b) at run end, tables_affected_summary() does SELECT "
             "COUNT(*) on each and labels the action by combining (existed-"
             "before, now-exists, table-pattern). No per-stage "
             "tables_affected[name]+=count plumbing required — the lifecycle "
             "of each table is statically known to the function.")

    add_h(doc, "Q8. What about backfilling parked snapshots for past runs?",
          level=3)
    add_para(doc,
             "Not possible. ARS_ALLOC_WORKING is dropped between runs, so "
             "past sessions have no source data to snapshot. Sessions that "
             "completed before this feature shipped show 'tables affected: "
             "not captured' and don't appear in the Parked Runs queue. "
             "Collection starts from the next /listing/generate forward.")

    # ── Section 7: implementation references ──────────────────────────────
    add_h(doc, "7. Implementation references", level=1)

    add_para(doc, "Backend", bold=True)
    make_table(doc,
               ["File", "Symbol / area", "Role"],
               [
                   ["backend/app/services/parked_history.py",
                    "_SNAPSHOT_TARGETS",
                    "List of (label, source, parked, history) triples. Currently 'alloc' and 'listing'. Add a third entry to extend to a new table."],
                   ["backend/app/services/parked_history.py",
                    "snapshot_session_to_parked",
                    "Iterates _SNAPSHOT_TARGETS, parks each via _snapshot_one_target. Aggregate result {by_table, total_parked_rows, any_error, any_parked}."],
                   ["backend/app/services/parked_history.py",
                    "snapshot_alloc_to_parked",
                    "Backward-compat wrapper around snapshot_session_to_parked; returns the alloc subset only."],
                   ["backend/app/services/parked_history.py",
                    "approve_parked",
                    "Promote to BOTH history tables atomically. Idempotent via per-target NOT EXISTS guard; no UNIQUE on SESSION_ID — row-grain tables."],
                   ["backend/app/services/parked_history.py",
                    "reject_parked",
                    "UPDATE PARK_STATUS='REJECTED' on BOTH parked tables + audit_log row"],
                   ["backend/app/services/parked_history.py",
                    "purge_old_parked",
                    "TTL: 14d PARKED, 30d REJECTED on BOTH parked tables. Returns by_table breakdown."],
                   ["backend/app/services/parked_history.py",
                    "list_alloc_history / list_listing_history",
                    "Read-side queries against the two history tables"],
                   ["backend/app/services/parked_history.py",
                    "tables_affected_summary",
                    "Post-run sweep, classifies action vs. pre_existence map"],
                   ["backend/app/services/parked_history.py",
                    "has_running_session",
                    "409 guard: any STATUS='RUNNING' row blocks new generate"],
                   ["backend/app/services/listing_sessions.py",
                    "_SCHEMA_DDL + _COLUMN_RECONCILE_DDL",
                    "Adds TABLES_AFFECTED + PARKED_STATUS columns idempotently"],
                   ["backend/app/services/listing_sessions.py",
                    "end_session",
                    "Persists summary['tables_affected'], summary['parked_status']"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "generate_listing",
                    "409 guard via has_running_session()"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "_generate_listing_impl",
                    "capture_pre_existence → Part 8.4 snapshot → tables_affected"],
                   ["backend/app/api/v1/endpoints/listing.py",
                    "/listing/parked-runs (5 endpoints)",
                    "list / detail / approve / reject / alloc-history / purge"],
               ],
               col_widths_in=[2.6, 1.8, 2.6])

    add_para(doc, "Frontend", bold=True)
    make_table(doc,
               ["File", "Symbol / area", "Role"],
               [
                   ["frontend/src/services/api.js",
                    "listingAPI.parkedRuns / parkedRunDetail / approveParked / rejectParked / allocHistory",
                    "HTTP wrappers"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Tables-affected panel",
                    "Inline card below KPI tiles, reads session.tables_affected"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Parked Runs section + drawer",
                    "Collapsible queue + paginated detail + Approve/Reject buttons"],
                   ["frontend/src/pages/ListingPage.jsx",
                    "Session poll → toast",
                    "Includes parked-status suffix; yellow toast on SKIPPED_ERROR"],
               ],
               col_widths_in=[2.6, 2.4, 2.0])

    add_para(doc, "Docs", bold=True)
    add_bullets(doc, [
        "backend/app/docs/processes/listing_generation_pipeline.md — 'Park-then-promote alloc history' section.",
    ])

    # ── Footer ────────────────────────────────────────────────────────────
    add_hr(doc)
    add_para(doc,
             "Companion docs: HOLD_QTY_Lifecycle.docx (the warehouse-side "
             "reservation that runs in parallel to parking), "
             "listing_generation_pipeline.md (the 8-Part pipeline that "
             "feeds Stage 3 here).",
             italic=True, size=9, color=(0x80, 0x80, 0x80))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    print(f"Wrote {out_path}  ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    import sys
    out = Path(__file__).parent / "PARKED_ALLOC_Lifecycle.docx"
    try:
        build_doc(out)
    except PermissionError:
        # File is open in Word — fall back to a versioned name so the run
        # still produces an artifact.
        fallback = out.with_name("PARKED_ALLOC_Lifecycle_v2.docx")
        build_doc(fallback)
        print(
            f"NOTE: original was locked (open in Word). Wrote {fallback} instead.",
            file=sys.stderr,
        )
