"""
Generates ARS_Complete_Process_Guide.docx — a layman-language SOP covering
every process in the ARS application along with performance suggestions
at each step.
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ─── Style helpers ──────────────────────────────────────────────────────────
def shade_cell(cell, hex_fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def set_cell_borders(cell):
    tc_pr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "BFBFBF")
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
             align=None, space_after=4):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    return p


def add_h(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
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
    """Single-cell shaded box used for tips/warnings/perf-notes."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.autofit = True
    cell = tbl.cell(0, 0)
    shade_cell(cell, fill_hex)
    set_cell_borders(cell)
    p1 = cell.paragraphs[0]
    r1 = p1.add_run(label + "  ")
    r1.bold = True
    r1.font.size = Pt(11)
    r1.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    r1.add_text(body)
    doc.add_paragraph()


def perf_box(doc, body):
    add_callout(doc, "PERFORMANCE TIP →", body, "FFF4CE")


def warn_box(doc, body):
    add_callout(doc, "WATCH OUT →", body, "FCE4D6")


def info_box(doc, body):
    add_callout(doc, "IN PLAIN ENGLISH →", body, "DDEBF7")


def add_module(doc, title, what_it_does, steps, slowdowns, suggestions):
    """Standard module section template."""
    add_h(doc, title, level=3)
    info_box(doc, what_it_does)
    add_para(doc, "Step-by-step, what actually happens:", bold=True, size=11)
    add_numbered(doc, steps)
    add_para(doc, "Where it commonly slows down:", bold=True, size=11)
    add_bullets(doc, slowdowns)
    add_para(doc, "Performance suggestions:", bold=True, size=11)
    add_bullets(doc, suggestions)
    add_hr(doc)


# ─── Build document ─────────────────────────────────────────────────────────
doc = Document()

# Page margins
for section in doc.sections:
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)

# Default body style
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(11)


# ═══ COVER ══════════════════════════════════════════════════════════════════
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("ARS")
r.bold = True
r.font.size = Pt(40)
r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("Auto Replenishment System")
r.font.size = Pt(18)
r.font.color.rgb = RGBColor(0x2E, 0x5C, 0x8A)

t = doc.add_paragraph()
t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("\nComplete Process Guide\n")
r.bold = True
r.font.size = Pt(22)

t = doc.add_paragraph()
t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("with Performance Improvement Suggestions")
r.italic = True
r.font.size = Pt(14)

doc.add_paragraph("\n\n\n\n")

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = meta.add_run("V2 Retail  •  Version 2.0  •  Internal SOP")
r.font.size = Pt(11)
r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)

doc.add_page_break()


# ═══ TABLE OF CONTENTS ══════════════════════════════════════════════════════
add_h(doc, "Contents", level=1)
toc_items = [
    "1.  What ARS Is, in Plain Words",
    "2.  Who Uses ARS and What They Get From It",
    "3.  How the System Is Organised (Architecture in Layman Terms)",
    "4.  Logging In and Permissions",
    "5.  The Daily Work Flow at a Glance",
    "6.  Detailed Module Guide",
    "        6.1   Dashboard",
    "        6.2   Allocations",
    "        6.3   Process",
    "        6.4   Data Management",
    "                6.4.1   All Tables",
    "                6.4.2   Create Table",
    "                6.4.3   Upload Data",
    "                6.4.4   Export Data",
    "                6.4.5   Jobs Dashboard",
    "                6.4.6   Data Editor",
    "        6.5   Data Preparation",
    "                6.5.1   MSA Stock Calculation",
    "                6.5.2   BDC Creation",
    "                6.5.3   Grid Builder",
    "                6.5.4   Lookup Art Master",
    "                6.5.5   Listing",
    "        6.6   Contribution %",
    "                6.6.1   Presets",
    "                6.6.2   Mappings",
    "                6.6.3   Execute",
    "                6.6.4   Review",
    "        6.7   Trends",
    "                6.7.1   Dashboard",
    "                6.7.2   Upload",
    "                6.7.3   Review",
    "        6.8   Reports — Pending Allocation",
    "        6.9   Data Validation",
    "                6.9.1   Store SLOC Validation",
    "                6.9.2   Data Checklist",
    "        6.10  Settings",
    "7.  Background Services Running All the Time",
    "8.  The Master Performance Checklist",
    "9.  Recommended Daily / Weekly / Monthly Maintenance",
    "10. Common Pitfalls and How to Avoid Them",
    "11. Glossary",
]
for it in toc_items:
    p = doc.add_paragraph(it)
    p.paragraph_format.space_after = Pt(2)
    p.runs[0].font.size = Pt(11)
doc.add_page_break()


# ═══ 1. WHAT ARS IS ════════════════════════════════════════════════════════
add_h(doc, "1.  What ARS Is, in Plain Words", level=1)
add_para(
    doc,
    "ARS — Auto Replenishment System — is the application V2 Retail uses "
    "to decide, every day, how much of every product to send to which "
    "store. Before ARS, twenty different people sat at twenty different "
    "machines running large Excel sheets, and each one would calculate a "
    "piece of the answer. ARS replaces that whole exercise with a single "
    "web application that connects directly to SAP, pulls the latest "
    "stock and sales data, applies the company's allocation rules, and "
    "produces the final \"this much of this product goes to this store\" "
    "decisions in minutes instead of hours.",
    space_after=8,
)
add_para(
    doc,
    "The system today serves more than 320 stores and 242 major "
    "categories. Every step that used to live in an Excel formula now "
    "lives somewhere inside ARS — usually as a button you click, a file "
    "you upload, or a setting you adjust. The job of this document is to "
    "walk through every one of those buttons, explain in plain English "
    "what happens behind it, and point out where the system tends to "
    "slow down and what to do about it.",
    space_after=8,
)
info_box(
    doc,
    "Think of ARS as a giant calculator that knows your store network. "
    "You feed it stock files, sales files and a few rules, press the "
    "right buttons in the right order, and it tells the warehouse what "
    "to ship.",
)


# ═══ 2. WHO USES IT ════════════════════════════════════════════════════════
add_h(doc, "2.  Who Uses ARS and What They Get From It", level=1)
roles = [
    ("Planners / Buyers",
     "Upload sales and stock data, run MSA, configure presets, review "
     "allocations before they go to the warehouse."),
    ("Allocation Team",
     "Use Allocations and BDC pages to generate, review and adjust the "
     "actual store-by-store distribution lists."),
    ("Data Team",
     "Maintain master tables (article master, store master), monitor "
     "uploads, fix bad rows in the Data Editor, run the Data Checklist."),
    ("Operations / Warehouse",
     "Read the final pending-allocation reports and pick / pack / ship "
     "the recommended quantities."),
    ("Super Admin",
     "Manages users, permissions, database settings, schema migrations "
     "and the overall health of the system."),
]
tbl = doc.add_table(rows=1 + len(roles), cols=2)
tbl.style = "Light Grid Accent 1"
hdr = tbl.rows[0].cells
hdr[0].text = "Role"
hdr[1].text = "What they do day-to-day"
for c in hdr:
    shade_cell(c, "1F3A5F")
    for p in c.paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
for i, (role, desc) in enumerate(roles, start=1):
    tbl.rows[i].cells[0].text = role
    tbl.rows[i].cells[1].text = desc

doc.add_paragraph()


