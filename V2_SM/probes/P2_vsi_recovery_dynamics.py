"""
P2 — VSI Dip-Recovery Dynamics
From crank events: recovery_slope already cached.
New metrics:
  - recovery_completeness_90d: mean recovery_slope in final 90d vs own baseline
  - slow_recovery_rate_90d: fraction of events where recovery_slope < p25 of baseline
  - "recovery degradation" = decline in recovery_slope trend over lifetime
Note: dip_depth and recovery_slope are NOT in the 10 production features (dip_depth_last90_delta IS,
but it's the delta of dip depth, not recovery slope dynamics).
recovery_slope = rate of VSI return after SMA episode ends (V/s or similar units).
NB: production feat "dip_depth_last90_delta" captures dip depth change, NOT recovery time/slope.
Density-confound check: slope is per-event, not count-based → inherently density-robust.
Outputs: out/P2_recovery_per_vin.csv, out/P2_recovery_auroc.csv
"""

import polars as pl
import numpy as np
from pathlib import Path
import sys
from sklearn.metrics import roc_auc_score
from scipy.stats import mannwhitneyu, theilslopes

REPO = Path("D:/Daimler-starter_motor_alternator_battery")
EVENTS = REPO / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"
OUT = REPO / "STARTER MOTOR/V2_program/probes/out"

SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

ev = pl.read_parquet(EVENTS)
ev = ev.filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
ev = ev.filter(pl.col("artifact") == False)
# Only events with recovery_slope and dip_depth
ev_rec = ev.filter(pl.col("recovery_slope").is_not_null())
print(f"Events with recovery_slope: {len(ev_rec)}, VINs: {ev_rec['vin_label'].n_unique()}", file=sys.stderr)
ev_dip = ev.filter(pl.col("dip_depth").is_not_null())
print(f"Events with dip_depth: {len(ev_dip)}, VINs: {ev_dip['vin_label'].n_unique()}", file=sys.stderr)

def safe_auroc(y, scores):
    mask = ~np.isnan(np.array(scores, dtype=float))
    y_arr = np.array(y, dtype=int)[mask]
    s_arr = np.array(scores, dtype=float)[mask]
    n_f = int(y_arr.sum())
    n_nf = int((1 - y_arr).sum())
    if n_f < 2 or n_nf < 2:
        return float("nan"), n_f, n_nf
    try:
        return roc_auc_score(y_arr, s_arr), n_f, n_nf
    except Exception:
        return float("nan"), n_f, n_nf

def cohens_d(f, n):
    f, n = np.array(f, dtype=float), np.array(n, dtype=float)
    f, n = f[~np.isnan(f)], n[~np.isnan(n)]
    if len(f) < 2 or len(n) < 2:
        return float("nan")
    pooled = np.sqrt(((len(f)-1)*np.var(f,ddof=1) + (len(n)-1)*np.var(n,ddof=1)) / (len(f)+len(n)-2))
    return float("nan") if pooled == 0 else (np.mean(f) - np.mean(n)) / pooled

vin_records = []
vins_used = ev_rec.select(["vin_label", "failed"]).unique().sort("vin_label")

