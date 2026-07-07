"""
V1_1_SM_package_model.py — package the frozen SM V1.1 champion (modal 4-feature
nested-ridge winner) into a loadable joblib bundle under
STARTER MOTOR/V1.1/models/V1_1_ridge_champion/.

The V1.1 headline (nested AUROC 0.9321) comes from per-fold subsets/thresholds.
A single production model requires one subset + one calibrator, so this packages
the MODAL winner subset with:
  - pipeline fit on all 34 trucks (median impute -> scaler -> ridge alpha=1.0)
  - Platt calibrator fit on the 34 modal-subset LOVO OOF decision values
  - frozen tier bands GREEN<0.35<=AMBER<0.55<=RED on the RECALIBRATED prob
  - auxiliary binary threshold = Youden on the OOF sigmoid probs

Parity gates (script aborts on any failure):
  P1  closed-form numpy ridge vs sklearn LOVO decision values < 1e-8
  P2  modal-subset LOVO AUROC rounds to 0.9357 (spec comparisons value)
  P3  SimpleImputer(median) statistics == np.nanmedian on all-34 fit (1e-12)
  P4  joblib round-trip bit-identical decision values

Outputs -> STARTER MOTOR/V1.1/models/V1_1_ridge_champion/:
  V1_1_SM_champion_bundle.joblib
  V1_1_SM_training_matrix.csv           (provenance copy)
  V1_1_SM_model_spec.json               (provenance copy)
  V1_1_SM_nested_lovo_predictions.csv   (provenance copy)
  V1_1_SM_verification.json
  V1_1_SM_MANIFEST.json

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_package_model.py"
"""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeClassifier
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
RES = ROOT / "STARTER MOTOR" / "V1.1" / "results"
MATRIX_CSV = RES / "V1_1_SM_feature_matrix.csv"
SPEC_JSON = RES / "V1_1_SM_model_spec.json"
NESTED_PREDS = RES / "V1_1_SM_nested_lovo_predictions.csv"
OUT = ROOT / "STARTER MOTOR" / "V1.1" / "models" / "V1_1_ridge_champion"

FEATURES = ["dip_depth_last90_delta", "rest_vsi_p05_delta90",
            "vsi_range_trend", "vsi_withinwk_std_ratio_30d_w"]  # modal winner (spec)
RIDGE_ALPHA = 1.0
RANDOM_SEED = 42
FROZEN_MODAL_LOVO = 0.9357   # spec: comparisons.non_nested_lovo_modal_subset
FROZEN_NESTED = 0.9321
TIER_GREEN, TIER_RED = 0.35, 0.55


