"""
V1_1_SM_build_daily_cache.py
Per-VIN DAILY aggregate cache for the SM fleet (daily-resolution graph layer).

Replicates the sentinel cleaning + regime logic of
"STARTER MOTOR/src/V1_SM_build_weekly_cache.py" EXACTLY, but aggregates by
CALENDAR DAY instead of ISO week.

Inputs  : SM_FAILED  (30.9M rows, 14 VINs)
          SM_NONFAIL (76.3M rows, 20 VINs)
Outputs : STARTER MOTOR/V1.1/cache/daily/V1_1_SM_daily_<vin_label>.parquet (34 files)

One row per ACTIVE calendar day. Columns (contract):
  vin_label, failed, date, n_rows, sma_obs_rows, sma1_rows,
  vsi_drive_rows,                                   # weight for reconciliation
  vsi_drive_mean, vsi_drive_std, vsi_drive_p05, vsi_drive_p95  (RPM > 700),
  vsi_rest_median, vsi_rest_p05                     (RPM null or 0),
  vsi_idle_mean                                     (0 < RPM <= 700),
  rpm_mean, csp_mean, vsi_below_21_rows, vsi_above_32_rows

Nullable contract: vsi_drive_*, vsi_rest_*, vsi_idle_mean are NULLABLE
(null = no rows in that regime that day).

READ-ONLY w.r.t. V1 files and Data/ — this script only writes under V1.1/.
"""

import datetime
import time
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

import polars as pl

