# F1_build_truck_week.py -- Agent F (Survival Analysis), V1.1 Phase 2
# Builds the discrete-time truck-week table with CAUSAL, 1-week-LAGGED covariates.
#
# Anti-leakage protocol:
#   - Time axis: age_week = integer weeks since first telemetry (t_start).
#   - Event = 1 at the last observed week of failed VINs (t_end-anchored).
#   - Covariate at week t uses ONLY weeks <= t-1 (strictly lagged: the event
#     week's own telemetry never feeds its covariates).
#   - No whole-life stats, no observation length, no t_start/epoch, no
#     vsi_dominant_freq.
#   - SMA-dead cohort (sma_null_pct > 0.99): crank covariate set to NaN
#     (masked); imputed with TRAINING-FOLD mean inside each LOVO fold.
#
# Covariates (3, per Agent C's EPV budget of 14 events):
#   1. vsi_std_ratio  : mean(vsi_drive_std, weeks t-4..t-1) / expanding mean of
#                       vsi_drive_std over weeks 0..t-5 (past baseline, >=4 wk).
#                       Charging-ripple instability vs the truck's own past.
#   2. crank_fail_rate: rolling 4-week failed-crank fraction (success==False,
#                       artifact excluded; success==None dropped), weeks t-4..t-1,
#                       requires >=5 cranks in window else NaN. Masked for
#                       SMA-dead trucks.
#   3. rest_delta     : mean(vsi_rest_p05, weeks t-4..t-1) minus the truck's
#                       early-life baseline (median of first 8 observed weeks,
#                       only weeks <= t-5 used). Negative = rest voltage sag.
import glob
import os

import numpy as np
import pandas as pd

ROOT = r"D:\Daimler-starter_motor_alternator_battery"
WEEKLY = os.path.join(ROOT, "STARTER MOTOR", "cache", "weekly")
EVENTS = os.path.join(ROOT, "STARTER MOTOR", "cache", "events",
                      "V1_SM_crank_events.parquet")
DQ = os.path.join(ROOT, "STARTER MOTOR", "results", "V1_SM_data_quality.csv")
OUT = os.path.join(ROOT, "STARTER MOTOR", "V1.1", "discovery", "out")
os.makedirs(OUT, exist_ok=True)

dq = pd.read_csv(DQ)
SMA_DEAD = set(dq.loc[dq.sma_null_pct > 0.99, "vin_label"])
print(f"SMA-dead cohort ({len(SMA_DEAD)}): {sorted(SMA_DEAD)}")

# ---- weekly crank aggregation (causal: keyed by ts_start week) -------------
ev = pd.read_parquet(EVENTS)
ev = ev[~ev.artifact & ev.success.notna()].copy()
ev["week"] = (ev.ts_start - pd.to_timedelta(ev.ts_start.dt.dayofweek, unit="D")
              ).dt.normalize()
wk_crank = (ev.groupby(["vin_label", "week"])
              .agg(n_cranks=("success", "size"),
                   n_failed_cranks=("success", lambda s: int((s == False).sum())))
              .reset_index())

