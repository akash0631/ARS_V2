"""
Generate ARS Project Tracker BRD as a Word document.

Run:
    backend/venv/Scripts/python.exe docs/generate_project_tracker_brd.py
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT_PATH = r"e:\ARS\docs\ARS_Project_Tracker_BRD.docx"

PURPLE = RGBColor(0x4F, 0x46, 0xE5)
DARK   = RGBColor(0x11, 0x18, 0x27)
GREY   = RGBColor(0x6B, 0x72, 0x80)


def set_cell_bg(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def add_h1(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = PURPLE


def add_h2(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(14)
    r.font.color.rgb = DARK
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(4)


def add_h3(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(11.5)
    r.font.color.rgb = DARK
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)


def add_para(doc, text, italic=False, size=10.5):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.italic = italic


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.left_indent = Cm(0.5 + level * 0.6)
    r = p.runs[0] if p.runs else p.add_run('')
    p.runs[0].text = ''
    r2 = p.add_run(text)
    r2.font.size = Pt(10.5)


def add_code(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = 'Consolas'
    r.font.size = Pt(9)
    pPr = p.paragraph_format
    pPr.left_indent = Cm(0.4)
    pPr.space_after = Pt(2)
    # light grey background
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), 'F3F4F6')
    p._p.get_or_add_pPr().append(shd)


def add_table(doc, headers, rows, col_widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = 'Light List Accent 1'
    t.autofit = True
    # header
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ''
        p = c.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(10)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_bg(c, '4F46E5')
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    # body
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            c = t.rows[ri].cells[ci]
            c.text = ''
            p = c.paragraphs[0]
            r = p.add_run(str(val))
            r.font.size = Pt(9.5)
            c.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


# ────────────────────────────────────────────────────────────────────────────
# Build the document
# ────────────────────────────────────────────────────────────────────────────
doc = Document()

# Cover
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("ARS PROJECT TRACKER")
r.bold = True
r.font.size = Pt(28)
r.font.color.rgb = PURPLE

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("Business Requirements Document (BRD)")
r.font.size = Pt(16)
r.font.color.rgb = DARK

ver = doc.add_paragraph()
ver.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = ver.add_run("Version 1.0   •   ARS V2.0   •   2026-05-06")
r.italic = True
r.font.size = Pt(11)
r.font.color.rgb = GREY

doc.add_paragraph()

# Document control table
add_h2(doc, "Document Control")
add_table(doc,
    ["Field", "Value"],
    [
        ("Title", "ARS Project Tracker — BRD"),
        ("Version", "1.0"),
        ("Status", "DRAFT — for one-shot implementation"),
        ("Author", "Santosh Kumar (santosh@v2kart.com)"),
        ("Date", "2026-05-06"),
        ("Module", "ARS V2.0 → new module: Project Tracker (PT)"),
        ("Audience", "Implementer (Claude Code) + Akash Agarwal (Director)"),
    ],
    col_widths=[4, 12]
)

doc.add_page_break()

# 1. Executive Summary
add_h1(doc, "1. Executive Summary")
add_para(doc,
    "The ARS Project Tracker is a new in-app module that lets the V2 team plan, "
    "classify, prioritise, and track every change request, feature, bug, or "
    "infrastructure task in a single place. It supports unlimited parent → child "
    "project hierarchies, phase-based roadmaps (Phase 1 / 2 / 3 / Backlog), priority "
    "matrices, status workflows, kanban + phase boards, and a per-user dashboard. "
    "It reuses ARS's existing FastAPI + React stack, RBAC, audit logging, and SQL "
    "Server backend — no new infrastructure required.")

# 2. Business Objectives
add_h1(doc, "2. Business Objectives")
add_bullet(doc, "Centralise all V2 change requests in one tool — no more scattered Excel/WhatsApp/email.")
add_bullet(doc, "Classify work by phase (Phase 1, 2, 3, Backlog, Icebox) and priority (Critical, High, Medium, Low) so urgent items rise to the top automatically.")
add_bullet(doc, "Support hierarchy: a Project contains Sub-Projects, each Sub-Project contains Tasks. Progress rolls up.")
add_bullet(doc, "Give every stakeholder real-time visibility into status, blockers, owners, and due dates.")
add_bullet(doc, "Auto-log every change (status, owner, dates) for full audit traceability.")
add_bullet(doc, "Integrate with existing ARS users / RBAC — no separate login.")

# 3. Scope
add_h1(doc, "3. Scope")
add_h3(doc, "In Scope (MVP + Phase 2 + Phase 3)")
add_bullet(doc, "Project / Sub-Project / Task CRUD with hierarchy")
add_bullet(doc, "Status workflow: DRAFT → NOT_STARTED → IN_PROGRESS → BLOCKED / ON_HOLD → COMPLETED / CANCELLED")
add_bullet(doc, "Priority: CRITICAL, HIGH, MEDIUM, LOW")
add_bullet(doc, "Phase classification: PHASE_1, PHASE_2, PHASE_3, BACKLOG, ICEBOX")
add_bullet(doc, "Category / Tags: BUG, FEATURE, ENHANCEMENT, RESEARCH, MAINTENANCE, INFRA + free-form tags")
add_bullet(doc, "Assignees (multiple), Owner (single), Due Date, Start Date, Estimated/Actual hours")
add_bullet(doc, "Progress %  — manual or auto-rolled from children")
add_bullet(doc, "List view (filterable, sortable), Tree view, Kanban (by status), Phase board (by phase)")
add_bullet(doc, "Project detail page: description, comments, activity log, attachments, dependencies, children")
add_bullet(doc, "Dashboard with KPIs (open count, overdue, completed-this-week, by phase, by priority)")
add_bullet(doc, "My Tasks (filtered to current user)")
add_bullet(doc, "Saved filter views per user")
add_bullet(doc, "Comments (threaded), Activity log (auto), File attachments, Dependencies (predecessor links)")
add_bullet(doc, "RBAC: PT_VIEW / PT_CREATE / PT_EDIT / PT_DELETE / PT_ADMIN permissions")

add_h3(doc, "Out of Scope (defer to Phase 4+)")
add_bullet(doc, "Gantt timeline visualisation")
add_bullet(doc, "Resource capacity planning / utilisation")
add_bullet(doc, "Time-tracking with start/stop timer")
add_bullet(doc, "Email or push notifications (in-app activity feed only for MVP)")
add_bullet(doc, "Burndown / velocity charts")
add_bullet(doc, "External integrations (Jira, GitHub, Slack)")
add_bullet(doc, "Mobile app (web-responsive only)")

# 4. Stakeholders & Personas
add_h1(doc, "4. Stakeholders & Personas")
add_table(doc,
    ["Persona", "Role", "Primary Need"],
    [
        ("Director (Akash)", "Owner / approver", "Roadmap visibility, phase progress, executive dashboard"),
        ("Lead Developer (Santosh)", "Architect / planner", "Create projects, assign work, classify by phase, track blockers"),
        ("Developer", "Doer", "See My Tasks, update status, log time, comment"),
        ("Tester / Analyst", "Reporter", "File bugs, link to features, follow status"),
        ("Super Admin", "RBAC manager", "Manage permissions, view audit log, archive projects"),
    ],
    col_widths=[4, 4, 8]
)

# 5. User Stories
add_h1(doc, "5. User Stories")
add_para(doc, "Format: As a <role>, I want to <goal>, so that <benefit>.")
stories = [
    ("US-01", "Director", "see a phase-grouped roadmap of all projects",
        "I can communicate priorities to the team in one screen"),
    ("US-02", "Director", "filter projects by Priority=Critical",
        "I see only the items that need immediate attention"),
    ("US-03", "Lead Dev", "create a project with sub-projects and tasks",
        "I can break down work hierarchically"),
    ("US-04", "Lead Dev", "classify a project as Phase 2 / Medium priority",
        "I can defer non-urgent work without losing it"),
    ("US-05", "Lead Dev", "drag a project between status columns on the kanban",
        "I can update many items quickly"),
    ("US-06", "Developer", "see only my open tasks on a 'My Tasks' page",
        "I know what to work on today"),
    ("US-07", "Developer", "comment on a project and @mention a teammate",
        "We can have async discussions in context"),
    ("US-08", "Developer", "mark a task as Blocked with a reason",
        "Lead Dev can unblock me quickly"),
    ("US-09", "Tester", "file a bug under an existing project",
        "Bugs are linked to the feature they affect"),
    ("US-10", "Anyone", "see the full activity log of a project",
        "I understand who changed what and when"),
    ("US-11", "Lead Dev", "save a custom filter ('My Phase 1 Critical Bugs')",
        "I don't rebuild filters every visit"),
    ("US-12", "Director", "see a dashboard tile of overdue items",
        "I can intervene before deadlines slip"),
    ("US-13", "Anyone", "attach a screenshot or file to a project",
        "Context lives with the project, not in email"),
    ("US-14", "Lead Dev", "set Project B as depending on Project A",
        "B can't start until A is complete"),
    ("US-15", "Super Admin", "archive completed projects older than 90 days",
        "The active list stays clean"),
]
add_table(doc,
    ["ID", "Role", "Goal", "Benefit"],
    [(s[0], s[1], s[2], s[3]) for s in stories],
    col_widths=[1.5, 2.5, 6, 6]
)

# 6. Functional Requirements
add_h1(doc, "6. Functional Requirements")

add_h3(doc, "6.1 Project Hierarchy")
add_bullet(doc, "FR-1.1 A Project record may have a PARENT_ID pointing to another Project record.")
add_bullet(doc, "FR-1.2 Maximum nesting depth is 3 (Project → Sub-Project → Task). System rejects deeper inserts.")
add_bullet(doc, "FR-1.3 PROJECT_TYPE auto-set: depth 0 = PROJECT, depth 1 = SUB_PROJECT, depth 2 = TASK.")
add_bullet(doc, "FR-1.4 Deleting a parent soft-deletes (archives) all descendants.")
add_bullet(doc, "FR-1.5 Moving a project to a new parent re-validates depth.")

add_h3(doc, "6.2 Status Workflow")
add_bullet(doc, "FR-2.1 Allowed statuses: DRAFT, NOT_STARTED, IN_PROGRESS, BLOCKED, ON_HOLD, COMPLETED, CANCELLED.")
add_bullet(doc, "FR-2.2 Allowed transitions: any → any (free workflow). UI shows recommended next states.")
add_bullet(doc, "FR-2.3 When transitioning to COMPLETED, system stamps COMPLETED_DATE = GETDATE() and sets PROGRESS_PCT = 100.")
add_bullet(doc, "FR-2.4 When transitioning to BLOCKED, the user must enter a blocker reason (saved as a comment).")

add_h3(doc, "6.3 Priority & Phase")
add_bullet(doc, "FR-3.1 PRIORITY ∈ {CRITICAL, HIGH, MEDIUM, LOW}. Default = MEDIUM.")
add_bullet(doc, "FR-3.2 PHASE ∈ {PHASE_1, PHASE_2, PHASE_3, BACKLOG, ICEBOX}. Default = BACKLOG.")
add_bullet(doc, "FR-3.3 List & dashboard sort default: PRIORITY DESC, DUE_DATE ASC.")

add_h3(doc, "6.4 Progress Calculation")
add_bullet(doc, "FR-4.1 If AUTO_PROGRESS=1 (default) and the project has children, PROGRESS_PCT = AVG(child.PROGRESS_PCT).")
add_bullet(doc, "FR-4.2 If AUTO_PROGRESS=0 OR no children, PROGRESS_PCT is user-editable (0..100).")
add_bullet(doc, "FR-4.3 Recompute on every child status/progress change (handled by service layer).")

add_h3(doc, "6.5 Comments")
add_bullet(doc, "FR-5.1 Any user with PT_VIEW can read comments.")
add_bullet(doc, "FR-5.2 Any user with PT_VIEW can create top-level or threaded reply comments.")
add_bullet(doc, "FR-5.3 Users can edit/soft-delete their own comments only (super-admin can edit/delete any).")
add_bullet(doc, "FR-5.4 Markdown rendering supported (bold, italic, code, links, lists).")

add_h3(doc, "6.6 Activity Log")
add_bullet(doc, "FR-6.1 Every CREATE/UPDATE/DELETE writes a row to PT_ACTIVITY_LOG with old → new diff.")
add_bullet(doc, "FR-6.2 Activity feed on detail page shows reverse-chronological log + comments inline.")
add_bullet(doc, "FR-6.3 Tracked fields: STATUS, PRIORITY, PHASE, OWNER_USERNAME, ASSIGNEES, DUE_DATE, PROGRESS_PCT.")

add_h3(doc, "6.7 Attachments")
add_bullet(doc, "FR-7.1 Allowed types: image (png/jpg/gif), pdf, docx, xlsx, csv, txt, log.")
add_bullet(doc, "FR-7.2 Max file size: 25 MB per file. Stored in backend/uploads/pt/<project_id>/.")
add_bullet(doc, "FR-7.3 Owner or super-admin can delete; everyone with PT_VIEW can download.")

add_h3(doc, "6.8 Dependencies")
add_bullet(doc, "FR-8.1 A project may have N predecessors (DEPENDS_ON_ID) of type FS (finish-to-start) by default.")
add_bullet(doc, "FR-8.2 UI warns if user attempts to mark COMPLETED while a predecessor is not COMPLETED — does not block (warning only).")
add_bullet(doc, "FR-8.3 Cyclic dependencies are rejected (server-side cycle check on insert).")

add_h3(doc, "6.9 Filters & Saved Views")
add_bullet(doc, "FR-9.1 List view supports filters: status, priority, phase, owner, assignee, search-text, tag, due-date range.")
add_bullet(doc, "FR-9.2 User can save current filter as a named view (PT_SAVED_VIEW) and mark one as default.")
add_bullet(doc, "FR-9.3 List view supports sort by any column.")

add_h3(doc, "6.10 Dashboard")
add_bullet(doc, "FR-10.1 Tiles: Total Open, Overdue, Completed (last 7 days), My Open, Critical Open.")
add_bullet(doc, "FR-10.2 Charts: Status distribution (donut), Phase distribution (bar), Priority distribution (bar), Completion trend (line, last 30 days).")
add_bullet(doc, "FR-10.3 'Top 10 overdue' table.")

add_h3(doc, "6.11 RBAC")
add_bullet(doc, "FR-11.1 New permissions: PT_VIEW, PT_CREATE, PT_EDIT, PT_DELETE, PT_ADMIN.")
add_bullet(doc, "FR-11.2 PT_VIEW required for all GET endpoints.")
add_bullet(doc, "FR-11.3 PT_CREATE for POST /projects, PT_EDIT for PUT, PT_DELETE for DELETE.")
add_bullet(doc, "FR-11.4 PT_ADMIN bypasses owner-only restrictions (e.g. edit any comment, archive bulk).")
add_bullet(doc, "FR-11.5 SUPER_ADMIN role is granted all PT_* permissions automatically.")

# 7. Non-Functional Requirements
add_h1(doc, "7. Non-Functional Requirements")
add_table(doc,
    ["ID", "Category", "Requirement"],
    [
        ("NFR-1", "Performance", "List page loads ≤ 1s for 500 projects with default filters."),
        ("NFR-2", "Performance", "Detail page loads ≤ 800ms (including 50 comments + 50 activity rows)."),
        ("NFR-3", "Scale", "Support 10,000 projects, 100,000 activity rows, 50 concurrent users."),
        ("NFR-4", "Security", "All endpoints require JWT auth via existing get_current_user dependency."),
        ("NFR-5", "Audit", "Activity log is append-only; no UPDATE/DELETE allowed by app code."),
        ("NFR-6", "Reliability", "Soft delete only (IS_ARCHIVED=1); hard delete requires PT_ADMIN + confirmation."),
        ("NFR-7", "Usability", "Mobile-responsive (works on tablet ≥ 768 px wide)."),
        ("NFR-8", "Maintainability", "Code mirrors existing ARS conventions (FastAPI/SQLAlchemy/Pydantic, React functional + hooks)."),
        ("NFR-9", "Logging", "All POST/PUT/DELETE write a loguru INFO line with batch_id, actor, project_id."),
        ("NFR-10", "Backward compat", "No changes to existing tables; PT_* tables are net-new."),
    ],
    col_widths=[1.5, 3, 11]
)

# 8. Data Model
add_h1(doc, "8. Data Model")
add_para(doc, "All tables created in the rep_data database (same as other ARS tables). Schema script lives at backend/sql/pt_schema.sql.")

add_h3(doc, "8.1 PT_PROJECT (main hierarchy table)")
add_code(doc, """CREATE TABLE PT_PROJECT (
    PROJECT_ID         INT IDENTITY(1,1) PRIMARY KEY,
    PARENT_ID          INT NULL,
    PROJECT_CODE       NVARCHAR(50) NOT NULL UNIQUE,
    NAME               NVARCHAR(255) NOT NULL,
    DESCRIPTION        NVARCHAR(MAX),
    PROJECT_TYPE       NVARCHAR(20) NOT NULL,    -- PROJECT|SUB_PROJECT|TASK
    STATUS             NVARCHAR(30) NOT NULL,    -- DRAFT|NOT_STARTED|IN_PROGRESS|BLOCKED|ON_HOLD|COMPLETED|CANCELLED
    PRIORITY           NVARCHAR(20) NOT NULL,    -- CRITICAL|HIGH|MEDIUM|LOW
    PHASE              NVARCHAR(20),             -- PHASE_1|PHASE_2|PHASE_3|BACKLOG|ICEBOX
    CATEGORY           NVARCHAR(30),             -- BUG|FEATURE|ENHANCEMENT|RESEARCH|MAINTENANCE|INFRA
    TAGS               NVARCHAR(500),
    OWNER_USERNAME     NVARCHAR(100),
    ASSIGNEES          NVARCHAR(MAX),            -- JSON array of usernames
    PROGRESS_PCT       INT NOT NULL DEFAULT 0,
    AUTO_PROGRESS      BIT NOT NULL DEFAULT 1,
    START_DATE         DATE,
    DUE_DATE           DATE,
    COMPLETED_DATE     DATETIME,
    ESTIMATED_HOURS    FLOAT,
    ACTUAL_HOURS       FLOAT,
    SORT_ORDER         INT NOT NULL DEFAULT 0,
    IS_ARCHIVED        BIT NOT NULL DEFAULT 0,
    CREATED_BY         NVARCHAR(100),
    CREATED_AT         DATETIME NOT NULL DEFAULT GETDATE(),
    UPDATED_BY         NVARCHAR(100),
    UPDATED_AT         DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_PT_PROJECT_PARENT
        FOREIGN KEY (PARENT_ID) REFERENCES PT_PROJECT(PROJECT_ID)
);
CREATE INDEX IX_PT_PROJECT_PARENT ON PT_PROJECT(PARENT_ID);
CREATE INDEX IX_PT_PROJECT_STATUS ON PT_PROJECT(STATUS, IS_ARCHIVED);
CREATE INDEX IX_PT_PROJECT_PHASE  ON PT_PROJECT(PHASE,  IS_ARCHIVED);
CREATE INDEX IX_PT_PROJECT_OWNER  ON PT_PROJECT(OWNER_USERNAME);
CREATE INDEX IX_PT_PROJECT_DUE    ON PT_PROJECT(DUE_DATE);""")

add_h3(doc, "8.2 PT_COMMENT (threaded discussion)")
add_code(doc, """CREATE TABLE PT_COMMENT (
    COMMENT_ID         INT IDENTITY(1,1) PRIMARY KEY,
    PROJECT_ID         INT NOT NULL,
    PARENT_COMMENT_ID  INT NULL,
    COMMENT_TEXT       NVARCHAR(MAX) NOT NULL,
    CREATED_BY         NVARCHAR(100) NOT NULL,
    CREATED_AT         DATETIME NOT NULL DEFAULT GETDATE(),
    EDITED_AT          DATETIME,
    IS_DELETED         BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_PT_COMMENT_PROJECT
        FOREIGN KEY (PROJECT_ID) REFERENCES PT_PROJECT(PROJECT_ID)
);
CREATE INDEX IX_PT_COMMENT_PROJECT ON PT_COMMENT(PROJECT_ID, CREATED_AT DESC);""")

add_h3(doc, "8.3 PT_ACTIVITY_LOG (audit, append-only)")
add_code(doc, """CREATE TABLE PT_ACTIVITY_LOG (
    ACTIVITY_ID        INT IDENTITY(1,1) PRIMARY KEY,
    PROJECT_ID         INT NOT NULL,
    ACTIVITY_TYPE      NVARCHAR(50) NOT NULL,    -- CREATED|FIELD_CHANGED|COMMENT_ADDED|ATTACHMENT_ADDED|...
    FIELD_NAME         NVARCHAR(100),
    OLD_VALUE          NVARCHAR(MAX),
    NEW_VALUE          NVARCHAR(MAX),
    ACTOR              NVARCHAR(100) NOT NULL,
    CREATED_AT         DATETIME NOT NULL DEFAULT GETDATE(),
    DETAILS            NVARCHAR(MAX)             -- JSON for extra context
);
CREATE INDEX IX_PT_ACTIVITY_PROJECT ON PT_ACTIVITY_LOG(PROJECT_ID, CREATED_AT DESC);""")

add_h3(doc, "8.4 PT_ATTACHMENT")
add_code(doc, """CREATE TABLE PT_ATTACHMENT (
    ATTACHMENT_ID      INT IDENTITY(1,1) PRIMARY KEY,
    PROJECT_ID         INT NOT NULL,
    FILE_NAME          NVARCHAR(255) NOT NULL,
    FILE_PATH          NVARCHAR(500) NOT NULL,
    FILE_SIZE          BIGINT,
    MIME_TYPE          NVARCHAR(100),
    UPLOADED_BY        NVARCHAR(100),
    UPLOADED_AT        DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT FK_PT_ATTACHMENT_PROJECT
        FOREIGN KEY (PROJECT_ID) REFERENCES PT_PROJECT(PROJECT_ID)
);""")

add_h3(doc, "8.5 PT_DEPENDENCY")
add_code(doc, """CREATE TABLE PT_DEPENDENCY (
    DEPENDENCY_ID      INT IDENTITY(1,1) PRIMARY KEY,
    PROJECT_ID         INT NOT NULL,             -- successor
    DEPENDS_ON_ID      INT NOT NULL,             -- predecessor
    DEP_TYPE           NVARCHAR(20) NOT NULL DEFAULT 'FS',
    CREATED_BY         NVARCHAR(100),
    CREATED_AT         DATETIME NOT NULL DEFAULT GETDATE(),
    CONSTRAINT UQ_PT_DEP UNIQUE (PROJECT_ID, DEPENDS_ON_ID)
);""")

add_h3(doc, "8.6 PT_SAVED_VIEW")
add_code(doc, """CREATE TABLE PT_SAVED_VIEW (
    VIEW_ID            INT IDENTITY(1,1) PRIMARY KEY,
    USERNAME           NVARCHAR(100) NOT NULL,
    NAME               NVARCHAR(100) NOT NULL,
    FILTER_JSON        NVARCHAR(MAX) NOT NULL,
    IS_DEFAULT         BIT NOT NULL DEFAULT 0,
    CREATED_AT         DATETIME NOT NULL DEFAULT GETDATE()
);""")

# 9. API Specification
add_h1(doc, "9. API Specification")
add_para(doc, "Base path: /api/v1/pt/  •  All endpoints require JWT (existing get_current_user dependency).")

add_h3(doc, "9.1 Project endpoints")
add_table(doc,
    ["Method", "Path", "Permission", "Purpose"],
    [
        ("POST",   "/projects",                          "PT_CREATE", "Create project (auto-derives PROJECT_TYPE from depth)"),
        ("GET",    "/projects",                          "PT_VIEW",   "List with filters: status, priority, phase, owner, assignee, q (search), tag, parent_id, due_before, due_after"),
        ("GET",    "/projects/tree",                     "PT_VIEW",   "Hierarchical JSON: roots with nested children"),
        ("GET",    "/projects/{id}",                     "PT_VIEW",   "Full detail incl. children/comments/activity counts"),
        ("PUT",    "/projects/{id}",                     "PT_EDIT",   "Update fields; auto-write activity rows for diffs"),
        ("DELETE", "/projects/{id}",                     "PT_DELETE", "Soft delete (IS_ARCHIVED=1) cascading to descendants"),
        ("POST",   "/projects/{id}/move",                "PT_EDIT",   "Body: {new_parent_id}. Validates depth ≤ 3"),
        ("POST",   "/projects/{id}/duplicate",           "PT_CREATE", "Clone with name + ' (copy)' and reset status to DRAFT"),
        ("POST",   "/projects/bulk-update",              "PT_EDIT",   "Body: {ids: [], updates: {…}}. Bulk patch"),
        ("GET",    "/projects/{id}/children",            "PT_VIEW",   "Direct children only"),
        ("GET",    "/projects/{id}/ancestors",           "PT_VIEW",   "Breadcrumb chain to root"),
    ],
    col_widths=[1.6, 5.5, 2.4, 7.5]
)

add_h3(doc, "9.2 Comments / Activity / Attachments / Dependencies")
add_table(doc,
    ["Method", "Path", "Permission", "Purpose"],
    [
        ("GET",    "/projects/{id}/comments",                    "PT_VIEW",   "Threaded list"),
        ("POST",   "/projects/{id}/comments",                    "PT_VIEW",   "Body: {text, parent_comment_id?}"),
        ("PUT",    "/comments/{cid}",                            "PT_VIEW",   "Edit own (or PT_ADMIN)"),
        ("DELETE", "/comments/{cid}",                            "PT_VIEW",   "Soft delete own (or PT_ADMIN)"),
        ("GET",    "/projects/{id}/activity",                    "PT_VIEW",   "Reverse-chronological log"),
        ("POST",   "/projects/{id}/attachments",                 "PT_EDIT",   "multipart/form-data; max 25 MB"),
        ("GET",    "/projects/{id}/attachments",                 "PT_VIEW",   "List metadata"),
        ("GET",    "/attachments/{aid}/download",                "PT_VIEW",   "Streamed file"),
        ("DELETE", "/attachments/{aid}",                         "PT_EDIT",   "Owner or PT_ADMIN"),
        ("POST",   "/dependencies",                              "PT_EDIT",   "Body: {project_id, depends_on_id}; cycle check"),
        ("DELETE", "/dependencies/{did}",                        "PT_EDIT",   "Remove edge"),
        ("GET",    "/projects/{id}/dependencies",                "PT_VIEW",   "Predecessors + successors"),
    ],
    col_widths=[1.6, 5.5, 2.4, 7.5]
)

add_h3(doc, "9.3 Dashboard / Reports / Saved Views")
add_table(doc,
    ["Method", "Path", "Permission", "Purpose"],
    [
        ("GET", "/dashboard",            "PT_VIEW", "KPI tiles + charts payload"),
        ("GET", "/my-work",              "PT_VIEW", "Current user's open assignments"),
        ("GET", "/board",                "PT_VIEW", "Kanban — grouped by status"),
        ("GET", "/phases",               "PT_VIEW", "Phase board — grouped by PHASE"),
        ("GET", "/reports/overdue",      "PT_VIEW", "DUE_DATE < today AND status not COMPLETED/CANCELLED"),
        ("GET", "/reports/by-priority",  "PT_VIEW", "Counts/sums grouped by priority"),
        ("GET", "/views",                "PT_VIEW", "User's saved views"),
        ("POST", "/views",               "PT_VIEW", "Body: {name, filter_json, is_default}"),
        ("DELETE", "/views/{vid}",       "PT_VIEW", "Owner or PT_ADMIN"),
    ],
    col_widths=[1.6, 5.5, 2.4, 7.5]
)

add_h3(doc, "9.4 Sample Pydantic schemas")
add_code(doc, """class ProjectCreate(BaseModel):
    parent_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: Literal['DRAFT','NOT_STARTED','IN_PROGRESS','BLOCKED','ON_HOLD',
                    'COMPLETED','CANCELLED'] = 'NOT_STARTED'
    priority: Literal['CRITICAL','HIGH','MEDIUM','LOW'] = 'MEDIUM'
    phase: Optional[Literal['PHASE_1','PHASE_2','PHASE_3','BACKLOG','ICEBOX']] = 'BACKLOG'
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    owner_username: Optional[str] = None
    assignees: Optional[List[str]] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimated_hours: Optional[float] = None

