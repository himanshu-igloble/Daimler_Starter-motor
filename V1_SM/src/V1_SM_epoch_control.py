"""
V1_SM_epoch_control.py  —  Plan §5: Calendar-Truncation Epoch-Leakage Control
BharatBenz Starter Motor predictive maintenance pipeline.

Plan §5 (binding): "Temporal honesty: NF trucks' final-window features use
their own t_end (2025-02..2026-02) — the classifier must not exploit
calendar-epoch differences. Add one control: re-run winner subset with NF
windows truncated to match failed-fleet calendar range; AUROC drop > 0.05
=> investigate epoch leakage."

Method:
  1. cutoff = max weekly 'week' across the 14 failed VINs (the failed-fleet
     calendar end; expect 2025-12-29 = VIN10_F_SM's last week).
  2. For each of the 20 NF VINs: truncate weekly rows to week <= cutoff and
     crank events to ts_start < cutoff + 7d (the same calendar week the
     failed fleet's last data falls in). The truncated t_end becomes the
     VIN's new anchor for days_before_t_end. NF VINs already ending before
     the cutoff are unchanged. Failed VINs unchanged (matrix values reused).
  3. Recompute the 4 winner features (vsi_std_ratio_30d, vsi_dominant_freq,
     vsi_range_trend, failed_crank_rate_last90) on truncated data, using
     definitions replicated 1:1 from V1_SM_features.py (line refs below).
     Replication is VALIDATED first: untruncated recompute must reproduce
     the existing feature matrix for ALL 34 VINs, and the recomputed
     days_before_t_end anchor must match the events parquet — else BLOCKED.
  4. 34-fold LOVO with the winner subset exactly as V1_SM_ridge_classifier.py
     (train-median imputation -> StandardScaler -> RidgeClassifier(alpha=1.0)
     -> sigmoid(decision_function)); classifier replication validated by
     reproducing the baseline AUROC from the untruncated matrix.
  5. Verdict: PASS if (baseline_auroc - truncated_auroc) <= 0.05,
     INVESTIGATE otherwise.

Produces: STARTER MOTOR/results/V1_SM_epoch_control.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import warnings
warnings.filterwarnings("ignore")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config import (directory has a space) ────────────────────────────────────
_spec = spec_from_file_location(
    "v1_sm_config",
    Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

import numpy as np
import pandas as pd
from scipy import stats, signal
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

DROP_THRESHOLD = 0.05   # plan §5: AUROC drop > 0.05 => INVESTIGATE
WINNER_FEATS = ["vsi_std_ratio_30d", "vsi_dominant_freq",
                "failed_crank_rate_last90", "vsi_range_trend"]


# ─────────────────────────────────────────────────────────────────────────────
# Feature definitions — replicated 1:1 from V1_SM_features.py
# ─────────────────────────────────────────────────────────────────────────────

def theil_sen(y: np.ndarray, x: np.ndarray):
    """V1_SM_features.py lines 37-42 (verbatim)."""
    mask = np.isfinite(y) & np.isfinite(x)
    if mask.sum() < 4:
        return None
    return float(stats.theilslopes(y[mask], x[mask]).slope)


def _masked_weekly(wk_vin: pd.DataFrame) -> pd.DataFrame:
    """V1_SM_features.py lines 85-97 (verbatim)."""
    wk = wk_vin[wk_vin["active_days"] >= 2].copy()
    wk = wk.sort_values("week").reset_index(drop=True)
    if wk.empty:
        wk["week_x"] = pd.Series(dtype=float)
        return wk
    first_week = wk["week"].iloc[0]
    wk["week_x"] = (wk["week"] - first_week).dt.days / 7.0
    return wk


def compute_winner_features(ev: pd.DataFrame, wk_raw: pd.DataFrame) -> dict:
    """
    The 4 winner features for one VIN.
    ev     : NON-ARTIFACT crank events for the VIN, with a valid
             days_before_t_end column (recomputed after truncation).
    wk_raw : raw weekly rows for the VIN (truncated where applicable).
    """
    wk = _masked_weekly(wk_raw)
    feat = {}

    # failed_crank_rate_last90 — V1_SM_features.py lines 207-219
    ev_succ = ev[ev["success"].notna()].copy()
    ev_succ["_succ"] = ev_succ["success"].astype(bool)
    ev90_succ = ev_succ[ev_succ["days_before_t_end"] <= 90]
    if len(ev90_succ) >= 10:
        feat["failed_crank_rate_last90"] = float((~ev90_succ["_succ"]).mean())
    else:
        feat["failed_crank_rate_last90"] = None

    n_wk = len(wk)

    # vsi_std_ratio_30d — V1_SM_features.py lines 247-258
    if n_wk >= 8:
        vdm_all = wk["vsi_drive_mean"].dropna().values
        std_all = np.std(vdm_all) if len(vdm_all) >= 2 else 0.0
        last4 = wk.tail(4)["vsi_drive_mean"].dropna().values
        std_last4 = np.std(last4) if len(last4) >= 2 else 0.0
        if std_all > 0 and std_last4 > 0:
            feat["vsi_std_ratio_30d"] = float(std_last4 / std_all)
        else:
            feat["vsi_std_ratio_30d"] = None
    else:
        feat["vsi_std_ratio_30d"] = None

    # vsi_dominant_freq — V1_SM_features.py lines 260-274
    if n_wk >= 10:
        vdm_series = wk["vsi_drive_mean"].copy()
        vdm_series = vdm_series.interpolate(method="linear", limit_direction="both")
        vdm_arr = vdm_series.values.astype(float)
        vdm_arr = vdm_arr - np.nanmean(vdm_arr)
        if not np.all(np.isfinite(vdm_arr)):
            vdm_arr = np.where(np.isfinite(vdm_arr), vdm_arr, 0.0)
        freqs, power = signal.periodogram(vdm_arr, fs=1.0)
        feat["vsi_dominant_freq"] = float(freqs[np.argmax(power)])
    else:
        feat["vsi_dominant_freq"] = None

    # vsi_range_trend — V1_SM_features.py lines 288-298
    last12 = wk.tail(12).copy()
    last12["_range"] = last12["vsi_drive_p95"] - last12["vsi_drive_p05"]
    valid_range = last12.dropna(subset=["_range"])
    if len(valid_range) >= 6:
        feat["vsi_range_trend"] = theil_sen(
            valid_range["_range"].values,
            valid_range["week_x"].values
        )
    else:
        feat["vsi_range_trend"] = None

    return feat


# ─────────────────────────────────────────────────────────────────────────────
# Classifier — replicated 1:1 from V1_SM_ridge_classifier.py
# ─────────────────────────────────────────────────────────────────────────────

def _sigmoid(x: np.ndarray) -> np.ndarray:
    """V1_SM_ridge_classifier.py lines 63-69 (verbatim)."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-np.abs(x))),
        np.exp(-np.abs(x)) / (1.0 + np.exp(-np.abs(x))),
    )


