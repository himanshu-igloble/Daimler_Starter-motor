"""
G3_prequential_horizon.py — Agent G, V1.1 discovery.

(d) Earliest-detection / prequential analysis: walk time backwards.
For each offset k = 0..26 weeks before each VIN's t_end (t_end = max event
ts_start; for NF trucks this is simply end-of-observation), compute CAUSAL
versions of the honest features using ONLY data up to the cut date
(cut = t_end - 7k days), on a fixed last-40-masked-week basis ending at cut:

  f1 vsi_withinwk_std_ratio_30d_c : mean(vsi_drive_std last 4 wks) /
                                    mean(vsi_drive_std over L40 window)
  f2 vsi_std_ratio_30d_c          : std(vsi_drive_mean last 4 wks) /
                                    std(vsi_drive_mean over L40 window)
  f3 failed_crank_rate_90d_c      : failed-crank share in [cut-90d, cut],
                                    SMA-dead cohort masked to NaN (median-
                                    imputed inside each LOVO train fold)
  f4 vsi_range_trend_c            : Theil-Sen slope of weekly (p95-p05) over
                                    the last 12 masked weeks before cut

Scoring: at each k, truck-level LOVO Ridge on [f1..f4], every truck truncated
at its own offset-k cut (train and test see the same causal horizon).
Report AUROC(k), median failed/NF score separation, and feature coverage.
Earliest actionable horizon = largest k with AUROC >= 0.75 sustained
(monotone reading from k=0 outward; single-k blips noted).

Control: G3b recomputes the G2 winner trend-slope feature on a fixed L=20
window (no VIN needs resampling at L=20) to disambiguate the span-correlation
flag on std_slope.

Outputs: STARTER MOTOR/V1.1/discovery/out/G3_horizon_curve.csv
         STARTER MOTOR/V1.1/discovery/out/G3_L20_control.csv
Run: py -3 G3_prequential_horizon.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "discovery" / "out"
L = 40
K_MAX = 26
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
RNG = np.random.default_rng(42)

wk_all = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev_all = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev_all = ev_all[ev_all["artifact"] == False].copy()
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
ev_all["succ_b"] = ev_all["success"].map(lambda x: bool(x) if x is not None and x == x else np.nan)
fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
vins = fm["vin_label"].tolist()
y = fm["failed"].values.astype(int)

T_END = {v: ev_all.loc[ev_all["vin_label"] == v, "ts_start"].max() for v in vins}
WK = {v: wk_all[(wk_all["vin_label"] == v) & (wk_all["active_days"] >= 2)]
      .sort_values("week").reset_index(drop=True) for v in vins}
EV = {v: ev_all[ev_all["vin_label"] == v] for v in vins}


def theil_sen(yv, xv):
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


def causal_feats(vin, cut):
    """Honest features using only data with timestamp <= cut, L40 window basis."""
    wm = WK[vin][WK[vin]["week"] <= cut].tail(L)
    f = {"n_wk": len(wm)}
    if len(wm) < 8:
        f.update({"f1": np.nan, "f2": np.nan, "f4": np.nan})
    else:
        vds = wm["vsi_drive_std"].values.astype(float)
        f["f1"] = (float(np.nanmean(vds[-4:]) / np.nanmean(vds))
                   if np.isfinite(vds).sum() >= 6 and np.nanmean(vds) > 0 else np.nan)
        vdm = wm["vsi_drive_mean"].values.astype(float)
        va = vdm[np.isfinite(vdm)]
        l4 = vdm[-4:]; l4 = l4[np.isfinite(l4)]
        f["f2"] = (float(np.std(l4) / np.std(va))
                   if len(va) >= 2 and len(l4) >= 2 and np.std(va) > 0 and np.std(l4) > 0
                   else np.nan)
        last12 = wm.tail(12)
        rng12 = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
        x12 = (last12["week"] - last12["week"].iloc[0]).dt.days.values / 7.0
        f["f4"] = theil_sen(rng12, x12) if np.isfinite(rng12).sum() >= 6 else np.nan
    if vin in SMA_DEAD:
        f["f3"] = np.nan
    else:
        ev = EV[vin]
        e90 = ev[(ev["ts_start"] <= cut) & (ev["ts_start"] > cut - pd.Timedelta(days=90))]
        e90 = e90[e90["succ_b"].notna()]
        f["f3"] = (float((~e90["succ_b"].astype(bool)).mean()) if len(e90) >= 10 else np.nan)
    return f


def rank_auroc(scores, labels):
    m = np.isfinite(scores)
    s, l = np.asarray(scores)[m], np.asarray(labels)[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    return sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos) / (len(pos) * len(neg))


def lovo_ridge(F, labels):
    """LOVO Ridge with per-fold median imputation + scaling."""
    oof = np.zeros(len(labels))
    for i in range(len(labels)):
        tr = np.ones(len(labels), bool); tr[i] = False
        med = np.nanmedian(F[tr], axis=0)
        Ftr = np.where(np.isfinite(F[tr]), F[tr], med)
        Fte = np.where(np.isfinite(F[~tr]), F[~tr], med)
        sc = StandardScaler().fit(Ftr)
        m = Ridge(alpha=1.0).fit(sc.transform(Ftr), labels[tr])
        oof[i] = m.predict(sc.transform(Fte))[0]
    return oof


def boot_ci(scores, labels, n=500):
    vals = []
    scores, labels = np.asarray(scores), np.asarray(labels)
    for _ in range(n):
        idx = RNG.integers(0, len(labels), len(labels))
        a = rank_auroc(scores[idx], labels[idx])
        if np.isfinite(a):
            vals.append(a)
    return np.percentile(vals, 2.5), np.percentile(vals, 97.5)


print("Prequential walk-back: k = 0..%d weeks before each VIN's t_end" % K_MAX)
rows = []
for k in range(K_MAX + 1):
    feats, valid = [], []
    for vin in vins:
        cut = T_END[vin] - pd.Timedelta(days=7 * k)
        f = causal_feats(vin, cut)
        feats.append([f["f1"], f["f2"], f["f3"], f["f4"]])
        valid.append(f["n_wk"])
    F = np.array(feats, float)
    cov = np.isfinite(F).mean(axis=0)
    # drop trucks with no usable window at this offset (n_wk < 8 -> all-VSI NaN)
    usable = np.array([v >= 8 for v in valid])
    if usable.sum() < 10 or y[usable].sum() < 4:
        print(f"  k={k:2d}: insufficient usable trucks ({usable.sum()}) — stop")
        break
    oof = lovo_ridge(F[usable], y[usable])
    a = rank_auroc(oof, y[usable])
    lo, hi = boot_ci(oof, y[usable])
    med_f = np.median(oof[y[usable] == 1]); med_nf = np.median(oof[y[usable] == 0])
    rows.append({"k_weeks": k, "auroc": round(a, 4), "ci95_lo": round(lo, 4),
                 "ci95_hi": round(hi, 4), "n_usable": int(usable.sum()),
                 "n_failed_usable": int(y[usable].sum()),
                 "median_score_failed": round(med_f, 4),
                 "median_score_nf": round(med_nf, 4),
                 "median_separation": round(med_f - med_nf, 4),
                 "cov_f1": round(cov[0], 2), "cov_f2": round(cov[1], 2),
                 "cov_f3": round(cov[2], 2), "cov_f4": round(cov[3], 2)})
    print(f"  k={k:2d}: AUROC={a:.3f} [{lo:.3f},{hi:.3f}]  sep={med_f-med_nf:+.3f}  "
          f"usable={usable.sum()} (F={y[usable].sum()})  cov f1..f4="
          f"{cov[0]:.2f}/{cov[1]:.2f}/{cov[2]:.2f}/{cov[3]:.2f}")

hc = pd.DataFrame(rows)
hc.to_csv(OUT / "G3_horizon_curve.csv", index=False)

# earliest actionable horizon: largest k such that AUROC >= 0.75 for all j <= k
thr = 0.75
k_star = -1
for _, r in hc.iterrows():
    if r["auroc"] >= thr:
        k_star = int(r["k_weeks"])
    else:
        break
print(f"\nEarliest actionable horizon (sustained AUROC >= {thr} from k=0): "
      f"k* = {k_star} weeks before t_end")
blips = hc[(hc["k_weeks"] > k_star) & (hc["auroc"] >= thr)]["k_weeks"].tolist()
if blips:
    print(f"  (isolated blips >= {thr} beyond k*: {blips} — not counted)")

# ── G3b: L=20 no-resample control for the G2 trend-slope feature ────────────
print("\nG3b: std_slope on fixed L=20 window (no VIN resampled) — leak control")
rows20 = []
nmin = min(len(WK[v]) for v in vins)
print(f"  min masked weeks across fleet = {nmin} (need >= 20)")
xg = np.linspace(0, 1, 20)
sl20, nwk_arr = [], []
for vin in vins:
    v = WK[vin]["vsi_drive_std"].values.astype(float)
    v = pd.Series(v).interpolate(limit_direction="both").values
    seg = v[-20:]
    mu, sd = np.nanmean(seg), np.nanstd(seg)
    z = (seg - mu) / sd if sd > 0 else seg * 0
    sl20.append(np.polyfit(xg, z, 1)[0])
    nwk_arr.append(len(WK[vin]))
sl20 = np.array(sl20); nwk_arr = np.array(nwk_arr, float)
a20 = rank_auroc(sl20, y)
t0 = np.array([WK[v]["week"].min().toordinal() for v in vins], float)
sp = np.array([(WK[v]["week"].max() - WK[v]["week"].min()).days for v in vins], float)
print(f"  std_slope_L20: AUROC={max(a20,1-a20):.4f}  "
      f"r_nweeks={stats.spearmanr(sl20, nwk_arr)[0]:+.3f}  "
      f"r_t_start={stats.spearmanr(sl20, t0)[0]:+.3f}  "
      f"r_span={stats.spearmanr(sl20, sp)[0]:+.3f}")
pd.DataFrame([{"feature": "std_slope_L20", "auroc": round(max(a20, 1 - a20), 4),
               "r_nweeks": round(stats.spearmanr(sl20, nwk_arr)[0], 3),
               "r_t_start": round(stats.spearmanr(sl20, t0)[0], 3),
               "r_span": round(stats.spearmanr(sl20, sp)[0], 3)}]
             ).to_csv(OUT / "G3_L20_control.csv", index=False)
print("\nSaved ->", OUT / "G3_horizon_curve.csv")