class ProjectUpdate(BaseModel):
    # All fields optional — PATCH semantics
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    phase: Optional[str] = None
    progress_pct: Optional[int] = Field(None, ge=0, le=100)
    # ... etc

class ProjectOut(BaseModel):
    project_id: int
    project_code: str
    parent_id: Optional[int]
    name: str
    status: str
    priority: str
    phase: Optional[str]
    progress_pct: int
    owner_username: Optional[str]
    assignees: List[str]
    due_date: Optional[date]
    children_count: int
    comments_count: int
    is_overdue: bool
    created_at: datetime""")

# 10. UI / UX Layout
add_h1(doc, "10. UI / UX Layout")
add_para(doc, "Reuses ARS design system (purple #4F46E5, slate textures, Inter font, lucide-react icons). All pages mobile-responsive ≥ 768 px.")

add_h3(doc, "10.1 Navigation")
add_para(doc, "New sidebar section 'Project Tracker' with sub-items:")
add_bullet(doc, "Dashboard")
add_bullet(doc, "All Projects (list + tree toggle)")
add_bullet(doc, "Kanban Board")
add_bullet(doc, "Phase Board")
add_bullet(doc, "My Tasks")

add_h3(doc, "10.2 Page wireframes")
add_table(doc,
    ["Page", "Layout"],
    [
        ("Dashboard",
         "Top: 5 KPI tiles. Mid: 3 donut/bar charts. Bottom: 'Top 10 Overdue' table."),
        ("Projects List",
         "Filter bar (status/priority/phase/owner/search) + saved-view dropdown. Table: code | name (indented for hierarchy) | status badge | priority chip | phase chip | owner | due | progress bar. Bulk-select checkbox column."),
        ("Project Detail",
         "Header: code, name, status, priority, phase, due, owner, progress. Tabs: Overview | Sub-projects | Comments | Activity | Attachments | Dependencies."),
        ("Create / Edit",
         "Modal or full-page form: Name (req), Description (markdown), Status, Priority, Phase, Category, Tags, Owner (user select), Assignees (multi user select), Start, Due, Estimated Hours, Parent (project picker)."),
        ("Kanban Board",
         "5 columns (NOT_STARTED, IN_PROGRESS, BLOCKED, ON_HOLD, COMPLETED). Drag card between columns → status update. WIP limit indicator per column."),
        ("Phase Board",
         "5 columns (PHASE_1, PHASE_2, PHASE_3, BACKLOG, ICEBOX). Drag card between phases. Tile colour = priority."),
        ("My Tasks",
         "Same as list but pre-filtered to assignees CONTAINS current user, status NOT IN (COMPLETED, CANCELLED). Sort by due date."),
    ],
    col_widths=[3, 13]
)

add_h3(doc, "10.3 Status & Priority Visual Conventions")
add_table(doc,
    ["Token", "Colour", "Usage"],
    [
        ("CRITICAL",  "#DC2626 (red)",     "Priority chip"),
        ("HIGH",      "#EA580C (orange)",  "Priority chip"),
        ("MEDIUM",    "#CA8A04 (yellow)",  "Priority chip"),
        ("LOW",       "#16A34A (green)",   "Priority chip"),
        ("IN_PROGRESS","#2563EB (blue)",   "Status badge"),
        ("BLOCKED",   "#DC2626 (red)",     "Status badge"),
        ("ON_HOLD",   "#6B7280 (grey)",    "Status badge"),
        ("COMPLETED", "#16A34A (green)",   "Status badge"),
        ("CANCELLED", "#9CA3AF (slate)",   "Status badge"),
    ],
    col_widths=[3.5, 4.5, 8]
)

# 11. Implementation Phases
add_h1(doc, "11. Implementation Phases")

add_h3(doc, "Phase 1 — MVP (target: ~2 days of single-shot Claude work)")
add_bullet(doc, "DB schema script (backend/sql/pt_schema.sql) executed on rep_data")
add_bullet(doc, "Backend models, schemas, service, endpoints for Project CRUD + hierarchy")
add_bullet(doc, "Backend RBAC permissions seeded (PT_VIEW/CREATE/EDIT/DELETE/ADMIN) for SUPER_ADMIN")
add_bullet(doc, "Frontend: Sidebar entry + 3 pages (Dashboard, List, Detail) + Create/Edit modal")
add_bullet(doc, "Frontend api.js wrapper at frontend/src/services/pt_api.js")

add_h3(doc, "Phase 2 — Boards + Comments + Activity")
add_bullet(doc, "Kanban board page with drag-and-drop")
add_bullet(doc, "Phase board page")
add_bullet(doc, "Comments tab with threaded UI")
add_bullet(doc, "Activity log auto-recording on every PUT")
add_bullet(doc, "My Tasks page")

add_h3(doc, "Phase 3 — Attachments + Dependencies + Saved Views")
add_bullet(doc, "Attachments upload/download/delete")
add_bullet(doc, "Dependencies UI + cycle check")
add_bullet(doc, "Saved filter views per user")
add_bullet(doc, "Bulk update")
add_bullet(doc, "Reports (overdue, by priority)")

add_h3(doc, "Phase 4 — Notifications & advanced (deferred)")
add_bullet(doc, "Email/in-app notifications on assignment, comment, status change")
add_bullet(doc, "Gantt timeline")
add_bullet(doc, "Calendar view")
add_bullet(doc, "Export to Excel")
add_bullet(doc, "Time tracking / burndown")

# 12. File Structure
add_h1(doc, "12. File Structure (one-shot scaffold)")
add_h3(doc, "Backend")
add_code(doc, """backend/
├── sql/
│   └── pt_schema.sql                  # NEW — 6 tables + indexes
├── app/
│   ├── models/
│   │   └── pt.py                      # NEW — SQLAlchemy ORM (Project, Comment, Activity, Attachment, Dependency, SavedView)
│   ├── schemas/
│   │   └── pt.py                      # NEW — Pydantic schemas (Create/Update/Out for each)
│   ├── services/
│   │   └── pt_service.py              # NEW — business logic (depth check, progress rollup, activity logging, cycle check)
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   └── pt.py                  # NEW — all PT routes
│   │   └── router.py                  # MODIFIED — register pt router
│   └── security/
│       └── permissions.py             # MODIFIED — add PT_* permission constants""")

