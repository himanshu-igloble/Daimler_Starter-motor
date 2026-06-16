"""
V1_SM_crank_events.py
Phase 1 - Gap-aware crank-event catalog for the SM pipeline.

Inputs  : SM_FAILED  (30.9M rows, 14 VINs)
          SM_NONFAIL (76.3M rows, 20 VINs)
Output  : cache/events/V1_SM_crank_events.parquet  (~20k rows, one per crank event)

Event definition (canonical):
  Consecutive SMA==1 rows belong to one event while the time gap between
  successive SMA==1 rows is <= cfg.CRANK_MAX_INTRA_GAP_S (10s).
  A larger gap starts a new event.

Per-event metrics computed from sentinel-cleaned per-VIN data.
Column contract consumed by Task-4 feature engineering - do NOT rename.

Nullable columns: success (null when rpm_max_15s is null, i.e. unknown outcome),
  baseline_vsi (null when fewer than 3 valid VSI readings in pre-crank window),
  dip_depth (null when baseline_vsi or min_vsi_crank is null),
  recovery_slope (null when min_vsi_crank is null or no post-event VSI with dt > 0).
"""

import sys
import time
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

import numpy as np
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
# Create output directory
# ---------------------------------------------------------------------------
cfg.CACHE_EVENTS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Sentinel cleaning (same rules as Task 2 / weekly cache)
# ---------------------------------------------------------------------------

def clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Replace sentinels with null and rescale VSI if needed."""
    df = df.with_columns([
        pl.when(pl.col("RPM") >= cfg.SENT_U16)
          .then(None).otherwise(pl.col("RPM")).alias("RPM"),
        pl.when(
            (pl.col("VSI") <= cfg.VSI_SENTINEL_LOW) |
            (pl.col("VSI") >= cfg.VSI_SENTINEL_HIGH)
        ).then(None).otherwise(pl.col("VSI")).alias("VSI"),
    ])
    # VSI scaling
    df = df.with_columns(
        pl.when(pl.col("VSI") > cfg.VSI_SCALE_TRIGGER)
          .then(pl.col("VSI") * cfg.VSI_SCALE_FACTOR)
          .otherwise(pl.col("VSI"))
          .alias("VSI")
    )
    return df


# ---------------------------------------------------------------------------
# Gap-aware event grouping
# ---------------------------------------------------------------------------

def extract_crank_events(
    ts_all: np.ndarray,   # int64 seconds, all rows sorted
    sma_all: np.ndarray,  # float32 SMA values
    vsi_all: np.ndarray,  # float32 VSI (sentinel-cleaned, may have nan)
    rpm_all: np.ndarray,  # float32 RPM (sentinel-cleaned, may have nan)
) -> list[dict]:
    """
    Gap-aware event extraction.

    Returns list of dicts with raw event metrics.
    ts_all is in integer seconds (epoch).
    """
    # Indices where SMA == 1
    sma1_mask = (sma_all == 1)
    sma1_idx = np.where(sma1_mask)[0]
    if len(sma1_idx) == 0:
        return []

    # Compute gap between consecutive SMA=1 rows (in seconds).
    # Note: sub-second timestamps are truncated to whole seconds before this point.
    # Duplicate-second rows therefore yield gap == 0, which keeps them intra-event
    # (intended behaviour at 5s telemetry resolution).
    ts_sma1 = ts_all[sma1_idx]
    gaps = np.diff(ts_sma1, prepend=ts_sma1[0])  # first element gap = 0

    # Split into events: new event when gap > CRANK_MAX_INTRA_GAP_S
    event_ids = np.cumsum(gaps > cfg.CRANK_MAX_INTRA_GAP_S)  # 0-indexed

    n_events = event_ids[-1] + 1
    events = []
    baseline_start_s = cfg.CRANK_BASELINE_WINDOW_S[0]  # -90
    baseline_end_s = cfg.CRANK_BASELINE_WINDOW_S[1]    # -10

    for eid in range(n_events):
        mask = event_ids == eid
        ev_global_idx = sma1_idx[mask]
        ev_ts = ts_all[ev_global_idx]

        n_rows = len(ev_global_idx)
        ts_start = ev_ts[0]
        ts_end = ev_ts[-1]
        dur_s = float(ts_end - ts_start) + cfg.CRANK_SAMPLE_WIDTH_S  # +1 sample width
        artifact = dur_s > cfg.CRANK_MAX_PLAUSIBLE_DUR_S
        multi_sample = n_rows >= 2

        # --- baseline VSI: window [start-90s, start-10s] ---
        bl_lo = ts_start + baseline_start_s   # ts_start - 90
        bl_hi = ts_start + baseline_end_s     # ts_start - 10
        # searchsorted on the sorted ts_all array
        bl_lo_idx = int(np.searchsorted(ts_all, bl_lo, side="left"))
        bl_hi_idx = int(np.searchsorted(ts_all, bl_hi, side="right"))
        bl_vsi = vsi_all[bl_lo_idx:bl_hi_idx]
        bl_vsi_valid = bl_vsi[~np.isnan(bl_vsi)]
        if len(bl_vsi_valid) >= 3:
            baseline_vsi = float(np.mean(bl_vsi_valid))
        else:
            baseline_vsi = np.nan

        # --- min VSI during crank rows ---
        ev_vsi = vsi_all[ev_global_idx]
        ev_vsi_valid = ev_vsi[~np.isnan(ev_vsi)]
        if len(ev_vsi_valid) > 0:
            min_vsi_crank = float(np.nanmin(ev_vsi_valid))
        else:
            min_vsi_crank = np.nan

        # --- dip depth ---
        if np.isnan(baseline_vsi) or np.isnan(min_vsi_crank):
            dip_depth = np.nan
        else:
            dip_depth = baseline_vsi - min_vsi_crank

        # --- RPM max in [start, end+15s] ---
        rpm_lo_idx = int(np.searchsorted(ts_all, ts_start, side="left"))
        rpm_hi_idx = int(np.searchsorted(ts_all, ts_end + cfg.CRANK_RPM_POST_S, side="right"))
        rpm_window = rpm_all[rpm_lo_idx:rpm_hi_idx]
        rpm_valid = rpm_window[~np.isnan(rpm_window)]
        if len(rpm_valid) > 0:
            rpm_max_15s = float(np.nanmax(rpm_valid))
        else:
            rpm_max_15s = np.nan

        # --- success ---
        if np.isnan(rpm_max_15s):
            success = None
        else:
            success = bool(rpm_max_15s >= cfg.CRANK_SUCCESS_RPM)

        # --- recovery slope ---
        # First valid VSI in (end, end+45s]
        rec_lo_idx = int(np.searchsorted(ts_all, ts_end, side="right"))
        rec_hi_idx = int(np.searchsorted(ts_all, ts_end + cfg.CRANK_RECOVERY_WINDOW_S, side="right"))
        recovery_slope = np.nan
        if not np.isnan(min_vsi_crank) and rec_lo_idx < rec_hi_idx:
            rec_vsi = vsi_all[rec_lo_idx:rec_hi_idx]
            rec_ts = ts_all[rec_lo_idx:rec_hi_idx]
            # Find min-VSI row timestamp within crank (for denominator)
            if len(ev_vsi_valid) > 0:
                # find actual minimum-VSI position (skip nan slots)
                valid_positions = np.where(~np.isnan(ev_vsi))[0]
                min_val_local = np.nanargmin(ev_vsi[valid_positions])
                min_vsi_ev_global = ev_global_idx[valid_positions[min_val_local]]
                ts_min_vsi = ts_all[min_vsi_ev_global]

                # Find first valid post-event VSI strictly after the min-VSI row
                for j in range(len(rec_vsi)):
                    if not np.isnan(rec_vsi[j]):
                        dt = float(rec_ts[j] - ts_min_vsi)
                        if dt > 0:
                            recovery_slope = float((rec_vsi[j] - min_vsi_crank) / dt)
                            break
                        # dt <= 0: keep scanning

        events.append({
            "n_rows": n_rows,
            "ts_start_s": int(ts_start),
            "ts_end_s": int(ts_end),
            "multi_sample": multi_sample,
            "dur_s": dur_s,
            "artifact": artifact,
            "baseline_vsi": None if np.isnan(baseline_vsi) else baseline_vsi,
            "min_vsi_crank": None if np.isnan(min_vsi_crank) else min_vsi_crank,
            "dip_depth": None if np.isnan(dip_depth) else dip_depth,
            "rpm_max_15s": None if np.isnan(rpm_max_15s) else rpm_max_15s,
            "success": success,
            "recovery_slope": None if np.isnan(recovery_slope) else recovery_slope,
        })

    return events


# ---------------------------------------------------------------------------
# Process one VIN
# ---------------------------------------------------------------------------

def process_vin(raw_vin: str, failed: bool, parquet_path: Path) -> list[dict]:
    """Collect one VIN's rows, clean, extract events, return list of event dicts."""
    suffix = "_F_SM" if failed else "_NF_SM"
    vin_label = cfg.vin_label(raw_vin, failed)

    # Lazy scan + filter + select + collect (streaming)
    lf = (
        pl.scan_parquet(str(parquet_path))
        .filter(pl.col("VIN") == raw_vin)
        .filter(pl.col("timestamp").is_not_null())
        .select(["timestamp", "VSI", "RPM", "SMA"])
    )
    df = lf.collect(engine="streaming")

    if len(df) == 0:
        print(f"  WARN: {vin_label} has 0 rows after filtering")
        return []

    # Sentinel cleaning
    df = clean_columns(df)

    # Sort by timestamp
    df = df.sort("timestamp")

    # Convert timestamp to int64 seconds (epoch)
    ts_np = df["timestamp"].cast(pl.Int64).to_numpy() // 1_000_000  # us -> s
    sma_np = df["SMA"].to_numpy().astype(np.float32)
    vsi_np = df["VSI"].to_numpy().astype(np.float32)
    rpm_np = df["RPM"].to_numpy().astype(np.float32)

    # t_end = max timestamp for this VIN
    t_end_s = int(ts_np[-1])  # already sorted

    # Extract events
    events = extract_crank_events(ts_np, sma_np, vsi_np, rpm_np)

    if len(events) == 0:
        print(f"  WARN: {vin_label} has 0 crank events")
        return []

    # Add days_before_t_end and compute retry_within_120s
    result_rows = []
    for i, ev in enumerate(events):
        ts_start_s = ev["ts_start_s"]
        ts_end_s_ev = ev["ts_end_s"]

        # days_before_t_end: (vin t_end date - ts_start date).days
        # ts_start_s is epoch seconds
        ts_start_date = ts_start_s // 86400
        days_before = (t_end_s // 86400) - ts_start_date
        ev["days_before_t_end"] = int(days_before)

        # retry_within_120s: does the NEXT event start within 120s of this event's end?
        if i + 1 < len(events):
            next_start = events[i + 1]["ts_start_s"]
            ev["retry_within_120s"] = bool((next_start - ts_end_s_ev) <= cfg.CRANK_RETRY_WINDOW_S)
        else:
            ev["retry_within_120s"] = False

        # Sequential event_id per VIN
        ev["event_id"] = i + 1  # 1-indexed
        ev["vin_label"] = vin_label
        ev["failed"] = failed

        result_rows.append(ev)

    return result_rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("V1_SM Phase 1: Gap-Aware Crank-Event Catalog")
    print("=" * 70)
    t_total = time.time()

    all_events = []

    # Failed VINs (VIN1-VIN14)
    print("\n[1/2] Processing FAILED parquet (14 VINs) ...")
    for i in range(1, cfg.N_FAILED + 1):
        raw_vin = f"VIN{i}"
        vin_label = cfg.vin_label(raw_vin, True)
        t0 = time.time()
        rows = process_vin(raw_vin, True, cfg.SM_FAILED)
        n_ev = len(rows)
        print(f"  {vin_label}: {n_ev} events ({time.time()-t0:.1f}s)")
        all_events.extend(rows)

    # Non-failed VINs (VIN1-VIN20)
    print("\n[2/2] Processing NONFAILED parquet (20 VINs) ...")
    for i in range(1, cfg.N_NONFAILED + 1):
        raw_vin = f"VIN{i}"
        vin_label = cfg.vin_label(raw_vin, False)
        t0 = time.time()
        rows = process_vin(raw_vin, False, cfg.SM_NONFAIL)
        n_ev = len(rows)
        print(f"  {vin_label}: {n_ev} events ({time.time()-t0:.1f}s)")
        all_events.extend(rows)

    print(f"\nTotal events extracted: {len(all_events)}")

    # ---------------------------------------------------------------------------
    # Build DataFrame with canonical column order
    # ---------------------------------------------------------------------------
    # Convert ts_start_s back to datetime for the output column ts_start
    import datetime as dt_mod
    from datetime import timezone as _tz

    output_rows = []
    for ev in all_events:
        ts_start_dt = dt_mod.datetime.fromtimestamp(ev["ts_start_s"], tz=_tz.utc).replace(tzinfo=None)
        output_rows.append({
            "vin_label": ev["vin_label"],
            "failed": ev["failed"],
            "event_id": ev["event_id"],
            "ts_start": ts_start_dt,
            "n_rows": ev["n_rows"],
            "multi_sample": ev["multi_sample"],
            "dur_s": ev["dur_s"],
            "artifact": ev["artifact"],
            "baseline_vsi": ev["baseline_vsi"],
            "min_vsi_crank": ev["min_vsi_crank"],
            "dip_depth": ev["dip_depth"],
            "rpm_max_15s": ev["rpm_max_15s"],
            "success": ev["success"],
            "recovery_slope": ev["recovery_slope"],
            "retry_within_120s": ev["retry_within_120s"],
            "days_before_t_end": ev["days_before_t_end"],
        })

    # Build polars DataFrame with explicit schema for nullable columns
    events_df = pl.DataFrame(
        output_rows,
        schema={
            "vin_label": pl.String,
            "failed": pl.Boolean,
            "event_id": pl.Int32,
            "ts_start": pl.Datetime("us"),
            "n_rows": pl.Int32,
            "multi_sample": pl.Boolean,
            "dur_s": pl.Float64,
            "artifact": pl.Boolean,
            "baseline_vsi": pl.Float64,
            "min_vsi_crank": pl.Float64,
            "dip_depth": pl.Float64,
            "rpm_max_15s": pl.Float64,
            "success": pl.Boolean,          # nullable - null when rpm_max_15s is null (unknown outcome)
            "recovery_slope": pl.Float64,
            "retry_within_120s": pl.Boolean,
            "days_before_t_end": pl.Int32,
        },
        orient="row",
    )

    # Write parquet
    out_path = cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet"
    tmp_path = out_path.with_suffix(".tmp.parquet")
    events_df.write_parquet(str(tmp_path))
    tmp_path.replace(out_path)
    print(f"Events parquet written: {out_path} ({len(events_df)} rows)")

    # ---------------------------------------------------------------------------
    # Step 2: Reconciliation console table
    # ---------------------------------------------------------------------------
    print()
    print("=" * 70)
    print("RECONCILIATION vs KT_startermotor_alternator.md 6.4 (gap-aware definition):")

    # Separate failed/nonfailed
    f_df = events_df.filter(pl.col("failed") == True)
    nf_df = events_df.filter(pl.col("failed") == False)

    total_events = len(events_df)
    n_artifacts = int(events_df["artifact"].sum())

    # Non-artifact subsets
    f_na = f_df.filter(pl.col("artifact") == False)
    nf_na = nf_df.filter(pl.col("artifact") == False)

    # Mean duration (non-artifact)
    f_mean_dur = float(f_na["dur_s"].mean()) if len(f_na) > 0 else float("nan")
    nf_mean_dur = float(nf_na["dur_s"].mean()) if len(nf_na) > 0 else float("nan")

    # Mean dip_depth (non-artifact, non-null)
    f_dip = f_na["dip_depth"].drop_nulls()
    nf_dip = nf_na["dip_depth"].drop_nulls()
    f_mean_dip = float(f_dip.mean()) if len(f_dip) > 0 else float("nan")
    nf_mean_dip = float(nf_dip.mean()) if len(nf_dip) > 0 else float("nan")

    # Failed crank rate: share of non-artifact events with success == False
    # excluding success-null events
    f_success_known = f_na.filter(pl.col("success").is_not_null())
    nf_success_known = nf_na.filter(pl.col("success").is_not_null())
    f_failed_crank_rate = (
        float(f_success_known.filter(pl.col("success") == False).shape[0]) / len(f_success_known) * 100
        if len(f_success_known) > 0 else float("nan")
    )
    nf_failed_crank_rate = (
        float(nf_success_known.filter(pl.col("success") == False).shape[0]) / len(nf_success_known) * 100
        if len(nf_success_known) > 0 else float("nan")
    )
    # null-success share
    f_null_success_pct = float(f_na.filter(pl.col("success").is_null()).shape[0]) / len(f_na) * 100 if len(f_na) > 0 else float("nan")
    nf_null_success_pct = float(nf_na.filter(pl.col("success").is_null()).shape[0]) / len(nf_na) * 100 if len(nf_na) > 0 else float("nan")

    # Multi-sample rate (non-artifact)
    f_multi_rate = float(f_na["multi_sample"].mean()) * 100 if len(f_na) > 0 else float("nan")
    nf_multi_rate = float(nf_na["multi_sample"].mean()) * 100 if len(nf_na) > 0 else float("nan")

    # Retry rate (non-artifact)
    f_retry_rate = float(f_na["retry_within_120s"].mean()) * 100 if len(f_na) > 0 else float("nan")
    nf_retry_rate = float(nf_na["retry_within_120s"].mean()) * 100 if len(nf_na) > 0 else float("nan")

    print(f"  events total:              {total_events} (raw prelim found 20,729 with gap-naive grouping)")
    print(f"  artifacts flagged:         {n_artifacts}")
    print(f"  mean dur_s (non-artifact): failed {f_mean_dur:.1f}s vs NF {nf_mean_dur:.1f}s   | KT claim: 3.2s vs 2.2s (+48%)")
    print(f"  mean dip_depth:            failed {f_mean_dip:.2f}V vs NF {nf_mean_dip:.2f}V | KT: min-VSI 23.1V vs 24.0V")
    print(f"  failed_crank_rate:         failed {f_failed_crank_rate:.1f}% vs NF {nf_failed_crank_rate:.1f}%   | KT threshold: >5% critical")
    print(f"  (null-success share:       failed {f_null_success_pct:.1f}% NF {nf_null_success_pct:.1f}%)")
    print(f"  multi_sample_rate:         failed {f_multi_rate:.1f}% vs NF {nf_multi_rate:.1f}%")
    print(f"  retry_rate:                failed {f_retry_rate:.1f}% vs NF {nf_retry_rate:.1f}%")
    print("=" * 70)

    # ---------------------------------------------------------------------------
    # Step 3: Sanity assertions
    # ---------------------------------------------------------------------------
    print()
    print("SANITY ASSERTIONS:")
    any_fail = False

    # Assertion 1: Every VIN has >= MIN_EVENTS_PER_VIN non-artifact events
    print(f"A1: Per-VIN non-artifact event counts (min required: {cfg.MIN_EVENTS_PER_VIN}):")
    vin_na_counts = (
        events_df
        .filter(pl.col("artifact") == False)
        .group_by("vin_label")
        .agg(pl.len().alias("n_na_events"))
        .sort("vin_label")
    )
    for row in vin_na_counts.iter_rows(named=True):
        ok = row["n_na_events"] >= cfg.MIN_EVENTS_PER_VIN
        status = "OK" if ok else "WARN-BELOW-MIN"
        if not ok:
            print(f"  WARN: {row['vin_label']}: {row['n_na_events']} non-artifact events < {cfg.MIN_EVENTS_PER_VIN}")
        else:
            print(f"  {row['vin_label']}: {row['n_na_events']} [{status}]")

    # Assertion 2: No event with dur_s > 60 has artifact == False
    bad_artifact = events_df.filter(
        (pl.col("dur_s") > cfg.CRANK_MAX_PLAUSIBLE_DUR_S) &
        (pl.col("artifact") == False)
    )
    a2_ok = len(bad_artifact) == 0
    if not a2_ok:
        print(f"A2: FAIL - {len(bad_artifact)} events with dur_s > 60 but artifact=False")
        any_fail = True
    else:
        print(f"A2: All events with dur_s > {cfg.CRANK_MAX_PLAUSIBLE_DUR_S}s correctly flagged artifact=True [PASS]")

    # Assertion 3: dip_depth null rate < 40%
    total_na = len(events_df.filter(pl.col("artifact") == False))
    n_dip_null = int(
        events_df.filter(pl.col("artifact") == False)["dip_depth"].is_null().sum()
    )
    dip_null_rate = n_dip_null / total_na * 100 if total_na > 0 else 100.0
    if dip_null_rate >= 40.0:
        print(f"A3: WARN - dip_depth null rate = {dip_null_rate:.1f}% >= 40% (baseline windows sparse)")
        any_fail = True
    else:
        print(f"A3: dip_depth null rate = {dip_null_rate:.1f}% < 40% [PASS]")

    # Assertion 4: Total events within +-15% of 20,729
    gap_naive_ref = 20729
    pct_diff = abs(total_events - gap_naive_ref) / gap_naive_ref * 100
    a4_ok = pct_diff <= 15.0
    if not a4_ok:
        print(f"A4: WARN - total events {total_events} is {pct_diff:.1f}% away from ref {gap_naive_ref} (limit 15%)")
        any_fail = True
    else:
        print(f"A4: total events {total_events} vs gap-naive ref {gap_naive_ref} ({pct_diff:.1f}% diff) [PASS]")

    if not any_fail:
        print("\nAll sanity assertions passed.")
    else:
        print("\nSome assertions had warnings (see above) -- script completed without crash.")

    elapsed = time.time() - t_total
    print(f"\nTotal runtime: {elapsed:.1f}s")
    print("=" * 70)
    print("Phase 1 complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
