"""
telemetry_health.py  (B7) -- Starter-Motor V2 Governance Monitors
=================================================================
Per-truck telemetry health check.  Reads per-VIN weekly cache parquets.

METRIC DERIVATION
-----------------
Activity proxy: weekly rows / active_days  (rows per active day = rpd).
  Source fields: n_rows (uint32) and active_days (uint32) from weekly cache.
  Weeks with active_days == 0 are excluded from all rolling computations
  (avoids division-by-zero and calendar-gap artefacts).

TAPER ALARM LOGIC
-----------------
Baseline: trailing-12-week mean rpd (weeks [i-13 : i-1] relative to target week i).
Signal:   single-week rpd at week i.
Ratio_i = rpd_i / baseline_12wk_mean.

Alarm fires if Ratio_i < TAPER_RATIO_THRESHOLD (0.50) for >= TAPER_SUSTAIN_WEEKS
consecutive weeks at the END of that truck's history.

Rationale for 1-week signal window: the A-audit taper facts (VIN1 ~97.3% drop,
VIN5 ~88.7% drop) are measured on individual weeks, not 4-week averages. A 4-week
rolling mean dilutes a single bad week (e.g. VIN5 week 31: 2789 rows vs ~40k normal
gives per-week ratio 0.23 but 4-week average ratio 0.59, above threshold). Using a
1-week signal window preserves the per-week drop sensitivity while the 12-week
baseline provides a stable reference.

Additional reported metric: trailing_4wk_mean_ratio (4-week mean signal / 12-week
baseline) is included in the output as a monitoring indicator even though the alarm
uses the 1-week ratio.

alarm_onset_date: calendar date of first week in the sustained alarm run.

SILENCE
-------
silence_days = calendar days between the last weekly row date and 2026-06-12 (TODAY).

VSI / SMA NULL-RATE DRIFT
--------------------------
null_rate per week = 1 - (obs_rows / n_rows) where obs_rows is the count of non-
sentinel observed rows.  VSI uses vsi_obs_rows; SMA uses sma_obs_rows.
Trailing-4-week mean null rate vs trailing-12-week baseline null rate (same 4 vs 12
week rolling pair used in production-style monitoring).
Alarm if delta >= NULL_DRIFT_ALARM_PP (15 percentage points).

OUTPUT
------
monitors/out/telemetry_health.csv -- one row per truck with:
  vin_label, failed, n_weeks,
  taper_ratio_final (single-week ratio at last week),
  trailing_4wk_mean_ratio (4-week mean ratio at last window),
  taper_alarm (bool), taper_alarm_onset (YYYY-MM-DD or blank),
  silence_days,
  vsi_null_drift_pp (percentage-point change), vsi_null_alarm (bool),
  sma_null_drift_pp, sma_null_alarm.

GATES (logged to stdout)
-------------------------
VIN1_F_SM  and VIN5_F_SM  must show taper_alarm = True.
VIN4_F_SM, VIN8_F_SM, VIN9_F_SM must show taper_alarm = False.
"""

from __future__ import annotations

import glob
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# -- Paths -------------------------------------------------------------------
ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
CACHE_DIR = ROOT / "cache" / "weekly"
OUT_DIR = ROOT / "V2_program" / "v2_system" / "monitors" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# -- Thresholds --------------------------------------------------------------
TAPER_RATIO_THRESHOLD: float = 0.50   # single-week ratio < 0.5 triggers alarm
TAPER_SUSTAIN_WEEKS: int = 2           # must be sustained >= 2 consecutive weeks at tail
BASELINE_WEEKS: int = 12               # rolling baseline length (weeks)
SIGNAL_WEEKS: int = 4                  # for 4-week mean ratio (monitoring metric only)
NULL_DRIFT_ALARM_PP: float = 15.0      # +15 pp null-rate drift alarm

TODAY = pd.Timestamp("2026-06-12")


# -- Taper alarm helper -------------------------------------------------------