# ═══ 3. ARCHITECTURE ═══════════════════════════════════════════════════════
add_h(doc, "3.  How the System Is Organised (Architecture in Layman Terms)", level=1)
add_para(
    doc,
    "ARS has four main pieces that work together. Understanding what "
    "lives where helps when something feels slow — most performance "
    "issues map to one of these four boxes.",
    space_after=6,
)
add_h(doc, "3.1  The Browser (Frontend)", level=2)
add_para(
    doc,
    "What you see is a React-based single-page application served at "
    "localhost:3001 in dev (or your production URL). It is just the "
    "screen — every piece of real data comes from the backend. The "
    "browser holds nothing important; if it slows down, the cause is "
    "almost always one of the boxes below.",
)
perf_box(
    doc,
    "If a page takes a long time to show data, the browser is usually "
    "fine — it is waiting for the backend or the database. Open the "
    "browser DevTools → Network tab and watch which request is the slow "
    "one before guessing.",
)

add_h(doc, "3.2  The API (Backend)", level=2)
add_para(
    doc,
    "A FastAPI Python application running on the server. Every button "
    "click in the browser becomes an HTTP call to this backend. The "
    "backend talks to the databases, runs all the heavy logic (MSA, "
    "allocation, contribution percentage, upserts) and returns the "
    "answer to the browser.",
)
perf_box(
    doc,
    "The backend uses an asyncio event loop. If any one request "
    "blocks the loop (for example, a synchronous file upload), every "
    "other request queues behind it. We have already moved the upload "
    "path off the event loop using asyncio.to_thread — keep this in "
    "mind whenever you add a new long-running endpoint."
)

add_h(doc, "3.3  Two Databases (Azure SQL)", level=2)
add_para(
    doc,
    "ARS uses two databases on the same Azure SQL server:",
)
add_bullets(doc, [
    "System DB (Claude) — holds the people-and-permissions data: users, "
    "roles, audit log, table metadata, upload jobs, schema history.",
    "Data DB (Rep_data) — holds the business data: stock, sales, "
    "allocations, MSA outputs, master tables.",
])
add_para(
    doc,
    "Splitting them this way means a heavy data query on Rep_data does "
    "not slow down the login screen, and a security audit query on "
    "Claude does not slow down a planner's allocation review.",
)
perf_box(
    doc,
    "Read-Committed Snapshot Isolation (RCSI) should be ON for both "
    "databases. With RCSI, readers never block writers and vice versa. "
    "Without it, a 2-minute upload locks every dashboard query. Verify "
    "with: SELECT name, is_read_committed_snapshot_on FROM sys.databases."
)

add_h(doc, "3.4  Cloudflare Workers (the supporting cast)", level=2)
add_para(
    doc,
    "There are 34 small worker programs deployed at Cloudflare that "
    "handle peripheral jobs: the SAP RFC pipeline, fleet dashboards, "
    "rate-limiting, log-forwarding, ad-hoc Snowflake queries, and the "
    "Universal MCP that gives Claude live access to all systems. They "
    "run independently — if one of them is down, the core ARS app keeps "
    "working.",
)


# ═══ 4. LOGIN & RBAC ════════════════════════════════════════════════════════
add_h(doc, "4.  Logging In and Permissions", level=1)
add_para(
    doc,
    "Every user gets a username and a role. The role decides which "
    "menu items appear in the left sidebar and which buttons are "
    "enabled. There are also Row-Level Security (RLS) rules — a planner "
    "looking at MENS apparel sees only MENS data, not WOMENS or KIDS, "
    "even though everyone is using the same database.",
    space_after=6,
)
add_para(doc, "What happens when you log in:", bold=True)
add_numbered(doc, [
    "You enter your username and password on the login page.",
    "Backend looks the user up in rbac_users (System DB) and verifies "
    "the hashed password.",
    "If valid, the backend returns a session token (JWT). The browser "
    "stores this token and sends it on every subsequent request.",
    "On every page load, the backend checks: \"Does this user have "
    "permission for this page?\" — if yes, the data loads; if no, you "
    "see an Access Denied notice.",
])
perf_box(
    doc,
    "Permission lookups happen on every single API call. Cache the "
    "user's permission set in memory once after login (15-minute TTL) "
    "instead of hitting rbac_permissions on every request — this alone "
    "saves dozens of database round-trips per page."
)
warn_box(
    doc,
    "Never share login credentials. Every action in ARS is logged with "
    "the username — if two people share an account, the audit trail "
    "becomes useless and accountability is lost."
)


# ═══ 5. DAILY WORKFLOW ═════════════════════════════════════════════════════
add_h(doc, "5.  The Daily Work Flow at a Glance", level=1)
add_para(
    doc,
    "Most days follow the same rough sequence. Knowing the pattern "
    "helps you spot when something is out of order.",
    space_after=6,
)
flow = [
    ("Morning — Data Refresh",
     "1. Receive nightly SAP files (stock, sales, master).  "
     "2. Upload them via Data Management → Upload Data, or wait for the "
     "automated pipeline to land them.  "
     "3. Run the Data Checklist — all green means data is ready."),
    ("Mid-morning — Calculations",
     "4. Run MSA Stock Calculation to generate ARS_MSA_TOTAL / GEN_ART / "
     "VAR_ART tables.  "
     "5. Run Contribution % execution if any preset has changed.  "
     "6. Run any Grid Builder grids that depend on the new MSA output."),
    ("Late morning — Allocations",
     "7. Open Allocations or BDC Creation, pick the products and "
     "stores, and generate allocation suggestions.  "
     "8. Review the output, override anything unusual, save."),
    ("Afternoon — Distribution",
     "9. Operations team reads Pending Allocation report.  "
     "10. Warehouse picks, packs and ships the recommended quantities."),
    ("End of day — Hygiene",
     "11. Check Jobs Dashboard for failed jobs.  "
     "12. Quick look at Trends → Dashboard for any obvious anomalies.  "
     "13. Logout."),
]
for title_, body in flow:
    add_h(doc, title_, level=3)
    add_para(doc, body, space_after=4)
perf_box(
    doc,
    "Avoid running heavy uploads (>500k rows) during allocation review "
    "hours. Schedule big uploads either before 9 AM or after 5 PM so "
    "Azure SQL DTUs and the API event loop are free for interactive "
    "users during peak."
)
doc.add_page_break()


# ═══ 6. DETAILED MODULE GUIDE ══════════════════════════════════════════════
add_h(doc, "6.  Detailed Module Guide", level=1)
add_para(
    doc,
    "Every section below follows the same template: what the module "
    "does in plain English, the step-by-step of what really happens, "
    "where it tends to slow down, and what to do about it.",
)


# ─── 6.1 Dashboard ──────────────────────────────────────────────────────────
add_h(doc, "6.1  Dashboard", level=2)
add_module(
    doc,
    "Dashboard (sidebar: Dashboard)",
    "The home screen — shows summary cards (today's allocation count, "
    "pending jobs, recent uploads, key KPIs) so you know at a glance "
    "what the system is doing.",
    [
        "When the page opens, the browser fires several small queries "
        "in parallel: today's job count, recent uploads, current "
        "allocation totals.",
        "Each query hits a single aggregated number from a table, so "
        "responses are usually small but plentiful.",
        "The cards refresh on a fixed interval (typically 30s) so the "
        "screen stays current without you reloading.",
    ],
    [
        "Many tiny queries fired in parallel can saturate the connection "
        "pool if pool_size is too small.",
        "If one card's underlying query is missing an index, the whole "
        "dashboard feels sluggish even when the others are fine.",
        "Auto-refresh every 30 seconds × every logged-in user can add "
        "real load on Azure SQL.",
    ],
    [
        "Cache each card's result in memory for 30–60 seconds — multiple "
        "users opening the dashboard then share one query result.",
        "Combine all dashboard cards into ONE backend endpoint that "
        "returns a single JSON blob instead of 5–8 separate calls.",
        "Add covering indexes on the columns the cards filter on "
        "(typically a date column and a status column).",
        "Pause auto-refresh when the browser tab is in the background "
        "(use document.hidden in the React effect).",
    ],
)


