"""
P6 — Serendipity: look for anomalous patterns not in any probe above.
Specifically checks:
  1. VSI baseline bimodality: are there VINs where vsi_rest_median shows two distinct levels
     (battery step-change not yet detected), and does this correlate with failure?
  2. Crank duration distribution shape: kurtosis / tail-heaviness of dur_s per VIN
     (heavy-tailed dur_s = occasional very long cranks = intermittent solenoid?)
  3. Day-of-week operational pattern: do failed trucks show different weekend vs weekday
     crank patterns (proxy for route/duty cycle alignment with failure)?
  4. "Crank silence before storm": are there VINs with a period of zero crank events
     (due to low usage) followed by a burst of failed cranks? — different from E4 "silent gap"
     which was telemetry gaps; this is operational silence (truck parked) then restart.
  5. VSI drive mean decline: does vsi_drive_mean trend downward (not just std going up)?
     Production features capture std, not level. A declining mean could indicate regulator
     output drop (failing alternator stressing starter).
Outputs: out/P6_serendipity_metrics.csv, out/P6_serendipity_auroc.csv
"""

import polars as pl
import numpy as np
from pathlib import Path
import sys
from sklearn.metrics import roc_auc_score
from scipy.stats import mannwhitneyu, theilslopes, kurtosis
from scipy.stats import skew

REPO = Path("D:/Daimler-starter_motor_alternator_battery")
WEEKLY_DIR = REPO / "STARTER MOTOR/cache/weekly"
EVENTS = REPO / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"
OUT = REPO / "STARTER MOTOR/V2_program/probes/out"

SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

# Load fleet weekly
weekly_frames = []
for f in sorted(WEEKLY_DIR.glob("*.parquet")):
    wk = pl.read_parquet(f)
    weekly_frames.append(wk)
fleet_weekly = pl.concat(weekly_frames).sort(["vin_label", "week"])

# Load crank events
ev = pl.read_parquet(EVENTS)
ev = ev.filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
ev = ev.filter(pl.col("artifact") == False)
ev = ev.sort(["vin_label", "ts_start"])
ev = ev.with_columns([
    pl.col("ts_start").dt.weekday().alias("weekday"),  # 0=Mon..6=Sun
    pl.col("ts_start").dt.date().alias("date"),
])

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

vin_records = []
vins = fleet_weekly.select(["vin_label", "failed"]).unique().sort("vin_label")

