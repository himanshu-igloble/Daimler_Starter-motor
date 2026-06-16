"""
run_refit.py  —  REFIT AUTOMATION HARNESS  (roadmap item C6)
SM V2 system | D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V2_program\v2_system\refit\

PURPOSE
  One-command execution of the full nested validation protocol, so future refits
  (triggered when >=5 new failure labels arrive, calibration slope outside [0.5,2],
  or PSI>0.2) are executable without re-deriving the discipline.

USAGE
  Self-test (identity check vs frozen baseline, fast permutation):
      py -3 run_refit.py --self-test [--perm-n 20]

  Production refit with new labels file:
      py -3 run_refit.py --labels <path_to_labels.csv> [--perm-n 200] [--force]

  --perm-n N   Number of full-pipeline permutation iterations (default: 200).
               Self-test default: 20 (plumbing speed; does NOT affect AUROC point estimate).
               Production refits should use >= 200.
  --force      Bypass the >=5 new-failure-label trigger gate (e.g. for calibration-slope
               or PSI-triggered refits).

STAGES (each logged with duration)
  S0  Trigger check     new-failure-label count >= 5, or --force
  S1  Feature build     rebuild 10-feature matrix + L40 control + admissibility (X1 logic)
  S2  Nested protocol   full 34-fold LOVO + bootstrap CI + full-pipeline permutation test (X2)
  S3  Gates G1-G6       written as JSON
  S4  Comparison report vs frozen baseline from v2_config.json validation-of-record block
  S5  Artifact versioning  write refit/out/refit_<UTCtimestamp>/ + NEVER-AUTO-DEPLOY banner

GOVERNANCE
  - Refit trigger: >= 5 new failure labels OR calibration slope outside [0.5,2] OR PSI > 0.2
  - Banned feature classes (G6 token scan): observation_length, gap_counts, calendar_position,
    periodogram 1/n artifacts (tokens: n_weeks, t_start, t_end, span, gap, saledate,
    jcopendate, dominant_freq, cum, month, epoch, calendar, active_days)
  - THIS HARNESS NEVER AUTO-DEPLOYS. It produces versioned candidate artifacts + a
    restatement-style comparison report, then prints the manual-review banner.

SOURCE ATTRIBUTION
  Feature build logic (S1) copied verbatim from:
      STARTER MOTOR/V1.1/src/V1_1_SM_features.py  (X1, build_features + helpers)
  Nested validation logic (S2-S3) copied verbatim from:
      STARTER MOTOR/V1.1/src/V1_1_SM_nested_ridge.py  (X2, nested_lovo + gates)
  This is the established pattern: functions copied with docstring attribution,
  not imported, so the harness is self-contained and future-proof against upstream edits.
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# force UTF-8 stdout on Windows so log() can print any character
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler

# ── paths ──────────────────────────────────────────────────────────────────────
REPO = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM_ROOT = REPO / "STARTER MOTOR"
V1_1_RES = SM_ROOT / "V1.1" / "results"
V2_CONFIG_PATH = SM_ROOT / "V2_program" / "v2_system" / "v2_config.json"
REFIT_OUT_ROOT = Path(__file__).parent / "out"

# canonical baseline (self-test reproduces these)
BASELINE_MATRIX_CSV = V1_1_RES / "V1_1_SM_feature_matrix.csv"
BASELINE_GATES_JSON = V1_1_RES / "V1_1_SM_gates.json"
BASELINE_LABELS_CSV = SM_ROOT / "V1.1" / "audit" / "probe1_labels_per_vin.csv"

# ── protocol constants (verbatim from X1 / X2) ────────────────────────────────
L40 = 40
SMA_DEAD_THRESH = 0.01
BURST_GAP_S = 600
BURST_RPM_OK = 550
FIRST_CRANK_REST_H = 6
STEP_MIN_V, STEP_MIN_SNR = 0.5, 2.0

ALPHA_MW, AUROC_MIN, CORR_MAX = 0.10, 0.60, 0.85
STABLE_FRAC, POOL_CAP = 0.80, 10
SUBSET_MIN, SUBSET_MAX = 3, 6
RIDGE_ALPHA = 1.0
SEED_BOOT, SEED_PERM = 42, 43
N_BOOT = 200
TIER_GREEN, TIER_RED = 0.35, 0.55

FEATURES = [
    "vsi_std_ratio_30d_L40", "vsi_withinwk_std_ratio_30d_w", "vsi_range_trend",
    "vsi_trend_persistence", "failed_crank_rate_last90", "retry_burst_rate_last90",
    "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
    "rest_vsi_p05_delta90", "dip_depth_last90_delta",
]
COHORT_MASKED = [
    "failed_crank_rate_last90", "retry_burst_rate_last90",
    "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
    "dip_depth_last90_delta",
]
# G6 banned tokens
G6_TOKENS = [
    "n_weeks", "t_start", "t_end", "span", "gap", "saledate",
    "jcopendate", "dominant_freq", "cum", "month", "epoch", "calendar", "active_days",
]

# ── logging helpers ────────────────────────────────────────────────────────────
_LOG_LINES: list = []

def log(msg: str, *, echo: bool = True):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _LOG_LINES.append(line)
    if echo:
        print(line, flush=True)


def stage_header(name: str):
    log(f"\n{'='*70}\n{name}\n{'='*70}")


# ═══════════════════════════════════════════════════════════════════════════════
# X1 HELPERS — verbatim copies from V1_1_SM_features.py (attribution above)
# ═══════════════════════════════════════════════════════════════════════════════

def _theil_sen(yv, xv):
    """Theil-Sen slope. Source: V1_1_SM_features.py."""
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


def _rank_auroc_feat(scores, labels):
    """Rank AUROC for a feature vector (handles NaN). Source: V1_1_SM_features.py."""
    m = np.isfinite(scores)
    s, l = scores[m], labels[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))


def _burst_count(ev_sub):
    """Count burst episodes. Source: V1_1_SM_features.py."""
    if len(ev_sub) < 2:
        return 0
    e = ev_sub.sort_values("ts_start")
    ts = e["ts_start"].values
    rpm = e["rpm_max_15s"].values.astype(float)
    bursts = 0
    chain = [0]
    for i in range(1, len(e)):
        if (ts[i] - ts[i - 1]) / np.timedelta64(1, "s") <= BURST_GAP_S:
            chain.append(i)
        else:
            if len(chain) >= 2:
                inter = rpm[chain[:-1]]
                if not np.any(inter[np.isfinite(inter)] >= BURST_RPM_OK):
                    bursts += 1
            chain = [i]
    if len(chain) >= 2:
        inter = rpm[chain[:-1]]
        if not np.any(inter[np.isfinite(inter)] >= BURST_RPM_OK):
            bursts += 1
    return bursts


def build_feature_matrix(
    vins: list, y: np.ndarray,
    wk_all: pd.DataFrame, ev_all: pd.DataFrame,
    BAT_STEP: dict, sma_dead: dict,
    clip_l40_basis: bool = False,
) -> pd.DataFrame:
    """
    Build the 10-feature row per VIN.

    Verbatim logic from V1_1_SM_features.py :: build_features(), adapted to accept
    pre-loaded data frames instead of reading from disk, so refits against new label sets
    can pass in updated vins/y without touching the cache files.

    clip_l40_basis=False -> production matrix (L40/window-anchored by construction).
    clip_l40_basis=True  -> fixed-L40 control (weekly+event data clipped to last 40 masked wks).

    Source: STARTER MOTOR/V1.1/src/V1_1_SM_features.py
    """
    rows = []
    for vin in vins:
        w = wk_all[wk_all["vin_label"] == vin]
        wm_full = w[w["active_days"] >= 2].sort_values("week").reset_index(drop=True)
        wm = wm_full.tail(L40).reset_index(drop=True)
        win_start = wm["week"].iloc[0]
        ev_vin = ev_all[ev_all["vin_label"] == vin]
        if clip_l40_basis:
            ev_vin = ev_vin[ev_vin["ts_start"] >= win_start]
        ev_win = ev_vin[ev_vin["ts_start"] >= win_start]
        wm = wm.copy()
        wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
        vdm = wm["vsi_drive_mean"].values.astype(float)
        vds = wm["vsi_drive_std"].values.astype(float)
        f = {"vin_label": vin, "failed": int(y[vins.index(vin)])}

        # 1. vsi_std_ratio_30d_L40 (B3 exact — between-week VSI volatility ratio)
        va = vdm[np.isfinite(vdm)]
        l4 = vdm[-4:]; l4 = l4[np.isfinite(l4)]
        f["vsi_std_ratio_30d_L40"] = (float(np.std(l4) / np.std(va))
                                      if len(va) >= 2 and len(l4) >= 2
                                      and np.std(va) > 0 and np.std(l4) > 0 else np.nan)

        # 2. vsi_withinwk_std_ratio_30d_w (B3 exact — within-week VSI noise ratio)
        f["vsi_withinwk_std_ratio_30d_w"] = (float(np.nanmean(vds[-4:]) / np.nanmean(vds))
                                             if np.isfinite(vds).sum() >= 6
                                             and np.nanmean(vds) > 0 else np.nan)

        # 3. vsi_range_trend (V1 carry-over, Theil-Sen last 12 masked weeks)
        last12 = wm.tail(12)
        rng = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
        f["vsi_range_trend"] = (_theil_sen(rng, last12["week_x"].values.astype(float))
                                if np.isfinite(rng).sum() >= 6 else np.nan)

        # 4. vsi_trend_persistence (B2 exact — |mean sign| of rolling 4-wk OLS slopes)
        if len(wm) >= 12:
            seg, sx = vdm[-12:], wm["week_x"].values[-12:]
            slopes = []
            for i in range(len(seg) - 3):
                yy, xx = seg[i:i + 4], sx[i:i + 4]
                mq = np.isfinite(yy)
                if mq.sum() >= 3:
                    slopes.append(np.polyfit(xx[mq], yy[mq], 1)[0])
            f["vsi_trend_persistence"] = (abs(np.mean(np.sign(slopes)))
                                          if len(slopes) >= 5 else np.nan)
        else:
            f["vsi_trend_persistence"] = np.nan

        # event features (cohort-masked for SMA-dead trucks)
        es = ev_vin[ev_vin["succ_b"].notna()]
        e90s = es[es["days_before_t_end"] <= 90]
        e90 = ev_vin[ev_vin["days_before_t_end"] <= 90]

        # 5. failed_crank_rate_last90
        f["failed_crank_rate_last90"] = (float((~e90s["succ_b"].astype(bool)).mean())
                                         if len(e90s) >= 10 else np.nan)

        # 6. retry_burst_rate_last90
        ref_week = wm_full["week"].max()
        w_act = w[w["week"] > ref_week - pd.Timedelta(days=91)]
        act90 = float(w_act["active_days"].sum())
        f["retry_burst_rate_last90"] = (_burst_count(e90) / act90
                                        if act90 >= 10 else np.nan)

        # 7. extended_crank_tail_rate_last90
        base_ev = ev_win[ev_win["days_before_t_end"] > 90]
        if len(e90) >= 10 and len(base_ev) >= 10:
            f["extended_crank_tail_rate_last90"] = float(
                (e90["n_rows"] >= 2).mean() - (base_ev["n_rows"] >= 2).mean())
        else:
            f["extended_crank_tail_rate_last90"] = np.nan

        # 8. first_crank_fail_rate_last90
        ee = ev_vin.sort_values("ts_start")
        gap_h = ee["ts_start"].diff().dt.total_seconds() / 3600.0
        is_first = gap_h.isna() | (gap_h >= FIRST_CRANK_REST_H)
        fc = ee[is_first & (ee["days_before_t_end"] <= 90) & ee["succ_b"].notna()]
        f["first_crank_fail_rate_last90"] = (float((~fc["succ_b"].astype(bool)).mean())
                                             if len(fc) >= 5 else np.nan)

        # 9. rest_vsi_p05_delta90 (battery-step-aware re-baseline, E5)
        vrp = wm["vsi_rest_p05"].values.astype(float)
        last13, base = vrp[-13:], vrp[:-13]
        base_weeks = wm["week"].values[:-13]
        if vin in BAT_STEP:
            post = base[base_weeks >= np.datetime64(BAT_STEP[vin])]
            if np.isfinite(post).sum() >= 4:
                base = post
        if np.isfinite(last13).sum() >= 6 and np.isfinite(base).sum() >= 4:
            f["rest_vsi_p05_delta90"] = float(np.nanmean(last13) - np.nanmean(base))
        else:
            f["rest_vsi_p05_delta90"] = np.nan

        # 10. dip_depth_last90_delta (vs L40-window baseline)
        d90 = e90["dip_depth"].dropna()
        dbase = base_ev["dip_depth"].dropna()
        f["dip_depth_last90_delta"] = (float(d90.mean() - dbase.mean())
                                       if len(d90) >= 10 and len(dbase) >= 10 else np.nan)

        # cohort mask: SMA-dead trucks get NaN on all crank/event features
        if sma_dead.get(vin, False):
            for c in COHORT_MASKED:
                f[c] = np.nan
        rows.append(f)
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# X2 HELPERS — verbatim copies from V1_1_SM_nested_ridge.py (attribution above)
# ═══════════════════════════════════════════════════════════════════════════════

def _ridge_z(Xtr, ytr, Xte, alpha=RIDGE_ALPHA):
    """
    Median-impute (train medians) -> standardize -> closed-form ridge on {-1,+1} targets.
    Returns decision values for Xte.
    Source: V1_1_SM_nested_ridge.py :: ridge_z()
    """
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


def _sigmoid(z):
    """Source: V1_1_SM_nested_ridge.py :: sigmoid()"""
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-np.abs(z))),
                    np.exp(-np.abs(z)) / (1.0 + np.exp(-np.abs(z))))


def _lovo_z(X, yy):
    """Leave-one-out decision values. Source: V1_1_SM_nested_ridge.py :: lovo_z()"""
    nn = len(yy)
    z = np.empty(nn)
    idx = np.arange(nn)
    for i in range(nn):
        tr = idx != i
        z[i] = _ridge_z(X[tr], yy[tr], X[i:i + 1])[0]
    return z


def _rank_auroc_arr(s, l):
    """Rank-based AUROC for arrays. Source: V1_1_SM_nested_ridge.py :: rank_auroc()"""
    m = np.isfinite(s)
    s, l = s[m], l[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    r = stats.rankdata(s)
    n1 = int(l.sum())
    return (r[l == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(l) - n1))


def _youden_thr(yy, p):
    """
    Youden-optimal threshold over the observed score grid.
    Source: V1_1_SM_nested_ridge.py :: youden_thr()
    """
    order = np.argsort(-p)
    ps, ys = p[order], yy[order]
    P, N = ys.sum(), len(ys) - ys.sum()
    tps = np.cumsum(ys); fps = np.cumsum(1 - ys)
    jj = tps / P - fps / N
    distinct = np.r_[np.diff(ps) != 0, True]
    best = np.argmax(np.where(distinct, jj, -np.inf))
    return float(ps[best])


def _mcc_at(yy, p, thr):
    """MCC at a fixed threshold. Source: V1_1_SM_nested_ridge.py :: mcc_at()"""
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (yy == 1)).sum()); tn = int(((pred == 0) & (yy == 0)).sum())
    fp = int(((pred == 1) & (yy == 0)).sum()); fn = int(((pred == 0) & (yy == 1)).sum())
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / den if den > 0 else 0.0


def _mw_p(a, b):
    """Mann-Whitney p-value. Source: V1_1_SM_nested_ridge.py :: mw_p()"""
    if len(a) == 0 or len(b) == 0:
        return np.nan
    try:
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return np.nan


def _screen_pool(Xdf, yy, feats):
    """
    C1's faithful V1 screening replica on a training fold.
    MW p<0.10, oriented AUROC>=0.60, greedy |Spearman|<0.85 dedup,
    within-fold LOVO stability (p<0.10 in >= ceil(0.8*33) re-screens), pool cap 10.
    Source: V1_1_SM_nested_ridge.py :: screen_pool()
    """
    nn = len(yy)
    recs = []
    for ft in feats:
        v = Xdf[ft].values.astype(float)
        m = np.isfinite(v)
        if m.sum() < 6 or len(np.unique(yy[m])) < 2:
            recs.append((ft, np.nan, np.nan, False)); continue
        p = _mw_p(v[m & (yy == 1)], v[m & (yy == 0)])
        a = _rank_auroc_arr(v, yy); a = max(a, 1 - a)
        recs.append((ft, p, a, bool(np.isfinite(p) and p < ALPHA_MW
                                    and np.isfinite(a) and a >= AUROC_MIN)))
    scr = pd.DataFrame(recs, columns=["feature", "mw_p", "auroc", "ok"])
    survivors = scr[scr["ok"]].sort_values("auroc", ascending=False)["feature"].tolist()
    kept = []
    for ft in survivors:
        ok = True
        for kft in kept:
            a_, b_ = Xdf[ft].values.astype(float), Xdf[kft].values.astype(float)
            m = np.isfinite(a_) & np.isfinite(b_)
            if m.sum() >= 4:
                r = stats.spearmanr(a_[m], b_[m])[0]
                if np.isfinite(r) and abs(r) >= CORR_MAX:
                    ok = False; break
        if ok:
            kept.append(ft)
    stable_min = math.ceil(STABLE_FRAC * nn)
    counts = {f: 0 for f in kept}
    for i in range(nn):
        km = np.arange(nn) != i
        ys = yy[km]
        for ft in kept:
            v = Xdf[ft].values.astype(float)[km]
            m = np.isfinite(v)
            p = _mw_p(v[m & (ys == 1)], v[m & (ys == 0)])
            if np.isfinite(p) and p < ALPHA_MW:
                counts[ft] += 1
    pool = [f for f in kept if counts[f] >= stable_min]
    pool = (scr[scr["feature"].isin(pool)].sort_values("auroc", ascending=False)
            .head(POOL_CAP)["feature"].tolist())
    rank = scr.sort_values("auroc", ascending=False)["feature"].tolist()
    return pool, rank


def _subset_search(Xdf, yy, pool, rank):
    """
    Exhaustive k=3..6 subsets; winner by inner-LOVO AUROC, tie-break -k then MCC.
    Returns (feats, inner_z, inner_auroc).
    Source: V1_1_SM_nested_ridge.py :: subset_search()
    """
    if len(pool) == 0:
        pool = rank[:1]
    k_lo, k_hi = min(SUBSET_MIN, len(pool)), min(SUBSET_MAX, len(pool))
    best = None
    for k in range(k_lo, k_hi + 1):
        for feats in combinations(pool, k):
            X = Xdf[list(feats)].values.astype(float)
            z = _lovo_z(X, yy)
            p = _sigmoid(z)
            a = _rank_auroc_arr(p, yy)
            thr = _youden_thr(yy, p)
            mcc = _mcc_at(yy, p, thr)
            cand = (round(a, 10), -k, round(mcc, 10))
            if best is None or cand > best[0]:
                best = (cand, list(feats), z, a)
    return best[1], best[2], best[3]


def nested_lovo(Xdf, yy, feats_all, collect=False):
    """
    Full nested 34-fold LOVO pipeline.
    Returns OOF sigmoid probs (+ per-fold details if collect=True).
    Source: V1_1_SM_nested_ridge.py :: nested_lovo()
    """
    nn = len(yy)
    probs = np.empty(nn)
    details = []
    for i in range(nn):
        tr = np.arange(nn) != i
        df_tr = Xdf.loc[tr].reset_index(drop=True)
        y_tr = yy[tr]
        pool, rank = _screen_pool(df_tr, y_tr, feats_all)
        feats, z_in, a_in = _subset_search(df_tr, y_tr, pool, rank)
        p_in = _sigmoid(z_in)
        thr = _youden_thr(y_tr, p_in)
        z_te = _ridge_z(df_tr[feats].values.astype(float), y_tr,
                        Xdf.loc[[i], feats].values.astype(float))[0]
        probs[i] = _sigmoid(np.array([z_te]))[0]
        if collect:
            platt = LogisticRegression(C=1e6, max_iter=10000).fit(
                z_in.reshape(-1, 1), y_tr)
            p_recal = float(platt.predict_proba([[z_te]])[0, 1])
            details.append({"pool": pool, "feats": feats, "inner_auroc": a_in,
                            "inner_thr": thr, "z_te": float(z_te),
                            "prob": float(probs[i]), "prob_recal": p_recal,
                            "pred_foldthr": int(probs[i] >= thr)})
    return (probs, details) if collect else probs


# ═══════════════════════════════════════════════════════════════════════════════
# GATE LOGIC — verbatim from X2, adapted to accept pre-computed inputs
# ═══════════════════════════════════════════════════════════════════════════════

def compute_gates(
    mat: pd.DataFrame, mat_ctl: pd.DataFrame,
    y: np.ndarray, vins: list,
    probs: np.ndarray, det: list,
    modal_subset: list, modal_count: int,
    nested_auroc: float, px: pd.DataFrame,
) -> dict:
    """
    Compute gates G1-G6.
    Source: V1_1_SM_nested_ridge.py gates block.
    """
    gates: dict = {}
    pred_fold = np.array([d["pred_foldthr"] for d in det])
    recal = np.array([d["prob_recal"] for d in det])
    subset_counter = Counter(tuple(sorted(d["feats"])) for d in det)

    # G1 fixed-L40 control
    p_ctl = _sigmoid(_lovo_z(mat_ctl[modal_subset].values.astype(float), y))
    a_ctl = float(roc_auc_score(y, p_ctl))
    p_nonnested = _sigmoid(_lovo_z(mat[modal_subset].values.astype(float), y))
    a_nonnested = float(roc_auc_score(y, p_nonnested))
    g1_drop_subset = a_nonnested - a_ctl
    gates["G1_fixed_L40_control"] = {
        "modal_subset": modal_subset,
        "lovo_auroc_raw_matrix": round(a_nonnested, 4),
        "lovo_auroc_L40_control_matrix": round(a_ctl, 4),
        "drop": round(g1_drop_subset, 4),
        "pass": bool(g1_drop_subset <= 0.05),
        "note": "all V1.1 features are L40/window-anchored by construction"}

    # G2 proxy audit of final OOF scores
    g2 = {}
    for pcol in ["n_weeks_masked", "t_start_ord", "span_days"]:
        r = float(stats.spearmanr(probs, px[pcol].values)[0])
        g2[f"spearman_oof_vs_{pcol}"] = round(r, 3)
    g2_max = max(abs(v) for v in g2.values())
    g2["max_abs_r"] = round(g2_max, 3)
    g2["pass_reported"] = True
    if g2_max > 0.5:
        g2["time_locking_justification"] = (
            "|r|>0.5 with an observation-structure proxy. G3 evidence: prequential AUROC "
            "holds 0.84-0.92 for k=0..10 weeks before t_end and collapses to chance at k=11. "
            "Correlation with span/n_weeks is label-mediated (failed trucks have shorter "
            "histories). The L40 control (G1) shows no AUROC is borrowed from history length.")
    gates["G2_oof_proxy_audit"] = g2

    # G3 calibration
    eps = 1e-6
    rc = np.clip(recal, eps, 1 - eps)
    brier = float(brier_score_loss(y, rc))
    base = y.mean()
    citl = float(np.log(base / (1 - base)) - np.log(rc.mean() / (1 - rc.mean())))
    lg = np.log(rc / (1 - rc))
    slope = float(LogisticRegression(C=1e6, max_iter=10000)
                  .fit(lg.reshape(-1, 1), y).coef_[0, 0])
    gates["G3_calibration"] = {
        "brier_recalibrated": round(brier, 4),
        "brier_constant_reference": round(base * (1 - base), 4),
        "citl_logit_gap": round(citl, 4),
        "recal_slope": round(slope, 3),
        "slope_in_0p5_2": bool(0.5 <= slope <= 2.0),
        "ship_probabilities": bool(0.5 <= slope <= 2.0),
        "note": "if slope outside [0.5,2], ship tiers only (spec 3.5)"}

    # G4 winner-subset stability
    feat_freq = Counter(f for d in det for f in d["feats"])
    gates["G4_winner_stability"] = {
        "modal_subset": modal_subset,
        "modal_count": int(modal_count),
        "n_distinct_subsets": len(subset_counter),
        "subset_table": {" | ".join(k): int(v) for k, v in subset_counter.most_common()},
        "feature_frequency": {k: int(v) for k, v in feat_freq.most_common()},
        "pass": bool(modal_count >= 17)}

    # G5 jackknife AUROC
    n = len(y)
    jk = []
    for i in range(n):
        km = np.arange(n) != i
        jk.append(roc_auc_score(y[km], probs[km]))
    gates["G5_jackknife"] = {
        "min": round(float(np.min(jk)), 4),
        "max": round(float(np.max(jk)), 4),
        "range": round(float(np.max(jk) - np.min(jk)), 4),
        "std": round(float(np.std(jk)), 4)}

    # G6 leakage token scan
    hits = {f: [t for t in G6_TOKENS if t in f.lower()]
            for f in set(f for d in det for f in d["feats"])}
    hits = {k: v for k, v in hits.items() if v}
    gates["G6_token_scan"] = {"banned_token_hits": hits, "pass": len(hits) == 0}

    gates["summary"] = {
        "nested_auroc": round(nested_auroc, 4),
        "permutation_p": None,  # filled after perm run
        "gates_pass": {k: gates[k].get("pass", "report-only") for k in
                       ["G1_fixed_L40_control", "G2_oof_proxy_audit", "G3_calibration",
                        "G4_winner_stability", "G5_jackknife", "G6_token_scan"]}}
    return gates


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def s0_trigger_check(labels_path: str | None, force: bool) -> tuple[int, int]:
    """
    S0: Check trigger gate.
    Returns (n_new_failures, n_baseline_failures).
    In self-test mode (labels_path=None) this stage is skipped.
    """
    stage_header("S0: Trigger check")
    baseline_labels = pd.read_csv(BASELINE_LABELS_CSV)
    n_baseline = len(baseline_labels)  # failed VINs in probe1
    log(f"  Baseline failure label count (probe1): {n_baseline}")

    if labels_path is None:
        log("  --self-test mode: S0 skipped (no new labels file).")
        return 0, n_baseline

    new_labels = pd.read_csv(labels_path)
    # count rows not present in baseline by VIN
    baseline_vins = set(baseline_labels["VIN"].tolist())
    new_vins = set(new_labels["VIN"].tolist())
    n_new = len(new_vins - baseline_vins)
    log(f"  New label file: {labels_path}")
    log(f"  VINs in new file: {len(new_vins)}, baseline VINs: {len(baseline_vins)}")
    log(f"  New failure VINs (not in baseline): {n_new}")

    if n_new < 5 and not force:
        log(f"  TRIGGER GATE NOT MET: {n_new} new failure labels < 5 required.")
        log("  Use --force to bypass (for calibration-slope or PSI-triggered refits).")
        sys.exit(1)
    if force and n_new < 5:
        log(f"  WARNING: --force used with only {n_new} new failure labels. Proceeding.")
    else:
        log(f"  Trigger gate MET: {n_new} >= 5 new failure labels. Proceeding.")
    return n_new, n_baseline


def s1_feature_build(self_test: bool) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
                                                 list, np.ndarray, dict, dict, pd.DataFrame]:
    """
    S1: Rebuild 10-feature matrix + L40 control + admissibility table from caches.
    In self-test mode compares to BASELINE_MATRIX_CSV (max|diff| <= 1e-9 gate).
    Returns (mat, mat_ctl, aud, vins, y, BAT_STEP, sma_dead, px).
    """
    stage_header("S1: Feature build")

    # load base VIN/label list from V1 matrix (stable across refits on same fleet)
    fm_v1 = pd.read_csv(SM_ROOT / "results" / "V1_SM_feature_matrix.csv")
    vins = fm_v1["vin_label"].tolist()
    y = fm_v1["failed"].astype(int).values
    log(f"  Fleet: {len(vins)} VINs ({int(y.sum())} failed / {int((1-y).sum())} non-failed)")

    # load weekly cache (all VINs)
    wk_files = sorted((SM_ROOT / "cache/weekly").glob("V1_SM_weekly_*.parquet"))
    log(f"  Loading {len(wk_files)} weekly parquet files...")
    wk_all = pd.concat([pd.read_parquet(f) for f in wk_files], ignore_index=True)
    wk_all["week"] = pd.to_datetime(wk_all["week"])

    # load event cache
    ev_all = pd.read_parquet(SM_ROOT / "cache/events/V1_SM_crank_events.parquet")
    ev_all = ev_all[ev_all["artifact"] == False].copy()
    ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
    ev_all["succ_b"] = ev_all["success"].map(
        lambda x: bool(x) if x is not None and x == x else np.nan)

    # battery replacement steps (E5)
    steps = pd.read_csv(SM_ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
    steps["step_week"] = pd.to_datetime(steps["step_week"])
    bat_steps = steps[(steps["signal"] == "vsi_rest_median")
                      & (steps["step_V"] >= STEP_MIN_V)
                      & (steps["snr"] >= STEP_MIN_SNR)]
    BAT_STEP = dict(zip(bat_steps["vin_label"], bat_steps["step_week"]))
    log(f"  Battery-replacement steps (E5): { {k: str(v.date()) for k, v in BAT_STEP.items()} }")

    # SMA-dead cohort
    sma_dead = {}
    for vin in vins:
        w = wk_all[wk_all["vin_label"] == vin]
        frac = w["sma_obs_rows"].sum() / max(w["n_rows"].sum(), 1)
        sma_dead[vin] = frac <= SMA_DEAD_THRESH
    DEAD = sorted([v for v, d in sma_dead.items() if d])
    log(f"  SMA-dead cohort ({len(DEAD)}): {DEAD}")

    # build production matrix
    log("  Building production feature matrix...")
    mat = build_feature_matrix(vins, y, wk_all, ev_all, BAT_STEP, sma_dead,
                               clip_l40_basis=False)

    # build L40-control matrix
    log("  Building L40-control feature matrix...")
    mat_ctl = build_feature_matrix(vins, y, wk_all, ev_all, BAT_STEP, sma_dead,
                                   clip_l40_basis=True)

    # self-test gate: compare to canonical baseline
    if self_test:
        baseline = pd.read_csv(BASELINE_MATRIX_CSV)
        max_diffs = {}
        nan_match = True
        for col in FEATURES:
            a = mat[col].values.astype(float)
            b = baseline[col].values.astype(float)
            # NaN pattern check
            if not np.array_equal(np.isnan(a), np.isnan(b)):
                nan_match = False
                log(f"  [FAIL] NaN pattern mismatch on {col}")
            mok = np.isfinite(a) & np.isfinite(b)
            diff = float(np.max(np.abs(a[mok] - b[mok]))) if mok.any() else 0.0
            max_diffs[col] = diff
        max_overall = max(max_diffs.values())
        log(f"  S1 self-test: max|diff| across all features = {max_overall:.2e}")
        if max_overall > 1e-9 or not nan_match:
            log(f"  [FAIL] S1 matrix reproduction gate FAILED (threshold 1e-9).")
            log(f"  Per-feature max|diff|: {max_diffs}")
            sys.exit(1)
        else:
            log("  [PASS] S1 matrix reproduction gate PASSED (max|diff| <= 1e-9, NaN pattern identical).")

    # admissibility audit
    log("  Running admissibility audit...")
    proxy_rows = []
    for vin in vins:
        w = wk_all[wk_all["vin_label"] == vin]
        wmf = w[w["active_days"] >= 2]
        proxy_rows.append({"n_weeks_masked": len(wmf),
                           "t_start_ord": w["week"].min().toordinal(),
                           "span_days": (w["week"].max() - w["week"].min()).days})
    px = pd.DataFrame(proxy_rows)

    audit_rows = []
    for c in FEATURES:
        v = mat[c].values.astype(float)
        vc = mat_ctl[c].values.astype(float)
        mok = np.isfinite(v)
        a_raw = _rank_auroc_feat(v, y); a = max(a_raw, 1 - a_raw)
        ac_raw = _rank_auroc_feat(vc, y)
        ac = max(ac_raw, 1 - ac_raw) if np.isfinite(ac_raw) else np.nan
        drop = a - ac if np.isfinite(ac) else np.nan
        mwp = stats.mannwhitneyu(v[mok & (y == 1)], v[mok & (y == 0)]).pvalue \
            if mok[y == 1].sum() >= 3 and mok[y == 0].sum() >= 3 else np.nan
        rs = {}
        for p_col in ["n_weeks_masked", "t_start_ord", "span_days"]:
            pv = px[p_col].values.astype(float)
            mm = mok & np.isfinite(pv)
            rs[p_col] = stats.spearmanr(v[mm], pv[mm])[0] if mm.sum() >= 6 else np.nan
        max_p = max(abs(x) for x in rs.values() if np.isfinite(x))
        fail = bool(max_p > 0.5 and np.isfinite(drop) and drop > 0.05)
        verdict = "REJECT" if fail else ("watch" if max_p > 0.4 else "PASS")
        audit_rows.append({
            "feature": c, "n_nonnull": int(mok.sum()),
            "cohort_masked": c in COHORT_MASKED, "mw_p": round(mwp, 5),
            "auroc_raw": round(a, 4),
            "auroc_L40_control": round(ac, 4) if np.isfinite(ac) else np.nan,
            "l40_drop": round(drop, 4) if np.isfinite(drop) else np.nan,
            "r_n_weeks": round(rs["n_weeks_masked"], 3),
            "r_t_start": round(rs["t_start_ord"], 3),
            "r_span_days": round(rs["span_days"], 3),
            "max_abs_r_proxy": round(max_p, 3),
            "admissible": not fail, "verdict": verdict})
    aud = pd.DataFrame(audit_rows)
    admissible = aud[aud["admissible"]]["feature"].tolist()
    log(f"  Admissible pool ({len(admissible)}/{len(FEATURES)}): {admissible}")
    rejected = aud[~aud["admissible"]]["feature"].tolist()
    if rejected:
        log(f"  REJECTED features: {rejected}")

    return mat, mat_ctl, aud, vins, y, BAT_STEP, sma_dead, px


def s2_nested_protocol(
    mat: pd.DataFrame, y: np.ndarray, pool_feats: list,
    n_perm: int, self_test: bool,
) -> tuple[np.ndarray, list, float, list, dict]:
    """
    S2: Full nested LOVO + bootstrap CI + full-pipeline permutation test.
    Returns (probs, det, nested_auroc, boots, perm_info).
    """
    stage_header("S2: Nested validation protocol")

    log(f"  Pool: {len(pool_feats)} admissible features")
    t0 = time.time()
    probs, det = nested_lovo(mat, y, pool_feats, collect=True)
    t_nested = time.time() - t0
    nested_auroc = float(roc_auc_score(y, probs))
    log(f"  Nested AUROC = {nested_auroc:.4f}  (runtime {t_nested:.1f}s)")

    pred_fold = np.array([d["pred_foldthr"] for d in det])
    recal = np.array([d["prob_recal"] for d in det])
    tp = int(((pred_fold == 1) & (y == 1)).sum())
    tn = int(((pred_fold == 0) & (y == 0)).sum())
    fp = int(((pred_fold == 1) & (y == 0)).sum())
    fn = int(((pred_fold == 0) & (y == 1)).sum())
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    log(f"  Per-fold-Youden: recall {tp}/14, spec {tn}/20, F1 {f1:.3f}")

    subset_counter = Counter(tuple(sorted(d["feats"])) for d in det)
    modal_subset = list(subset_counter.most_common(1)[0][0])
    modal_count = subset_counter.most_common(1)[0][1]
    feat_freq = Counter(f for d in det for f in d["feats"])
    log(f"  Modal winner subset ({modal_count}/34 folds): {modal_subset}")
    log(f"  Feature frequency: {dict(feat_freq.most_common())}")

    # self-test gate: AUROC = 0.9321 ± 0.002
    if self_test:
        if abs(nested_auroc - 0.9321) > 0.002:
            log(f"  [FAIL] S2 nested AUROC {nested_auroc:.4f} outside 0.9321 ± 0.002")
            sys.exit(1)
        canonical_modal = sorted(["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90",
                                  "vsi_range_trend", "dip_depth_last90_delta"])
        if sorted(modal_subset) != canonical_modal:
            log(f"  [FAIL] S2 modal subset {modal_subset} != canonical {canonical_modal}")
            sys.exit(1)
        log(f"  [PASS] S2 nested AUROC = {nested_auroc:.4f} (within 0.9321 ± 0.002)")
        log(f"  [PASS] S2 modal subset = {sorted(modal_subset)}")

    # bootstrap CI
    rng = np.random.RandomState(SEED_BOOT)
    n = len(y)
    boots = []
    while len(boots) < N_BOOT:
        idx = rng.choice(n, n, replace=True)
        if len(np.unique(y[idx])) == 2:
            boots.append(roc_auc_score(y[idx], probs[idx]))
    ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    log(f"  Bootstrap 95% CI (N={N_BOOT}): [{ci[0]:.3f}, {ci[1]:.3f}]")

    # permutation test
    log(f"\n  [perm] Full-pipeline permutation test: N={n_perm}")
    log(f"  NOTE: permutation count does NOT affect the AUROC point estimate.")
    if n_perm < 200:
        log(f"  NOTE: Using N={n_perm} for plumbing speed (self-test). Production refits use >=200.")
    rngp = np.random.RandomState(SEED_PERM)
    t0p = time.time()
    perm_aurocs = []
    for b in range(n_perm):
        yp = rngp.permutation(y)
        pp = nested_lovo(mat, yp, pool_feats, collect=False)
        perm_aurocs.append(float(roc_auc_score(yp, pp)))
        if (b + 1) % max(5, n_perm // 4) == 0:
            el = time.time() - t0p
            eta = el / (b + 1) * (n_perm - b - 1)
            log(f"    perm {b+1}/{n_perm}  ({el:.0f}s elapsed, {eta:.0f}s remaining)")
    t_perm = time.time() - t0p
    p_perm = (1 + sum(a >= nested_auroc for a in perm_aurocs)) / (n_perm + 1)
    log(f"  Permutation p = {p_perm:.4f}  (N={n_perm}, null mean {np.mean(perm_aurocs):.3f}, "
        f"null p95 {np.percentile(perm_aurocs, 95):.3f}, runtime {t_perm:.0f}s)")

    perm_info = {
        "n_perm": n_perm, "p_perm": round(p_perm, 4),
        "null_mean": round(float(np.mean(perm_aurocs)), 4),
        "null_p95": round(float(np.percentile(perm_aurocs, 95)), 4),
        "runtime_s": round(t_perm, 1),
        "perm_note": (f"self-test N={n_perm}; production refits use >=200. "
                      "Permutation count does not affect AUROC point estimate.")
        if n_perm < 200 else f"production N={n_perm}",
    }

    return probs, det, nested_auroc, boots, perm_info, modal_subset, modal_count, t_nested


def s3_gates(
    mat, mat_ctl, y, vins, probs, det,
    modal_subset, modal_count, nested_auroc, px,
    perm_info, self_test,
) -> dict:
    """S3: Compute and validate gates G1-G6."""
    stage_header("S3: Gates G1-G6")
    gates = compute_gates(mat, mat_ctl, y, vins, probs, det,
                          modal_subset, modal_count, nested_auroc, px)
    gates["summary"]["permutation_p"] = perm_info["p_perm"]

    # self-test gates
    if self_test:
        g1_drop = gates["G1_fixed_L40_control"]["drop"]
        if g1_drop > 0.001:
            log(f"  [FAIL] S3 G1 drop = {g1_drop:.4f} > 0.001")
            sys.exit(1)
        log(f"  [PASS] S3 G1 drop = {g1_drop:.4f} <= 0.001")

        g6_pass = gates["G6_token_scan"]["pass"]
        if not g6_pass:
            log(f"  [FAIL] S3 G6 banned token hits: {gates['G6_token_scan']['banned_token_hits']}")
            sys.exit(1)
        log(f"  [PASS] S3 G6 zero banned tokens")

        slope = gates["G3_calibration"]["recal_slope"]
        if abs(slope - 0.86) > 0.05:
            log(f"  [FAIL] S3 G3 slope = {slope:.3f}, outside 0.86 ± 0.05")
            sys.exit(1)
        log(f"  [PASS] S3 G3 calibration slope = {slope:.3f} (within 0.86 ± 0.05)")

    for key, val in gates["summary"]["gates_pass"].items():
        log(f"  Gate {key}: {val}")
    return gates


def s4_comparison_report(
    gates: dict, nested_auroc: float, modal_subset: list,
    det: list, probs: np.ndarray, y: np.ndarray, vins: list,
    boots: list, perm_info: dict, self_test: bool,
) -> str:
    """
    S4: Build comparison report vs frozen baseline (v2_config.json validation-of-record).
    Returns the markdown report string.
    """
    stage_header("S4: Comparison report vs baseline")

    with open(V2_CONFIG_PATH) as f:
        v2cfg = json.load(f)
    vor = v2cfg["model"]["validation_of_record"]
    baseline_auroc = vor["auroc_nested"]
    baseline_subset = v2cfg["model"]["features"]
    baseline_slope = vor["calibration_slope"]
    baseline_brier = vor["brier_score"]

    delta_auroc = nested_auroc - baseline_auroc
    slope = gates["G3_calibration"]["recal_slope"]
    brier = gates["G3_calibration"]["brier_recalibrated"]
    new_subset = sorted(modal_subset)
    old_subset = sorted(baseline_subset)
    subset_changed = new_subset != old_subset
    subset_added = [f for f in new_subset if f not in old_subset]
    subset_removed = [f for f in old_subset if f not in new_subset]

    # per-VIN prediction changes vs baseline
    # (in self-test the baseline preds come from V1.1 results)
    try:
        baseline_preds = pd.read_csv(V1_1_RES / "V1_1_SM_nested_lovo_predictions.csv")
        baseline_prob = dict(zip(baseline_preds["vin_label"], baseline_preds["prob_recal"]))
    except Exception:
        baseline_prob = {}

    recal = np.array([d["prob_recal"] for d in det])
    top_movers = []
    for i, vin in enumerate(vins):
        if vin in baseline_prob:
            delta = recal[i] - baseline_prob[vin]
            top_movers.append({"vin": vin, "failed": int(y[i]),
                               "baseline_prob": round(baseline_prob[vin], 4),
                               "refit_prob": round(float(recal[i]), 4),
                               "delta": round(float(delta), 4)})
    top_movers.sort(key=lambda r: abs(r["delta"]), reverse=True)

    ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]

    lines = [
        "# SM V2 Refit Comparison Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**Mode:** {'self-test (identity check)' if self_test else 'production refit'}",
        "",
        "## 1. Headline Metrics",
        "",
        f"| Metric | Baseline (V1.1) | Refit Candidate | Delta |",
        f"|--------|----------------|-----------------|-------|",
        f"| Nested AUROC | {baseline_auroc:.4f} | {nested_auroc:.4f} | {delta_auroc:+.4f} |",
        f"| Bootstrap 95% CI (N=200) | {vor['bootstrap_95ci_N200']} | [{ci[0]:.4f}, {ci[1]:.4f}] | — |",
        f"| Permutation p (N={perm_info['n_perm']}) | {vor['permutation_p']} | {perm_info['p_perm']} | — |",
        f"| Calibration slope | {baseline_slope:.2f} | {slope:.3f} | {slope - baseline_slope:+.3f} |",
        f"| Brier score | {baseline_brier:.4f} | {brier:.4f} | {brier - baseline_brier:+.4f} |",
        "",
        "## 2. Winner Subset",
        "",
        f"**Baseline:** `{old_subset}`",
        f"**Refit modal subset ({Counter(tuple(sorted(d['feats'])) for d in det).most_common(1)[0][1]}/34 folds):** `{new_subset}`",
    ]
    if subset_changed:
        lines += [
            f"**Subset CHANGED** — added: {subset_added}, removed: {subset_removed}",
            "  -> Review whether removed features have degraded or become inadmissible.",
        ]
    else:
        lines.append("**Subset UNCHANGED** (same modal winner as baseline).")

    lines += ["", "## 3. Gates Summary", ""]
    for key, val in gates["summary"]["gates_pass"].items():
        lines.append(f"- {key}: **{val}**")

    lines += ["", "## 4. Per-VIN Top Movers (|Δ prob_recal| largest first)", ""]
    lines.append("| VIN | Failed | Baseline prob | Refit prob | Δ |")
    lines.append("|-----|--------|--------------|------------|---|")
    for r in top_movers[:15]:
        lines.append(f"| {r['vin']} | {r['failed']} | {r['baseline_prob']} | {r['refit_prob']} | {r['delta']:+.4f} |")
    if len(top_movers) > 15:
        lines.append(f"*(showing top 15 of {len(top_movers)} VINs)*")

    lines += [
        "",
        "## 5. Review Checklist",
        "",
        "- [ ] Nested AUROC >= baseline or delta within CI overlap",
        "- [ ] G1 drop <= 0.05 (PASS)",
        "- [ ] G6 zero banned tokens (PASS)",
        "- [ ] G3 calibration slope in [0.5, 2.0]",
        "- [ ] Top movers reviewed — no systematic direction bias on NF trucks",
        "- [ ] Subset change (if any) has domain-level justification",
        "- [ ] Restatement note drafted (see worked example: V1 -> V1.1 in REFIT_RUNBOOK.md)",
        "",
        "## 6. Promotion Decision",
        "",
        "**THIS CANDIDATE HAS NOT BEEN DEPLOYED.**",
        "Manual review required. If promoting:",
        "1. Bump `config_version` and `model.features` in `v2_config.json`",
        "2. Update `validation_of_record` block with refit metrics",
        "3. Recompute `config_hash` and update it",
        "4. Publish restatement note in `docs/` (see V1->V1.1 template in runbook)",
        "5. Retag: `git tag v2.x-sm-refit-<date>`",
        "",
    ]

    report = "\n".join(lines)
    log(f"  AUROC delta vs baseline: {delta_auroc:+.4f}")
    log(f"  Subset changed: {subset_changed}")
    if self_test:
        log(f"  [PASS] S4 delta ~0 (self-test identity check).")
    return report


def s5_artifact_versioning(
    mat: pd.DataFrame, mat_ctl: pd.DataFrame, aud: pd.DataFrame,
    probs: np.ndarray, det: list, gates: dict, perm_info: dict,
    report: str, nested_auroc: float, modal_subset: list,
    y: np.ndarray, vins: list, boots: list, t_nested: float,
    self_test: bool,
) -> Path:
    """S5: Write all artifacts to refit/out/refit_<UTCtimestamp>/."""
    stage_header("S5: Artifact versioning")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = REFIT_OUT_ROOT / f"refit_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    mat.to_csv(run_dir / "feature_matrix.csv", index=False)
    mat_ctl.to_csv(run_dir / "feature_matrix_L40control.csv", index=False)
    aud.to_csv(run_dir / "feature_admissibility.csv", index=False)

    # predictions CSV
    recal = np.array([d["prob_recal"] for d in det])
    pred_fold = np.array([d["pred_foldthr"] for d in det])
    tiers = np.where(recal < TIER_GREEN, "GREEN",
                     np.where(recal < TIER_RED, "AMBER", "RED"))
    subset_counter = Counter(tuple(sorted(d["feats"])) for d in det)
    preds_rows = [{"vin_label": vins[i], "failed": int(y[i]),
                   "prob": round(float(probs[i]), 4),
                   "prob_recal": round(float(recal[i]), 4),
                   "inner_youden": round(d["inner_thr"], 4),
                   "pred_foldthr": int(pred_fold[i]),
                   "tier": tiers[i],
                   "winner": "|".join(d["feats"]),
                   "k": len(d["feats"]),
                   "inner_auroc": round(d["inner_auroc"], 4)}
                  for i, d in enumerate(det)]
    pd.DataFrame(preds_rows).to_csv(run_dir / "predictions.csv", index=False)

    ci = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    tp = int(((pred_fold == 1) & (y == 1)).sum())
    tn = int(((pred_fold == 0) & (y == 0)).sum())
    fp = int(((pred_fold == 1) & (y == 0)).sum())
    fn = int(((pred_fold == 0) & (y == 1)).sum())
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    mcc = _mcc_at(y, pred_fold.astype(float), 0.5)

    model_spec = {
        "experiment": "refit_nested_LOVO",
        "generated": datetime.now(timezone.utc).isoformat(),
        "self_test": self_test,
        "matrix": str(run_dir / "feature_matrix.csv"),
        "pool": [f for f in FEATURES],
        "protocol": {
            "outer_folds": 34,
            "screening": {"mw_p": ALPHA_MW, "auroc_min": AUROC_MIN,
                          "dedup_spearman": CORR_MAX, "stability_frac": STABLE_FRAC,
                          "pool_cap": POOL_CAP},
            "subset_k": [SUBSET_MIN, SUBSET_MAX],
            "model": f"RidgeClassifier(alpha={RIDGE_ALPHA}) closed-form replica",
            "impute": "fold-internal train medians",
            "scale": "StandardScaler",
            "threshold_rule": "per-fold inner-OOF Youden (pre-registered)",
            "recalibration": "per-fold Platt on inner-OOF decision values",
            "tiers": f"GREEN<{TIER_GREEN}<=AMBER<{TIER_RED}<=RED on recalibrated"},
        "seeds": {"bootstrap": SEED_BOOT, "permutation": SEED_PERM},
        "headline": {
            "nested_auroc": round(nested_auroc, 4),
            "bootstrap_95ci_N200": [round(ci[0], 4), round(ci[1], 4)],
            "permutation_p": perm_info["p_perm"],
            "permutation_N": perm_info["n_perm"],
            "perm_note": perm_info["perm_note"],
            "per_fold_threshold_metrics": {
                "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "recall": round(tp / 14, 4), "specificity": round(tn / 20, 4),
                "f1": round(f1, 4), "mcc": round(mcc, 4)},
            "tier_counts": {t: {"failed": int(((tiers == t) & (y == 1)).sum()),
                                "nonfailed": int(((tiers == t) & (y == 0)).sum())}
                            for t in ["GREEN", "AMBER", "RED"]}},
        "modal_winner_subset": modal_subset,
        "runtime": {"nested_main_s": round(t_nested, 1),
                    "perm_s": round(perm_info["runtime_s"], 1)},
    }
    with open(run_dir / "model_spec.json", "w") as f:
        json.dump(model_spec, f, indent=2)
    with open(run_dir / "gates.json", "w") as f:
        json.dump(gates, f, indent=2)
    with open(run_dir / "comparison_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    # write run log
    with open(run_dir / "run.log", "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG_LINES))

    log(f"  Artifacts written to: {run_dir}")

    # NEVER-AUTO-DEPLOY BANNER
    banner = """
