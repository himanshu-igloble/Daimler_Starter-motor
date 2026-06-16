"""
P5 — Aging / Drift: per-VIN Theil-Sen trends of session metrics over full life.
Also: does fleet-percentile rank of a truck's crank quality drift years before failure?
Uses: weekly cache (vsi_drive_std exists) + crank events for multi-attempt rate per week.
Key question: Is there an "early warning" years before failure (>180d lead), or
only a final-10-week terminal rise (already known from G3 prequential)?
This is new: checking fleet-percentile rank drift, not just within-VIN trend.
Density check: Theil-Sen is slope per unit time, not cumulative count.
Outputs: out/P5_aging_trends.csv, out/P5_percentile_rank_trajectory.csv, out/P5_aging_auroc.csv
"""

import polars as pl
import numpy as np
from pathlib import Path
import sys
from sklearn.metrics import roc_auc_score
from scipy.stats import mannwhitneyu, theilslopes

REPO = Path("D:/Daimler-starter_motor_alternator_battery")
WEEKLY_DIR = REPO / "STARTER MOTOR/cache/weekly"
EVENTS = REPO / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"
OUT = REPO / "STARTER MOTOR/V2_program/probes/out"

SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

# Load all weekly caches
weekly_frames = []
for f in sorted(WEEKLY_DIR.glob("*.parquet")):
    wk = pl.read_parquet(f)
    weekly_frames.append(wk)
fleet_weekly = pl.concat(weekly_frames).sort(["vin_label", "week"])
print(f"Fleet weekly: {fleet_weekly.shape}", file=sys.stderr)

# Load crank events for multi-attempt rate per week
ev = pl.read_parquet(EVENTS)
ev = ev.filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
ev = ev.filter(pl.col("artifact") == False)
ev = ev.sort(["vin_label", "ts_start"])
ev = ev.with_columns([
    pl.col("ts_start").diff().dt.total_seconds().over("vin_label").alias("gap_to_prev_s")
])
ev = ev.with_columns([
    ((pl.col("gap_to_prev_s").is_null()) | (pl.col("gap_to_prev_s") > 60)).alias("is_session_start"),
    pl.col("ts_start").dt.truncate("1w").alias("week"),  # truncate to week
])
# Multi-attempt rate per week: sessions with n>1 / total sessions per week
ev_weekly = ev.group_by(["vin_label", "failed", "week"]).agg([
    pl.col("is_session_start").sum().alias("n_sessions"),
    (pl.col("retry_within_120s").cast(pl.Int32).sum() / (pl.col("is_session_start").sum()).clip(lower_bound=1)).alias("retry_rate_week"),
    pl.col("dur_s").mean().alias("mean_dur_week"),
])

# Merge weekly VSI with event metrics
fleet_weekly_all = fleet_weekly.join(
    ev_weekly.select(["vin_label", "week", "n_sessions", "retry_rate_week", "mean_dur_week"]),
    on=["vin_label", "week"],
    how="left"
)
print(f"Fleet weekly merged: {fleet_weekly_all.shape}", file=sys.stderr)

# ===========================================================================
# Compute fleet-percentile rank per week for key metrics
# (At each calendar week, where does each truck rank relative to ALL trucks
# with observed data that week?)
# ===========================================================================
def fleet_rank_trajectory(fleet_df, col):
    """For each VIN×week, compute the fleet percentile rank."""
    records = []
    # Get all weeks
    all_weeks = fleet_df["week"].unique().sort()
    for wk in all_weeks.to_list():
        slice_wk = fleet_df.filter(pl.col("week") == wk).filter(pl.col(col).is_not_null())
        if len(slice_wk) < 3:
            continue
        vals = slice_wk[col].to_numpy().astype(float)
        ranks = (np.argsort(np.argsort(vals)) + 0.5) / len(vals)  # fractional rank
        for vin, fld, rank_pct in zip(slice_wk["vin_label"].to_list(),
                                       slice_wk["failed"].to_list(),
                                       ranks):
            records.append({
                "vin_label": vin,
                "failed": fld,
                "week": wk,
                "fleet_rank_pct": float(rank_pct),
                "metric": col,
            })
    return pl.DataFrame(records)