for vin_label, failed in vins.rows():
    vw = fleet_weekly.filter(pl.col("vin_label") == vin_label).sort("week")
    ve = ev.filter(pl.col("vin_label") == vin_label)
    n_weeks_v = len(vw)
    if n_weeks_v < 4:
        vin_records.append({"vin_label": vin_label, "failed": int(failed), "n_weeks": n_weeks_v})
        continue

    # 1. vsi_drive_mean trend (level decline, not just std rise)
    drive_mean = vw["vsi_drive_mean"].drop_nulls().to_numpy().astype(float)
    ts_drive_mean_slope = float("nan")
    if len(drive_mean) >= 5:
        try:
            res = theilslopes(drive_mean, np.arange(len(drive_mean)))
            ts_drive_mean_slope = float(res.slope)
        except Exception:
            pass

    # Delta final-90d vs baseline
    # We'll use weeks as proxy (last 13 weeks = ~90d vs earlier)
    n_w = len(vw)
    last_13 = min(13, n_w)
    dm_final = vw["vsi_drive_mean"].tail(last_13).drop_nulls()
    dm_early = vw["vsi_drive_mean"].head(max(1, n_w - last_13)).drop_nulls()
    drive_mean_delta = float("nan")
    if len(dm_final) >= 2 and len(dm_early) >= 2:
        drive_mean_delta = float(dm_final.mean()) - float(dm_early.mean())

    # 2. Crank duration kurtosis (heavy tail = occasional very long cranks)
    dur_vals = ve["dur_s"].drop_nulls().to_numpy().astype(float)
    dur_kurtosis = float("nan")
    dur_p95 = float("nan")
    dur_p95_over_p50 = float("nan")
    if len(dur_vals) >= 10:
        dur_kurtosis = float(kurtosis(dur_vals, fisher=True))
        dur_p95 = float(np.percentile(dur_vals, 95))
        dur_p50 = float(np.percentile(dur_vals, 50))
        dur_p95_over_p50 = dur_p95 / dur_p50 if dur_p50 > 0 else float("nan")

    # 3. Weekend vs weekday crank failure rate
    we_fail_rate = float("nan")
    wd_fail_rate = float("nan")
    weekend_weekday_ratio = float("nan")
    if len(ve) >= 10 and "success" in ve.columns:
        ve_valid = ve.filter(pl.col("success").is_not_null())
        if len(ve_valid) >= 10:
            we = ve_valid.filter(pl.col("weekday") >= 5)  # Sat=5, Sun=6
            wd = ve_valid.filter(pl.col("weekday") < 5)
            if len(we) >= 5:
                we_fail_rate = float(1 - we["success"].cast(pl.Float64).mean())
            if len(wd) >= 5:
                wd_fail_rate = float(1 - wd["success"].cast(pl.Float64).mean())
            if not np.isnan(we_fail_rate) and not np.isnan(wd_fail_rate) and wd_fail_rate > 0:
                weekend_weekday_ratio = we_fail_rate / wd_fail_rate

    # 4. "Silence before storm": max consecutive days with 0 crank events in final 180d,
    #    followed by a day with ≥2 failed cranks
    silence_before_storm = 0
    if len(ve) >= 5:
        final_180 = ve.filter(pl.col("days_before_t_end") <= 180).sort("ts_start")
        if len(final_180) >= 5:
            # Get daily event counts and failure counts
            daily_ev = final_180.group_by("date").agg([
                pl.len().alias("n_events"),
                (pl.col("success") == False).sum().alias("n_failed_cranks"),
            ]).sort("date")
            if len(daily_ev) >= 5:
                dates = daily_ev["date"].to_list()
                n_ev = daily_ev["n_events"].to_list()
                n_fail = daily_ev["n_failed_cranks"].to_list()
                # Find: any sequence of >=3 consecutive dates with 0 events, then a date with n_fail >= 2
                from datetime import timedelta
                max_silence = 0
                i = 0
                while i < len(dates) - 1:
                    if n_ev[i] == 0:
                        silence_len = 1
                        j = i + 1
                        while j < len(dates) and n_ev[j] == 0:
                            silence_len += 1
                            j += 1
                        # After silence, is there a storm?
                        if j < len(dates) and n_fail[j] >= 2 and silence_len >= 3:
                            max_silence = max(max_silence, silence_len)
                        i = j
                    else:
                        i += 1
                silence_before_storm = max_silence

    # 5. VSI rest bimodality proxy: coefficient of variation of vsi_rest_median over lifetime
    #    (high CV = two regimes, possible battery step)
    rest_cv = float("nan")
    rest_median_vals = vw["vsi_rest_median"].drop_nulls().to_numpy().astype(float)
    if len(rest_median_vals) >= 8:
        mean_r = np.mean(rest_median_vals)
        std_r = np.std(rest_median_vals)
        rest_cv = std_r / mean_r if mean_r > 0 else float("nan")

    vin_records.append({
        "vin_label": vin_label,
        "failed": int(failed),
        "n_weeks": n_weeks_v,
        "ts_drive_mean_slope_per_week": ts_drive_mean_slope,
        "drive_mean_delta_last90d": drive_mean_delta,
        "dur_kurtosis": dur_kurtosis,
        "dur_p95_over_p50": dur_p95_over_p50,
        "dur_p95": dur_p95,
        "weekend_weekday_fail_ratio": weekend_weekday_ratio,
        "silence_before_storm_days": float(silence_before_storm),
        "rest_vsi_median_cv": rest_cv,
        "n_crank_events": len(ve),
    })

vin_df = pl.DataFrame(vin_records)
vin_df.write_csv(OUT / "P6_serendipity_metrics.csv")
print(f"Saved P6_serendipity_metrics.csv: {vin_df.shape}", file=sys.stderr)

y = vin_df["failed"].to_list()
auroc_rows = []
for metric in ["ts_drive_mean_slope_per_week", "drive_mean_delta_last90d",
               "dur_kurtosis", "dur_p95_over_p50",
               "weekend_weekday_fail_ratio", "silence_before_storm_days",
               "rest_vsi_median_cv"]:
    scores = vin_df[metric].to_list() if metric in vin_df.columns else [float("nan")] * len(y)
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
        "probe": "P6_serendipity",
    })

# Density check for drive_mean_slope: correlation with n_weeks
n_weeks = vin_df["n_weeks"].to_list()
for metric in ["ts_drive_mean_slope_per_week", "drive_mean_delta_last90d", "dur_kurtosis"]:
    vals = vin_df[metric].to_list() if metric in vin_df.columns else [float("nan")] * len(y)
    v_arr = [float(s) if s is not None else float("nan") for s in vals]
    mask = [not np.isnan(v) and not np.isnan(float(n)) for v, n in zip(v_arr, n_weeks)]
    v_c = np.array([v for v, m in zip(v_arr, mask) if m])
    n_c = np.array([float(n) for n, m in zip(n_weeks, mask) if m])
    if len(v_c) > 3:
        r = np.corrcoef(v_c, n_c)[0, 1]
        print(f"density_check P6: r({metric}, n_weeks)={r:.3f}", file=sys.stderr)

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P6_serendipity_auroc.csv")
print("=== P6 AUROC ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)
print("P6 done.", file=sys.stderr)
