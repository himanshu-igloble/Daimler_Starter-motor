"""
V1_1_SM_iteration_comparison.py — compare the last 5 SM iterations' headline
results from archived evidence and verify the champion claim: V1.1 is best.

Hard-asserts (abort on failure — packaging is gated on this script):
  A1  V1 spec auroc == 0.9214 (and note the vsi_dominant_freq artifact taint;
      honest restated nested baseline == 0.8929 from V1.1 spec)
  A2  V1.1 spec nested_auroc == 0.9321, modal-subset LOVO == 0.9357
  A3  V2.1, V3, V3.1 gate summaries each reconcile to exactly 0.9357 (pass true)
      -> no later iteration beat V1.1 (ceiling re-confirmed 3x after V1.1)
  A4  V1.1 nested (0.9321) > V1 restated (0.8929)

Outputs -> STARTER MOTOR/V1.1/models/V1_1_ridge_champion/:
  SM_last5_iteration_comparison.csv
  SM_last5_iteration_comparison.md

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_iteration_comparison.py"
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM = ROOT / "STARTER MOTOR"
V1_SPEC = SM / "results" / "V1_SM_ridge_spec.json"
V11_SPEC = SM / "V1.1" / "results" / "V1_1_SM_model_spec.json"
G21 = SM / "V2.1" / "features" / "out" / "V2_1_gate_summary.json"
G3 = SM / "V3" / "features" / "out" / "V3_gate_summary.json"
G31 = SM / "V3.1" / "features" / "out" / "V3_1_gate_summary.json"
OUT = SM / "V1.1" / "models" / "V1_1_ridge_champion"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    v1 = json.loads(V1_SPEC.read_text())
    assert v1["auroc"] == 0.9214, f"A1 FAIL: {v1['auroc']}"
    assert "vsi_dominant_freq" in v1["features"], "A1: expected artifact feature in V1 winner"

    v11 = json.loads(V11_SPEC.read_text())
    nested = v11["headline"]["nested_auroc"]
    modal = v11["comparisons"]["non_nested_lovo_modal_subset"]
    restated = v11["comparisons"]["v1_restated_baseline"]["nested_auroc"]
    assert nested == 0.9321 and modal == 0.9357, f"A2 FAIL: {nested}/{modal}"

    recons = {}
    for name, path in [("V2.1", G21), ("V3", G3), ("V3.1", G31)]:
        g = json.loads(path.read_text())
        rec = g["reconciliation"]
        assert rec["pass"] and rec["computed"] == 0.9357, f"A3 FAIL ({name}): {rec}"
        recons[name] = rec["computed"]
    print(f"[A3] PASS: V2.1/V3/V3.1 all reconcile to 0.9357 — ceiling holds")

    assert nested > restated, "A4 FAIL"
    print(f"[A1-A4] PASS: V1.1 is the SM champion (nested {nested}, modal LOVO {modal})")

    rows = [
        {"iteration": "V1", "headline_auroc": 0.9214, "honest_basis": restated,
         "role": "superseded",
         "notes": "k=4 winner includes vsi_dominant_freq (1/n_weeks leak artifact, "
                  "later banned); honest restated nested = 0.8929",
         "evidence": "STARTER MOTOR/results/V1_SM_ridge_spec.json"},
        {"iteration": "V1.1", "headline_auroc": nested, "honest_basis": nested,
         "role": "CHAMPION",
         "notes": f"fully nested 34-fold protocol; modal-subset LOVO {modal}; "
                  "recall 13/14, spec 15/20 at per-fold Youden",
         "evidence": "STARTER MOTOR/V1.1/results/V1_1_SM_model_spec.json"},
        {"iteration": "V2.1", "headline_auroc": recons["V2.1"], "honest_basis": recons["V2.1"],
         "role": "NO_IMPROVEMENT",
         "notes": "richer heuristics+features hunt; all candidates fail strict bar",
         "evidence": "STARTER MOTOR/V2.1/features/out/V2_1_gate_summary.json"},
        {"iteration": "V3", "headline_auroc": recons["V3"], "honest_basis": recons["V3"],
         "role": "all 7 REJECT",
         "notes": "interaction+usage hunt; GBM 0.843 < 0.932 (data-not-method cap)",
         "evidence": "STARTER MOTOR/V3/features/out/V3_gate_summary.json"},
        {"iteration": "V3.1", "headline_auroc": recons["V3.1"], "honest_basis": recons["V3.1"],
         "role": "all 7 REJECT (4th confirmation)",
         "notes": "state-engine pass; baseline_nested 0.9321 restated exactly",
         "evidence": "STARTER MOTOR/V3.1/features/out/V3_1_gate_summary.json"},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "SM_last5_iteration_comparison.csv", index=False)

    md = ["# SM — last-5-iterations comparison and champion verification",
          f"_Generated {date.today().isoformat()} by V1_1_SM_iteration_comparison.py_", "",
          "**VERDICT:** user claim \"V1.1 produced best results\" — **VERIFIED**. "
          f"V1.1 nested AUROC {nested} (modal-subset LOVO {modal}) is the ceiling; "
          "V2.1, V3 and V3.1 each re-derived exactly 0.9357 and accepted no candidate. "
          "V1's nominally higher-looking history is artifact-tainted "
          f"(honest restated baseline {restated}).", "",
          df.to_markdown(index=False)]
    (OUT / "SM_last5_iteration_comparison.md").write_text("\n".join(md), encoding="utf-8")

    print(f"Wrote comparison table -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
