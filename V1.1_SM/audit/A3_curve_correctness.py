"""
A3_curve_correctness.py — audit steps 2 (gap-mask numeric + crop prep) and 3
(curve data correctness).

- Probe degradation inputs at 3 dates for 6 sample VINs: window_features fed
  by the DAILY CACHE vs fed by the independent RAW recompute (A1).
- Forecast endpoint vs JCOPENDATE for all 14 failed VINs.
- NF anchor: 779 d vs conditional Weibull for all 20 NF VINs.
- Zone-band transition dates == first crossing of 0.15/0.35/0.55.
- gap_mask numeric check: NaN break present for every mid-history gap.
- Writes zoomed crops of the 6 largest mid-history gaps to audit/out/crops/.
"""
from pathlib import Path
import importlib.util
import datetime as dt
import numpy as np
import pandas as pd
import polars as pl
from PIL import Image

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery")
SM = ROOT / "STARTER MOTOR"
AUDIT = SM / "V1.1" / "audit"
DAILY_DIR = SM / "V1.1" / "cache" / "daily"
GRAPH_DIR = SM / "V1.1" / "graphs"
CROP_DIR = AUDIT / "out" / "crops"
CROP_DIR.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location(
    "graphs_mod", SM / "V1.1" / "src" / "V1_1_SM_daily_risk_graphs.py")
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)

raw_daily_all = pl.read_parquet(str(AUDIT / "A1_raw_daily.parquet")).to_pandas()
raw_daily_all["date"] = pd.to_datetime(raw_daily_all["date"])
inv = pl.read_csv(str(SM / "V1.1" / "results" / "V1_1_SM_data_gap_inventory.csv")).to_dicts()

lines = []
def log(s=""):
    print(s)
    lines.append(s)

def load_cache(vin):
    d = pd.read_parquet(DAILY_DIR / f"V1_1_SM_daily_{vin}.parquet")
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values("date").reset_index(drop=True)

def max_rul_for(vin, daily):
    if "_F_" in vin:
        m = gm.META[vin]
        return float((m["jcopendate"] - m["saledate"]).days), False
    span = int((daily["date"].iloc[-1] - daily["date"].iloc[0]).days)
    return gm.nf_max_rul(span)

# ===========================================================================
# CHECK 3a — degradation inputs at 3 probe dates, cache vs raw (6 VINs)
# ===========================================================================
log("=" * 78)
log("CHECK 3a — window_features cache vs independent raw recompute (3 probes/VIN)")
log("=" * 78)
SAMPLE = ["VIN1_F_SM", "VIN6_F_SM", "VIN8_F_SM", "VIN1_NF_SM", "VIN12_NF_SM", "VIN20_NF_SM"]
KEYS = ["vsi_mean", "vsi_std", "vsi_range", "vsi_deviation", "uv_share", "failed_crank_rate"]
n_ok = n_tot = 0
TRAJ = {}
for vin in SAMPLE:
    daily = load_cache(vin)
    raw = raw_daily_all[raw_daily_all["vin_label"] == vin].sort_values("date").reset_index(drop=True)
    mr, _ = max_rul_for(vin, daily)
    traj, sma_dead = gm.compute_daily_trajectory(vin, daily, mr)
    TRAJ[vin] = (traj, sma_dead, mr, daily)

    fc = gm.FAILED_CRANKS.get(vin, pd.Series(dtype="int64"))
    fc_dates = fc.index.values if len(fc) else np.array([], dtype="datetime64[ns]")
    fc_counts = fc.values if len(fc) else np.array([], dtype="int64")
    first_date = daily["date"].iloc[0]
    base_c = gm.window_features(daily, fc_dates, fc_counts, first_date + pd.Timedelta(days=90), 90)
    base_r = gm.window_features(raw, fc_dates, fc_counts, first_date + pd.Timedelta(days=90), 90)

    n = len(daily)
    for tag, idx in [("early", int(n * 0.15)), ("mid", int(n * 0.50)), ("late", int(n * 0.90))]:
        d = daily["date"].iloc[idx]
        fc_ = gm.window_features(daily, fc_dates, fc_counts, d, 30)
        fr_ = gm.window_features(raw, fc_dates, fc_counts, d, 30)
        deg_c = gm.features_to_degradation(fc_, base_c, sma_dead)
        deg_r = gm.features_to_degradation(fr_, base_r, sma_dead)
        deg_traj = float(traj.loc[traj["date"] == d, "degradation"].iloc[0])
        maxdiff = max(abs(fc_[k] - fr_[k]) for k in KEYS)
        ok = maxdiff < 1e-9 and abs(deg_c - deg_r) < 1e-12 and abs(deg_traj - deg_c) < 1e-12
        n_ok += ok; n_tot += 1
        log(f"  {vin:<13} {tag:<5} {d:%Y-%m-%d}  deg traj/cache/raw = "
            f"{deg_traj:.6f}/{deg_c:.6f}/{deg_r:.6f}  feat maxdiff={maxdiff:.2e} "
            f"[{'PASS' if ok else 'FAIL'}]")
