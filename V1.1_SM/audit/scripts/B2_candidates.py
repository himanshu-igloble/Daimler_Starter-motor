"""
B2_candidates.py — Agent B, V1.1 feature audit, Part 2.
Builds ~24 NEW candidate features from existing caches (no raw-data passes),
screens each with MW p / oriented AUROC / Cohen's d / jackknife stability,
checks leakage (Spearman vs obs-length & epoch proxies) and redundancy
(Spearman vs the 4 V1 winners), then measures INCREMENTAL value via LOVO
RidgeClassifier (winners-4 + candidate) against the replicated 0.9214 baseline.

Also: mechanics check on vsi_dominant_freq (is it 1/n_weeks?) and a
fixed-window (last 24 masked weeks) dominant-freq deconfounded variant.

Outputs: STARTER MOTOR/V1.1/audit/out/B2_candidate_screening.csv,
         B2_incremental_lovo.csv
Run: py -3 B2_candidates.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats, signal
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "audit" / "out"
WINNERS = ["vsi_std_ratio_30d", "vsi_dominant_freq", "failed_crank_rate_last90", "vsi_range_trend"]
ALPHA, SEED = 1.0, 42

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


def theil_sen(yv, xv):
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


def rank_auroc(scores, labels):
    m = np.isfinite(scores)
    s, l = scores[m], labels[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))


def masked_weekly(vin):
    w = wk_all[wk_all["vin_label"] == vin]
    wm = w[w["active_days"] >= 2].sort_values("week").reset_index(drop=True)
    if len(wm):
        wm = wm.copy()
        wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
    return w, wm


# ── NF fleet age-matched baseline (vsi_drive_mean by masked-week ordinal) ────
# week index = ordinal position in the VIN's own masked-week series (age proxy)
nf_series = {}
for vin in vins:
    _, wm = masked_weekly(vin)
    nf_series[vin] = wm["vsi_drive_mean"].values.astype(float)
max_len = max(len(s) for s in nf_series.values())
nf_mat = np.full((sum(1 for v in vins if "_NF_" in v), max_len), np.nan)
ri = 0
nf_vin_order = []
for vin in vins:
    if "_NF_" in vin:
        s = nf_series[vin]
        nf_mat[ri, :len(s)] = s
        nf_vin_order.append(vin)
        ri += 1

# ── Candidate builder ────────────────────────────────────────────────────────
rows = []
domfreq_checks = []
for vin in vins:
    w, wm = masked_weekly(vin)
    ev = ev_all[ev_all["vin_label"] == vin]
    vdm = wm["vsi_drive_mean"].values.astype(float)
    wx = wm["week_x"].values.astype(float) if len(wm) else np.array([])
    f = {"vin_label": vin}

    # ---- TEMPORAL ----
    # C1 vsi_grad_last8: Theil-Sen slope of vsi_drive_mean over last 8 masked weeks
    f["vsi_grad_last8"] = theil_sen(vdm[-8:], wx[-8:]) if len(wm) >= 8 else np.nan

    # C2 vsi_trend_persistence: |mean sign| of rolling 4-wk OLS slopes in last 12 wks
    if len(wm) >= 12:
        seg, sx = vdm[-12:], wx[-12:]
        slopes = []
        for i in range(len(seg) - 3):
            yy, xx = seg[i:i + 4], sx[i:i + 4]
            m = np.isfinite(yy)
            if m.sum() >= 3:
                slopes.append(np.polyfit(xx[m], yy[m], 1)[0])
        f["vsi_trend_persistence"] = abs(np.mean(np.sign(slopes))) if len(slopes) >= 5 else np.nan
    else:
        f["vsi_trend_persistence"] = np.nan

    # C3 vsi_accel: mean of last 3 second-differences of monthly vsi_drive_mean
    if len(wm) >= 10:
        mon = wm.copy()
        mon["_m"] = mon["week"].dt.to_period("M")
        g = mon.groupby("_m")["vsi_drive_mean"].agg(["mean", "count"])
        g = g[g["count"] >= 2]
        if len(g) >= 5:
            d2 = np.diff(g["mean"].values.astype(float), 2)
            f["vsi_accel"] = float(np.mean(d2[-3:])) if len(d2) >= 3 else np.nan
        else:
            f["vsi_accel"] = np.nan
    else:
        f["vsi_accel"] = np.nan

    # C4 vsi_drive_mean_last60_delta
    if len(wm) >= 16:
        f["vsi_drive_mean_last60_delta"] = float(np.nanmean(vdm[-8:]) - np.nanmean(vdm[:-8]))
    else:
        f["vsi_drive_mean_last60_delta"] = np.nan

    # C5 vsi_rest_median_last90_delta
    vr = wm["vsi_rest_median"].values.astype(float)
    if len(wm) >= 21 and np.isfinite(vr[-13:]).sum() >= 6 and np.isfinite(vr[:-13]).sum() >= 6:
        f["vsi_rest_median_last90_delta"] = float(np.nanmean(vr[-13:]) - np.nanmean(vr[:-13]))
    else:
        f["vsi_rest_median_last90_delta"] = np.nan

    # C6-C8 event last-90d deltas
    e90 = ev[ev["days_before_t_end"] <= 90]
    epre = ev[ev["days_before_t_end"] > 90]
    f["crank_dur_last90_delta"] = (float(e90["dur_s"].mean() - epre["dur_s"].mean())
                                   if len(e90) >= 10 and len(epre) >= 10 else np.nan)
    mv90, mvp = e90["min_vsi_crank"].dropna(), epre["min_vsi_crank"].dropna()
    f["min_vsi_crank_p05_last90_delta"] = (float(np.percentile(mv90, 5) - np.percentile(mvp, 5))
                                           if len(mv90) >= 10 and len(mvp) >= 10 else np.nan)
    rs90, rsp = e90["recovery_slope"].dropna(), epre["recovery_slope"].dropna()
    f["recovery_slope_last90_delta"] = (float(rs90.mean() - rsp.mean())
                                        if len(rs90) >= 10 and len(rsp) >= 10 else np.nan)

    # C9 failed_crank_rate_last30 / last60 / delta90
    es = ev[ev["succ_b"].notna()]
    def fcr(sub, min_n):
        return float((~sub["succ_b"].astype(bool)).mean()) if len(sub) >= min_n else np.nan
    f["failed_crank_rate_last30"] = fcr(es[es["days_before_t_end"] <= 30], 5)
    f["failed_crank_rate_last60"] = fcr(es[es["days_before_t_end"] <= 60], 8)
    r90 = fcr(es[es["days_before_t_end"] <= 90], 10)
    rpre = fcr(es[es["days_before_t_end"] > 90], 10)
    f["failed_crank_rate_delta90"] = (r90 - rpre) if np.isfinite(r90) and np.isfinite(rpre) else np.nan

    # ---- STATISTICAL ----
    # C10 variance-of-variance: rolling 4-wk std series of vsi_drive_mean
    if len(wm) >= 12:
        rs_series = pd.Series(vdm).rolling(4, min_periods=3).std().values
        rs_series = rs_series[np.isfinite(rs_series)]
        if len(rs_series) >= 8 and np.nanmean(rs_series) > 0:
            f["vsi_vov_cv"] = float(np.nanstd(rs_series) / np.nanmean(rs_series))
            f["vsi_rollstd4_last_ratio"] = float(np.nanmean(rs_series[-4:]) / np.nanmean(rs_series))
        else:
            f["vsi_vov_cv"] = np.nan
            f["vsi_rollstd4_last_ratio"] = np.nan
    else:
        f["vsi_vov_cv"] = np.nan
        f["vsi_rollstd4_last_ratio"] = np.nan

    # C11 entropy of weekly vsi_drive_mean distribution (8 bins, own range)
    vv = vdm[np.isfinite(vdm)]
    if len(vv) >= 12 and vv.max() > vv.min():
        h, _ = np.histogram(vv, bins=8)
        p = h[h > 0] / h.sum()
        f["vsi_weekly_entropy"] = float(-(p * np.log(p)).sum() / np.log(8))
    else:
        f["vsi_weekly_entropy"] = np.nan

    # C12 dip-depth distribution shape
    dd = ev["dip_depth"].dropna().values
    f["dip_depth_skew"] = float(stats.skew(dd)) if len(dd) >= 30 else np.nan
    f["dip_depth_kurt"] = float(stats.kurtosis(dd)) if len(dd) >= 30 else np.nan
    f["crank_dur_cv"] = (float(ev["dur_s"].std() / ev["dur_s"].mean())
                         if len(ev) >= 30 and ev["dur_s"].mean() > 0 else np.nan)

    # C13 multi-window volatility ratios
    def std_ratio(last_n):
        if len(wm) < max(2 * last_n, 8):
            return np.nan
        sa = np.nanstd(vdm[np.isfinite(vdm)])
        sl_vals = vdm[-last_n:]
        sl_vals = sl_vals[np.isfinite(sl_vals)]
        if sa > 0 and len(sl_vals) >= 2:
            return float(np.nanstd(sl_vals) / sa)
        return np.nan
    f["vsi_std_ratio_60d"] = std_ratio(8)
    f["vsi_std_ratio_90d"] = std_ratio(13)

    # C14 within-week volatility ratio (weekly vsi_drive_std column)
    vds = wm["vsi_drive_std"].values.astype(float)
    if len(wm) >= 8 and np.isfinite(vds).sum() >= 6 and np.nanmean(vds) > 0:
        f["vsi_withinwk_std_ratio_30d"] = float(np.nanmean(vds[-4:]) / np.nanmean(vds))
    else:
        f["vsi_withinwk_std_ratio_30d"] = np.nan

    # ---- HEALTH INDICES ----
    # C15 composite crank health (higher = healthier)
    f["crank_health_last90"] = ((1.0 - r90) * float(rs90.mean())
                                if np.isfinite(r90) and len(rs90) >= 10 else np.nan)
    # C16 battery proxies
    vrp = wm["vsi_rest_p05"].values.astype(float)
    f["vsi_rest_p05_trend"] = theil_sen(vrp, wx)
    if len(wm) >= 21 and np.isfinite(vrp[-13:]).sum() >= 6 and np.isfinite(vrp[:-13]).sum() >= 6:
        f["vsi_rest_p05_last90_delta"] = float(np.nanmean(vrp[-13:]) - np.nanmean(vrp[:-13]))
    else:
        f["vsi_rest_p05_last90_delta"] = np.nan
    # C17 duty: SMA-active rows per active day, last 90d and ratio to lifetime
    sma13, ad13 = wm["sma1_rows"].tail(13).sum(), wm["active_days"].tail(13).sum()
    sma_all, ad_all = wm["sma1_rows"].sum(), wm["active_days"].sum()
    f["sma_duty_last90"] = float(sma13 / ad13) if ad13 > 0 else np.nan
    f["sma_duty_ratio_90"] = (float((sma13 / ad13) / (sma_all / ad_all))
                              if ad13 > 0 and ad_all > 0 and sma_all > 0 else np.nan)
    # C18 severe-low-voltage rate change
    b13, o13 = wm["vsi_below_21_rows"].tail(13).sum(), wm["vsi_obs_rows"].tail(13).sum()
    ball, oall = wm["vsi_below_21_rows"].sum(), wm["vsi_obs_rows"].sum()
    if o13 > 0 and oall > 0 and ball > 0:
        f["below21_rate_ratio_90"] = float((b13 / o13) / (ball / oall))
    else:
        f["below21_rate_ratio_90"] = np.nan

    # ---- FLEET-RELATIVE (age-normalized; label-dependent baseline -> flag) ----
    if len(vdm) >= 13:
        zs = []
        for k in range(len(vdm) - 13, len(vdm)):
            if not np.isfinite(vdm[k]) or k >= max_len:
                continue
            col = nf_mat[:, k]
            if vin in nf_vin_order:
                col = np.delete(col, nf_vin_order.index(vin))
            col = col[np.isfinite(col)]
            if len(col) >= 5 and np.std(col) > 0:
                zs.append((vdm[k] - np.median(col)) / np.std(col))
        f["vsi_drive_zage_last90"] = float(np.mean(zs)) if len(zs) >= 6 else np.nan
        f["vsi_drive_zage_abs_last90"] = float(np.mean(np.abs(zs))) if len(zs) >= 6 else np.nan
    else:
        f["vsi_drive_zage_last90"] = np.nan
        f["vsi_drive_zage_abs_last90"] = np.nan

    # ---- DOMFREQ DECONFOUND: fixed 24-masked-week window ----
    if len(wm) >= 24:
        seg = pd.Series(vdm[-24:]).interpolate(limit_direction="both").values
        seg = seg - np.nanmean(seg)
        seg = np.where(np.isfinite(seg), seg, 0.0)
        fr, pw = signal.periodogram(seg, fs=1.0)
        f["vsi_dominant_freq_fix24"] = float(fr[np.argmax(pw)])
    else:
        f["vsi_dominant_freq_fix24"] = np.nan

    # domfreq mechanics check data
    n_mask = len(wm)
    domfreq_checks.append({
        "vin_label": vin, "n_weeks_masked": n_mask,
        "inv_n": 1.0 / n_mask if n_mask else np.nan,
        "domfreq_v1": fm.loc[fm["vin_label"] == vin, "vsi_dominant_freq"].iloc[0],
    })
    rows.append(f)

cand = pd.DataFrame(rows)
CANDS = [c for c in cand.columns if c != "vin_label"]
assert list(cand["vin_label"]) == vins

# ── domfreq mechanics check ──────────────────────────────────────────────────
dfc = pd.DataFrame(domfreq_checks)
m = np.isfinite(dfc["domfreq_v1"])
r_inv, _ = stats.spearmanr(dfc.loc[m, "domfreq_v1"], dfc.loc[m, "inv_n"])
is_lowest_bin = np.isclose(dfc.loc[m, "domfreq_v1"], dfc.loc[m, "inv_n"], rtol=0.02)
print("=" * 78)
print("DOMFREQ MECHANICS CHECK (is vsi_dominant_freq a 1/series-length artifact?)")
print("=" * 78)
print(f"  Spearman r(vsi_dominant_freq, 1/n_weeks_masked) = {r_inv:+.3f}")
print(f"  VINs whose dominant freq == lowest periodogram bin (1/n): "
      f"{int(is_lowest_bin.sum())}/{int(m.sum())}")
a_inv = rank_auroc(dfc["inv_n"].values.astype(float), y)
print(f"  AUROC of 1/n_weeks_masked alone: {max(a_inv, 1-a_inv):.3f}")

# ── proxies (recompute as in B1) ─────────────────────────────────────────────
proxy_rows = []
for vin in vins:
    w, wm = masked_weekly(vin)
    proxy_rows.append({
        "n_weeks_masked": len(wm),
        "active_days_total": int(w["active_days"].sum()),
        "t_start_ord": w["week"].min().toordinal(),
        "t_end_ord": w["week"].max().toordinal(),
        "span_days": (w["week"].max() - w["week"].min()).days,
    })
px = pd.DataFrame(proxy_rows)
PROXIES = list(px.columns)

# ── screening ────────────────────────────────────────────────────────────────
LABEL_DEP = {"vsi_drive_zage_last90", "vsi_drive_zage_abs_last90"}
scr = []
for c in CANDS:
    v = cand[c].values.astype(float)
    mok = np.isfinite(v)
    n_f, n_nf = int(mok[y == 1].sum()), int(mok[y == 0].sum())
    if n_f < 5 or n_nf < 5:
        scr.append({"feature": c, "n_nonnull": int(mok.sum()), "note": "too sparse"})
        continue
    a_raw = rank_auroc(v, y)
    a = max(a_raw, 1 - a_raw)
    direction = "higher_in_failed" if a_raw >= 0.5 else "lower_in_failed"
    mwp = stats.mannwhitneyu(v[mok & (y == 1)], v[mok & (y == 0)]).pvalue
    s1, s0 = v[mok & (y == 1)], v[mok & (y == 0)]
    sp = np.sqrt(((len(s1)-1)*s1.std(ddof=1)**2 + (len(s0)-1)*s0.std(ddof=1)**2) / (len(s1)+len(s0)-2))
    d = (s1.mean() - s0.mean()) / sp if sp > 0 else np.nan
    # jackknife stability: fraction of 34 folds with oriented AUROC >= 0.70
    jk = []
    for i in range(len(y)):
        mm = np.ones(len(y), bool); mm[i] = False
        aa = rank_auroc(v[mm], y[mm])
        jk.append(max(aa, 1 - aa) if np.isfinite(aa) else np.nan)
    stab = float(np.mean(np.array(jk) >= 0.70))
    # redundancy vs winners
    wcorr = {}
    for wf in WINNERS:
        wv = fm[wf].values.astype(float)
        mm = mok & np.isfinite(wv)
        wcorr[wf] = stats.spearmanr(v[mm], wv[mm])[0] if mm.sum() >= 6 else np.nan
    max_w = max(abs(x) for x in wcorr.values() if np.isfinite(x))
    # leakage proxies
    pcorr = {}
    for p in PROXIES:
        mm = mok
        pcorr[p] = stats.spearmanr(v[mm], px[p].values[mm])[0]
    max_p = max(abs(x) for x in pcorr.values() if np.isfinite(x))
    leak = "LABEL_DEP" if c in LABEL_DEP else ("PROXY>=0.5" if max_p >= 0.5 else
                                               ("watch(0.4)" if max_p >= 0.4 else "ok"))
    scr.append({
        "feature": c, "n_nonnull": int(mok.sum()), "mw_p": round(mwp, 5),
        "auroc": round(a, 4), "direction": direction, "cohens_d": round(d, 3),
        "jk_stable_frac@0.70": round(stab, 3),
        "max_abs_r_winners": round(max_w, 3),
        "r_vsi_std_ratio_30d": round(wcorr["vsi_std_ratio_30d"], 3),
        "r_vsi_dominant_freq": round(wcorr["vsi_dominant_freq"], 3),
        "r_fcr_last90": round(wcorr["failed_crank_rate_last90"], 3),
        "r_vsi_range_trend": round(wcorr["vsi_range_trend"], 3),
        "max_abs_r_proxy": round(max_p, 3),
        "worst_proxy": max(pcorr, key=lambda k: abs(pcorr[k]) if np.isfinite(pcorr[k]) else -1),
        "leak_flag": leak,
        "note": "",
    })
scr_df = pd.DataFrame(scr).sort_values("auroc", ascending=False)
scr_df.to_csv(OUT / "B2_candidate_screening.csv", index=False)
print("\n" + "=" * 78)
print("CANDIDATE SCREENING (sorted by oriented AUROC)")
print("=" * 78)
with pd.option_context("display.width", 220, "display.max_columns", 50):
    print(scr_df.to_string(index=False))

# ── incremental LOVO ridge ───────────────────────────────────────────────────
def lovo_ridge(Xr, yy):
    n = len(yy)
    probs = np.full(n, np.nan)
    for i in range(n):
        tr = np.concatenate([np.arange(0, i), np.arange(i + 1, n)])
        Xtr, Xte = Xr[tr].copy(), Xr[i:i+1].copy()
        for j in range(Xtr.shape[1]):
            med = np.nanmedian(Xtr[:, j])
            med = 0.0 if np.isnan(med) else med
            Xtr[np.isnan(Xtr[:, j]), j] = med
            Xte[np.isnan(Xte[:, j]), j] = med
        sc = StandardScaler().fit(Xtr)
        mdl = RidgeClassifier(alpha=ALPHA, random_state=SEED).fit(sc.transform(Xtr), yy[tr])
        z = mdl.decision_function(sc.transform(Xte))[0]
        probs[i] = 1.0 / (1.0 + np.exp(-z)) if z >= 0 else np.exp(z) / (1.0 + np.exp(z))
    return probs

from sklearn.metrics import roc_auc_score
Xw = fm[WINNERS].values.astype(float)
base_p = lovo_ridge(Xw, y)
base_auc = roc_auc_score(y, base_p)
i_v8 = vins.index("VIN8_F_SM")
print("\n" + "=" * 78)
print(f"BASELINE REPLICATION: winners-4 LOVO AUROC = {base_auc:.4f} (V1 reported 0.9214)")
print(f"  VIN8_F_SM baseline LOVO prob = {base_p[i_v8]:.4f}")
print("=" * 78)

inc_rows = []
test_set = scr_df[(scr_df["auroc"].astype(float) >= 0.62) & scr_df["mw_p"].notna()]["feature"].tolist()
for c in test_set:
    Xc = np.column_stack([Xw, cand[c].values.astype(float)])
    p5 = lovo_ridge(Xc, y)
    auc5 = roc_auc_score(y, p5)
    inc_rows.append({
        "candidate": c,
        "auroc_5feat": round(auc5, 4),
        "delta_vs_base": round(auc5 - base_auc, 4),
        "vin8_prob": round(p5[i_v8], 4),
        "vin8_delta": round(p5[i_v8] - base_p[i_v8], 4),
        "leak_flag": scr_df.loc[scr_df["feature"] == c, "leak_flag"].iloc[0],
    })
inc_df = pd.DataFrame(inc_rows).sort_values("auroc_5feat", ascending=False)
inc_df.to_csv(OUT / "B2_incremental_lovo.csv", index=False)
print("\nINCREMENTAL LOVO (winners-4 + candidate):")
print(inc_df.to_string(index=False))

# VIN8 values for top candidates
print("\nVIN8_F_SM candidate values (fleet percentile):")
for c in test_set:
    v = cand[c].values.astype(float)
    val = v[i_v8]
    if np.isfinite(val):
        mm = np.isfinite(v)
        pct = 100.0 * (v[mm] < val).mean()
        print(f"  {c:<32} = {val:+.4f}  ({pct:.0f}th pctile)")
    else:
        print(f"  {c:<32} = NaN")

cand.to_csv(OUT / "B2_candidate_matrix.csv", index=False)
print("\nDone. Outputs in", OUT)
