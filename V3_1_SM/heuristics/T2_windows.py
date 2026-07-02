# STARTER MOTOR/V3.1/heuristics/T2_windows.py
"""A5 graded windows extended with the attribution dimension (spec §8, table logic only)."""
import json
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parent
import sys; sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

W = L.CP["t2_windows_days"]
bands = pd.read_csv(L.SMROOT / "V2.1" / "heuristics" / "out" / "A5_per_truck_bands.csv")
t1 = pd.read_csv(HERE / "out" / "T1_attribution.csv")[["vin_label", "attribution"]]
t = bands.merge(t1, on="vin_label", how="left")


def window(row):
    if "GREEN" in str(row["band"]) or row["band"] == "AMBER_only":   # robust to exact GREEN band string
        return None
    a = row["attribution"]
    if a == "BATTERY_FIRST":
        return W["battery_first"]
    if a == "STARTER_FIRST":
        return W["starter_first"]
    if a == "MIXED":
        return W["mixed"]
    return W["starter_first"] if row["band"] == "persistence_AND_RED" else W["battery_first"]


t["window_days"] = t.apply(window, axis=1).astype(str)
t["action"] = t["attribution"].map({"BATTERY_FIRST": "battery service first, then re-evaluate",
                                    "STARTER_FIRST": "starter inspection",
                                    "MIXED": "battery-first triage, starter inspection same visit",
                                    "INSUFFICIENT": "monitor / data-quality follow-up"})
t.to_csv(HERE / "out" / "T2_windows.csv", index=False)
print(t[["vin_label", "band", "attribution", "window_days"]].to_string(index=False))
