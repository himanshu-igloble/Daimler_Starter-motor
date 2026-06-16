"""
P1 — Crank Session Anatomy (event-level, from cache/events)
Groups SMA crank events into sessions (gap < 60 s within same VIN+day).
Per session: n_attempts, total_dur, max_attempt_dur, inter_attempt_gap_median,
             baseline_vsi, min_vsi_session, dip_depth_session, engine_started.
Per VIN: session-metric distributions; final-90d and final-180d vs own baseline delta.
EXCLUDES SMA-dead cohort from session crank analyses.
Density-confound check: repeat per-row rate (events/day) normalized version.
Outputs: out/P1_sessions.csv, out/P1_session_metrics_per_vin.csv, out/P1_session_auroc.csv
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
OUT.mkdir(parents=True, exist_ok=True)

# SMA-dead cohort — exclude from crank session analyses
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}

# Production features (already known — don't re-derive)
KNOWN_FEATS = {
    "vsi_std_ratio_30d_L40", "vsi_withinwk_std_ratio_30d_w",
    "vsi_range_trend", "vsi_trend_persistence",
    "failed_crank_rate_last90", "retry_burst_rate_last90",
    "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
    "rest_vsi_p05_delta90", "dip_depth_last90_delta"
}

ev = pl.read_parquet(EVENTS)
print(f"Loaded {len(ev)} events, {ev['vin_label'].n_unique()} VINs", file=sys.stderr)

# Filter out SMA-dead
ev_active = ev.filter(~pl.col("vin_label").is_in(list(SMA_DEAD)))
print(f"After SMA-dead exclusion: {len(ev_active)} events, {ev_active['vin_label'].n_unique()} VINs", file=sys.stderr)

# Also filter artifact events
ev_active = ev_active.filter(pl.col("artifact") == False)
print(f"After artifact filter: {len(ev_active)} events", file=sys.stderr)

# Sort by VIN and timestamp
ev_active = ev_active.sort(["vin_label", "ts_start"])

# Compute inter-event gap within each VIN (seconds)
ev_active = ev_active.with_columns([
    pl.col("ts_start").diff().dt.total_seconds().over("vin_label").alias("gap_to_prev_s")
])

# Session assignment: new session when gap > 60s OR first event for VIN
ev_active = ev_active.with_columns([
    ((pl.col("gap_to_prev_s").is_null()) | (pl.col("gap_to_prev_s") > 60)).alias("is_session_start")
])

# Cumulative sum of session starts per VIN = session_id
ev_active = ev_active.with_columns([
    pl.col("is_session_start").cast(pl.Int32).cum_sum().over("vin_label").alias("session_id_local")
])

ev_active = ev_active.with_columns([
    (pl.col("vin_label") + "_s" + pl.col("session_id_local").cast(pl.String)).alias("session_key")
])

print(f"Sessions identified: {ev_active['session_key'].n_unique()}", file=sys.stderr)

# Aggregate to session level
# Use gap_to_prev_s for intra-session gap (only for events after session start)
# For inter-attempt gap within session: mean of gap_to_prev_s where > 0 within session
sessions = ev_active.group_by(["session_key", "vin_label", "failed"]).agg([
    pl.col("ts_start").min().alias("session_start"),
    pl.col("ts_start").max().alias("session_end"),
    pl.len().alias("n_attempts"),
    pl.col("dur_s").sum().alias("total_dur_s"),
    pl.col("dur_s").max().alias("max_attempt_dur_s"),
    pl.col("dur_s").mean().alias("mean_attempt_dur_s"),
    # inter-attempt gap (only non-null gaps within session)
    pl.col("gap_to_prev_s").filter(pl.col("gap_to_prev_s").is_not_null() & (pl.col("gap_to_prev_s") <= 60)).mean().alias("intra_session_gap_mean_s"),
    pl.col("gap_to_prev_s").filter(pl.col("gap_to_prev_s").is_not_null() & (pl.col("gap_to_prev_s") <= 60)).median().alias("intra_session_gap_median_s"),
    # VSI metrics
    pl.col("baseline_vsi").first().alias("pre_session_vsi"),  # baseline before first attempt
    pl.col("min_vsi_crank").min().alias("session_min_vsi"),
    pl.col("dip_depth").max().alias("session_max_dip"),
    pl.col("dip_depth").mean().alias("session_mean_dip"),
    # RPM outcome: did any attempt reach >500 RPM?
    (pl.col("rpm_max_15s").max() > 500).alias("engine_started"),
    # Success flag
    pl.col("success").any().alias("any_success"),
    pl.col("success").last().alias("final_success"),
    pl.col("days_before_t_end").min().alias("days_before_t_end"),
    # Recovery slope: mean over session
    pl.col("recovery_slope").mean().alias("mean_recovery_slope"),
])

print(f"Session table: {sessions.shape}", file=sys.stderr)
print(f"Multi-attempt sessions: {(sessions['n_attempts'] > 1).sum()}", file=sys.stderr)

# Flag multi-attempt sessions
sessions = sessions.with_columns([
    (pl.col("n_attempts") > 1).alias("is_multi_attempt"),
    pl.col("session_start").dt.date().alias("session_date"),
])

# Save sessions table
sessions.write_csv(OUT / "P1_sessions.csv")
print(f"Saved P1_sessions.csv: {sessions.shape}", file=sys.stderr)

# ===========================================================================
# Per-VIN session metrics: final-90d vs own baseline, final-180d vs baseline
# ===========================================================================
vin_records = []
for vin_label, failed in ev_active.select(["vin_label", "failed"]).unique().sort("vin_label").rows():
    vs = sessions.filter(pl.col("vin_label") == vin_label)
    if len(vs) == 0:
        continue

    # Get t_end: minimum days_before_t_end = 0 → that's t_end itself
    t_end_days = vs["days_before_t_end"].min()  # should be ~0 for failed, some number for NF

    # Baseline: events older than 180 days before t_end
    baseline = vs.filter(pl.col("days_before_t_end") > 180)
    final_90 = vs.filter(pl.col("days_before_t_end") <= 90)
    final_180 = vs.filter(pl.col("days_before_t_end") <= 180)

    if len(baseline) < 3:
        # Use > 90d as baseline if < 3 sessions in >180d
        baseline = vs.filter(pl.col("days_before_t_end") > 90)

    def safe_mean(df, col):
        if len(df) == 0 or df[col].is_null().all():
            return float("nan")
        vals = df[col].drop_nulls()
        return float(vals.mean()) if len(vals) > 0 else float("nan")

    def safe_rate(df, col):
        if len(df) == 0:
            return float("nan")
        return float(df[col].cast(pl.Float64).mean())

    # Key session metrics
    bl_multi_rate = safe_rate(baseline, "is_multi_attempt")
    bl_mean_dip = safe_mean(baseline, "session_max_dip")
    bl_mean_dur = safe_mean(baseline, "total_dur_s")
    bl_recovery_slope = safe_mean(baseline, "mean_recovery_slope")

    f90_multi_rate = safe_rate(final_90, "is_multi_attempt")
    f90_mean_dip = safe_mean(final_90, "session_max_dip")
    f90_mean_dur = safe_mean(final_90, "total_dur_s")
    f90_recovery_slope = safe_mean(final_90, "mean_recovery_slope")

    f180_multi_rate = safe_rate(final_180, "is_multi_attempt")
    f180_mean_dip = safe_mean(final_180, "session_max_dip")

    # Delta = final - baseline (positive = worse for multi/dip/dur)
    multi_rate_delta90 = f90_multi_rate - bl_multi_rate if not np.isnan(f90_multi_rate) and not np.isnan(bl_multi_rate) else float("nan")
    dip_delta90 = f90_mean_dip - bl_mean_dip if not np.isnan(f90_mean_dip) and not np.isnan(bl_mean_dip) else float("nan")
    dur_delta90 = f90_mean_dur - bl_mean_dur if not np.isnan(f90_mean_dur) and not np.isnan(bl_mean_dur) else float("nan")
    recovery_slope_delta90 = f90_recovery_slope - bl_recovery_slope if not np.isnan(f90_recovery_slope) and not np.isnan(bl_recovery_slope) else float("nan")

    vin_records.append({
        "vin_label": vin_label,
        "failed": failed,
        "n_sessions_total": len(vs),
        "n_sessions_baseline": len(baseline),
        "n_sessions_final_90": len(final_90),
        "n_sessions_final_180": len(final_180),
        # baseline rates
        "bl_multi_attempt_rate": bl_multi_rate,
        "bl_mean_session_dip": bl_mean_dip,
        "bl_mean_session_dur_s": bl_mean_dur,
        "bl_mean_recovery_slope": bl_recovery_slope,
        # final-90d rates
        "f90_multi_attempt_rate": f90_multi_rate,
        "f90_mean_session_dip": f90_mean_dip,
        "f90_mean_session_dur_s": f90_mean_dur,
        "f90_mean_recovery_slope": f90_recovery_slope,
        # final-180d rates
        "f180_multi_attempt_rate": f180_multi_rate,
        "f180_mean_session_dip": f180_mean_dip,
        # deltas
        "multi_rate_delta90": multi_rate_delta90,
        "dip_depth_delta90": dip_delta90,
        "session_dur_delta90": dur_delta90,
        "recovery_slope_delta90": recovery_slope_delta90,
    })

vin_df = pl.DataFrame(vin_records)
vin_df.write_csv(OUT / "P1_session_metrics_per_vin.csv")
print(f"Saved P1_session_metrics_per_vin.csv: {vin_df.shape}", file=sys.stderr)

# ===========================================================================
# AUROC for each metric, Failed vs NF (exclude NaN)
# ===========================================================================
from scipy.stats import rankdata

def safe_auroc(y, scores):
    """Return AUROC and n; handle ties and NaN."""
    mask = ~np.isnan(np.array(scores, dtype=float))
    y_arr = np.array(y, dtype=int)[mask]
    s_arr = np.array(scores, dtype=float)[mask]
    n_f = int(y_arr.sum())
    n_nf = int((1 - y_arr).sum())
    if n_f < 2 or n_nf < 2:
        return float("nan"), n_f, n_nf
    try:
        auc = roc_auc_score(y_arr, s_arr)
        return auc, n_f, n_nf
    except Exception:
        return float("nan"), n_f, n_nf

def cohens_d(failed_vals, nf_vals):
    f = np.array(failed_vals, dtype=float)
    n = np.array(nf_vals, dtype=float)
    f = f[~np.isnan(f)]
    n = n[~np.isnan(n)]
    if len(f) < 2 or len(n) < 2:
        return float("nan")
    pooled_std = np.sqrt((np.var(f, ddof=1) * (len(f)-1) + np.var(n, ddof=1) * (len(n)-1)) / (len(f) + len(n) - 2))
    if pooled_std == 0:
        return float("nan")
    return (np.mean(f) - np.mean(n)) / pooled_std

metrics_to_check = [
    "multi_rate_delta90", "dip_depth_delta90", "session_dur_delta90",
    "recovery_slope_delta90", "f90_multi_attempt_rate", "f90_mean_session_dip",
    "f90_mean_session_dur_s", "bl_multi_attempt_rate", "bl_mean_session_dip",
]

auroc_rows = []
y = vin_df["failed"].cast(pl.Int32).to_list()
for metric in metrics_to_check:
    scores = vin_df[metric].to_list()
    auc, n_f, n_nf = safe_auroc(y, scores)
    f_vals = [s for s, yi in zip(scores, y) if yi == 1 and not np.isnan(float(s) if s is not None else float("nan"))]
    nf_vals = [s for s, yi in zip(scores, y) if yi == 0 and not np.isnan(float(s) if s is not None else float("nan"))]
    d = cohens_d(f_vals, nf_vals)

    # MWU test
    try:
        stat, pval = mannwhitneyu(f_vals, nf_vals, alternative="two-sided")
    except Exception:
        pval = float("nan")

    auroc_rows.append({
        "metric": metric,
        "auroc": round(auc, 3) if not np.isnan(auc) else None,
        "cohens_d": round(d, 3) if not np.isnan(d) else None,
        "n_failed": n_f,
        "n_nf": n_nf,
        "mwu_pval": round(pval, 4) if not np.isnan(pval) else None,
        "note": "P1 session anatomy"
    })

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P1_session_auroc.csv")
print("=== P1 AUROC results ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)

# ===========================================================================
# Density-confound check:
# "multi_rate_delta90" computed on density-normalized events
# (events per active day, not raw count) — we recompute multi_rate as fraction
# of sessions that are multi-attempt, which is inherently density-normalized
# since it's a rate, not a count.
# We additionally check: correlation of metrics with n_sessions_total (proxy for density)
# ===========================================================================
n_sessions = vin_df["n_sessions_total"].to_list()
for metric in ["multi_rate_delta90", "dip_depth_delta90", "f90_multi_attempt_rate"]:
    vals = vin_df[metric].to_list()
    mask = [v is not None and not np.isnan(float(v)) for v in vals]
    v_clean = np.array([float(v) for v, m in zip(vals, mask) if m])
    n_clean = np.array([float(n) for n, m in zip(n_sessions, mask) if m])
    if len(v_clean) > 3:
        r = np.corrcoef(v_clean, n_clean)[0, 1]
        print(f"density_check: r({metric}, n_sessions_total)={r:.3f}", file=sys.stderr)

print("P1 done.", file=sys.stderr)
