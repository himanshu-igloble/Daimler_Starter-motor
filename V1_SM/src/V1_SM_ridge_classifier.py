"""
V1_SM_ridge_classifier.py  —  Phase 4: Ridge Classifier + Exhaustive Subset Search
BharatBenz Starter Motor predictive maintenance pipeline.

Exactly the V10.5.3 alternator recipe at n=34:
  - 34-fold LOVO; inside each fold: median imputation (train medians)
    -> StandardScaler -> RidgeClassifier(alpha=1.0, random_state=42);
    sigmoid of decision_function as probability.
  - Exhaustive subsets: all combinations of k=SUBSET_MIN..SUBSET_MAX from the
    candidate pool (k capped at pool size when the pool is smaller).
  - Per subset: AUROC, recall, specificity, F1, MCC at the Youden threshold
    computed from the pooled out-of-fold LOVO predictions.
  - Winner = highest AUROC; ties -> smaller k; further ties -> higher MCC.
  - Winner extras: bootstrap 95% CI (N=200, resample fixed LOVO preds),
    label-permutation test (N=1000), permutation feature importance
    (in-sample, diagnostic only), per-VIN prediction table with alert tiers
    (GREEN < 0.35 <= AMBER < 0.55 <= RED).

Produces:
  STARTER MOTOR/results/V1_SM_elimination_results.csv   — one row per subset
  STARTER MOTOR/results/V1_SM_lovo_predictions.csv      — 34 rows, winner preds
  STARTER MOTOR/results/V1_SM_ridge_spec.json           — winner spec + config

Leakage guards: vin_label never used as a feature; imputation medians and
scaler statistics are fit on the 33 training VINs of each fold only.
All randomness derives from cfg.RANDOM_STATE — reruns are deterministic.
"""

import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import warnings
warnings.filterwarnings("ignore")

# ── Config import (directory has a space) ────────────────────────────────────
_spec = spec_from_file_location(
    "v1_sm_config",
    Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score, roc_curve, f1_score, recall_score,
    matthews_corrcoef, confusion_matrix,
)

# Alert tiers (winner LOVO probabilities)
TIER_AMBER, TIER_RED = 0.35, 0.55
N_IMPORTANCE_REPEATS = 50


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-np.abs(x))),
        np.exp(-np.abs(x)) / (1.0 + np.exp(-np.abs(x))),
    )


def _impute_train_medians(X_train: np.ndarray, X_test: np.ndarray):
    """Impute NaN with column medians computed from TRAINING rows only."""
    X_tr, X_te = X_train.copy(), X_test.copy()
    for j in range(X_tr.shape[1]):
        med = np.nanmedian(X_tr[:, j])
        if np.isnan(med):
            med = 0.0
        X_tr[np.isnan(X_tr[:, j]), j] = med
        X_te[np.isnan(X_te[:, j]), j] = med
    return X_tr, X_te


def lovo_ridge(X_raw: np.ndarray, y: np.ndarray) -> np.ndarray:
    """34-fold leave-one-VIN-out; per fold impute+scale+Ridge on train only."""
    n = len(y)
    probs = np.full(n, np.nan)
    for i in range(n):
        train_idx = np.concatenate([np.arange(0, i), np.arange(i + 1, n)])
        X_tr, X_te = _impute_train_medians(X_raw[train_idx], X_raw[i:i + 1])
        scaler = StandardScaler()
        X_tr = scaler.fit_transform(X_tr)
        X_te = scaler.transform(X_te)
        model = RidgeClassifier(alpha=cfg.RIDGE_ALPHA, random_state=cfg.RANDOM_STATE)
        model.fit(X_tr, y[train_idx])
        probs[i] = _sigmoid(model.decision_function(X_te))[0]
    return probs


def youden_threshold(y: np.ndarray, probs: np.ndarray) -> float:
    """Youden-J optimal threshold from ROC on pooled out-of-fold predictions."""
    fpr, tpr, thr = roc_curve(y, probs)
    j_idx = int(np.argmax(tpr - fpr))
    t = float(thr[j_idx])
    if not np.isfinite(t):          # sklearn pads thresholds[0] with inf
        t = 1.0
    return t


