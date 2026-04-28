"""
alloc_cancellation.py
Process-local registry that powers the "Cancel Batch" / "Kill Job" UI.

When a user clicks Cancel:
  1. Set a threading.Event keyed by batch_id (cooperative stop)
  2. Issue `KILL <spid>` on every worker SQL Server session that has
     registered with this batch (forceful stop — ends in-flight queries).

Each parallel worker:
  - calls register_spid(batch_id, spid) on startup
  - calls is_cancelled(batch_id) before each new MAJ_CAT claim
  - calls unregister_spid(batch_id, spid) on exit

If the app login lacks ALTER ANY CONNECTION (= can't KILL), the cooperative
event still stops new MAJ_CAT pulls. The current MAJ_CAT finishes naturally
within seconds-to-minutes; that's the worst-case latency without KILL.
"""
from __future__ import annotations

import threading
from typing import Dict, List, Set

from loguru import logger
from sqlalchemy import text

from app.database.session import get_data_engine


_LOCK = threading.Lock()
_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_BATCH_SPIDS:   Dict[str, Set[int]]        = {}


# ─── cooperative cancel ──────────────────────────────────────────────
def get_event(batch_id: str) -> threading.Event:
    """Return (creating if needed) the cancel-event for this batch."""
    with _LOCK:
        ev = _CANCEL_EVENTS.get(batch_id)
        if ev is None:
            ev = threading.Event()
            _CANCEL_EVENTS[batch_id] = ev
        return ev


def is_cancelled(batch_id: str) -> bool:
    ev = _CANCEL_EVENTS.get(batch_id)
    return bool(ev and ev.is_set())


# ─── SPID registry ───────────────────────────────────────────────────
def register_spid(batch_id: str, spid: int) -> None:
    if not spid:
        return
    with _LOCK:
        _BATCH_SPIDS.setdefault(batch_id, set()).add(int(spid))


def unregister_spid(batch_id: str, spid: int) -> None:
    if not spid:
        return
    with _LOCK:
        s = _BATCH_SPIDS.get(batch_id)
        if s is not None:
            s.discard(int(spid))


def get_spids(batch_id: str) -> List[int]:
    with _LOCK:
        return list(_BATCH_SPIDS.get(batch_id, set()))


# ─── Hard cancel (called by /cancel-batch endpoint) ──────────────────
def hard_cancel(batch_id: str) -> Dict:
    """
    1. Set the cancel event so workers stop claiming new MAJ_CATs.
    2. Issue KILL <spid> on every registered worker session so any
       in-flight UPDATE inside that worker terminates immediately.

    Returns {event_set, kill_attempted, killed, kill_failed} for logging.
    """
    ev = get_event(batch_id)
    ev.set()

    spids = get_spids(batch_id)
    if not spids:
        return {"event_set": True, "kill_attempted": 0, "killed": 0, "kill_failed": []}

    engine = get_data_engine()
    killed: List[int]      = []
    kill_failed: List[Dict] = []
    # KILL is a server-level command and must NOT run inside a transaction.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for spid in spids:
            try:
                conn.exec_driver_sql(f"KILL {int(spid)}")
                killed.append(int(spid))
            except Exception as e:
                # Most likely cause: the login lacks ALTER ANY CONNECTION
                # permission. Log and let cooperative cancel handle it.
                kill_failed.append({"spid": int(spid), "error": str(e)[:300]})

    if killed:
        logger.warning(
            f"[cancel] batch={batch_id} KILL'd {len(killed)} SPID(s): {killed}"
        )
    if kill_failed:
        logger.warning(
            f"[cancel] batch={batch_id} KILL failed for {len(kill_failed)} "
            f"SPID(s) — relying on cooperative event. First error: "
            f"{kill_failed[0]['error']}"
        )

    return {
        "event_set":      True,
        "kill_attempted": len(spids),
        "killed":         killed,
        "kill_failed":    kill_failed,
    }


def cleanup(batch_id: str) -> None:
    """Remove this batch's registry state — call after the run finishes."""
    with _LOCK:
        _CANCEL_EVENTS.pop(batch_id, None)
        _BATCH_SPIDS.pop(batch_id, None)


# ─── Helper: get the current connection's SPID ───────────────────────
def get_current_spid(conn) -> int:
    """Return @@SPID for the given SQLAlchemy connection."""
    try:
        return int(conn.execute(text("SELECT @@SPID")).scalar() or 0)
    except Exception:
        return 0