# ─── 6.2 Allocations ────────────────────────────────────────────────────────
add_h(doc, "6.2  Allocations", level=2)
add_module(
    doc,
    "Allocations (sidebar: Allocations)",
    "The page where you generate the actual store-by-store distribution. "
    "You pick products, pick stores, pick a rule (grade-based, size-curve, "
    "stock-based, etc.) and ARS produces the recommended quantities.",
    [
        "Choose allocation type: store-grade, size-curve, stock-based, "
        "sales-based, or fully manual.",
        "Pick product list (filter by brand / category / GEN_ART).",
        "Pick store list (or use store-grade ratios to auto-pick).",
        "Set min/max quantity rules per store (e.g. \"never less than 1, "
        "never more than 12\").",
        "Press Run. Backend pulls warehouse stock, applies the rule, "
        "applies constraints, and writes ARS_ALLOCATION_MASTER + DETAIL.",
        "Review the result, override anything unusual, save.",
    ],
    [
        "Size-curve allocation across 300 stores × 50k SKUs is O(n×m) — "
        "can take minutes if not vectorised.",
        "Warehouse capacity check requires iterative recalculation if "
        "any store exceeds its limit.",
        "Manual overrides save one row at a time — slow over many edits.",
    ],
    [
        "Vectorise the size-curve loop in Python using NumPy / pandas "
        "rather than nested for-loops.",
        "Run the allocation as a background job for product lists "
        "above ~5,000 SKUs; let the user keep working.",
        "Batch manual overrides — collect all of them and save in one "
        "round-trip rather than per-row.",
        "Add an index on ARS_ALLOCATION_DETAIL (allocation_code, "
        "store_code, gen_art_number) to speed review/filter queries.",
    ],
)


# ─── 6.3 Process ────────────────────────────────────────────────────────────
add_h(doc, "6.3  Process", level=2)
add_module(
    doc,
    "Process (sidebar: Process)",
    "A guided wizard that walks you through the standard end-to-end "
    "replenishment flow: load data → MSA → allocation → release. Useful "
    "for new users who want the system to suggest the next step.",
    [
        "Wizard opens at Step 1 — \"Have you uploaded today's data?\"",
        "Each step calls a small backend route that checks whether the "
        "underlying tables are fresh (max date column).",
        "When all steps are green, the wizard offers a single \"Run "
        "Pipeline\" button that fires the steps in order.",
    ],
    [
        "Each freshness check is a separate query — adds round-trips.",
        "The pipeline button runs steps sequentially even when some "
        "could run in parallel.",
    ],
    [
        "Combine freshness checks into one endpoint that returns the "
        "max-date for every relevant table in a single query.",
        "Wherever steps don't depend on each other, run them in parallel.",
        "Cache the green/red status for 60 seconds so a quick "
        "user-double-click doesn't refire all checks.",
    ],
)


# ─── 6.4 DATA MANAGEMENT ────────────────────────────────────────────────────
add_h(doc, "6.4  Data Management", level=2)

# 6.4.1 All Tables
add_module(
    doc,
    "6.4.1  All Tables",
    "Lists every table you have access to with row counts, last-modified "
    "dates and quick links to view, edit or export.",
    [
        "Page loads list of tables from INFORMATION_SCHEMA.",
        "For each table, a count query (SELECT COUNT(*)) runs to show "
        "the row count.",
        "Click any table → opens the Data Editor or Export with that "
        "table preselected.",
    ],
    [
        "SELECT COUNT(*) on a 50M-row table is a full scan — adds "
        "seconds per table.",
        "Listing 200+ tables × 1 count query each = many round-trips.",
    ],
    [
        "Use approximate row counts from sys.partitions instead of "
        "COUNT(*) — instant, accurate enough for a list view.",
        "Issue counts in parallel via asyncio.gather rather than serially.",
        "Cache the table list (with row counts) for 5 minutes per user.",
    ],
)

# 6.4.2 Create Table
add_module(
    doc,
    "6.4.2  Create Table",
    "Lets an admin define a new table directly from the UI: column names, "
    "data types, primary key. The backend issues the CREATE TABLE.",
    [
        "Type a table name and add columns one by one.",
        "Choose data types (string, integer, decimal, date, etc.).",
        "Mark which columns make up the primary key.",
        "Submit — backend builds and runs CREATE TABLE on Rep_data.",
        "Table immediately appears in All Tables.",
    ],
    [
        "Creating a table with no indexes besides the PK means every "
        "later query against it will scan the whole table.",
    ],
    [
        "After creating, immediately add the indexes you'll filter on "
        "(typically a date column and any foreign-key-like columns).",
        "Default new string columns to NVARCHAR(500) not NVARCHAR(MAX) — "
        "MAX is a LOB type that defeats some optimisations and slows "
        "down our staging path during upserts.",
    ],
)

# 6.4.3 Upload Data — DETAILED
add_h(doc, "6.4.3  Upload Data (the most-used and most-critical screen)", level=3)
info_box(
    doc,
    "This is where you push CSV / XLSX files into ARS tables. It is "
    "also the screen most likely to feel slow, because it touches "
    "everything: file parsing, type validation, network upload to Azure "
    "SQL, MERGE statements, audit logging.",
)
add_para(doc, "What happens, step by step:", bold=True)
add_numbered(doc, [
    "You pick a target table from the dropdown.",
    "You drop or browse to an Excel / CSV file.",
    "(Optional) Click Preview — the backend reads the first ~50 rows so "
    "you can verify columns line up.",
    "You select Operation Mode = Upsert (insert new, update changed) or "
    "Delete (remove matched rows).",
    "Optionally tick \"Background\" — for files >100k rows we strongly "
    "recommend this so your browser doesn't have to stay open.",
    "Press Upsert. Backend reads the entire file into a pandas DataFrame, "
    "cleans it (blanks → __SKIP__, '|' or '-' → __NULL__), validates "
    "types, then runs the Fast Bulk Upsert path:",
])
add_bullets(doc, [
    "Creates a temporary staging table on Azure SQL with NVARCHAR(4000) "
    "columns.",
    "Bulk-inserts your data into staging in batches of ~20,000 rows "
    "(one network round-trip per batch).",
    "Issues ONE big UPDATE that joins staging to the target and updates "
    "rows whose values changed.",
    "Issues ONE big INSERT that writes rows that don't yet exist.",
    "Drops the staging table.",
    "Writes a single audit summary row to audit_log.",
])
add_numbered(doc, [
    "When the path above succeeds, the page shows Total Records, "
    "Inserted, Updated, Unchanged, Errors, Duration.",
    "If the fast path fails for any reason (rare — type mismatch, "
    "constraint violation), the engine falls back to a slower chunked "
    "MERGE path that processes 10,000 rows per chunk and shows "
    "progress in real time.",
])
add_para(doc, "Where it commonly slows down:", bold=True)
add_bullets(doc, [
    "Excel parsing of large XLSX files — 34 MB Excel ≈ 300–400 MB RAM "
    "and 30+ seconds just to read.",
    "Network round-trip to Azure SQL — every batch is one trip; if your "
    "API is on-prem and the DB is in Azure, expect 30–80ms per trip.",
    "NVARCHAR(MAX) staging columns — pyodbc fast_executemany allocates "
    "huge buffers for MAX types and slows down at large batch sizes. "
    "We use NVARCHAR(4000) as the sweet spot.",
    "Audit log writes — if row-level audit is enabled on a 100k-row "
    "upload, that's 100k audit rows being written.",
    "Azure SQL transient errors (40613) — serverless tier wakeup or "
    "reconfiguration can sever the connection mid-upload.",
])
add_para(doc, "Performance suggestions:", bold=True)
add_bullets(doc, [
    "ALWAYS use Background mode for files >100k rows. The user can close "
    "the browser; the worker keeps running.",
    "Convert Excel to CSV before upload — pandas reads CSV ~5–10× faster "
    "than XLSX.",
    "Make sure the API and Azure SQL are in the same Azure region — "
    "latency drops from ~50ms to <5ms per round-trip.",
    "Keep ConnectRetryCount=5, ConnectRetryInterval=10 in the ODBC "
    "string (already set) — handles 40613 transparently.",
    "Disable row-level audit (set enable_row_audit=False) for uploads "
    "where you don't need per-row diff tracking — only the summary row "
    "is written.",
    "Run Upload Data uploads outside business hours when possible — "
    "they consume Azure SQL DTUs that the rest of the app needs.",
    "Add a TCP keepalive (KeepAlive=30 in ODBC string) so a dead "
    "connection is detected in 30s instead of 2 hours — prevents "
    "\"running\" jobs from hanging indefinitely.",
    "On backend startup, add a sweep that marks any \"running\" upload "
    "job older than 1 hour with no progress as failed — prevents "
    "zombie jobs after a backend restart.",
])
warn_box(
    doc,
    "Do not click Upsert twice in quick succession on the same file — "
    "without an idempotency check, both runs will try to insert the "
    "same rows and the second will see all of them as updates."
)
add_hr(doc)

