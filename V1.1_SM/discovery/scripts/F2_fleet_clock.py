# F2_fleet_clock.py -- Agent F: fleet-clock survival baselines (KM + Weibull)
# Baseline (a): Kaplan-Meier / Weibull on age-to-failure with right-censoring.
#   - Conditional-median RUL: med(T - t | T > t), evaluated leave-one-VIN-out
#     (the held-out failed VIN is excluded from the fit that predicts it).
#   - MAE on failed VINs at actual-RUL horizons {4, 9, 13, 26} weeks and over
#     each failed VIN's full last 26 observed weeks.
# Baseline (b): marginal weekly hazard = 14 events / 2636 truck-weeks (constant).
# Sensitivity: JCOPENDATE event times for the 5 silent-gap VINs (+gap_days).
import os

import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter, WeibullFitter

ROOT = r"D:\Daimler-starter_motor_alternator_battery"
OUT = os.path.join(ROOT, "STARTER MOTOR", "V1.1", "discovery", "out")
tw = pd.read_parquet(os.path.join(OUT, "F_truck_week.parquet"))
dq = pd.read_csv(os.path.join(ROOT, "STARTER MOTOR", "results",
                              "V1_SM_data_quality.csv"))

surv = (tw.groupby("vin_label")
          .agg(failed=("failed", "first"), T=("age_week", "max"))
          .reset_index())
surv["T"] = surv["T"].clip(lower=1)
surv = surv.merge(dq[["vin_label", "gap_days"]], on="vin_label", how="left")
surv["T_jco"] = surv["T"] + np.where(surv.failed,
                                     surv.gap_days.fillna(0) / 7.0, 0.0)

# ---------- fleet-level fits (descriptive, all 34 trucks) --------------------
km = KaplanMeierFitter().fit(surv["T"], surv["failed"])
wb = WeibullFitter().fit(surv["T"], surv["failed"])
print("=== Fleet clock (age axis = weeks since first telemetry, t_end events) ===")
print(f"KM median: {km.median_survival_time_:.1f} wk "
      f"({km.median_survival_time_*7:.0f} d)")
try:
    from lifelines.utils import median_survival_times
    ci = median_survival_times(km.confidence_interval_)
    print(f"KM median 95% CI: {ci.iloc[0,0]:.0f}-{ci.iloc[0,1]:.0f} wk")
except Exception as e:
    print("KM median CI unavailable:", e)
q = lambda fitter, p: fitter.percentile(p)
print(f"Weibull: lambda={wb.lambda_:.1f}, rho={wb.rho_:.2f}; "
      f"median {wb.median_survival_time_:.1f} wk; "
      f"IQR {q(wb,0.75):.1f}-{q(wb,0.25):.1f} wk")
print(f"KM IQR (25th-75th pct of failure dist): "
      f"{km.percentile(0.75):.1f}-{km.percentile(0.25):.1f} wk")

base_rate = tw.event.sum() / len(tw)
print(f"\nMarginal weekly hazard (baseline b): {tw.event.sum()}/{len(tw)} "
      f"= {base_rate:.5f}/wk (~{base_rate*52:.3f}/yr)")

# ---------- conditional-median RUL helper ------------------------------------
def cond_median_rul(fitter_surv_fn, t, t_grid):
    """median of (T - t | T > t) from a survival function on t_grid."""
    St = float(fitter_surv_fn(t))
    if St <= 0:
        return np.nan
    target = 0.5 * St
    future = t_grid[t_grid > t]
    Sf = np.array([float(fitter_surv_fn(u)) for u in future])
    hit = future[Sf <= target]
    return (hit[0] - t) if len(hit) else np.nan  # nan = beyond observed support

GRID = np.arange(0, 261, 1.0)  # weeks, extrapolation horizon 5y for Weibull

# ---------- LOVO evaluation on failed VINs -----------------------------------
HORIZONS = [4, 9, 13, 26]  # actual RUL in weeks (~30/60/90/180 d)
rows, traj_rows = [], []
for vin in surv.loc[surv.failed, "vin_label"]:
    tr = surv[surv.vin_label != vin]
    wb_f = WeibullFitter().fit(tr["T"], tr["failed"])
    km_f = KaplanMeierFitter().fit(tr["T"], tr["failed"])
    wb_sf = lambda u: np.exp(-(u / wb_f.lambda_) ** wb_f.rho_) if u > 0 else 1.0
    km_sf = lambda u: float(km_f.predict(u))
    T_i = float(surv.loc[surv.vin_label == vin, "T"].iloc[0])
    for h in HORIZONS:
        t_eval = T_i - h
        if t_eval < 1:
            continue
        pw = cond_median_rul(wb_sf, t_eval, GRID)
        pk = cond_median_rul(km_sf, t_eval, GRID)
        rows.append(dict(vin=vin, horizon_wk=h, t_eval=t_eval,
                         rul_wb=pw, rul_km=pk, actual=h))
    # full last-26-weeks trajectory at observed weeks
    vw = tw[(tw.vin_label == vin) & (tw.weeks_to_fail >= 1)
            & (tw.weeks_to_fail <= 26)]
    for _, r in vw.iterrows():
        t_eval = float(r.age_week)
        pw = cond_median_rul(wb_sf, t_eval, GRID)
        traj_rows.append(dict(vin=vin, age_week=t_eval,
                              actual=float(r.weeks_to_fail), rul_wb=pw))

ev = pd.DataFrame(rows)
tj = pd.DataFrame(traj_rows)
ev.to_csv(os.path.join(OUT, "F_fleetclock_horizon_eval.csv"), index=False)
tj.to_csv(os.path.join(OUT, "F_fleetclock_rul_traj.csv"), index=False)

print("\n=== LOVO conditional-median RUL MAE on failed VINs (days) ===")
for h in HORIZONS:
    e = ev[ev.horizon_wk == h]
    mw = (e.rul_wb - e.actual).abs().mean() * 7
    mk = (e.rul_km - e.actual).abs().mean() * 7
    nk = e.rul_km.notna().sum()
    print(f"  actual RUL {h:>2} wk ({h*7:>3} d): n={len(e)}  "
          f"Weibull MAE {mw:6.1f} d | KM MAE {mk:6.1f} d (KM defined {nk}/{len(e)})")
mt = (tj.rul_wb - tj.actual).abs().mean() * 7
print(f"\nLast-26-weeks trajectory (n={len(tj)} truck-weeks, 14 VINs): "
      f"Weibull fleet-clock MAE = {mt:.1f} d")
print(f"  naive constant predictor (median actual RUL "
      f"{tj.actual.median()*7:.0f} d): MAE = "
      f"{(tj.actual - tj.actual.median()).abs().mean()*7:.1f} d")

# ---------- JCOPENDATE sensitivity -------------------------------------------
wb_j = WeibullFitter().fit(surv["T_jco"], surv["failed"])
km_j = KaplanMeierFitter().fit(surv["T_jco"], surv["failed"])
print("\n=== Sensitivity: JCOPENDATE event times (5 gap VINs +32..142 d) ===")
print(f"KM median: {km_j.median_survival_time_:.1f} wk "
      f"(vs {km.median_survival_time_:.1f}); Weibull median "
      f"{wb_j.median_survival_time_:.1f} wk (vs {wb.median_survival_time_:.1f})")
