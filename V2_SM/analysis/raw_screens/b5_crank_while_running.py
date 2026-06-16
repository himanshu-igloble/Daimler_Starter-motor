"""
B5 — True Crank-While-Running (CWR) Screen
Physics: starter engaged while engine already running (RPM >400 BEFORE SMA=1 onset).
Excludes normal crank spin-up (RPM rising from ~0 during the SMA=1 window).

Definition: row where SMA==1 AND RPM>400 AND prev_row (same VIN, gap<=10s)
also had RPM>400 (SMA was 0 or 1 — engine was already turning at engagement start).

Episode grouping: consecutive qualifying rows within same VIN, gap <=10s.
SMA-dead trucks excluded: VIN8_F, VIN9_F, VIN10_NF, VIN11_NF, VIN12_NF, VIN13_NF, VIN20_NF.

Runtime note: processes all 14 failed VINs + 10 largest active NF VINs (by row count).
"""

import polars as pl
import numpy as np
from scipy.stats import mannwhitneyu
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path("D:/Daimler-starter_motor_alternator_battery")
FAILED_PARQ = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
NF_PARQ = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
DQ_CSV = ROOT / "STARTER MOTOR/results/V1_SM_data_quality.csv"
OUT_DIR = ROOT / "STARTER MOTOR/V2_program/analysis/raw_screens/out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RPM_SENTINEL = 65535.0
RPM_THRESH = 400.0
GAP_THRESH_S = 10.0

# SMA-dead trucks (>99% SMA null)
SMA_DEAD = {"VIN8", "VIN9"}  # failed
SMA_DEAD_NF = {"VIN10", "VIN11", "VIN12", "VIN13", "VIN20"}  # NF

# Load data quality for truck-year normalization
dq = pl.read_csv(DQ_CSV)
dq_map = {
    row["vin_label"]: row["active_days_total"]
    for row in dq.iter_rows(named=True)
}

# NF top-10 active (by row count, excluding SMA-dead)
NF_TOP10_ACTIVE = ["VIN16", "VIN18", "VIN1", "VIN20", "VIN4",
                   "VIN7", "VIN17", "VIN8", "VIN5", "VIN19"]
# Remove SMA-dead from NF list (VIN10,11,12,13,20 dead; VIN20 is in top-10 => remove it)
NF_PROCESS = [v for v in NF_TOP10_ACTIVE if v not in SMA_DEAD_NF]
print(f"NF VINs to process (top-10 active, excl. SMA-dead): {NF_PROCESS}")


def process_vin(df_vin: pl.DataFrame, vin_raw: str, failed: bool) -> dict:
    """
    For one VIN: sort by timestamp, filter sentinels, apply CWR definition,
    group into episodes (gap<=10s), return summary dict.
    """
    label = f"{vin_raw}_F_SM" if failed else f"{vin_raw}_NF_SM"
    active_days = dq_map.get(label, None)

    # Filter sentinel RPM and null
    df = (
        df_vin
        .filter(pl.col("VIN") == vin_raw)
        .select(["timestamp", "RPM", "SMA"])
        .filter(
            pl.col("RPM").is_not_null() &
            pl.col("SMA").is_not_null() &
            (pl.col("RPM") < RPM_SENTINEL)
        )
        .sort("timestamp")
    )

    if df.height < 2:
        return {
            "vin_label": label, "failed": failed,
            "n_rows_valid": df.height, "n_cwr_rows": 0,
            "n_episodes": 0, "active_days": active_days,
            "ep_per_truck_yr": 0.0, "note": "too few rows"
        }

    # Compute previous-row values within this VIN
    df = df.with_columns([
        pl.col("timestamp").shift(1).alias("prev_ts"),
        pl.col("RPM").shift(1).alias("prev_rpm"),
        pl.col("SMA").shift(1).alias("prev_sma"),
    ])

    # Gap in seconds
    df = df.with_columns([
        (
            (pl.col("timestamp").cast(pl.Int64) - pl.col("prev_ts").cast(pl.Int64)) / 1_000_000
        ).alias("gap_s")
    ])

    # CWR condition: current SMA==1, RPM>400, gap<=10s, prev_rpm>400
    cwr = df.filter(
        (pl.col("SMA") == 1.0) &
        (pl.col("RPM") > RPM_THRESH) &
        (pl.col("gap_s") <= GAP_THRESH_S) &
        (pl.col("prev_rpm") > RPM_THRESH)
    )

    n_cwr_rows = cwr.height

    if n_cwr_rows == 0:
        ep_per_yr = 0.0
        n_eps = 0
    else:
        # Episode grouping: group consecutive CWR rows with gap<=10s
        cwr_sorted = cwr.sort("timestamp")
        ts_vals = cwr_sorted["timestamp"].cast(pl.Int64).to_numpy() / 1_000_000  # seconds
        gaps = np.diff(ts_vals, prepend=ts_vals[0] - 999)
        episode_id = np.cumsum(gaps > GAP_THRESH_S)
        n_eps = int(episode_id[-1]) + 1 if n_cwr_rows > 0 else 0
        ep_per_yr = (n_eps / active_days * 365.25) if active_days and active_days > 0 else float("nan")

    return {
        "vin_label": label, "failed": failed,
        "n_rows_valid": df.height, "n_cwr_rows": n_cwr_rows,
        "n_episodes": n_eps if n_cwr_rows > 0 else 0,
        "active_days": active_days,
        "ep_per_truck_yr": round(ep_per_yr, 3) if n_cwr_rows > 0 else 0.0,
        "note": ""
    }


