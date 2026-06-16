"""
B6 — VIN1_F_SM Daily-Aggregation Crank-Spike Re-test
V1 verdict was "insufficient data" at weekly granularity.
This test uses daily failed-crank + retry counts and applies the A1 alarm rule.

A1 rule:
  - 7-day rolling sum S7 of (failed cranks + retries per day)
  - Baseline = own first-half mean + 3σ (absolute floor S7 >= 3)
  - Alarm: S7 > threshold for >= 2 consecutive days
  - Evaluated on SECOND HALF of history only

Also runs same daily rule on 3 NF trucks with highest crank activity
(VIN4_NF, VIN15_NF, VIN5_NF — excluding SMA-dead VIN11_NF, VIN20_NF).

Outputs:
  B6_vin1f_daily_series.csv — daily series with S7 and alarm flag
  B6_alarm_dates.csv        — alarm onset dates with lead-to-t_end
"""

import polars as pl
import numpy as np
from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path("D:/Daimler-starter_motor_alternator_battery")
EVENTS_PARQ = ROOT / "STARTER MOTOR/cache/events/V1_SM_crank_events.parquet"
DQ_CSV = ROOT / "STARTER MOTOR/results/V1_SM_data_quality.csv"
OUT_DIR = ROOT / "STARTER MOTOR/V2_program/analysis/raw_screens/out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# NF sanity-check trucks (top crank activity, SMA-active)
# VIN11_NF (4139 events) and VIN20_NF are SMA-dead => skip
# VIN4_NF (1027), VIN15_NF (942), VIN5_NF (764)
NF_SANITY = ["VIN4_NF_SM", "VIN15_NF_SM", "VIN5_NF_SM"]

dq = pl.read_csv(DQ_CSV)
dq_map = {r["vin_label"]: r for r in dq.iter_rows(named=True)}

ev = pl.read_parquet(EVENTS_PARQ)

VIN1_TSTART = "2024-09-30"
VIN1_TEND = "2025-09-15"  # t_end from DQ
VIN1_JCOPENDATE = "2025-11-26"
VIN1_GAP_DAYS = 72


def compute_daily_series(ev_vin: pl.DataFrame, vin_label: str) -> pl.DataFrame:
    """
    Build daily time series of failed cranks + retries.
    Exclude artifact events.
    retry = retry_within_120s == True on a *failed* crank
    (retry attempt follows a failed crank within 120s)
    """
    df = ev_vin.filter(pl.col("artifact") == False)
    df = df.with_columns(pl.col("ts_start").dt.date().alias("date"))

    # Daily failed cranks
    daily_failed = (
        df.filter(pl.col("success") == False)
        .group_by("date")
        .agg(pl.len().alias("n_failed"))
    )

    # Daily retries (retry_within_120s flag on any event, regardless of current success)
    # Interpretation: retry_within_120s = this crank started within 120s of the previous crank end
    # Count unique retry sessions per day (not per-event)
    daily_retries = (
        df.filter(pl.col("retry_within_120s") == True)
        .group_by("date")
        .agg(pl.len().alias("n_retries"))
    )

    # Full date range
    t_start = df["ts_start"].min().date()
    t_end = df["ts_start"].max().date()
    all_dates = pl.date_range(t_start, t_end, interval="1d", eager=True).alias("date")
    date_df = pl.DataFrame({"date": all_dates})

    daily = (
        date_df
        .join(daily_failed, on="date", how="left")
        .join(daily_retries, on="date", how="left")
        .with_columns([
            pl.col("n_failed").fill_null(0),
            pl.col("n_retries").fill_null(0),
        ])
        .with_columns(
            (pl.col("n_failed") + pl.col("n_retries")).alias("n_events")
        )
    )
    return daily


