"""Probe 4 — VSI sensor reliability: quantization step, stuck-value runs, per-VIN
calibration baselines (drive-regime regulation setpoint differences between trucks)."""
import polars as pl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
F = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet"
NF = ROOT / "Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet"
OUT = ROOT / "STARTER MOTOR/V1.1/audit"

# 1) global VSI value histogram (quantization)
vc = []
for path in (F, NF):
    v = (
        pl.scan_parquet(path)
        .filter((pl.col("VSI") > 0) & (pl.col("VSI") < 255))
        .group_by(pl.col("VSI").round(2).alias("vsi"))
        .agg(pl.len().alias("n"))
        .collect(engine="streaming")
    )
    vc.append(v)
hist = pl.concat(vc).group_by("vsi").agg(pl.col("n").sum()).sort("vsi")
hist.write_csv(OUT / "probe4_vsi_value_hist.csv")
vals = hist["vsi"].to_list()
steps = sorted(set(round(b - a, 3) for a, b in zip(vals, vals[1:])))
print(f"distinct VSI values: {len(vals)}, min={vals[0]}, max={vals[-1]}")
print("unique step sizes (first 15):", steps[:15])
top = hist.sort("n", descending=True).head(12)
print("top-12 values:", top.to_dicts())

# 2) stuck runs + per-VIN drive baseline
res = []
for path, suffix in [(F, "_F_SM"), (NF, "_NF_SM")]:
    df = (
        pl.scan_parquet(path)
        .select(
            (pl.col("VIN") + pl.lit(suffix)).alias("vin_label"),
            "timestamp",
            pl.when((pl.col("VSI") > 0) & (pl.col("VSI") < 255)).then(pl.col("VSI")).alias("vsi"),
            pl.when(pl.col("RPM") != 65535.0).then(pl.col("RPM")).alias("rpm"),
        )
        .collect(engine="streaming")
    )
    # stuck runs: consecutive identical non-null VSI while engine on (rpm>700, alternator charging)
    dr = df.filter((pl.col("rpm") > 700) & pl.col("vsi").is_not_null())
    dr = dr.with_columns(((pl.col("vsi") != pl.col("vsi").shift(1)).fill_null(True).cum_sum()).over("vin_label").alias("run_id"))
    runs = dr.group_by("vin_label", "run_id").agg(pl.len().alias("run_len"))
    stuck = runs.group_by("vin_label").agg(
        pl.col("run_len").max().alias("max_stuck_run"),
        (pl.col("run_len") >= 360).sum().alias("n_runs_ge30min"),  # 360 samples * 5s = 30 min
        pl.col("run_len").quantile(0.999).alias("run_p999"),
    )
    base = dr.group_by("vin_label").agg(
        pl.len().alias("drive_rows"),
        pl.col("vsi").median().alias("vsi_drive_median"),
        pl.col("vsi").mean().alias("vsi_drive_mean"),
        pl.col("vsi").std().alias("vsi_drive_std"),
        pl.col("vsi").quantile(0.05).alias("vsi_drive_p05"),
        pl.col("vsi").quantile(0.95).alias("vsi_drive_p95"),
    )
    res.append(stuck.join(base, on="vin_label"))

per_vin = pl.concat(res).sort("vin_label")
per_vin.write_csv(OUT / "probe4_vsi_stuck_baseline_per_vin.csv")
with pl.Config(tbl_rows=40, tbl_cols=12, tbl_width_chars=240):
    print(per_vin)
print("drive-median spread across fleet: min={:.2f} max={:.2f} std={:.3f}".format(
    per_vin["vsi_drive_median"].min(), per_vin["vsi_drive_median"].max(), per_vin["vsi_drive_median"].std()))
coh = per_vin.with_columns(pl.col("vin_label").str.contains("_F_SM").alias("failed")).group_by("failed").agg(pl.selectors.numeric().mean()).sort("failed")
with pl.Config(tbl_cols=14, tbl_width_chars=240):
    print(coh)
