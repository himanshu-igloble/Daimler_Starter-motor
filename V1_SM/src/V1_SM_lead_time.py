"""
V1_SM_lead_time.py  —  Phase 5: Honest Lead-Time Analysis
BharatBenz Starter Motor predictive maintenance pipeline.

Produces: STARTER MOTOR/results/V1_SM_lead_time_verdicts.csv
  - Long format: one row per VIN x signal x window (34 x 8 x 3 = 816 rows)
  - Per-row: Mann-Whitney p (final window vs baseline), direction, Theil-Sen
    slope over the full weekly series, window verdict
  - Summary columns repeated per row: signal_verdict, vin_verdict,
    lead_vs_t_end, lead_vs_jcopen, best_signal, gap flags

Question (per failed VIN, ALT-fleet lesson applied): does any Branch-A/B
signal change measurably in the final 30/60/90 days before t_end, relative
to that VIN's OWN baseline?  The 20 NF VINs run the IDENTICAL protocol as
the false-positive control — their "trending" rate calibrates the test
battery.  NO multiple-comparison correction is applied (mirrors the ALT
protocol); the NF control rate IS the honest calibration.

Anchoring: all windows are relative to t_end = last week in that VIN's
weekly cache.  NEVER JCOPENDATE — for the 5 GAP_VINS telemetry ends
gap_days before JCOPENDATE, so lead_vs_jcopen = lead_vs_t_end + gap_days.

Verdict rules (per signal):
  trending          p<0.05 with the SAME direction in >=2 of 3 windows
  late-spike        p<0.05 only in the 30d window
  flat              no window significant (incl. isolated 60/90d-only hits
                    and mixed-direction pairs — no consistent, late signal)
  insufficient-data <2 windows evaluable (>=3 weekly values needed in BOTH
                    final window and baseline per window)

Per-VIN: trending if >=1 signal trending; else late-spike if >=1 signal
late-spike; else flat; insufficient-data only if ALL signals insufficient.

lead_vs_t_end: max significant (consistent-direction) window W over the
VIN's trending signals; null when no trending signal (a 30d late-spike is
NOT counted as lead — it bounds lead at <30d and is reported as verdict).
"""

from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import warnings
warnings.filterwarnings("ignore")

# ── Config import (directory has a space) ────────────────────────────────────
_spec = spec_from_file_location(
    "v1_sm_config",
    Path(__file__).resolve().parent / "V1_SM_config.py"
)
cfg = module_from_spec(_spec)
_spec.loader.exec_module(cfg)

import numpy as np
import pandas as pd
from scipy import stats

# ── Protocol constants ───────────────────────────────────────────────────────
ALPHA = 0.05                 # per-window Mann-Whitney significance level
WINDOWS = (30, 60, 90)       # final-window lengths, days before t_end
MIN_WEEKS = 3                # min non-null weekly values in final AND baseline

BRANCH_B_SIGNALS = ["vsi_drive_std", "vsi_drive_range",
                    "vsi_drive_mean", "vsi_rest_median"]
BRANCH_A_SIGNALS = ["failed_crank_rate", "dip_depth_mean",
                    "dur_s_mean", "retry_rate"]
SIGNALS = BRANCH_B_SIGNALS + BRANCH_A_SIGNALS


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def monday_week(ts: pd.Series) -> pd.Series:
    """Floor timestamps to Monday week-start (matches weekly cache 'week')."""
    d = ts.dt.normalize()
    return d - pd.to_timedelta(d.dt.weekday, unit="D")


