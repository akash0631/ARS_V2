"""
Store-specific overrides API.

CRUD over Master_ST_SPECIFIC plus a CSV/XLSX bulk-upload endpoint.
The actual stamping of FOCUS_WO_CAP / ST_SPECIFIC_TARGET onto
ARS_LISTING_WORKING happens during /listing/generate via
st_specific.apply_overrides().
"""
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel

from app.database.session import get_data_engine
from app.models.rbac import User
from app.security.dependencies import get_current_user
from app.services import st_specific as sts


router = APIRouter(prefix="/st-specific", tags=["Store Specific Overrides"])


class STSpecificEntry(BaseModel):
    werks:           str
    maj_cat:         str
    gen_art_number:  int
    clr:             Optional[str] = None
    target_qty:      Optional[int] = None
    reason:          Optional[str] = None
    is_active:       bool = True
    effective_from:  Optional[str] = None  # YYYY-MM-DD
    effective_to:    Optional[str] = None


class BulkUploadResponse(BaseModel):
    success: bool
    summary: dict
    errors:  List[dict] = []


@router.get("")
def list_st_specific_entries(
    werks:     Optional[str]  = None,
    maj_cat:   Optional[str]  = None,
    is_active: Optional[bool] = None,
    limit:     int            = Query(1000, ge=1, le=10000),
    current_user: User = Depends(get_current_user),
):
    engine = get_data_engine()
    with engine.connect() as conn:
        rows = sts.list_entries(conn, werks=werks, maj_cat=maj_cat,
                                 is_active=is_active, limit=limit)
    return {"success": True, "rows": rows, "count": len(rows)}


@router.post("")
def upsert_one_entry(
    entry: STSpecificEntry,
    current_user: User = Depends(get_current_user),
):
    import pandas as pd
    df = pd.DataFrame([{
        "WERKS": entry.werks,
        "MAJ_CAT": entry.maj_cat,
        "GEN_ART_NUMBER": entry.gen_art_number,
        "CLR": entry.clr,
        "TARGET_QTY": entry.target_qty,
        "REASON": entry.reason,
        "IS_ACTIVE": "1" if entry.is_active else "0",
        "EFFECTIVE_FROM": entry.effective_from,
        "EFFECTIVE_TO": entry.effective_to,
    }])
    validation = sts.validate_dataframe(df)
    if validation.summary["valid"] == 0:
        err = (validation.errors.iloc[0]["error"]
               if not validation.errors.empty else "validation failed")
        raise HTTPException(400, err)
    user = getattr(current_user, "username", None) or "user"
    engine = get_data_engine()
    with engine.connect() as conn:
        result = sts.bulk_upsert(conn, validation.valid, user=user)
    return {"success": True, **result}


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_st_specific(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Bulk upload CSV or XLSX. Required: WERKS, MAJ_CAT, GEN_ART_NUMBER.
    Optional: CLR, TARGET_QTY, REASON, IS_ACTIVE,
    EFFECTIVE_FROM (YYYY-MM-DD), EFFECTIVE_TO."""
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

    validation = sts.validate_dataframe(df)
    summary = dict(validation.summary)
    summary["inserted"] = 0
    summary["updated"] = 0
    if validation.summary["valid"] > 0:
        user = getattr(current_user, "username", None) or "user"
        engine = get_data_engine()
        with engine.connect() as conn:
            merge_result = sts.bulk_upsert(conn, validation.valid, user=user)
        summary.update(merge_result)
    errors_payload = (
        validation.errors.head(200).to_dict("records")
        if not validation.errors.empty else []
    )
    logger.info(f"[st_specific] upload: {summary}")
    return {"success": True, "summary": summary, "errors": errors_payload}


@router.delete("/{entry_id}")
def delete_st_specific(
    entry_id: int,
    current_user: User = Depends(get_current_user),
):
    engine = get_data_engine()
    with engine.connect() as conn:
        ok = sts.delete_entry(conn, entry_id)
    if not ok:
        raise HTTPException(404, f"st-specific entry {entry_id} not found")
    return {"success": True, "deleted": entry_id}


@router.post("/apply")
def apply_overrides_now(
    working_table: str = Query("ARS_LISTING_WORKING"),
    current_user: User = Depends(get_current_user),
):
    """Manually re-stamp ST_SPECIFIC overrides onto working_table. Usually
    runs as part of /listing/generate Part 7.6."""
    engine = get_data_engine()
    with engine.connect() as conn:
        counts = sts.apply_overrides(conn, working_table=working_table)
    return {"success": True, **counts}
