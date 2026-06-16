"""
V1_1_SM_features.py — Experiment X1: build the V1.1 candidate feature matrix
(one row per VIN, 34 trucks) + mandatory admissibility audit (spec section 2).

Pool (10 candidates):
  1. vsi_std_ratio_30d_L40        between-week VSI volatility ratio, fixed L40 basis
                                  (B3's vsi_std_ratio_30d_w: std of vsi_drive_mean over
                                  last 4 masked wks / std over last-40-masked-week window)
  2. vsi_withinwk_std_ratio_30d_w within-week VSI noise ratio, L40 basis (B3 exact:
                                  mean weekly vsi_drive_std last 4 wks / mean over L40)
  3. vsi_range_trend              Theil-Sen of weekly (p95-p05) drive VSI, last 12 masked
                                  wks (V1 carry-over, recomputed; window-limited by constr.)
  4. vsi_trend_persistence        |mean sign| of rolling 4-wk OLS slopes of vsi_drive_mean,
                                  last 12 masked wks (B2 exact definition)
  5. failed_crank_rate_last90     share success==False among success-known non-artifact
                                  events, last 90 d (V1 carry-over; cohort-masked)
  6. retry_burst_rate_last90      burst episodes (>=2 events within 10 min, no intervening
                                  rpm_max_15s>=550 success) per active day, last 90 d
                                  (cohort-masked)
  7. extended_crank_tail_rate_last90  P(event n_rows>=2) last 90 d MINUS same share over
                                  the L40-window baseline (events >90 d); cohort-masked
  8. first_crank_fail_rate_last90 among first cranks after >=6 h event silence, share
                                  success==False, last 90 d (cohort-masked)
  9. rest_vsi_p05_delta90         mean weekly vsi_rest_p05 last 13 masked wks MINUS
                                  baseline mean (L40 window minus last 13; re-baselined
                                  after detected battery-replacement step, E5: rest-VSI
                                  step >= +0.5 V, SNR >= 2)
 10. dip_depth_last90_delta       mean dip_depth last 90 d minus L40-window baseline mean
                                  (non-artifact events; cohort-masked)

Interpretation note on #1: the task wording for vsi_std_ratio_30d_L40 ("mean weekly
vsi_drive_std ...") would duplicate #2 verbatim; spec section 1 defines #1 as the
"fixed-basis redefinition" of the V1 winner vsi_std_ratio_30d, which is the BETWEEN-week
volatility ratio. We therefore use Agent B's B3 definition (vsi_std_ratio_30d_w).

Cohort masking: SMA-dead trucks (sma_obs_rows/n_rows <= 1% over full history) get NaN on
all crank/SMA features (5,6,7,8,10); imputation happens fold-internally in X2, never here.

Admissibility audit (spec 2.3): per feature — Spearman r vs n_weeks_masked / t_start
ordinal / span_days; oriented AUROC raw AND under the fixed-L40 control (every VIN
clipped to its last 40 masked weeks before recomputation). REJECT iff max|r_proxy| > 0.5
AND L40 drop > 0.05.

Outputs:
  STARTER MOTOR/V1.1/results/V1_1_SM_feature_matrix.csv
  STARTER MOTOR/V1.1/results/V1_1_SM_feature_matrix_L40control.csv
  STARTER MOTOR/V1.1/results/V1_1_SM_feature_admissibility.csv

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_features.py"
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "results"
OUT.mkdir(parents=True, exist_ok=True)
L40 = 40                      # fixed masked-week basis
SMA_DEAD_THRESH = 0.01        # sma_obs_rows / n_rows over full history
BURST_GAP_S = 600             # 10 min
BURST_RPM_OK = 550            # intervening success = rpm_max_15s >= 550
FIRST_CRANK_REST_H = 6
STEP_MIN_V, STEP_MIN_SNR = 0.5, 2.0

fm_v1 = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
vins = fm_v1["vin_label"].tolist()
y = fm_v1["failed"].astype(int).values

wk_all = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "cache/weekly").glob("V1_SM_weekly_*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev_all = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev_all = ev_all[ev_all["artifact"] == False].copy()
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
ev_all["succ_b"] = ev_all["success"].map(lambda x: bool(x) if x is not None and x == x else np.nan)

# Battery-replacement step detections (Agent E, E5): rest-VSI step up >= +0.5 V, SNR >= 2
steps = pd.read_csv(ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
steps["step_week"] = pd.to_datetime(steps["step_week"])
bat_steps = steps[(steps["signal"] == "vsi_rest_median")
                  & (steps["step_V"] >= STEP_MIN_V) & (steps["snr"] >= STEP_MIN_SNR)]
BAT_STEP = dict(zip(bat_steps["vin_label"], bat_steps["step_week"]))
print(f"Battery-replacement steps (E5, >=+{STEP_MIN_V} V, SNR>={STEP_MIN_SNR}): "
      f"{ {k: str(v.date()) for k, v in BAT_STEP.items()} }")

# SMA-dead config cohort
sma_dead = {}
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    frac = w["sma_obs_rows"].sum() / max(w["n_rows"].sum(), 1)
    sma_dead[vin] = frac <= SMA_DEAD_THRESH
DEAD = sorted([v for v, d in sma_dead.items() if d])
print(f"SMA-dead cohort ({len(DEAD)}): {DEAD}")

COHORT_MASKED = ["failed_crank_rate_last90", "retry_burst_rate_last90",
                 "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
                 "dip_depth_last90_delta"]
FEATURES = ["vsi_std_ratio_30d_L40", "vsi_withinwk_std_ratio_30d_w", "vsi_range_trend",
            "vsi_trend_persistence", "failed_crank_rate_last90", "retry_burst_rate_last90",
            "extended_crank_tail_rate_last90", "first_crank_fail_rate_last90",
            "rest_vsi_p05_delta90", "dip_depth_last90_delta"]


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


def burst_count(ev_sub):
    """Count burst episodes: maximal chains of events with consecutive gaps <= 10 min,
    >=2 events, where no event before the last in the chain reached rpm_max_15s >= 550."""
    if len(ev_sub) < 2:
        return 0
    e = ev_sub.sort_values("ts_start")
    ts = e["ts_start"].values
    rpm = e["rpm_max_15s"].values.astype(float)
    bursts = 0
    chain = [0]
    for i in range(1, len(e)):
        if (ts[i] - ts[i - 1]) / np.timedelta64(1, "s") <= BURST_GAP_S:
            chain.append(i)
        else:
            if len(chain) >= 2:
                inter = rpm[chain[:-1]]
                if not np.any(inter[np.isfinite(inter)] >= BURST_RPM_OK):
                    bursts += 1
            chain = [i]
    if len(chain) >= 2:
        inter = rpm[chain[:-1]]
        if not np.any(inter[np.isfinite(inter)] >= BURST_RPM_OK):
            bursts += 1
    return bursts


def build_features(clip_l40_basis: bool):
    """Build the 10-feature row per VIN.
    clip_l40_basis=False -> production matrix (features are already L40/window-anchored
      by definition; full weekly history used only to locate the L40 window and t_end).
    clip_l40_basis=True  -> fixed-L40 control: EVERY computation restricted to each
      VIN's last 40 masked weeks (weekly rows AND events clipped to the window span)."""
    rows = []
    for vin in vins:
        w = wk_all[wk_all["vin_label"] == vin]
        wm_full = w[w["active_days"] >= 2].sort_values("week").reset_index(drop=True)
        wm = wm_full.tail(L40).reset_index(drop=True)           # L40 basis (always)
        win_start = wm["week"].iloc[0]
        ev_vin = ev_all[ev_all["vin_label"] == vin]
        if clip_l40_basis:
            ev_vin = ev_vin[ev_vin["ts_start"] >= win_start]
        ev_win = ev_vin[ev_vin["ts_start"] >= win_start]        # L40-window events
        wm = wm.copy()
        wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
        vdm = wm["vsi_drive_mean"].values.astype(float)
        vds = wm["vsi_drive_std"].values.astype(float)
        f = {"vin_label": vin, "failed": int(y[vins.index(vin)])}

        # 1. vsi_std_ratio_30d_L40 (B3 exact)
        va = vdm[np.isfinite(vdm)]
        l4 = vdm[-4:]; l4 = l4[np.isfinite(l4)]
        f["vsi_std_ratio_30d_L40"] = (float(np.std(l4) / np.std(va))
                                      if len(va) >= 2 and len(l4) >= 2
                                      and np.std(va) > 0 and np.std(l4) > 0 else np.nan)

        # 2. vsi_withinwk_std_ratio_30d_w (B3 exact)
        f["vsi_withinwk_std_ratio_30d_w"] = (float(np.nanmean(vds[-4:]) / np.nanmean(vds))
                                             if np.isfinite(vds).sum() >= 6
                                             and np.nanmean(vds) > 0 else np.nan)

        # 3. vsi_range_trend (V1 carry-over, last 12 masked weeks)
        last12 = wm.tail(12)
        rng = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
        f["vsi_range_trend"] = (theil_sen(rng, last12["week_x"].values.astype(float))
                                if np.isfinite(rng).sum() >= 6 else np.nan)

        # 4. vsi_trend_persistence (B2 exact, last 12 masked weeks)
        if len(wm) >= 12:
            seg, sx = vdm[-12:], wm["week_x"].values[-12:]
            slopes = []
            for i in range(len(seg) - 3):
                yy, xx = seg[i:i + 4], sx[i:i + 4]
                mq = np.isfinite(yy)
                if mq.sum() >= 3:
                    slopes.append(np.polyfit(xx[mq], yy[mq], 1)[0])
            f["vsi_trend_persistence"] = (abs(np.mean(np.sign(slopes)))
                                          if len(slopes) >= 5 else np.nan)
        else:
            f["vsi_trend_persistence"] = np.nan

        # ---- event features (cohort-masked) ----
        es = ev_vin[ev_vin["succ_b"].notna()]
        e90s = es[es["days_before_t_end"] <= 90]
        e90 = ev_vin[ev_vin["days_before_t_end"] <= 90]

        # 5. failed_crank_rate_last90 (V1 def: >=10 success-known events)
        f["failed_crank_rate_last90"] = (float((~e90s["succ_b"].astype(bool)).mean())
                                         if len(e90s) >= 10 else np.nan)

        # 6. retry_burst_rate_last90 (bursts per active day, last 90 d)
        ref_week = wm_full["week"].max()
        w_act = w[w["week"] > ref_week - pd.Timedelta(days=91)]
        act90 = float(w_act["active_days"].sum())
        f["retry_burst_rate_last90"] = (burst_count(e90) / act90
                                        if act90 >= 10 else np.nan)

        # 7. extended_crank_tail_rate_last90 (last-90d share minus L40 baseline >90 d)
        base_ev = ev_win[ev_win["days_before_t_end"] > 90]
        if len(e90) >= 10 and len(base_ev) >= 10:
            f["extended_crank_tail_rate_last90"] = float(
                (e90["n_rows"] >= 2).mean() - (base_ev["n_rows"] >= 2).mean())
        else:
            f["extended_crank_tail_rate_last90"] = np.nan

        # 8. first_crank_fail_rate_last90 (first crank after >=6 h event silence)
        ee = ev_vin.sort_values("ts_start")
        gap_h = ee["ts_start"].diff().dt.total_seconds() / 3600.0
        is_first = gap_h.isna() | (gap_h >= FIRST_CRANK_REST_H)
        fc = ee[is_first & (ee["days_before_t_end"] <= 90) & ee["succ_b"].notna()]
        f["first_crank_fail_rate_last90"] = (float((~fc["succ_b"].astype(bool)).mean())
                                             if len(fc) >= 5 else np.nan)

        # 9. rest_vsi_p05_delta90 (battery-step-aware re-baseline)
        vrp = wm["vsi_rest_p05"].values.astype(float)
        last13, base = vrp[-13:], vrp[:-13]
        base_weeks = wm["week"].values[:-13]
        if vin in BAT_STEP:
            post = base[base_weeks >= np.datetime64(BAT_STEP[vin])]
            if np.isfinite(post).sum() >= 4:
                base = post
        if np.isfinite(last13).sum() >= 6 and np.isfinite(base).sum() >= 4:
            f["rest_vsi_p05_delta90"] = float(np.nanmean(last13) - np.nanmean(base))
        else:
            f["rest_vsi_p05_delta90"] = np.nan

        # 10. dip_depth_last90_delta (vs L40-window baseline)
        d90 = e90["dip_depth"].dropna()
        dbase = base_ev["dip_depth"].dropna()
        f["dip_depth_last90_delta"] = (float(d90.mean() - dbase.mean())
                                       if len(d90) >= 10 and len(dbase) >= 10 else np.nan)

        # cohort mask
        if sma_dead[vin]:
            for c in COHORT_MASKED:
                f[c] = np.nan
        rows.append(f)
    return pd.DataFrame(rows)


