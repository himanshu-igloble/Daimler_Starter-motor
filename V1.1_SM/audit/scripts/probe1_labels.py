"""Probe 1 — Failure labeling quality: Failure_type enumeration, JCOPENDATE vs telemetry alignment."""
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
OUT = ROOT / "STARTER MOTOR/V1.1/audit"

lf = pl.scan_parquet(F)

# distinct Failure_type values overall and per VIN
ft_global = lf.select(pl.col("Failure_type").value_counts()).collect(engine="streaming")
print("GLOBAL Failure_type value_counts:", ft_global.to_dicts())

per_vin = (
    lf.group_by("VIN")
    .agg(
        pl.col("Failure_type").n_unique().alias("ft_nunique"),
        pl.col("Failure_type").first().alias("ft_first"),
        pl.col("Failure_type").null_count().alias("ft_nulls"),
        pl.col("SALEDATE").n_unique().alias("sale_nunique"),
        pl.col("JCOPENDATE").n_unique().alias("jco_nunique"),
        pl.col("SALEDATE").first().alias("saledate"),
        pl.col("JCOPENDATE").first().alias("jcopendate"),
        pl.col("timestamp").min().alias("t_min"),
        pl.col("timestamp").max().alias("t_max"),
        pl.len().alias("rows"),
        # rows AFTER jcopendate (telemetry past failure label = post-repair contamination)
        (pl.col("timestamp").dt.date() > pl.col("JCOPENDATE").first()).sum().alias("rows_after_jco"),
        (pl.col("timestamp").dt.date() == pl.col("JCOPENDATE").first()).sum().alias("rows_on_jco_day"),
    )
    .with_columns(
        (pl.col("jcopendate") - pl.col("t_max").dt.date()).dt.total_days().alias("gap_jco_minus_lastts_days"),
        (pl.col("t_min").dt.date() - pl.col("saledate")).dt.total_days().alias("firstts_minus_sale_days"),
        (pl.col("jcopendate") - pl.col("saledate")).dt.total_days().alias("life_days_sale_to_jco"),
    )
    .sort("VIN")
    .collect(engine="streaming")
)
per_vin.write_csv(OUT / "probe1_labels_per_vin.csv")
with pl.Config(tbl_cols=20, tbl_rows=20, tbl_width_chars=240):
    print(per_vin)