# 6.4.4 Export Data
add_module(
    doc,
    "6.4.4  Export Data",
    "Pull data back out — choose a table, choose columns, apply filters, "
    "pick CSV or XLSX, and the system streams a download.",
    [
        "Select target table.",
        "Select which columns you want.",
        "Apply filters (equals, contains, between, etc.). Filter "
        "dropdowns load distinct values from the column.",
        "Click Preview to see first 100 rows.",
        "Submit — runs as a background job; you get a job_id.",
        "When ready, the file appears in the job list with a download "
        "button.",
    ],
    [
        "Loading distinct values for a high-cardinality column "
        "(10k+ unique values) is slow and uses memory.",
        "Exporting 1M+ rows to XLSX is much slower than CSV (Excel has "
        "row/sheet limits and xlsxwriter is single-threaded).",
        "If the export job's worker thread crashes, the job sits "
        "\"running\" forever.",
    ],
    [
        "For high-cardinality filter dropdowns, switch to a typeahead "
        "search (server-side) instead of preloading the full list.",
        "For exports above 500k rows, default to CSV. Offer XLSX only "
        "as an explicit choice.",
        "Run exports through the same job-recovery sweep used for uploads "
        "— mark stale running jobs as failed at startup.",
        "Stream large CSVs directly to disk instead of buffering in "
        "memory — avoids the worker's RSS ballooning.",
    ],
)

# 6.4.5 Jobs Dashboard
add_module(
    doc,
    "6.4.5  Jobs Dashboard",
    "Real-time view of every background job — uploads, exports, MSA, "
    "contribution executions. Shows status, progress, duration, and lets "
    "you cancel or delete jobs.",
    [
        "List view shows queued, running, completed, failed, cancelled.",
        "Filter by status / table / user.",
        "Click a job → see logs, error message, sample changes.",
        "For a running job, you can request cancellation — backend sets "
        "a flag; the worker checks the flag at chunk boundaries.",
    ],
    [
        "Polling the list every 5 seconds × N users adds steady DB load.",
        "Cancel only takes effect at chunk boundaries — a running MERGE "
        "or INSERT cannot be interrupted by the cancel flag alone.",
    ],
    [
        "Switch from polling to server-sent events or WebSocket so the "
        "browser only refreshes when something actually changed.",
        "Implement \"hard cancel\" — the backend stores the SQL session "
        "ID per job and runs KILL <spid> when the user requests force-stop.",
        "Add a heartbeat column updated by the worker every 5 seconds; "
        "any job with a heartbeat older than 5 minutes is auto-failed by "
        "a reaper task.",
    ],
)

# 6.4.6 Data Editor
add_module(
    doc,
    "6.4.6  Data Editor",
    "Spreadsheet-like view of any table — view, edit, add or delete rows "
    "directly without writing SQL.",
    [
        "Pick a table → schema (columns + types) loads.",
        "Apply optional pre-load filters (cascading dropdowns).",
        "Data loads in pages of N rows.",
        "Edit a cell → change tracked in browser as \"unsaved\".",
        "Click Save → backend issues UPDATEs for each changed row.",
        "Add a new row by filling all PK columns → auto-saves.",
        "Select rows + Delete → batch DELETE.",
    ],
    [
        "Loading distinct values per column for cascade filters fires "
        "many small queries.",
        "Save is per-row UPDATE — slow if you've edited 200 rows.",
        "No optimistic locking — if two users edit the same row, last "
        "save wins silently.",
    ],
    [
        "Cache distinct-value lookups in memory for 5 minutes.",
        "Batch save — collect all edits and send one update with multiple "
        "rows; backend uses MERGE.",
        "Add a row-version (rowversion / timestamp) column on edited "
        "tables; reject saves whose row-version is older than current.",
    ],
)


# ─── 6.5 DATA PREPARATION ──────────────────────────────────────────────────
add_h(doc, "6.5  Data Preparation", level=2)