def metrics_at_threshold(y: np.ndarray, probs: np.ndarray, thr: float) -> dict:
    """AUROC + threshold-dependent metrics at the given probability cutoff."""
    preds = (probs >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, preds, labels=[0, 1]).ravel()
    return {
        "auroc": float(roc_auc_score(y, probs)),
        "recall": float(recall_score(y, preds, zero_division=0)),
        "specificity": float(tn / max(tn + fp, 1)),
        "f1": float(f1_score(y, preds, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, preds)),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }


def bootstrap_ci(y: np.ndarray, probs: np.ndarray, n_boot: int):
    """Bootstrap 95% CI: resample the 34 FIXED LOVO (y, prob) tuples."""
    rng = np.random.RandomState(cfg.RANDOM_STATE)
    aurocs = []
    for _ in range(n_boot):
        idx = rng.choice(len(y), size=len(y), replace=True)
        if len(np.unique(y[idx])) < 2:      # degenerate one-class resample
            continue
        aurocs.append(roc_auc_score(y[idx], probs[idx]))
    aurocs = np.array(aurocs)
    return (
        float(np.percentile(aurocs, 2.5)),
        float(np.percentile(aurocs, 97.5)),
        int(len(aurocs)),
    )


def permutation_test(y: np.ndarray, probs: np.ndarray, observed: float, n_perm: int):
    """Label-permutation p: shuffle y_true against FIXED winner predictions."""
    rng = np.random.RandomState(cfg.RANDOM_STATE + 1)
    n_geq = 0
    for _ in range(n_perm):
        y_perm = rng.permutation(y)
        if roc_auc_score(y_perm, probs) >= observed:
            n_geq += 1
    return float((1 + n_geq) / (n_perm + 1))


def feature_importance_insample(X_raw: np.ndarray, y: np.ndarray,
                                features: list, n_repeats: int) -> list:
    """
    Permutation feature importance — IN-SAMPLE, diagnostic only.
    Refit impute+scale+Ridge on all 34 VINs; shuffle each (imputed, scaled)
    feature column; AUROC drop vs in-sample baseline, averaged over repeats.
    """
    X_full, _ = _impute_train_medians(X_raw, X_raw[:0])
    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X_full)
    model = RidgeClassifier(alpha=cfg.RIDGE_ALPHA, random_state=cfg.RANDOM_STATE)
    model.fit(X_sc, y)
    baseline = roc_auc_score(y, _sigmoid(model.decision_function(X_sc)))

    rows = []
    for j, feat in enumerate(features):
        drops = []
        for rep in range(n_repeats):
            rng = np.random.RandomState(cfg.RANDOM_STATE + 100 * j + rep)
            X_perm = X_sc.copy()
            X_perm[:, j] = rng.permutation(X_perm[:, j])
            perm_auc = roc_auc_score(y, _sigmoid(model.decision_function(X_perm)))
            drops.append(baseline - perm_auc)
        rows.append({
            "feature": feat,
            "importance_mean": round(float(np.mean(drops)), 4),
            "importance_std": round(float(np.std(drops)), 4),
        })
    rows.sort(key=lambda r: r["importance_mean"], reverse=True)
    return rows


def alert_tier(prob: float) -> str:
    """GREEN < 0.35 <= AMBER < 0.55 <= RED."""
    if prob >= TIER_RED:
        return "RED"
    if prob >= TIER_AMBER:
        return "AMBER"
    return "GREEN"


# ─────────────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────────────
mat = pd.read_csv(cfg.RESULTS / "V1_SM_feature_matrix.csv")
scr = pd.read_csv(cfg.RESULTS / "V1_SM_feature_screening.csv")

assert len(mat) == cfg.N_VINS, f"VIN COUNT MISMATCH: {len(mat)}"
assert int(mat["failed"].sum()) == cfg.N_FAILED, "FAILED COUNT MISMATCH"

