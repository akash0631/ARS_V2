"""
Pure-Python implementations of the allocation formulas.

These mirror the inline SQL in `grid_builder.py`, `listing.py`, and
`listing_allocator.py` so that the math can be unit-tested without a
database. They are NOT used at runtime — the live engines compute these
formulas in SQL — but if the SQL ever drifts from this module, the unit
tests will surface the drift.

Source of truth for each formula is `ARS_Process_Workflow.md` in the
repo root (the SOP) and the worked examples in
`ARS_Allocation_Engine_SOP.md`.
"""
from __future__ import annotations

from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────
# 1. GRID-LEVEL: MBQ and OPT_CNT
#    SQL site: backend/app/api/v1/endpoints/grid_builder.py:_calculate_grid_columns
# ─────────────────────────────────────────────────────────────────────

def mbq(
    sal_pd: float,
    alc_d: float,
    disp_q: float,
    cont: float,
    bgt_sl_gr: float = 1.0,
    disp_gr: float = 1.0,
) -> float:
    """
    MBQ = ((SAL_PD * BGT_GR) * ALC_D + DISP_Q * DISP_GR) * CONT, rounded to 0dp.

    BGT_GR and DISP_GR default to 1 when blank/zero (matches SQL CASE).
    CONT=0 ⇒ MBQ=0.
    """
    bgt = bgt_sl_gr if (bgt_sl_gr and bgt_sl_gr != 0) else 1.0
    dgr = disp_gr if (disp_gr and disp_gr != 0) else 1.0
    raw = round((sal_pd * bgt) * alc_d + disp_q * dgr, 0)
    if not cont:
        return 0.0
    return round(raw * cont, 0)


def opt_cnt(disp_q: float, cont: float, acs_d: float, disp_gr: float = 1.0) -> float:
    """
    OPT_CNT = DISP_Q * DISP_GR * CONT / ACS_D, rounded to 0dp.

    CONT=0 or ACS_D=0 ⇒ 0.
    """
    if not cont or not acs_d:
        return 0.0
    dgr = disp_gr if (disp_gr and disp_gr != 0) else 1.0
    return round(disp_q * dgr * cont / acs_d, 0)


# ─────────────────────────────────────────────────────────────────────
# 2. LISTING: OPT_TYPE classification
#    SQL site: listing.py:_classify_opt_type
# ─────────────────────────────────────────────────────────────────────

def classify_opt_type(
    stk_ttl: float,
    msa_fnl_q: float,
    rl_hold_qty: float,
    var_count: float,
    var_fnl_count: float,
    acs_d: float,
    threshold_pct: float = 0.6,
    default_acs: float = 18.0,
    min_size_count: int = 0,
) -> str:
    """
    Returns one of {'RL', 'TBC', 'TBL', 'MIX'}.

    Rules (top-to-bottom, first match wins — exact mirror of the SQL CASE):
      MIX(a): low stock AND no MSA AND no RL_HOLD          (nothing to send)
      MIX(b): poor color fill (var ratio < thr OR var_fnl < min_size_count)
      RL    : adequate stock OR RL_HOLD > 0
      TBC   : 0 < stk < thr*ACS, MSA or RL_HOLD available
      TBL   : stk <= 0, MSA or RL_HOLD available
      else  : MIX
    """
    eff_acs = acs_d if acs_d else default_acs
    threshold_qty = threshold_pct * eff_acs

    # MIX(a)
    if stk_ttl < threshold_qty and msa_fnl_q == 0 and rl_hold_qty == 0:
        return "MIX"

    # MIX(b) — poor color fill
    if var_count > 0:
        ratio_under = (var_fnl_count / var_count) < threshold_pct
        count_under = (min_size_count > 0) and (var_fnl_count < min_size_count)
        if ratio_under or count_under:
            return "MIX"

    # RL
    if stk_ttl >= threshold_qty or rl_hold_qty > 0:
        return "RL"

    # TBC
    if 0 < stk_ttl < threshold_qty and (msa_fnl_q > 0 or rl_hold_qty > 0):
        return "TBC"

    # TBL
    if stk_ttl <= 0 and (msa_fnl_q > 0 or rl_hold_qty > 0):
        return "TBL"

    return "MIX"


# ─────────────────────────────────────────────────────────────────────
# 3. ALLOCATION: OPT_MBQ_WH (hold buffer for new listings)
#    Source: ARS_Allocation_Engine_SOP.md §1, table column definitions
# ─────────────────────────────────────────────────────────────────────

def opt_mbq_wh(
    opt_mbq: float,
    rate: float,
    hold_days: int,
    is_new: bool,
) -> float:
    """
    For IS_NEW=1 (TBL):  OPT_MBQ_WH = OPT_MBQ + rate * hold_days
    For IS_NEW=0 (RL/TBC): OPT_MBQ_WH = OPT_MBQ (no hold buffer).

    `rate` is the daily sale rate used by OPT_MBQ (typically max of L-7,
    AUTO_GEN_ART_SALE, and PER_OPT_SALE for new articles).
    """
    if is_new and hold_days > 0:
        return opt_mbq + rate * hold_days
    return opt_mbq


