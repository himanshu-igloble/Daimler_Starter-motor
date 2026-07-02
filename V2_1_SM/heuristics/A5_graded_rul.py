"""A5_graded_rul.py — graded inspection-window policy from V2 D6 evidence matrix.
Maps the strongest currently-active signal -> a recommended inspection window.
No new modeling; windows are fixed constants from the V2 D6 finding.

Run: py -3 "STARTER MOTOR/V2.1/heuristics/A5_graded_rul.py"
"""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1")
sys.path.insert(0, str(HERE / "heuristics"))
import _heuristic_lib as L  # noqa: E402

OUT = HERE / "heuristics" / "out"

# D6 evidence-window matrix (fixed constants from V2 program)
POLICY = [
    {"signal": "A2_battery_cascade", "window_days_lo": 28, "window_days_hi": 91,
     "action": "Inspect within 4-13 weeks; battery-first triage", "n_support": 4},
    {"signal": "persistence_AND_RED", "window_days_lo": 126, "window_days_hi": 284,
     "action": "Schedule inspection ~6 months (median 206 d)", "n_support": 10},
    {"signal": "AMBER_only", "window_days_lo": None, "window_days_hi": None,
     "action": "Monitor; no failed truck observed in AMBER-only (empirically empty)", "n_support": 0},
]


def main():
    pd.DataFrame(POLICY).to_csv(OUT / "A5_graded_rul_policy.csv", index=False)

    ws = L.load_walking()
    val = L.load_alert_validation()
    latest = ws[ws["k_weeks"] == 0].set_index("vin_label")
    rows = []
    for vin in ws["vin_label"].unique():
        tier = latest.loc[vin, "tier"] if vin in latest.index else "NA"
        a2_on = vin in val.index and pd.notna(val.loc[vin, "a2_fire_week"])
        if a2_on:
            band = "A2_battery_cascade"
        elif tier == "RED":
            band = "persistence_AND_RED"
        elif tier == "AMBER":
            band = "AMBER_only"
        else:
            band = "GREEN_no_action"
        rows.append({"vin_label": vin, "tier_k0": tier, "a2_active": a2_on, "band": band})
    pd.DataFrame(rows).to_csv(OUT / "A5_per_truck_bands.csv", index=False)
    print("Saved A5 policy + per-truck bands. Band counts:")
    print(pd.DataFrame(rows)["band"].value_counts().to_string())


if __name__ == "__main__":
    main()