log(f"CHECK 3a verdict: {n_ok}/{n_tot} -> {'PASS' if n_ok == n_tot else 'FAIL'}")

# ===========================================================================
# CHECK 3b — forecast endpoint vs JCOPENDATE (all 14 failed)
# ===========================================================================
log()
log("=" * 78)
log("CHECK 3b — forecast_fail_date (first_date + max_rul) vs JCOPENDATE")
log("=" * 78)
n_exact = 0
for vin in sorted([v for v in gm.META if "_F_" in v], key=gm.vin_sort_key):
    daily = load_cache(vin)
    m = gm.META[vin]
    mr = float((m["jcopendate"] - m["saledate"]).days)
    fc_date = daily["date"].iloc[0] + pd.Timedelta(days=int(mr))
    off = (fc_date - m["jcopendate"]).days
    n_exact += (off == 0)
    log(f"  {vin:<13} saledate {m['saledate']:%Y-%m-%d}  t_start {daily['date'].iloc[0]:%Y-%m-%d}  "
        f"max_rul {mr:.0f}d  forecast {fc_date:%Y-%m-%d}  JCO {m['jcopendate']:%Y-%m-%d}  "
        f"offset {off:+d}d [{'PASS' if off == 0 else 'FAIL'}]")
log(f"CHECK 3b verdict: {n_exact}/14 exact -> {'PASS' if n_exact == 14 else 'FAIL'}")

# ===========================================================================
# CHECK 3c — NF anchor 779 d / conditional Weibull
# ===========================================================================
log()
log("=" * 78)
log("CHECK 3c — NF max_rul anchor (779 d or conditional Weibull)")
log("=" * 78)
for vin in sorted([v for v in gm.META if "_NF_" in v], key=gm.vin_sort_key):
    daily = load_cache(vin)
    span = int((daily["date"].iloc[-1] - daily["date"].iloc[0]).days)
    mr, cond = gm.nf_max_rul(span)
    # independent recomputation
    if span + 14 < 779.0:
        mr_i, cond_i = 779.0, False
    else:
        lam, rho = 133.3 * 7.0, 2.03
        mr_i = lam * ((span / lam) ** rho + np.log(2.0)) ** (1.0 / rho)
        cond_i = True
    ok = abs(mr - mr_i) < 1e-9 and cond == cond_i
    log(f"  {vin:<13} span {span:>4}d  max_rul {mr:8.1f}d  conditional={cond}  "
        f"indep {mr_i:8.1f}/{cond_i} [{'PASS' if ok else 'FAIL'}]")

# ===========================================================================
# CHECK 3d — zone transition dates == first crossing of thresholds
# ===========================================================================
log()
log("=" * 78)
log("CHECK 3d — find_zone_transitions == independent first-crossing (6 VINs)")
log("=" * 78)
for vin in SAMPLE:
    traj, sma_dead, mr, daily = TRAJ[vin]
    trans = gm.find_zone_transitions(traj)
    deg = traj["degradation"].values
    dates = traj["date"].values
    msgs = []
    all_ok = True
    for zone, th in gm.ZONE_THRESHOLDS.items():
        hits = np.nonzero(deg >= th)[0]
        indep = pd.Timestamp(dates[hits[0]]) if len(hits) else None
        got = trans.get(zone)
        ok = (indep is None and got is None) or (indep is not None and got == indep)
        all_ok &= ok
        msgs.append(f"{zone}: {got.date() if got is not None else '-'}"
                    f"{'' if ok else f' != indep {indep}'}")
    log(f"  {vin:<13} {' | '.join(msgs)} [{'PASS' if all_ok else 'FAIL'}]")