def final_90d_vs_baseline(df_vin: pl.DataFrame, vin_raw: str, t_end_str: str) -> dict:
    """Episode rate in final 90 days vs remaining baseline for one failed VIN."""
    label = f"{vin_raw}_F_SM"
    df = (
        df_vin
        .filter(pl.col("VIN") == vin_raw)
        .select(["timestamp", "RPM", "SMA"])
        .filter(
            pl.col("RPM").is_not_null() &
            pl.col("SMA").is_not_null() &
            (pl.col("RPM") < RPM_SENTINEL)
        )
        .sort("timestamp")
    )
    if df.height < 2:
        return {"vin_label": label, "ep_final90": 0, "ep_baseline": 0,
                "ep_rate_final90": float("nan"), "ep_rate_baseline": float("nan"), "note": "too few rows"}

    df = df.with_columns([
        pl.col("timestamp").shift(1).alias("prev_ts"),
        pl.col("RPM").shift(1).alias("prev_rpm"),
        pl.col("SMA").shift(1).alias("prev_sma"),
    ])
    df = df.with_columns([
        ((pl.col("timestamp").cast(pl.Int64) - pl.col("prev_ts").cast(pl.Int64)) / 1_000_000).alias("gap_s")
    ])
    cwr = df.filter(
        (pl.col("SMA") == 1.0) &
        (pl.col("RPM") > RPM_THRESH) &
        (pl.col("gap_s") <= GAP_THRESH_S) &
        (pl.col("prev_rpm") > RPM_THRESH)
    )

    t_end_val = df["timestamp"].max()
    # Compute cutoff as Python datetime
    import datetime
    t_end_dt = t_end_val
    t_cutoff_dt = t_end_dt - datetime.timedelta(days=90)
    t_cutoff_pl = pl.lit(t_cutoff_dt)

    final_cwr = cwr.filter(pl.col("timestamp") >= t_cutoff_pl)
    base_cwr = cwr.filter(pl.col("timestamp") < t_cutoff_pl)

    # Episode count in each window
    def count_eps(ts_series):
        if len(ts_series) == 0:
            return 0
        ts_vals = ts_series.cast(pl.Int64).to_numpy() / 1_000_000
        gaps = np.diff(ts_vals, prepend=ts_vals[0] - 999)
        return int(np.cumsum(gaps > GAP_THRESH_S)[-1]) + 1

    ep_f = count_eps(final_cwr["timestamp"])
    ep_b = count_eps(base_cwr["timestamp"])
    active_days_val = dq_map.get(label, 90)
    base_days = max(int(active_days_val) - 90, 1)

    return {
        "vin_label": label,
        "ep_final90": ep_f,
        "ep_baseline": ep_b,
        "ep_rate_final90_per_yr": round(ep_f / 90 * 365.25, 2),
        "ep_rate_baseline_per_yr": round(ep_b / max(dq_map.get(label, 90) - 90, 1) * 365.25, 2),
        "note": ""
    }


print("Loading failed parquet (all 14 VINs)...")
lf_f = pl.scan_parquet(FAILED_PARQ).select(["VIN", "timestamp", "RPM", "SMA"])
df_f = lf_f.collect()
print(f"  Loaded {df_f.height:,} rows")

print("Loading NF parquet (top-10 active VINs)...")
lf_nf = pl.scan_parquet(NF_PARQ).filter(pl.col("VIN").is_in(NF_PROCESS)).select(["VIN", "timestamp", "RPM", "SMA"])
df_nf = lf_nf.collect()
print(f"  Loaded {df_nf.height:,} rows")