add_h3(doc, "Frontend")
add_code(doc, """frontend/src/
├── pages/pt/
│   ├── DashboardPage.jsx              # NEW
│   ├── ProjectsListPage.jsx           # NEW
│   ├── ProjectDetailPage.jsx          # NEW
│   ├── BoardPage.jsx                  # NEW (kanban)
│   ├── PhasesPage.jsx                 # NEW
│   └── MyTasksPage.jsx                # NEW
├── components/pt/
│   ├── ProjectTree.jsx                # NEW
│   ├── ProjectCard.jsx                # NEW (used in board + list)
│   ├── ProjectForm.jsx                # NEW (create/edit modal)
│   ├── StatusBadge.jsx                # NEW
│   ├── PriorityChip.jsx               # NEW
│   ├── PhaseChip.jsx                  # NEW
│   ├── CommentThread.jsx              # NEW
│   ├── ActivityFeed.jsx               # NEW
│   └── AttachmentList.jsx             # NEW
├── services/
│   └── pt_api.js                      # NEW — fetch wrappers
├── App.jsx                            # MODIFIED — add /pt/* routes
└── components/layout/Sidebar.jsx      # MODIFIED — add Project Tracker section""")

# 13. Acceptance Criteria
add_h1(doc, "13. Acceptance Criteria")
ac = [
    ("AC-01", "User can create a Phase 1 / Critical / IN_PROGRESS project with one parent + 2 children. Detail page shows all 3 levels."),
    ("AC-02", "Setting child to COMPLETED auto-recomputes parent PROGRESS_PCT (e.g. 1 of 2 children done → 50%)."),
    ("AC-03", "List page filtered by Phase=PHASE_1 + Priority=CRITICAL returns only matching rows."),
    ("AC-04", "Kanban: dragging a card from IN_PROGRESS to BLOCKED prompts for blocker reason; comment is saved automatically."),
    ("AC-05", "Activity tab shows 'Santosh changed Status from IN_PROGRESS to BLOCKED at 2026-05-06 14:23'."),
    ("AC-06", "User without PT_EDIT cannot see Edit / Delete buttons; PUT endpoint returns 403."),
    ("AC-07", "Overdue dashboard tile counts only items with DUE_DATE < today AND status NOT IN (COMPLETED, CANCELLED)."),
    ("AC-08", "Cyclic dependency attempt (A → B → A) returns 400 with clear error."),
    ("AC-09", "Soft-deleted project hides from default list; super-admin Archive view shows it; restore works."),
    ("AC-10", "Saved view 'My P1 Critical' persists across sessions and applies on next visit."),
    ("AC-11", "Page works on tablet (≥ 768 px) — sidebar collapses, table scrolls horizontally."),
    ("AC-12", "Backend handles 1000 projects in list endpoint in ≤ 1 s end-to-end."),
]
add_table(doc,
    ["ID", "Acceptance Criterion"],
    [(a[0], a[1]) for a in ac],
    col_widths=[1.5, 14.5]
)

