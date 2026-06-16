"""Probe 3 — Sampling consistency, gap structure, density drift near t_end, and
engine-off VSI decay across long gaps (battery self-discharge proxy).

Timestamps verified sorted within VIN (probe0). Uses diff().over(VIN).
"""
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
NF = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
OUT = ROOT / "STARTER MOTOR/V1.1/audit"

def load(path, suffix):
    return (
        pl.scan_parquet(path)
        .select(
            (pl.col("VIN") + pl.lit(suffix)).alias("vin_label"),
            "timestamp",
            pl.when((pl.col("VSI") > 0) & (pl.col("VSI") < 255)).then(pl.col("VSI")).alias("vsi"),
            pl.when(pl.col("RPM") != 65535.0).then(pl.col("RPM")).alias("rpm"),
        )
        .with_columns(pl.col("timestamp").diff().over("vin_label").dt.total_seconds().alias("dt_s"))
        .collect(engine="streaming")
    )

rows = []
gap_decay = []
density = []
for path, suffix in [(F, "_F_SM"), (NF, "_NF_SM")]:
    df = load(path, suffix)
    # --- dt distribution per VIN ---
    agg = (
        df.group_by("vin_label")
        .agg(
            pl.len().alias("rows"),
            pl.col("dt_s").median().alias("dt_median"),
            pl.col("dt_s").quantile(0.99).alias("dt_p99"),
            (pl.col("dt_s") <= 6).sum().alias("n_dt_le6s"),
            ((pl.col("dt_s") > 6) & (pl.col("dt_s") <= 60)).sum().alias("n_dt_6_60s"),
            ((pl.col("dt_s") > 3600) & (pl.col("dt_s") <= 86400)).sum().alias("n_gaps_1h_1d"),
            (pl.col("dt_s") > 86400).sum().alias("n_gaps_gt1d"),
            pl.col("dt_s").filter(pl.col("dt_s") > 86400).sum().alias("sum_gap_gt1d_s"),
            pl.col("dt_s").filter(pl.col("dt_s") > 86400).max().alias("max_gap_s"),
            pl.col("timestamp").min().alias("t_start"),
            pl.col("timestamp").max().alias("t_end"),
        )
    )
    rows.append(agg)

    # --- engine-off VSI decay across gaps 6h..7d: (vsi_after - vsi_before)/gap_days ---
    # only when engine was off before the gap (rpm<100 or null) -> battery rest decay proxy
    d = df.with_columns(
        pl.col("vsi").shift(1).over("vin_label").alias("vsi_before"),
        pl.col("rpm").shift(1).over("vin_label").alias("rpm_before"),
    ).filter(
        (pl.col("dt_s") > 6 * 3600) & (pl.col("dt_s") < 7 * 86400)
        & pl.col("vsi").is_not_null() & pl.col("vsi_before").is_not_null()
        & ((pl.col("rpm_before") < 100) | pl.col("rpm_before").is_null())
        & ((pl.col("rpm") < 100) | pl.col("rpm").is_null())
    ).with_columns(
        ((pl.col("vsi") - pl.col("vsi_before")) / (pl.col("dt_s") / 86400.0)).alias("decay_v_per_day"),
    )
    gd = d.group_by("vin_label").agg(
        pl.len().alias("n_rest_gaps"),
        pl.col("decay_v_per_day").median().alias("decay_vpd_median"),
        pl.col("decay_v_per_day").quantile(0.25).alias("decay_vpd_p25"),
        pl.col("vsi_before").median().alias("vsi_pre_gap_median"),
        pl.col("vsi").median().alias("vsi_post_gap_median"),
    )
    gap_decay.append(gd)

    # --- density drift: rows/day in final windows vs baseline ---
    dd = (
        df.group_by("vin_label", pl.col("timestamp").dt.date().alias("day"))
        .agg(pl.len().alias("rows_day"))
    )
    dd = dd.join(dd.group_by("vin_label").agg(pl.col("day").max().alias("last_day")), on="vin_label")
    dd = dd.with_columns((pl.col("last_day") - pl.col("day")).dt.total_days().alias("days_before_end"))
    dens = dd.group_by("vin_label").agg(
        pl.col("rows_day").filter(pl.col("days_before_end") <= 30).mean().alias("rowsday_final30"),
        pl.col("rows_day").filter((pl.col("days_before_end") > 30) & (pl.col("days_before_end") <= 90)).mean().alias("rowsday_31_90"),
        pl.col("rows_day").filter(pl.col("days_before_end") > 90).mean().alias("rowsday_baseline_gt90"),
        pl.col("rows_day").filter(pl.col("days_before_end") <= 30).len().alias("ndays_obs_final30"),
    )
    density.append(dens)

dt_all = pl.concat(rows).sort("vin_label")
dt_all.write_csv(OUT / "probe3_dt_gaps_per_vin.csv")
decay_all = pl.concat(gap_decay).sort("vin_label")
decay_all.write_csv(OUT / "probe3_rest_gap_vsi_decay.csv")
dens_all = pl.concat(density).sort("vin_label")
dens_all = dens_all.with_columns((pl.col("rowsday_final30") / pl.col("rowsday_baseline_gt90")).alias("density_ratio_final30"))
dens_all.write_csv(OUT / "probe3_density_drift.csv")

with pl.Config(tbl_rows=40, tbl_cols=15, tbl_width_chars=250):
    print(dt_all)
    print(decay_all)
    print(dens_all)

# cohort means
for name, d in [("gaps", dt_all), ("decay", decay_all), ("density", dens_all)]:
    c = d.with_columns(pl.col("vin_label").str.contains("_F_SM").alias("failed")).group_by("failed").agg(pl.selectors.numeric().mean()).sort("failed")
    with pl.Config(tbl_cols=20, tbl_width_chars=250):
        print(name, c)
