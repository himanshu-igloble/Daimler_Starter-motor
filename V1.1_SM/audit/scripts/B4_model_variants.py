"""
B4_model_variants.py — Agent B, V1.1 feature audit, Part 4.
LOVO RidgeClassifier model variants following the B3 finding that
vsi_dominant_freq is a history-length artifact and the B2 finding that
vsi_withinwk_std_ratio_30d is the strongest clean new candidate.

Variants (all LOVO, alpha=1.0, train-median impute, StandardScaler):
  A  baseline 4 winners (replication, 0.9214)
  B  drop vsi_dominant_freq (3 features)
  C  swap vsi_dominant_freq -> vsi_withinwk_std_ratio_30d (full-history defn)
  D  swap vsi_dominant_freq -> vsi_withinwk_std_ratio_30d_w (L40 windowed defn)
  E  4 winners + vsi_withinwk_std_ratio_30d (5 features)
  F  C + vsi_trend_persistence (5 features)
  G  swap also vsi_std_ratio_30d -> windowed defn (all-windowed honest 4-feat)

Reports AUROC, VIN8_F_SM prob, false-alarm VINs (VIN8_NF, VIN9_NF) probs.
Output: STARTER MOTOR/V1.1/audit/out/B4_model_variants.csv
Run: py -3 B4_model_variants.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats, signal
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, roc_curve
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "audit" / "out"
L = 40

fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
y = fm["failed"].values.astype(int)
vins = fm["vin_label"].tolist()

wk_all = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])

# build the candidate columns needed
extra = {}
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    wm = w[w["active_days"] >= 2].sort_values("week").reset_index(drop=True)
    vds_full = wm["vsi_drive_std"].values.astype(float)
    vdm_full = wm["vsi_drive_mean"].values.astype(float)
    row = {}
    row["vsi_withinwk_std_ratio_30d"] = (float(np.nanmean(vds_full[-4:]) / np.nanmean(vds_full))
                                         if np.isfinite(vds_full).sum() >= 6
                                         and np.nanmean(vds_full) > 0 else np.nan)
    wmL = wm.tail(L)
    vdsL = wmL["vsi_drive_std"].values.astype(float)
    row["vsi_withinwk_std_ratio_30d_w"] = (float(np.nanmean(vdsL[-4:]) / np.nanmean(vdsL))
                                           if np.isfinite(vdsL).sum() >= 6
                                           and np.nanmean(vdsL) > 0 else np.nan)
    vdmL = wmL["vsi_drive_mean"].values.astype(float)
    va = vdmL[np.isfinite(vdmL)]
    l4 = vdmL[-4:]; l4 = l4[np.isfinite(l4)]
    row["vsi_std_ratio_30d_w"] = (float(np.std(l4) / np.std(va))
                                  if len(va) >= 2 and len(l4) >= 2 and np.std(va) > 0
                                  and np.std(l4) > 0 else np.nan)
    # trend persistence (last 12 masked weeks)
    if len(wm) >= 12:
        wmm = wm.copy()
        wmm["week_x"] = (wmm["week"] - wmm["week"].iloc[0]).dt.days / 7.0
        seg = vdm_full[-12:]; sx = wmm["week_x"].values[-12:]
        slopes = []
        for i in range(len(seg) - 3):
            yy, xx = seg[i:i+4], sx[i:i+4]
            mq = np.isfinite(yy)
            if mq.sum() >= 3:
                slopes.append(np.polyfit(xx[mq], yy[mq], 1)[0])
        row["vsi_trend_persistence"] = (abs(np.mean(np.sign(slopes)))
                                        if len(slopes) >= 5 else np.nan)
    else:
        row["vsi_trend_persistence"] = np.nan
    extra[vin] = row
ex = pd.DataFrame([dict(vin_label=v, **extra[v]) for v in vins])
b2 = pd.read_csv(OUT / "B2_candidate_matrix.csv")[["vin_label", "failed_crank_rate_last30"]]
df = fm.merge(ex, on="vin_label").merge(b2, on="vin_label")


def lovo(cols):
    X = df[cols].values.astype(float)
    n = len(y)
    probs = np.full(n, np.nan)
    for i in range(n):
        tr = np.concatenate([np.arange(0, i), np.arange(i + 1, n)])
        Xtr, Xte = X[tr].copy(), X[i:i+1].copy()
        for j in range(Xtr.shape[1]):
            med = np.nanmedian(Xtr[:, j])
            med = 0.0 if np.isnan(med) else med
            Xtr[np.isnan(Xtr[:, j]), j] = med
            Xte[np.isnan(Xte[:, j]), j] = med
        sc = StandardScaler().fit(Xtr)
        mdl = RidgeClassifier(alpha=1.0, random_state=42).fit(sc.transform(Xtr), y[tr])
        z = mdl.decision_function(sc.transform(Xte))[0]
        probs[i] = 1.0 / (1.0 + np.exp(-z)) if z >= 0 else np.exp(z) / (1.0 + np.exp(z))
    return probs


W = ["vsi_std_ratio_30d", "vsi_dominant_freq", "failed_crank_rate_last90", "vsi_range_trend"]
VARIANTS = {
    "A_baseline_4winners": W,
    "B_drop_domfreq_3feat": ["vsi_std_ratio_30d", "failed_crank_rate_last90", "vsi_range_trend"],
    "C_swap_domfreq_to_withinwk": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d",
                                   "failed_crank_rate_last90", "vsi_range_trend"],
    "D_swap_windowed_withinwk": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d_w",
                                 "failed_crank_rate_last90", "vsi_range_trend"],
    "E_add_withinwk_5feat": W + ["vsi_withinwk_std_ratio_30d"],
    "F_C_plus_persistence_5feat": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d",
                                   "failed_crank_rate_last90", "vsi_range_trend",
                                   "vsi_trend_persistence"],
    "G_all_windowed_4feat": ["vsi_std_ratio_30d_w", "vsi_withinwk_std_ratio_30d_w",
                             "failed_crank_rate_last90", "vsi_range_trend"],
    "H_D_plus_persistence_5feat": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d_w",
                                   "failed_crank_rate_last90", "vsi_range_trend",
                                   "vsi_trend_persistence"],
    "I_D_swap_fcr30": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d_w",
                       "failed_crank_rate_last30", "vsi_range_trend"],
    "J_honest_3feat": ["vsi_std_ratio_30d", "vsi_withinwk_std_ratio_30d_w",
                       "failed_crank_rate_last90"],
}
iv8 = vins.index("VIN8_F_SM")
iv8n = vins.index("VIN8_NF_SM")
iv9n = vins.index("VIN9_NF_SM")
rows = []
for name, cols in VARIANTS.items():
    p = lovo(cols)
    auc = roc_auc_score(y, p)
    fpr, tpr, thr = roc_curve(y, p)
    t = float(thr[np.argmax(tpr - fpr)])
    miss = int(((p < t) & (y == 1)).sum())
    fa = int(((p >= t) & (y == 0)).sum())
    rows.append({"variant": name, "k": len(cols), "auroc": round(auc, 4),
                 "youden_misses": miss, "youden_false_alarms": fa,
                 "vin8F_prob": round(p[iv8], 4), "vin8NF_prob": round(p[iv8n], 4),
                 "vin9NF_prob": round(p[iv9n], 4)})
res = pd.DataFrame(rows)
res.to_csv(OUT / "B4_model_variants.csv", index=False)
print(res.to_string(index=False))
print("\nDone ->", OUT / "B4_model_variants.csv")
