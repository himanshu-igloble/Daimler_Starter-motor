"""
P4 — Event-Level Separability at matched truck age.
Compute per-event features for all non-SMA-dead VINs, then assess F vs NF at MATCHED
truck age (same days_before_t_end range), reporting per-feature single AUROC.
Features (NOT in production set):
  - is_multi_attempt (session-based, proxy from retry_within_120s)
  - dur_s > 10s (extended crank)
  - dip_depth > 6V (deep dip)
  - recovery_slope < 1.0 (slow recovery, threshold from p25 of distribution)
  - engine_started_by_rpm (rpm_max_15s < 500)
Note: failed_crank_rate, retry_burst_rate are already production features at window level,
but we check event-level separability at MATCHED age (new angle).
Density confound: age-matched comparison with equal-depth windows.
Outputs: out/P4_event_features.csv, out/P4_event_auroc.csv
"""

import polars as pl
import numpy as np
from pathlib import Path
import sys
from sklearn.metrics import roc_auc_score
from scipy.stats import mannwhitneyu

REPO = Path("D:/Daimler-starter_motor_alternator_battery")
EVENTS = REPO / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"
OUT = REPO / "STARTER MOTOR/V2_program/probes/out"

SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

ev = pl.read_parquet(EVENTS)
ev = ev.filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
ev = ev.filter(pl.col("artifact") == False)

# Sort by VIN and timestamp
ev = ev.sort(["vin_label", "ts_start"])

# Compute inter-event gap for retry proxy
ev = ev.with_columns([
    pl.col("ts_start").diff().dt.total_seconds().over("vin_label").alias("gap_to_prev_s")
])

# Event-level binary features
ev = ev.with_columns([
    # Multi-attempt: retry within 120s (this is already in the raw event as retry_within_120s)
    pl.col("retry_within_120s").alias("is_retry"),
    # Extended crank: duration > 10s
    (pl.col("dur_s") > 10).alias("is_extended_crank"),
    # Very extended crank: duration > 20s
    (pl.col("dur_s") > 20).alias("is_very_extended_crank"),
    # Deep dip
    (pl.col("dip_depth") > 6.0).alias("is_deep_dip"),
    # Very deep dip
    (pl.col("dip_depth") > 8.0).alias("is_very_deep_dip"),
    # Failed engine start (RPM < 500 within 15s)
    ((pl.col("rpm_max_15s") < 500) & pl.col("rpm_max_15s").is_not_null()).alias("engine_fail_rpm"),
    # Slow recovery
    ((pl.col("recovery_slope") < 1.0) & pl.col("recovery_slope").is_not_null()).alias("is_slow_recovery"),
])

# Age-matched analysis: compare Failed vs NF in final-90d window
# (both groups' events within 90d of their respective t_end)
ev_final_90 = ev.filter(pl.col("days_before_t_end") <= 90)
print(f"Events in final-90d window: {len(ev_final_90)}", file=sys.stderr)
print(f"  Failed VINs: {ev_final_90.filter(pl.col('failed'))['vin_label'].n_unique()}", file=sys.stderr)
print(f"  NF VINs: {ev_final_90.filter(~pl.col('failed'))['vin_label'].n_unique()}", file=sys.stderr)

def safe_auroc_events(y, scores):
    """AUROC at event level (individual events as observations)."""
    mask = ~np.isnan(np.array(scores, dtype=float))
    y_arr = np.array(y, dtype=int)[mask]
    s_arr = np.array(scores, dtype=float)[mask]
    n_f = int(y_arr.sum())
    n_nf = int((1 - y_arr).sum())
    if n_f < 10 or n_nf < 10:
        return float("nan"), n_f, n_nf
    try:
        return roc_auc_score(y_arr, s_arr), n_f, n_nf
    except Exception:
        return float("nan"), n_f, n_nf

def safe_auroc_vin(y_vin, scores_vin):
    """AUROC at VIN level (per-VIN aggregated rate)."""
    mask = ~np.isnan(np.array(scores_vin, dtype=float))
    y_arr = np.array(y_vin, dtype=int)[mask]
    s_arr = np.array(scores_vin, dtype=float)[mask]
    n_f, n_nf = int(y_arr.sum()), int((1 - y_arr).sum())
    if n_f < 2 or n_nf < 2:
        return float("nan"), n_f, n_nf
    try:
        return roc_auc_score(y_arr, s_arr), n_f, n_nf
    except Exception:
        return float("nan"), n_f, n_nf

