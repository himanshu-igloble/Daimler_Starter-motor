"""
H_walking_scores.py — V2 Heuristic Intelligence Layer: Walking Score Engine
============================================================================
Computes per-VIN per-k LOVO decision values and probability tiers for the
heuristics backtest (H1-H5).

Approach:
- Replicates V1_1_SM_horizon.py machinery (no import — no main-guard).
- For each k=0..26, runs 34-fold LOVO Ridge on the 4 frozen features at each
  truncation cut = t_end - 7k days.
- Saves per-VIN per-k decision values (walking_scores.csv) with probability
  mapped through k=0 Platt sigmoid + tier labels.
  SIMPLIFICATION NOTE: per-cut Platt calibration would require >34 inner-OOF
  scores per training fold — not available here. We therefore fit one Platt
  sigmoid at k=0 using the 34 LOVO decision values and apply it unchanged at
  all k. This is an approximation; results at large k (where the score
  distribution shifts) may have miscalibrated probabilities but tier assignments
  are anchored to GREEN<0.35<=AMBER<0.55<=RED.

Outputs:
  STARTER MOTOR/V2_program/analysis/heuristics/out/walking_scores.csv
    columns: vin_label, k_weeks, cut_date, decision_value, prob, tier, label,
             n_wk, usable

Run: py -3 "STARTER MOTOR/V2_program/analysis/heuristics/H_walking_scores.py"
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats, special
from sklearn.linear_model import RidgeClassifier, LogisticRegression
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR")
OUT_DIR = ROOT / "V2_program" / "analysis" / "heuristics" / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

L40 = 40
K_MAX = 26
STEP_MIN_V, STEP_MIN_SNR = 0.5, 2.0
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM",
            "VIN12_NF_SM", "VIN13_NF_SM", "VIN20_NF_SM"}
FROZEN = ["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90",
          "vsi_range_trend", "dip_depth_last90_delta"]
TIER_THRESHOLDS = (0.35, 0.55)   # GREEN < 0.35 <= AMBER < 0.55 <= RED
RNG = np.random.default_rng(42)

# ── load data (identical to V1_1_SM_horizon.py) ─────────────────────────────
print("Loading weekly cache and events...")
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
         for _, r in dq.iterrows()}

steps = pd.read_csv(ROOT / "V1.1" / "discovery" / "out" / "E5_step_changes_all.csv")
steps["step_week"] = pd.to_datetime(steps["step_week"])
bat = steps[(steps["signal"] == "vsi_rest_median")
            & (steps["step_V"] >= STEP_MIN_V) & (steps["snr"] >= STEP_MIN_SNR)]
BAT_STEP = dict(zip(bat["vin_label"], bat["step_week"]))

WK = {v: wk_all[(wk_all["vin_label"] == v) & (wk_all["active_days"] >= 2)]
      .sort_values("week").reset_index(drop=True) for v in vins}
EV = {v: ev_all[ev_all["vin_label"] == v].sort_values("ts_start") for v in vins}


def theil_sen(yv, xv):
    m = np.isfinite(yv) & np.isfinite(xv)
    if m.sum() < 4:
        return np.nan
    return float(stats.theilslopes(yv[m], xv[m]).slope)


def frozen_feats(vin, cut):
    """Verbatim from V1_1_SM_horizon.py: 4 features at truncation cut."""
    wm = WK[vin][WK[vin]["week"] <= cut].tail(L40).reset_index(drop=True)
    f = {"n_wk": len(wm)}
    if len(wm) < 8:
        f.update({k: np.nan for k in FROZEN})
        return f
    win_start = wm["week"].iloc[0]
    wm = wm.copy()
    wm["week_x"] = (wm["week"] - wm["week"].iloc[0]).dt.days / 7.0
    vds = wm["vsi_drive_std"].values.astype(float)

    f["vsi_withinwk_std_ratio_30d_w"] = (
        float(np.nanmean(vds[-4:]) / np.nanmean(vds))
        if np.isfinite(vds).sum() >= 6 and np.nanmean(vds) > 0 else np.nan)

    last12 = wm.tail(12)
    rng = (last12["vsi_drive_p95"] - last12["vsi_drive_p05"]).values.astype(float)
    f["vsi_range_trend"] = (theil_sen(rng, last12["week_x"].values.astype(float))
                            if np.isfinite(rng).sum() >= 6 else np.nan)

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

    if vin in SMA_DEAD:
        f["dip_depth_last90_delta"] = np.nan
    else:
        ev = EV[vin][EV[vin]["ts_start"] <= cut]
        dbc = (cut.normalize() - ev["ts_day"]).dt.days
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
    """LOVO: train-median impute -> StandardScaler -> RidgeClassifier."""
    oof = np.full(len(labels), np.nan)
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


# ── k=0 reconciliation ───────────────────────────────────────────────────────
print("k=0 reconciliation vs frozen feature matrix...")
frozen_mat = pd.read_csv(ROOT / "V1.1" / "results" / "V1_1_SM_feature_matrix.csv")
rec0 = pd.DataFrame([{**{"vin_label": v}, **frozen_feats(v, T_END[v])} for v in vins])
ok = True
for c in FROZEN:
    a = rec0[c].values.astype(float)
    b = frozen_mat[c].values.astype(float)
    both = np.isfinite(a) & np.isfinite(b)
    nan_mismatch = int((np.isfinite(a) != np.isfinite(b)).sum())
    md = np.max(np.abs(a[both] - b[both])) if both.any() else 0.0
    flag = "OK" if (md < 1e-9 and nan_mismatch == 0) else "MISMATCH"
    ok &= flag == "OK"
    print(f"  {c:<36} max|diff|={md:.2e}  NaN-mismatches={nan_mismatch}  {flag}")
if not ok:
    raise SystemExit("k=0 reconciliation FAILED — abort (spec requirement).")
print("Reconciliation PASS.")

# ── k=0 AUROC check ──────────────────────────────────────────────────────────
print("Computing k=0 LOVO for AUROC gate check...")
F0 = np.array([[frozen_feats(v, T_END[v])[c] for c in FROZEN] for v in vins], float)
usable0 = np.array([frozen_feats(v, T_END[v])["n_wk"] >= 8 for v in vins])
oof0 = lovo_ridge(F0[usable0], y[usable0])
auroc0 = rank_auroc(oof0, y[usable0])
print(f"k=0 AUROC = {auroc0:.4f}  (spec target 0.9357 ±0.002)")
if abs(auroc0 - 0.9357) > 0.002:
    raise SystemExit(f"k=0 AUROC {auroc0:.4f} deviates from 0.9357 by more than 0.002 — STOP.")
print("AUROC gate PASS.")

# ── Platt calibration at k=0 ────────────────────────────────────────────────
# Fit sigmoid on k=0 LOVO decision values → probabilities
# SIMPLIFICATION: same sigmoid used at all k (stated prominently in report)
full_oof0 = np.full(len(vins), np.nan)
oof0_idx = np.where(usable0)[0]
full_oof0[oof0_idx] = oof0
lr = LogisticRegression(C=1e4, solver="lbfgs")
m_platt = lr.fit(oof0.reshape(-1, 1), y[usable0])
print(f"Platt sigmoid (k=0): coef={m_platt.coef_[0][0]:.4f}  "
      f"intercept={m_platt.intercept_[0]:.4f}")


def dv_to_prob(dv_arr):
    """Apply k=0 Platt sigmoid to decision values."""
    dv = np.asarray(dv_arr, float)
    p = m_platt.predict_proba(dv.reshape(-1, 1))[:, 1]
    return p


def prob_to_tier(p):
    lo, hi = TIER_THRESHOLDS
    if np.isnan(p):
        return "UNKNOWN"
    if p >= hi:
        return "RED"
    elif p >= lo:
        return "AMBER"
    return "GREEN"


# ── full walk-back ────────────────────────────────────────────────────────────
print(f"\nWalk-back k=0..{K_MAX}:")
rows = []
for k in range(K_MAX + 1):
    for i, v in enumerate(vins):
        cut = T_END[v] - pd.Timedelta(days=7 * k)
        f = frozen_feats(v, cut)
        rows.append({
            "vin_label": v,
            "k_weeks": k,
            "cut_date": cut.date(),
            "n_wk": f["n_wk"],
            "usable": f["n_wk"] >= 8,
            "label": y[i],
            **{c: f[c] for c in FROZEN}
        })
    print(f"  k={k:2d} computed", end="\r")

df_raw = pd.DataFrame(rows)
print(f"\nFeatures computed: {len(df_raw)} rows (34 VINs x {K_MAX+1} k values)")

# For each k, run LOVO on usable trucks, propagate scores back
oof_records = []
for k in range(K_MAX + 1):
    sub = df_raw[df_raw["k_weeks"] == k].reset_index(drop=True)
    usable_mask = sub["usable"].values
    if usable_mask.sum() < 10:
        # assign NaN to all
        for _, row in sub.iterrows():
            oof_records.append({"vin_label": row["vin_label"], "k_weeks": k,
                                 "decision_value": np.nan})
        continue
    F = sub[FROZEN].values.astype(float)
    lab = sub["label"].values
    oof_sub = np.full(len(sub), np.nan)
    # LOVO only on usable subset; index mapping
    usable_idx = np.where(usable_mask)[0]
    F_use = F[usable_mask]
    lab_use = lab[usable_mask]
    oof_use = lovo_ridge(F_use, lab_use)
    for j, idx in enumerate(usable_idx):
        oof_sub[idx] = oof_use[j]
    for j in range(len(sub)):
        oof_records.append({"vin_label": sub.loc[j, "vin_label"],
                            "k_weeks": k,
                            "decision_value": oof_sub[j]})

df_oof = pd.DataFrame(oof_records)
df_scores = df_raw.merge(df_oof, on=["vin_label", "k_weeks"])

# Apply Platt calibration (k=0 sigmoid, SIMPLIFICATION)
# Only calibrate where decision_value is finite
prob_vals = np.full(len(df_scores), np.nan)
finite_mask = np.isfinite(df_scores["decision_value"].values)
if finite_mask.any():
    prob_vals[finite_mask] = dv_to_prob(df_scores["decision_value"].values[finite_mask])
df_scores["prob"] = prob_vals
df_scores["tier"] = df_scores["prob"].apply(
    lambda p: prob_to_tier(p) if np.isfinite(p) else "UNKNOWN")

# Keep essential columns only
out_cols = ["vin_label", "label", "k_weeks", "cut_date", "n_wk", "usable",
            "decision_value", "prob", "tier"]
df_out = df_scores[out_cols].sort_values(["vin_label", "k_weeks"]).reset_index(drop=True)
out_path = OUT_DIR / "walking_scores.csv"
df_out.to_csv(out_path, index=False)
print(f"\nSaved walking_scores.csv -> {out_path}")
print(f"  Shape: {df_out.shape}")
print(f"  k=0 AUROC = {auroc0:.4f}")
print(f"  Simplification: k=0 Platt sigmoid used at ALL k (not per-cut calibrated)")
print(f"  Tier distribution (k=0, usable trucks):")
k0 = df_out[(df_out["k_weeks"] == 0) & df_out["usable"]]
print(k0.groupby(["label", "tier"]).size().to_string())
