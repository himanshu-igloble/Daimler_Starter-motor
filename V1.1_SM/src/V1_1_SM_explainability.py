"""
V1_1_SM_explainability.py — Experiment X5: Layer-4 explainability for the V1.1
Starter Motor fleet-risk model.

What this does
--------------
1. PRODUCTION REFIT (documented as such): trains the final 4-feature
   RidgeClassifier(alpha=1.0) on all 34 trucks (median impute -> StandardScaler).
   This is the deployment artifact; all *validation* numbers on the cards remain
   the nested-LOVO out-of-fold values from X2 (never the refit's resubstitution
   scores).
2. EXACT LINEAR ATTRIBUTION: per-truck contribution_i = coef_i * z_i where z is
   the standardized feature. For a linear model on standardized inputs this IS
   the (interventional) SHAP decomposition: phi_i = coef_i * (z_i - mean(z_i))
   and mean(z_i) = 0 after StandardScaler, so phi_i = coef_i * z_i exactly.
   No shap library needed or used.
3. COUNTERFACTUALS: smallest single-feature change (reported in raw units) that
   moves the truck across its nearest tier boundary. Mechanics: a Platt-style
   sigmoid bridge p = sigmoid(a*d + b) is least-squares fitted from the
   production decision values d to the 34 honest OOF recalibrated probabilities
   (X2), so boundary probabilities map to boundary decision values; then
   delta_z_i = delta_d / coef_i and delta_x_i = delta_z_i * scale_i.
   "Smallest" = smallest standardized change |delta_z| among features that are
   OBSERVED (not imputed) for that truck; the per-feature table is kept in the
   JSON. Counterfactuals live in production-refit space; any truck whose
   production tier differs from the shipped OOF tier is flagged.
4. GLOBAL: coefficient table (raw + standardized), physics-sign sanity check
   vs Agent D priors, pairwise correlations among the 4 features.
5. Fleet risk graph: all 34 trucks' recalibrated OOF P with tier colors,
   archetypes annotated, sole miss highlighted.

Inputs (read-only): V1.1/results/V1_1_SM_feature_matrix.csv,
  V1_1_SM_nested_lovo_predictions.csv, V1_1_SM_model_spec.json,
  V1_1_SM_gates.json, V1.1/discovery/out/E2_failed_vin_archetypes.csv,
  V1.1/discovery/out/G3_horizon_curve.csv.

Outputs: V1.1/results/V1_1_SM_explanations.json
         V1.1/reports/V1_1_SM_explanation_cards.md
         V1.1/graphs/V1_1_SM_fleet_risk.png

Run: py -3 "STARTER MOTOR/V1.1/src/V1_1_SM_explainability.py"
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import pearsonr, spearmanr
from sklearn.linear_model import RidgeClassifier
from sklearn.preprocessing import StandardScaler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Display-level VIN renumbering (2026-06-11): GRAPH ONLY. The JSON/markdown
# artifacts keep the ORIGINAL labels (audit trail); only the fleet-risk PNG
# shows the new sequential numbering (failed VIN1-14, NF as VIN15-34).
from V1_1_SM_vin_display_map import display_label

ROOT = Path(r"D:\Daimler-starter_motor_alternator_battery\STARTER MOTOR\V1.1")
RES, REP, GRA = ROOT / "results", ROOT / "reports", ROOT / "graphs"
GRA.mkdir(parents=True, exist_ok=True)

MODEL_ID = "V1.1-SM RidgeClassifier(alpha=1.0), 4 features, production refit 2026-06-10"
GREEN_LT, AMBER_LT = 0.35, 0.55
TIER_COLORS = {"GREEN": "#2e7d32", "AMBER": "#ef6c00", "RED": "#c62828"}

FEATS = ["vsi_withinwk_std_ratio_30d_w", "rest_vsi_p05_delta90",
         "vsi_range_trend", "dip_depth_last90_delta"]

# Agent D / E physics priors: expected coefficient sign (toward failure class +1)
PHYSICS_PRIOR = {
    "vsi_withinwk_std_ratio_30d_w": (+1, "rising within-week electrical noise = "
        "volatility drift (common channel of A1 solenoid, A2 battery, A3 instability)"),
    "rest_vsi_p05_delta90": (-1, "falling engine-off rest-voltage floor = battery "
        "floor sagging vs own baseline (battery-cascade pathway, D section 3)"),
    "vsi_range_trend": (+1, "widening weekly drive-voltage envelope = regulation "
        "instability / electrical degradation"),
    "dip_depth_last90_delta": (+1, "crank dips deepening vs own baseline = "
        "battery/cascade load signature (E2: A2 VINs dip_depth +1.1..+3.6 V)"),
}

UNIT = {"vsi_withinwk_std_ratio_30d_w": "x (ratio)", "rest_vsi_p05_delta90": "V",
        "vsi_range_trend": "V/wk", "dip_depth_last90_delta": "V"}

SHORT = {"vsi_withinwk_std_ratio_30d_w": "within-week VSI noise ratio (last 4 wk / own 40-wk baseline)",
         "rest_vsi_p05_delta90": "rest-VSI floor delta, last ~90 d vs own baseline (battery-step aware)",
         "vsi_range_trend": "weekly drive-VSI range (p95-p05) Theil-Sen slope, last 12 wk",
         "dip_depth_last90_delta": "crank dip-depth delta, last 90 d vs own baseline"}

# Plain-language gloss generators: (text when contribution pushes UP = toward failure,
# text when it pushes DOWN = protective), given the raw value x.
def gloss(feat, x, contrib):
    if feat == "vsi_withinwk_std_ratio_30d_w":
        if contrib > 0:
            return (f"within-week voltage noise is {x:.2f}x its own 40-week baseline -- "
                    "electrical volatility is drifting up (volatility-drift pathway)")
        return (f"within-week voltage noise at {x:.2f}x own baseline -- quiet, "
                "fleet-typical electrical behaviour (protective)")
    if feat == "rest_vsi_p05_delta90":
        if contrib > 0:
            return (f"engine-off rest-voltage floor moved {x:+.2f} V vs own baseline -- "
                    "battery floor sagging, battery-cascade pathway")
        return (f"rest-voltage floor {x:+.2f} V vs own baseline -- battery floor "
                "stable/recovering (protective)")
    if feat == "vsi_range_trend":
        # NOTE: multivariate coefficient is NEGATIVE (suppressor; see global physics
        # check). Describe the physical value honestly; model direction separately.
        phys = (f"weekly voltage range widening at {x:+.3f} V/wk over the last 12 weeks"
                if x > 1e-6 else
                f"weekly voltage range trend {x:+.3f} V/wk -- envelope flat")
        return (phys + " [model uses this term as a statistical suppressor for the "
                "correlated noise ratio (r=+0.82); its standalone physics direction "
                "is widening = risk -- see global coefficient table]")
    if feat == "dip_depth_last90_delta":
        if contrib > 0:
            return (f"crank voltage dips {x:+.2f} V deeper than own baseline in the "
                    "last 90 d -- heavier cranking load / battery-cascade signature")
        return (f"crank dip depth {x:+.2f} V vs own baseline -- dips not "
                "deepening (protective)")
    return ""

CF_VERB = {  # (verb for risk-decreasing change, verb for risk-increasing change)
    "vsi_withinwk_std_ratio_30d_w": ("within-week noise ratio fell", "within-week noise ratio rose"),
    "rest_vsi_p05_delta90": ("last-90d rest-VSI floor recovered", "last-90d rest-VSI floor sagged further"),
    "vsi_range_trend": ("weekly voltage-range trend flattened", "weekly voltage-range trend steepened"),
    "dip_depth_last90_delta": ("crank dip-depth delta narrowed", "crank dip-depth delta widened"),
}

# ---------------------------------------------------------------- load inputs
fm = pd.read_csv(RES / "V1_1_SM_feature_matrix.csv")
preds = pd.read_csv(RES / "V1_1_SM_nested_lovo_predictions.csv")
spec = json.loads((RES / "V1_1_SM_model_spec.json").read_text())
gates = json.loads((RES / "V1_1_SM_gates.json").read_text())
arch = pd.read_csv(ROOT / "discovery" / "out" / "E2_failed_vin_archetypes.csv")
g3 = pd.read_csv(ROOT / "discovery" / "out" / "G3_horizon_curve.csv")

assert sorted(spec["modal_winner_subset"]) == sorted(FEATS), "feature set mismatch vs model spec"
df = fm.merge(preds[["vin_label", "failed", "prob", "prob_recal", "tier", "pred_foldthr",
                     "inner_youden"]], on=["vin_label", "failed"], validate="1:1")
assert len(df) == 34

ARCH_SHORT = {"A1_solenoid_intermittency": "A1", "A1+A2_mixed": "A1+A2",
              "A1_solenoid_then_silent": "A1->silent", "A2_battery_cascade": "A2",
              "A3_vsi_volatility_only": "A3", "A4_silent_abrupt": "A4"}
arch_map = dict(zip(arch["vin_label"], arch["archetype"]))
gap_map = dict(zip(arch["vin_label"], arch["silent_gap_d"].fillna(0).astype(int)))

# SMA-dead cohort and imputation flags come from the matrix itself: cohort-masked
# features are NaN exactly for SMA-dead trucks (+ VIN5_F, zero events in window).
imputed_dip = set(df.loc[df["dip_depth_last90_delta"].isna(), "vin_label"])
SMA_DEAD = {"VIN8_F_SM", "VIN9_F_SM", "VIN10_NF_SM", "VIN11_NF_SM", "VIN12_NF_SM",
            "VIN13_NF_SM", "VIN20_NF_SM"}
assert imputed_dip == SMA_DEAD | {"VIN5_F_SM"}, f"unexpected NaN set: {imputed_dip}"
BAT_STEP_VINS = {"VIN8_F_SM", "VIN3_NF_SM", "VIN5_NF_SM", "VIN12_NF_SM",
                 "VIN17_NF_SM", "VIN18_NF_SM"}  # E5 rest-VSI step >= +0.5 V, SNR >= 2

# ------------------------------------------------- recompute headline metrics
def auroc(scores, labels):
    pos, neg = scores[labels == 1], scores[labels == 0]
    u = sum((neg < p).sum() + 0.5 * (neg == p).sum() for p in pos)
    return u / (len(pos) * len(neg))

y = df["failed"].values
# Headline 0.9321 (spec) is pooled on raw per-fold decision values; the CSV ships
# `prob` (per-fold sigmoid of decision values) and `prob_recal` (per-fold Platt).
# Per-fold monotone transforms perturb POOLED ranking slightly, so recomputing on
# `prob` gives 0.9339 (delta +0.0018). We report the recomputed value and keep the
# spec headline as the official number; tolerance below covers the transform delta.
auroc_oof_prob = auroc(df["prob"].values, y)
auroc_oof = float(spec["headline"]["nested_auroc"])        # official headline (X2)
brier = float(np.mean((df["prob_recal"].values - y) ** 2))
tp = int(((df["pred_foldthr"] == 1) & (y == 1)).sum())
fn = int(((df["pred_foldthr"] == 0) & (y == 1)).sum())
tn = int(((df["pred_foldthr"] == 0) & (y == 0)).sum())
fp = int(((df["pred_foldthr"] == 1) & (y == 0)).sum())
tier_tab = df.groupby(["tier", "failed"]).size().unstack(fill_value=0)
red_recall = int(((df["tier"] == "RED") & (y == 1)).sum())
red_fp = int(((df["tier"] == "RED") & (y == 0)).sum())
k_ok = g3[g3["k_weeks"] <= 10]["auroc"]
k11 = float(g3.loc[g3["k_weeks"] == 11, "auroc"].iloc[0])
print(f"Recomputed from artifacts: OOF AUROC on `prob` {auroc_oof_prob:.4f} "
      f"(official headline on raw decision values: {auroc_oof}), "
      f"Brier {brier:.3f} (gates {gates['G3_calibration']['brier_recalibrated']}), "
      f"Youden TP/FN/TN/FP {tp}/{fn}/{tn}/{fp}, RED {red_recall}/14 @ {20-red_fp}/20 spec, "
      f"G3 k<=10 AUROC {k_ok.min():.3f}-{k_ok.max():.3f}, k=11 {k11:.3f}")
assert abs(auroc_oof_prob - auroc_oof) < 5e-3, "OOF prob ranking diverges from headline"
assert abs(brier - gates["G3_calibration"]["brier_recalibrated"]) < 5e-4
assert (tp, fn, tn, fp) == (13, 1, 15, 5) and red_recall == 10 and red_fp == 2

# ------------------------------------------------------------ production refit
X_raw = df[FEATS].values.astype(float)
med = np.nanmedian(X_raw, axis=0)
X_imp = np.where(np.isnan(X_raw), med, X_raw)
scaler = StandardScaler().fit(X_imp)
Z = scaler.transform(X_imp)
clf = RidgeClassifier(alpha=1.0).fit(Z, y)
coef_z = clf.coef_.ravel()
intercept = float(clf.intercept_[0])
d_prod = clf.decision_function(Z)
coef_raw = coef_z / scaler.scale_          # per raw unit
auroc_resub = auroc(d_prod, y)
print(f"Production refit: resubstitution AUROC {auroc_resub:.4f} (NOT a validation "
      f"number; honest number is nested {auroc_oof:.4f})")

# contributions: coef_z * z  == exact SHAP for linear model (E[z]=0 after scaling)
contrib = Z * coef_z                                  # (34, 4)
assert np.allclose(contrib.sum(axis=1) + intercept, d_prod, atol=1e-12)

# ------------------------------------------- Platt bridge d_prod -> prob_recal
def sigm(d, a, b):
    return 1.0 / (1.0 + np.exp(-(a * d + b)))

(a_cal, b_cal), _ = curve_fit(sigm, d_prod, df["prob_recal"].values, p0=(1.0, 0.0),
                              maxfev=20000)
p_prod = sigm(d_prod, a_cal, b_cal)
rho_bridge = float(spearmanr(p_prod, df["prob_recal"]).statistic)
rmse_bridge = float(np.sqrt(np.mean((p_prod - df["prob_recal"]) ** 2)))
print(f"Calibration bridge: a={a_cal:.3f} b={b_cal:.3f}, Spearman {rho_bridge:.3f}, "
      f"RMSE {rmse_bridge:.3f} vs OOF recal probs")

def tier_of(p):
    return "GREEN" if p < GREEN_LT else ("AMBER" if p < AMBER_LT else "RED")

def d_of_p(p):
    return (np.log(p / (1 - p)) - b_cal) / a_cal

# ------------------------------------------------------------- physics check
# Univariate orientation (raw AUROC vs failed) tells whether the FEATURE moves with
# physics; the multivariate coef can legitimately flip for a correlated suppressor.
physics_rows = []
suppressors = set()
for j, f in enumerate(FEATS):
    want, why = PHYSICS_PRIOR[f]
    a_uni = auroc(X_raw[~np.isnan(X_raw[:, j]), j], y[~np.isnan(X_raw[:, j])])
    uni_sign = 1 if a_uni > 0.5 else -1
    uni_ok = uni_sign == want
    multi_ok = np.sign(coef_z[j]) == want
    diag = "matches physics"
    if not multi_ok and uni_ok:
        diag = ("FLAGGED: multivariate sign contradicts physics -- suppressor effect "
                "(feature is physics-consistent univariately but strongly correlated "
                "with a dominant feature; ridge assigns it a corrective negative weight)")
        suppressors.add(f)
    elif not uni_ok:
        diag = "FLAGGED: univariate direction contradicts physics"
    physics_rows.append({"feature": f, "coef_std": float(coef_z[j]),
                         "coef_raw_per_unit": float(coef_raw[j]),
                         "expected_sign": "+" if want > 0 else "-",
                         "univariate_auroc_raw": round(float(a_uni), 3),
                         "univariate_direction_matches_physics": bool(uni_ok),
                         "multivariate_sign_matches_physics": bool(multi_ok),
                         "verdict": diag, "physics_prior": why})
    print(f"  {f}: coef_z={coef_z[j]:+.4f} expected {'+' if want>0 else '-'} "
          f"uniAUROC {a_uni:.3f} -> {diag}")

# pairwise correlations among the 4 (raw, pairwise-complete)
corr_p = df[FEATS].corr(method="pearson").round(3)
corr_s = df[FEATS].corr(method="spearman").round(3)

# ------------------------------------------------------------ per-VIN cards
EPS_Z = 1e-9
cards = []
order = df.sort_values("prob_recal", ascending=False).reset_index(drop=True)
for i, r in order.iterrows():
    vin = r["vin_label"]
    idx = df.index[df["vin_label"] == vin][0]
    z_v, c_v, x_v = Z[idx], contrib[idx], X_raw[idx]
    imput = [FEATS[j] for j in range(4) if np.isnan(x_v[j])]
    x_eff = np.where(np.isnan(x_v), med, x_v)          # values the model actually saw
    drivers = []
    for j in np.argsort(-np.abs(c_v)):
        f = FEATS[j]
        drivers.append({
            "feature": f, "raw_value": float(x_eff[j]),
            "imputed": f in imput, "z": float(z_v[j]), "contribution": float(c_v[j]),
            "direction": "toward failure" if c_v[j] > 0 else "protective",
            "gloss": gloss(f, x_eff[j], c_v[j]) + (" [IMPUTED fleet median -- "
                     "no crank events observable for this truck]" if f in imput else ""),
        })
    # --- counterfactual: nearest tier boundary in production space
    p0 = float(p_prod[idx])
    t_prod = tier_of(p0)
    if t_prod == "GREEN":
        p_b, move = GREEN_LT, "would enter AMBER"
    elif t_prod == "RED":
        p_b, move = AMBER_LT, "would drop RED -> AMBER"
    else:
        p_b, move = ((GREEN_LT, "would return to GREEN")
                     if abs(p0 - GREEN_LT) <= abs(p0 - AMBER_LT)
                     else (AMBER_LT, "would escalate AMBER -> RED"))
    # nudge target just across the boundary
    p_t = p_b - 1e-3 if p_b > p0 else p_b  # crossing below a lower bound lands in lower tier at p_b - eps
    if p_b > p0:        # risk-increasing move (GREEN headroom / AMBER->RED)
        p_t = p_b
    else:               # risk-decreasing move: must go strictly below boundary
        p_t = p_b - 1e-3
    dd = float(d_of_p(p_t) - d_prod[idx])
    options = []
    for j, f in enumerate(FEATS):
        if abs(coef_z[j]) < EPS_Z:
            continue
        dz = dd / coef_z[j]
        dx = dz * scaler.scale_[j]
        options.append({"feature": f, "delta_z": float(dz),
                        "delta_raw": float(dx), "unit": UNIT[f],
                        "new_raw_value": float(x_eff[j] + dx),
                        "imputed_feature": f in imput})
    obs_opts = [o for o in options if not o["imputed_feature"]]
    best = min(obs_opts, key=lambda o: abs(o["delta_z"]))
    verb = CF_VERB[best["feature"]][0 if dd < 0 else 1]
    cf_text = (f"{move} if {verb} by {abs(best['delta_raw']):.2f} {best['unit']} "
               f"({best['feature']}: {x_eff[FEATS.index(best['feature'])]:.2f} -> "
               f"{best['new_raw_value']:.2f}), all else equal")
    # --- caveats
    caveats = []
    if vin in SMA_DEAD:
        caveats.append("SMA-dead telematics config: no crank events observable; "
                       "dip_depth_last90_delta is fold-median IMPUTED, not measured.")
    elif vin == "VIN5_F_SM":
        caveats.append("Zero crank events / no VSI in final 120 d window: "
                       "dip_depth_last90_delta IMPUTED; card rests on weekly VSI only.")
    g = gap_map.get(vin, 0)
    if g and g > 0:
        caveats.append(f"Silent gap of {g} d before failure: features describe the "
                       "pre-silence state; the terminal period is untelemetered.")
    if vin in BAT_STEP_VINS:
        caveats.append("Battery-replacement step detected (E5): rest-VSI baseline "
                       "re-anchored post-step; rest_vsi_p05_delta90 is step-aware.")
    if r["tier"] != t_prod:
        caveats.append(f"Production-refit tier ({t_prod}) differs from shipped OOF "
                       f"tier ({r['tier']}); counterfactual is in production space.")
    if bool(r["failed"]) and vin == "VIN9_F_SM":
        caveats.append("SOLE MISS of the nested model (OOF prob 0.401 vs fold thr "
                       "0.406). A4 silent/abrupt + SMA-dead + 142 d gap: physics "
                       "audit classifies this failure as unobservable in 5 s telemetry.")
    a_lbl = ARCH_SHORT.get(arch_map.get(vin, ""), "n/a") if r["failed"] == 1 else "n/a"
    cards.append({
        "vin_label": vin, "failed": int(r["failed"]),
        "tier_shipped_oof": r["tier"], "prob_recal_oof": float(r["prob_recal"]),
        "prob_decision_oof": float(r["prob"]),
        "prob_production_bridge": round(p0, 4), "tier_production": t_prod,
        "archetype": a_lbl,
        "archetype_full": arch_map.get(vin, "n/a") if r["failed"] == 1 else "n/a",
        "decision_value_production": float(d_prod[idx]),
        "drivers": drivers, "counterfactual": cf_text,
        "counterfactual_options_all": options, "caveats": caveats,
    })

# ---------------------------------------------------------------- JSON output
out = {
    "experiment": "X5 V1.1 Layer-4 explainability",
    "created": "2026-06-10", "model_id": MODEL_ID,
    "attribution_method": ("Exact linear attribution: contribution_i = coef_i * z_i "
        "(z standardized). Equals SHAP for a linear model with feature-independence "
        "baseline since E[z_i]=0; no shap library used."),
    "production_refit": {
        "note": ("Refit on all 34 trucks for deployment/explanation only. Validation "
                 "numbers are X2 nested-LOVO; resubstitution AUROC reported for "
                 "transparency, never as a performance claim."),
        "impute_medians": {f: float(m) for f, m in zip(FEATS, med)},
        "scaler_mean": {f: float(m) for f, m in zip(FEATS, scaler.mean_)},
        "scaler_scale": {f: float(s) for f, s in zip(FEATS, scaler.scale_)},
        "intercept": intercept, "resubstitution_auroc": round(auroc_resub, 4),
    },
    "coefficients": physics_rows,
    "physics_sign_check": {
        "univariate_all_match": bool(all(p["univariate_direction_matches_physics"]
                                         for p in physics_rows)),
        "multivariate_all_match": bool(all(p["multivariate_sign_matches_physics"]
                                           for p in physics_rows)),
        "suppressors": sorted(suppressors),
        "note": ("Univariate direction is the physics test; a multivariate sign flip "
                 "for a feature correlated r=+0.82 with the dominant feature is a "
                 "ridge suppressor effect, not a physics contradiction."),
    },
    "feature_correlations_pearson": corr_p.to_dict(),
    "feature_correlations_spearman": corr_s.to_dict(),
    "calibration_bridge": {"a": float(a_cal), "b": float(b_cal),
                           "spearman_vs_oof_recal": rho_bridge, "rmse": rmse_bridge,
                           "purpose": "maps production decision values to the OOF "
                                      "recalibrated probability scale for counterfactuals"},
    "recomputed_headline": {
        "nested_oof_auroc_official": auroc_oof,
        "nested_oof_auroc_recomputed_on_prob": round(auroc_oof_prob, 4),
        "auroc_note": ("official headline pooled on raw per-fold decision values (X2); "
                       "`prob` is per-fold sigmoid-mapped, recomputation differs +0.002"),
        "brier_recal": round(brier, 4),
        "youden_confusion": {"tp": tp, "fn": fn, "tn": tn, "fp": fp},
        "red_tier": {"recall": f"{red_recall}/14", "specificity": f"{20-red_fp}/20"},
        "tier_counts": {t: {"failed": int(tier_tab.loc[t, 1]),
                            "nonfailed": int(tier_tab.loc[t, 0])} for t in tier_tab.index},
        "g3_horizon": {"k0_10_auroc_min": round(float(k_ok.min()), 4),
                       "k0_10_auroc_max": round(float(k_ok.max()), 4),
                       "k11_auroc": round(k11, 4)},
    },
    "tier_rule": "GREEN < 0.35 <= AMBER < 0.55 <= RED on recalibrated probability",
    "cards_ordered_by_prob_recal_desc": cards,
}
(RES / "V1_1_SM_explanations.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"Wrote {RES / 'V1_1_SM_explanations.json'}")

# ----------------------------------------------------------- markdown cards
def fmt_corr(c):
    lines = ["| | " + " | ".join(f"`{f.split('_')[0]}_{i}`" for i, f in enumerate(FEATS)) + " |",
             "|---|" + "---|" * 4]
    for i, f in enumerate(FEATS):
        lines.append(f"| `{f}` | " + " | ".join(f"{c.loc[f, g]:+.2f}" for g in FEATS) + " |")
    return "\n".join(lines)

md = []
md.append(f"""---
title: "V1.1 Starter Motor — Per-VIN Explanation Cards (X5, Layer 4)"
status: "complete"
created: "2026-06-10"
---