# 14. Risks
add_h1(doc, "14. Risks & Mitigations")
add_table(doc,
    ["Risk", "Impact", "Likelihood", "Mitigation"],
    [
        ("Hierarchy depth abuse", "Medium", "Medium", "Hard depth cap (3) enforced server-side; UI hides 'Add Child' on TASK rows."),
        ("Activity log table grows unboundedly", "Medium", "High", "Add archival job (move > 1 year to PT_ACTIVITY_LOG_HISTORY)."),
        ("Attachment storage fills disk", "High", "Medium", "Per-project quota (200 MB) + total cap; warn user > 80%."),
        ("Cycle in dependencies", "Medium", "Low", "Server-side cycle check on every POST /dependencies."),
        ("RBAC bypass", "High", "Low", "All endpoints route through Depends(RequirePermissions([…])) — covered by existing tests."),
        ("Concurrent edits", "Low", "Medium", "Optimistic UPDATED_AT check; 409 on stale write; UI offers reload."),
    ],
    col_widths=[4, 2, 2.5, 7.5]
)

# 15. Migration & Rollout
add_h1(doc, "15. Migration & Rollout Plan")
add_bullet(doc, "Step 1: Run pt_schema.sql against rep_data on hopc560 (idempotent — wraps each CREATE in IF NOT EXISTS).")
add_bullet(doc, "Step 2: Seed PT_* permissions into ARS_permission table; assign to SUPER_ADMIN role.")
add_bullet(doc, "Step 3: Deploy backend (zip-deploy to ars-v2retail-api). Smoke-test /pt/dashboard.")
add_bullet(doc, "Step 4: Deploy frontend (npm run build → static folder).")
add_bullet(doc, "Step 5: Demo session with Director (Akash) to seed first 5 real projects.")
add_bullet(doc, "Step 6: Train team in 30-min walkthrough; share short video.")
add_bullet(doc, "No data migration needed — net-new module. No down-time required.")

