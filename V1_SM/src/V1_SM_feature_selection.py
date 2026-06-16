"""
V1_SM_feature_selection.py  —  Phase 3: Feature Screening
BharatBenz Starter Motor predictive maintenance pipeline.

Produces: STARTER MOTOR/results/V1_SM_feature_screening.csv
  - One row per feature (all 23), ranked by direction-agnostic AUROC
  - Statistics: Mann-Whitney U p, single-feature AUROC, Cohen's d, LOVO stability
  - Pass/fail flag per criterion + final in_pool flag

Selection pipeline (order binds):
  1. Screen:       Mann-Whitney p < 0.10  AND  AUROC >= 0.60
  2. Corr filter:  |Spearman r| < 0.85 among survivors (keep higher-AUROC member)
  3. LOVO filter:  Mann-Whitney p < 0.10 in >= 28/34 leave-one-VIN-out re-screens
  4. Rank by AUROC, cap candidate pool at 12

Methodology notes:
  - AUROC is direction-agnostic: score = max(auc, 1 - auc); raw direction recorded.
  - Nulls: screen on available (non-null) values per feature; NO imputation.
  - Cohen's d uses pooled std (ddof=1), sign = failed_mean - nonfailed_mean.
"""

import math
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
from scipy import stats
from sklearn.metrics import roc_auc_score

# ── Screening constants ──────────────────────────────────────────────────────
ALPHA = 0.10            # Mann-Whitney significance level
AUROC_MIN = 0.60        # direction-agnostic single-feature AUROC floor
CORR_MAX = 0.85         # |Spearman r| threshold among survivors
LOVO_STABLE_FRAC = 0.80  # required fraction of stable leave-one-out re-screens
LOVO_STABLE_MIN = math.ceil(LOVO_STABLE_FRAC * cfg.LOVO_FOLDS)  # 28 when LOVO_FOLDS=34
POOL_CAP = 12           # maximum candidate-pool size


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def mw_pvalue(pos: np.ndarray, neg: np.ndarray) -> float:
    """Two-sided Mann-Whitney U p-value; NaN if either group is empty/degenerate."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    try:
        _, p = stats.mannwhitneyu(pos, neg, alternative="two-sided")
        return float(p)
    except ValueError:  # e.g. all values identical
        return float("nan")


def cohens_d(pos: np.ndarray, neg: np.ndarray) -> float:
    """Cohen's d with pooled std (ddof=1). Sign: failed - non-failed."""
    n1, n2 = len(pos), len(neg)
    if n1 < 2 or n2 < 2:
        return float("nan")
    s1, s2 = np.std(pos, ddof=1), np.std(neg, ddof=1)
    pooled = np.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    if pooled == 0:
        return float("nan")
    return float((np.mean(pos) - np.mean(neg)) / pooled)


def spearman_abs_r(a: np.ndarray, b: np.ndarray) -> float:
    """|Spearman r| on jointly non-null pairs; 0.0 if < 4 valid pairs."""
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 4:
        return 0.0
    r, _ = stats.spearmanr(a[mask], b[mask])
    return abs(float(r)) if np.isfinite(r) else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Load feature matrix
# ─────────────────────────────────────────────────────────────────────────────
print("Loading feature matrix...")
mat_path = cfg.RESULTS / "V1_SM_feature_matrix.csv"
df = pd.read_csv(mat_path)

FEATURE_COLS = [c for c in df.columns if c not in ("vin_label", "failed")]
labels = df["failed"].astype(int).values

print(f"  Matrix: {df.shape[0]} VINs x {len(FEATURE_COLS)} features")
assert df.shape[0] == cfg.N_VINS, f"VIN COUNT MISMATCH: {df.shape[0]}"
assert len(FEATURE_COLS) == 23, f"FEATURE COUNT MISMATCH: {len(FEATURE_COLS)}"
assert int(labels.sum()) == cfg.N_FAILED, f"FAILED COUNT MISMATCH: {labels.sum()}"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: per-feature statistics (full fleet, non-null values only)
# ─────────────────────────────────────────────────────────────────────────────
print("\nStep 1: screening statistics (Mann-Whitney, AUROC, Cohen's d)...")

records = []
for feat in FEATURE_COLS:
    vals = df[feat].values.astype(float)
    mask = np.isfinite(vals)
    v, l = vals[mask], labels[mask]
    pos, neg = v[l == 1], v[l == 0]

    p_mw = mw_pvalue(pos, neg)
    d = cohens_d(pos, neg)

    if len(pos) > 0 and len(neg) > 0:
        auroc_raw = float(roc_auc_score(l, v))
    else:
        auroc_raw = float("nan")
    auroc = max(auroc_raw, 1.0 - auroc_raw) if np.isfinite(auroc_raw) else float("nan")
    direction = (
        "higher_in_failed" if np.isfinite(auroc_raw) and auroc_raw >= 0.5
        else ("lower_in_failed" if np.isfinite(auroc_raw) else "n/a")
    )

    records.append({
        "feature": feat,
        "n_nonnull": int(mask.sum()),
        "n_failed_nonnull": int(len(pos)),
        "n_nonfailed_nonnull": int(len(neg)),
        "mw_p": p_mw,
        "auroc_raw": auroc_raw,
        "auroc": auroc,
        "direction": direction,
        "cohens_d": d,
        "pass_p": bool(np.isfinite(p_mw) and p_mw < ALPHA),
        "pass_auroc": bool(np.isfinite(auroc) and auroc >= AUROC_MIN),
    })