# ===========================================================================
# CHECK 2a — gap_mask numeric: NaN break at every mid-history gap
# ===========================================================================
log()
log("=" * 78)
log("CHECK 2a — gap_mask inserts NaN at every >=7d mid-history gap (all 34 VINs)")
log("=" * 78)
n_ok = n_tot = 0
for vin in sorted(gm.META, key=gm.vin_sort_key):
    daily = load_cache(vin)
    gaps = [g for g in inv if g["vin"] == vin and g["type"] == "mid_history"]
    if not gaps:
        continue
    dates = daily["date"].tolist()
    vals = list(range(len(dates)))
    m_dates, m_vals = gm.gap_mask(dates, vals)
    m_dates = pd.to_datetime(pd.Series(m_dates))
    for g in gaps:
        gs = pd.Timestamp(g["gap_start"]); ge = pd.Timestamp(g["gap_end"])
        inside = m_vals[(m_dates >= gs) & (m_dates <= ge)]
        ok = len(inside) > 0 and np.all(np.isnan(inside))
        n_ok += ok; n_tot += 1
        if not ok:
            log(f"  {vin:<13} gap {g['gap_start']}..{g['gap_end']} ({g['days']}d): "
                f"NO NaN break -> WOULD BE INTERPOLATED [FAIL]")
log(f"CHECK 2a verdict: {n_ok}/{n_tot} mid-history gaps have NaN break -> "
    f"{'PASS' if n_ok == n_tot else 'FAIL'}")

# ===========================================================================
# CHECK 2b prep — crops of the 6 largest mid-history gaps
# ===========================================================================
log()
log("=" * 78)
log("CHECK 2b — writing crops for visual verification")
log("=" * 78)
CROPS = [
    ("VIN5_F_SM",  "2024-12-04", "2025-10-26"),
    ("VIN11_F_SM", "2024-09-21", "2025-02-28"),
    ("VIN10_F_SM", "2024-09-21", "2025-01-22"),
    ("VIN17_NF_SM", "2024-07-25", "2024-12-02"),   # covers both 67d + 52d gaps
    ("VIN6_NF_SM", "2025-08-23", "2025-10-25"),
    ("VIN16_NF_SM", "2024-03-02", "2024-05-29"),   # covers 39d + 49d gaps
    ("VIN1_F_SM",  "2025-07-31", "2025-11-26"),    # user's trigger question window
]
for vin, gs, ge in CROPS:
    daily = load_cache(vin)
    mr, cond = max_rul_for(vin, daily)
    first, last = daily["date"].iloc[0], daily["date"].iloc[-1]
    forecast_fail = first + pd.Timedelta(days=int(mr))
    plot_start = first - pd.Timedelta(days=10)
    plot_end = max(last + pd.Timedelta(days=21), forecast_fail + pd.Timedelta(days=14))
    if "_F_" in vin:
        fail_dt = gm.META[vin]["jcopendate"]
        plot_end = max(plot_end, fail_dt + pd.Timedelta(days=14))
    span = (plot_end - plot_start).days
    f0 = (pd.Timestamp(gs) - plot_start).days / span
    f1 = (pd.Timestamp(ge) - plot_start).days / span
    img = Image.open(GRAPH_DIR / f"V1_1_SM_daily_risk_{vin}_dashboard.png")
    W, H = img.size
    # axes occupy roughly x in [0.05, 0.87] after tight bbox; pad generously
    ax0, ax1 = 0.05, 0.87
    x0 = int(max(0, (ax0 + f0 * (ax1 - ax0)) * W - 0.06 * W))
    x1 = int(min(W, (ax0 + f1 * (ax1 - ax0)) * W + 0.06 * W))
    img.crop((x0, 0, x1, int(H * 0.72))).save(CROP_DIR / f"crop_RUL_{vin}_{gs}.png")
    img.crop((x0, int(H * 0.66), x1, H)).save(CROP_DIR / f"crop_SPARK_{vin}_{gs}.png")
    log(f"  {vin:<13} gap {gs}..{ge} -> crops x[{x0},{x1}] of {W}px")

(AUDIT / "out" / "A3_results.txt").write_text("\n".join(lines), encoding="utf-8")
print("\nwrote", AUDIT / "out" / "A3_results.txt")