pool = (
    scr[scr["in_pool"].astype(bool)]
    .sort_values("auroc", ascending=False)["feature"]
    .tolist()
)
assert len(pool) > 0, "EMPTY CANDIDATE POOL"
missing = [f for f in pool if f not in mat.columns]
assert not missing, f"POOL FEATURES MISSING FROM MATRIX: {missing}"

y = mat["failed"].astype(int).values
vin_labels = mat["vin_label"].values   # identifiers only — never a feature

# k range: cap at pool size when pool < SUBSET_MAX (or even < SUBSET_MIN)
k_lo = min(cfg.SUBSET_MIN, len(pool))
k_hi = min(cfg.SUBSET_MAX, len(pool))
subsets = [list(c) for k in range(k_lo, k_hi + 1) for c in combinations(pool, k)]

print(f"V1_SM RIDGE — exhaustive subset search "
      f"({len(subsets)} subsets, {cfg.LOVO_FOLDS}-fold LOVO)")
print(f"  pool ({len(pool)}): {', '.join(pool)}")
print(f"  k range: {k_lo}..{k_hi} (config {cfg.SUBSET_MIN}..{cfg.SUBSET_MAX}, "
      f"capped at pool size)")


# ─────────────────────────────────────────────────────────────────────────────
# Exhaustive subset search — LOVO per subset, Youden threshold on OOF preds
# ─────────────────────────────────────────────────────────────────────────────
results, prob_cache, thr_cache = [], {}, {}
for feats in subsets:
    X = mat[feats].values.astype(float)
    probs = lovo_ridge(X, y)
    thr = youden_threshold(y, probs)
    m = metrics_at_threshold(y, probs, thr)
    key = "|".join(feats)
    prob_cache[key] = probs
    thr_cache[key] = thr
    results.append({
        "features": key, "k": len(feats),
        "auroc": round(m["auroc"], 4),
        "recall": round(m["recall"], 4),
        "specificity": round(m["specificity"], 4),
        "f1": round(m["f1"], 4),
        "mcc": round(m["mcc"], 4),
        "youden_threshold": round(thr, 4),
    })

elim = pd.DataFrame(results)

# Winner: highest AUROC -> smaller k -> higher MCC
elim_ranked = elim.sort_values(
    ["auroc", "k", "mcc"], ascending=[False, True, False], kind="mergesort"
).reset_index(drop=True)
winner = elim_ranked.iloc[0]
win_feats = winner["features"].split("|")
win_k = int(winner["k"])
win_probs = prob_cache[winner["features"]]
win_thr = thr_cache[winner["features"]]   # exact Youden threshold (CSV stores rounded)
win_m = metrics_at_threshold(y, win_probs, win_thr)

best_per_k = elim_ranked.groupby("k", as_index=False).first().sort_values("k")
print("  best per k:  " + " | ".join(
    f"k={int(r['k'])} AUROC={r['auroc']:.3f}" for _, r in best_per_k.iterrows()))