def window_test(weeks: pd.Series, values: pd.Series,
                t_end: pd.Timestamp, w_days: int) -> dict:
    """Mann-Whitney final-window vs baseline for one VIN x signal x window."""
    cutoff = t_end - pd.Timedelta(days=w_days)
    in_final = weeks >= cutoff
    fin, base = values[in_final].values, values[~in_final].values
    rec = {"n_final": int(len(fin)), "n_baseline": int(len(base)),
           "mw_p": np.nan, "direction": "", "window_verdict": "insufficient-data"}
    if len(fin) < MIN_WEEKS or len(base) < MIN_WEEKS:
        return rec
    try:
        _, p = stats.mannwhitneyu(fin, base, alternative="two-sided")
        p = float(p)
    except ValueError:                      # all values identical
        p = np.nan
    delta = float(np.median(fin) - np.median(base))
    direction = "up" if delta > 0 else ("down" if delta < 0 else "none")
    sig = np.isfinite(p) and p < ALPHA
    rec.update({
        "mw_p": p,
        "direction": direction,
        "window_verdict": (f"significant-{direction}" if sig
                           else "not-significant"),
    })
    return rec


def signal_verdict(win_recs: dict) -> str:
    """Combine the 3 window records for one signal into a verdict."""
    evaluable = [w for w in WINDOWS
                 if win_recs[w]["window_verdict"] != "insufficient-data"]
    if len(evaluable) < 2:
        return "insufficient-data"
    sig_dirs = {w: win_recs[w]["direction"] for w in evaluable
                if win_recs[w]["window_verdict"].startswith("significant")}
    if not sig_dirs:
        return "flat"
    for d in ("up", "down"):
        if sum(1 for v in sig_dirs.values() if v == d) >= 2:
            return "trending"
    if set(sig_dirs.keys()) == {30}:
        return "late-spike"
    return "flat"   # isolated 60/90d hit or mixed directions: not consistent


def theil_sen(weeks: pd.Series, values: pd.Series) -> float:
    """Theil-Sen slope (units/day) over the full weekly series."""
    if len(values) < 3:
        return np.nan
    x = (weeks - weeks.min()).dt.total_seconds().values / 86400.0
    try:
        slope, _, _, _ = stats.theilslopes(values.values, x)
        return float(slope)
    except Exception:
        return np.nan


# ─────────────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────────────
print("Loading weekly cache + crank events...")
weekly_files = sorted(cfg.CACHE_WEEKLY.glob("V1_SM_weekly_*.parquet"))
weekly = pd.concat([pd.read_parquet(f) for f in weekly_files], ignore_index=True)
events = pd.read_parquet(cfg.CACHE_EVENTS / "V1_SM_crank_events.parquet")

assert weekly["vin_label"].nunique() == cfg.N_VINS, "WEEKLY VIN COUNT MISMATCH"
assert events["vin_label"].nunique() == cfg.N_VINS, "EVENT VIN COUNT MISMATCH"

weekly["vsi_drive_range"] = weekly["vsi_drive_p95"] - weekly["vsi_drive_p05"]

# Branch A: weekly aggregation of NON-ARTIFACT events only.  Weeks without
# events are simply absent (sparsity preserved), not imputed as zero.
ev = events[~events["artifact"]].copy()
ev["week"] = monday_week(ev["ts_start"])
ev["success_num"] = ev["success"].map({True: 1.0, False: 0.0})  # None -> NaN

grp = ev.groupby(["vin_label", "week"])
branch_a = pd.DataFrame({
    "failed_crank_rate": 1.0 - grp["success_num"].mean(),   # NaN-success dropped
    "dip_depth_mean": grp["dip_depth"].mean(),
    "dur_s_mean": grp["dur_s"].mean(),
    "retry_rate": grp["retry_within_120s"].mean(),
}).reset_index()

# Per-VIN t_end: last week in the weekly cache (windows anchor here — NEVER
# JCOPENDATE; GAP_VINS telemetry ends gap_days before JCOPENDATE).
t_end_map = weekly.groupby("vin_label")["week"].max().to_dict()
failed_map = weekly.groupby("vin_label")["failed"].first().to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Per-VIN x signal x window test battery
# ─────────────────────────────────────────────────────────────────────────────
print(f"Running test battery: {cfg.N_VINS} VINs x {len(SIGNALS)} signals x "
      f"{len(WINDOWS)} windows (alpha={ALPHA}, no correction -- NF control "
      f"calibrates)...")

rows = []
vin_summaries = {}

