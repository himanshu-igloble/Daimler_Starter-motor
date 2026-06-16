"""Probe 6 — VIN-level single-feature AUROC screen over underutilized signals
(events parquet + weekly caches + probe3/4/5 outputs) AND pure data-volume
leakage features. Mann-Whitney AUROC, failed=positive class.
"""
import polars as pl
import numpy as np
from pathlib import Path
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "STARTER MOTOR/V1.1/audit"
WK = ROOT / "STARTER MOTOR/cache/weekly"
EV = ROOT / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"

# ---------- per-VIN aggregates from weekly caches ----------
wk = pl.concat([pl.read_parquet(p) for p in sorted(WK.glob("*.parquet"))])
wk_vin = (
    wk.group_by("vin_label", "failed")
    .agg(
        pl.col("n_rows").sum().alias("total_rows"),
        pl.len().alias("n_weeks"),
        pl.col("active_days").sum().alias("active_days_total"),
        (pl.col("n_rows").sum() / pl.len()).alias("rows_per_week"),
        pl.col("vsi_rest_median").median().alias("vsi_rest_median_med"),
        pl.col("vsi_rest_p05").median().alias("vsi_rest_p05_med"),
        pl.col("vsi_drive_mean").median().alias("vsi_drive_mean_med"),
        pl.col("vsi_drive_std").median().alias("vsi_drive_std_med"),
        pl.col("vsi_drive_p95").quantile(0.9).alias("vsi_drive_p95_q90"),
        (pl.col("vsi_below_21_rows").sum() / pl.col("vsi_obs_rows").sum()).alias("vsi_below21_rate"),
        (pl.col("vsi_above_32_rows").sum() / pl.col("vsi_obs_rows").sum()).alias("vsi_above32_rate"),
        pl.col("rpm_mean").median().alias("rpm_mean_med"),
        pl.col("csp_mean").median().alias("csp_mean_med"),
        pl.col("anr_pos_mean").median().alias("anr_pos_mean_med"),
        (pl.col("sma1_rows").sum() / pl.col("active_days").sum()).alias("sma1_per_active_day"),
        (pl.col("ged3_rows").sum() / pl.col("n_rows").sum()).alias("ged3_rate"),
        # week-density volatility (leakage probe)
        (pl.col("n_rows").std() / pl.col("n_rows").mean()).alias("rows_week_cv"),
        (pl.col("active_days") < 2).sum().alias("weeks_lt2_active"),
    )
)

# ---------- per-VIN aggregates from crank events ----------
ev = pl.read_parquet(EV).filter(~pl.col("artifact"))
ev_vin = (
    ev.group_by("vin_label")
    .agg(
        pl.len().alias("n_events"),
        pl.col("dur_s").filter(pl.col("multi_sample")).median().alias("crank_dur_med_ms"),
        pl.col("dip_depth").median().alias("dip_depth_med"),
        pl.col("dip_depth").quantile(0.9).alias("dip_depth_p90"),
        pl.col("recovery_slope").median().alias("recovery_slope_med"),
        pl.col("rpm_max_15s").median().alias("rpm_max15_med"),
        pl.col("rpm_max_15s").quantile(0.1).alias("rpm_max15_p10"),
        pl.col("success").mean().alias("success_rate"),
        pl.col("retry_within_120s").mean().alias("retry_rate"),
        pl.col("baseline_vsi").median().alias("baseline_vsi_med"),
        pl.col("min_vsi_crank").median().alias("min_vsi_crank_med"),
        pl.col("min_vsi_crank").quantile(0.05).alias("min_vsi_crank_p05"),
    )
)

# ---------- probe3/4/5 outputs ----------
p3 = pl.read_csv(OUT / "probe3_dt_gaps_per_vin.csv").select(
    "vin_label", "n_gaps_1h_1d", "n_gaps_gt1d", "dt_p99")
p4 = pl.read_csv(OUT / "probe4_vsi_stuck_baseline_per_vin.csv").select(
    "vin_label", "vsi_drive_median", "vsi_drive_std", "n_runs_ge30min", "max_stuck_run")
p5 = pl.read_csv(OUT / "probe5_rest_bout_decay_per_vin.csv")

m = (
    wk_vin.join(ev_vin, on="vin_label", how="left")
    .join(p3, on="vin_label", how="left")
    .join(p4, on="vin_label", how="left")
    .join(p5, on="vin_label", how="left")
    .with_columns((pl.col("n_events") / pl.col("active_days_total")).alias("events_per_active_day"))
)
m.write_csv(OUT / "probe6_vin_feature_matrix.csv")

y = m["failed"].to_numpy()
rows = []
for c in m.columns:
    if c in ("vin_label", "failed"):
        continue
    x = m[c].to_numpy().astype(float)
    ok = ~np.isnan(x)
    if ok.sum() < 10 or len(np.unique(x[ok])) < 3:
        continue
    yf, xv = y[ok], x[ok]
    nF, nNF = int(yf.sum()), int((~yf).sum())
    if nF < 5 or nNF < 5:
        continue
    u, p = mannwhitneyu(xv[yf], xv[~yf], alternative="two-sided")
    auc = u / (nF * nNF)
    rows.append({"feature": c, "auroc_F_high": round(auc, 3),
                 "auroc_directional": round(max(auc, 1 - auc), 3),
                 "p_mwu": round(p, 4), "nF": nF, "nNF": nNF,
                 "mean_F": round(float(np.nanmean(xv[yf])), 4),
                 "mean_NF": round(float(np.nanmean(xv[~yf])), 4)})
scr = pl.DataFrame(rows).sort("auroc_directional", descending=True)
scr.write_csv(OUT / "probe6_single_feature_auroc.csv")
with pl.Config(tbl_rows=60, tbl_width_chars=200, fmt_str_lengths=30):
    print(scr)