# 6.5.1 MSA
add_h(doc, "6.5.1  MSA Stock Calculation (the engine room)", level=3)
info_box(
    doc,
    "MSA — Master Stock Allocation — is the calculation that turns raw "
    "stock and pending allocations into the three core tables that "
    "drive the rest of the system: ARS_MSA_TOTAL, ARS_MSA_GEN_ART, and "
    "ARS_MSA_VAR_ART. If MSA is wrong or stale, every downstream "
    "calculation is wrong."
)
add_para(doc, "What happens, step by step:", bold=True)
add_numbered(doc, [
    "You open MSA Stock Calculation. The page loads available columns "
    "and dates from VW_ET_MSA_STK_WITH_MASTER, plus saved filter "
    "presets.",
    "You select cascading filters (Store Code → SLOC → SEG, etc.) and "
    "a calculation date.",
    "You pick a SEG filter (typically APP for apparel and GM for "
    "general merchandise).",
    "Set the Threshold % (default 1).",
    "Press Calculate MSA. The backend runs the 9-step algorithm:",
])
add_bullets(doc, [
    "Filter the source by SLOC.",
    "Normalize values (trim, uppercase).",
    "Fill missing dimensions.",
    "Build SEG = [APP, GM].",
    "Pivot by SLOC so each SLOC becomes a column.",
    "Merge MASTER_ALC_PEND (pending allocations).",
    "Compute FNL_Q = max(STK − PEND, 0).",
    "Generate color variants.",
    "Aggregate to GEN_ART and VAR_ART grain.",
])
add_numbered(doc, [
    "Output is written to ARS_MSA_TOTAL, ARS_MSA_GEN_ART, ARS_MSA_VAR_ART. "
    "ST_CD is renamed to RDC in all three.",
    "Page shows result summary; the data is now ready for downstream "
    "modules (Allocations, Contribution %, BDC).",
])
add_para(doc, "Where it commonly slows down:", bold=True)
add_bullets(doc, [
    "Page open is slow — see \"PERFORMANCE TIP\" below; the page does "
    "FOUR separate Azure SQL queries before showing anything.",
    "DISTINCT CAST([DATE] AS DATE) on VW_ET_MSA_STK_WITH_MASTER is "
    "non-sargable — full view scan.",
    "VW_ET_MSA_STK_WITH_MASTER is a heavy view that joins multiple "
    "master tables; even SELECT TOP 1 forces plan compile.",
    "Pivot operation in pandas can balloon memory if SLOC count is high.",
    "Merging MASTER_ALC_PEND requires a full join.",
])
add_para(doc, "Performance suggestions:", bold=True)
add_bullets(doc, [
    "Drop the CAST([DATE] AS DATE) wrappers — query [DATE] directly. "
    "This single change cuts page-open time from 30s to <1s.",
    "Replace SELECT TOP 1 * (used to discover columns) with "
    "INFORMATION_SCHEMA.COLUMNS — metadata only, instant.",
    "Cache columns + dates + filter_configs for 5 minutes.",
    "Don't auto-load the first preset on page open. Only auto-load if "
    "the user has set is_last_used=1.",
    "Run the three sub-queries in /msa/columns in parallel via "
    "asyncio.gather(to_thread(...)).",
    "Materialize VW_ET_MSA_STK_WITH_MASTER as a refreshed table after "
    "every nightly ingest — turns minutes of view scan into "
    "milliseconds of indexed seek.",
    "Run MSA as a background job rather than blocking the page when "
    "the SLOC list is long.",
    "Add an index on ET_MSA_STK([DATE]).",
])
add_hr(doc)

# 6.5.2 BDC
add_module(
    doc,
    "6.5.2  BDC Creation",
    "BDC = Business Document Creation. Used to upload a delivery "
    "document, build allocation sequences from it, manage delivery "
    "orders inside an existing allocation, and optionally save the "
    "result back to the master allocation table.",
    [
        "Upload Excel containing the BDC sheet.",
        "Backend parses the sheet; you pick columns/sheets if multiple.",
        "View the resulting allocation sequence (historical record).",
        "Adjust delivery-order quantities inline if needed.",
        "Save to ARS_ALLOCATION_MASTER + DETAIL.",
    ],
    [
        "Large XLSX with multiple sheets is slow to parse.",
        "Sequence deletion can break the audit chain if not soft-deleted.",
    ],
    [
        "Soft-delete (mark deleted=1) instead of hard-delete sequences.",
        "Pre-validate the BDC file format before parsing fully — fail "
        "fast if the structure is wrong.",
        "Cache parsed result by file hash so a re-upload of the same "
        "file is instant.",
    ],
)

# 6.5.3 Grid Builder
add_module(
    doc,
    "6.5.3  Grid Builder",
    "A power tool — define a pivot \"grid\" (which dimensions become "
    "rows, which KPIs become columns, what aggregation, what weightage) "
    "and run it. Used to build derived calculation tables.",
    [
        "Define grid: hierarchy columns, KPI filters, output table name, "
        "weightage formula, group.",
        "Save the grid definition.",
        "Run individual grid → produces output table with row count "
        "and duration.",
        "Or Run All Active Grids → batch run.",
        "Reorder grids if dependencies require.",
    ],
    [
        "Large pivots (millions of input rows) are heavy on Azure SQL.",
        "Cascading grid dependencies aren't auto-detected — running them "
        "in the wrong order produces stale outputs.",
        "No incremental refresh — every run rebuilds from scratch.",
    ],
    [
        "Add an explicit \"depends-on\" relationship between grids; the "
        "Run-All path resolves topologically.",
        "Add \"last successful run\" timestamp; let users skip grids "
        "whose inputs haven't changed.",
        "Run grids in parallel when the dependency graph allows.",
        "Persist the SQL plan for each grid so you can spot regressions "
        "after schema changes.",
    ],
)

# 6.5.4 Lookup Art Master
add_module(
    doc,
    "6.5.4  Lookup Art Master",
    "Take any user file and enrich it by looking up additional columns "
    "from the master product view. Useful when a planner has a sales "
    "file that has only article codes and they need the descriptions.",
    [
        "Upload your Excel/CSV.",
        "Pick the join key (which column matches VW_MASTER_PRODUCT).",
        "Pick the master columns you want pulled in.",
        "Preview shows matched-vs-unmatched counts.",
        "Download the enriched file.",
    ],
    [
        "JOIN against VW_MASTER_PRODUCT can timeout for files >100k rows.",
        "Column type inference scans the whole file.",
    ],
    [
        "Limit user upload size to a sensible cap (50k rows) — anything "
        "above that should be done via Export Data with the master "
        "view joined on the SQL side.",
        "Pre-validate the join key column has matching dtype with the "
        "master before running the JOIN.",
        "Use NOLOCK on VW_MASTER_PRODUCT for read-only enrichment — it's "
        "a master view that rarely changes during the day.",
    ],
)

# 6.5.5 Listing
add_module(
    doc,
    "6.5.5  Listing",
    "Manages product listing — which articles are listed at which "
    "stores, with attributes like listing rank, division, brand. The "
    "listing layer feeds into allocation rules.",
    [
        "Open Listing → loads listing master with current state.",
        "Filter by store, brand, category.",
        "Inline-edit listing flags; save.",
    ],
    [
        "Listing master is wide and grows every season.",
        "Bulk listing changes (add/remove an article from 300 stores) "
        "are slow row-by-row.",
    ],
    [
        "Provide a \"bulk listing\" upload path — single CSV "
        "(article × store) → one upsert.",
        "Add seasonal partitioning if listing rules differ by season.",
        "Index (store_code, article_code) — the most common filter.",
    ],
)


# ─── 6.6 CONTRIBUTION % ─────────────────────────────────────────────────────
add_h(doc, "6.6  Contribution %", level=2)
add_para(
    doc,
    "Contribution % is the calculation that decides what share of total "
    "category sales each article should get. It is one of the heaviest "
    "calculations in the system — large product list × large store list "
    "× multiple time-windows.",
    space_after=6,
)

add_module(
    doc,
    "6.6.1  Presets",
    "A preset is a saved calculation recipe — \"L30D\" (last 30 days), "
    "\"L18M\" (last 18 months), etc. Pick the months, average days, KPI "
    "type and a description.",
    [
        "Open Presets → see existing presets in priority order.",
        "Create a new preset (name, months, avg_days, kpi_type, "
        "description).",
        "Reorder existing presets — order matters when fallbacks fire.",
    ],
    [
        "No version history — overwriting a preset loses the old "
        "definition.",
        "Reorder requires read-modify-write — risk of conflict if two "
        "admins edit at once.",
    ],
    [
        "Add an immutable preset_history table — every change appends "
        "a new row instead of overwriting.",
        "Use optimistic concurrency on reorder (compare-and-swap on a "
        "version column).",
    ],
)

