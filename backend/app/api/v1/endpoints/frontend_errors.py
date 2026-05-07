"""
Frontend error log sink.

The React ErrorBoundary in frontend/src/App.jsx POSTs render errors
here so we have a server-side trail. Body is small + truncated by the
client. No DB writes — the events go to the loguru log so they appear
in Azure Log Analytics / log files alongside backend errors with the
same error_id the user sees in the UI.

If you later want a queryable history, add a table and an INSERT here.
"""
from typing import Optional

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel


router = APIRouter(prefix="/frontend-errors", tags=["Frontend Errors"])


class FrontendError(BaseModel):
    error_id:        str
    message:         str
    stack:           Optional[str] = None
    component_stack: Optional[str] = None
    path:            Optional[str] = None
    user_agent:      Optional[str] = None


@router.post("")
async def log_frontend_error(payload: FrontendError):
    """No auth — render-error reports may fire BEFORE the user logs in
    (LoginPage itself can crash). Treat this as best-effort telemetry."""
    logger.error(
        f"[frontend-error] id={payload.error_id} path={payload.path} "
        f"msg={payload.message[:200]} ua={(payload.user_agent or '')[:80]}"
    )
    if payload.stack:
        logger.debug(f"[frontend-error stack] {payload.error_id}\n{payload.stack}")
    if payload.component_stack:
        logger.debug(
            f"[frontend-error component_stack] {payload.error_id}\n"
            f"{payload.component_stack}"
        )
    return {"success": True, "error_id": payload.error_id}