# Process failed VINs (all 14; skip SMA-dead)
failed_vins = [f"VIN{i}" for i in range(1, 15)]
results_f = []
for v in failed_vins:
    label = f"{v}_F_SM"
    if v in SMA_DEAD:
        results_f.append({
            "vin_label": label, "failed": True,
            "n_rows_valid": 0, "n_cwr_rows": 0,
            "n_episodes": 0, "active_days": dq_map.get(label),
            "ep_per_truck_yr": float("nan"), "note": "SMA_DEAD_EXCLUDED"
        })
        continue
    print(f"  Processing {label}...")
    results_f.append(process_vin(df_f, v, True))

# Process active NF VINs
results_nf = []
for v in NF_PROCESS:
    label = f"{v}_NF_SM"
    print(f"  Processing {label}...")
    results_nf.append(process_vin(df_nf, v, False))

all_results = results_f + results_nf
per_vin_df = pl.DataFrame(all_results)
per_vin_csv = OUT_DIR / "B5_cwr_per_vin.csv"
per_vin_df.write_csv(per_vin_csv)
print(f"\nPer-VIN results saved to {per_vin_csv}")
print(per_vin_df.select(["vin_label", "n_episodes", "ep_per_truck_yr", "note"]))

# Mann-Whitney test: F vs NF episodes/truck-yr (exclude excluded/nan)
f_rates = per_vin_df.filter(pl.col("failed") & pl.col("ep_per_truck_yr").is_not_nan())["ep_per_truck_yr"].to_list()
nf_rates = per_vin_df.filter(~pl.col("failed") & pl.col("ep_per_truck_yr").is_not_nan())["ep_per_truck_yr"].to_list()

print(f"\nF  n={len(f_rates)}: median={np.median(f_rates):.2f}, rates={[round(r,2) for r in sorted(f_rates, reverse=True)]}")
print(f"NF n={len(nf_rates)}: median={np.median(nf_rates):.2f}, rates={[round(r,2) for r in sorted(nf_rates, reverse=True)]}")

if len(f_rates) >= 2 and len(nf_rates) >= 2:
    stat, pval = mannwhitneyu(f_rates, nf_rates, alternative="two-sided")
    print(f"Mann-Whitney U={stat:.1f}, p={pval:.4f}")
else:
    pval = float("nan")
    print("Insufficient samples for Mann-Whitney")

# Episode-level output (per-VIN summary of episodes)
ep_rows = []
for r in all_results:
    if r["n_episodes"] > 0:
        ep_rows.append({"vin_label": r["vin_label"], "failed": r["failed"],
                        "n_episodes": r["n_episodes"], "n_cwr_rows": r["n_cwr_rows"],
                        "ep_per_truck_yr": r["ep_per_truck_yr"]})
ep_df = pl.DataFrame(ep_rows) if ep_rows else pl.DataFrame({"vin_label": [], "failed": [], "n_episodes": [], "n_cwr_rows": [], "ep_per_truck_yr": []})
ep_csv = OUT_DIR / "B5_cwr_episodes.csv"
ep_df.write_csv(ep_csv)
print(f"\nEpisode summary saved to {ep_csv}")

# Final-90d vs baseline for failed VINs (exclude SMA-dead)
print("\n--- Final-90d vs Baseline CWR episode rates (failed VINs) ---")
f90_rows = []
for v in failed_vins:
    label = f"{v}_F_SM"
    if v in SMA_DEAD:
        continue
    t_end_row = dq.filter(pl.col("vin_label") == label)
    if t_end_row.height == 0:
        continue
    t_end_str = t_end_row["t_end"][0]
    res = final_90d_vs_baseline(df_f, v, t_end_str)
    f90_rows.append(res)
    print(f"  {label}: final90_eps={res['ep_final90']}, baseline_eps={res['ep_baseline']}, "
          f"rate_f90={res['ep_rate_final90_per_yr']}/yr, rate_base={res['ep_rate_baseline_per_yr']}/yr")

f90_df = pl.DataFrame(f90_rows)
f90_csv = OUT_DIR / "B5_cwr_final90_vs_baseline.csv"
f90_df.write_csv(f90_csv)
print(f"\nFinal-90d vs baseline saved to {f90_csv}")

# Summary verdict
print("\n=== B5 VERDICT SUMMARY ===")
print(f"F  ep/truck-yr: median={np.median(f_rates):.2f} (n={len(f_rates)} active)")
print(f"NF ep/truck-yr: median={np.median(nf_rates):.2f} (n={len(nf_rates)}, top-10 active)")
print(f"Mann-Whitney p={pval:.4f}")
print(f"NOTE: SMA-dead excluded: VIN8_F, VIN9_F (F); VIN10,11,12,13,20_NF (NF subset, only 10/15 NF processed)")
print("A1-archetype trucks (VIN1_F, VIN10_F, VIN14_F): see per-VIN CSV for episode counts")
