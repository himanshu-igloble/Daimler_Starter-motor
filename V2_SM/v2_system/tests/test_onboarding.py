"""
test_onboarding.py  — Unit tests for V2 onboarding / maturity gating (B3)
=========================================================================
Usage:
    py -3 test_onboarding.py

Tests:
  1. Immature truck (8 weeks): assert immature=True, tier capped to AMBER
     when raw tier is RED, H1/H2/H5 suppressed.
  2. Mature truck (14 weeks): assert immature=False, tier unchanged, all
     heuristics pass through.

Design: import maturity functions directly from V2_weekly_job; construct
synthetic walking-score DataFrames from one real VIN's rows truncated to
8 or 14 distinct k_weeks values.

NOTE: weeks_observed is OPERATIONAL METADATA for maturity gating only.
Observation length remains BANNED as a model feature (leak class D5).
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

# Make v2_system importable
HERE = Path(__file__).resolve().parent
V2_SYS = HERE.parent
sys.path.insert(0, str(V2_SYS))

# Import the testable functions from V2_weekly_job
from V2_weekly_job import (
    compute_weeks_observed,
    apply_maturity_gate,
    MIN_WEEKS_MATURE,
    IMMATURE_TIER_CAP,
    IMMATURE_SUPPRESS,
    WALKING_SCORES,
)

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  PASS  {name}")
    else:
        FAIL_COUNT += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def make_synthetic_ws(real_ws: pd.DataFrame, vin: str, n_weeks: int) -> pd.DataFrame:
    """
    Build a synthetic walking_scores DataFrame by taking one real VIN's rows
    and truncating to the first n_weeks distinct k_weeks values (k=0..n_weeks-1).
    The VIN label is renamed to a synthetic label to avoid contaminating real state.
    """
    vin_rows = real_ws[real_ws["vin_label"] == vin].copy()
    keep_k = sorted(vin_rows["k_weeks"].unique())[:n_weeks]
    synthetic = vin_rows[vin_rows["k_weeks"].isin(keep_k)].copy()
    synthetic["vin_label"] = f"SYNTH_{vin}_{n_weeks}wk"
    return synthetic


def run_tests() -> None:
    print("=" * 60)
    print("V2 Onboarding Maturity Gate — Unit Tests")
    print(f"MIN_WEEKS_MATURE={MIN_WEEKS_MATURE}, IMMATURE_TIER_CAP={IMMATURE_TIER_CAP}, "
          f"IMMATURE_SUPPRESS={sorted(IMMATURE_SUPPRESS)}")
    print("=" * 60)

    # Load real walking scores as a source of synthetic data
    real_ws = pd.read_csv(WALKING_SCORES)
    real_ws["cut_date"] = pd.to_datetime(real_ws["cut_date"])

    # Pick a donor VIN that has RED at k=0 (to test capping)
    # VIN10_F_SM is RED at k=0 per verified gate results
    donor_vin = "VIN10_F_SM"

    # ── Test group A: 8-week immature truck ─────────────────────────────────
    print("\n[A] Immature truck (8 weeks, RED donor)")
    synth_8 = make_synthetic_ws(real_ws, donor_vin, 8)
    synth_vin_8 = synth_8["vin_label"].iloc[0]

    # weeks_observed
    wo_8 = compute_weeks_observed(synth_8, synth_vin_8)
    check("A1: weeks_observed == 8", wo_8 == 8, f"got {wo_8}")

    # Raw tier from k=0 row of the synthetic set
    k0_row_8 = synth_8[synth_8["k_weeks"] == 0].iloc[0]
    tier_raw_8 = k0_row_8["tier"]
    check("A2: donor tier is RED at k=0 (prerequisite)", tier_raw_8 == "RED",
          f"got {tier_raw_8}")

    # Mock heuristics that would fire for mature truck
    h1_mock = {"h1_fires": True, "h1_delta": 0.20}
    h2_mock = {"h2_fires": True, "h2_consec_red": 4}
    h5_mock = {"h5_fires": True, "h5_weeks_above": 5}

    mg_8 = apply_maturity_gate(
        vin=synth_vin_8,
        tier_raw=tier_raw_8,
        prob=float(k0_row_8["prob"]),
        weeks_observed=wo_8,
        h1=h1_mock,
        h2=h2_mock,
        h5=h5_mock,
    )

    check("A3: immature=True when weeks_observed=8 < 12", mg_8["immature"] is True,
          f"got {mg_8['immature']}")
    check("A4: tier_display capped to AMBER (not RED)",
          mg_8["tier_display"] == IMMATURE_TIER_CAP,
          f"got {mg_8['tier_display']}")
    check("A5: tier_uncapped preserved as RED",
          mg_8["tier_uncapped"] == "RED",
          f"got {mg_8['tier_uncapped']}")
    check("A6: H1 suppressed (False) for immature truck",
          mg_8["h1_fires"] is False,
          f"got {mg_8['h1_fires']}")
    check("A7: H2 suppressed (False) for immature truck",
          mg_8["h2_fires"] is False,
          f"got {mg_8['h2_fires']}")
    check("A8: H5 suppressed (False) for immature truck",
          mg_8["h5_fires"] is False,
          f"got {mg_8['h5_fires']}")
    check("A9: suppress_reason non-empty for immature truck",
          len(mg_8["suppress_reason"]) > 0,
          f"got '{mg_8['suppress_reason']}'")

    # ── Test group B: 14-week mature truck ──────────────────────────────────
    print("\n[B] Mature truck (14 weeks, RED donor)")
    synth_14 = make_synthetic_ws(real_ws, donor_vin, 14)
    synth_vin_14 = synth_14["vin_label"].iloc[0]

    wo_14 = compute_weeks_observed(synth_14, synth_vin_14)
    check("B1: weeks_observed == 14", wo_14 == 14, f"got {wo_14}")

    k0_row_14 = synth_14[synth_14["k_weeks"] == 0].iloc[0]
    tier_raw_14 = k0_row_14["tier"]

    mg_14 = apply_maturity_gate(
        vin=synth_vin_14,
        tier_raw=tier_raw_14,
        prob=float(k0_row_14["prob"]),
        weeks_observed=wo_14,
        h1=h1_mock,
        h2=h2_mock,
        h5=h5_mock,
    )

    check("B2: immature=False when weeks_observed=14 >= 12", mg_14["immature"] is False,
          f"got {mg_14['immature']}")
    check("B3: tier_display unchanged for mature truck",
          mg_14["tier_display"] == tier_raw_14,
          f"got display={mg_14['tier_display']} raw={tier_raw_14}")
    check("B4: tier_uncapped == tier_raw for mature truck",
          mg_14["tier_uncapped"] == tier_raw_14,
          f"got {mg_14['tier_uncapped']}")
    check("B5: H1 passes through (True) for mature truck",
          mg_14["h1_fires"] is True,
          f"got {mg_14['h1_fires']}")
    check("B6: H2 passes through (True) for mature truck",
          mg_14["h2_fires"] is True,
          f"got {mg_14['h2_fires']}")
    check("B7: H5 passes through (True) for mature truck",
          mg_14["h5_fires"] is True,
          f"got {mg_14['h5_fires']}")
    check("B8: suppress_reason empty for mature truck",
          mg_14["suppress_reason"] == "",
          f"got '{mg_14['suppress_reason']}'")

    # ── Test group C: edge cases ─────────────────────────────────────────────
    print("\n[C] Edge cases")

    # Exactly at boundary: 12 weeks = mature
    synth_12 = make_synthetic_ws(real_ws, donor_vin, 12)
    synth_vin_12 = synth_12["vin_label"].iloc[0]
    wo_12 = compute_weeks_observed(synth_12, synth_vin_12)
    k0_row_12 = synth_12[synth_12["k_weeks"] == 0].iloc[0]
    mg_12 = apply_maturity_gate(
        vin=synth_vin_12,
        tier_raw=k0_row_12["tier"],
        prob=float(k0_row_12["prob"]),
        weeks_observed=wo_12,
        h1={"h1_fires": False, "h1_delta": None},
        h2={"h2_fires": False, "h2_consec_red": 0},
        h5={"h5_fires": False, "h5_weeks_above": 0},
    )
    check("C1: weeks_observed==12 is MATURE (boundary inclusive)",
          mg_12["immature"] is False,
          f"got immature={mg_12['immature']} (wo={wo_12})")

    # 11 weeks = immature
    synth_11 = make_synthetic_ws(real_ws, donor_vin, 11)
    synth_vin_11 = synth_11["vin_label"].iloc[0]
    wo_11 = compute_weeks_observed(synth_11, synth_vin_11)
    k0_row_11 = synth_11[synth_11["k_weeks"] == 0].iloc[0]
    mg_11 = apply_maturity_gate(
        vin=synth_vin_11,
        tier_raw=k0_row_11["tier"],
        prob=float(k0_row_11["prob"]),
        weeks_observed=wo_11,
        h1={"h1_fires": False, "h1_delta": None},
        h2={"h2_fires": False, "h2_consec_red": 0},
        h5={"h5_fires": False, "h5_weeks_above": 0},
    )
    check("C2: weeks_observed==11 is IMMATURE (boundary exclusive)",
          mg_11["immature"] is True,
          f"got immature={mg_11['immature']} (wo={wo_11})")

    # GREEN tier immature truck: cap has no effect (GREEN stays GREEN)
    mg_green_immature = apply_maturity_gate(
        vin="SYNTH_GREEN",
        tier_raw="GREEN",
        prob=0.20,
        weeks_observed=5,
        h1={"h1_fires": True, "h1_delta": 0.18},
        h2={"h2_fires": False, "h2_consec_red": 0},
        h5={"h5_fires": False, "h5_weeks_above": 0},
    )
    check("C3: GREEN tier immature truck stays GREEN (cap only clips RED to AMBER)",
          mg_green_immature["tier_display"] == "GREEN",
          f"got {mg_green_immature['tier_display']}")
    check("C4: GREEN immature truck still immature=True",
          mg_green_immature["immature"] is True,
          f"got {mg_green_immature['immature']}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} PASS, {FAIL_COUNT} FAIL")
    if FAIL_COUNT == 0:
        print("ALL TESTS PASS")
    else:
        print("SOME TESTS FAILED — see above")
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