mat = build_features(clip_l40_basis=False)
mat_ctl = build_features(clip_l40_basis=True)
mat.to_csv(OUT / "V1_1_SM_feature_matrix.csv", index=False)
mat_ctl.to_csv(OUT / "V1_1_SM_feature_matrix_L40control.csv", index=False)

# sanity: carry-overs must match the V1 matrix where definitions coincide
for col in ["vsi_range_trend", "failed_crank_rate_last90"]:
    a, b = mat[col].values.astype(float), fm_v1[col].values.astype(float)
    live = ~np.array([sma_dead[v] for v in vins]) if col in COHORT_MASKED else np.ones(34, bool)
    mm = np.isfinite(a) & np.isfinite(b) & live
    print(f"carry-over check {col}: max|diff| vs V1 matrix = "
          f"{np.max(np.abs(a[mm]-b[mm])):.2e} on {mm.sum()} VINs")

# ── admissibility audit ──────────────────────────────────────────────────────
proxy_rows = []
for vin in vins:
    w = wk_all[wk_all["vin_label"] == vin]
    wmf = w[w["active_days"] >= 2]
    proxy_rows.append({"n_weeks_masked": len(wmf),
                       "t_start_ord": w["week"].min().toordinal(),
                       "span_days": (w["week"].max() - w["week"].min()).days})
