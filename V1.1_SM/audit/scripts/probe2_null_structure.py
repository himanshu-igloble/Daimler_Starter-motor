"""Probe 2 — Missing-value structure: SMA/VSI nulls per VIN x month and per regime (engine on/off).

Null definitions (match V1 config / column dictionary):
  VSI null  : raw null, <=0, or >=255  (values >36 would need x0.2 rescale; flag count too)
  SMA null  : raw null
  RPM valid : not null and != 65535
"""
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
NF = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
OUT = ROOT / "STARTER MOTOR/V1.1/audit"

def month_nulls(path, suffix):
    lf = pl.scan_parquet(path).with_columns(
        (pl.col("VIN") + pl.lit(suffix)).alias("vin_label"),
        pl.col("timestamp").dt.truncate("1mo").alias("month"),
        ((pl.col("RPM").is_not_null()) & (pl.col("RPM") != 65535.0) & (pl.col("RPM") > 400)).alias("eng_on"),
        (pl.col("VSI").is_null() | (pl.col("VSI") <= 0) | (pl.col("VSI") >= 255)).alias("vsi_null"),
        pl.col("SMA").is_null().alias("sma_null"),
    )
    return (
        lf.group_by("vin_label", "month")
        .agg(
            pl.len().alias("rows"),
            pl.col("vsi_null").sum().alias("vsi_nulls"),
            pl.col("sma_null").sum().alias("sma_nulls"),
            pl.col("eng_on").sum().alias("eng_on_rows"),
            (pl.col("vsi_null") & pl.col("eng_on")).sum().alias("vsi_nulls_engon"),
            (pl.col("sma_null") & pl.col("eng_on")).sum().alias("sma_nulls_engon"),
            (pl.col("vsi_null") & ~pl.col("eng_on")).sum().alias("vsi_nulls_engoff"),
            (pl.col("sma_null") & ~pl.col("eng_on")).sum().alias("sma_nulls_engoff"),
            ((pl.col("VSI") > 36) & (pl.col("VSI") < 255)).sum().alias("vsi_needs_rescale"),
            pl.col("GED").is_null().sum().alias("ged_nulls"),
        )
        .sort("vin_label", "month")
        .collect(engine="streaming")
    )

fa = month_nulls(F, "_F_SM")
nf = month_nulls(NF, "_NF_SM")
allm = pl.concat([fa, nf])
allm.write_csv(OUT / "probe2_null_by_vin_month.csv")

# per-VIN summary with regime split
summ = (
    allm.group_by("vin_label")
    .agg(
        pl.col("rows").sum(),
        (pl.col("vsi_nulls").sum() / pl.col("rows").sum()).alias("vsi_null_rate"),
        (pl.col("sma_nulls").sum() / pl.col("rows").sum()).alias("sma_null_rate"),
        (pl.col("vsi_nulls_engon").sum() / pl.col("eng_on_rows").sum()).alias("vsi_null_rate_engon"),
        (pl.col("sma_nulls_engon").sum() / pl.col("eng_on_rows").sum()).alias("sma_null_rate_engon"),
        (pl.col("vsi_nulls_engoff").sum() / (pl.col("rows").sum() - pl.col("eng_on_rows").sum())).alias("vsi_null_rate_engoff"),
        (pl.col("sma_nulls_engoff").sum() / (pl.col("rows").sum() - pl.col("eng_on_rows").sum())).alias("sma_null_rate_engoff"),
        pl.col("vsi_needs_rescale").sum(),
        # month-level volatility of null rate: does reporting switch on/off mid-stream?
        (pl.col("sma_nulls") / pl.col("rows")).min().alias("sma_null_rate_month_min"),
        (pl.col("sma_nulls") / pl.col("rows")).max().alias("sma_null_rate_month_max"),
        (pl.col("vsi_nulls") / pl.col("rows")).min().alias("vsi_null_rate_month_min"),
        (pl.col("vsi_nulls") / pl.col("rows")).max().alias("vsi_null_rate_month_max"),
    )
    .sort("vin_label")
)
summ.write_csv(OUT / "probe2_null_summary_per_vin.csv")
with pl.Config(tbl_cols=20, tbl_rows=40, tbl_width_chars=260, fmt_str_lengths=20):
    print(summ)

# cohort comparison
coh = (
    summ.with_columns(pl.col("vin_label").str.contains("_F_SM").alias("failed"))
    .group_by("failed")
    .agg(
        pl.col("vsi_null_rate").mean().alias("vsi_null_mean"),
        pl.col("sma_null_rate").mean().alias("sma_null_mean"),
        (pl.col("sma_null_rate") > 0.9).sum().alias("n_vins_sma_dead"),
        (pl.col("vsi_null_rate") > 0.5).sum().alias("n_vins_vsi_degraded"),
        pl.len().alias("n_vins"),
    )
)
print(coh)