def cohens_d_events(y, vals):
    f = np.array([v for v, yi in zip(vals, y) if yi == 1 and not np.isnan(float(v)) if v is not None], dtype=float)
    n = np.array([v for v, yi in zip(vals, y) if yi == 0 and not np.isnan(float(v)) if v is not None], dtype=float)
    if len(f) < 2 or len(n) < 2: return float("nan")
    pooled = np.sqrt(((len(f)-1)*np.var(f,ddof=1) + (len(n)-1)*np.var(n,ddof=1)) / (len(f)+len(n)-2))
    return float("nan") if pooled == 0 else (np.mean(f) - np.mean(n)) / pooled

# Event-level analysis (note: pseudo-replication at event level — primary is VIN-level)
auroc_rows = []
ev_final_90 = ev_final_90.with_columns([
    pl.col("failed").cast(pl.Int32).alias("failed_int")
])

for feat in ["is_retry", "is_extended_crank", "is_very_extended_crank",
             "is_deep_dip", "is_very_deep_dip", "engine_fail_rpm", "is_slow_recovery",
             "dip_depth", "dur_s", "recovery_slope"]:
    col_data = ev_final_90[feat]
    if col_data.dtype == pl.Boolean:
        scores = col_data.cast(pl.Float64).to_list()
    else:
        scores = col_data.to_list()
    scores_f = [float(s) if s is not None else float("nan") for s in scores]
    y_ev = ev_final_90["failed_int"].to_list()
    auc_ev, n_f_ev, n_nf_ev = safe_auroc_events(y_ev, scores_f)

    # VIN-level rate for this feature (more honest)
    vin_rates = ev_final_90.group_by(["vin_label", "failed_int"]).agg(
        pl.col(feat).cast(pl.Float64).mean().alias("rate")
    ).sort("vin_label")
    auc_vin, n_f_vin, n_nf_vin = safe_auroc_vin(
        vin_rates["failed_int"].to_list(),
        vin_rates["rate"].to_list()
    )
    d = cohens_d_events(vin_rates["failed_int"].to_list(), vin_rates["rate"].to_list())
    try:
        fv = [v for v, y in zip(vin_rates["rate"].to_list(), vin_rates["failed_int"].to_list()) if y == 1 and v is not None]
        nv = [v for v, y in zip(vin_rates["rate"].to_list(), vin_rates["failed_int"].to_list()) if y == 0 and v is not None]
        _, pval = mannwhitneyu(fv, nv, alternative="two-sided") if len(fv) > 1 and len(nv) > 1 else (None, float("nan"))
    except Exception:
        pval = float("nan")

    auroc_rows.append({
        "feature": feat,
        "auroc_event_level": round(auc_ev, 3) if not np.isnan(auc_ev) else None,
        "auroc_vin_level": round(auc_vin, 3) if not np.isnan(auc_vin) else None,
        "cohens_d_vin": round(d, 3) if not np.isnan(d) else None,
        "n_failed_vins": n_f_vin,
        "n_nf_vins": n_nf_vin,
        "n_failed_events": n_f_ev,
        "n_nf_events": n_nf_ev,
        "mwu_pval_vin": round(pval, 4) if not np.isnan(pval) else None,
        "window": "final_90d",
        "note": "age_matched: both F and NF in final 90d of their own history"
    })

# Also check EXTENDED window: final-30d (higher signal?)
ev_final_30 = ev.filter(pl.col("days_before_t_end") <= 30)
for feat in ["is_retry", "is_extended_crank", "dip_depth", "dur_s"]:
    col_data = ev_final_30[feat]
    if col_data.dtype == pl.Boolean:
        scores = col_data.cast(pl.Float64).to_list()
    else:
        scores = col_data.to_list()
    vin_rates = ev_final_30.group_by(["vin_label", pl.col("failed").cast(pl.Int32).alias("failed_int")]).agg(
        pl.col(feat).cast(pl.Float64).mean().alias("rate")
    ).sort("vin_label")
    auc_vin, n_f_vin, n_nf_vin = safe_auroc_vin(
        vin_rates["failed_int"].to_list(),
        vin_rates["rate"].to_list()
    )
    auroc_rows.append({
        "feature": feat,
        "auroc_event_level": None,
        "auroc_vin_level": round(auc_vin, 3) if not np.isnan(auc_vin) else None,
        "cohens_d_vin": None,
        "n_failed_vins": n_f_vin,
        "n_nf_vins": n_nf_vin,
        "n_failed_events": None,
        "n_nf_events": None,
        "mwu_pval_vin": None,
        "window": "final_30d",
        "note": "short-horizon separability"
    })

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P4_event_auroc.csv")
print("=== P4 AUROC ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)

# Save enriched event table (sample)
sample = ev.filter(pl.col("days_before_t_end") <= 180).sample(min(5000, len(ev.filter(pl.col("days_before_t_end") <= 180))), seed=42)
sample.write_csv(OUT / "P4_event_features_sample.csv")
print("P4 done.", file=sys.stderr)