# 16. Testing Plan
add_h1(doc, "16. Testing Plan")
add_h3(doc, "Backend (pytest)")
add_bullet(doc, "Unit: ProjectService.create / update / delete / move / progress rollup / cycle check")
add_bullet(doc, "Integration: full CRUD via TestClient, RBAC denial paths, hierarchy depth limit")
add_bullet(doc, "Performance: seed 1000 projects, assert list endpoint < 1s")

add_h3(doc, "Frontend (manual + Cypress optional)")
add_bullet(doc, "Smoke: each page loads without console errors")
add_bullet(doc, "Flows: create → assign → move kanban → comment → mark complete → see in dashboard")
add_bullet(doc, "Responsive: tablet breakpoint sanity check")

# 17. Open Questions
add_h1(doc, "17. Open Questions (to confirm before build)")
add_bullet(doc, "Q1: Should hierarchy go deeper than 3 levels? (Default: NO — keep simple.)")
add_bullet(doc, "Q2: Markdown vs rich-text for description/comments? (Default: Markdown, simpler.)")
add_bullet(doc, "Q3: Default phase for new projects — BACKLOG or PHASE_1? (Default: BACKLOG.)")
add_bullet(doc, "Q4: Email notifications in MVP or Phase 4? (Default: Phase 4.)")
add_bullet(doc, "Q5: Allow editing past activity log entries by SUPER_ADMIN? (Default: NO — append-only.)")