def _compute_taper_alarm(
    df_vin: pd.DataFrame,
) -> tuple[float, float, bool, pd.Timestamp | None]:
    """
    Compute per-week taper ratios and check for sustained alarm at tail.

    Alarm uses SINGLE-WEEK signal vs 12-week baseline (see module docstring).
    Also computes the 4-week-mean ratio at the last available window (for reporting).

    Returns
    -------
    taper_ratio_final     : single-week ratio at last week (NaN if insufficient)
    trailing_4wk_ratio    : 4-week mean / 12-week baseline at last window (NaN if insufficient)
    alarm                 : True if single-week ratio < threshold for >= TAPER_SUSTAIN_WEEKS
                            consecutive weeks at the tail
    alarm_onset           : Timestamp of first week in the sustained alarm run, or None
    """
    df = df_vin[df_vin["active_days"] > 0].copy().reset_index(drop=True)
    n = len(df)
    min_history = BASELINE_WEEKS + 1   # need 12 baseline + 1 signal week

    if n < min_history:
        return float("nan"), float("nan"), False, None

    df["rpd"] = df["n_rows"] / df["active_days"]

    # Per-week ratio: i is 1-based (week index); for week at position i (0-indexed),
    # baseline = rpd[i-12 : i] (12 prior weeks), signal = rpd[i].
    ratios_1wk: list[tuple[int, float]] = []   # (row_index, ratio)
    for i in range(BASELINE_WEEKS, n):
        base = df["rpd"].iloc[i - BASELINE_WEEKS : i].mean()
        if base > 0:
            ratios_1wk.append((i, df["rpd"].iloc[i] / base))

    if not ratios_1wk:
        return float("nan"), float("nan"), False, None

    taper_ratio_final = ratios_1wk[-1][1]

    # 4-week mean ratio at last window (for reporting)
    trailing_4wk_ratio = float("nan")
    min_4wk = BASELINE_WEEKS + SIGNAL_WEEKS
    if n >= min_4wk:
        i = n
        sig4 = df["rpd"].iloc[i - SIGNAL_WEEKS : i].mean()
        base4 = df["rpd"].iloc[i - SIGNAL_WEEKS - BASELINE_WEEKS : i - SIGNAL_WEEKS].mean()
        if base4 > 0:
            trailing_4wk_ratio = sig4 / base4

    # Sustained run at tail
    below_flags = [r < TAPER_RATIO_THRESHOLD for _, r in ratios_1wk]
    run_len = 0
    for flag in reversed(below_flags):
        if flag:
            run_len += 1
        else:
            break

    if run_len >= TAPER_SUSTAIN_WEEKS:
        onset_pos = len(ratios_1wk) - run_len
        onset_row_idx = ratios_1wk[onset_pos][0]
        alarm_onset = df["week"].iloc[onset_row_idx]
        return taper_ratio_final, trailing_4wk_ratio, True, alarm_onset

    return taper_ratio_final, trailing_4wk_ratio, False, None


# -- Null-rate drift helper ---------------------------------------------------

def _compute_null_drift(
    df_vin: pd.DataFrame, obs_col: str
) -> tuple[float, bool]:
    """
    Trailing-4-week mean null rate vs trailing-12-week baseline null rate.
    null_rate_week = 1 - (obs_col / n_rows), clipped to [0, 1].

    Returns (delta_pp, alarm) where delta_pp is in percentage points.
    """
    df = df_vin[df_vin["n_rows"] > 0].copy().reset_index(drop=True)
    n = len(df)

    if obs_col not in df.columns:
        return float("nan"), False

    df["null_rate"] = 1.0 - (df[obs_col] / df["n_rows"]).clip(0.0, 1.0)

    min_hist = BASELINE_WEEKS + SIGNAL_WEEKS
    if n < min_hist:
        return float("nan"), False

    i = n
    sig = df["null_rate"].iloc[i - SIGNAL_WEEKS : i].mean()
    base = df["null_rate"].iloc[i - SIGNAL_WEEKS - BASELINE_WEEKS : i - SIGNAL_WEEKS].mean()
    delta_pp = (sig - base) * 100.0
    alarm = delta_pp >= NULL_DRIFT_ALARM_PP
    return delta_pp, alarm


# -- Main --------------------------------------------------------------------

