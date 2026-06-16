"""
C1_model_audit.py — Agent C adversarial methodological audit of V1 SM modeling stack.

Read-only on V1 files. Reruns:
  1. NESTED LOVO (screening 23->pool + subset search redone inside each of 34 folds)
  2. Threshold honesty (per-fold inner-OOF Youden vs pooled post-hoc Youden)
  3. Calibration of the 34 OOF probabilities (Brier, CITL, recalibration slope)
  4. Model-class sweep on the fixed winner 4 features (LOVO)
  5. Jackknife AUROC over VINs + fold-order / seed invariance
  6. Truck-week count from the weekly cache (survival reframing math)

Outputs: STARTER MOTOR/V1.1/audit/results/C1_audit_results.json + console log.
"""

import json
import math
from itertools import combinations
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import RidgeClassifier, LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, roc_curve, confusion_matrix, brier_score_loss

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
RESULTS_V1 = ROOT / "STARTER MOTOR" / "results"
OUT_DIR = ROOT / "STARTER MOTOR" / "V1.1" / "audit" / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)
WEEKLY = ROOT / "STARTER MOTOR" / "cache" / "weekly"

# V1 constants (mirrored from V1_SM_config.py / scripts — read-only fidelity)
ALPHA_MW = 0.10
AUROC_MIN = 0.60
CORR_MAX = 0.85
LOVO_STABLE_FRAC = 0.80
POOL_CAP = 12
RIDGE_ALPHA = 1.0
RANDOM_STATE = 42
SUBSET_MIN, SUBSET_MAX = 4, 8
WINNER_FEATS = ["vsi_std_ratio_30d", "vsi_dominant_freq",
                "failed_crank_rate_last90", "vsi_range_trend"]
V1_AUROC = 0.9214
V1_YOUDEN = 0.4382

audit = {}

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers (faithful replicas of V1 code)
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid(x):
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-np.abs(x))),
                    np.exp(-np.abs(x)) / (1.0 + np.exp(-np.abs(x))))


def _impute_train_medians(X_train, X_test):
    X_tr, X_te = X_train.copy(), X_test.copy()
    for j in range(X_tr.shape[1]):
        med = np.nanmedian(X_tr[:, j])
        if np.isnan(med):
            med = 0.0
        X_tr[np.isnan(X_tr[:, j]), j] = med
        X_te[np.isnan(X_te[:, j]), j] = med
    return X_tr, X_te


def lovo_probs(X_raw, y, model_factory):
    """Generic LOVO: per fold impute (train medians) + scale + model."""
    n = len(y)
    probs = np.full(n, np.nan)
    for i in range(n):
        tr = np.concatenate([np.arange(0, i), np.arange(i + 1, n)])
        X_tr, X_te = _impute_train_medians(X_raw[tr], X_raw[i:i + 1])
        sc = StandardScaler()
        X_tr = sc.fit_transform(X_tr)
        X_te = sc.transform(X_te)
        m = model_factory()
        m.fit(X_tr, y[tr])
        if hasattr(m, "predict_proba"):
            probs[i] = m.predict_proba(X_te)[0, 1]
        else:
            probs[i] = _sigmoid(m.decision_function(X_te))[0]
    return probs


def ridge_factory():
    return RidgeClassifier(alpha=RIDGE_ALPHA, random_state=RANDOM_STATE)


def youden_threshold(y, probs):
    fpr, tpr, thr = roc_curve(y, probs)
    t = float(thr[int(np.argmax(tpr - fpr))])
    return 1.0 if not np.isfinite(t) else t


def metrics_at(y, probs, thr):
    preds = (probs >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, preds, labels=[0, 1]).ravel()
    return {"auroc": float(roc_auc_score(y, probs)),
            "recall": tp / max(tp + fn, 1), "specificity": tn / max(tn + fp, 1),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}


def mw_pvalue(pos, neg):
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    try:
        _, p = stats.mannwhitneyu(pos, neg, alternative="two-sided")
        return float(p)
    except ValueError:
        return float("nan")


