"""
V1_1_SM_bundle_smoketest.py — load-and-predict smoke test for the packaged SM
champion bundle. Exits non-zero on any failure.

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_bundle_smoketest.py"
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
DEP = ROOT / "STARTER MOTOR" / "V1.1" / "models" / "V1_1_ridge_champion"
BUNDLE = DEP / "V1_1_SM_champion_bundle.joblib"
MATRIX = DEP / "V1_1_SM_training_matrix.csv"
PREDICT = DEP / "V1_1_SM_predict.py"

EXPECT_FEATURES = ["dip_depth_last90_delta", "rest_vsi_p05_delta90",
                   "vsi_range_trend", "vsi_withinwk_std_ratio_30d_w"]
EXPECT_KEYS = {"component", "champion_version", "validated_by", "created", "features",
               "pipeline", "platt", "score_mapping", "threshold", "tier_bands",
               "tier_score", "frozen_metrics", "training", "environment"}


def sigmoid(z):
    z = np.asarray(z, dtype=float)
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def main():
    if not BUNDLE.exists():
        print(f"BUNDLE MISSING: {BUNDLE}")
        return 1

    b = joblib.load(BUNDLE)
    missing = EXPECT_KEYS - set(b)
    assert not missing, f"bundle missing keys: {missing}"
    assert b["champion_version"] == "V1_1_SM"
    assert sorted(b["features"]) == sorted(EXPECT_FEATURES)
    assert b["tier_bands"] == {"amber_ge": 0.35, "red_ge": 0.55}
    assert b["tier_score"] == "prob_recal"
    assert b["frozen_metrics"]["nested_auroc"] == 0.9321
    assert b["frozen_metrics"]["modal_subset_lovo_auroc"] == 0.9357

    df = pd.read_csv(MATRIX)
    X = df[b["features"]].values.astype(float)
    y = df["failed"].values.astype(int)

    # In-process ORACLE — computed directly from the bundle, independent of the
    # shipped loader. This is the reference the loader must reproduce.
    z = b["pipeline"].decision_function(X)
    prob_raw = sigmoid(z)
    prob_recal = b["platt"].predict_proba(z.reshape(-1, 1))[:, 1]
    assert prob_raw.shape == (34,) and np.all(np.isfinite(prob_recal))
    oracle_tiers = np.where(prob_recal >= 0.55, "RED",
                            np.where(prob_recal >= 0.35, "AMBER", "GREEN"))
    pred_class = (prob_raw >= b["threshold"]).astype(int)
    resub_auroc = roc_auc_score(y, prob_raw)
    assert resub_auroc > 0.90, f"resubstitution AUROC suspiciously low: {resub_auroc:.4f}"

    # Exercise the SHIPPED loader in-process (imported by file path — the folder
    # has a space and a dot, so a normal import will not resolve it). Its outputs
    # must match the oracle exactly for all 34 rows (loader rounds to 4 dp).
    _spec = importlib.util.spec_from_file_location("v1_1_sm_predict", str(PREDICT))
    predmod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(predmod)
    out = predmod.predict(df, b)
    assert len(out) == 34, f"shipped predict() returned {len(out)} rows, expected 34"
    assert np.allclose(out["prob_recal"].values, np.round(prob_recal, 4), atol=1e-9), \
        "shipped predict() prob_recal does not match oracle"
    assert np.allclose(out["prob_raw"].values, np.round(prob_raw, 4), atol=1e-9), \
        "shipped predict() prob_raw does not match oracle"
    assert np.array_equal(out["tier"].values, oracle_tiers), \
        "shipped predict() tier does not match oracle"
    assert np.array_equal(out["predicted_class"].values, pred_class), \
        "shipped predict() predicted_class does not match oracle"

    # CLI loader round-trip — run predict.py with --out and prove its numeric
    # output equals the oracle (loader rounds prob_recal to 4 dp; row order
    # matches MATRIX order since both consume the same matrix).
    fd, cli_out = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    try:
        r = subprocess.run([sys.executable, str(PREDICT), str(MATRIX), "--out", cli_out],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"predict.py CLI failed:\n{r.stderr}"
        assert "tier" in r.stdout
        cli = pd.read_csv(cli_out)
        assert len(cli) == 34, f"CLI produced {len(cli)} rows, expected 34"
        assert np.allclose(cli["prob_recal"].values, np.round(prob_recal, 4), atol=1e-9), \
            "CLI prob_recal does not match oracle"
    finally:
        os.remove(cli_out)

    print(f"SMOKE PASS  resub_auroc={resub_auroc:.4f}  n=34")
    return 0


if __name__ == "__main__":
    sys.exit(main())