def _impute_train_medians(X_train: np.ndarray, X_test: np.ndarray):
    """V1_SM_ridge_classifier.py lines 72-81 (verbatim)."""
    X_tr, X_te = X_train.copy(), X_test.copy()
    for j in range(X_tr.shape[1]):
        med = np.nanmedian(X_tr[:, j])
        if np.isnan(med):
            med = 0.0
        X_tr[np.isnan(X_tr[:, j]), j] = med
        X_te[np.isnan(X_te[:, j]), j] = med
    return X_tr, X_te


def lovo_ridge(X_raw: np.ndarray, y: np.ndarray) -> np.ndarray:
    """V1_SM_ridge_classifier.py lines 84-97 (verbatim)."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("V1_SM EPOCH-LEAKAGE CONTROL (plan §5: calendar truncation)")
print("=" * 70)

mat = pd.read_csv(cfg.RESULTS / "V1_SM_feature_matrix.csv")
dq = pd.read_csv(cfg.RESULTS / "V1_SM_data_quality.csv")
with open(cfg.RESULTS / "V1_SM_ridge_spec.json") as f:
    spec = json.load(f)
assert spec["features"] == WINNER_FEATS or set(spec["features"]) == set(WINNER_FEATS), \
    f"winner subset changed: {spec['features']}"
WINNER_FEATS = spec["features"]          # honour spec ordering
baseline_auroc = float(spec["auroc"])

events_all = pd.read_parquet(cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet")
events_all["ts_start"] = pd.to_datetime(events_all["ts_start"])
# success cast — V1_SM_features.py lines 132-134
events_all["success"] = events_all["success"].map(
    lambda x: (bool(x) if x is not None and x != "None" else None)
)
events = events_all[events_all["artifact"] == False].copy()   # noqa: E712

weekly_files = list(cfg.CACHE_WEEKLY.glob("*.parquet"))
weekly_all = pd.concat([pd.read_parquet(f) for f in weekly_files], ignore_index=True)
weekly_all["week"] = pd.to_datetime(weekly_all["week"])

vins = mat["vin_label"].tolist()
failed_map = dict(zip(mat["vin_label"], mat["failed"]))
t_end_map = {r["vin_label"]: pd.to_datetime(r["t_end"]).normalize()
             for _, r in dq.iterrows()}

# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — cutoff = failed-fleet calendar end (max weekly week over 14 F VINs)
# ─────────────────────────────────────────────────────────────────────────────
f_weekly = weekly_all[weekly_all["failed"] == True]            # noqa: E712
cutoff_week = f_weekly["week"].max()                # week START of last failed week
cutoff_ts = cutoff_week + pd.Timedelta(days=7)      # events kept if ts_start < this
cutoff_t_end = cutoff_week + pd.Timedelta(days=6)   # truncated anchor date (week end)
f_last = f_weekly.groupby("vin_label")["week"].max()
print(f"\nStep 1 — cutoff (failed-fleet last weekly week): "
      f"{cutoff_week.date()}  (from {f_last.idxmax()})")

# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — VALIDATE replication: untruncated recompute must reproduce matrix
# ─────────────────────────────────────────────────────────────────────────────
print("\nStep 2 — replication validation (untruncated, all 34 VINs):")

# 2a. anchor recompute check: days_before_t_end from dq t_end must match the
#     events parquet (same day-floor arithmetic as V1_SM_crank_events.py 254-258)
anchor_mismatch = 0
for vin in vins:
    ev_v = events[events["vin_label"] == vin]
    recomputed = (t_end_map[vin] - ev_v["ts_start"].dt.normalize()).dt.days
    anchor_mismatch += int((recomputed.values != ev_v["days_before_t_end"].values).sum())
print(f"  anchor check: days_before_t_end recomputed from data-quality t_end — "
      f"{anchor_mismatch} mismatches across {len(events):,} non-artifact events")

# 2b. feature recompute check vs the shipped matrix
def _close(a, b) -> bool:
    a_nan = a is None or (isinstance(a, float) and np.isnan(a))
    b_nan = b is None or (isinstance(b, float) and np.isnan(b))
    if a_nan or b_nan:
        return a_nan and b_nan
    return np.isclose(float(a), float(b), rtol=1e-9, atol=1e-12)

feat_mismatches = []
for vin in vins:
    ev_v = events[events["vin_label"] == vin]
    wk_v = weekly_all[weekly_all["vin_label"] == vin]
    rec = compute_winner_features(ev_v, wk_v)
    row = mat[mat["vin_label"] == vin].iloc[0]
    for ft in WINNER_FEATS:
        mv = row[ft] if pd.notna(row[ft]) else None
        if not _close(rec[ft], mv):
            feat_mismatches.append((vin, ft, rec[ft], mv))
print(f"  feature check: 34 VINs x 4 winner features recomputed — "
      f"{len(feat_mismatches)} mismatches vs V1_SM_feature_matrix.csv")

# 2c. classifier replication: baseline LOVO AUROC must reproduce the spec
y = mat["failed"].astype(int).values
X_base = mat[WINNER_FEATS].values.astype(float)
probs_base = lovo_ridge(X_base, y)
auroc_base_recomputed = float(roc_auc_score(y, probs_base))
clf_ok = abs(round(auroc_base_recomputed, 4) - baseline_auroc) < 1e-9
print(f"  classifier check: baseline LOVO AUROC recomputed = "
      f"{auroc_base_recomputed:.4f} vs spec {baseline_auroc:.4f} "
      f"({'match' if clf_ok else 'MISMATCH'})")

if anchor_mismatch or feat_mismatches or not clf_ok:
    for m in feat_mismatches[:10]:
        print(f"    MISMATCH {m[0]} {m[1]}: recomputed={m[2]} matrix={m[3]}")
    print("\nBLOCKED: replication does not reproduce shipped artifacts — "
          "epoch control NOT run.")
    sys.exit(2)
print("  replication VALIDATED — exact reproduction of matrix, anchors, AUROC.")

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — truncate NF VINs to the failed-fleet calendar range, recompute
# ─────────────────────────────────────────────────────────────────────────────
print(f"\nStep 3 — NF truncation to week <= {cutoff_week.date()} "
      f"(events ts_start < {cutoff_ts.date()}):")

mat_trunc = mat.copy()
trunc_summary = []
for vin in vins:
    if failed_map[vin] == 1:
        continue   # failed VINs keep their shipped matrix values
    wk_v = weekly_all[weekly_all["vin_label"] == vin]
    ev_v = events[events["vin_label"] == vin]

    wk_t = wk_v[wk_v["week"] <= cutoff_week].copy()
    ev_t = ev_v[ev_v["ts_start"] < cutoff_ts].copy()
    weeks_removed = len(wk_v) - len(wk_t)
    events_removed = len(ev_v) - len(ev_t)

    # new anchor: truncated t_end (telemetry continues past the cutoff for
    # truncated trucks, so the truncated series ends at the cutoff week's end;
    # untruncated trucks keep their own t_end)
    new_t_end = min(t_end_map[vin], cutoff_t_end)
    # recompute days_before_t_end with the original day-floor arithmetic
    # (V1_SM_crank_events.py lines 254-258, validated in step 2a)
    ev_t["days_before_t_end"] = (new_t_end - ev_t["ts_start"].dt.normalize()).dt.days

    rec = compute_winner_features(ev_t, wk_t)
    for ft in WINNER_FEATS:
        mat_trunc.loc[mat_trunc["vin_label"] == vin, ft] = (
            np.nan if rec[ft] is None else rec[ft])

    trunc_summary.append({
        "vin_label": vin,
        "original_t_end": str(t_end_map[vin].date()),
        "truncated": bool(weeks_removed > 0 or events_removed > 0),
        "weeks_removed": int(weeks_removed),
        "events_removed": int(events_removed),
        "new_last_week": str(wk_t["week"].max().date()) if len(wk_t) else None,
    })

n_truncated = sum(1 for r in trunc_summary if r["truncated"])
for r in trunc_summary:
    tag = (f"truncated: -{r['weeks_removed']} weeks, -{r['events_removed']} events"
           if r["truncated"] else "unchanged (ends before cutoff)")
    print(f"  {r['vin_label']:<12} t_end {r['original_t_end']}  {tag}")
print(f"  => {n_truncated}/20 NF VINs truncated; 14 failed VINs untouched")

# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — LOVO on the truncated matrix, winner subset
# ─────────────────────────────────────────────────────────────────────────────
X_trunc = mat_trunc[WINNER_FEATS].values.astype(float)
probs_trunc = lovo_ridge(X_trunc, y)
truncated_auroc = float(roc_auc_score(y, probs_trunc))
drop = baseline_auroc - truncated_auroc
verdict = "PASS" if drop <= DROP_THRESHOLD else "INVESTIGATE"

print(f"\nStep 4 — results:")
print(f"  baseline AUROC (NF own t_end):        {baseline_auroc:.4f}")
print(f"  truncated AUROC (NF cut to {cutoff_week.date()}): {truncated_auroc:.4f}")
print(f"  drop: {drop:+.4f}   threshold: {DROP_THRESHOLD}")
print(f"  VERDICT: {verdict}" + (
    "  — no evidence the classifier exploits calendar-epoch differences"
    if verdict == "PASS" else
    "  — AUROC drop exceeds 0.05: investigate epoch leakage before deployment"))

# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — write JSON
# ─────────────────────────────────────────────────────────────────────────────
out = {
    "control": "calendar-truncation epoch-leakage control (V1_SM plan §5)",
    "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "cutoff_week": str(cutoff_week.date()),
    "cutoff_source": f"max weekly week across 14 failed VINs ({f_last.idxmax()})",
    "truncation_rule": (
        "NF weekly rows kept if week <= cutoff_week; NF crank events kept if "
        "ts_start < cutoff_week + 7d; new anchor t_end = min(own t_end, "
        "cutoff_week + 6d); days_before_t_end recomputed with original "
        "day-floor arithmetic; failed VINs and NF VINs ending before the "
        "cutoff unchanged"),
    "replication_validation": {
        "anchor_mismatches": int(anchor_mismatch),
        "feature_mismatches_34x4": len(feat_mismatches),
        "baseline_auroc_recomputed": round(auroc_base_recomputed, 4),
        "status": "VALIDATED",
    },
    "winner_features": WINNER_FEATS,
    "n_nf_truncated": n_truncated,
    "nf_truncation_summary": trunc_summary,
    "baseline_auroc": round(baseline_auroc, 4),
    "truncated_auroc": round(truncated_auroc, 4),
    "auroc_drop": round(drop, 4),
    "drop_threshold": DROP_THRESHOLD,
    "verdict": verdict,
}
out_path = cfg.RESULTS / "V1_SM_epoch_control.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nSaved: {out_path}")