# ---- per-VIN truck-week assembly --------------------------------------------
rows = []
for f in sorted(glob.glob(os.path.join(WEEKLY, "V1_SM_weekly_*.parquet"))):
    d = pd.read_parquet(f).sort_values("week").reset_index(drop=True)
    vin = d.vin_label.iloc[0]
    failed = bool(d.failed.iloc[0])
    d = d.merge(wk_crank[wk_crank.vin_label == vin].drop(columns="vin_label"),
                on="week", how="left")
    d[["n_cranks", "n_failed_cranks"]] = d[["n_cranks", "n_failed_cranks"]].fillna(0)

    # integer age in weeks since first telemetry week (calendar-true, keeps gaps)
    d["age_week"] = ((d.week - d.week.iloc[0]).dt.days // 7).astype(int)

    s = d.vsi_drive_std.to_numpy(dtype=float)
    r = d.vsi_rest_p05.to_numpy(dtype=float)
    cf = d.n_failed_cranks.to_numpy(dtype=float)
    ct = d.n_cranks.to_numpy(dtype=float)
    n = len(d)
    vsi_std_ratio = np.full(n, np.nan)
    crank_fail_rate = np.full(n, np.nan)
    rest_delta = np.full(n, np.nan)
    for i in range(n):
        win = slice(max(0, i - 4), i)          # observed weeks t-4..t-1
        past = slice(0, max(0, i - 4))         # observed weeks 0..t-5
        # 1. vsi_std_ratio
        w = s[win]; p = s[past]
        w = w[np.isfinite(w)]; p = p[np.isfinite(p)]
        if len(w) >= 2 and len(p) >= 4 and np.mean(p) > 1e-6:
            vsi_std_ratio[i] = np.mean(w) / np.mean(p)
        # 2. crank_fail_rate (masked later for SMA-dead)
        if ct[win].sum() >= 5:
            crank_fail_rate[i] = cf[win].sum() / ct[win].sum()
        # 3. rest_delta vs early-life baseline (first 8 obs weeks, causal part)
        base_idx = min(i - 4, 8)
        rw = r[win]; rb = r[0:max(base_idx, 0)]
        rw = rw[np.isfinite(rw)]; rb = rb[np.isfinite(rb)]
        if len(rw) >= 2 and len(rb) >= 4:
            rest_delta[i] = np.mean(rw) - np.median(rb)
    if vin in SMA_DEAD:
        crank_fail_rate[:] = np.nan  # masked: fallback-path events untrusted

    out = pd.DataFrame({
        "vin_label": vin, "failed": failed, "week": d.week,
        "age_week": d.age_week,
        "obs_idx": np.arange(n),
        "vsi_std_ratio": np.clip(vsi_std_ratio, 0.2, 5.0),
        "crank_fail_rate": crank_fail_rate,
        "rest_delta": np.clip(rest_delta, -6, 6),
        "sma_dead": vin in SMA_DEAD,
        "n_cranks_w": ct, "n_failed_cranks_w": cf,
    })
    out["event"] = 0
    if failed:
        out.loc[out.index[-1], "event"] = 1   # t_end-anchored event week
    # weeks-to-event (failed only; from age axis, calendar-true)
    if failed:
        out["weeks_to_fail"] = out.age_week.iloc[-1] - out.age_week
    else:
        out["weeks_to_fail"] = np.nan
    rows.append(out)

tw = pd.concat(rows, ignore_index=True)
tw.to_parquet(os.path.join(OUT, "F_truck_week.parquet"), index=False)

print(f"\nTruck-week table: {tw.shape[0]} rows x {tw.shape[1]} cols, "
      f"{tw.vin_label.nunique()} trucks, {int(tw.event.sum())} events")
print(f"Events: {sorted(tw.loc[tw.event == 1, 'vin_label'])}")
print("\nCovariate availability (non-null %):")
for c in ["vsi_std_ratio", "crank_fail_rate", "rest_delta"]:
    print(f"  {c:18s} {tw[c].notna().mean():.1%}  "
          f"(non-masked trucks: {tw.loc[~tw.sma_dead, c].notna().mean():.1%})")
print("\nCovariate summary (last-26-weeks of failed vs all NF weeks):")
fl = tw[(tw.failed) & (tw.weeks_to_fail <= 26)]
nf = tw[~tw.failed]
for c in ["vsi_std_ratio", "crank_fail_rate", "rest_delta"]:
    print(f"  {c:18s} failed<=26w: {fl[c].mean():+.4f}  NF: {nf[c].mean():+.4f}")
print("\nEvent-time summary (age weeks at t_end):")
et = tw.groupby("vin_label").agg(failed=("failed", "first"),
                                 T=("age_week", "max"))
print(et.groupby("failed").T.describe().round(1).to_string())