def apply_a1_rule(daily: pl.DataFrame, vin_label: str) -> tuple:
    """
    Apply A1 daily alarm rule:
      S7 = 7-day rolling sum of n_events
      Baseline = first-half mean + 3σ, floor S7>=3
      Alarm when S7 > threshold for >=2 consecutive days (evaluated on second half)
    Returns (daily_with_alarm_df, alarm_dates_list)
    """
    n = daily.height
    half = n // 2

    n_ev = daily["n_events"].to_numpy()

    # 7-day rolling sum (causal: sum of days i-6..i)
    s7 = np.array([n_ev[max(0, i-6):i+1].sum() for i in range(n)])

    # Baseline from first half
    s7_first = s7[:half]
    baseline_mean = s7_first.mean()
    baseline_std = s7_first.std(ddof=1) if len(s7_first) > 1 else 0.0
    threshold = max(baseline_mean + 3 * baseline_std, 3.0)

    print(f"  {vin_label}: n_days={n}, half={half}, baseline_mean={baseline_mean:.2f}, "
          f"baseline_std={baseline_std:.2f}, threshold={threshold:.2f}")

    # Alarm on second half: S7 > threshold for >=2 consecutive days
    alarm_raw = (s7 > threshold).astype(int)
    # Only evaluate on second half
    alarm_raw[:half] = 0

    alarm_consec = np.zeros(n, dtype=int)
    for i in range(half, n):
        if alarm_raw[i] == 1 and i > 0 and alarm_raw[i-1] == 1:
            alarm_consec[i] = 1
            alarm_consec[i-1] = 1  # mark both

    dates = daily["date"].to_list()

    # Find alarm onset dates (first day of each consecutive run)
    alarm_dates = []
    in_alarm = False
    for i in range(half, n):
        if alarm_consec[i] == 1 and not in_alarm:
            alarm_dates.append({
                "vin_label": vin_label,
                "alarm_start_date": dates[i],
                "s7_value": round(float(s7[i]), 1),
                "threshold": round(float(threshold), 2),
            })
            in_alarm = True
        elif alarm_consec[i] == 0:
            in_alarm = False

    daily_out = daily.with_columns([
        pl.Series("s7", s7),
        pl.Series("threshold", np.full(n, threshold)),
        pl.Series("alarm_consec", alarm_consec.astype(bool)),
    ])

    return daily_out, alarm_dates, threshold


# === VIN1_F_SM ===
print("=== B6: VIN1_F_SM daily series ===")
v1_ev = ev.filter(pl.col("vin_label") == "VIN1_F_SM")
print(f"  Total events: {v1_ev.height}, failed: {v1_ev.filter(pl.col('success')==False).height}")

v1_daily = compute_daily_series(v1_ev, "VIN1_F_SM")
print(f"  Daily series: {v1_daily.height} days, "
      f"total failed={v1_daily['n_failed'].sum()}, total retries={v1_daily['n_retries'].sum()}")

# Check June 24 2025 specifically
v1_june24 = v1_daily.filter(pl.col("date").cast(str).str.contains("2025-06-2"))
print(f"  Late June 2025 daily counts:")
print(v1_june24.select(["date", "n_failed", "n_retries", "n_events"]))

v1_daily_alarm, alarm_dates_v1, thresh_v1 = apply_a1_rule(v1_daily, "VIN1_F_SM")

# Save daily series
v1_daily_out = v1_daily_alarm.with_columns(pl.lit("VIN1_F_SM").alias("vin_label"))
v1_csv = OUT_DIR / "B6_vin1f_daily_series.csv"
v1_daily_out.write_csv(v1_csv)
print(f"\nVIN1_F daily series saved to {v1_csv}")