# ─────────────────────────────────────────────────────────────────────
# 4. ALLOCATION: ALLOC vs HOLD split
#    SQL site: listing_allocator._reflect_to_working (now in _legacy/)
#    Live site: rule_engine_pandas / rule_engine_new — same logic
#    Source: ARS_Allocation_Engine_SOP.md §11
# ─────────────────────────────────────────────────────────────────────

@dataclass
class AllocHoldSplit:
    alloc_qty: float
    hold_qty: float
    status: str  # ALLOCATED / PARTIAL / NOT_PROCESSED


def alloc_hold_split(
    dispatched: float,
    opt_req_orig: float,
) -> AllocHoldSplit:
    """
    Rule: ALLOC always gets priority. HOLD is sacrificed first when the
    pool is short.

      ALLOC_QTY = MIN(dispatched, OPT_REQ_ORIG)
      HOLD_QTY  = dispatched - ALLOC_QTY

    Status:
      ALLOCATED      if ALLOC_QTY >= OPT_REQ_ORIG
      PARTIAL        if 0 < ALLOC_QTY < OPT_REQ_ORIG
      NOT_PROCESSED  if dispatched == 0
    """
    if dispatched <= 0:
        return AllocHoldSplit(0.0, 0.0, "NOT_PROCESSED")

    alloc = min(dispatched, opt_req_orig)
    hold = max(dispatched - alloc, 0.0)
    if opt_req_orig <= 0:
        # Pure hold — base need was zero, anything dispatched is buffer.
        # Treat as ALLOCATED so it does not look like a partial fill.
        return AllocHoldSplit(0.0, dispatched, "ALLOCATED")
    status = "ALLOCATED" if alloc >= opt_req_orig else "PARTIAL"
    return AllocHoldSplit(alloc, hold, status)


# ─────────────────────────────────────────────────────────────────────
# 5. FALLBACK: STR-tier boost
#    SQL site: listing_allocator (str_tiers parameter)
#    Default tiers: "30:150,45:130,60:120,90:110"
# ─────────────────────────────────────────────────────────────────────

def parse_str_tiers(tiers_str: str) -> list[tuple[float, float]]:
    """
    Parse 'D1:P1,D2:P2,...' into [(D1, P1), (D2, P2), ...] sorted by D ascending.
    """
    out: list[tuple[float, float]] = []
    for part in tiers_str.split(","):
        part = part.strip()
        if not part:
            continue
        d_str, p_str = part.split(":")
        out.append((float(d_str.strip()), float(p_str.strip())))
    out.sort(key=lambda x: x[0])
    return out


def str_boost_pct(
    days_of_cover: float,
    tiers: list[tuple[float, float]] | str = "30:150,45:130,60:120,90:110",
) -> float:
    """
    Returns the boost % for an article given its days-of-cover (STK_TTL / daily_sale).

    Walks the tiers in ascending day order, returning the first tier whose
    threshold is greater than days_of_cover. Days >= last tier ⇒ 100% (no boost).
    """
    if isinstance(tiers, str):
        tiers = parse_str_tiers(tiers)
    for d_thr, pct in tiers:
        if days_of_cover < d_thr:
            return pct
    return 100.0


# ─────────────────────────────────────────────────────────────────────
# 6. ELIGIBILITY: E1–E5 (initial gate, before allocation)
#    SQL site: listing_allocator._mark_initial_eligibility
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EligibilityResult:
    eligible: bool
    failed_check: str | None  # 'E1'..'E5' or None
    reason: str | None


def check_eligibility(
    *,
    listing: int,
    alloc_flag: int,
    opt_type: str,
    msa_fnl_q: float,
    opt_req_wh: float,
    focus_wo_cap: int = 0,
) -> EligibilityResult:
    """
    Mirrors the SQL CASE in _mark_initial_eligibility (priority order:
    E3 → E1 → E2 → E4 → E5).
    """
    if opt_type == "MIX":
        return EligibilityResult(False, "E3", "OPT_TYPE=MIX")
    if listing != 1:
        return EligibilityResult(False, "E1", "LISTING!=1")
    if alloc_flag != 1:
        return EligibilityResult(False, "E2", "ALLOC_FLAG=0")
    if msa_fnl_q <= 0:
        return EligibilityResult(False, "E4", "MSA_FNL_Q=0")
    if opt_req_wh < 1 and focus_wo_cap != 1:
        return EligibilityResult(False, "E5", f"OPT_REQ_WH={opt_req_wh}<1")
    return EligibilityResult(True, None, None)
