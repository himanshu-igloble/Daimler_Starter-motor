# F3_hazard_lovo.py -- Agent F: discrete-time hazard model, truck-level LOVO
# Model: logistic regression on truck-weeks
#        logit h(t) = b0 + b1*log1p(age_week) + b2*vsi_std_ratio
#                        + b3*crank_fail_rate + b4*rest_delta
# (3 time-varying covariates + log-age baseline; EPV = 14/4 = 3.5, ridge-stab.)
# All preprocessing (imputation means, scaler) fit INSIDE each LOVO fold.
# Metrics on pooled held-out truck-weeks:
#   - pooled weekly-hazard AUROC (event week vs all other at-risk weeks)
#   - age-matched concordance (event week vs other trucks at-risk at same age)
#   - P(fail within H) AUROC for H in {30,60,90} d (covariates frozen at t)
#   - calibration: cal-in-the-large, logistic recalibration slope, decile table
#   - per-failed-VIN median-RUL trajectory over last 26 weeks -> MAE
# NOTE on inference: weekly rows within a truck are correlated; no SEs are
# reported from the pooled logistic. LOVO at truck level handles optimism;
# concordance/AUROC point estimates remain subject to clustering (stated).
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = r"D:\Daimler-starter_motor_alternator_battery"
OUT = os.path.join(ROOT, "STARTER MOTOR", "V1.1", "discovery", "out")
tw = pd.read_parquet(os.path.join(OUT, "F_truck_week.parquet"))
dq = pd.read_csv(os.path.join(ROOT, "STARTER MOTOR", "results",
                              "V1_SM_data_quality.csv"))
tw = tw.merge(dq[["vin_label", "gap_days"]], on="vin_label", how="left")

COV = ["vsi_std_ratio", "crank_fail_rate", "rest_delta"]
FEAT = ["log_age"] + COV
tw["log_age"] = np.log1p(tw.age_week)
MAXK = 260
rng = np.random.default_rng(42)

vins = sorted(tw.vin_label.unique())
preds = []          # one row per held-out truck-week with hazard + P(fail<=H)
coefs = []
for vin in vins:
    tr = tw[tw.vin_label != vin].copy()
    te = tw[tw.vin_label == vin].copy()
    imp = tr[COV].mean()                       # fold-internal imputation
    Xtr = tr[FEAT].fillna(imp).to_numpy()
    ytr = tr.event.to_numpy()
    sc = StandardScaler().fit(Xtr)
    clf = LogisticRegression(C=1.0, max_iter=5000).fit(sc.transform(Xtr), ytr)
    coefs.append(dict(zip(FEAT, clf.coef_[0] / sc.scale_), vin=vin))

    Xte = te[FEAT].fillna(imp)
    h = clf.predict_proba(sc.transform(Xte.to_numpy()))[:, 1]
    te = te.assign(hazard=h)
    # P(fail within H days | covariates frozen at t), age advances
    cov_vals = Xte[COV].to_numpy()
    ages = te.age_week.to_numpy()
    for H, Hw in [(30, 4), (60, 9), (90, 13)]:
        p = np.empty(len(te))
        for j in range(len(te)):
            fut_age = np.log1p(ages[j] + np.arange(1, Hw + 1))
            Xf = np.column_stack([fut_age,
                                  np.repeat(cov_vals[j][None, :], Hw, axis=0)])
            hf = clf.predict_proba(sc.transform(Xf))[:, 1]
            p[j] = 1 - np.prod(1 - hf)
        te[f"p_fail_{H}d"] = p
    # median RUL (weeks): smallest k with S(t+k) <= 0.5, covariates frozen
    med = np.empty(len(te))
    for j in range(len(te)):
        fut_age = np.log1p(ages[j] + np.arange(1, MAXK + 1))
        Xf = np.column_stack([fut_age,
                              np.repeat(cov_vals[j][None, :], MAXK, axis=0)])
        hf = clf.predict_proba(sc.transform(Xf))[:, 1]
        S = np.cumprod(1 - hf)
        k = np.argmax(S <= 0.5)
        med[j] = (k + 1) if S.min() <= 0.5 else MAXK  # capped
    te["med_rul_wk"] = med
    preds.append(te)

P = pd.concat(preds, ignore_index=True)
P.to_parquet(os.path.join(OUT, "F_hazard_lovo_preds.parquet"), index=False)
cf = pd.DataFrame(coefs).set_index("vin")[FEAT]
print("=== LOVO coefficient stability (per-unit, unstandardized) ===")
print(cf.describe().loc[["mean", "std", "min", "max"]].round(3).to_string())

# ---- pooled weekly-hazard AUROC ---------------------------------------------
auc_pool = roc_auc_score(P.event, P.hazard)
print(f"\nPooled weekly-hazard AUROC (14 event-weeks vs {len(P)-14} "
      f"at-risk weeks): {auc_pool:.3f}")

# ---- age-matched concordance (time-dependent C) ------------------------------
conc, n_pairs = 0, 0
for _, e in P[P.event == 1].iterrows():
    cmp_ = P[(P.vin_label != e.vin_label) & (P.age_week == e.age_week)]
    if len(cmp_) == 0:
        continue
    conc += ((e.hazard > cmp_.hazard).sum() + 0.5 * (e.hazard == cmp_.hazard).sum())
    n_pairs += len(cmp_)