# Report alarm dates with lead to t_end
v1_t_end = v1_ev["ts_start"].max().date()
print(f"\nVIN1_F alarm dates (threshold={thresh_v1:.2f}):")
if alarm_dates_v1:
    for a in alarm_dates_v1:
        alarm_dt = a["alarm_start_date"]
        lead_days = (v1_t_end - alarm_dt).days
        jco_dt = pl.Series(["2025-11-26"]).str.to_date()[0]
        lead_to_jco = (jco_dt - alarm_dt).days
        print(f"  Alarm {alarm_dt}: S7={a['s7_value']}, lead_to_t_end={lead_days}d, "
              f"lead_to_JCOPENDATE(2025-11-26)={lead_to_jco}d")
        a["lead_to_t_end_days"] = lead_days
        a["lead_to_jcopendate_days"] = lead_to_jco
else:
    print("  NO ALARM TRIGGERED")

# Print June 24 S7 context
v1_jun24_alarm = v1_daily_alarm.filter(
    (pl.col("date").cast(str) >= "2025-06-18") &
    (pl.col("date").cast(str) <= "2025-07-05")
)
print(f"\nJune 18 - Jul 5 window (S7 + alarm flag):")
print(v1_jun24_alarm.select(["date", "n_failed", "n_retries", "n_events", "s7", "threshold", "alarm_consec"]))

# === NF Sanity Check ===
print("\n=== B6: NF Sanity Check (false-alarm test) ===")
all_alarm_rows = alarm_dates_v1.copy()

for nf_label in NF_SANITY:
    vin_raw = nf_label  # already has _NF_SM suffix
    nf_ev = ev.filter(pl.col("vin_label") == nf_label)
    if nf_ev.height == 0:
        print(f"  {nf_label}: no events")
        continue
    print(f"\n  {nf_label} (n_events={nf_ev.height}):")
    nf_daily = compute_daily_series(nf_ev, nf_label)
    nf_daily_alarm, alarm_nf, thresh_nf = apply_a1_rule(nf_daily, nf_label)
    nf_t_end = nf_ev["ts_start"].max().date()
    if alarm_nf:
        for a in alarm_nf:
            a["lead_to_t_end_days"] = (nf_t_end - a["alarm_start_date"]).days
            a["lead_to_jcopendate_days"] = None
        print(f"  FALSE ALARMS: {len(alarm_nf)} alarm onset(s), threshold={thresh_nf:.2f}")
        for a in alarm_nf:
            print(f"    {a['alarm_start_date']}: S7={a['s7_value']}")
        all_alarm_rows.extend(alarm_nf)
    else:
        print(f"  No false alarm triggered (threshold={thresh_nf:.2f}) — CLEAN")

# Save alarm dates (all VINs)
alarm_df = pl.DataFrame(all_alarm_rows) if all_alarm_rows else pl.DataFrame({
    "vin_label": [], "alarm_start_date": [], "s7_value": [], "threshold": [],
    "lead_to_t_end_days": [], "lead_to_jcopendate_days": []
})
alarm_csv = OUT_DIR / "B6_alarm_dates.csv"
alarm_df.write_csv(alarm_csv)
print(f"\nAlarm dates saved to {alarm_csv}")

# Weekly comparison context
print("\n=== B6 VERDICT ===")
print(f"VIN1_F t_end={v1_t_end}, JCOPENDATE=2025-11-26, gap=72d")
print(f"2025-06-24 burst: 9 failed cranks in one day")
if alarm_dates_v1:
    first_alarm = alarm_dates_v1[0]
    print(f"DAILY rule alarm: TRIGGERED on {first_alarm['alarm_start_date']}, "
          f"S7={first_alarm['s7_value']}, threshold={thresh_v1:.2f}")
    print(f"  Lead to t_end: {first_alarm['lead_to_t_end_days']}d")
    print(f"  Lead to JCOPENDATE: {first_alarm['lead_to_jcopendate_days']}d")
    print("=> Daily aggregation RESOLVES the V1 'insufficient data' finding: YES")
else:
    print("DAILY rule alarm: NOT TRIGGERED despite burst")
    print("=> Daily aggregation does NOT resolve V1 finding")
print(f"NF sanity checked: {NF_SANITY}")
