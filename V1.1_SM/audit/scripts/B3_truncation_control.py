"""
B3_truncation_control.py — Agent B, V1.1 feature audit, Part 3.
History-LENGTH control (stronger than V1's calendar-truncation epoch control,
which only removed <=7 trailing NF weeks and never equalized history length).

Control A (fixed window): every feature recomputed using ONLY each VIN's last
L=40 masked weeks (and events in the same calendar span). All NF VINs (>=40
weeks) get exactly a 40-week basis; failed VINs keep min(n, 40).
If a feature's AUROC collapses under the fixed window, its V1 discriminative
power was substantially a history-length artifact.

Features tested: the 4 V1 winners + the top span-flagged candidates from B2.
Output: STARTER MOTOR/V1.1/audit/out/B3_truncation_control.csv
Run: py -3 B3_truncation_control.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats, signal
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "audit" / "out"
L = 40  # fixed masked-week window

fm = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
y = fm["failed"].values.astype(int)
vins = fm["vin_label"].tolist()

wk_all = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev_all = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev_all = ev_all[ev_all["artifact"] == False].copy()
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
ev_all["succ_b"] = ev_all["success"].map(lambda x: bool(x) if x is not None and x == x else np.nan)


def rank_auroc(scores, labels):
    m = np.isfinite(scores)
    s, l = scores[m], labels[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))


def theil_sen(yv, xv):
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


# masked-week length distribution
lens = {}
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    lens[vin] = int((w["active_days"] >= 2).sum())
lf = np.array([lens[v] for v in vins])
print(f"Masked-week count — failed: min={lf[y==1].min()} med={np.median(lf[y==1]):.0f} "
      f"max={lf[y==1].max()} | NF: min={lf[y==0].min()} med={np.median(lf[y==0]):.0f} "
      f"max={lf[y==0].max()}")
print(f"Fixed window L = {L} masked weeks; "
      f"failed VINs with full {L}: {(lf[y==1] >= L).sum()}/14, NF: {(lf[y==0] >= L).sum()}/20")

rows = []
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    wm = w[w["active_days"] >= 2].sort_values("week").reset_index(drop=True)
    wm = wm.tail(L).reset_index(drop=True)           # FIXED WINDOW
    wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
    win_start = wm["week"].iloc[0]
    ev = ev_all[(ev_all["vin_label"] == vin) & (ev_all["ts_start"] >= win_start)]
    vdm = wm["vsi_drive_mean"].values.astype(float)
    f = {"vin_label": vin, "n_wk_window": len(wm)}

    # winner 1: vsi_std_ratio_30d (within window)
    va = vdm[np.isfinite(vdm)]
    l4 = vdm[-4:]; l4 = l4[np.isfinite(l4)]
    f["vsi_std_ratio_30d_w"] = (float(np.std(l4) / np.std(va))
                                if len(va) >= 2 and len(l4) >= 2 and np.std(va) > 0
                                and np.std(l4) > 0 else np.nan)
    # candidates: 60d / 90d ratios within window
    for n_last, name in ((8, "vsi_std_ratio_60d_w"), (13, "vsi_std_ratio_90d_w")):
        ll = vdm[-n_last:]; ll = ll[np.isfinite(ll)]
        f[name] = (float(np.std(ll) / np.std(va))
                   if len(va) >= 2 and len(ll) >= 2 and np.std(va) > 0 else np.nan)
    # within-week std ratio
    vds = wm["vsi_drive_std"].values.astype(float)
    f["vsi_withinwk_std_ratio_30d_w"] = (float(np.nanmean(vds[-4:]) / np.nanmean(vds))
                                         if np.isfinite(vds).sum() >= 6
                                         and np.nanmean(vds) > 0 else np.nan)
    # rolling-std last ratio
    if len(wm) >= 12:
        rs = pd.Series(vdm).rolling(4, min_periods=3).std().values
        rs = rs[np.isfinite(rs)]
        f["vsi_rollstd4_last_ratio_w"] = (float(np.nanmean(rs[-4:]) / np.nanmean(rs))
                                          if len(rs) >= 8 and np.nanmean(rs) > 0 else np.nan)
    else:
        f["vsi_rollstd4_last_ratio_w"] = np.nan
    # winner 2: vsi_dominant_freq (within window)
    if len(wm) >= 10:
        seg = pd.Series(vdm).interpolate(limit_direction="both").values
        seg = seg - np.nanmean(seg)
        seg = np.where(np.isfinite(seg), seg, 0.0)
        fr, pw = signal.periodogram(seg, fs=1.0)
        f["vsi_dominant_freq_w"] = float(fr[np.argmax(pw)])
    else:
        f["vsi_dominant_freq_w"] = np.nan
    # winner 3: failed_crank_rate_last90 (events within window already last-90 anchored)
    es = ev[ev["succ_b"].notna()]
    e90 = es[es["days_before_t_end"] <= 90]
    f["failed_crank_rate_last90_w"] = (float((~e90["succ_b"].astype(bool)).mean())
                                       if len(e90) >= 10 else np.nan)
    # winner 4: vsi_range_trend (last 12 masked weeks — already window-limited)
    last12 = wm.tail(12).copy()
    rng = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
    f["vsi_range_trend_w"] = (theil_sen(rng, last12["week_x"].values.astype(float))
                              if np.isfinite(rng).sum() >= 6 else np.nan)
    # candidate: trend persistence (last 12 wks within window)
    if len(wm) >= 12:
        seg, sx = vdm[-12:], wm["week_x"].values[-12:]
        slopes = []
        for i in range(len(seg) - 3):
            yy, xx = seg[i:i+4], sx[i:i+4]
            mq = np.isfinite(yy)
            if mq.sum() >= 3:
                slopes.append(np.polyfit(xx[mq], yy[mq], 1)[0])
        f["vsi_trend_persistence_w"] = (abs(np.mean(np.sign(slopes)))
                                        if len(slopes) >= 5 else np.nan)
    else:
        f["vsi_trend_persistence_w"] = np.nan
    # candidate: below21 ratio within window
    b13, o13 = wm["vsi_below_21_rows"].tail(13).sum(), wm["vsi_obs_rows"].tail(13).sum()
    ball, oall = wm["vsi_below_21_rows"].sum(), wm["vsi_obs_rows"].sum()
    f["below21_rate_ratio_90_w"] = (float((b13/o13)/(ball/oall))
                                    if o13 > 0 and oall > 0 and ball > 0 else np.nan)
    rows.append(f)

tw = pd.DataFrame(rows)

ORIG = {
    "vsi_std_ratio_30d_w": ("vsi_std_ratio_30d", 0.8786),
    "vsi_dominant_freq_w": ("vsi_dominant_freq", 0.7482),
    "failed_crank_rate_last90_w": ("failed_crank_rate_last90", 0.7404),
    "vsi_range_trend_w": ("vsi_range_trend", 0.7321),
    "vsi_std_ratio_60d_w": ("vsi_std_ratio_60d [B2]", 0.9000),
    "vsi_std_ratio_90d_w": ("vsi_std_ratio_90d [B2]", 0.9750),
    "vsi_withinwk_std_ratio_30d_w": ("vsi_withinwk_std_ratio_30d [B2]", 0.9679),
    "vsi_rollstd4_last_ratio_w": ("vsi_rollstd4_last_ratio [B2]", 0.9357),
    "vsi_trend_persistence_w": ("vsi_trend_persistence [B2]", 0.7393),
    "below21_rate_ratio_90_w": ("below21_rate_ratio_90 [B2]", 0.7464),
}
out_rows = []
print("\nFIXED-WINDOW (last %d masked weeks) CONTROL — AUROC full-history vs windowed:" % L)
print(f"  {'feature':<36} {'AUROC_full':>10} {'AUROC_L40':>10} {'drop':>7}  verdict")
for col, (label, a_full) in ORIG.items():
    v = tw[col].values.astype(float)
    a = rank_auroc(v, y)
    a_o = max(a, 1 - a) if np.isfinite(a) else np.nan
    drop = a_full - a_o
    verdict = ("LENGTH-ARTIFACT" if drop >= 0.15 else
               "PARTIAL" if drop >= 0.07 else "SURVIVES")
    print(f"  {label:<36} {a_full:>10.4f} {a_o:>10.4f} {drop:>+7.4f}  {verdict}")
    out_rows.append({"feature": label, "auroc_full_history": a_full,
                     "auroc_fixed_window_L40": round(a_o, 4),
                     "drop": round(drop, 4), "verdict": verdict})
pd.DataFrame(out_rows).to_csv(OUT / "B3_truncation_control.csv", index=False)

# residual length signal inside the window basis
nwin = tw["n_wk_window"].values.astype(float)
a_n = rank_auroc(nwin, y)
print(f"\n  Residual: AUROC of n_weeks_in_window (capped at {L}) = {max(a_n,1-a_n):.3f} "
      f"(this is the floor any windowed feature could 'cheat' from)")
print("\nDone ->", OUT / "B3_truncation_control.csv")
