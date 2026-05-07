"""
Focus / Hero list API.

CRUD over Master_FOCUS_LIST plus a CSV/XLSX bulk-upload endpoint with
row-by-row validation. The allocation engine reads FOCUS_W_CAP /
FOCUS_WO_CAP from ARS_LISTING_WORKING; this module is the planner-
facing surface that populates that master table. The actual
working_table flag-write happens during /listing/generate via
focus_list.apply_focus_flags() — see the hook in listing.py.
"""
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel

from app.database.session import get_data_engine
from app.models.rbac import User
from app.security.dependencies import get_current_user
from app.services import focus_list as fl


router = APIRouter(prefix="/focus-list", tags=["Focus List"])


# ── Schemas ──────────────────────────────────────────────────────────

class FocusEntry(BaseModel):
    """Single row written via the JSON POST endpoint."""
    werks:           Optional[str] = None
    maj_cat:         str
    gen_art_number:  int
    clr:             Optional[str] = None
    focus_type:      str
    tier:            Optional[str] = None
    is_active:       bool = True
    note:            Optional[str] = None


class BulkUploadResponse(BaseModel):
    success: bool
    summary: dict   # {"input": n, "valid": n, "errors": n, "inserted": n, "updated": n}
    errors:  List[dict] = []   # offending rows + error messages


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
def list_focus_entries(
    werks:      Optional[str]  = None,
    maj_cat:    Optional[str]  = None,
    focus_type: Optional[str]  = Query(None, regex="^(W_CAP|WO_CAP)$"),
    is_active:  Optional[bool] = None,
    limit:      int            = Query(1000, ge=1, le=10000),
    current_user: User = Depends(get_current_user),
):
    """List Master_FOCUS_LIST entries with optional filters."""
    engine = get_data_engine()
    with engine.connect() as conn:
        rows = fl.list_entries(
            conn,
            werks=werks, maj_cat=maj_cat,
            focus_type=focus_type, is_active=is_active,
            limit=limit,
        )
    return {"success": True, "rows": rows, "count": len(rows)}


@router.post("")
def upsert_one_focus_entry(
    entry: FocusEntry,
    current_user: User = Depends(get_current_user),
):
    """Insert or update a single focus-list entry. Idempotent — repeated
    calls with the same scope key (WERKS, MAJ_CAT, GEN_ART, CLR) update
    the existing row instead of duplicating."""
    import pandas as pd
    df = pd.DataFrame([{
        "WERKS": entry.werks,
        "MAJ_CAT": entry.maj_cat,
        "GEN_ART_NUMBER": entry.gen_art_number,
        "CLR": entry.clr,
        "FOCUS_TYPE": entry.focus_type,
        "TIER": entry.tier,
        "IS_ACTIVE": "1" if entry.is_active else "0",
        "NOTE": entry.note,
    }])
    validation = fl.validate_dataframe(df)
    if validation.summary["valid"] == 0:
        err = (validation.errors.iloc[0]["error"]
               if not validation.errors.empty else "validation failed")
        raise HTTPException(400, err)

    user = getattr(current_user, "username", None) or "user"
    engine = get_data_engine()
    with engine.connect() as conn:
        result = fl.bulk_upsert(conn, validation.valid, user=user)
    return {"success": True, **result}


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_focus_list(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Bulk upload a CSV or XLSX. Required columns: MAJ_CAT,
    GEN_ART_NUMBER, FOCUS_TYPE. Optional: WERKS, CLR, TIER, IS_ACTIVE, NOTE.

    Validation is row-by-row — bad rows are reported with reasons but
    do NOT abort the upload. Good rows are MERGE-upserted into
    Master_FOCUS_LIST."""
    import pandas as pd
    name = (file.filename or "").lower()
    raw = await file.read()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        elif name.endswith((".xlsx", ".xls", ".xlsm")):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            raise HTTPException(400, "File must be .csv, .xlsx, .xls, or .xlsm")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    validation = fl.validate_dataframe(df)
    summary = dict(validation.summary)
    summary["inserted"] = 0
    summary["updated"] = 0

    if validation.summary["valid"] > 0:
        user = getattr(current_user, "username", None) or "user"
        engine = get_data_engine()
        with engine.connect() as conn:
            merge_result = fl.bulk_upsert(conn, validation.valid, user=user)
        summary.update(merge_result)

    errors_payload = (
        validation.errors.head(200).to_dict("records")
        if not validation.errors.empty else []
    )
    logger.info(
        f"[focus_list] upload by {getattr(current_user, 'username', '?')}: "
        f"{summary}"
    )
    return {"success": True, "summary": summary, "errors": errors_payload}


@router.delete("/{entry_id}")
def delete_focus_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
):
    """Delete one entry by id."""
    engine = get_data_engine()
    with engine.connect() as conn:
        ok = fl.delete_entry(conn, entry_id)
    if not ok:
        raise HTTPException(404, f"focus-list entry {entry_id} not found")
    return {"success": True, "deleted": entry_id}


@router.post("/apply")
def apply_focus_flags_now(
    working_table: str = Query("ARS_LISTING_WORKING"),
    current_user: User = Depends(get_current_user),
):
    """Manually re-apply focus flags to working_table.

    This usually runs automatically as part of /listing/generate (Part 7
    in listing.py). Exposed as its own endpoint so a planner who edits
    the focus list AFTER a generate can re-stamp the flags without
    re-running the whole pipeline. The allocation step reads the flags
    fresh on each run, so re-stamping then re-running allocation alone
    will pick up the change."""
    engine = get_data_engine()
    with engine.connect() as conn:
        counts = fl.apply_focus_flags(conn, working_table=working_table)
    return {"success": True, **counts}