add_module(
    doc,
    "6.6.2  Mappings",
    "Two tabs. SSN Mappings: which SSN values use which preset (with "
    "a fallback). Assignments: which output column gets fed by which "
    "SSN mapping, with a prefix template, targeted at Store / Company / "
    "Both.",
    [
        "Tab 1: pick SSN value → assign a preset and a fallback.",
        "Tab 2: define the output column name pattern, choose the SSN "
        "mapping that drives it, and the target scope.",
        "Save.",
    ],
    [
        "Circular mapping references aren't validated — possible to "
        "create infinite-loop fallbacks.",
        "Duplicate prefix templates with different SSNs aren't detected.",
    ],
    [
        "Add a server-side validator that runs DFS on the mapping graph "
        "before save and rejects cycles.",
        "Warn on duplicate prefix templates pointing to different SSNs.",
        "Show a preview of the resulting output column names before "
        "save.",
    ],
)

add_module(
    doc,
    "6.6.3  Execute",
    "The button that actually runs Contribution %. Configure grouping "
    "column, major categories, presets, target scope; submit as a "
    "background job; monitor progress; download results.",
    [
        "Configure: grouping column, major-category multi-select, "
        "preset selection, target (Store / Company / Both), use_sequence "
        "toggle, save_to_db toggle.",
        "Click Execute → backend creates a job and returns job_id.",
        "Live log streams in via the job dashboard.",
        "When done, two result tabs: store-level and company-level.",
    ],
    [
        "Long-running jobs (100k+ SKUs × 300+ stores) can run for "
        "20–60 minutes.",
        "Sequence execution adds ~30% overhead.",
        "Live log streaming requires a persistent connection.",
    ],
    [
        "Pre-aggregate sales/stock at the SLOC × GEN_ART grain in a "
        "materialised table that refreshes nightly — turns 60-minute "
        "jobs into 5-minute ones.",
        "Use SQL window functions (LAG / OVER) instead of pandas for "
        "the trailing-window calculations — pushes work to the DB.",
        "Allow users to skip sequence-mode for ad-hoc runs (it's only "
        "needed when historical reproducibility matters).",
        "Switch live logs to server-sent events; close the connection "
        "after the job completes to free server resources.",
    ],
)

add_module(
    doc,
    "6.6.4  Review",
    "Browse and download Contribution % result tables. Apply filters, "
    "preview rows, download CSV, delete old result tables.",
    [
        "List all result tables (named ARS_CONTRIB_RESULTS_*).",
        "Click one → preview with filters and distinct-value counts "
        "per column.",
        "Download or delete.",
    ],
    [
        "Result tables of 1M+ rows make Preview timeout.",
        "Delete fails if foreign keys reference the result.",
    ],
    [
        "Limit Preview to 1,000 rows max; offer full download as a "
        "background export.",
        "Add cleanup-cascade on delete — drop dependent rows first.",
        "Auto-delete result tables older than 30 days unless flagged "
        "as \"keep\".",
    ],
)


# ─── 6.7 TRENDS ─────────────────────────────────────────────────────────────
add_h(doc, "6.7  Trends", level=2)

add_module(
    doc,
    "6.7.1  Dashboard",
    "Analytical dashboard with charts and stats over Trend_* tables. "
    "Toggle between summary and trend modes; pick metrics, aggregations, "
    "date ranges and chart types.",
    [
        "Pick view mode (summary vs trend).",
        "Choose grouping column, metrics, aggregation function "
        "(SUM/AVG/COUNT/MAX/MIN), top N.",
        "For trends: choose date grain (day/week/month/quarter/year) "
        "and optional breakdown column.",
        "Apply filters and date range → cards, chart, table preview.",
    ],
    [
        "Cross-year aggregations on large date ranges are slow.",
        "Distinct values for filters are computed per request — "
        "duplicates work.",
        "Composed charts (multiple series stacked) are O(n²).",
    ],
    [
        "Pre-aggregate Trend_* into materialised summaries at "
        "day/week/month grain — chart loads in milliseconds.",
        "Cache distinct values per (column, date-range) tuple.",
        "Limit Top N to a hard ceiling (e.g. 200) on the backend.",
        "Lazy-load chart components — heavy ones (composed) only when "
        "explicitly chosen.",
    ],
)

add_module(
    doc,
    "6.7.2  Upload",
    "Upload a trend data file. Pick a report_date, check for conflicts "
    "with existing data, choose append/upsert/replace, execute.",
    [
        "Upload XLSX → server reads.",
        "Pick report_date.",
        "Check Conflicts → backend counts overlapping rows.",
        "Choose conflict mode and execute.",
        "Result panel shows inserted/updated/deleted.",
    ],
    [
        "UPSERT against a 50M-row Trend table can lock for minutes.",
        "Replace mode does a full delete + insert — heavy on transaction "
        "log.",
    ],
    [
        "Use the same fast-bulk staging path that Upload Data uses — "
        "currently this path may go through chunked MERGE.",
        "For Replace mode, prefer TRUNCATE + INSERT (minimal logging) "
        "where SIMPLE recovery model is enabled.",
        "Always recommend Background mode for Trend uploads.",
    ],
)

add_module(
    doc,
    "6.7.3  Review",
    "Browse and download Trend_* tables with filters and date range.",
    [
        "Pick a Trend table → load with default filters.",
        "Apply column filters / date range.",
        "Download CSV.",
    ],
    [
        "Distinct value computation slow on high-cardinality columns "
        "(brand, article).",
        "ag-Grid client-side rendering chokes past 100k rows.",
    ],
    [
        "Server-side typeahead for filter dropdowns.",
        "ag-Grid server-side rowmodel for tables >100k rows.",
        "Default download to CSV; XLSX as opt-in.",
    ],
)


# ─── 6.8 REPORTS ────────────────────────────────────────────────────────────
add_h(doc, "6.8  Reports — Pending Allocation", level=2)
add_module(
    doc,
    "6.8  Pending Allocation Report",
    "Shows ARS_pend_alc joined with the master product view — the "
    "current to-be-shipped list. Used by Operations / Warehouse to drive "
    "picking and packing.",
    [
        "Page loads ARS_pend_alc LEFT JOIN VW_MASTER_PRODUCT.",
        "Default columns shown: RDC, ST_CD, MATNR, QTY, MAJ_CAT, DIV, "
        "SEG, GEN_ART_NUMBER, CLR.",
        "Toggle other columns on/off.",
        "Apply searchable filters and a global search.",
        "Row count + total quantity shown; first 2000 rows displayed.",
    ],
    [
        "Global search scans all columns — O(n×m).",
        "ARS_pend_alc grows to millions of rows during peak allocation.",
        "VW_MASTER_PRODUCT join can be slow if master_product is large.",
    ],
    [
        "Server-side filtering instead of client-side; ag-Grid server-side "
        "rowmodel.",
        "Add a covering index on ARS_pend_alc(RDC, ST_CD, MATNR).",
        "Restrict global search to indexed columns by default; expose "
        "\"deep search\" as an explicit, slow option.",
        "Auto-archive rows older than 30 days into ARS_pend_alc_history "
        "to keep the live table small.",
    ],
)


# ─── 6.9 DATA VALIDATION ────────────────────────────────────────────────────
add_h(doc, "6.9  Data Validation", level=2)
add_module(
    doc,
    "6.9.1  Store SLOC Validation",
    "Manage which SLOCs are active for each store and what KPI label "
    "they carry. Discovers brand-new SLOCs from ET_STORE_STOCK so you "
    "can configure them before they are used downstream.",
    [
        "Page loads ARS_STORE_SLOC_SETTINGS.",
        "Sync button → backend scans ET_STORE_STOCK for SLOCs not yet "
        "in settings, inserts them in pending state.",
        "User toggles Active/Inactive and sets KPI label.",
        "Bulk save.",
    ],
    [
        "Sync requires a full ET_STORE_STOCK scan.",
        "Freshness indicator computes max date per page load.",
    ],
    [
        "Run Sync as a daily background job, not on user click.",
        "Cache freshness for 5 minutes.",
        "Index ET_STORE_STOCK(store_code, sloc).",
    ],
)

