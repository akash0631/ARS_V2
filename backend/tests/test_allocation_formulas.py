"""
Pin the allocation math to the SOP examples.

Source documents:
  - ARS_Process_Workflow.md  (formula reference, §5)
  - ARS_Allocation_Engine_SOP.md (worked examples for HN10/1001/BLK and
    HN10/1003/BLU, used here as ground truth)

These tests run against pure-Python re-implementations in
`app.services.allocation_formulas`. If anyone edits the SQL UPDATE
statements in grid_builder.py / listing.py / rule_engine_pandas.py,
the corresponding formula here MUST be updated and these tests MUST
still pass — that is the regression contract.
"""
import pytest

from app.services.allocation_formulas import (
    mbq,
    opt_cnt,
    classify_opt_type,
    opt_mbq_wh,
    alloc_hold_split,
    str_boost_pct,
    parse_str_tiers,
    check_eligibility,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. MBQ — formula: ((SAL_PD * BGT_GR) * ALC_D + DISP_Q * DISP_GR) * CONT
# ═══════════════════════════════════════════════════════════════════════

class TestMBQ:
    def test_basic(self):
        # SAL_PD=216, ALC_D=9, DISP_Q=20, CONT=1.0, growths=1.0
        # = (216*1)*9 + 20*1 = 1944 + 20 = 1964 → *1.0 = 1964
        assert mbq(sal_pd=216, alc_d=9, disp_q=20, cont=1.0) == 1964.0

    def test_with_cont_50pct(self):
        # MBQ at 50% contribution slot
        assert mbq(sal_pd=216, alc_d=9, disp_q=20, cont=0.5) == round(1964 * 0.5, 0)

    def test_growth_defaults_to_1_when_zero(self):
        # SQL defaults BGT_SL_GR_DGR / DISP_GR_DGR to 1 when 0/NULL
        a = mbq(sal_pd=10, alc_d=5, disp_q=8, cont=1.0, bgt_sl_gr=0, disp_gr=0)
        b = mbq(sal_pd=10, alc_d=5, disp_q=8, cont=1.0, bgt_sl_gr=1, disp_gr=1)
        assert a == b == round(10 * 5 + 8, 0)  # 58

    def test_cont_zero_yields_zero(self):
        assert mbq(sal_pd=100, alc_d=10, disp_q=50, cont=0.0) == 0.0

    def test_growth_above_one_amplifies(self):
        # 30% sales budget growth + 20% display growth
        v = mbq(sal_pd=10, alc_d=5, disp_q=10, cont=1.0, bgt_sl_gr=1.3, disp_gr=1.2)
        # = (10*1.3)*5 + 10*1.2 = 65 + 12 = 77
        assert v == 77.0


# ═══════════════════════════════════════════════════════════════════════
# 2. OPT_CNT — formula: DISP_Q * DISP_GR * CONT / ACS_D
# ═══════════════════════════════════════════════════════════════════════

class TestOptCnt:
    def test_basic(self):
        # DISP_Q=120, CONT=1.0, ACS_D=18, DISP_GR=1 → 120/18 = 6.67 → 7
        assert opt_cnt(disp_q=120, cont=1.0, acs_d=18) == 7.0

    def test_cont_zero_yields_zero(self):
        assert opt_cnt(disp_q=120, cont=0.0, acs_d=18) == 0.0

    def test_acs_zero_yields_zero(self):
        # SQL guards against divide-by-zero
        assert opt_cnt(disp_q=120, cont=1.0, acs_d=0) == 0.0

    def test_disp_growth_applied(self):
        # DISP_Q=100, DISP_GR=1.2, CONT=0.5, ACS_D=20 → 100*1.2*0.5/20 = 3.0
        assert opt_cnt(disp_q=100, cont=0.5, acs_d=20, disp_gr=1.2) == 3.0


# ═══════════════════════════════════════════════════════════════════════
# 3. OPT_TYPE classification (RL / TBC / TBL / MIX)
# ═══════════════════════════════════════════════════════════════════════

class TestOptType:
    def test_rl_when_stock_above_threshold(self):
        # 60% of 18 = 10.8; STK=15 > 10.8 ⇒ RL
        assert classify_opt_type(
            stk_ttl=15, msa_fnl_q=100, rl_hold_qty=0,
            var_count=4, var_fnl_count=4, acs_d=18,
        ) == "RL"

    def test_tbl_when_zero_stock_with_msa(self):
        assert classify_opt_type(
            stk_ttl=0, msa_fnl_q=100, rl_hold_qty=0,
            var_count=5, var_fnl_count=5, acs_d=18,
        ) == "TBL"

    def test_tbc_when_partial_stock_with_msa(self):
        # STK=5, threshold=10.8, MSA available ⇒ TBC
        assert classify_opt_type(
            stk_ttl=5, msa_fnl_q=100, rl_hold_qty=0,
            var_count=4, var_fnl_count=4, acs_d=18,
        ) == "TBC"

    def test_mix_when_low_stock_no_msa_no_hold(self):
        # MIX(a) — nothing to send
        assert classify_opt_type(
            stk_ttl=2, msa_fnl_q=0, rl_hold_qty=0,
            var_count=4, var_fnl_count=4, acs_d=18,
        ) == "MIX"

    def test_mix_b_poor_color_fill(self):
        # 1 of 5 variants has stock = 20% < 60% threshold ⇒ MIX(b)
        # Even with adequate stock and MSA available
        assert classify_opt_type(
            stk_ttl=20, msa_fnl_q=100, rl_hold_qty=0,
            var_count=5, var_fnl_count=1, acs_d=18,
        ) == "MIX"

    def test_mix_b_min_size_count(self):
        # min_size_count=3, but only 2 variants have stock ⇒ MIX(b)
        assert classify_opt_type(
            stk_ttl=20, msa_fnl_q=100, rl_hold_qty=0,
            var_count=5, var_fnl_count=2, acs_d=18,
            min_size_count=3,
        ) == "MIX"

    def test_rl_hold_overrides_low_stock(self):
        # Prior-run NL hold is dispatched stock — even if STK_TTL is low,
        # treat as RL (not MIX)
        assert classify_opt_type(
            stk_ttl=2, msa_fnl_q=0, rl_hold_qty=10,
            var_count=4, var_fnl_count=4, acs_d=18,
        ) == "RL"

    def test_default_acs_used_when_zero(self):
        # ACS_D=0 should fall back to default_acs (18)
        # STK=12 > 0.6*18=10.8 ⇒ RL
        assert classify_opt_type(
            stk_ttl=12, msa_fnl_q=0, rl_hold_qty=0,
            var_count=4, var_fnl_count=4, acs_d=0,
            default_acs=18,
        ) == "RL"


# ═══════════════════════════════════════════════════════════════════════
# 4. OPT_MBQ_WH — hold buffer for new listings (TBL / IS_NEW=1)
# ═══════════════════════════════════════════════════════════════════════

class TestOptMbqWh:
    def test_existing_option_no_buffer(self):
        # IS_NEW=0 → OPT_MBQ_WH = OPT_MBQ
        assert opt_mbq_wh(opt_mbq=33, rate=2.0, hold_days=5, is_new=False) == 33

    def test_new_option_adds_buffer(self):
        # SOP example: HN10/1003/BLU TBL, OPT_MBQ=33, hold→OPT_MBQ_WH=46
        # If hold_days=5 and rate=2.6, 33+13=46
        assert opt_mbq_wh(opt_mbq=33, rate=2.6, hold_days=5, is_new=True) == pytest.approx(46.0)

    def test_zero_hold_days_no_change(self):
        assert opt_mbq_wh(opt_mbq=33, rate=2.6, hold_days=0, is_new=True) == 33


# ═══════════════════════════════════════════════════════════════════════
# 5. ALLOC vs HOLD split — base need first, hold sacrificed first
# ═══════════════════════════════════════════════════════════════════════

class TestAllocHoldSplit:
    def test_rl_with_rounding_overflow(self):
        # SOP example: HN10/1001/BLK RL — dispatched=17, OPT_REQ_ORIG=15
        # → ALLOC=15, HOLD=2 (rounding spillover)
        r = alloc_hold_split(dispatched=17, opt_req_orig=15)
        assert r.alloc_qty == 15
        assert r.hold_qty == 2
        assert r.status == "ALLOCATED"

    def test_tbl_full_pool(self):
        # SOP: HN10/1003/BLU TBL — dispatched=46, OPT_REQ_ORIG=33
        # → ALLOC=33, HOLD=13
        r = alloc_hold_split(dispatched=46, opt_req_orig=33)
        assert r.alloc_qty == 33
        assert r.hold_qty == 13
        assert r.status == "ALLOCATED"

    def test_tbl_partial_pool_alloc_still_filled(self):
        # SOP: dispatched=40, OPT_REQ_ORIG=33 → ALLOC=33 (filled), HOLD=7
        r = alloc_hold_split(dispatched=40, opt_req_orig=33)
        assert r.alloc_qty == 33
        assert r.hold_qty == 7
        assert r.status == "ALLOCATED"

    def test_tbl_short_pool_hold_sacrificed(self):
        # SOP: dispatched=25, OPT_REQ_ORIG=33 → ALLOC=25 (partial), HOLD=0
        r = alloc_hold_split(dispatched=25, opt_req_orig=33)
        assert r.alloc_qty == 25
        assert r.hold_qty == 0
        assert r.status == "PARTIAL"

    def test_zero_dispatched(self):
        r = alloc_hold_split(dispatched=0, opt_req_orig=33)
        assert r.alloc_qty == 0
        assert r.hold_qty == 0
        assert r.status == "NOT_PROCESSED"

    def test_zero_base_need_pure_hold(self):
        # When OPT_REQ_ORIG=0 (store already at MBQ) anything dispatched is
        # pure buffer — store does not strictly need it. Treat as ALLOCATED
        # so it doesn't look like a partial fill.
        r = alloc_hold_split(dispatched=10, opt_req_orig=0)
        assert r.alloc_qty == 0
        assert r.hold_qty == 10
        assert r.status == "ALLOCATED"


# ═══════════════════════════════════════════════════════════════════════
# 6. STR boost tiers
# ═══════════════════════════════════════════════════════════════════════

class TestStrBoost:
    def test_default_tiers(self):
        assert str_boost_pct(10) == 150.0   # < 30 days
        assert str_boost_pct(35) == 130.0   # < 45
        assert str_boost_pct(50) == 120.0   # < 60
        assert str_boost_pct(75) == 110.0   # < 90
        assert str_boost_pct(120) == 100.0  # >= 90

    def test_boundary_values(self):
        # At exactly the threshold, NEXT tier kicks in
        assert str_boost_pct(30) == 130.0
        assert str_boost_pct(45) == 120.0
        assert str_boost_pct(60) == 110.0
        assert str_boost_pct(90) == 100.0

    def test_parse_tiers(self):
        assert parse_str_tiers("30:150,45:130") == [(30.0, 150.0), (45.0, 130.0)]

    def test_unsorted_input_is_sorted(self):
        # Even if tiers are passed unsorted, they are walked in ascending order
        tiers = parse_str_tiers("90:110,30:150,60:120,45:130")
        assert str_boost_pct(35, tiers=tiers) == 130.0


# ═══════════════════════════════════════════════════════════════════════
# 7. Eligibility checks E1–E5
# ═══════════════════════════════════════════════════════════════════════

class TestEligibility:
    def test_pass(self):
        r = check_eligibility(
            listing=1, alloc_flag=1, opt_type="RL",
            msa_fnl_q=100, opt_req_wh=15,
        )
        assert r.eligible is True
        assert r.failed_check is None

    def test_e3_mix_excluded(self):
        r = check_eligibility(
            listing=1, alloc_flag=1, opt_type="MIX",
            msa_fnl_q=100, opt_req_wh=15,
        )
        assert r.failed_check == "E3"

    def test_e1_listing_off(self):
        r = check_eligibility(
            listing=0, alloc_flag=1, opt_type="RL",
            msa_fnl_q=100, opt_req_wh=15,
        )
        assert r.failed_check == "E1"

    def test_e2_alloc_flag_off(self):
        r = check_eligibility(
            listing=1, alloc_flag=0, opt_type="RL",
            msa_fnl_q=100, opt_req_wh=15,
        )
        assert r.failed_check == "E2"

    def test_e4_no_msa(self):
        r = check_eligibility(
            listing=1, alloc_flag=1, opt_type="RL",
            msa_fnl_q=0, opt_req_wh=15,
        )
        assert r.failed_check == "E4"

    def test_e5_no_demand(self):
        r = check_eligibility(
            listing=1, alloc_flag=1, opt_type="RL",
            msa_fnl_q=100, opt_req_wh=0,
        )
        assert r.failed_check == "E5"

    def test_focus_wo_cap_bypasses_e5(self):
        # Forced focus options skip the demand floor
        r = check_eligibility(
            listing=1, alloc_flag=1, opt_type="RL",
            msa_fnl_q=100, opt_req_wh=0, focus_wo_cap=1,
        )
        assert r.eligible is True

    def test_priority_order(self):
        # E3 fires before E1 fires before E2 (priority order in the SQL CASE)
        r = check_eligibility(
            listing=0, alloc_flag=0, opt_type="MIX",
            msa_fnl_q=0, opt_req_wh=0,
        )
        assert r.failed_check == "E3"