# ---------------------------------------------------------------------------
# Load V1 config (single source of truth for paths / sentinels / thresholds)
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[3]
_spec = spec_from_file_location(
    "v1_sm_config", _REPO / "STARTER MOTOR" / "src" / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

V11 = _REPO / "STARTER MOTOR" / "V1.1"
CACHE_DAILY = V11 / "cache" / "daily"
CACHE_DAILY.mkdir(parents=True, exist_ok=True)

WEEKLY_DIR = _REPO / "STARTER MOTOR" / "cache" / "weekly"
DQ_CSV = _REPO / "STARTER MOTOR" / "results" / "V1_SM_data_quality.csv"


# ---------------------------------------------------------------------------
# Sentinel cleaning — IDENTICAL to V1_SM_build_weekly_cache.clean()
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
# Daily aggregation expressions (regimes identical to weekly cache)
#   driving: RPM > RPM_DRIVE_THRESH (700)
#   rest   : RPM null or 0
#   idle   : 0 < RPM <= 700
# ---------------------------------------------------------------------------
_DRIVE = pl.col("RPM") > cfg.RPM_DRIVE_THRESH
_REST = pl.col("RPM").is_null() | (pl.col("RPM") == 0)
_IDLE = (pl.col("RPM") > 0) & (pl.col("RPM") <= cfg.RPM_DRIVE_THRESH)

AGG = [
    pl.len().alias("n_rows"),
    pl.col("SMA").is_not_null().sum().alias("sma_obs_rows"),
    (pl.col("SMA").fill_null(0) == 1).sum().alias("sma1_rows"),
    # Driving regime (alternator charging)
    pl.col("VSI").filter(_DRIVE).is_not_null().sum().alias("vsi_drive_rows"),
    pl.col("VSI").filter(_DRIVE).mean().alias("vsi_drive_mean"),
    pl.col("VSI").filter(_DRIVE).std().alias("vsi_drive_std"),
    pl.col("VSI").filter(_DRIVE).quantile(0.05).alias("vsi_drive_p05"),
    pl.col("VSI").filter(_DRIVE).quantile(0.95).alias("vsi_drive_p95"),
    # Resting (engine off = battery state)
    pl.col("VSI").filter(_REST).median().alias("vsi_rest_median"),
    pl.col("VSI").filter(_REST).quantile(0.05).alias("vsi_rest_p05"),
    # Idle regime
    pl.col("VSI").filter(_IDLE).mean().alias("vsi_idle_mean"),
    pl.col("RPM").mean().alias("rpm_mean"),
    pl.col("CSP").mean().alias("csp_mean"),
    (pl.col("VSI") < cfg.VSI_ALERT_LOW).sum().alias("vsi_below_21_rows"),
    (pl.col("VSI") > cfg.VSI_ALERT_HIGH).sum().alias("vsi_above_32_rows"),
]

COL_ORDER = [
    "vin_label", "failed", "date", "n_rows", "sma_obs_rows", "sma1_rows",
    "vsi_drive_rows", "vsi_drive_mean", "vsi_drive_std",
    "vsi_drive_p05", "vsi_drive_p95",
    "vsi_rest_median", "vsi_rest_p05", "vsi_idle_mean",
    "rpm_mean", "csp_mean", "vsi_below_21_rows", "vsi_above_32_rows",
]


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------
def process_file(parquet_path: Path, failed: bool) -> list[dict]:
    tag = "FAILED" if failed else "NONFAIL"
    print(f"  Daily aggregation {tag} ... ", end="", flush=True)
    t0 = time.time()

    lf = pl.scan_parquet(str(parquet_path))
    lf = clean(lf)
    lf = lf.filter(pl.col("timestamp").is_not_null())   # same null-ts drop as V1
    lf = lf.with_columns([
        pl.concat_str([
            pl.col("VIN"),
            pl.lit("_F_SM" if failed else "_NF_SM")
        ]).alias("vin_label"),
        pl.col("timestamp").dt.date().alias("date"),
    ])

    daily_df = (
        lf.group_by(["vin_label", "date"])
        .agg(AGG)
        .collect(engine="streaming")
    )
    print(f"done ({time.time()-t0:.1f}s)", flush=True)

    meta = []
    for vin_label in sorted(daily_df["vin_label"].unique().to_list()):
        vin_daily = (
            daily_df
            .filter(pl.col("vin_label") == vin_label)
            .with_columns(pl.lit(failed).alias("failed"))
            .sort("date")
            .select(COL_ORDER)
        )
        out_path = CACHE_DAILY / f"V1_1_SM_daily_{vin_label}.parquet"
        tmp_path = out_path.with_suffix(".tmp.parquet")
        vin_daily.write_parquet(str(tmp_path))
        tmp_path.replace(out_path)
        meta.append({
            "vin_label": vin_label,
            "n_days": len(vin_daily),
            "d_start": vin_daily["date"].min(),
            "d_end": vin_daily["date"].max(),
            "n_rows_total": int(vin_daily["n_rows"].sum()),
        })
    return meta


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(all_meta: list[dict]) -> None:
    print("\n" + "=" * 64)
    print("VERIFICATION")
    print("=" * 64)

    # V1: file count
    files = sorted(CACHE_DAILY.glob("V1_1_SM_daily_*.parquet"))
    status = "PASS" if len(files) == 34 else "FAIL"
    print(f"V1 - Daily parquet count: {len(files)}/34 [{status}]")

    n_days_all = [m["n_days"] for m in all_meta]
    print(f"V1b - Rows-per-file (active days) range: "
          f"min={min(n_days_all)}, max={max(n_days_all)}")

    # V2: weekly reconciliation for 3 VINs
    print("\nV2 - Weekly-cache reconciliation (3 VINs):")
    for vin in ["VIN8_F_SM", "VIN1_NF_SM", "VIN5_F_SM"]:
        wk = pl.read_parquet(str(WEEKLY_DIR / f"V1_SM_weekly_{vin}.parquet"))
        dy = pl.read_parquet(str(CACHE_DAILY / f"V1_1_SM_daily_{vin}.parquet"))
        wk_sum = int(wk["n_rows"].sum())
        dy_sum = int(dy["n_rows"].sum())
        ok = "PASS" if wk_sum == dy_sum else "FAIL"
        print(f"  {vin}: weekly n_rows sum={wk_sum:,}  daily sum={dy_sum:,}  "
              f"diff={wk_sum - dy_sum} [{ok}]")

        # 2 sample weeks: pick weeks with non-null vsi_drive_mean and >=3 active days
        cand = wk.filter(
            pl.col("vsi_drive_mean").is_not_null() & (pl.col("active_days") >= 3)
        ).sort("week")
        sample_weeks = [cand["week"][len(cand) // 3], cand["week"][2 * len(cand) // 3]]
        for w in sample_weeks:
            w_date = w.date() if isinstance(w, datetime.datetime) else w
            w_end = w_date + datetime.timedelta(days=7)
            wk_val = wk.filter(pl.col("week") == w)["vsi_drive_mean"][0]
            d = dy.filter(
                (pl.col("date") >= w_date) & (pl.col("date") < w_end) &
                pl.col("vsi_drive_mean").is_not_null()
            )
            num = (d["vsi_drive_mean"] * d["vsi_drive_rows"]).sum()
            den = d["vsi_drive_rows"].sum()
            dy_val = num / den if den else float("nan")
            diff = abs(wk_val - dy_val)
            ok = "PASS" if diff < 1e-6 else ("OK(float)" if diff < 1e-3 else "FAIL")
            print(f"     week {w_date}: weekly vsi_drive_mean={wk_val:.6f}  "
                  f"daily row-weighted={dy_val:.6f}  diff={diff:.2e} [{ok}]")

    # V3: per-VIN date range vs V1 data-quality t_start / t_end
    print("\nV3 - Per-VIN date range vs V1_SM_data_quality.csv:")
    dq = pl.read_csv(str(DQ_CSV))
    print(f"  {'VIN':<14} {'n_days':>6}  {'d_start':<11} {'d_end':<11} match")
    print("  " + "-" * 54)
    all_ok = True
    for m in sorted(all_meta, key=lambda x: x["vin_label"]):
        row = dq.filter(pl.col("vin_label") == m["vin_label"]).to_dicts()[0]
        exp_start = datetime.datetime.fromisoformat(row["t_start"]).date()
        exp_end = datetime.datetime.fromisoformat(row["t_end"]).date()
        ok = (m["d_start"] == exp_start) and (m["d_end"] == exp_end)
        all_ok &= ok
        print(f"  {m['vin_label']:<14} {m['n_days']:>6}  "
              f"{m['d_start']}  {m['d_end']}  {'PASS' if ok else f'FAIL (exp {exp_start}..{exp_end})'}")
    print(f"V3 overall: [{'PASS' if all_ok else 'FAIL'}]")

    # V3b: VIN8_F_SM telemetry ceiling
    vin8_end = next(m["d_end"] for m in all_meta if m["vin_label"] == "VIN8_F_SM")
    ok = "PASS" if vin8_end == datetime.date(2025, 10, 26) else "FAIL"
    print(f"V3b - VIN8_F_SM ends {vin8_end} (expected 2025-10-26) [{ok}]")


# ---------------------------------------------------------------------------
def main():
    print("=" * 64)
    print("V1.1 SM: Daily Aggregate Cache Builder")
    print("=" * 64)
    t0 = time.time()

    all_meta = []
    print("\n[1/2] FAILED parquet ...")
    all_meta += process_file(cfg.SM_FAILED, failed=True)
    print("\n[2/2] NONFAILED parquet ...")
    all_meta += process_file(cfg.SM_NONFAIL, failed=False)

    verify(all_meta)
    print(f"\nTotal runtime: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