for vin in sorted(t_end_map):
    t_end = t_end_map[vin]
    is_failed = bool(failed_map[vin])
    gap_days = cfg.GAP_VINS.get(vin, 0)

    wk_vin = weekly[weekly["vin_label"] == vin].sort_values("week")
    ba_vin = branch_a[branch_a["vin_label"] == vin].sort_values("week")

    sig_results = {}
    for signal in SIGNALS:
        src = wk_vin if signal in BRANCH_B_SIGNALS else ba_vin
        series = src[["week", signal]].dropna()
        weeks, values = series["week"], series[signal]

        slope = theil_sen(weeks, values)
        win_recs = {w: window_test(weeks, values, t_end, w) for w in WINDOWS}
        sv = signal_verdict(win_recs)
        sig_results[signal] = {"verdict": sv, "windows": win_recs,
                               "slope": slope}

    # ── Per-VIN verdict ──────────────────────────────────────────────────
    verdicts = {s: r["verdict"] for s, r in sig_results.items()}
    if all(v == "insufficient-data" for v in verdicts.values()):
        vin_verdict = "insufficient-data"
    elif any(v == "trending" for v in verdicts.values()):
        vin_verdict = "trending"
    elif any(v == "late-spike" for v in verdicts.values()):
        vin_verdict = "late-spike"
    else:
        vin_verdict = "flat"

    # lead_vs_t_end: longest significant consistent-direction window across
    # trending signals.  best_signal: the signal that supplies it (ties ->
    # smaller min p across its significant windows).
    lead = np.nan
    best_signal = ""
    if vin_verdict == "trending":
        cands = []
        for s, r in sig_results.items():
            if r["verdict"] != "trending":
                continue
            dirs = [r["windows"][w]["direction"] for w in WINDOWS
                    if r["windows"][w]["window_verdict"].startswith("significant")]
            major = max(set(dirs), key=dirs.count)
            sig_ws = [w for w in WINDOWS
                      if r["windows"][w]["window_verdict"] == f"significant-{major}"]
            min_p = min(r["windows"][w]["mw_p"] for w in sig_ws)
            cands.append((max(sig_ws), -min_p, s))
        cands.sort(reverse=True)
        lead, _, best_signal = cands[0][0], cands[0][1], cands[0][2]
    elif vin_verdict == "late-spike":
        spikes = [(r["windows"][30]["mw_p"], s) for s, r in sig_results.items()
                  if r["verdict"] == "late-spike"]
        best_signal = min(spikes)[1]

    lead_vs_jcopen = (lead + gap_days) if (is_failed and np.isfinite(lead)) \
        else np.nan

    vin_summaries[vin] = {
        "failed": is_failed, "vin_verdict": vin_verdict,
        "best_signal": best_signal, "lead_vs_t_end": lead,
        "lead_vs_jcopen": lead_vs_jcopen,
        "is_gap_vin": vin in cfg.GAP_VINS, "gap_days": gap_days,
    }

    for signal in SIGNALS:
        r = sig_results[signal]
        for w in WINDOWS:
            wr = r["windows"][w]
            rows.append({
                "vin_label": vin,
                "failed": is_failed,
                "is_gap_vin": vin in cfg.GAP_VINS,
                "gap_days": gap_days,
                "branch": "B" if signal in BRANCH_B_SIGNALS else "A",
                "signal": signal,
                "window_days": w,
                "n_final": wr["n_final"],
                "n_baseline": wr["n_baseline"],
                "mw_p": wr["mw_p"],
                "direction": wr["direction"],
                "theil_sen_slope": r["slope"],
                "window_verdict": wr["window_verdict"],
                "signal_verdict": r["verdict"],
                "vin_verdict": vin_summaries[vin]["vin_verdict"],
                "best_signal": vin_summaries[vin]["best_signal"],
                "lead_vs_t_end": vin_summaries[vin]["lead_vs_t_end"],
                "lead_vs_jcopen": (vin_summaries[vin]["lead_vs_jcopen"]
                                   if is_failed else np.nan),
            })

out = pd.DataFrame(rows)
assert len(out) == cfg.N_VINS * len(SIGNALS) * len(WINDOWS), "ROW COUNT MISMATCH"
assert out["vin_label"].nunique() == cfg.N_VINS, "OUTPUT VIN COUNT MISMATCH"
assert all(v in vin_summaries for v in t_end_map), "MISSING VIN VERDICT"

