"""
Rate limiter + idempotency guard for long-running endpoints.

Wraps slowapi for per-user rate limits and exposes a small helper that
checks the existing ARS_ALLOC_MAJCAT_QUEUE for an in-flight session
before allowing /listing/generate to start a second one.

Why both?
  - Rate limiting prevents accidental DoS (a frontend with a misbehaving
    retry loop can fire 50 generates in a minute).
  - Idempotency is a stronger guarantee: even if the rate limit allows
    a second call (separate burst windows), we refuse to start when a
    previous run for the same user is still IN_PROGRESS.

Configurable via env:
  ARS_GENERATE_RATE_PER_HOUR (default: 5)   — slowapi limit string
  ARS_GENERATE_INFLIGHT_LOOKBACK_MIN (default: 30)  — for idempotency check
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _user_key(request: Request) -> str:
    """Limit per JWT subject when one is present; fall back to IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 32:
        # Use the last 16 chars of the token as a stable user-bucket
        # without verifying signatures (slowapi just needs a stable key).
        return f"user:{auth[-16:]}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_user_key)


# ─────────────────────────────────────────────────────────────────────
# Idempotency check — used in concert with rate limiting.
# ─────────────────────────────────────────────────────────────────────

def has_inflight_generate(conn, user_key: Optional[str] = None,
                          lookback_min: Optional[int] = None) -> Optional[str]:
    """Return the batch_id of an in-flight generate run for `user_key`,
    or None if none is currently running.

    Uses ARS_ALLOC_MAJCAT_QUEUE (the queue table the parallel allocation
    engine already populates). If the table doesn't exist the function
    returns None — caller treats that as 'no idempotency available, allow'."""
    from sqlalchemy import text  # lazy

    lookback = int(lookback_min or os.environ.get(
        "ARS_GENERATE_INFLIGHT_LOOKBACK_MIN", "30",
    ))

    try:
        sql = text("""
            SELECT TOP 1 BATCH_ID
            FROM ARS_ALLOC_MAJCAT_QUEUE WITH (NOLOCK)
            WHERE STATUS IN ('PENDING', 'IN_PROGRESS')
              AND CREATED_AT >= DATEADD(MINUTE, -:lookback, SYSUTCDATETIME())
              AND (:uk IS NULL OR ISNULL(WORKER_USER, '') = :uk)
            ORDER BY CREATED_AT DESC
        """)
        row = conn.execute(sql, {
            "lookback": lookback,
            "uk": user_key,
        }).fetchone()
        return row[0] if row else None
    except Exception:
        return None