scr = pd.DataFrame(records)
scr["pass_screen"] = scr["pass_p"] & scr["pass_auroc"]
print(f"  Pass p<{ALPHA}: {int(scr['pass_p'].sum())}/{len(scr)}")
print(f"  Pass AUROC>={AUROC_MIN}: {int(scr['pass_auroc'].sum())}/{len(scr)}")
print(f"  Pass both: {int(scr['pass_screen'].sum())}/{len(scr)}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: correlation filter among screen survivors
#   Greedy by descending AUROC: keep a feature unless |Spearman r| >= 0.85
#   with an already-kept (higher-AUROC) feature.
# ─────────────────────────────────────────────────────────────────────────────
print(f"\nStep 2: correlation filter (|Spearman r| < {CORR_MAX})...")

survivors = (
    scr[scr["pass_screen"]]
    .sort_values("auroc", ascending=False)["feature"]
    .tolist()
)

kept, corr_partner = [], {}
for feat in survivors:
    clash = None
    for k in kept:
        r = spearman_abs_r(df[feat].values.astype(float),
                           df[k].values.astype(float))
        if r >= CORR_MAX:
            clash = k
            break
    if clash is None:
        kept.append(feat)
    else:
        corr_partner[feat] = clash
        print(f"  DROP {feat} (|r| >= {CORR_MAX} with higher-AUROC {clash})")

scr["pass_corr"] = scr["feature"].apply(
    lambda f: bool(f in kept)  # only screen survivors can pass
)
scr["corr_dropped_for"] = scr["feature"].map(corr_partner).fillna("")
print(f"  Survivors after correlation filter: {len(kept)}/{len(survivors)}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: LOVO stability — 34 leave-one-VIN-out Mann-Whitney re-screens
#   (computed for ALL features for reporting; filter applies to corr survivors)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\nStep 3: LOVO stability (p < {ALPHA} in >= {LOVO_STABLE_MIN}/{cfg.LOVO_FOLDS} re-screens)...")

assert len(df) == cfg.LOVO_FOLDS, (
    f"LOVO FOLD MISMATCH: matrix has {len(df)} VINs but cfg.LOVO_FOLDS={cfg.LOVO_FOLDS}; "
    "loop count and lovo_stable_frac denominator would diverge"
)
lovo_counts = {feat: 0 for feat in FEATURE_COLS}
for i in range(len(df)):
    keep_mask = np.ones(len(df), dtype=bool)
    keep_mask[i] = False
    l_sub = labels[keep_mask]
    for feat in FEATURE_COLS:
        vals = df[feat].values.astype(float)[keep_mask]
        m = np.isfinite(vals)
        v, l = vals[m], l_sub[m]
        p = mw_pvalue(v[l == 1], v[l == 0])
        if np.isfinite(p) and p < ALPHA:
            lovo_counts[feat] += 1

scr["lovo_n_stable"] = scr["feature"].map(lovo_counts)
scr["lovo_stable_frac"] = scr["lovo_n_stable"] / cfg.LOVO_FOLDS
scr["pass_lovo"] = scr["lovo_n_stable"] >= LOVO_STABLE_MIN


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: final pool — rank by AUROC, cap at 12
# ─────────────────────────────────────────────────────────────────────────────
pool = (
    scr[scr["pass_screen"] & scr["pass_corr"] & scr["pass_lovo"]]
    .sort_values("auroc", ascending=False)
    .head(POOL_CAP)["feature"]
    .tolist()
)
scr["in_pool"] = scr["feature"].isin(pool)

# Rank all features by AUROC (NaN last)
scr = scr.sort_values("auroc", ascending=False, na_position="last").reset_index(drop=True)
scr.insert(0, "rank", scr.index + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Save + report
# ─────────────────────────────────────────────────────────────────────────────
out_path = cfg.RESULTS / "V1_SM_feature_screening.csv"
out_path.parent.mkdir(parents=True, exist_ok=True)
scr.to_csv(out_path, index=False)

print()
print("=" * 78)
print("SCREENING SUMMARY (all 23 features, ranked by direction-agnostic AUROC)")
print("=" * 78)
print(f"{'Feature':<28} {'AUROC':>6} {'p_MW':>8} {'d':>7} {'LOVO':>6} "
      f"{'scr':>4} {'cor':>4} {'lov':>4} {'POOL':>5}")
print("-" * 78)
for _, r in scr.iterrows():
    print(f"{r['feature']:<28} {r['auroc']:>6.3f} {r['mw_p']:>8.4f} "
          f"{r['cohens_d']:>7.3f} {r['lovo_n_stable']:>3d}/{cfg.LOVO_FOLDS} "
          f"{'Y' if r['pass_screen'] else '.':>4} "
          f"{'Y' if r['pass_corr'] else '.':>4} "
          f"{'Y' if r['pass_lovo'] else '.':>4} "
          f"{'IN' if r['in_pool'] else '':>5}")

print()
print("=" * 78)
print(f"CANDIDATE POOL ({len(pool)} features, cap {POOL_CAP}) for subset search:")
print("=" * 78)
pool_rows = scr[scr["in_pool"]].sort_values("auroc", ascending=False)
for _, r in pool_rows.iterrows():
    print(f"  {r['feature']:<30} AUROC={r['auroc']:.3f}  ({r['direction']})")

assert len(pool) <= POOL_CAP, "POOL EXCEEDS CAP"
assert len(scr) == 23, "SCREENING CSV MUST CONTAIN ALL 23 FEATURES"

print()
print(f"Saved: {out_path}")
print(f"Screening table: {scr.shape[0]} rows x {scr.shape[1]} cols")