def spearman_abs_r(a, b):
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 4:
        return 0.0
    r, _ = stats.spearmanr(a[mask], b[mask])
    return abs(float(r)) if np.isfinite(r) else 0.0


def screen_pool(df, labels, feature_cols):
    """Faithful replica of V1_SM_feature_selection.py on an arbitrary VIN subset.

    Steps: (1) MW p<0.10 & dir-agnostic AUROC>=0.60, (2) greedy |Spearman|<0.85,
    (3) leave-one-out stability p<0.10 in >= ceil(0.8*n) re-screens, (4) top-12 by AUROC.
    """
    n = len(df)
    recs = []
    for feat in feature_cols:
        vals = df[feat].values.astype(float)
        mask = np.isfinite(vals)
        v, l = vals[mask], labels[mask]
        pos, neg = v[l == 1], v[l == 0]
        p_mw = mw_pvalue(pos, neg)
        if len(pos) > 0 and len(neg) > 0 and len(np.unique(l)) == 2:
            a_raw = float(roc_auc_score(l, v))
            a = max(a_raw, 1 - a_raw)
        else:
            a = float("nan")
        recs.append({"feature": feat, "mw_p": p_mw, "auroc": a,
                     "pass_screen": bool(np.isfinite(p_mw) and p_mw < ALPHA_MW
                                         and np.isfinite(a) and a >= AUROC_MIN)})
    scr = pd.DataFrame(recs)

    survivors = scr[scr["pass_screen"]].sort_values(
        "auroc", ascending=False)["feature"].tolist()
    kept = []
    for feat in survivors:
        if all(spearman_abs_r(df[feat].values.astype(float),
                              df[k].values.astype(float)) < CORR_MAX for k in kept):
            kept.append(feat)

    stable_min = math.ceil(LOVO_STABLE_FRAC * n)
    lovo_counts = {f: 0 for f in kept}
    lab = labels
    for i in range(n):
        km = np.ones(n, dtype=bool)
        km[i] = False
        l_sub = lab[km]
        for feat in kept:
            vals = df[feat].values.astype(float)[km]
            m = np.isfinite(vals)
            v, l = vals[m], l_sub[m]
            p = mw_pvalue(v[l == 1], v[l == 0])
            if np.isfinite(p) and p < ALPHA_MW:
                lovo_counts[feat] += 1

    pool = [f for f in kept if lovo_counts[f] >= stable_min]
    pool = (scr[scr["feature"].isin(pool)]
            .sort_values("auroc", ascending=False)
            .head(POOL_CAP)["feature"].tolist())
    auroc_rank = scr.sort_values("auroc", ascending=False)["feature"].tolist()
    return pool, auroc_rank


def subset_search(df_tr, y_tr, pool, auroc_rank):
    """Replica of the V1 exhaustive subset search on training VINs only.
    Returns (winner_feats, inner_youden_thr, inner_auroc)."""
    if len(pool) == 0:                       # degenerate fallback — log it
        pool = auroc_rank[:1]
    k_lo = min(SUBSET_MIN, len(pool))
    k_hi = min(SUBSET_MAX, len(pool))
    best = None
    for k in range(k_lo, k_hi + 1):
        for feats in combinations(pool, k):
            feats = list(feats)
            X = df_tr[feats].values.astype(float)
            probs = lovo_probs(X, y_tr, ridge_factory)
            thr = youden_threshold(y_tr, probs)
            m = metrics_at(y_tr, probs, thr)
            preds = (probs >= thr).astype(int)
            from sklearn.metrics import matthews_corrcoef
            mcc = matthews_corrcoef(y_tr, preds)
            cand = (round(m["auroc"], 10), -k, round(mcc, 10), feats, thr)
            if best is None or (cand[0], cand[1], cand[2]) > (best[0], best[1], best[2]):
                best = cand
    return best[3], best[4], best[0]


