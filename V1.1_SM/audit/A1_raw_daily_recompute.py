"""
A1_raw_daily_recompute.py — audit step 1
Recompute per-VIN per-day aggregates DIRECTLY from the raw parquet files,
using the identical sentinel cleaning / regime logic as
V1_1_SM_build_daily_cache.py (re-implemented here, not imported, so this is
an independent re-derivation from ground truth).

Outputs (under STARTER MOTOR/V1.1/audit/):
  A1_raw_daily.parquet   — vin_label, date, n_rows, sma_obs_rows, sma1_rows,
                           vsi_drive_rows, vsi_drive_mean/std/p05/p95,
                           vsi_below_21_rows
  A1_raw_vin_meta.csv    — vin_label, rows, t_start, t_end, active_days
"""
from pathlib import Path
import time
import polars as pl

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
RAW_F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
RAW_NF = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
AUDIT = ROOT / "STARTER MOTOR" / "V1.1" / "audit"

SENT_U16 = 65535.0
VSI_SENT_LOW, VSI_SENT_HIGH = 0.0, 255.0
VSI_SCALE_TRIGGER, VSI_SCALE_FACTOR = 36.0, 0.2
RPM_DRIVE = 700
VSI_ALERT_LOW = 21.0


def clean(lf: pl.LazyFrame) -> pl.LazyFrame:
    lf = lf.with_columns([
        pl.when(pl.col("RPM") >= SENT_U16).then(None).otherwise(pl.col("RPM")).alias("RPM"),
        pl.when((pl.col("VSI") <= VSI_SENT_LOW) | (pl.col("VSI") >= VSI_SENT_HIGH))
          .then(None).otherwise(pl.col("VSI")).alias("VSI"),
    ])
    return lf.with_columns(
        pl.when(pl.col("VSI") > VSI_SCALE_TRIGGER)
          .then(pl.col("VSI") * VSI_SCALE_FACTOR)
          .otherwise(pl.col("VSI")).alias("VSI")
    )


_DRIVE = pl.col("RPM") > RPM_DRIVE
AGG = [
    pl.len().alias("n_rows"),
    pl.col("SMA").is_not_null().sum().alias("sma_obs_rows"),
    (pl.col("SMA").fill_null(0) == 1).sum().alias("sma1_rows"),
    pl.col("VSI").filter(_DRIVE).is_not_null().sum().alias("vsi_drive_rows"),
    pl.col("VSI").filter(_DRIVE).mean().alias("vsi_drive_mean"),
    pl.col("VSI").filter(_DRIVE).std().alias("vsi_drive_std"),
    pl.col("VSI").filter(_DRIVE).quantile(0.05).alias("vsi_drive_p05"),
    pl.col("VSI").filter(_DRIVE).quantile(0.95).alias("vsi_drive_p95"),
    (pl.col("VSI") < VSI_ALERT_LOW).sum().alias("vsi_below_21_rows"),
]


def scan(path: Path, suffix: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    t0 = time.time()
    lf = pl.scan_parquet(str(path)).select(["VIN", "timestamp", "RPM", "VSI", "SMA"])
    lf = clean(lf)
    lf = lf.filter(pl.col("timestamp").is_not_null())
    lf = lf.with_columns([
        (pl.col("VIN") + pl.lit(suffix)).alias("vin_label"),
        pl.col("timestamp").dt.date().alias("date"),
    ])
    daily = lf.group_by(["vin_label", "date"]).agg(AGG).sort(["vin_label", "date"]).collect(engine="streaming")
    meta = (
        pl.scan_parquet(str(path)).select(["VIN", "timestamp"])
        .filter(pl.col("timestamp").is_not_null())
        .with_columns((pl.col("VIN") + pl.lit(suffix)).alias("vin_label"))
        .group_by("vin_label")
        .agg([
            pl.len().alias("rows"),
            pl.col("timestamp").min().alias("t_start"),
            pl.col("timestamp").max().alias("t_end"),
            pl.col("timestamp").dt.date().n_unique().alias("active_days"),
        ])
        .sort("vin_label")
        .collect(engine="streaming")
    )
    print(f"  {path.name}: {len(daily)} vin-days, {len(meta)} VINs ({time.time()-t0:.1f}s)")
    return daily, meta


def main():
    print("A1: raw daily recompute (independent ground-truth pass)")
    d1, m1 = scan(RAW_F, "_F_SM")
    d2, m2 = scan(RAW_NF, "_NF_SM")
    daily = pl.concat([d1, d2]).sort(["vin_label", "date"])
    meta = pl.concat([m1, m2]).sort("vin_label")
    daily.write_parquet(str(AUDIT / "A1_raw_daily.parquet"))
    meta.write_csv(str(AUDIT / "A1_raw_vin_meta.csv"))
    print(f"  wrote {AUDIT / 'A1_raw_daily.parquet'} ({len(daily)} rows)")
    print(f"  wrote {AUDIT / 'A1_raw_vin_meta.csv'} ({len(meta)} rows)")


if __name__ == "__main__":
    main()