# Compute fleet rank for vsi_drive_std (higher = worse)
rank_std = fleet_rank_trajectory(fleet_weekly_all, "vsi_drive_std")
print(f"Fleet rank std: {rank_std.shape}", file=sys.stderr)

# ===========================================================================
# Per-VIN: does rank drift EARLY (>180d before t_end)?
# ===========================================================================
# Get t_end (days_before_t_end from events)
ev_tend = (pl.read_parquet(EVENTS)
           .filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
           .group_by(["vin_label", "failed"])
           .agg(pl.col("ts_start").max().alias("t_end")))

vin_records = []
vins = fleet_weekly_all.select(["vin_label", "failed"]).unique().sort("vin_label")

for vin_label, failed in vins.rows():
    vw = fleet_weekly_all.filter(pl.col("vin_label") == vin_label)
    if len(vw) < 8:
        continue

    vw = vw.sort("week")
    weeks = vw["week"].to_list()
    n_weeks = len(weeks)

    # Metrics to trend
    std_vals = vw["vsi_drive_std"].to_numpy().astype(float)
    t_idx = np.arange(n_weeks)

    # Theil-Sen slope of vsi_drive_std over full life
    mask_std = ~np.isnan(std_vals)
    ts_std_slope = float("nan")
    if mask_std.sum() >= 5:
        try:
            res = theilslopes(std_vals[mask_std], t_idx[mask_std])
            ts_std_slope = float(res.slope)
        except Exception:
            pass

    # Fleet rank trajectory for this VIN
    vr = rank_std.filter(pl.col("vin_label") == vin_label).sort("week")
    rank_vals = vr["fleet_rank_pct"].to_numpy().astype(float) if len(vr) > 0 else np.array([])

    # Early rank drift: weeks 0..-(n/2) vs last n/4 weeks
    early_rank = float("nan")
    late_rank = float("nan")
    rank_drift = float("nan")
    if len(rank_vals) >= 8:
        n_r = len(rank_vals)
        early_rank = float(np.nanmean(rank_vals[:n_r//2]))
        late_rank = float(np.nanmean(rank_vals[-n_r//4:]))
        rank_drift = late_rank - early_rank  # positive = worsened (higher rank = higher std)

    # Theil-Sen slope of fleet rank over lifetime (weeks)
    ts_rank_slope = float("nan")
    if len(rank_vals) >= 8:
        t_r = np.arange(len(rank_vals))
        mask_r = ~np.isnan(rank_vals)
        if mask_r.sum() >= 5:
            try:
                res = theilslopes(rank_vals[mask_r], t_r[mask_r])
                ts_rank_slope = float(res.slope)
            except Exception:
                pass

    # How early does rank first exceed 0.7 (top 30% worst fleet)?
    weeks_above_p70 = float("nan")
    first_weeks_above_p70 = float("nan")
    if len(rank_vals) >= 8:
        above = rank_vals > 0.70
        weeks_above_p70 = float(above.sum())
        if above.any():
            first_weeks_above_p70 = float(np.argmax(above))  # index of first exceedance

    # Weekly retry rate trend (Theil-Sen)
    retry_vals = vw["retry_rate_week"].drop_nulls().to_numpy().astype(float) if "retry_rate_week" in vw.columns else np.array([])
    ts_retry_slope = float("nan")
    if len(retry_vals) >= 5:
        try:
            res = theilslopes(retry_vals, np.arange(len(retry_vals)))
            ts_retry_slope = float(res.slope)
        except Exception:
            pass

    vin_records.append({
        "vin_label": vin_label,
        "failed": int(failed),
        "n_weeks": n_weeks,
        "ts_vsi_std_slope_per_week": ts_std_slope,
        "early_fleet_rank_pct": early_rank,
        "late_fleet_rank_pct": late_rank,
        "fleet_rank_drift": rank_drift,
        "ts_fleet_rank_slope": ts_rank_slope,
        "weeks_above_p70_fleet": weeks_above_p70,
        "first_week_above_p70": first_weeks_above_p70,
        "ts_retry_rate_slope_per_week": ts_retry_slope,
    })

vin_df = pl.DataFrame(vin_records)
vin_df.write_csv(OUT / "P5_aging_trends.csv")
print(f"Saved P5_aging_trends.csv", file=sys.stderr)

# Save rank trajectory
rank_std.write_csv(OUT / "P5_percentile_rank_trajectory.csv")
print(f"Saved P5_percentile_rank_trajectory.csv: {rank_std.shape}", file=sys.stderr)

# AUROC
def safe_auroc(y, scores):
    mask = ~np.isnan(np.array(scores, dtype=float))
    y_arr = np.array(y, dtype=int)[mask]
    s_arr = np.array(scores, dtype=float)[mask]
    n_f, n_nf = int(y_arr.sum()), int((1 - y_arr).sum())
    if n_f < 2 or n_nf < 2:
        return float("nan"), n_f, n_nf
    try:
        return roc_auc_score(y_arr, s_arr), n_f, n_nf
    except Exception:
        return float("nan"), n_f, n_nf

def cohens_d(f, n):
    f, n = np.array(f, dtype=float), np.array(n, dtype=float)
    f, n = f[~np.isnan(f)], n[~np.isnan(n)]
    if len(f) < 2 or len(n) < 2: return float("nan")
    pooled = np.sqrt(((len(f)-1)*np.var(f,ddof=1) + (len(n)-1)*np.var(n,ddof=1)) / (len(f)+len(n)-2))
    return float("nan") if pooled == 0 else (np.mean(f) - np.mean(n)) / pooled

y = vin_df["failed"].to_list()
auroc_rows = []
for metric in ["ts_vsi_std_slope_per_week", "fleet_rank_drift", "ts_fleet_rank_slope",
               "weeks_above_p70_fleet", "first_week_above_p70", "ts_retry_rate_slope_per_week",
               "late_fleet_rank_pct"]:
    scores = vin_df[metric].to_list()
    scores_f = [float(s) if s is not None else float("nan") for s in scores]
    auc, n_f, n_nf = safe_auroc(y, scores_f)
    fv = [s for s, yi in zip(scores_f, y) if yi == 1 and not np.isnan(s)]
    nv = [s for s, yi in zip(scores_f, y) if yi == 0 and not np.isnan(s)]
    d = cohens_d(fv, nv)
    try:
        _, pval = mannwhitneyu(fv, nv, alternative="two-sided") if len(fv) > 1 and len(nv) > 1 else (None, float("nan"))
    except Exception:
        pval = float("nan")
    auroc_rows.append({
        "metric": metric,
        "auroc": round(auc, 3) if not np.isnan(auc) else None,
        "cohens_d": round(d, 3) if not np.isnan(d) else None,
        "n_failed": n_f,
        "n_nf": n_nf,
        "mwu_pval": round(pval, 4) if not np.isnan(pval) else None,
        "density_check": "Theil-Sen slope per week = time-normalized, density-robust",
    })

# CRITICAL DENSITY CHECK: correlation of fleet_rank_drift with observation_length
n_weeks = vin_df["n_weeks"].to_list()
for metric in ["fleet_rank_drift", "ts_fleet_rank_slope", "weeks_above_p70_fleet"]:
    vals = vin_df[metric].to_list()
    v_arr = [float(s) if s is not None else float("nan") for s in vals]
    mask = [not np.isnan(v) and not np.isnan(float(n)) for v, n in zip(v_arr, n_weeks)]
    v_c = np.array([v for v, m in zip(v_arr, mask) if m])
    n_c = np.array([float(n) for n, m in zip(n_weeks, mask) if m])
    if len(v_c) > 3:
        r = np.corrcoef(v_c, n_c)[0, 1]
        print(f"density_check P5: r({metric}, n_weeks)={r:.3f}", file=sys.stderr)

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P5_aging_auroc.csv")
print("=== P5 AUROC ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)
print("P5 done.", file=sys.stderr)
