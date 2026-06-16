"""
V1_SM_build_weekly_cache.py
Phase 0 - Sentinel cleaning + weekly aggregate cache for the SM pipeline.

Inputs  : SM_FAILED  (30.9M rows, 14 VINs)
          SM_NONFAIL (76.3M rows, 20 VINs)
Outputs : cache/weekly/V1_SM_weekly_<vin_label>.parquet  (34 files)
          results/V1_SM_data_quality.csv                 (34 rows)

Column names are a CONTRACT consumed by Task-4 feature engineering.

Nullable contract:
  - vsi_drive_* columns (vsi_drive_mean, vsi_drive_std, vsi_drive_p05, vsi_drive_p95)
    are NULLABLE: null = no rows with RPM > RPM_DRIVE_THRESH that week.
  - vsi_rest_* columns (vsi_rest_median, vsi_rest_p05) are NULLABLE: null = no
    engine-off rows that week.
  - vsi_obs_rows: count of non-null VSI rows (valid readings, sentinel-cleaned).
    Use this as the denominator when normalising vsi_below_21_rows / vsi_above_32_rows.
"""

import datetime
import sys
import time
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

import polars as pl

# ---------------------------------------------------------------------------
# Load config (path contains a space)
# ---------------------------------------------------------------------------
_spec = spec_from_file_location(
    "v1_sm_config", Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

# ---------------------------------------------------------------------------
# Create output directories
# ---------------------------------------------------------------------------
cfg.CACHE_WEEKLY.mkdir(parents=True, exist_ok=True)
cfg.RESULTS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Sentinel cleaning (lazy, applied before any aggregation)
# ---------------------------------------------------------------------------

def clean(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Replace sentinel / out-of-range values with null; rescale VSI if needed."""
    lf = lf.with_columns([
        pl.when(pl.col("CSP") >= cfg.SENT_U16)
          .then(None).otherwise(pl.col("CSP")).alias("CSP"),
        pl.when(pl.col("RPM") >= cfg.SENT_U16)
          .then(None).otherwise(pl.col("RPM")).alias("RPM"),
        pl.when((pl.col("ANR") >= cfg.SENT_U16) | (pl.col("ANR") <= cfg.SENT_ANR_NEG))
          .then(None).otherwise(pl.col("ANR")).alias("ANR"),
        pl.when(
            (pl.col("VSI") <= cfg.VSI_SENTINEL_LOW) |
            (pl.col("VSI") >= cfg.VSI_SENTINEL_HIGH)
        ).then(None).otherwise(pl.col("VSI")).alias("VSI"),
    ])
    lf = lf.with_columns(
        pl.when(pl.col("VSI") > cfg.VSI_SCALE_TRIGGER)
          .then(pl.col("VSI") * cfg.VSI_SCALE_FACTOR)
          .otherwise(pl.col("VSI"))
          .alias("VSI")
    )
    return lf


# ---------------------------------------------------------------------------
# Weekly aggregation expressions (CONTRACT - do not rename columns)
# ---------------------------------------------------------------------------
AGG = [
    pl.len().alias("n_rows"),
    pl.col("timestamp").dt.date().n_unique().alias("active_days"),
    pl.col("SMA").is_not_null().sum().alias("sma_obs_rows"),
    (pl.col("SMA").fill_null(0) == 1).sum().alias("sma1_rows"),
    pl.col("VSI").is_not_null().sum().alias("vsi_obs_rows"),   # valid-VSI denominator
    # VSI conditioned on driving regime (RPM > RPM_DRIVE_THRESH = alternator charging)
    pl.col("VSI").filter(pl.col("RPM") > cfg.RPM_DRIVE_THRESH).mean().alias("vsi_drive_mean"),
    pl.col("VSI").filter(pl.col("RPM") > cfg.RPM_DRIVE_THRESH).std().alias("vsi_drive_std"),
    pl.col("VSI").filter(pl.col("RPM") > cfg.RPM_DRIVE_THRESH).quantile(0.05).alias("vsi_drive_p05"),
    pl.col("VSI").filter(pl.col("RPM") > cfg.RPM_DRIVE_THRESH).quantile(0.95).alias("vsi_drive_p95"),
    # Resting VSI (engine off = battery state)
    pl.col("VSI").filter(
        pl.col("RPM").is_null() | (pl.col("RPM") == 0)
    ).median().alias("vsi_rest_median"),
    pl.col("VSI").filter(
        pl.col("RPM").is_null() | (pl.col("RPM") == 0)
    ).quantile(0.05).alias("vsi_rest_p05"),
    (pl.col("VSI") < cfg.VSI_ALERT_LOW).sum().alias("vsi_below_21_rows"),   # DICV A5 severe-low
    (pl.col("VSI") > cfg.VSI_ALERT_HIGH).sum().alias("vsi_above_32_rows"),  # DICV A4 battery rejection
    pl.col("RPM").mean().alias("rpm_mean"),
    pl.col("CSP").mean().alias("csp_mean"),
    pl.col("ANR").filter(pl.col("ANR") > 0).mean().alias("anr_pos_mean"),
    (pl.col("GED") == 3).sum().alias("ged3_rows"),             # data-quality covariate only
]


# ---------------------------------------------------------------------------
# Per-file processing helper
# ---------------------------------------------------------------------------

def process_file(parquet_path: Path, failed: bool) -> tuple[list[dict], list[dict]]:
    """
    Stream-aggregate one parquet file; write per-VIN weekly parquets.

    Returns:
        weekly_meta : list of dicts (one per VIN) for the summary table
        quality_rows: list of dicts (one per VIN) for the data-quality CSV
    """
    tag = "FAILED" if failed else "NONFAIL"
    print(f"  Loading {tag} parquet ... ", end="", flush=True)
    t0 = time.time()

    # Read into LazyFrame and apply sentinel cleaning
    lf = pl.scan_parquet(str(parquet_path))
    lf = clean(lf)

    # Drop rows with null timestamp (raw data artifact; ~730k rows in NF file)
    lf = lf.filter(pl.col("timestamp").is_not_null())

    # Add relabelled VIN column and truncated week column
    lf = lf.with_columns([
        pl.concat_str([
            pl.col("VIN"),
            pl.lit("_F_SM" if failed else "_NF_SM")
        ]).alias("vin_label"),
        pl.col("timestamp").dt.truncate("1w").alias("week"),
    ])

    # ---------- Collect per-VIN metadata (timestamps, null pcts, saledate) ----------
    # Collect a lightweight metadata frame (timestamps, nulls) - streaming friendly
    meta_cols = ["vin_label", "timestamp", "CSP", "RPM", "ANR", "VSI", "SMA", "GED"]
    if failed:
        meta_cols += ["SALEDATE", "JCOPENDATE"]

    meta_lf = lf.select(meta_cols)
    meta_agg_exprs = [
        pl.col("timestamp").count().alias("rows"),
        pl.col("timestamp").min().alias("t_start"),
        pl.col("timestamp").max().alias("t_end"),
        (pl.col("CSP").is_null().sum() / pl.len()).alias("csp_null_pct"),
        (pl.col("RPM").is_null().sum() / pl.len()).alias("rpm_null_pct"),
        (pl.col("ANR").is_null().sum() / pl.len()).alias("anr_null_pct"),
        (pl.col("VSI").is_null().sum() / pl.len()).alias("vsi_null_pct"),
        (pl.col("SMA").is_null().sum() / pl.len()).alias("sma_null_pct"),
        (pl.col("GED").is_null().sum() / pl.len()).alias("ged_null_pct"),
    ]
    if failed:
        meta_agg_exprs += [
            pl.col("SALEDATE").first().alias("saledate"),
            pl.col("JCOPENDATE").first().alias("jcopendate"),
        ]

    meta_df = meta_lf.group_by("vin_label").agg(meta_agg_exprs).collect(engine="streaming")
    print(f"meta done ({time.time()-t0:.1f}s)", flush=True)

    # ---------- Weekly aggregation ----------
    print(f"  Weekly aggregation {tag} ... ", end="", flush=True)
    t1 = time.time()

    weekly_df = (
        lf.group_by(["vin_label", "week"])
        .agg(AGG)
        .collect(engine="streaming")
    )
    print(f"done ({time.time()-t1:.1f}s)", flush=True)

    # ---------- Write per-VIN parquets ----------
    vin_labels = weekly_df["vin_label"].unique().to_list()
    weekly_meta = []
    quality_rows = []

    for vin_label in sorted(vin_labels):
        # Weekly parquet
        vin_weekly = (
            weekly_df
            .filter(pl.col("vin_label") == vin_label)
            .with_columns(pl.lit(failed).alias("failed"))
            .sort("week")
        )
        # Reorder: vin_label, failed, week, then aggregates
        col_order = ["vin_label", "failed", "week"] + [
            c for c in vin_weekly.columns if c not in ("vin_label", "failed", "week")
        ]
        vin_weekly = vin_weekly.select(col_order)

        out_path = cfg.CACHE_WEEKLY / f"V1_SM_weekly_{vin_label}.parquet"
        tmp_path = out_path.with_suffix(".tmp.parquet")
        vin_weekly.write_parquet(str(tmp_path))
        tmp_path.replace(out_path)

        n_weeks = len(vin_weekly)
        t_start_w = vin_weekly["week"].min()
        t_end_w = vin_weekly["week"].max()
        weeks_lt2 = int((vin_weekly["active_days"] < 2).sum())

        # Summary meta
        weekly_meta.append({
            "vin_label": vin_label,
            "n_weeks": n_weeks,
            "t_start_week": str(t_start_w),
            "t_end_week": str(t_end_w),
        })

        # Quality row
        meta_row = meta_df.filter(pl.col("vin_label") == vin_label).to_dicts()[0]
        t_start = meta_row["t_start"]
        t_end = meta_row["t_end"]
        active_days_total = int(
            vin_weekly["active_days"].sum()
        )

        qrow = {
            "vin_label": vin_label,
            "failed": failed,
            "rows": int(meta_row["rows"]),
            "t_start": str(t_start),
            "t_end": str(t_end),
            "active_days_total": active_days_total,
            "n_weeks": n_weeks,
            "weeks_lt2_active_days": weeks_lt2,
            "csp_null_pct": round(float(meta_row["csp_null_pct"]), 4),
            "rpm_null_pct": round(float(meta_row["rpm_null_pct"]), 4),
            "anr_null_pct": round(float(meta_row["anr_null_pct"]), 4),
            "vsi_null_pct": round(float(meta_row["vsi_null_pct"]), 4),
            "sma_null_pct": round(float(meta_row["sma_null_pct"]), 4),
            "ged_null_pct": round(float(meta_row["ged_null_pct"]), 4),
            "saledate": str(meta_row["saledate"]) if failed else "",
            "jcopendate": str(meta_row["jcopendate"]) if failed else "",
            "gap_days": "",
        }

        if failed:
            # gap_days = (jcopendate - t_end.date()).days
            jco = meta_row["jcopendate"]
            if jco is not None and t_end is not None:
                jco_date = jco.date() if isinstance(jco, datetime.datetime) else jco
                t_end_date = t_end.date() if isinstance(t_end, datetime.datetime) else t_end
                gap = (jco_date - t_end_date).days
                qrow["gap_days"] = gap

        quality_rows.append(qrow)

    return weekly_meta, quality_rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("V1_SM Phase 0: Sentinel Cleaning + Weekly Cache Builder")
    print("=" * 60)
    t_total = time.time()

    all_meta = []
    all_quality = []

    # Process FAILED file (14 VINs)
    print("\n[1/2] Processing FAILED parquet ...")
    meta_f, qual_f = process_file(cfg.SM_FAILED, failed=True)
    all_meta.extend(meta_f)
    all_quality.extend(qual_f)

    # Process NONFAILED file (20 VINs)
    print("\n[2/2] Processing NONFAILED parquet ...")
    meta_nf, qual_nf = process_file(cfg.SM_NONFAIL, failed=False)
    all_meta.extend(meta_nf)
    all_quality.extend(qual_nf)

    # ---------- Write data-quality CSV ----------
    dq_df = pl.DataFrame(all_quality)
    # Ensure column order matches spec
    col_order = [
        "vin_label", "failed", "rows", "t_start", "t_end",
        "active_days_total", "n_weeks", "weeks_lt2_active_days",
        "csp_null_pct", "rpm_null_pct", "anr_null_pct", "vsi_null_pct",
        "sma_null_pct", "ged_null_pct",
        "saledate", "jcopendate", "gap_days",
    ]
    dq_df = dq_df.select(col_order).sort("vin_label")
    dq_path = cfg.RESULTS / "V1_SM_data_quality.csv"
    dq_df.write_csv(str(dq_path))
    print(f"\nData-quality CSV written: {dq_path}")

    elapsed = time.time() - t_total
    print(f"\nTotal runtime: {elapsed:.1f}s")

    # ---------- Verification ----------
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # V1: Count parquet files
    parquet_files = list(cfg.CACHE_WEEKLY.glob("V1_SM_weekly_*.parquet"))
    n_files = len(parquet_files)
    status_v1 = "PASS" if n_files == 34 else "FAIL"
    print(f"V1 - Weekly parquet count: {n_files}/34 [{status_v1}]")

    # V1b: Label-consistency assertion — every parquet's vin_label column must
    #      match cfg.vin_label(raw_vin, failed) for the raw VIN embedded in the file.
    label_errors = []
    for pq in parquet_files:
        pq_df = pl.read_parquet(str(pq), columns=["vin_label", "failed"])
        file_label = pq_df["vin_label"][0]
        file_failed = bool(pq_df["failed"][0])
        # raw VIN: strip the _F_SM / _NF_SM suffix
        suffix = "_F_SM" if file_failed else "_NF_SM"
        raw_vin = file_label.removesuffix(suffix)
        expected_label = cfg.vin_label(raw_vin, file_failed)
        if file_label != expected_label:
            label_errors.append(f"{pq.name}: got '{file_label}', expected '{expected_label}'")
    if label_errors:
        print(f"V1b - Label consistency: FAIL ({len(label_errors)} mismatches)")
        for err in label_errors:
            print(f"     {err}")
    else:
        print(f"V1b - Label consistency: all {n_files} files match cfg.vin_label() [PASS]")

    # V2: VIN8_F_SM span check
    vin8_path = cfg.CACHE_WEEKLY / "V1_SM_weekly_VIN8_F_SM.parquet"
    if vin8_path.exists():
        vin8 = pl.read_parquet(str(vin8_path))
        w_min = str(vin8["week"].min())
        w_max = str(vin8["week"].max())
        n_wks = len(vin8)
        # max week must be <= 2025-10-26 (last telemetry), NOT 2025-12-02 (JCOPENDATE)
        max_week_dt = vin8["week"].max()
        max_week_date = max_week_dt.date() if isinstance(max_week_dt, datetime.datetime) else max_week_dt
        ceiling = datetime.date(2025, 10, 26)
        status_v2 = "PASS" if max_week_date <= ceiling else "FAIL"
        print(f"V2 - VIN8_F_SM: {n_wks} weeks, {w_min} to {w_max} [{status_v2}]")
        print(f"     (max week {max_week_date} <= 2025-10-26 telemetry ceiling)")
    else:
        print("V2 - VIN8_F_SM parquet NOT FOUND [FAIL]")

    # V3: Data-quality CSV - 34 rows + gap VINs
    dq_check = pl.read_csv(str(dq_path))
    n_dq_rows = len(dq_check)
    status_v3a = "PASS" if n_dq_rows == 34 else "FAIL"
    print(f"V3a - DQ CSV rows: {n_dq_rows}/34 [{status_v3a}]")

    print("V3b - Gap VIN check (expected vs actual, tolerance +-1 day):")
    all_gap_pass = True
    for vin_lbl, expected_gap in cfg.GAP_VINS.items():
        row = dq_check.filter(pl.col("vin_label") == vin_lbl)
        if len(row) == 0:
            print(f"     {vin_lbl}: NOT FOUND [FAIL]")
            all_gap_pass = False
            continue
        actual_gap = row["gap_days"][0]
        try:
            actual_gap_int = int(actual_gap)
            diff = abs(actual_gap_int - expected_gap)
            ok = diff <= 1
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_gap_pass = False
            print(f"     {vin_lbl}: expected={expected_gap}, actual={actual_gap_int}, diff={diff} [{status}]")
        except Exception:
            print(f"     {vin_lbl}: gap_days='{actual_gap}' (could not parse) [FAIL]")
            all_gap_pass = False

    gap_overall = "PASS" if all_gap_pass else "FAIL"
    print(f"V3b - Gap VINs overall [{gap_overall}]")

    # V4: Per-VIN summary table
    print("\nV4 - Per-VIN summary (vin_label, n_weeks, t_start, t_end):")
    print(f"  {'VIN':<20} {'n_weeks':>8}  {'t_start':<12}  {'t_end':<12}")
    print("  " + "-" * 58)
    all_meta_sorted = sorted(all_meta, key=lambda x: x["vin_label"])
    for row in all_meta_sorted:
        print(
            f"  {row['vin_label']:<20} {row['n_weeks']:>8}  "
            f"{row['t_start_week']:<12}  {row['t_end_week']:<12}"
        )

    print("\n" + "=" * 60)
    print("Phase 0 complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