def fit_predict_one(df_tr, y_tr, df_te_row, feats):
    X_tr_raw = df_tr[feats].values.astype(float)
    X_te_raw = df_te_row[feats].values.astype(float).reshape(1, -1)
    X_tr, X_te = _impute_train_medians(X_tr_raw, X_te_raw)
    sc = StandardScaler()
    X_tr = sc.fit_transform(X_tr)
    X_te = sc.transform(X_te)
    m = ridge_factory()
    m.fit(X_tr, y_tr)
    return float(_sigmoid(m.decision_function(X_te))[0])


# ─────────────────────────────────────────────────────────────────────────────
# Load data + V1 artefacts
# ─────────────────────────────────────────────────────────────────────────────
mat = pd.read_csv(RESULTS_V1 / "V1_SM_feature_matrix.csv")
preds_v1 = pd.read_csv(RESULTS_V1 / "V1_SM_lovo_predictions.csv")
FEATURE_COLS = [c for c in mat.columns if c not in ("vin_label", "failed")]
y = mat["failed"].astype(int).values
vins = mat["vin_label"].values
n = len(y)
assert n == 34 and y.sum() == 14 and len(FEATURE_COLS) == 23

# Reproduce V1 winner LOVO probs (sanity: must match lovo_predictions.csv)
v1_probs = lovo_probs(mat[WINNER_FEATS].values.astype(float), y, ridge_factory)
v1_csv_probs = preds_v1.set_index("vin_label").loc[vins, "y_prob"].values
repro_max_diff = float(np.max(np.abs(v1_probs - v1_csv_probs)))
v1_auroc_repro = float(roc_auc_score(y, v1_probs))
print(f"[0] V1 reproduction: AUROC={v1_auroc_repro:.4f} (reported {V1_AUROC}), "
      f"max |prob diff| vs CSV = {repro_max_diff:.2e}")
audit["v1_reproduction"] = {"auroc": v1_auroc_repro, "max_prob_diff_vs_csv": repro_max_diff}

# ─────────────────────────────────────────────────────────────────────────────
# 1. NESTED LOVO — screening + subset selection inside every fold
# ─────────────────────────────────────────────────────────────────────────────
print("\n[1] NESTED LOVO (screening + subset search per fold) ...")
nested_probs = np.full(n, np.nan)
nested_pred_foldthr = np.full(n, -1, dtype=int)
fold_rows = []
for i in range(n):
    tr_mask = np.ones(n, dtype=bool)
    tr_mask[i] = False
    df_tr = mat[tr_mask].reset_index(drop=True)
    y_tr = y[tr_mask]
    pool, auroc_rank = screen_pool(df_tr, y_tr, FEATURE_COLS)
    feats, thr_inner, auroc_inner = subset_search(df_tr, y_tr, pool, auroc_rank)
    p = fit_predict_one(df_tr, y_tr, mat.iloc[i], feats)
    nested_probs[i] = p
    nested_pred_foldthr[i] = int(p >= thr_inner)
    fold_rows.append({"vin": vins[i], "failed": int(y[i]), "pool_size": len(pool),
                      "pool": "|".join(pool), "winner": "|".join(feats),
                      "k": len(feats), "inner_auroc": round(auroc_inner, 4),
                      "inner_youden": round(thr_inner, 4), "prob": round(p, 4),
                      "pred_foldthr": int(p >= thr_inner)})
    print(f"  fold {i+1:>2}/{n} held-out={vins[i]:<12} pool={len(pool)} "
          f"winner_k={len(feats)} inner_AUROC={auroc_inner:.3f} "
          f"thr={thr_inner:.3f} prob={p:.3f}")

folds_df = pd.DataFrame(fold_rows)
folds_df.to_csv(OUT_DIR / "C1_nested_lovo_folds.csv", index=False)

