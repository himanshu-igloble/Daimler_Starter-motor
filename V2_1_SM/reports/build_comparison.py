"""build_comparison.py — assemble the V2.1 recall/FP/lead comparison vs H2 baseline.
Reads all A-rule summaries + the B gate summary, writes reports/V2_1_comparison.csv.

Run: py -3 "STARTER MOTOR/V2.1/reports/build_comparison.py"
"""
import json
from pathlib import Path
import pandas as pd

HO = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\heuristics\out")
RO = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2.1\reports")

baseline = {"heuristic": "H2_baseline", "recall_n_of_14": 10, "med_lead_d": 116,
            "nf_ever_fire_n": 5, "nf_eps_per_truck_year": 0.19}
frames = [pd.DataFrame([baseline])]
for f in ["A1_cusum_summary.csv", "A2_conjunction_summary.csv", "A3_h4_summary.csv"]:
    p = HO / f
    if p.exists():
        frames.append(pd.read_csv(p))
cmp = pd.concat(frames, ignore_index=True)
cols = ["heuristic", "recall_n_of_14", "med_lead_d", "nf_ever_fire_n", "nf_eps_per_truck_year"]
keep = [c for c in cols if c in cmp.columns] + [c for c in cmp.columns if c not in cols]
cmp = cmp[keep]
cmp.to_csv(RO / "V2_1_comparison.csv", index=False)
print(cmp[[c for c in cols if c in cmp.columns]].to_string(index=False))

gate = json.loads((RO.parent / "features" / "out" / "V2_1_gate_summary.json").read_text())
print("\nFeature verdicts:")
for k, v in gate["verdicts"].items():
    print(f"  {k}: {v['verdict']} — {v['reason']}")