print(f"Age-matched concordance (event vs same-age at-risk weeks): "
      f"{conc/n_pairs:.3f} over {n_pairs} pairs, 14 events")

# ---- horizon AUROCs ----------------------------------------------------------
print("\n=== P(fail within H) AUROC over held-out truck-weeks ===")
print("(positives: failed VINs' weeks with weeks_to_fail <= Hw;"
      " negatives: all NF weeks + failed VINs' earlier weeks)")
P["wtf_jco"] = P.weeks_to_fail + np.where(P.failed, P.gap_days.fillna(0) / 7, 0)
for H, Hw in [(30, 4), (60, 9), (90, 13)]:
    y = np.where(P.failed & (P.weeks_to_fail <= Hw), 1, 0)
    a = roc_auc_score(y, P[f"p_fail_{H}d"])
    yj = np.where(P.failed & (P.wtf_jco <= Hw), 1, 0)
    aj = roc_auc_score(yj, P[f"p_fail_{H}d"]) if yj.sum() > 0 else np.nan
    # log-age-only ablation comparison via age itself as score
    a_age = roc_auc_score(y, P.age_week)
    print(f"  H={H:>2}d (Hw={Hw:>2}): AUROC {a:.3f} (n_pos={y.sum():>3})  "
          f"| age-only score {a_age:.3f}  | JCOPEN-shifted labels {aj:.3f} "
          f"(n_pos={yj.sum()})")

# ---- calibration -------------------------------------------------------------
print("\n=== Calibration of weekly hazard (held-out) ===")
print(f"Sum predicted events: {P.hazard.sum():.1f} vs observed 14 "
      f"(cal-in-large ratio {P.hazard.sum()/14:.2f})")
eps = 1e-10
lo = np.log(np.clip(P.hazard, eps, 1 - eps) / (1 - np.clip(P.hazard, eps, 1 - eps)))
rc = LogisticRegression(C=1e6, max_iter=5000).fit(lo.to_numpy().reshape(-1, 1), P.event)
print(f"Logistic recalibration slope: {rc.coef_[0][0]:.2f} "
      f"(1.0 = perfect; <1 = overconfident spread)")
P["dec"] = pd.qcut(P.hazard, 10, labels=False, duplicates="drop")
cal = P.groupby("dec").agg(pred=("hazard", "mean"), obs=("event", "mean"),
                           n=("event", "size"))
print(cal.round(5).to_string())

# ---- truck-level risk score vs V1 static classifier ---------------------------
tl = P.groupby("vin_label").agg(failed=("failed", "first"),
                                last4=("hazard", lambda s: s.tail(4).mean()),
                                peak=("hazard", "max"))
print("\n=== Truck-level risk ranking (held-out hazard) ===")
print(f"AUROC failed-vs-NF, mean hazard last 4 obs weeks: "
      f"{roc_auc_score(tl.failed, tl.last4):.3f}")
print(f"AUROC failed-vs-NF, peak hazard:                  "
      f"{roc_auc_score(tl.failed, tl.peak):.3f}")
print("(V1 static nested-LOVO baseline: 0.893)")
print("NOTE: last-4-weeks mean is leakage-adjacent for ranking (failed trucks'"
      " last weeks ARE pre-failure weeks); shown for context, not as a deploy"
      " metric.")

# ---- RUL trajectories: hazard model vs fleet clock vs constant -----------------
tj_fc = pd.read_csv(os.path.join(OUT, "F_fleetclock_rul_traj.csv"))
mask = P.failed & (P.weeks_to_fail >= 1) & (P.weeks_to_fail <= 26)
tj = P.loc[mask, ["vin_label", "age_week", "weeks_to_fail", "med_rul_wk"]].copy()
mae_hz = (tj.med_rul_wk - tj.weeks_to_fail).abs().mean() * 7
print(f"\n=== Median-RUL MAE, failed VINs' last 26 weeks "
      f"(n={len(tj)} truck-weeks) ===")
print(f"  Discrete-time hazard model : {mae_hz:7.1f} d "
      f"(median pred {tj.med_rul_wk.median()*7:.0f} d, capped@{MAXK}wk: "
      f"{(tj.med_rul_wk >= MAXK).mean():.0%})")
mae_fc = (tj_fc.rul_wb - tj_fc.actual).abs().mean() * 7
print(f"  Weibull fleet clock (LOVO) : {mae_fc:7.1f} d")
const = tj_fc.actual.median()
print(f"  Constant ({const*7:.0f} d)          : "
      f"{(tj_fc.actual - const).abs().mean()*7:7.1f} d")
tj.to_csv(os.path.join(OUT, "F_hazard_rul_traj.csv"), index=False)
per_vin = tj.groupby("vin_label").apply(
    lambda g: (g.med_rul_wk - g.weeks_to_fail).abs().mean() * 7,
    include_groups=False)
print("\nPer-VIN hazard-model RUL MAE (d):")
print(per_vin.round(0).to_string())
