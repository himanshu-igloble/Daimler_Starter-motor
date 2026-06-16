"""
V1_SM_features.py  —  Phase 2: Feature Matrix
BharatBenz Starter Motor predictive maintenance pipeline.

Produces: STARTER MOTOR/results/V1_SM_feature_matrix.csv
  - 34 rows x 25 cols (vin_label, failed, 23 features)
  - Branch A: 13 crank-physics features (from non-artifact events)
  - Branch B: 10 electrical/VSI weekly features

Anti-leakage contract:
  - NO cumulative counts, NO observation length, NO gap-to-failure
  - All last-N-days windows anchor on t_end = max(ts_start) per VIN
  - Rates and trends only
"""

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
from scipy import stats, signal

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def theil_sen(y: np.ndarray, x: np.ndarray) -> float | None:
    """Theil-Sen slope; returns None if < 4 valid (non-NaN) paired points."""
    mask = np.isfinite(y) & np.isfinite(x)
    if mask.sum() < 4:
        return None
    return float(stats.theilslopes(y[mask], x[mask]).slope)


def _monthly_agg(ev_vin: pd.DataFrame, col: str, min_count: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """
    Aggregate a column by calendar month for trend slopes.
    Returns (monthly_means, month_index) for months with >= min_count non-null values.
    month_index = (year*12 + month) - (first_month_integer)
    """
    tmp = ev_vin[["ts_start", col]].copy()
    tmp = tmp.dropna(subset=[col])
    if tmp.empty:
        return np.array([]), np.array([])

    tmp["_ym"] = tmp["ts_start"].dt.year * 12 + tmp["ts_start"].dt.month
    grouped = tmp.groupby("_ym")[col].agg(["mean", "count"])
    grouped = grouped[grouped["count"] >= min_count]
    if grouped.empty:
        return np.array([]), np.array([])

    first_ym = grouped.index.min()
    month_idx = (grouped.index - first_ym).values.astype(float)
    return grouped["mean"].values, month_idx


def _monthly_agg_min_vals(ev_vin: pd.DataFrame, col: str, min_vals: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Like _monthly_agg but with a custom minimum non-null threshold per month."""
    tmp = ev_vin[["ts_start", col]].copy()
    tmp = tmp.dropna(subset=[col])
    if tmp.empty:
        return np.array([]), np.array([])

    tmp["_ym"] = tmp["ts_start"].dt.year * 12 + tmp["ts_start"].dt.month
    grouped = tmp.groupby("_ym")[col].agg(["mean", "count"])
    grouped = grouped[grouped["count"] >= min_vals]
    if grouped.empty:
        return np.array([]), np.array([])

    first_ym = grouped.index.min()
    month_idx = (grouped.index - first_ym).values.astype(float)
    return grouped["mean"].values, month_idx


def _masked_weekly(wk_vin: pd.DataFrame) -> pd.DataFrame:
    """
    Return weekly rows with active_days >= 2, sorted by week.
    Adds 'week_x' column = (week - first_week).days / 7.0
    """
    wk = wk_vin[wk_vin["active_days"] >= 2].copy()
    wk = wk.sort_values("week").reset_index(drop=True)
    if wk.empty:
        wk["week_x"] = pd.Series(dtype=float)
        return wk
    first_week = wk["week"].iloc[0]
    wk["week_x"] = (wk["week"] - first_week).dt.days / 7.0
    return wk


def spearman_r(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman r between two 1-D arrays; drops NaN pairs."""
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 4:
        return 0.0
    r, _ = stats.spearmanr(a[mask], b[mask])
    return float(r)


def rank_auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUROC; higher score = more likely failed. Nulls excluded."""
    mask = np.isfinite(scores)
    s, l = scores[mask], labels[mask]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return float("nan")
    # Mann-Whitney U
    pos = s[l == 1]
    neg = s[l == 0]
    u = 0.0
    for p in pos:
        u += (neg < p).sum() + 0.5 * (neg == p).sum()
    return float(u / (len(pos) * len(neg)))


# ─────────────────────────────────────────────────────────────────────────────
# Load caches
# ─────────────────────────────────────────────────────────────────────────────
print("Loading caches...")
events_all = pd.read_parquet(cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet")
# Ensure ts_start is datetime
events_all["ts_start"] = pd.to_datetime(events_all["ts_start"])
# Cast success to nullable bool
events_all["success"] = events_all["success"].map(
    lambda x: (bool(x) if x is not None and x != "None" else None)
)

# Non-artifact only
events = events_all[events_all["artifact"] == False].copy()
print(f"  Events (all):        {len(events_all):,}")
print(f"  Events (non-artifact): {len(events):,}")

# Load all weekly files
weekly_files = list(cfg.CACHE_WEEKLY.glob("*.parquet"))
weekly_all = pd.concat(
    [pd.read_parquet(f) for f in weekly_files],
    ignore_index=True
)
weekly_all["week"] = pd.to_datetime(weekly_all["week"])
print(f"  Weekly rows:         {len(weekly_all):,}")

# VIN roster
vin_roster = (
    events[["vin_label", "failed"]]
    .drop_duplicates()
    .sort_values("vin_label")
    .reset_index(drop=True)
)
print(f"  VINs in events:      {len(vin_roster)}")


# ─────────────────────────────────────────────────────────────────────────────
# Feature computation
# ─────────────────────────────────────────────────────────────────────────────

rows = []

for _, meta in vin_roster.iterrows():
    vin = meta["vin_label"]
    failed = meta["failed"]

    ev = events[events["vin_label"] == vin].copy()
    wk_raw = weekly_all[weekly_all["vin_label"] == vin].copy()
    wk = _masked_weekly(wk_raw)

    feat = {"vin_label": vin, "failed": int(failed)}

    # ── Branch A: crank physics ───────────────────────────────────────────────

    # 1. crank_dur_mean
    feat["crank_dur_mean"] = float(ev["dur_s"].mean()) if len(ev) > 0 else None

    # 2. crank_dur_trend  (monthly mean dur_s; months with >= 5 events)
    m_vals, m_idx = _monthly_agg(ev, "dur_s", min_count=5)
    feat["crank_dur_trend"] = theil_sen(m_vals, m_idx)

    # 3. multi_sample_rate
    feat["multi_sample_rate"] = float((ev["n_rows"] >= 2).mean()) if len(ev) > 0 else None

    # 4. dip_depth_mean
    dd = ev["dip_depth"].dropna()
    feat["dip_depth_mean"] = float(dd.mean()) if len(dd) > 0 else None

    # 5. dip_depth_trend  (monthly mean dip_depth; months with >= 3 non-null dip values)
    m_vals, m_idx = _monthly_agg_min_vals(ev, "dip_depth", min_vals=3)
    feat["dip_depth_trend"] = theil_sen(m_vals, m_idx)

    # 6. dip_depth_last90_delta
    ev90 = ev[ev["days_before_t_end"] <= 90]
    ev_rest = ev[ev["days_before_t_end"] > 90]
    dd90 = ev90["dip_depth"].dropna()
    dd_rest = ev_rest["dip_depth"].dropna()
    if len(dd90) >= 10 and len(dd_rest) >= 10:
        feat["dip_depth_last90_delta"] = float(dd90.mean() - dd_rest.mean())
    else:
        feat["dip_depth_last90_delta"] = None

    # 7. failed_crank_rate
    ev_succ = ev[ev["success"].notna()].copy()
    ev_succ["_succ"] = ev_succ["success"].astype(bool)
    if len(ev_succ) > 0:
        feat["failed_crank_rate"] = float((~ev_succ["_succ"]).mean())
    else:
        feat["failed_crank_rate"] = None

    # 8. failed_crank_rate_last90
    ev90_succ = ev_succ[ev_succ["days_before_t_end"] <= 90]
    if len(ev90_succ) >= 10:
        feat["failed_crank_rate_last90"] = float((~ev90_succ["_succ"]).mean())
    else:
        feat["failed_crank_rate_last90"] = None

    # 9. retry_rate
    feat["retry_rate"] = float(ev["retry_within_120s"].mean()) if len(ev) > 0 else None

    # 10. recovery_slope_mean
    rs = ev["recovery_slope"].dropna()
    feat["recovery_slope_mean"] = float(rs.mean()) if len(rs) > 0 else None

    # 11. recovery_slope_trend
    m_vals, m_idx = _monthly_agg(ev, "recovery_slope", min_count=5)
    feat["recovery_slope_trend"] = theil_sen(m_vals, m_idx)

    # 12. crank_per_active_day
    total_active = wk_raw["active_days"].sum()
    if total_active > 0:
        feat["crank_per_active_day"] = float(len(ev)) / float(total_active)
    else:
        feat["crank_per_active_day"] = None

    # 13. min_vsi_crank_p05
    mvc = ev["min_vsi_crank"].dropna()
    feat["min_vsi_crank_p05"] = float(np.percentile(mvc, 5)) if len(mvc) > 0 else None

    # ── Branch B: electrical/VSI weekly ──────────────────────────────────────

    n_wk = len(wk)

    # 14. vsi_std_ratio_30d
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

    # 15 & 16: vsi_dominant_freq, vsi_spectral_entropy
    if n_wk >= 10:
        vdm_series = wk["vsi_drive_mean"].copy()
        # Linear-interpolate interior nulls
        vdm_series = vdm_series.interpolate(method="linear", limit_direction="both")
        vdm_arr = vdm_series.values.astype(float)
        # Subtract mean (detrend by mean)
        vdm_arr = vdm_arr - np.nanmean(vdm_arr)
        if not np.all(np.isfinite(vdm_arr)):
            vdm_arr = np.where(np.isfinite(vdm_arr), vdm_arr, 0.0)

        freqs, power = signal.periodogram(vdm_arr, fs=1.0)  # fs=1 sample/week

        # dominant freq
        feat["vsi_dominant_freq"] = float(freqs[np.argmax(power)])

        # spectral entropy (normalized)
        p_nonzero = power[power > 0]
        if len(p_nonzero) > 1:
            p_norm = p_nonzero / p_nonzero.sum()
            ent = -np.sum(p_norm * np.log(p_norm))
            feat["vsi_spectral_entropy"] = float(ent / np.log(len(p_nonzero)))
        else:
            feat["vsi_spectral_entropy"] = None
    else:
        feat["vsi_dominant_freq"] = None
        feat["vsi_spectral_entropy"] = None

    # 17. vsi_range_trend  (last 12 masked weeks; need >= 6 valid)
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

    # 18. progressive_drift
    if n_wk >= 12:
        baseline8 = wk.head(8)["vsi_drive_mean"].dropna()
        if len(baseline8) >= 4:
            baseline_mean = float(baseline8.mean())
            post = wk.iloc[8:]
            post_vals = post["vsi_drive_mean"].dropna().values
            overall_std = float(wk["vsi_drive_mean"].dropna().std())
            n_after = len(post_vals)
            if n_after > 0 and overall_std > 0:
                feat["progressive_drift"] = float(
                    np.abs(np.sum(post_vals - baseline_mean)) / (overall_std * n_after)
                )
            else:
                feat["progressive_drift"] = None
        else:
            feat["progressive_drift"] = None
    else:
        feat["progressive_drift"] = None

    # 19. bat_charge_delta_trend  = theil_sen(vsi_drive_mean - vsi_rest_median, week_x)
    bcd = wk.dropna(subset=["vsi_drive_mean", "vsi_rest_median"]).copy()
    bcd["_delta"] = bcd["vsi_drive_mean"] - bcd["vsi_rest_median"]
    feat["bat_charge_delta_trend"] = theil_sen(
        bcd["_delta"].values, bcd["week_x"].values
    )

    # 20. vsi_rest_median_trend
    vrm = wk.dropna(subset=["vsi_rest_median"]).copy()
    feat["vsi_rest_median_trend"] = theil_sen(
        vrm["vsi_rest_median"].values.astype(float),
        vrm["week_x"].values
    )

    # 21. vsi_rest_p05_last90  = mean of last 13 masked weeks' vsi_rest_p05
    last13 = wk.tail(13)
    vrp05 = last13["vsi_rest_p05"].dropna()
    feat["vsi_rest_p05_last90"] = float(vrp05.mean()) if len(vrp05) > 0 else None

    # 22. rate_vsi_below_21
    total_vsi_obs = wk_raw["vsi_obs_rows"].sum()
    if total_vsi_obs > 0:
        feat["rate_vsi_below_21"] = float(wk_raw["vsi_below_21_rows"].sum()) / float(total_vsi_obs)
    else:
        feat["rate_vsi_below_21"] = None

    # 23. rate_vsi_above_32
    if total_vsi_obs > 0:
        feat["rate_vsi_above_32"] = float(wk_raw["vsi_above_32_rows"].sum()) / float(total_vsi_obs)
    else:
        feat["rate_vsi_above_32"] = None

    rows.append(feat)


# ─────────────────────────────────────────────────────────────────────────────
# Assemble feature matrix
# ─────────────────────────────────────────────────────────────────────────────
FEATURE_COLS = [
    "crank_dur_mean", "crank_dur_trend", "multi_sample_rate",
    "dip_depth_mean", "dip_depth_trend", "dip_depth_last90_delta",
    "failed_crank_rate", "failed_crank_rate_last90", "retry_rate",
    "recovery_slope_mean", "recovery_slope_trend", "crank_per_active_day",
    "min_vsi_crank_p05",
    "vsi_std_ratio_30d", "vsi_dominant_freq", "vsi_spectral_entropy",
    "vsi_range_trend", "progressive_drift",
    "bat_charge_delta_trend", "vsi_rest_median_trend",
    "vsi_rest_p05_last90", "rate_vsi_below_21", "rate_vsi_above_32",
]

df = pd.DataFrame(rows)[["vin_label", "failed"] + FEATURE_COLS]

# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("VERIFICATION")
print("=" * 70)

# Check 1: shape + cohort counts
print(f"\n1. Shape: {df.shape}  (expected 34 x 25)")
n_failed = int(df["failed"].sum())
n_nf = int((~df["failed"].astype(bool)).sum())
print(f"   Failed={n_failed} (expected 14), Non-Failed={n_nf} (expected 20)")
assert df.shape == (34, 25), f"SHAPE MISMATCH: {df.shape}"
assert n_failed == 14, f"FAILED COUNT MISMATCH: {n_failed}"
assert n_nf == 20, f"NF COUNT MISMATCH: {n_nf}"

# Check 2: null counts
print("\n2. Per-feature null counts (WARN-NULL if > 8 of 34):")
print(f"   {'Feature':<35} {'Nulls':>5}  {'%':>6}")
print(f"   {'-'*35} {'-----':>5}  {'------':>6}")
for col in FEATURE_COLS:
    n_null = int(df[col].isnull().sum())
    pct = 100.0 * n_null / len(df)
    warn = "  WARN-NULL" if n_null > 8 else ""
    print(f"   {col:<35} {n_null:>5}  {pct:>5.1f}%{warn}")

# Check 3: cohort means + single-feature AUROC
print("\n3. Cohort means (failed vs NF) and rank AUROC (higher = failed):")
print(f"   {'Feature':<35} {'F_mean':>10} {'NF_mean':>10} {'AUROC':>7}")
print(f"   {'-'*35} {'-------':>10} {'--------':>10} {'-----':>7}")
labels = df["failed"].astype(int).values
for col in FEATURE_COLS:
    vals = df[col].values.astype(float)
    f_mean = np.nanmean(vals[labels == 1])
    nf_mean = np.nanmean(vals[labels == 0])
    auroc = rank_auroc(vals, labels)
    # flip if AUROC < 0.5 (convention: report best direction)
    auroc_disp = max(auroc, 1.0 - auroc) if not np.isnan(auroc) else float("nan")
    print(f"   {col:<35} {f_mean:>10.4f} {nf_mean:>10.4f} {auroc_disp:>7.3f}")

# Check 4: leakage tripwire
print("\n4. Leakage tripwire: Spearman |r| with observation length (total masked weeks):")
# Compute observation length proxy per VIN using masked weeks count
obs_len = []
for vin in df["vin_label"]:
    wk_raw = weekly_all[weekly_all["vin_label"] == vin]
    wk_masked = wk_raw[wk_raw["active_days"] >= 2]
    obs_len.append(len(wk_masked))
obs_arr = np.array(obs_len, dtype=float)

corrs = {}
for col in FEATURE_COLS:
    vals = df[col].values.astype(float)
    r = spearman_r(vals, obs_arr)
    corrs[col] = abs(r)

top3 = sorted(corrs.items(), key=lambda x: x[1], reverse=True)[:3]
print(f"   Top-3 |Spearman r| with obs length:")
any_leak = False
for feat_name, r_val in top3:
    flag = ""
    if r_val > 0.8:
        flag = "  WARN-LEAK"
        any_leak = True
    print(f"   {feat_name:<35} |r|={r_val:.3f}{flag}")
if not any_leak:
    print("   No leakage tripwire exceeded (all |r| <= 0.80).")

print()
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────────────────────
out_path = cfg.RESULTS / "V1_SM_feature_matrix.csv"
out_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out_path, index=False)
print(f"Saved: {out_path}")
print(f"Matrix: {df.shape[0]} rows x {df.shape[1]} cols")