# 18. Sign-off
add_h1(doc, "18. Sign-off")
add_para(doc,
    "Approved by:  ________________________________   Director (Akash Agarwal)        Date: ____________")
doc.add_paragraph()
add_para(doc,
    "Approved by:  ________________________________   Lead Developer (Santosh Kumar)  Date: ____________")

# Appendix
doc.add_page_break()
add_h1(doc, "Appendix A — Sample Seed Projects")
add_para(doc, "Suggested first 5 projects to populate the system on day 1, demonstrating the classification model:")
add_table(doc,
    ["#", "Name", "Phase", "Priority", "Category"],
    [
        (1, "ARS V2 Production Stabilisation", "PHASE_1", "CRITICAL", "MAINTENANCE"),
        (2, "Listing Engine Pandas Refactor",   "PHASE_1", "HIGH",     "ENHANCEMENT"),
        (3, "OPT_TYPE Filter Feature",          "PHASE_1", "MEDIUM",   "FEATURE"),
        (4, "Project Tracker Module (this BRD)","PHASE_2", "HIGH",     "FEATURE"),
        (5, "Mobile Field-Ops App",             "PHASE_3", "LOW",      "RESEARCH"),
    ],
    col_widths=[1, 7, 2, 2, 2.5]
)

add_h1(doc, "Appendix B — Sample SQL Queries")
add_h3(doc, "All overdue Phase 1 critical items")
add_code(doc, """SELECT PROJECT_CODE, NAME, OWNER_USERNAME, DUE_DATE,
       DATEDIFF(day, DUE_DATE, GETDATE()) AS days_overdue
FROM PT_PROJECT
WHERE IS_ARCHIVED = 0
  AND PHASE = 'PHASE_1'
  AND PRIORITY = 'CRITICAL'
  AND STATUS NOT IN ('COMPLETED', 'CANCELLED')
  AND DUE_DATE < CAST(GETDATE() AS DATE)
ORDER BY days_overdue DESC;""")

