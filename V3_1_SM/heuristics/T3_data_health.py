# STARTER MOTOR/V3.1/heuristics/T3_data_health.py
"""Per-VIN weekly dropout tracker + escalation flag (would have flagged the 5 silent-gap VINs)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
HERE = Path(__file__).resolve().parent
import sys; sys.path.insert(0, str(HERE.parent / "features"))
import _v31_lib as L

E = L.CP["t3_escalation"]
roll = L.load_state_weekly()
rows = []
for v, g in roll.groupby("vin_label"):
    g = g.sort_values("week").copy()
    g["dropout_share"] = g["dropout_hours"] / (g["dropout_hours"] + g["observed_hours"]).clip(lower=1e-9)
    g["trail4_h"] = g["dropout_hours"].rolling(E["trailing_weeks"], min_periods=1).mean()
    own_med = float(g["dropout_hours"].median())
    g["escalation"] = (g["trail4_h"] > E["ratio_vs_own_median"] * max(own_med, 1e-9)) & (g["trail4_h"] > E["min_hours"])
    rows.append(g[["vin_label", "week", "dropout_hours", "dropout_share", "trail4_h", "escalation"]])
out = pd.concat(rows, ignore_index=True)
out.to_csv(HERE / "out" / "T3_data_health.csv", index=False)
sil = ["VIN1_F_SM", "VIN4_F_SM", "VIN5_F_SM", "VIN8_F_SM", "VIN9_F_SM"]
summ = {v: bool(out[(out["vin_label"] == v)]["escalation"].any()) for v in sil}
print(json.dumps({"silent_gap_vins_ever_escalated": summ}, indent=2))