add_module(
    doc,
    "6.9.2  Data Checklist",
    "Pre-process validation. Click Run → checks every configured table "
    "for freshness, missing required fields, referential integrity. "
    "Green/yellow/red per check.",
    [
        "Click Run.",
        "Backend runs each check rule.",
        "Per-table results displayed.",
        "Drill into red items → row-level details.",
        "Fix → re-run.",
    ],
    [
        "Each rule runs a full table scan.",
        "No incremental check; re-running validates everything.",
        "Drill-down can return huge result sets.",
    ],
    [
        "Add an updated_at column to every checked table; rules check "
        "only rows with updated_at > last successful run.",
        "Cap drill-down to 500 rows; offer full export.",
        "Run rules in parallel; respect a max-DTU budget so the checklist "
        "doesn't bring the rest of the app to a crawl.",
    ],
)


# ─── 6.10 SETTINGS ──────────────────────────────────────────────────────────
add_h(doc, "6.10  Settings", level=2)
add_module(
    doc,
    "6.10  Settings (Admin only)",
    "Configure DB connections, manage users and roles, view the audit "
    "log, run schema reconciliation, hot-reload connection strings.",
    [
        "DB Settings → edit server, database name, credentials → click "
        "Save → backend reloads engines without restart.",
        "Users → add/disable users, assign roles.",
        "Permissions → grant/revoke per module per role.",
        "Schema → diff current DB against canonical model; apply or "
        "rollback migrations.",
    ],
    [
        "Hot-reload swaps engine pools — if the new credentials are "
        "wrong, the entire app loses DB access until reverted.",
        "Schema migrations on huge tables can lock for minutes.",
    ],
    [
        "Probe the new connection BEFORE swapping (already done in "
        "reload_db_engines — keep that safety net).",
        "Run schema migrations in a maintenance window; warn users.",
        "Cache permission lookups; audit log writes should be async.",
    ],
)


# ═══ 7. BACKGROUND SERVICES ════════════════════════════════════════════════
doc.add_page_break()
add_h(doc, "7.  Background Services Running All the Time", level=1)
add_para(
    doc,
    "Even when no user is on the screen, several services keep working "
    "in the background. Knowing they exist helps when a planner asks "
    "\"why is something happening that I didn't trigger?\"",
    space_after=6,
)

add_h(doc, "7.1  Upload Worker Thread", level=2)
add_para(
    doc,
    "When a user submits a background upload, the request returns "
    "instantly and a single worker thread picks the job off a queue and "
    "processes it. Only one upload runs at a time — others wait their "
    "turn.",
)
perf_box(
    doc,
    "Single worker = guaranteed-no-conflict but no parallelism. If "
    "uploads pile up, they all wait. Consider adding a small worker "
    "pool (3–5 workers) gated to NOT touch the same target table at "
    "the same time."
)

add_h(doc, "7.2  TempDB Cleanup Service", level=2)
add_para(
    doc,
    "A daemon that wakes up periodically to clean orphaned ARS temp "
    "tables in tempdb and (in aggressive mode) shrink the tempdb data "
    "files. Useful because failed uploads or crashed workers can leave "
    "global temp tables behind.",
)
perf_box(
    doc,
    "On Azure SQL Database (managed service), DBCC SHRINKFILE on system "
    "DBs is restricted — the service detects EngineEdition 5/6 and "
    "skips unsupported operations. Aggressive mode is safe to leave on "
    "in dev but should be tested carefully in production."
)

add_h(doc, "7.3  Schema Reconciliation on Startup", level=2)
add_para(
    doc,
    "When the FastAPI app boots, it walks every model in Base.metadata "
    "and checks the live DB. If a model declares a column the DB lacks, "
    "the column is auto-added (nullable). If a model says a column "
    "should be nullable but the DB says NOT NULL, the column is widened. "
    "This closes the gap that create_all leaves — create_all only "
    "creates missing tables, never alters existing ones.",
)
perf_box(
    doc,
    "Reconciliation runs on every startup. On a DB with hundreds of "
    "tables × dozens of columns, this is many round-trips. Cache the "
    "result per app version — re-run only when the build version "
    "changes."
)

add_h(doc, "7.4  Audit Logging", level=2)
add_para(
    doc,
    "Almost every write operation produces an audit_log row recording "
    "who, what, when, batch_id, IP, and (for upserts) a column-level "
    "diff. The log is the system of record for compliance and "
    "troubleshooting.",
)
warn_box(
    doc,
    "Per-row audit logging on a 1M-row upload writes 1M audit rows. For "
    "large bulk operations, prefer the summary-only audit row over "
    "row-level audit unless you specifically need the diff trail."
)


# ═══ 8. PERFORMANCE MASTER CHECKLIST ════════════════════════════════════════
doc.add_page_break()
add_h(doc, "8.  The Master Performance Checklist", level=1)
add_para(
    doc,
    "Use this as a one-page reference. Most performance problems in "
    "ARS reduce to one of the items below.",
    space_after=6,
)

cats = [
    ("Database (Azure SQL)", [
        "RCSI is enabled on both Claude and Rep_data (readers don't "
        "block writers).",
        "Every WHERE / JOIN / ORDER BY column has an index.",
        "No CAST(...) wrapping a date column in WHERE / ORDER BY — "
        "kills index seeks.",
        "Heavy views are materialised as nightly-refreshed tables when "
        "queried often.",
        "ConnectRetryCount=5, ConnectRetryInterval=10, "
        "Connection Timeout=60 in the ODBC string — handles transient "
        "40613 errors automatically.",
        "Add KeepAlive=30 to detect dead connections in 30s instead of "
        "the 2-hour OS default.",
        "Audit log table is indexed on (table_name, batch_id, created_at).",
        "tempdb is monitored; orphaned global temp tables are cleaned.",
    ]),
    ("Backend (FastAPI)", [
        "Long-running endpoints use asyncio.to_thread or "
        "run_in_threadpool — never block the event loop.",
        "Connection pool sized for peak: pool_size + max_overflow ≥ "
        "expected concurrent DB users.",
        "Per-row loops are vectorised (pandas / numpy) before they hit "
        "the DB.",
        "fast_executemany is enabled on every engine that bulk-inserts.",
        "Staging tables use NVARCHAR(4000) not NVARCHAR(MAX).",
        "Background jobs have heartbeats; a reaper marks stale ones "
        "as failed.",
        "Cancellation translates to KILL <spid>, not just a Python flag.",
    ]),
    ("Frontend (React)", [
        "Avoid auto-running heavy queries on page open — wait for the "
        "user to click.",
        "Combine N small calls into one batch endpoint where possible.",
        "Server-side pagination/filtering for any grid above ~10k rows.",
        "Pause polling when the tab is hidden (document.hidden).",
        "Distinct-value dropdowns use server-side typeahead for "
        "high-cardinality columns.",
    ]),
    ("Operational", [
        "Run heavy uploads outside business hours.",
        "One target table = one in-flight upload at a time (per worker).",
        "Convert XLSX to CSV before uploading large files.",
        "Verify upload result counts (Total / Inserted / Updated / "
        "Errors) on every job.",
        "Watch the Jobs Dashboard at the end of every day for failed "
        "jobs.",
    ]),
]
for title_, items in cats:
    add_h(doc, title_, level=3)
    add_bullets(doc, items)


