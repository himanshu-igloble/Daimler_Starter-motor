"""
V1_1_SM_horizon.py — Experiment X4: prequential horizon for the FINAL frozen model.

Adapts the working walk-back implementation (discovery/scripts/G3_prequential_horizon.py)
to the X2 frozen modal-winner 4-feature subset:
    f1 vsi_withinwk_std_ratio_30d_w   (B3 exact: mean weekly vsi_drive_std last 4 masked
                                       wks / mean over fixed L40 masked-week basis)
    f2 rest_vsi_p05_delta90           (mean vsi_rest_p05 last 13 masked wks minus
                                       L40-window baseline; battery-replacement step
                                       re-baseline kept — applied only if the E5 step
                                       week precedes the cut, i.e. causally knowable)
    f3 vsi_range_trend                (Theil-Sen of weekly p95-p05 drive VSI, last 12
                                       masked wks)
    f4 dip_depth_last90_delta         (mean dip_depth last 90 d minus L40-window
                                       baseline; SMA-dead cohort masked to NaN)

Feature code is copied VERBATIM from V1_1_SM_features.py (which executes the full X1
build on import, so it cannot be imported as a module); correctness is verified by an
exact k=0 reconciliation against the frozen matrix V1_1_SM_feature_matrix.csv.

Method (per task spec):
  For each offset k = 0..16 weeks, truncate every VIN's weekly cache AND events at its
  own cut = t_end - 7k days (t_end = max raw timestamp, the days_before_t_end anchor
  of the frozen matrix, from V1_SM_data_quality.csv). Recompute the 4 features causally
  on the truncated data (last-90-d / L40 / last-13-wk windows re-anchored at the cut).
  Then LOVO over usable trucks: median-impute (train medians) -> StandardScaler ->
  RidgeClassifier(alpha=1.0, random_state=42) on the FROZEN 4 features (no re-screening).
  Record AUROC(k) (+ bootstrap 95% CI, seed 42) and recall at the 18/20-specificity
  operating point (threshold = 3rd-largest NF OOF score; fire = strictly greater).
  Usability: trucks with < 8 masked weeks before the cut are dropped (all-VSI NaN),
  exactly as in G3; n_usable reported per k.

k* = largest k with AUROC >= 0.75 sustained from k=0 (monotone reading; blips noted).
Sanity: the curve MUST decay toward chance at large k (time-locking evidence); if it
does not, a LOUD suspected-leak flag is printed and written to the CSV header comment.

Output: STARTER MOTOR/V1.1/results/V1_1_SM_horizon_curve.csv
Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_horizon.py"
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT = ROOT / "V1.1" / "results"
L40 = 40
K_SPEC = 16          # spec range for the headline curve / k*
K_MAX = 26           # extended walk-back (G3 range) to adjudicate decay-to-chance:
                     # at k=16 the tail has not yet bottomed out (G3 reached chance
                     # ~k=20), so the leak check needs the longer horizon
AUROC_THR = 0.75
STEP_MIN_V, STEP_MIN_SNR = 0.5, 2.0          # V1_1_SM_features.py exact
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
FROZEN = ["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90",
          "vsi_range_trend", "dip_depth_last90_delta"]
RNG = np.random.default_rng(42)

# ── load (identical sources to V1_1_SM_features.py) ─────────────────────────
wk_all = pd.concat([pd.read_parquet(f) for f in
                    sorted((ROOT / "cache/weekly").glob("V1_SM_weekly_*.parquet"))],
                   ignore_index=True)
wk_all["week"] = pd.to_datetime(wk_all["week"])
ev_all = pd.read_parquet(ROOT / "cache/events/V1_SM_crank_events.parquet")
ev_all = ev_all[ev_all["artifact"] == False].copy()
ev_all["ts_start"] = pd.to_datetime(ev_all["ts_start"])
ev_all["ts_day"] = ev_all["ts_start"].dt.normalize()

fm_v1 = pd.read_csv(ROOT / "results" / "V1_SM_feature_matrix.csv")
vins = fm_v1["vin_label"].tolist()
y = fm_v1["failed"].astype(int).values

dq = pd.read_csv(ROOT / "results" / "V1_SM_data_quality.csv")
T_END = {r["vin_label"]: pd.to_datetime(r["t_end"])
         for _, r in dq.iterrows()}    # full precision: days_before_t_end anchor;
                                       # day-floor applied only in the 90-d arithmetic

steps = pd.read_csv(ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
steps["step_week"] = pd.to_datetime(steps["step_week"])
bat = steps[(steps["signal"] == "vsi_rest_median")
            & (steps["step_V"] >= STEP_MIN_V) & (steps["snr"] >= STEP_MIN_SNR)]
BAT_STEP = dict(zip(bat["vin_label"], bat["step_week"]))
print(f"Battery-replacement steps (E5): "
      f"{ {k: str(v.date()) for k, v in BAT_STEP.items()} }")

WK = {v: wk_all[(wk_all["vin_label"] == v) & (wk_all["active_days"] >= 2)]
      .sort_values("week").reset_index(drop=True) for v in vins}
EV = {v: ev_all[ev_all["vin_label"] == v].sort_values("ts_start") for v in vins}


def theil_sen(yv, xv):
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


def frozen_feats(vin, cut):
    """The 4 frozen X1 features computed only from data <= cut.
    Windows re-anchored at cut; code blocks verbatim from V1_1_SM_features.py
    with t_end -> cut. Returns dict + n masked weeks available."""
    wm = WK[vin][WK[vin]["week"] <= cut].tail(L40).reset_index(drop=True)
    f = {"n_wk": len(wm)}
    if len(wm) < 8:                       # G3 usability rule: all-VSI NaN
        f.update({k: np.nan for k in FROZEN})
        return f
    win_start = wm["week"].iloc[0]
    wm = wm.copy()
    wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
    vds = wm["vsi_drive_std"].values.astype(float)

    # f1 vsi_withinwk_std_ratio_30d_w (B3 exact)
    f["vsi_withinwk_std_ratio_30d_w"] = (
        float(np.nanmean(vds[-4:]) / np.nanmean(vds))
        if np.isfinite(vds).sum() >= 6 and np.nanmean(vds) > 0 else np.nan)

    # f3 vsi_range_trend (last 12 masked weeks)
    last12 = wm.tail(12)
    rng = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
    f["vsi_range_trend"] = (theil_sen(rng, last12["week_x"].values.astype(float))
                            if np.isfinite(rng).sum() >= 6 else np.nan)

    # f2 rest_vsi_p05_delta90 (battery-step-aware re-baseline; step used only
    # if its week precedes the cut — causally knowable at scoring time)
    vrp = wm["vsi_rest_p05"].values.astype(float)
    last13, base = vrp[-13:], vrp[:-13]
    base_weeks = wm["week"].values[:-13]
    if vin in BAT_STEP and pd.Timestamp(BAT_STEP[vin]) <= cut:
        post = base[base_weeks >= np.datetime64(BAT_STEP[vin])]
        if np.isfinite(post).sum() >= 4:
            base = post
    if np.isfinite(last13).sum() >= 6 and np.isfinite(base).sum() >= 4:
        f["rest_vsi_p05_delta90"] = float(np.nanmean(last13) - np.nanmean(base))
    else:
        f["rest_vsi_p05_delta90"] = np.nan

    # f4 dip_depth_last90_delta (cohort-masked; last-90d vs L40-window baseline,
    # day-floor arithmetic identical to days_before_t_end)
    if vin in SMA_DEAD:
        f["dip_depth_last90_delta"] = np.nan
    else:
        ev = EV[vin][EV[vin]["ts_start"] <= cut]
        dbc = (cut.normalize() - ev["ts_day"]).dt.days   # day-floor, matches
                                                         # days_before_t_end arithmetic
        e90 = ev[dbc <= 90]
        base_ev = ev[(ev["ts_start"] >= win_start) & (dbc > 90)]
        d90 = e90["dip_depth"].dropna()
        dbase = base_ev["dip_depth"].dropna()
        f["dip_depth_last90_delta"] = (float(d90.mean() - dbase.mean())
                                       if len(d90) >= 10 and len(dbase) >= 10
                                       else np.nan)
    return f


def rank_auroc(scores, labels):
    m = np.isfinite(scores)
    s, l = np.asarray(scores)[m], np.asarray(labels)[m]
    if l.sum() == 0 or (1 - l).sum() == 0:
        return np.nan
    pos, neg = s[l == 1], s[l == 0]
    return sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos) / (len(pos) * len(neg))


def lovo_ridge(F, labels):
    """LOVO: train-median impute -> StandardScaler -> RidgeClassifier(alpha=1.0)."""
    oof = np.zeros(len(labels))
    for i in range(len(labels)):
        tr = np.ones(len(labels), bool)
        tr[i] = False
        med = np.nanmedian(F[tr], axis=0)
        med = np.where(np.isfinite(med), med, 0.0)
        Ftr = np.where(np.isfinite(F[tr]), F[tr], med)
        Fte = np.where(np.isfinite(F[[i]]), F[[i]], med)
        sc = StandardScaler().fit(Ftr)
        m = RidgeClassifier(alpha=1.0, random_state=42).fit(sc.transform(Ftr), labels[tr])
        oof[i] = m.decision_function(sc.transform(Fte))[0]
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


def spec1820_recall(oof, labels):
    """Recall at the 18/20-specificity operating point: threshold = 3rd-largest
    NF OOF score (exactly 2 NF strictly above); recall = failed strictly above."""
    nf = np.sort(oof[labels == 0])
    if len(nf) < 3:
        return np.nan, np.nan
    thr = nf[-3]
    rec = float((oof[labels == 1] > thr).mean())
    spec = float((oof[labels == 0] <= thr).mean())
    return rec, spec


# ── k=0 reconciliation against the frozen X1 matrix ─────────────────────────
frozen_mat = pd.read_csv(OUT / "V1_1_SM_feature_matrix.csv")
rec0 = pd.DataFrame([{**{"vin_label": v}, **frozen_feats(v, T_END[v])} for v in vins])
print("\nk=0 reconciliation vs frozen V1_1_SM_feature_matrix.csv:")
ok = True
for c in FROZEN:
    a = rec0[c].values.astype(float)
    b = frozen_mat[c].values.astype(float)
    both = np.isfinite(a) & np.isfinite(b)
    nan_mismatch = int((np.isfinite(a) != np.isfinite(b)).sum())
    md = np.max(np.abs(a[both] - b[both])) if both.any() else 0.0
    flag = "OK" if (md < 1e-9 and nan_mismatch == 0) else "MISMATCH"
    ok &= flag == "OK"
    print(f"  {c:<32} max|diff|={md:.2e}  NaN-pattern mismatches={nan_mismatch}  {flag}")
if not ok:
    raise SystemExit("k=0 reconciliation FAILED — feature replication is not exact; abort.")

# ── prequential walk-back ────────────────────────────────────────────────────
print(f"\nPrequential walk-back, frozen 4-feature RidgeClassifier, k = 0..{K_MAX}")
rows = []
for k in range(K_MAX + 1):
    feats, nwk = [], []
    for v in vins:
        cut = T_END[v] - pd.Timedelta(days=7 * k)
        f = frozen_feats(v, cut)
        feats.append([f[c] for c in FROZEN])
        nwk.append(f["n_wk"])
    F = np.array(feats, float)
    usable = np.array([n >= 8 for n in nwk])
    if usable.sum() < 10 or y[usable].sum() < 4:
        print(f"  k={k:2d}: insufficient usable trucks ({usable.sum()}) — stop")
        break
    cov = np.isfinite(F[usable]).mean(axis=0)
    oof = lovo_ridge(F[usable], y[usable])
    a = rank_auroc(oof, y[usable])
    lo, hi = boot_ci(oof, y[usable])
    rec, spec = spec1820_recall(oof, y[usable])
    med_f = np.median(oof[y[usable] == 1])
    med_nf = np.median(oof[y[usable] == 0])
    rows.append({"k_weeks": k, "auroc": round(a, 4), "ci95_lo": round(lo, 4),
                 "ci95_hi": round(hi, 4),
                 "recall_at_spec1820": round(rec, 4),
                 "specificity_actual": round(spec, 4),
                 "n_usable": int(usable.sum()),
                 "n_failed_usable": int(y[usable].sum()),
                 "median_score_failed": round(med_f, 4),
                 "median_score_nf": round(med_nf, 4),
                 "median_separation": round(med_f - med_nf, 4),
                 "cov_f1_withinwk": round(cov[0], 2),
                 "cov_f2_restp05": round(cov[1], 2),
                 "cov_f3_rangetrend": round(cov[2], 2),
                 "cov_f4_dipdepth": round(cov[3], 2)})
    print(f"  k={k:2d}: AUROC={a:.3f} [{lo:.3f},{hi:.3f}]  recall@spec18/20={rec:.3f}  "
          f"sep={med_f - med_nf:+.3f}  usable={usable.sum()} (F={y[usable].sum()})  "
          f"cov={cov[0]:.2f}/{cov[1]:.2f}/{cov[2]:.2f}/{cov[3]:.2f}")

hc = pd.DataFrame(rows)
hc["in_spec_range"] = hc["k_weeks"] <= K_SPEC

# k* = largest k with AUROC >= thr sustained from k=0 (within spec range)
k_star = -1
for _, r in hc.iterrows():
    if r["auroc"] >= AUROC_THR:
        k_star = int(r["k_weeks"])
    else:
        break
blips = hc[(hc["k_weeks"] > k_star) & (hc["auroc"] >= AUROC_THR)]["k_weeks"].tolist()

# decay verdict on the EXTENDED tail (last 4 available offsets):
# (i) tail mean must sit near chance (< 0.65), (ii) head-tail drop > 0.15, and
# (iii) the tail bootstrap CIs must include 0.5 (no significant residual signal)
head = hc[hc["k_weeks"] <= 2]["auroc"].mean()
tail_df = hc.tail(4)
tail = tail_df["auroc"].mean()
tail_ci_chance = bool((tail_df["ci95_lo"] <= 0.5).all())
decays = bool(tail < 0.65 and (head - tail) > 0.15 and tail_ci_chance)
hc["k_star_sustained"] = k_star
hc["decay_head_mean"] = round(head, 4)
hc["decay_tail_mean"] = round(tail, 4)
hc["decay_confirmed"] = decays
hc.to_csv(OUT / "V1_1_SM_horizon_curve.csv", index=False)

print(f"\nSustained-AUROC>={AUROC_THR} horizon: k* = {k_star} weeks before t_end")
if blips:
    print(f"  (isolated blips >= {AUROC_THR} beyond k*: {blips} — not counted)")
kt = tail_df["k_weeks"].tolist()
print(f"Decay check: head mean (k<=2) = {head:.3f}, tail mean (k={kt[0]}..{kt[-1]}) = "
      f"{tail:.3f}, all tail CIs include 0.5: {tail_ci_chance}")
if decays:
    print("DECAY CONFIRMED — score is time-locked to failure (no leak signature).")
else:
    print("*** SUSPECTED LEAK *** — the horizon curve does NOT decay toward chance at "
          "large k. A genuinely prognostic score must lose signal when all data within "
          f"{kt[0]}+ weeks of failure is removed. Investigate before shipping.")
print("\nSaved ->", OUT / "V1_1_SM_horizon_curve.csv")
