"""Probe 5 — Engine-off VSI decay within rest bouts (battery health proxy).

Rest row: RPM null or <100, VSI valid. Bout: consecutive rest rows with dt<=45min
(heartbeat is ~900s). For bouts >=3h: slope V/h from first->last sample, and
'settled' voltage = median VSI beyond 2h into the bout.
"""
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
NF = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
OUT = ROOT / "STARTER MOTOR/V1.1/audit"

out = []
for path, suffix in [(F, "_F_SM"), (NF, "_NF_SM")]:
    df = (
        pl.scan_parquet(path)
        .select(
            (pl.col("VIN") + pl.lit(suffix)).alias("vin_label"),
            "timestamp",
            pl.when((pl.col("VSI") > 0) & (pl.col("VSI") < 255)).then(pl.col("VSI")).alias("vsi"),
            pl.when(pl.col("RPM") != 65535.0).then(pl.col("RPM")).alias("rpm"),
        )
        .with_columns(((pl.col("rpm") < 100) | pl.col("rpm").is_null()).alias("rest"))
        .filter(pl.col("rest") & pl.col("vsi").is_not_null())
        .with_columns(pl.col("timestamp").diff().over("vin_label").dt.total_seconds().alias("dt_s"))
        .with_columns(
            ((pl.col("dt_s") > 2700) | pl.col("dt_s").is_null()).cum_sum().over("vin_label").alias("bout_id")
        )
        .collect(engine="streaming")
    )
    bouts = (
        df.group_by("vin_label", "bout_id")
        .agg(
            pl.len().alias("n"),
            pl.col("timestamp").min().alias("t0"),
            pl.col("timestamp").max().alias("t1"),
            pl.col("vsi").first().alias("vsi_first"),
            pl.col("vsi").last().alias("vsi_last"),
            pl.col("vsi").filter(
                (pl.col("timestamp") - pl.col("timestamp").min()).dt.total_seconds() > 7200
            ).median().alias("vsi_settled"),
        )
        .with_columns(((pl.col("t1") - pl.col("t0")).dt.total_seconds() / 3600).alias("hours"))
        .filter((pl.col("hours") >= 3) & (pl.col("n") >= 6))
        .with_columns(((pl.col("vsi_last") - pl.col("vsi_first")) / pl.col("hours")).alias("slope_v_per_h"))
    )
    per_vin = bouts.group_by("vin_label").agg(
        pl.len().alias("n_bouts_ge3h"),
        pl.col("hours").median().alias("bout_hours_median"),
        pl.col("slope_v_per_h").median().alias("rest_slope_vph_median"),
        pl.col("slope_v_per_h").quantile(0.10).alias("rest_slope_vph_p10"),
        pl.col("vsi_settled").median().alias("vsi_settled_median"),
        pl.col("vsi_settled").quantile(0.05).alias("vsi_settled_p05"),
        pl.col("vsi_first").median().alias("vsi_bout_start_median"),
    )
    out.append(per_vin)

res = pl.concat(out).sort("vin_label")
res.write_csv(OUT / "probe5_rest_bout_decay_per_vin.csv")
with pl.Config(tbl_rows=40, tbl_cols=12, tbl_width_chars=220):
    print(res)
coh = res.with_columns(pl.col("vin_label").str.contains("_F_SM").alias("failed")).group_by("failed").agg(pl.selectors.numeric().mean()).sort("failed")
with pl.Config(tbl_cols=12, tbl_width_chars=220):
    print(coh)
