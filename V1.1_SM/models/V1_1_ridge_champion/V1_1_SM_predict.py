"""
V1_1_SM_predict.py — self-contained loader for the frozen SM V1.1 champion.

CLI:
    py -3 V1_1_SM_predict.py <features_csv> [--out <predictions_csv>]

Outputs per truck: prob_raw (sigmoid of ridge decision), prob_recal (Platt),
tier (GREEN/AMBER/RED on prob_recal, bands 0.35/0.55), predicted_class
(prob_raw >= auxiliary OOF-Youden threshold).
Requires only: numpy, pandas, scikit-learn, joblib (packaged with sklearn 1.8.0).
NaNs in feature columns are fine — the pipeline imputes with TRAINING medians.
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BUNDLE_PATH = HERE / "V1_1_SM_champion_bundle.joblib"


def sigmoid(z):
    z = np.asarray(z, dtype=float)
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def load_bundle(path=BUNDLE_PATH):
    return joblib.load(path)


def predict(df, bundle=None):
    """Score trucks. df: DataFrame containing the 4 champion feature columns.
    Returns DataFrame with prob_raw, prob_recal, predicted_class, tier."""
    if bundle is None:
        bundle = load_bundle()
    feats = bundle["features"]
    missing = [f for f in feats if f not in df.columns]
    if missing:
        raise ValueError(f"missing feature columns: {missing}")
    X = df[feats].values.astype(float)
    z = bundle["pipeline"].decision_function(X)
    prob_raw = sigmoid(z)
    prob_recal = bundle["platt"].predict_proba(z.reshape(-1, 1))[:, 1]
    bands = bundle["tier_bands"]
    tier = np.where(prob_recal >= bands["red_ge"], "RED",
                    np.where(prob_recal >= bands["amber_ge"], "AMBER", "GREEN"))
    out = pd.DataFrame({
        "VIN": df["vin_label"] if "vin_label" in df.columns else np.arange(len(df)),
        "prob_raw": np.round(prob_raw, 4),
        "prob_recal": np.round(prob_recal, 4),
        "predicted_class": (prob_raw >= bundle["threshold"]).astype(int),
        "tier": tier,
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features_csv")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    df = pd.read_csv(args.features_csv)
    out = predict(df)
    if args.out:
        out.to_csv(args.out, index=False)
        print(f"wrote {args.out} ({len(out)} rows)")
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