nested_auroc = float(roc_auc_score(y, nested_probs))
m_foldthr = {"recall": None, "specificity": None}
tn, fp, fn, tp = confusion_matrix(y, nested_pred_foldthr, labels=[0, 1]).ravel()
m_foldthr = {"recall": tp / 14, "specificity": tn / 20,
             "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}
pooled_thr_nested = youden_threshold(y, nested_probs)
m_pooled_nested = metrics_at(y, nested_probs, pooled_thr_nested)

# Bootstrap CI on the nested OOF preds (same recipe as V1: resample fixed tuples)
rng = np.random.RandomState(RANDOM_STATE)
boots = []
for _ in range(2000):
    idx = rng.choice(n, n, replace=True)
    if len(np.unique(y[idx])) < 2:
        continue
    boots.append(roc_auc_score(y[idx], nested_probs[idx]))
nested_ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]

# Feature-selection stability across folds
from collections import Counter
feat_counts = Counter()
for r in fold_rows:
    feat_counts.update(r["winner"].split("|"))
winner_identical = sum(1 for r in fold_rows if set(r["winner"].split("|")) == set(WINNER_FEATS))

print(f"\n  NESTED AUROC = {nested_auroc:.4f}  (V1 reported {V1_AUROC}; "
      f"optimism = {V1_AUROC - nested_auroc:+.4f})")
print(f"  Nested bootstrap 95% CI: [{nested_ci[0]:.3f}, {nested_ci[1]:.3f}]")
print(f"  Per-fold-threshold confusion: TP={tp} FN={fn} TN={tn} FP={fp} "
      f"(recall {tp}/14, spec {tn}/20)")
print(f"  Folds picking exactly the V1 winner set: {winner_identical}/34")
print(f"  Feature frequency in fold winners: {dict(feat_counts)}")

