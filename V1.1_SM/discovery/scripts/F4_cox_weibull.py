# F4_cox_weibull.py -- Agent F: Cox PH (time-varying) sanity check + Weibull AFT
# Cox: lifelines CoxTimeVaryingFitter, 2 covariates (EPV = 14/2 = 7):
#      vsi_std_ratio + rest_delta (the two covariates available for ALL trucks;
#      crank_fail_rate excluded here -- masked for 7 SMA-dead trucks).
#      Each observed week contributes interval [age_week, age_week+1); silent
#      gap weeks are treated as not-at-risk (no telemetry, no covariates).
# Inference caveat: lifelines CTV has no cluster-robust SEs; we attempt
#      robust=True, else report naive SEs with an explicit warning that
#      within-truck correlation makes them anti-conservative.
# Weibull AFT: per-truck static fit with ONE causal early-life covariate
#      (mean vsi_drive_std over first 8 observed weeks -- known by week 8,
#      earliest failure is week 21).
import os
import warnings

import numpy as np
import pandas as pd
from lifelines import CoxTimeVaryingFitter, WeibullAFTFitter

warnings.filterwarnings("ignore")
ROOT = r"D:\Daimler-starter_motor_alternator_battery"
OUT = os.path.join(ROOT, "STARTER MOTOR", "V1.1", "discovery", "out")
tw = pd.read_parquet(os.path.join(OUT, "F_truck_week.parquet"))

# ---------------- Cox time-varying -------------------------------------------
COX_COV = ["vsi_std_ratio", "rest_delta"]
ctv_df = tw[["vin_label", "age_week", "event"] + COX_COV].copy()
ctv_df[COX_COV] = ctv_df[COX_COV].fillna(ctv_df[COX_COV].mean())
ctv_df["start"] = ctv_df.age_week.astype(float)
ctv_df["stop"] = ctv_df.start + 1.0
ctv_df = ctv_df.drop(columns="age_week")  # age IS the Cox time axis
ctv = CoxTimeVaryingFitter(penalizer=0.01)
robust_note = ""
try:
    ctv.fit(ctv_df, id_col="vin_label", start_col="start", stop_col="stop",
            event_col="event", robust=True)
    robust_note = "robust=True (within-id sandwich) accepted by lifelines CTV"
except (TypeError, NotImplementedError):
    ctv.fit(ctv_df, id_col="vin_label", start_col="start", stop_col="stop",
            event_col="event")
    robust_note = ("robust SEs NOT available in CTV -> naive SEs shown; "
                   "within-truck correlation makes them ANTI-CONSERVATIVE")
print("=== Cox PH time-varying (penalizer=0.01, 2 covariates, 14 events) ===")
print(robust_note)
print(ctv.summary[["coef", "exp(coef)", "se(coef)", "p"]].round(3).to_string())
print(f"Partial log-likelihood: {ctv.log_likelihood_:.2f}")

# null model for LR-style comparison
ctv0 = CoxTimeVaryingFitter(penalizer=0.01)
ctv_df0 = ctv_df.copy()
ctv_df0["zero"] = 0.0
# lifelines needs >=1 covariate; use ~null via tiny-variance column workaround:
ctv_df0["zero"] = np.random.default_rng(0).normal(0, 1e-8, len(ctv_df0))
try:
    ctv0.fit(ctv_df0[["vin_label", "start", "stop", "event", "zero"]],
             id_col="vin_label", start_col="start", stop_col="stop",
             event_col="event")
    lr = 2 * (ctv.log_likelihood_ - ctv0.log_likelihood_)
    from scipy.stats import chi2
    print(f"LR vs null: {lr:.2f} (chi2_2 p={chi2.sf(lr, 2):.4f}) "
          f"[naive, ignores clustering]")
except Exception as e:
    print("null CTV fit failed:", e)

# ---------------- Weibull AFT (static, 1 early-life covariate) -----------------
# early-life covariate from raw weekly cache (first 8 observed weeks):
import glob
rows = []
for f in sorted(glob.glob(os.path.join(
        ROOT, "STARTER MOTOR", "cache", "weekly", "V1_SM_weekly_*.parquet"))):
    d = pd.read_parquet(f).sort_values("week")
    rows.append(dict(vin_label=d.vin_label.iloc[0],
                     early_vsi_std=float(d.vsi_drive_std.head(8).mean(skipna=True))))
early = pd.DataFrame(rows)
surv = (tw.groupby("vin_label")
          .agg(failed=("failed", "first"), T=("age_week", "max"))
          .reset_index().merge(early, on="vin_label"))
surv["T"] = surv["T"].clip(lower=1)
surv["early_vsi_std"] = surv.early_vsi_std.fillna(surv.early_vsi_std.mean())
aft = WeibullAFTFitter(penalizer=0.01)
aft.fit(surv[["T", "failed", "early_vsi_std"]], duration_col="T",
        event_col="failed")
print("\n=== Weibull AFT (static, early-life mean vsi_drive_std wk0-7) ===")
print(aft.summary[["coef", "exp(coef)", "se(coef)", "p"]].round(3).to_string())
print(f"Concordance (in-sample, n=34): {aft.concordance_index_:.3f}")
print(f"rho (shape): {np.exp(aft.summary.loc[('rho_','Intercept'),'coef']):.2f}"
      f"  -> hazard {'increases' if np.exp(aft.summary.loc[('rho_','Intercept'),'coef'])>1 else 'decreases'} with age")
print("n=34, 14 events: one covariate => EPV 14. Cluster note: one row per "
      "truck, no within-truck repetition here.")
