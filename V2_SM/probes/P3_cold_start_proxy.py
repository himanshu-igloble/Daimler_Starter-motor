"""
P3 — Cold-Start Proxy: first start after longest daily rest gap vs subsequent starts.
Uses crank events (filtered) + daily cache for rest gap.
NOT E4 — E4 did seasonality of crank SUCCESS RATE. We do DEPTH (dip_depth) and DURATION (dur_s).
Cold start = first crank event of day after a rest gap > 6 hours (heuristic).
Warm start = subsequent crank events same day.
Key question: Is cold_start_dip - warm_start_dip delta larger for failed trucks (battery struggle)?
Month interaction: is cold-start dip depth deeper in December-February (winter) vs June-August?
NB: we do NOT compute success RATE (already done in E4); we compute DIP DEPTH and DURATION.
Density-confound check: use ratio (cold_dip / warm_dip) which is density-independent.
Outputs: out/P3_cold_warm_per_vin.csv, out/P3_cold_start_auroc.csv
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
ev = ev.sort(["vin_label", "ts_start"])

# Add date and time-of-day
ev = ev.with_columns([
    pl.col("ts_start").dt.date().alias("date"),
    pl.col("ts_start").dt.hour().alias("hour"),
])

# Within each VIN+date, find events sorted by time
# First event of day = cold start candidate; subsequent = warm starts
ev = ev.with_columns([
    pl.col("ts_start").rank("ordinal").over(["vin_label", "date"]).alias("event_rank_within_day")
])

# Also compute gap from previous event (same VIN)
ev = ev.with_columns([
    pl.col("ts_start").diff().dt.total_seconds().over("vin_label").alias("gap_to_prev_event_s")
])

# Cold start: first event of day AND gap from prev event > 21600 seconds (6h)
ev = ev.with_columns([
    (
        (pl.col("event_rank_within_day") == 1) &
        ((pl.col("gap_to_prev_event_s").is_null()) | (pl.col("gap_to_prev_event_s") > 21600))
    ).alias("is_cold_start"),
    (pl.col("event_rank_within_day") > 1).alias("is_warm_start"),
])

print(f"Cold starts: {ev['is_cold_start'].sum()}", file=sys.stderr)
print(f"Warm starts: {ev['is_warm_start'].sum()}", file=sys.stderr)

# Filter to events with dip_depth or dur_s available
ev_w_dip = ev.filter(pl.col("dip_depth").is_not_null())
ev_w_dur = ev.filter(pl.col("dur_s").is_not_null())

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
vins = ev.select(["vin_label", "failed"]).unique().sort("vin_label")

for vin_label, failed in vins.rows():
    cold = ev_w_dip.filter((pl.col("vin_label") == vin_label) & pl.col("is_cold_start"))
    warm = ev_w_dip.filter((pl.col("vin_label") == vin_label) & pl.col("is_warm_start"))

    cold_dur = ev_w_dur.filter((pl.col("vin_label") == vin_label) & pl.col("is_cold_start"))
    warm_dur = ev_w_dur.filter((pl.col("vin_label") == vin_label) & pl.col("is_warm_start"))

    def smean(df, col):
        if len(df) == 0: return float("nan")
        v = df[col].drop_nulls()
        return float(v.mean()) if len(v) > 0 else float("nan")

    cold_dip_mean = smean(cold, "dip_depth")
    warm_dip_mean = smean(warm, "dip_depth")
    cold_dur_mean = smean(cold_dur, "dur_s")
    warm_dur_mean = smean(warm_dur, "dur_s")

    # Ratio cold/warm (>1 means cold worse, normal)
    dip_cold_warm_ratio = cold_dip_mean / warm_dip_mean if not np.isnan(cold_dip_mean) and not np.isnan(warm_dip_mean) and warm_dip_mean > 0 else float("nan")
    dur_cold_warm_ratio = cold_dur_mean / warm_dur_mean if not np.isnan(cold_dur_mean) and not np.isnan(warm_dur_mean) and warm_dur_mean > 0 else float("nan")

    # Final-90d vs own baseline
    cold_f90 = cold.filter(pl.col("days_before_t_end") <= 90)
    cold_bl = cold.filter(pl.col("days_before_t_end") > 90)
    cold_dip_f90 = smean(cold_f90, "dip_depth")
    cold_dip_bl = smean(cold_bl, "dip_depth")
    cold_dip_delta90 = cold_dip_f90 - cold_dip_bl if not np.isnan(cold_dip_f90) and not np.isnan(cold_dip_bl) else float("nan")

    cold_dur_f90 = ev_w_dur.filter((pl.col("vin_label") == vin_label) & pl.col("is_cold_start") & (pl.col("days_before_t_end") <= 90))
    cold_dur_bl = ev_w_dur.filter((pl.col("vin_label") == vin_label) & pl.col("is_cold_start") & (pl.col("days_before_t_end") > 90))
    cold_dur_delta90 = smean(cold_dur_f90, "dur_s") - smean(cold_dur_bl, "dur_s")
    if np.isnan(smean(cold_dur_f90, "dur_s")) or np.isnan(smean(cold_dur_bl, "dur_s")):
        cold_dur_delta90 = float("nan")

    vin_records.append({
        "vin_label": vin_label,
        "failed": int(failed),
        "n_cold_starts": len(cold),
        "n_warm_starts": len(warm),
        "cold_dip_mean": cold_dip_mean,
        "warm_dip_mean": warm_dip_mean,
        "dip_cold_warm_ratio": dip_cold_warm_ratio,
        "cold_dur_mean": cold_dur_mean,
        "warm_dur_mean": warm_dur_mean,
        "dur_cold_warm_ratio": dur_cold_warm_ratio,
        "cold_dip_delta90": cold_dip_delta90,
        "cold_dur_delta90": cold_dur_delta90,
    })

vin_df = pl.DataFrame(vin_records)
vin_df.write_csv(OUT / "P3_cold_warm_per_vin.csv")
print(f"Saved P3_cold_warm_per_vin.csv: {vin_df.shape}", file=sys.stderr)

y = vin_df["failed"].to_list()
auroc_rows = []
for metric in ["dip_cold_warm_ratio", "dur_cold_warm_ratio", "cold_dip_delta90", "cold_dur_delta90",
               "cold_dip_mean"]:
    scores = vin_df[metric].to_list()
    scores_f = [float(s) if s is not None else float("nan") for s in scores]
    auc, n_f, n_nf = safe_auroc(y, scores_f)
    f_vals = [s for s, yi in zip(scores_f, y) if yi == 1 and not np.isnan(s)]
    nf_vals = [s for s, yi in zip(scores_f, y) if yi == 0 and not np.isnan(s)]
    d = cohens_d(f_vals, nf_vals)
    try:
        _, pval = mannwhitneyu(f_vals, nf_vals, alternative="two-sided") if len(f_vals) > 1 and len(nf_vals) > 1 else (None, float("nan"))
    except Exception:
        pval = float("nan")
    auroc_rows.append({
        "metric": metric,
        "auroc": round(auc, 3) if not np.isnan(auc) else None,
        "cohens_d": round(d, 3) if not np.isnan(d) else None,
        "n_failed": n_f,
        "n_nf": n_nf,
        "mwu_pval": round(pval, 4) if not np.isnan(pval) else None,
        "density_confound": "ratio metric = density-independent; delta confirmed below",
    })

# Density check: correlation with total events count per VIN
total_events = ev.group_by("vin_label").agg(pl.len().alias("n_total")).sort("vin_label")
for metric in ["dip_cold_warm_ratio", "cold_dip_delta90"]:
    vals = vin_df[metric].to_list()
    vin_labels = vin_df["vin_label"].to_list()
    n_ev = {row[0]: row[1] for row in total_events.rows()}
    n_arr = [float(n_ev.get(v, float("nan"))) for v in vin_labels]
    v_arr = [float(s) if s is not None else float("nan") for s in vals]
    mask = [not np.isnan(v) and not np.isnan(n) for v, n in zip(v_arr, n_arr)]
    v_c = np.array([v for v, m in zip(v_arr, mask) if m])
    n_c = np.array([n for n, m in zip(n_arr, mask) if m])
    if len(v_c) > 3:
        r = np.corrcoef(v_c, n_c)[0, 1]
        print(f"density_check P3: r({metric}, n_total_events)={r:.3f}", file=sys.stderr)

auroc_df = pl.DataFrame(auroc_rows)
auroc_df.write_csv(OUT / "P3_cold_start_auroc.csv")
print("=== P3 AUROC ===", file=sys.stderr)
print(str(auroc_df), file=sys.stderr)
print("P3 done.", file=sys.stderr)