out_path = cfg.RESULTS / "V1_SM_lead_time_verdicts.csv"
out_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(out_path, index=False)


# ─────────────────────────────────────────────────────────────────────────────
# Console report
# ─────────────────────────────────────────────────────────────────────────────
failed_vins = sorted([v for v, s in vin_summaries.items() if s["failed"]],
                     key=lambda v: int(v.replace("VIN", "").split("_")[0]))
nf_vins = sorted([v for v, s in vin_summaries.items() if not s["failed"]],
                 key=lambda v: int(v.replace("VIN", "").split("_")[0]))

print()
print("=" * 88)
print(f"FAILED-VIN LEAD-TIME VERDICTS ({len(failed_vins)} VINs) -- "
      f"anchored on t_end (last telemetry week), NEVER JCOPENDATE")
print("=" * 88)
print(f"{'VIN':<12} {'verdict':<18} {'best signal':<20} "
      f"{'lead_t_end':>10} {'lead_jcopen':>11} {'gap':>5}")
print("-" * 88)
for vin in failed_vins:
    s = vin_summaries[vin]
    lead = f"{int(s['lead_vs_t_end'])}d" if np.isfinite(s["lead_vs_t_end"]) else "-"
    leadj = f"{int(s['lead_vs_jcopen'])}d" if np.isfinite(s["lead_vs_jcopen"]) else "-"
    gap = f"+{s['gap_days']}d" if s["is_gap_vin"] else ""
    print(f"{vin:<12} {s['vin_verdict']:<18} {s['best_signal']:<20} "
          f"{lead:>10} {leadj:>11} {gap:>5}")

n_trend_f = sum(1 for v in failed_vins
                if vin_summaries[v]["vin_verdict"] == "trending")
n_spike_f = sum(1 for v in failed_vins
                if vin_summaries[v]["vin_verdict"] == "late-spike")
n_flat_f = sum(1 for v in failed_vins
               if vin_summaries[v]["vin_verdict"] == "flat")
n_insuf_f = sum(1 for v in failed_vins
                if vin_summaries[v]["vin_verdict"] == "insufficient-data")

n_trend_nf = sum(1 for v in nf_vins
                 if vin_summaries[v]["vin_verdict"] == "trending")
n_spike_nf = sum(1 for v in nf_vins
                 if vin_summaries[v]["vin_verdict"] == "late-spike")

print()
print("=" * 88)
print("NF CONTROL (identical protocol, final windows before each NF VIN's own t_end)")
print("=" * 88)
for vin in nf_vins:
    s = vin_summaries[vin]
    print(f"  {vin:<14} {s['vin_verdict']:<18} {s['best_signal']}")
print()
print(f"  NF 'trending' rate: {n_trend_nf}/{len(nf_vins)} "
      f"({100*n_trend_nf/len(nf_vins):.0f}%)  <- FALSE-POSITIVE RATE of this "
      f"test battery")
print(f"  NF 'late-spike' rate: {n_spike_nf}/{len(nf_vins)} "
      f"({100*n_spike_nf/len(nf_vins):.0f}%)")
print()
print("=" * 88)
print("HONEST BOTTOM LINE")
print("=" * 88)
print(f"  Failed:  {n_trend_f}/{len(failed_vins)} trending, "
      f"{n_spike_f} late-spike, {n_flat_f} flat, {n_insuf_f} insufficient-data")
print(f"  Control: {n_trend_nf}/{len(nf_vins)} NF VINs 'trend' under the same "
      f"battery -- any failed-VIN lead claim must be read against this rate.")
print(f"  No multiple-comparison correction applied "
      f"({len(SIGNALS)} signals x {len(WINDOWS)} windows x {cfg.N_VINS} VINs); "
      f"the NF control rate IS the calibration (mirrors ALT protocol).")
print()
print(f"Saved: {out_path}  ({out.shape[0]} rows x {out.shape[1]} cols)")