def sigmoid(z):
    z = np.asarray(z, dtype=float)
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def ridge_z_numpy(Xtr, ytr, Xte, alpha=RIDGE_ALPHA):
    """Closed-form replica from V1_1_SM_nested_ridge.py (verified <1e-9 vs sklearn)."""
    Xtr = Xtr.copy(); Xte = Xte.copy()
    med = np.nanmedian(Xtr, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    for j in range(Xtr.shape[1]):
        Xtr[np.isnan(Xtr[:, j]), j] = med[j]
        Xte[np.isnan(Xte[:, j]), j] = med[j]
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd = np.where(sd == 0, 1.0, sd)
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
    yp = 2.0 * ytr - 1.0
    yc = yp - yp.mean()
    k = Xtr.shape[1]
    beta = np.linalg.solve(Xtr.T @ Xtr + alpha * np.eye(k), Xtr.T @ yc)
    return Xte @ beta + yp.mean()


def lovo_z_sklearn(X, y):
    """Per-fold impute/scale/RidgeClassifier decision values (sklearn stack)."""
    n = len(y)
    z = np.empty(n)
    for i in range(n):
        tr = np.arange(n) != i
        Xtr, Xte = X[tr].copy(), X[i:i + 1].copy()
        for j in range(Xtr.shape[1]):
            med = np.nanmedian(Xtr[:, j])
            med = 0.0 if np.isnan(med) else med
            Xtr[np.isnan(Xtr[:, j]), j] = med
            Xte[np.isnan(Xte[:, j]), j] = med
        sc = StandardScaler().fit(Xtr)
        m = RidgeClassifier(alpha=RIDGE_ALPHA, random_state=RANDOM_SEED).fit(
            sc.transform(Xtr), y[tr])
        z[i] = m.decision_function(sc.transform(Xte))[0]
    return z


def youden_thr(yy, p):
    """Replica of youden_thr in V1_1_SM_nested_ridge.py."""
    order = np.argsort(-p)
    ps, ys = p[order], yy[order]
    P, N = ys.sum(), len(ys) - ys.sum()
    tps = np.cumsum(ys); fps = np.cumsum(1 - ys)
    jj = tps / P - fps / N
    distinct = np.r_[np.diff(ps) != 0, True]
    best = np.argmax(np.where(distinct, jj, -np.inf))
    return float(ps[best])


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(MATRIX_CSV)
    assert len(df) == 34 and int(df["failed"].sum()) == 14, "frozen matrix changed"
    missing = [f for f in FEATURES if f not in df.columns]
    assert not missing, f"modal features missing from matrix: {missing}"
    X = df[FEATURES].values.astype(float)
    y = df["failed"].values.astype(int)
    assert all(np.isfinite(X[:, j]).any() for j in range(X.shape[1]))

    # ── P1: closed-form vs sklearn parity on LOVO decision values ───────────
    z_sk = lovo_z_sklearn(X, y)
    z_np = np.empty(len(y))
    for i in range(len(y)):
        tr = np.arange(len(y)) != i
        z_np[i] = ridge_z_numpy(X[tr], y[tr], X[i:i + 1])[0]
    diff = float(np.max(np.abs(z_np - z_sk)))
    print(f"[P1] numpy closed-form vs sklearn LOVO: max|dz| = {diff:.2e}")
    assert diff < 1e-8, f"P1 FAIL: {diff:.2e}"

    # ── P2: modal-subset LOVO AUROC vs frozen spec value ────────────────────
    prob_oof = sigmoid(z_sk)
    auroc = float(roc_auc_score(y, prob_oof))
    print(f"[P2] modal-subset LOVO AUROC = {auroc:.6f} (frozen {FROZEN_MODAL_LOVO})")
    assert round(auroc, 4) == FROZEN_MODAL_LOVO, f"P2 FAIL: {auroc:.6f}"

    # ── production calibrator + auxiliary threshold (both from OOF) ─────────
    platt = LogisticRegression(C=1e6, max_iter=10000).fit(z_sk.reshape(-1, 1), y)
    thr_youden_oof = youden_thr(y, prob_oof)
    print(f"     Platt fit on 34 OOF z; auxiliary Youden(OOF prob) = {thr_youden_oof:.4f}")

    # ── production fit on all 34 ────────────────────────────────────────────
    pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("ridge", RidgeClassifier(alpha=RIDGE_ALPHA, random_state=RANDOM_SEED)),
    ])
    pipe.fit(X, y)
    assert np.allclose(pipe.named_steps["impute"].statistics_,
                       np.nanmedian(X, axis=0), atol=1e-12), "P3 FAIL"
    print("[P3] SimpleImputer(median) == np.nanmedian  OK")
    dec_train = pipe.decision_function(X)

    # ── bundle ──────────────────────────────────────────────────────────────
    spec = json.loads(SPEC_JSON.read_text())
    env = {"python": platform.python_version(), "sklearn": sklearn.__version__,
           "numpy": np.__version__, "pandas": pd.__version__,
           "joblib": joblib.__version__, "platform": platform.platform()}
    bundle = {
        "component": "starter_motor",
        "champion_version": "V1_1_SM",
        "validated_by": "ceiling re-confirmed by V2.1, V3, V3.1 (all candidates "
                        "rejected; reconciliation 0.9357 exact each time)",
        "created": date.today().isoformat(),
        "features": FEATURES,
        "pipeline": pipe,
        "platt": platt,
        "score_mapping": ("z = pipeline.decision_function(X[features]); "
                          "prob_raw = sigmoid(z); "
                          "prob_recal = platt.predict_proba(z.reshape(-1,1))[:,1]; "
                          "tier on prob_recal"),
        "threshold": thr_youden_oof,   # auxiliary binary rule, derived from OOF probs
        "tier_bands": {"amber_ge": TIER_GREEN, "red_ge": TIER_RED},
        "tier_score": "prob_recal",
        "frozen_metrics": {
            "nested_auroc": spec["headline"]["nested_auroc"],
            "modal_subset_lovo_auroc": spec["comparisons"]["non_nested_lovo_modal_subset"],
            "recall": spec["headline"]["per_fold_threshold_metrics"]["recall"],
            "specificity": spec["headline"]["per_fold_threshold_metrics"]["specificity"]},
        "training": {"matrix": "STARTER MOTOR/V1.1/results/V1_1_SM_feature_matrix.csv",
                     "matrix_sha256": sha256(MATRIX_CSV),
                     "n_trucks": 34, "n_failed": 14,
                     "fit_scope": ("modal winner subset, fit on all 34 trucks; "
                                   "Platt fit on modal-subset LOVO OOF z (NOT the "
                                   "nested per-fold calibrators)"),
                     "git_head": git_head()},
        "environment": env,
    }
    bundle_path = OUT / "V1_1_SM_champion_bundle.joblib"
    joblib.dump(bundle, bundle_path)

    # ── P4: round trip ──────────────────────────────────────────────────────
    b2 = joblib.load(bundle_path)
    assert np.array_equal(dec_train, b2["pipeline"].decision_function(X)), "P4 FAIL"
    p1 = platt.predict_proba(z_sk.reshape(-1, 1))[:, 1]
    p2 = b2["platt"].predict_proba(z_sk.reshape(-1, 1))[:, 1]
    assert np.array_equal(p1, p2), "P4 FAIL (platt)"
    print("[P4] joblib round-trip bit-identical  OK")

    # ── provenance copies ───────────────────────────────────────────────────
    shutil.copy2(MATRIX_CSV, OUT / "V1_1_SM_training_matrix.csv")
    shutil.copy2(SPEC_JSON, OUT / "V1_1_SM_model_spec.json")
    shutil.copy2(NESTED_PREDS, OUT / "V1_1_SM_nested_lovo_predictions.csv")

    # ── verification + manifest ─────────────────────────────────────────────
    verification = {
        "created": date.today().isoformat(),
        "P1_closedform_vs_sklearn": {"max_abs_dz": diff, "tol": 1e-8, "pass": True},
        "P2_modal_lovo_auroc": {"value": round(auroc, 6),
                                "frozen": FROZEN_MODAL_LOVO, "pass": True},
        "P3_imputer_equivalence": {"atol": 1e-12, "pass": True},
        "P4_roundtrip": {"pass": True},
        "auxiliary_threshold_youden_oof": round(thr_youden_oof, 4),
        "note": ("production model = modal subset + pooled-OOF Platt; nested per-fold "
                 "numbers in the spec are the validation estimate, not this model's "
                 "resubstitution output"),
        "environment": env,
    }
    (OUT / "V1_1_SM_verification.json").write_text(json.dumps(verification, indent=2))

    files = sorted(p for p in OUT.iterdir()
                   if p.is_file() and p.name != "V1_1_SM_MANIFEST.json")
    manifest = {
        "artifact": "V1_1_SM frozen champion (starter motor)",
        "created": date.today().isoformat(),
        "git_head": git_head(),
        "environment": env,
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                  for p in files],
        "inputs": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p)}
                   for p in (MATRIX_CSV, SPEC_JSON, NESTED_PREDS)],
    }
    (OUT / "V1_1_SM_MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    print(f"\nPACKAGED OK -> {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