audit["nested_lovo"] = {
    "nested_auroc": nested_auroc, "v1_reported_auroc": V1_AUROC,
    "optimism": V1_AUROC - nested_auroc, "nested_bootstrap_95ci": nested_ci,
    "per_fold_threshold_metrics": m_foldthr,
    "pooled_youden_on_nested": {"thr": pooled_thr_nested, **m_pooled_nested},
    "winner_set_identical_folds": int(winner_identical),
    "feature_frequency": dict(feat_counts),
    "pool_size_min_max": [int(folds_df["pool_size"].min()), int(folds_df["pool_size"].max())],
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. Threshold honesty — fixed winner features, per-fold inner-OOF Youden
# ─────────────────────────────────────────────────────────────────────────────
print("\n[2] Threshold honesty (fixed 4 features, per-fold inner Youden) ...")
fold_thrs = np.full(n, np.nan)
pred_foldthr_fixed = np.full(n, -1, dtype=int)
for i in range(n):
    tr_mask = np.ones(n, dtype=bool)
    tr_mask[i] = False
    df_tr = mat[tr_mask].reset_index(drop=True)
    y_tr = y[tr_mask]
    X = df_tr[WINNER_FEATS].values.astype(float)
    probs_inner = lovo_probs(X, y_tr, ridge_factory)
    fold_thrs[i] = youden_threshold(y_tr, probs_inner)
    pred_foldthr_fixed[i] = int(v1_probs[i] >= fold_thrs[i])

tn2, fp2, fn2, tp2 = confusion_matrix(y, pred_foldthr_fixed, labels=[0, 1]).ravel()
m_pooled_v1 = metrics_at(y, v1_probs, V1_YOUDEN)
print(f"  Per-fold thresholds: min={fold_thrs.min():.4f} median={np.median(fold_thrs):.4f} "
      f"max={fold_thrs.max():.4f} (pooled post-hoc = {V1_YOUDEN})")
print(f"  Pooled-Youden (V1, post-hoc): recall {m_pooled_v1['tp']}/14, "
      f"spec {m_pooled_v1['tn']}/20")
print(f"  Per-fold-Youden (honest):     recall {tp2}/14, spec {tn2}/20")
audit["threshold_honesty"] = {
    "fold_thr_min": float(fold_thrs.min()), "fold_thr_median": float(np.median(fold_thrs)),
    "fold_thr_max": float(fold_thrs.max()), "pooled_thr": V1_YOUDEN,
    "pooled_metrics": m_pooled_v1,
    "per_fold_metrics": {"tp": int(tp2), "fp": int(fp2), "fn": int(fn2), "tn": int(tn2),
                         "recall": tp2 / 14, "specificity": tn2 / 20},
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. Calibration of the 34 OOF probabilities
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Calibration ...")
base_rate = y.mean()
brier = float(brier_score_loss(y, v1_probs))
brier_ref = float(base_rate * (1 - base_rate))           # constant-base-rate predictor
mean_p = float(v1_probs.mean())
mean_p_pos = float(v1_probs[y == 1].mean())
mean_p_neg = float(v1_probs[y == 0].mean())
eps = 1e-6
logit_p = np.log(np.clip(v1_probs, eps, 1 - eps) / (1 - np.clip(v1_probs, eps, 1 - eps)))
recal = LogisticRegression(C=1e6, max_iter=10000).fit(logit_p.reshape(-1, 1), y)
cal_slope = float(recal.coef_[0, 0])
cal_intercept = float(recal.intercept_[0])
citl = float(np.log(base_rate / (1 - base_rate)) - np.log(mean_p / (1 - mean_p)))
print(f"  Base rate 14/34 = {base_rate:.4f}; mean predicted prob = {mean_p:.4f}")
print(f"  Brier = {brier:.4f}  (constant-base-rate reference = {brier_ref:.4f})")
print(f"  Mean prob | failed = {mean_p_pos:.3f}; | non-failed = {mean_p_neg:.3f}")
print(f"  Recalibration slope = {cal_slope:.3f}, intercept = {cal_intercept:.3f} "
      f"(slope >> 1 => underconfident/compressed)")
audit["calibration"] = {
    "base_rate": float(base_rate), "mean_pred_prob": mean_p,
    "brier": brier, "brier_constant_reference": brier_ref,
    "mean_prob_failed": mean_p_pos, "mean_prob_nonfailed": mean_p_neg,
    "recal_slope": cal_slope, "recal_intercept": cal_intercept,
    "citl_logit_gap": citl,
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. Model-class sweep on the fixed winner 4 features
# ─────────────────────────────────────────────────────────────────────────────
print("\n[4] Model-class sweep (same 4 features, same LOVO) ...")
X4 = mat[WINNER_FEATS].values.astype(float)
model_zoo = {
    "RidgeClassifier(a=1.0)": ridge_factory,
    "LogisticRegression(L2,C=1)": lambda: LogisticRegression(C=1.0, max_iter=10000),
    "LogisticRegression(L2,C=0.1)": lambda: LogisticRegression(C=0.1, max_iter=10000),
    "LinearSVM(C=1)": lambda: LinearSVC(C=1.0, max_iter=20000),
    "GaussianNB": GaussianNB,
    "kNN(k=5)": lambda: KNeighborsClassifier(n_neighbors=5),
    "kNN(k=7)": lambda: KNeighborsClassifier(n_neighbors=7),
    "DecisionTree(depth=2)": lambda: DecisionTreeClassifier(max_depth=2, random_state=42),
    "GradientBoosting(d2,100)": lambda: GradientBoostingClassifier(
        n_estimators=100, max_depth=2, random_state=42),
    "RandomForest(300)": lambda: RandomForestClassifier(n_estimators=300, random_state=42),
}
zoo_results = {}
for name, fac in model_zoo.items():
    p = lovo_probs(X4, y, fac)
    a = float(roc_auc_score(y, p))
    thr = youden_threshold(y, p)
    m = metrics_at(y, p, thr)
    zoo_results[name] = {"auroc": round(a, 4), "recall": round(m["recall"], 4),
                         "specificity": round(m["specificity"], 4)}
    print(f"  {name:<30} AUROC={a:.4f}  recall={m['recall']:.3f} spec={m['specificity']:.3f}")
audit["model_zoo"] = zoo_results

# ─────────────────────────────────────────────────────────────────────────────
# 5. Jackknife AUROC + invariance checks
# ─────────────────────────────────────────────────────────────────────────────
print("\n[5] Jackknife + invariance ...")
jack = []
for i in range(n):
    km = np.ones(n, dtype=bool)
    km[i] = False
    a = float(roc_auc_score(y[km], v1_probs[km]))
    jack.append({"vin": vins[i], "failed": int(y[i]),
                 "auroc_without": round(a, 4),
                 "delta": round(a - v1_auroc_repro, 4)})
jack_df = pd.DataFrame(jack).sort_values("delta")
jack_df.to_csv(OUT_DIR / "C1_jackknife.csv", index=False)
print(f"  Jackknife AUROC range: [{jack_df['auroc_without'].min():.4f}, "
      f"{jack_df['auroc_without'].max():.4f}]")
print("  Most negative deltas (model HURTS without them — it leans on these):")
print(jack_df.head(3).to_string(index=False))
print("  Most positive deltas (model IMPROVES without them — these are its errors):")
print(jack_df.tail(3).to_string(index=False))

# fold-order invariance: shuffle row order, rerun LOVO
rng = np.random.RandomState(7)
order_aurocs = []
for rep in range(5):
    perm = rng.permutation(n)
    p_perm = lovo_probs(X4[perm], y[perm], ridge_factory)
    order_aurocs.append(float(roc_auc_score(y[perm], p_perm)))
# ridge seed invariance
seed_diff = 0.0
for rs in (0, 7, 1234):
    p_rs = lovo_probs(X4, y, lambda: RidgeClassifier(alpha=RIDGE_ALPHA, random_state=rs))
    seed_diff = max(seed_diff, float(np.max(np.abs(p_rs - v1_probs))))
print(f"  Fold-order shuffles (5x): AUROCs = {[round(a,6) for a in order_aurocs]}")
print(f"  Ridge random_state sweep: max |prob diff| = {seed_diff:.2e}")
audit["stability"] = {
    "jackknife_min": float(jack_df["auroc_without"].min()),
    "jackknife_max": float(jack_df["auroc_without"].max()),
    "jackknife_top_negative": jack_df.head(3).to_dict("records"),
    "jackknife_top_positive": jack_df.tail(3).to_dict("records"),
    "fold_order_aurocs": order_aurocs,
    "ridge_seed_max_prob_diff": seed_diff,
}

# ─────────────────────────────────────────────────────────────────────────────
# 6. Truck-week reframing math
# ─────────────────────────────────────────────────────────────────────────────
print("\n[6] Truck-week counts from weekly cache ...")
week_counts = {}
for f in sorted(WEEKLY.glob("V1_SM_weekly_*.parquet")):
    vin = f.stem.replace("V1_SM_weekly_", "")
    try:
        wk = pd.read_parquet(f)
        week_counts[vin] = len(wk)
    except Exception as e:
        week_counts[vin] = f"ERROR: {e}"
total_weeks = sum(v for v in week_counts.values() if isinstance(v, int))
print(f"  Total truck-weeks: {total_weeks} across {len(week_counts)} VINs "
      f"(min={min(v for v in week_counts.values() if isinstance(v,int))}, "
      f"max={max(v for v in week_counts.values() if isinstance(v,int))})")
audit["truck_weeks"] = {"total": total_weeks, "per_vin": week_counts}

# lifelines availability
try:
    import lifelines
    audit["lifelines"] = lifelines.__version__
except ImportError:
    audit["lifelines"] = None
print(f"  lifelines: {audit['lifelines']}")

# OOF error feature context (for section 6 narrative)
err_vins = ["VIN8_F_SM", "VIN8_NF_SM", "VIN9_NF_SM", "VIN5_F_SM"]
audit["error_context"] = mat[mat["vin_label"].isin(err_vins)][
    ["vin_label", "failed"] + WINNER_FEATS].to_dict("records")

with open(OUT_DIR / "C1_audit_results.json", "w") as f:
    json.dump(audit, f, indent=2, default=str)
print(f"\nSaved: {OUT_DIR / 'C1_audit_results.json'}")