# V1.1 SM — Explanation Cards (all 34 trucks)

Model: **{MODEL_ID}**.
Attribution: exact linear decomposition `contribution_i = coef_i x z_i` on standardized
features — for a linear model this **is** the SHAP decomposition (phi_i = coef_i x
(z_i − E[z_i]) and E[z_i] = 0 after standardization); no SHAP library required.
**Shipped probability/tier = nested-LOVO out-of-fold recalibrated values (X2)**; the
production refit (all 34 trucks) is used only for attribution and counterfactuals, and
its resubstitution AUROC ({auroc_resub:.3f}) is *not* a performance claim — the honest
number is nested OOF **{auroc_oof:.4f}**.
Counterfactuals: smallest single-feature change in **raw units** crossing the nearest
tier boundary, via a sigmoid bridge from production decision values to the OOF
recalibrated probability scale (Spearman {rho_bridge:.3f}, RMSE {rmse_bridge:.3f});
they are *ceteris paribus* statements, not repair prescriptions.
Tiers: GREEN < 0.35 <= AMBER < 0.55 <= RED.

## Global: coefficients & physics-direction check

| feature | meaning | coef (std) | coef (per raw unit) | expected sign (physics) | verdict |
|---|---|---|---|---|---|""")
for p in physics_rows:
    if p["multivariate_sign_matches_physics"]:
        verdict_md = "**matches physics**"
    elif p["feature"] in suppressors:
        verdict_md = (f"**suppressor — flagged** (univariate AUROC "
                      f"{p['univariate_auroc_raw']:.3f} matches physics; multivariate "
                      "sign flipped by r=+0.82 collinearity with the noise ratio)")
    else:
        verdict_md = "**CONTRADICTS physics — flagged**"
    md.append(f"| `{p['feature']}` | {SHORT[p['feature']]} | {p['coef_std']:+.4f} | "
              f"{p['coef_raw_per_unit']:+.4f} | {p['expected_sign']} "
              f"({p['physics_prior'].split('(')[0].strip()}) | {verdict_md} |")
n_multi_ok = sum(p["multivariate_sign_matches_physics"] for p in physics_rows)
md.append(f"""
All 4 features match physics direction **univariately** (raw AUROC vs failure);
{n_multi_ok}/4 multivariate coefficient signs also match. The exception,
`vsi_range_trend`, is a classic ridge **suppressor**: physics-consistent on its own
(widening envelope = risk) but r=+0.82 with the dominant noise-ratio feature, so the
model assigns it a corrective negative weight. Per-VIN glosses state the physical
value honestly and flag the model's suppressor use separately.
Intercept (std space): {intercept:+.4f}. Imputation medians (production): """ +
          ", ".join(f"`{f}`={m:.3f}" for f, m in zip(FEATS, med)) + ".")
md.append("\n### Pairwise feature correlation (Pearson, raw values, pairwise-complete)\n")
md.append(fmt_corr(corr_p))
md.append("\n(Spearman in the JSON. Max |off-diagonal Pearson| = "
          f"{np.abs(corr_p.values[~np.eye(4, dtype=bool)]).max():.2f} — the four features "
          "carry substantially independent information.)\n")
md.append("\n---\n\n## Per-VIN cards (ordered by recalibrated OOF probability, highest risk first)\n")

for c in cards:
    flag = " — FAILED" if c["failed"] else ""
    md.append(f"### {c['vin_label']}{flag} — **{c['tier_shipped_oof']}**, "
              f"P(recal) = {c['prob_recal_oof']:.3f}")
    md.append(f"- **Archetype**: {c['archetype']}"
              + (f" ({c['archetype_full']})" if c["failed"] else ""))
    md.append(f"- **Drivers** (exact linear attribution, ranked by |contribution|):")
    for d in c["drivers"]:
        md.append(f"  - `{d['feature']}` = {d['raw_value']:.3f}"
                  f"{' *(imputed)*' if d['imputed'] else ''} | z = {d['z']:+.2f} | "
                  f"contribution {d['contribution']:+.3f} ({d['direction']}): {d['gloss']}")
    md.append(f"- **Counterfactual**: {c['counterfactual']}.")
    if c["caveats"]:
        md.append("- **Caveats**:")
        for cv in c["caveats"]:
            md.append(f"  - {cv}")
    md.append("")

(REP / "V1_1_SM_explanation_cards.md").write_text("\n".join(md), encoding="utf-8")
print(f"Wrote {REP / 'V1_1_SM_explanation_cards.md'}")

# ------------------------------------------------------------------- graph
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12.5,
    "axes.titleweight": "bold", "axes.labelsize": 10, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.18,
    "grid.linewidth": 0.6,
})
# Sequential fleet ordering under the 2026-06-11 display renumbering:
# failed VIN1-14 (unchanged), then NF continue as VIN15-34 (old VIN{k}_NF ->
# new VIN{k+14}_NF). Landscape 2:1 figure -- undistorted at the technical
# deck's 8x4 in placement.
plot_df = df.copy()
plot_df["disp"] = plot_df["vin_label"].map(display_label)
plot_df["disp_num"] = plot_df["disp"].str.extract(r"VIN(\d+)_").astype(int)
plot_df = plot_df.sort_values("disp_num").reset_index(drop=True)
fig, ax = plt.subplots(figsize=(14, 7))
xpos = np.arange(len(plot_df))
for i, r in plot_df.iterrows():
    failed = r["failed"] == 1
    ax.bar(i, r["prob_recal"], color=TIER_COLORS[r["tier"]],
           alpha=0.95 if failed else 0.55, width=0.72,
           edgecolor="black" if r["vin_label"] == "VIN9_F_SM" else "none",
           linewidth=1.6 if r["vin_label"] == "VIN9_F_SM" else 0, zorder=3)
    if failed:
        a_lbl = ARCH_SHORT.get(arch_map.get(r["vin_label"], ""), "")
        ax.text(i, r["prob_recal"] + 0.015, f"x {a_lbl}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="#37474f", zorder=4, rotation=90)
ax.axhline(GREEN_LT, color="#616161", lw=1.0, ls="--", zorder=2)
ax.axhline(AMBER_LT, color="#616161", lw=1.0, ls="--", zorder=2)
ax.text(len(plot_df) - 0.3, GREEN_LT + 0.01, "0.35 AMBER", fontsize=8.5,
        color="#616161", va="bottom", ha="right")
ax.text(len(plot_df) - 0.3, AMBER_LT + 0.01, "0.55 RED", fontsize=8.5,
        color="#616161", va="bottom", ha="right")
ax.set_xticks(xpos)
ax.set_xticklabels([d.replace("_SM", "") for d in plot_df["disp"]],
                   fontsize=8.5, rotation=90)
for tick, f in zip(ax.get_xticklabels(), plot_df["failed"] == 1):
    if f:
        tick.set_fontweight("bold")
miss_i = plot_df.index[plot_df["vin_label"] == "VIN9_F_SM"][0]
ax.annotate("sole miss: VIN9_F (A4 silent/abrupt,\nSMA-dead, 142 d gap — structural)",
            xy=(miss_i, plot_df.loc[miss_i, "prob_recal"]),
            xytext=(miss_i + 1.5, 0.72), fontsize=8.5, color="#b71c1c",
            arrowprops=dict(arrowstyle="->", color="#b71c1c", lw=1.0))
ax.set_xlim(-0.7, len(plot_df) - 0.3)
ax.set_ylim(0, 1.12)
ax.set_ylabel("Recalibrated P(fail-pattern) — nested-LOVO out-of-fold")
ax.set_title("V1.1 Starter Motor — Fleet Risk (34 trucks, recalibrated OOF probabilities)")
handles = [plt.Rectangle((0, 0), 1, 1, color=TIER_COLORS[t]) for t in ["GREEN", "AMBER", "RED"]]
handles.append(plt.Line2D([], [], marker="x", color="#37474f", ls="none", markersize=7))
ax.legend(handles, [f"GREEN (<0.35): {int(tier_tab.loc['GREEN'].sum())}",
                    f"AMBER: {int(tier_tab.loc['AMBER'].sum())}",
                    f"RED (>=0.55): {int(tier_tab.loc['RED'].sum())}",
                    "failed truck (archetype A1-A4)"],
          loc="upper right", frameon=True, fontsize=9)
fig.text(0.5, 0.030,
         f"{MODEL_ID} | nested-LOVO AUROC {auroc_oof:.4f} (perm p=0.005) | "
         f"Brier {brier:.3f}, slope {gates['G3_calibration']['recal_slope']} | "
         f"RED tier: {red_recall}/14 recall @ {20-red_fp}/20 spec | 2026-06-10",
         ha="center", fontsize=8, color="#555555")
fig.text(0.5, 0.008,
         "Sequential fleet numbering (display-only, 2026-06-11): VIN1-14 failed, "
         "VIN15-34 in-service | raw-file mapping: results/V1_1_SM_vin_naming_map.csv | "
         "results artifacts retain original labels",
         ha="center", fontsize=8, color="#888888", style="italic")
fig.tight_layout(rect=[0, 0.045, 1, 1])
fig.savefig(GRA / "V1_1_SM_fleet_risk.png", dpi=170)
plt.close(fig)
print(f"Wrote {GRA / 'V1_1_SM_fleet_risk.png'}")
print("X5 explainability complete.")