print(f"  WINNER: k={win_k}, AUROC={win_m['auroc']:.3f} {win_feats}")
print(f"  Recall: {win_m['tp']}/{cfg.N_FAILED}   "
      f"Specificity: {win_m['tn']}/{cfg.N_NONFAILED}   "
      f"F1: {win_m['f1']:.3f}   MCC: {win_m['mcc']:.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# Winner statistics: bootstrap CI, permutation test, feature importance
# ─────────────────────────────────────────────────────────────────────────────
ci_lo, ci_hi, n_boot_valid = bootstrap_ci(y, win_probs, cfg.N_BOOTSTRAP)
perm_p = permutation_test(y, win_probs, win_m["auroc"], cfg.N_PERMUTATION)
print(f"  Bootstrap 95% CI: [{ci_lo:.2f}, {ci_hi:.2f}]   Permutation p: {perm_p:.3f}")

importance = feature_importance_insample(
    mat[win_feats].values.astype(float), y, win_feats, N_IMPORTANCE_REPEATS)
print(f"  Feature importance (IN-SAMPLE, diagnostic only, "
      f"{N_IMPORTANCE_REPEATS} repeats):")
for r in importance:
    print(f"    {r['feature']:<28} drop={r['importance_mean']:+.4f} "
          f"+/- {r['importance_std']:.4f}")

# Gate check (G1)
if win_m["auroc"] >= 0.85:
    gate = "PASS (AUROC >= 0.85 — goal G1 met)"
elif win_m["auroc"] >= 0.80:
    gate = "MARGINAL (0.80 <= AUROC < 0.85 — shippable with honest framing)"
else:
    gate = "FAIL (AUROC < 0.80 — reported honestly, no further feature mining)"
print(f"  Gate G1: {gate}")


# ─────────────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────────────
cfg.RESULTS.mkdir(parents=True, exist_ok=True)

elim_out = cfg.RESULTS / "V1_SM_elimination_results.csv"
elim.sort_values(
    ["auroc", "k", "mcc"], ascending=[False, True, False], kind="mergesort"
).to_csv(elim_out, index=False)

pred_rows = []
for i in range(len(y)):
    p = float(win_probs[i])
    pred = int(p >= win_thr)
    pred_rows.append({
        "vin_label": vin_labels[i],
        "failed": int(y[i]),
        "y_prob": round(p, 4),
        "y_pred_youden": pred,
        "alert_tier": alert_tier(p),
        "correct": int(pred == y[i]),
    })
pred_out = cfg.RESULTS / "V1_SM_lovo_predictions.csv"
pd.DataFrame(pred_rows).to_csv(pred_out, index=False)

spec = {
    "version": cfg.VERSION,
    "model": "RidgeClassifier",
    "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "features": win_feats,
    "k": win_k,
    "alpha": cfg.RIDGE_ALPHA,
    "lovo_folds": cfg.LOVO_FOLDS,
    "auroc": round(win_m["auroc"], 4),
    "bootstrap_95ci": [round(ci_lo, 4), round(ci_hi, 4)],
    "bootstrap_n_valid": n_boot_valid,
    "permutation_p": round(perm_p, 4),
    "youden_threshold": round(win_thr, 4),
    "recall": round(win_m["recall"], 4),
    "specificity": round(win_m["specificity"], 4),
    "f1": round(win_m["f1"], 4),
    "mcc": round(win_m["mcc"], 4),
    "confusion": {"tp": win_m["tp"], "fp": win_m["fp"],
                  "fn": win_m["fn"], "tn": win_m["tn"]},
    "alert_tiers": {"green_lt": TIER_AMBER, "amber_lt": TIER_RED,
                    "red_gte": TIER_RED},
    "feature_importance_insample": importance,
    "feature_importance_note": (
        "Permutation importance on an all-34 in-sample refit; "
        "diagnostic only, not an out-of-fold estimate."
    ),
    "subset_search": {
        "pool": pool,
        "pool_size": len(pool),
        "k_range_config": [cfg.SUBSET_MIN, cfg.SUBSET_MAX],
        "k_range_effective": [k_lo, k_hi],
        "n_subsets": len(subsets),
        "tie_breaking": "highest AUROC -> smaller k -> higher MCC",
    },
    "gate_g1": gate,
    "config_snapshot": {
        "alpha": cfg.RIDGE_ALPHA,
        "random_state": cfg.RANDOM_STATE,
        "bootstrap_seed": cfg.RANDOM_STATE,
        "permutation_seed": cfg.RANDOM_STATE + 1,
        "n_bootstrap": cfg.N_BOOTSTRAP,
        "n_permutation": cfg.N_PERMUTATION,
        "n_importance_repeats": N_IMPORTANCE_REPEATS,
    },
}
spec_out = cfg.RESULTS / "V1_SM_ridge_spec.json"
with open(spec_out, "w") as f:
    json.dump(spec, f, indent=2)

print()
print(f"Saved: {elim_out}")
print(f"Saved: {pred_out}")
print(f"Saved: {spec_out}")
