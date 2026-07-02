import sys, json
from pathlib import Path
import pandas as pd
HERE = Path(__file__).resolve().parents[1]           # .../V3/features
SMROOT = HERE.parents[1]                              # .../STARTER MOTOR
sys.path.insert(0, str(HERE))
import _gate_core as G

def main():
    mat = pd.read_csv(SMROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
    y = mat["failed"].astype(int).values
    assert len(y) == 34 and int(y.sum()) == 14, f"bad matrix {len(y)}/{y.sum()}"
    modal = ["vsi_withinwk_std_ratio_30d_w","rest_vsi_p05_delta90","vsi_range_trend","dip_depth_last90_delta"]
    X = mat[modal].values.astype(float)
    a = G.rank_auroc(G.plain_lovo(X, y), y)
    assert abs(a - 0.9357) <= 0.002, f"RECONCILE FAIL: {a} != 0.9357"
    print(f"PASS reconcile modal-4 non-nested LOVO AUROC = {a:.4f}")

if __name__ == "__main__":
    main()