for vin_label, failed in vins_used.rows():
    vs = ev_rec.filter(pl.col("vin_label") == vin_label)
    vs_dip = ev_dip.filter(pl.col("vin_label") == vin_label)

    # Baseline (>180d before t_end) and final windows
    baseline_rec = vs.filter(pl.col("days_before_t_end") > 180)
    if len(baseline_rec) < 5:
        baseline_rec = vs.filter(pl.col("days_before_t_end") > 90)
    final_90_rec = vs.filter(pl.col("days_before_t_end") <= 90)
    final_180_rec = vs.filter(pl.col("days_before_t_end") <= 180)

    baseline_dip = vs_dip.filter(pl.col("days_before_t_end") > 180)
    if len(baseline_dip) < 5:
        baseline_dip = vs_dip.filter(pl.col("days_before_t_end") > 90)
    final_90_dip = vs_dip.filter(pl.col("days_before_t_end") <= 90)

    def smean(df, col):
        if len(df) == 0: return float("nan")
        v = df[col].drop_nulls()
        return float(v.mean()) if len(v) > 0 else float("nan")

    bl_slope = smean(baseline_rec, "recovery_slope")
    f90_slope = smean(final_90_rec, "recovery_slope")
    f180_slope = smean(final_180_rec, "recovery_slope")

    # Slow recovery rate: fraction of final-90d events below baseline p25
    slow_rec_rate_90 = float("nan")
    if len(baseline_rec) >= 5 and len(final_90_rec) > 0:
        bl_p25 = float(baseline_rec["recovery_slope"].quantile(0.25))
        slow_count = (final_90_rec["recovery_slope"] < bl_p25).sum()
        slow_rec_rate_90 = slow_count / len(final_90_rec)

    # Delta
    slope_delta90 = f90_slope - bl_slope if not np.isnan(f90_slope) and not np.isnan(bl_slope) else float("nan")
    slope_delta180 = f180_slope - bl_slope if not np.isnan(f180_slope) and not np.isnan(bl_slope) else float("nan")

    # Theil-Sen trend of recovery_slope over lifetime (life-span normalized)
    ts_slope_trend = float("nan")
    if len(vs) >= 10:
        days_arr = vs["days_before_t_end"].to_numpy().astype(float)
        slope_arr = vs["recovery_slope"].to_numpy().astype(float)
        mask = ~np.isnan(slope_arr)
        if mask.sum() >= 5:
            try:
                result = theilslopes(slope_arr[mask], -days_arr[mask])  # flip sign: lower days_before = later
                ts_slope_trend = float(result.slope)
            except Exception:
                pass

    # Dip depth metrics (separate from production dip_depth_last90_delta — that's delta,
    # but we're capturing absolute dip in final period AND relationship with recovery slope)
    bl_dip = smean(baseline_dip, "dip_depth")
    f90_dip = smean(final_90_dip, "dip_depth")
    dip_delta90 = f90_dip - bl_dip if not np.isnan(f90_dip) and not np.isnan(bl_dip) else float("nan")

    # Recovery efficiency: recovery_slope / dip_depth (V/s per V of dip — does recovery slow relative to dip?)
    # Compare baseline vs final-90d
    re_bl = float("nan")
    re_f90 = float("nan")
    if len(baseline_rec.filter(pl.col("dip_depth").is_not_null())) >= 5:
        tmp = baseline_rec.filter(pl.col("dip_depth").is_not_null())
        re_bl = float((tmp["recovery_slope"] / tmp["dip_depth"].clip(lower_bound=0.1)).mean())
    if len(final_90_rec.filter(pl.col("dip_depth").is_not_null())) >= 3:
        tmp = final_90_rec.filter(pl.col("dip_depth").is_not_null())
        re_f90 = float((tmp["recovery_slope"] / tmp["dip_depth"].clip(lower_bound=0.1)).mean())
    recovery_efficiency_delta90 = re_f90 - re_bl if not np.isnan(re_f90) and not np.isnan(re_bl) else float("nan")

    vin_records.append({
        "vin_label": vin_label,
        "failed": int(failed),
        "n_events_with_slope": len(vs),
        "n_baseline": len(baseline_rec),
        "n_final_90": len(final_90_rec),
        "bl_recovery_slope": bl_slope,
        "f90_recovery_slope": f90_slope,
        "recovery_slope_delta90": slope_delta90,
        "recovery_slope_delta180": slope_delta180,
        "slow_recovery_rate_90": slow_rec_rate_90,
        "ts_recovery_slope_trend": ts_slope_trend,
        "bl_dip": bl_dip,
        "f90_dip": f90_dip,
        "dip_delta90": dip_delta90,
        "re_bl": re_bl,
        "re_f90": re_f90,
        "recovery_efficiency_delta90": recovery_efficiency_delta90,
    })

vin_df = pl.DataFrame(vin_records)
vin_df.write_csv(OUT / "P2_recovery_per_vin.csv")
print(f"Saved P2_recovery_per_vin.csv: {vin_df.shape}", file=sys.stderr)

# AUROC
y = vin_df["failed"].to_list()
auroc_rows = []
for metric in ["recovery_slope_delta90", "recovery_slope_delta180", "slow_recovery_rate_90",
               "ts_recovery_slope_trend", "dip_delta90", "recovery_efficiency_delta90",
               "f90_recovery_slope"]:
    scores = vin_df[metric].to_list()
    # Recovery slope DECREASING is bad, so we negate for AUROC (lower slope = more degraded)
    sign = -1 if "slope" in metric and "delta" not in metric else 1
    scores_s = [float(s) * sign if s is not None else float("nan") for s in scores]
    auc, n_f, n_nf = safe_auroc(y, scores_s)
    f_vals = [float(s) for s, yi in zip(scores, y) if yi == 1 and s is not None and not np.isnan(float(s))]
    nf_vals = [float(s) for s, yi in zip(scores, y) if yi == 0 and s is not None and not np.isnan(float(s))]
    d = cohens_d(f_vals, nf_vals)
    try:
        _, pval = mannwhitneyu(f_vals, nf_vals, alternative="two-sided")
    except Exception:
        pval = float("nan")
    auroc_rows.append({
        "metric": metric,
        "auroc": round(auc, 3) if not np.isnan(auc) else None,
        "cohens_d": round(d, 3) if not np.isnan(d) else None,
        "n_failed": n_f,
        "n_nf": n_nf,
        "mwu_pval": round(pval, 4) if not np.isnan(pval) else None,
        "density_confound": "per-event rate, density-robust",
    })

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P2_recovery_auroc.csv")
print("=== P2 AUROC ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)
print("P2 done.", file=sys.stderr)