def main() -> pd.DataFrame:
    parquet_files = sorted(
        glob.glob(str(CACHE_DIR / "V1_SM_weekly_*.parquet"))
    )
    if not parquet_files:
        raise FileNotFoundError(f"No weekly cache parquets found in {CACHE_DIR}")

    records: list[dict] = []

    for fpath in parquet_files:
        vin = Path(fpath).stem.replace("V1_SM_weekly_", "")
        df_vin = pd.read_parquet(fpath)
        df_vin = df_vin.sort_values("week").reset_index(drop=True)

        failed = bool(df_vin["failed"].iloc[0])
        n_weeks = len(df_vin)

        # Taper (1-week signal / 12-week baseline)
        taper_ratio_final, trailing_4wk_ratio, taper_alarm, taper_onset = (
            _compute_taper_alarm(df_vin)
        )

        # Silence
        last_week = df_vin["week"].max()
        silence_days = max(0, (TODAY - last_week).days)

        # VSI null drift
        vsi_null_drift_pp, vsi_null_alarm = _compute_null_drift(
            df_vin, "vsi_obs_rows"
        )

        # SMA null drift
        sma_null_drift_pp, sma_null_alarm = _compute_null_drift(
            df_vin, "sma_obs_rows"
        )

        records.append(
            {
                "vin_label": vin,
                "failed": failed,
                "n_weeks": n_weeks,
                "taper_ratio_final": round(taper_ratio_final, 4)
                if not np.isnan(taper_ratio_final)
                else float("nan"),
                "trailing_4wk_mean_ratio": round(trailing_4wk_ratio, 4)
                if not np.isnan(trailing_4wk_ratio)
                else float("nan"),
                "taper_alarm": taper_alarm,
                "taper_alarm_onset": taper_onset.strftime("%Y-%m-%d")
                if taper_onset is not None
                else None,
                "silence_days": silence_days,
                "vsi_null_drift_pp": round(vsi_null_drift_pp, 2)
                if not np.isnan(vsi_null_drift_pp)
                else float("nan"),
                "vsi_null_alarm": vsi_null_alarm,
                "sma_null_drift_pp": round(sma_null_drift_pp, 2)
                if not np.isnan(sma_null_drift_pp)
                else float("nan"),
                "sma_null_alarm": sma_null_alarm,
            }
        )

    result = (
        pd.DataFrame(records)
        .sort_values("vin_label")
        .reset_index(drop=True)
    )

    out_path = OUT_DIR / "telemetry_health.csv"
    result.to_csv(out_path, index=False)
    print(f"[telemetry_health] Written: {out_path}")
    return result


# -- Gate report -------------------------------------------------------------

def report_gates(df: pd.DataFrame) -> dict:
    """
    Check five-VIN taper gate (A-audit facts).
    Returns dict of gate results for consumption by run_monitors.py.
    """
    TAPER_EXPECTED_TRUE = ["VIN1_F_SM", "VIN5_F_SM"]
    TAPER_EXPECTED_FALSE = ["VIN4_F_SM", "VIN8_F_SM", "VIN9_F_SM"]

    idx = df.set_index("vin_label")
    gate_pass = True
    rows = []

    for vin in TAPER_EXPECTED_TRUE + TAPER_EXPECTED_FALSE:
        if vin not in idx.index:
            print(f"  [WARN] {vin} not found in telemetry_health output")
            continue
        row = idx.loc[vin]
        expected = vin in TAPER_EXPECTED_TRUE
        actual = bool(row["taper_alarm"])
        ratio = row["taper_ratio_final"]
        ok = actual == expected
        if not ok:
            gate_pass = False
        status = "PASS" if ok else "FAIL"
        rows.append(
            {
                "vin": vin,
                "expected_alarm": expected,
                "actual_alarm": actual,
                "taper_ratio_final": float(ratio),
                "status": status,
            }
        )
        print(
            f"  [taper_gate] {vin:16s}  expected={expected}  "
            f"actual={actual}  ratio={ratio:.4f}  -> {status}"
        )

    return {"pass": gate_pass, "detail": rows}


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    print("=" * 60)
    print("telemetry_health.py  (B7)")
    print("=" * 60)

    df_out = main()

    print("\n--- TAPER ALARM GATES ---")
    gate_result = report_gates(df_out)

    print("\n--- FULL RESULT ---")
    cols = [
        "vin_label", "failed", "n_weeks",
        "taper_ratio_final", "trailing_4wk_mean_ratio",
        "taper_alarm", "taper_alarm_onset",
        "silence_days", "vsi_null_alarm", "sma_null_alarm",
    ]
    print(df_out[cols].to_string(index=False))

    status = "PASS" if gate_result["pass"] else "FAIL"
    print(f"\n[telemetry_health] Gate result: {status}")