add_h3(doc, "Auto progress rollup for one parent")
add_code(doc, """;WITH ChildAvg AS (
    SELECT PARENT_ID, AVG(CAST(PROGRESS_PCT AS FLOAT)) AS avg_pct
    FROM PT_PROJECT
    WHERE IS_ARCHIVED = 0 AND PARENT_ID = @parent_id
    GROUP BY PARENT_ID
)
UPDATE p
SET p.PROGRESS_PCT = CAST(c.avg_pct AS INT),
    p.UPDATED_AT   = GETDATE()
FROM PT_PROJECT p
INNER JOIN ChildAvg c ON c.PARENT_ID = p.PROJECT_ID
WHERE p.AUTO_PROGRESS = 1;""")

add_h3(doc, "Cycle check on insert dependency (A → B; check B doesn't already reach A)")
add_code(doc, """;WITH Reach AS (
    SELECT PROJECT_ID, DEPENDS_ON_ID FROM PT_DEPENDENCY WHERE PROJECT_ID = @b
    UNION ALL
    SELECT d.PROJECT_ID, d.DEPENDS_ON_ID
    FROM PT_DEPENDENCY d
    INNER JOIN Reach r ON d.PROJECT_ID = r.DEPENDS_ON_ID
)
SELECT 1 WHERE EXISTS (SELECT 1 FROM Reach WHERE DEPENDS_ON_ID = @a);
-- if any row returned → cycle, reject""")

# End
doc.save(OUT_PATH)
print(f"BRD written to {OUT_PATH}")
