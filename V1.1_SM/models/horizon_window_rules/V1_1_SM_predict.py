"""
V1_1_SM_predict.py — self-contained loader for the frozen SM V1.1 horizon +
alert-channel RULES bundle.

IMPORTANT: this is a RULE-BASED artifact, NOT a fitted ML model
(`bundle["is_ml_model"] is False`). It wraps the frozen 10-week detection
horizon and the three alert channels that REPLACE per-truck RUL for the starter
motor (per-truck day-precision RUL is mathematically closed at n=34). There are
no learned coefficients — nothing is "scored". You feed it a classifier TIER
and it returns the recommended maintenance window; you feed it a lead week and
it returns the validated AUROC at that horizon.

Library:
    from V1_1_SM_predict import (load_bundle, maintenance_window,
                                 horizon_auroc, channel_lead_summary)

CLI:
    py -3 V1_1_SM_predict.py [--tier RED|AMBER|GREEN] [--k-weeks N]

Requires only: numpy, pandas, joblib.
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np  # noqa: F401  (kept for parity / downstream numeric use)
import pandas as pd  # noqa: F401  (kept for parity / tabular downstream use)

HERE = Path(__file__).resolve().parent
BUNDLE_PATH = HERE / "V1_1_SM_horizon_window_bundle.joblib"


def load_bundle(path=BUNDLE_PATH):
    """Load the plain-dict horizon/window rules bundle."""
    return joblib.load(path)


def maintenance_window(tier, bundle=None):
    """Map a classifier TIER to a recommended maintenance action + window.

    RED   -> schedule within the k*=10-week (~70-day) detection window
    AMBER -> watch (no scheduled window; re-score)
    GREEN -> routine (no action)
    """
    if bundle is None:
        bundle = load_bundle()
    hz = bundle["horizon"]
    t = str(tier).strip().upper()
    if t == "RED":
        return {"tier": "RED", "action": "schedule within",
                "window_days": int(hz["detection_window_days"]),
                "window_weeks": int(hz["k_star_weeks"]),
                "basis": "validated 10-week (~70-day) detection horizon"}
    if t == "AMBER":
        return {"tier": "AMBER", "action": "watch",
                "window_days": None, "window_weeks": None,
                "basis": "sub-threshold risk; re-score on next cycle"}
    if t == "GREEN":
        return {"tier": "GREEN", "action": "routine",
                "window_days": None, "window_weeks": None,
                "basis": "no elevated risk"}
    raise ValueError(f"unknown tier {tier!r}; expected RED / AMBER / GREEN")


def horizon_auroc(k_weeks, bundle=None):
    """Return the validated AUROC at detection lead of k_weeks (0..26).

    Raises KeyError if the requested week is not in the frozen curve.
    """
    if bundle is None:
        bundle = load_bundle()
    for row in bundle["horizon"]["auroc_by_week"]:
        if int(row["k_weeks"]) == int(k_weeks):
            return float(row["auroc"])
    raise KeyError(f"k_weeks={k_weeks} not in frozen horizon curve "
                   f"(0..{bundle['horizon']['auroc_by_week'][-1]['k_weeks']})")


def channel_lead_summary(bundle=None):
    """Validated first-fire lead stats (days) for the failed trucks."""
    if bundle is None:
        bundle = load_bundle()
    return dict(bundle["validated_leads"])


def _fmt_days(v):
    return "n/a" if v is None else f"{int(v)}d ({int(v) / 7:.1f}w)"


def main():
    ap = argparse.ArgumentParser(description="SM V1.1 horizon + window rules (rule-based)")
    ap.add_argument("--tier", default="RED", help="classifier tier: RED/AMBER/GREEN")
    ap.add_argument("--k-weeks", type=int, default=None,
                    help="lead week to look up the validated AUROC for")
    args = ap.parse_args()

    b = load_bundle()
    hz = b["horizon"]
    print("SM V1.1 HORIZON + WINDOW RULES  (rule-based, is_ml_model="
          f"{b['is_ml_model']})")
    print(f"  component            : {b['component']}")
    print(f"  detection horizon k* : {hz['k_star_weeks']} weeks "
          f"(~{hz['detection_window_days']} days)")
    print(f"  AUROC at k=0         : {hz['auroc_at_k0']:.4f}")
    print(f"  in-spec through week : {hz['in_spec_max_week']}")
    print(f"  alert channels       : "
          f"{', '.join(k for k in b['alert_channels'] if k != 'per_vin_alert_policy')}")

    win = maintenance_window(args.tier, b)
    print(f"\n  tier {win['tier']} -> {win['action']} "
          f"window={_fmt_days(win['window_days'])}  [{win['basis']}]")

    if args.k_weeks is not None:
        print(f"  AUROC at k={args.k_weeks}w  : {horizon_auroc(args.k_weeks, b):.4f}")

    ls = channel_lead_summary(b)
    print("\n  validated first-fire leads (failed trucks, historical - not guarantees):")
    print(f"    fired {ls['n_failed_fired']}/{ls['n_failed_total']} failed  "
          f"(silent {ls['n_failed_silent']})")
    print(f"    lead days  median={ls['median_days']:.0f}  "
          f"min={ls['min_days']:.0f}  max={ls['max_days']:.0f}  "
          f"mean={ls['mean_days']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