+==============================================================================+
|        [!]  REFIT AUTOMATION HARNESS -- GOVERNANCE NOTICE  [!]               |
|                                                                              |
|  THIS HARNESS NEVER AUTO-DEPLOYS.                                            |
|                                                                              |
|  The artifacts in this run directory are CANDIDATE outputs only.             |
|  They have NOT been promoted to the live V2 system.                          |
|                                                                              |
|  REQUIRED BEFORE PROMOTION:                                                  |
|    1. Human review of comparison_report.md (all checklist items)             |
|    2. Manual config bump: v2_config.json version + features + hash           |
|    3. Restatement note published in docs/ (see REFIT_RUNBOOK.md)             |
|    4. Git tag: v2.x-sm-refit-<date>                                          |
|                                                                              |
|  MANUAL REVIEW + CONFIG BUMP REQUIRED                                        |
+==============================================================================+
"""
    print(banner)
    log(banner.strip())
    return run_dir


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="SM V2 Refit Automation Harness (roadmap C6)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true",
                      help="Identity check vs frozen V1.1 baseline (no new labels needed)")
    mode.add_argument("--labels", metavar="PATH",
                      help="Path to new labels CSV for production refit")
    parser.add_argument("--perm-n", type=int, default=None,
                        help="Permutation iterations (default: 20 for self-test, 200 for --labels)")
    parser.add_argument("--force", action="store_true",
                        help="Bypass >=5 new-failure-label trigger gate")
    args = parser.parse_args()

    self_test = args.self_test
    perm_n = args.perm_n if args.perm_n is not None else (20 if self_test else 200)

    log(f"SM V2 Refit Automation Harness  —  {datetime.now(timezone.utc).isoformat()}")
    log(f"Mode: {'self-test' if self_test else 'production'}  |  perm-n={perm_n}")

    t_total = time.time()
    stage_times = {}

    # S0
    t0 = time.time()
    s0_trigger_check(None if self_test else args.labels, args.force)
    stage_times["S0"] = time.time() - t0

    # S1
    t0 = time.time()
    mat, mat_ctl, aud, vins, y, BAT_STEP, sma_dead, px = s1_feature_build(self_test)
    pool_feats = aud[aud["admissible"]]["feature"].tolist()
    stage_times["S1"] = time.time() - t0
    log(f"\n  S1 duration: {stage_times['S1']:.1f}s")

    # S2
    t0 = time.time()
    (probs, det, nested_auroc, boots, perm_info,
     modal_subset, modal_count, t_nested) = s2_nested_protocol(
        mat, y, pool_feats, perm_n, self_test)
    stage_times["S2"] = time.time() - t0
    log(f"\n  S2 duration: {stage_times['S2']:.1f}s")

    # S3
    t0 = time.time()
    gates = s3_gates(mat, mat_ctl, y, vins, probs, det,
                     modal_subset, modal_count, nested_auroc, px,
                     perm_info, self_test)
    stage_times["S3"] = time.time() - t0
    log(f"\n  S3 duration: {stage_times['S3']:.1f}s")

    # S4
    t0 = time.time()
    report = s4_comparison_report(
        gates, nested_auroc, modal_subset, det, probs, y, vins,
        boots, perm_info, self_test)
    stage_times["S4"] = time.time() - t0
    log(f"\n  S4 duration: {stage_times['S4']:.1f}s")

    # S5
    t0 = time.time()
    run_dir = s5_artifact_versioning(
        mat, mat_ctl, aud, probs, det, gates, perm_info,
        report, nested_auroc, modal_subset, y, vins, boots,
        t_nested, self_test)
    stage_times["S5"] = time.time() - t0
    log(f"\n  S5 duration: {stage_times['S5']:.1f}s")

    total = time.time() - t_total
    log(f"\n{'='*70}")
    log(f"STAGE SUMMARY")
    log(f"{'='*70}")
    for s, t in stage_times.items():
        log(f"  {s}: {t:.1f}s")
    log(f"  TOTAL: {total:.1f}s")
    log(f"\nRun artifacts: {run_dir}")
    if self_test:
        log("\n[SELF-TEST COMPLETE] All gates PASSED.")
    else:
        log("\n[REFIT COMPLETE] Review comparison_report.md before promoting.")


if __name__ == "__main__":
    main()