# ═══ 9. MAINTENANCE SCHEDULE ════════════════════════════════════════════════
doc.add_page_break()
add_h(doc, "9.  Recommended Daily / Weekly / Monthly Maintenance", level=1)

add_h(doc, "9.1  Daily (5–10 minutes)", level=2)
add_bullets(doc, [
    "Open the Jobs Dashboard. Confirm no jobs are stuck in \"running\" "
    "for more than the expected duration.",
    "Open Data Checklist; run it once. Confirm all rows are green.",
    "Glance at Trends → Dashboard for any obvious anomaly (sudden zero, "
    "huge spike).",
    "If any job failed, capture the error and re-run after addressing "
    "root cause.",
])

add_h(doc, "9.2  Weekly", level=2)
add_bullets(doc, [
    "Review Jobs Dashboard for jobs that took noticeably longer than "
    "the week before — early warning of a regression.",
    "Run a query: SELECT TOP 20 query_text, total_elapsed_time / "
    "execution_count AS avg_ms FROM sys.dm_exec_query_stats — find the "
    "slowest queries and check if they have indexes.",
    "Verify tempdb size and active connection count are within "
    "expected ranges.",
    "Review audit_log row count; if it's growing dangerously, plan an "
    "archive.",
])

add_h(doc, "9.3  Monthly", level=2)
add_bullets(doc, [
    "Rebuild indexes on heavy tables (ARS_pend_alc, ARS_MSA_TOTAL, "
    "Trend_*) — fragmented indexes slow scans noticeably.",
    "Review user list — disable accounts that haven't logged in for "
    "60+ days.",
    "Run a query plan diff on the top 5 most-expensive endpoints — "
    "spot regressions caused by data growth.",
    "Archive audit_log rows older than 6 months to a history table.",
    "Test the schema reconciliation path on a staging copy before "
    "deploying any model changes.",
])


# ═══ 10. PITFALLS ══════════════════════════════════════════════════════════
add_h(doc, "10. Common Pitfalls and How to Avoid Them", level=1)
pitfalls = [
    ("\"Upload says Total Records 0 but Errors equal total file size\"",
     "Means the result-builder positional arguments are misaligned in "
     "the upsert engine. Verify _build_result is called with "
     "(total, inserted, updated, unchanged, errors) IN THAT ORDER. The "
     "fast-bulk path used to have this bug."),
    ("\"Upload completes but the UI never updates from running\"",
     "Worker thread crashed or backend was restarted. Run the auto-fail "
     "SQL from Section 6.4.5 and re-upload. Permanent fix: heartbeat + "
     "startup recovery."),
    ("\"40613: Database is not currently available\"",
     "Azure SQL transient — usually a serverless wakeup or "
     "reconfiguration. With ConnectRetryCount=5 in the ODBC string, "
     "the driver retries automatically. If it persists, check "
     "service_objective in sys.databases — if it includes _S_, you're "
     "on serverless and the DB auto-paused."),
    ("\"Page open is slow on MSA Stock Calculation\"",
     "The CAST([DATE] AS DATE) and SELECT TOP 1 * make every column / "
     "date discovery query a full view scan. Drop the CAST, use "
     "INFORMATION_SCHEMA.COLUMNS, cache results. See Section 6.5.1."),
    ("\"Upload took 90 minutes the first time, now takes 1 minute\"",
     "The first upload triggered the buggy fast-bulk fallback to slow "
     "chunked MERGE because of the AuditService.log_data_change "
     "AttributeError. After the fix it goes through the fast path. If "
     "you ever see chunked MERGE running unexpectedly, check the logs "
     "for 'Fast bulk failed, falling back'."),
    ("\"Data Checklist tab won't load while an upload is running\"",
     "The upload was on a synchronous async-def endpoint that blocked "
     "the event loop. Use Background mode, or verify "
     "asyncio.to_thread is wrapping the upsert call in "
     "file_upload_service.process_upload."),
    ("\"Two concurrent uploads to the same table\"",
     "The single worker thread serialises uploads, so two go through "
     "fine in queue. But if you skip the worker queue (e.g., direct "
     "API call), staging tables can collide. Always go through the "
     "Upload Data UI."),
]
for q, a in pitfalls:
    add_h(doc, q, level=3)
    add_para(doc, a, space_after=8)


# ═══ 11. GLOSSARY ══════════════════════════════════════════════════════════
add_h(doc, "11. Glossary", level=1)
glossary = [
    ("ARS", "Auto Replenishment System — this application."),
    ("MSA", "Master Stock Allocation — the calculation that produces "
            "ARS_MSA_TOTAL / GEN_ART / VAR_ART."),
    ("BDC", "Business Document Creation — module for processing "
            "delivery documents into allocation sequences."),
    ("RDC", "Regional Distribution Centre — formerly ST_CD in MSA "
            "outputs."),
    ("SLOC", "Storage Location — a stock-holding sub-unit at a store."),
    ("SEG", "Segment — typically APP (apparel) or GM (general "
            "merchandise)."),
    ("RBAC", "Role-Based Access Control."),
    ("RLS", "Row-Level Security — filters rows so each user sees only "
            "their authorised data."),
    ("RCSI", "Read-Committed Snapshot Isolation — Azure SQL feature "
             "that lets readers and writers not block each other."),
    ("Upsert", "INSERT new rows + UPDATE existing rows in one operation."),
    ("Staging table", "Temporary holding table where uploaded data lands "
                      "before the final UPDATE / INSERT."),
    ("Fast bulk path", "The optimised upsert path: bulk insert into "
                       "staging, one big UPDATE, one big INSERT. ~30s for "
                       "165k rows."),
    ("Chunked MERGE path", "The fallback upsert path used when fast bulk "
                           "fails: 10k-row chunks each running a MERGE "
                           "statement. Slower (~minutes for 165k rows)."),
    ("DTU", "Database Transaction Unit — Azure SQL's resource budget "
            "unit. Quota issues here cause throttling."),
    ("Heartbeat", "Periodic timestamp updated by a running worker; lets "
                  "a reaper detect dead workers."),
    ("Pre-ping", "SQLAlchemy connection-pool feature that tests a "
                 "connection with SELECT 1 before checking it out — "
                 "catches connections killed by Azure SQL silently."),
]
tbl = doc.add_table(rows=1 + len(glossary), cols=2)
tbl.style = "Light Grid Accent 1"
hdr = tbl.rows[0].cells
hdr[0].text = "Term"
hdr[1].text = "Plain-English Meaning"
for c in hdr:
    shade_cell(c, "1F3A5F")
    for p in c.paragraphs:
        for r in p.runs:
            r.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
for i, (term, mean) in enumerate(glossary, start=1):
    tbl.rows[i].cells[0].text = term
    tbl.rows[i].cells[1].text = mean


# ─── FOOTER PAGE ────────────────────────────────────────────────────────────
doc.add_page_break()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("End of Document")
r.bold = True
r.font.size = Pt(14)
r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("ARS — Auto Replenishment System  •  V2 Retail")
r.font.size = Pt(10)
r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run(
    "If a step in this document doesn't match what you see in the app, "
    "the app is right and the document is stale — please log a doc bug."
)
r.italic = True
r.font.size = Pt(9)
r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)


# ─── SAVE ───────────────────────────────────────────────────────────────────
out_path = r"E:\ARS\doc\ARS_Complete_Process_Guide.docx"
doc.save(out_path)
print(f"Saved: {out_path}")