px = pd.DataFrame(proxy_rows)

audit_rows = []
print(f"\n{'feature':<34}{'AUROC':>7}{'L40':>7}{'drop':>8}{'r_nwk':>8}{'r_tst':>8}{'r_span':>8}  verdict")
for c in FEATURES:
    v = mat[c].values.astype(float)
    vc = mat_ctl[c].values.astype(float)
    mok = np.isfinite(v)
    a_raw = rank_auroc(v, y); a = max(a_raw, 1 - a_raw)
    ac_raw = rank_auroc(vc, y); ac = max(ac_raw, 1 - ac_raw) if np.isfinite(ac_raw) else np.nan
    drop = a - ac if np.isfinite(ac) else np.nan
    mwp = stats.mannwhitneyu(v[mok & (y == 1)], v[mok & (y == 0)]).pvalue \
        if mok[y == 1].sum() >= 3 and mok[y == 0].sum() >= 3 else np.nan
    rs = {}
    for p in ["n_weeks_masked", "t_start_ord", "span_days"]:
        pv = px[p].values.astype(float)
        mm = mok & np.isfinite(pv)
        rs[p] = stats.spearmanr(v[mm], pv[mm])[0] if mm.sum() >= 6 else np.nan
    max_p = max(abs(x) for x in rs.values() if np.isfinite(x))
    fail = bool(max_p > 0.5 and np.isfinite(drop) and drop > 0.05)
    verdict = "REJECT" if fail else ("watch" if max_p > 0.4 else "PASS")
    audit_rows.append({
        "feature": c, "n_nonnull": int(mok.sum()),
        "cohort_masked": c in COHORT_MASKED, "mw_p": round(mwp, 5),
        "auroc_raw": round(a, 4), "auroc_L40_control": round(ac, 4),
        "l40_drop": round(drop, 4) if np.isfinite(drop) else np.nan,
        "r_n_weeks": round(rs["n_weeks_masked"], 3),
        "r_t_start": round(rs["t_start_ord"], 3),
        "r_span_days": round(rs["span_days"], 3),
        "max_abs_r_proxy": round(max_p, 3),
        "admissible": not fail, "verdict": verdict})
    print(f"{c:<34}{a:>7.3f}{ac:>7.3f}{drop:>+8.4f}{rs['n_weeks_masked']:>+8.3f}"
          f"{rs['t_start_ord']:>+8.3f}{rs['span_days']:>+8.3f}  {verdict}")

aud = pd.DataFrame(audit_rows)
aud.to_csv(OUT / "V1_1_SM_feature_admissibility.csv", index=False)
admissible = aud[aud["admissible"]]["feature"].tolist()
print(f"\nAdmissible pool ({len(admissible)}/{len(FEATURES)}): {admissible}")
dropped = aud[~aud["admissible"]]["feature"].tolist()
if dropped:
    print(f"REJECTED: {dropped}")
print(f"\nSaved: {OUT / 'V1_1_SM_feature_matrix.csv'}")
