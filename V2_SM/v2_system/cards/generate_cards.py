"""
V2 Evidence Card Generator — Starter Motor fleet (34 trucks, _SM)
Layer 4 of the V2 system architecture.

Production fit: median-impute (all-34) -> StandardScaler -> RidgeClassifier(alpha=1.0)
on modal 4 features. Platt calibration for display probabilities.
Validation-of-record: nested LOVO AUROC 0.9321, CI [0.811, 0.986]
"""
import os, sys, json, hashlib
import numpy as np
import pandas as pd
from scipy.stats import percentileofscore
from sklearn.linear_model import RidgeClassifier, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = "D:/Daimler-starter_motor_alternator_battery/STARTER MOTOR"
RESULTS = f"{ROOT}/V1.1/results"
DISC    = f"{ROOT}/V1.1/discovery/out"
V2ECON  = f"{ROOT}/V2_program/analysis/econ"
V2HEUR  = f"{ROOT}/V2_program/analysis/heuristics/out"
OUTDIR  = f"{ROOT}/V2_program/v2_system/cards"
os.makedirs(OUTDIR, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
MODAL_FEATURES = [
    "vsi_withinwk_std_ratio_30d_w",
    "rest_vsi_p05_delta90",
    "vsi_range_trend",
    "dip_depth_last90_delta",
]
ALPHA = 1.0
CONFIG_VERSION = "2.0.0-A"
GEN_DATE = "2026-06-12"
NESTED_AUROC = 0.9321
NESTED_CI_LO = 0.811
NESTED_CI_HI = 0.986

TIER_GREEN_MAX  = 0.35   # prob < 0.35 = GREEN
TIER_AMBER_MAX  = 0.55   # 0.35 <= prob < 0.55 = AMBER
                          # prob >= 0.55 = RED

SMA_DEAD_VINS = {"VIN8_F_SM","VIN9_F_SM","VIN10_NF_SM","VIN11_NF_SM",
                 "VIN12_NF_SM","VIN13_NF_SM","VIN20_NF_SM"}
WATCHLIST_VINS = {"VIN2_NF_SM","VIN5_NF_SM","VIN8_NF_SM","VIN15_NF_SM"}

# Physics glossary for features
PHYSICS_GLOSS = {
    "vsi_withinwk_std_ratio_30d_w": (
        "within-week supply-voltage noise ratio vs own 40-wk baseline",
        "higher = electrical volatility drifting up (solenoid/battery/instability pathway)",
        "+"
    ),
    "rest_vsi_p05_delta90": (
        "engine-off rest-voltage 5th-pctile delta vs own baseline (last 90 d)",
        "more negative = battery floor sagging (battery-cascade pathway); sign convention: DOWN is negative = risk",
        "-"
    ),
    "vsi_range_trend": (
        "weekly drive-voltage range trend (V/wk) over last 12 wks",
        "SUPPRESSOR: multivariate sign flipped (ridge corrective weight, r=+0.82 with noise ratio); univariate direction = positive = risk",
        "+"
    ),
    "dip_depth_last90_delta": (
        "crank dip depth delta vs own baseline (last 90 d, V)",
        "higher = deeper dips during cranking = heavier battery load signature",
        "+"
    ),
}

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading data...", flush=True)
fm_full = pd.read_csv(f"{RESULTS}/V1_1_SM_feature_matrix.csv")
oof_preds = pd.read_csv(f"{RESULTS}/V1_1_SM_nested_lovo_predictions.csv")
archetypes = pd.read_csv(f"{DISC}/E2_failed_vin_archetypes.csv")
alert_policy = pd.read_csv(f"{RESULTS}/V1_1_SM_alert_policy.csv")
alert_val    = pd.read_csv(f"{RESULTS}/V1_1_SM_alert_validation.csv")
window_mat   = pd.read_csv(f"{V2ECON}/failure_window_matrix.csv")
walking      = pd.read_csv(f"{V2HEUR}/walking_scores.csv")

with open(f"{RESULTS}/V1_1_SM_explanations.json", encoding="utf-8") as f:
    expl_json = json.load(f)

# ── Build production model ────────────────────────────────────────────────────
print("Fitting production model...", flush=True)

X_df = fm_full[MODAL_FEATURES].copy()
y    = fm_full["failed"].values

# Median impute
medians = X_df.median()
X_imp   = X_df.fillna(medians)

# StandardScaler
scaler = StandardScaler()
X_sc   = scaler.fit_transform(X_imp)

# RidgeClassifier
ridge = RidgeClassifier(alpha=ALPHA)
ridge.fit(X_sc, y)
dec_vals = ridge.decision_function(X_sc)

# Platt calibration (logistic on decision values)
platt = LogisticRegression(C=1e6, max_iter=1000)
platt.fit(dec_vals.reshape(-1, 1), y)
prod_probs = platt.predict_proba(dec_vals.reshape(-1, 1))[:, 1]

# In-sample AUROC
insample_auroc = roc_auc_score(y, prod_probs)
print(f"In-sample AUROC: {insample_auroc:.4f} (should be >= {NESTED_AUROC})", flush=True)

# Coefficients — ridge.coef_ is shape (4,) for binary case
coefs_std = np.asarray(ridge.coef_).ravel()  # in standardized space, shape (4,)
coefs_raw = coefs_std / np.asarray(scaler.scale_).ravel()

print("\nCoefficient table (standardized space):", flush=True)
for feat, c_std, c_raw in zip(MODAL_FEATURES, coefs_std, coefs_raw):
    phys_sign = PHYSICS_GLOSS[feat][2]
    actual_sign = "+" if c_std > 0 else "-"
    flag = "" if actual_sign == phys_sign else " *** SUPPRESSOR/FLAG"
    if feat == "vsi_range_trend":
        flag = " [KNOWN SUPPRESSOR — see physics_gloss]"
    print(f"  {feat}: coef_std={c_std:+.4f} coef_raw={c_raw:+.6f} expected={phys_sign} actual={actual_sign}{flag}")

# Model hash
feat_str = "|".join(MODAL_FEATURES) + f"|alpha={ALPHA}"
model_hash = hashlib.sha256(feat_str.encode()).hexdigest()[:16]
print(f"\nModel hash (feature+alpha): {model_hash}", flush=True)

# ── Fleet percentiles ─────────────────────────────────────────────────────────
# Compute z-scores and fleet percentiles for each feature
fleet_vals = {}
for feat in MODAL_FEATURES:
    fleet_vals[feat] = X_imp[feat].values

# ── Tier assignment ────────────────────────────────────────────────────────────
def assign_tier(prob):
    if prob < TIER_GREEN_MAX:
        return "GREEN"
    elif prob < TIER_AMBER_MAX:
        return "AMBER"
    return "RED"

# ── Persistent RED ≥3 weeks from walking scores ───────────────────────────────
print("\nComputing persistent RED streaks...", flush=True)
persistent_red_3wk = {}
for vin, grp in walking.groupby("vin_label"):
    recent = grp.sort_values("k_weeks", ascending=True)  # ascending: lower k_weeks is more recent
    recent = recent.sort_values("k_weeks")
    # k_weeks=0 = most recent snapshot; check from there
    streak = 0
    for _, row in recent.iterrows():
        if row["tier"] == "RED":
            streak += 1
        else:
            break
    persistent_red_3wk[vin] = streak

print("VINs with persistent RED >= 3 weeks:")
for vin, s in sorted(persistent_red_3wk.items(), key=lambda x: -x[1]):
    if s >= 3:
        print(f"  {vin}: {s} weeks")

# ── Merge OOF predictions ─────────────────────────────────────────────────────
oof_map = dict(zip(oof_preds["vin_label"], oof_preds["prob_recal"]))
oof_tier_map = dict(zip(oof_preds["vin_label"], oof_preds["tier"]))

# ── Window matrix lookup ──────────────────────────────────────────────────────
# window_mat is a summary table (6 rows by evidence state), not per-VIN
# fw_by_state dict below is the correct per-card lookup

# ── Alert policy/validation lookup ───────────────────────────────────────────
ap_idx  = alert_policy.set_index("vin_label")
av_idx  = alert_val.set_index("vin_label")
arc_idx = archetypes.set_index("vin_label")

# Failure window summary rows (for the window evidence block)
fw_by_state = {
    "A2_battery_cascade_fired": {
        "n": 4,
        "median_lead_d": 66.5,
        "ci_lo": 28.0,
        "ci_hi": 91.0,
        "scheduling_window": "14–30 days from alert",
        "caveat": "Retrospective n=4. NF false alarms: 0/20. Min lead 28d — tight; prioritize."
    },
    "persistence_terminal_AND_RED_tier": {
        "n": 10,
        "median_lead_d": 206.5,
        "ci_lo": 126.0,
        "ci_hi": 283.5,
        "scheduling_window": "14–28 days",
        "caveat": "Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk)."
    },
    "RED_tier_no_channel_yet": {
        "n": 10,
        "median_lead_d": 206.5,
        "ci_lo": 128.0,
        "ci_hi": 273.0,
        "scheduling_window": "30–60 days or next scheduled service",
        "caveat": "Act on channel fire, not score alone. 2 RED NF are false positives (VIN5_NF, VIN20_NF)."
    },
    "AMBER_tier_no_channel": {
        "n": 0,
        "median_lead_d": None,
        "ci_lo": None,
        "ci_hi": None,
        "scheduling_window": "At next scheduled service (<=90 days)",
        "caveat": "0 failed trucks scored AMBER in OOF — no empirical lead-time data. 2/20 NF scored AMBER."
    },
    "GREEN_tier_channel_fires_eventually": {
        "n": 3,
        "median_lead_d": 160.0,
        "ci_lo": 28.0,
        "ci_hi": 168.0,
        "scheduling_window": "Next scheduled service (50,000 km or 6 months)",
        "caveat": "3/4 GREEN-failed trucks eventually fired a channel. 1 (VIN9_F) fired nothing — irreducible blind spot."
    },
    "SILENT_SMA_30d_while_RED_or_AMBER": {
        "n": 2,
        "median_lead_d": None,
        "ci_lo": None,
        "ci_hi": None,
        "scheduling_window": "Within 72 hours",
        "caveat": "SMA-dead + VSI persistence detectable (VIN8_F, 98d lead). VIN9_F was fully blind. n=2 — very limited evidence."
    }
}

# ── Archetype physics map ─────────────────────────────────────────────────────
ARCHETYPE_PHYSICS = {
    "A1_solenoid_intermittency":   "Solenoid contact resistance degrading — repeated crank bursts with VSI volatility; wear-fatigue mode",
    "A1_solenoid_then_silent":     "Solenoid wear followed by data silence (SMA gap); progressive contact degradation then abrupt cutoff",
    "A1+A2_mixed":                 "Mixed: solenoid crank bursts + battery voltage floor decline; compound electro-mechanical degradation",
    "A2_battery_cascade":          "Battery voltage floor sagging (rest VSI p05 decline) triggering cascade load on starter; battery-primary mode",
    "A3_vsi_volatility_only":      "Electrical instability without dominant crank pattern; regulation or wiring intermittency mode",
    "A4_silent_abrupt":            "Data silence (SMA dead) with/without prior VSI signals; abrupt failure with minimal observable precursor",
}

NF_ARCHETYPE = "Non-failed — no archetype assigned (archetype analysis for failed trucks only)"

# ── Cards output ──────────────────────────────────────────────────────────────
all_cards = []
fm_full_indexed = fm_full.set_index("vin_label")

for idx, row in fm_full.iterrows():
    vin = row["vin_label"]
    failed = int(row["failed"])
    feat_vec = X_imp.iloc[idx][MODAL_FEATURES].values

    # Production prob
    prod_prob = float(prod_probs[idx])
    prod_tier = assign_tier(prod_prob)
    dec_val   = float(dec_vals[idx])

    # OOF prob
    oof_prob = float(oof_map.get(vin, np.nan))
    oof_tier = oof_tier_map.get(vin, "N/A")

    # Badges
    sma_dead_badge  = vin in SMA_DEAD_VINS
    watchlist_badge = vin in WATCHLIST_VINS

    # Archetype
    if failed and vin in arc_idx.index:
        ar = arc_idx.loc[vin]
        archetype_key = ar["archetype"]
        archetype_flags = ar["flags"]
        physics_mode = ARCHETYPE_PHYSICS.get(archetype_key, archetype_key)
    else:
        archetype_key = "NF"
        archetype_flags = "—"
        physics_mode = NF_ARCHETYPE

    # Alert channels — use alert_policy (ap_idx) which has pers_end_fire, a1_fire, a2_fire
    if vin in ap_idx.index:
        ap = ap_idx.loc[vin]
        pers_end_fire  = bool(ap["pers_end_fire"]) if not pd.isna(ap["pers_end_fire"]) else False
        a1_fire_raw    = str(ap["a1_fire"])
        a2_fire_raw    = str(ap["a2_fire"])
        a2_fire        = bool(ap["a2_fire"]) if str(ap["a2_fire"]) == "True" else False
        first_channel  = str(ap["first_channel"])
        first_fire_date= str(ap["first_fire_date"]) if not pd.isna(ap["first_fire_date"]) else "—"
        a1_fire        = "n/a (SMA-dead)" if "SMA-dead" in a1_fire_raw else (
                          "True" if a1_fire_raw == "True" else "False")
    else:
        pers_end_fire = False; a1_fire = "False"; a2_fire = False
        first_channel = "NONE"; first_fire_date = "—"

    # Persistent RED streak
    pers_streak = persistent_red_3wk.get(vin, 0)

    # Priority assignment
    # A2-fired -> P0; persistent-RED>=3wk -> P0; RED -> P1; AMBER -> P2; else routine
    priority = "routine"
    priority_reasons = []
    if a2_fire:
        priority = "P0"; priority_reasons.append("A2 battery-cascade fired")
    if pers_streak >= 3:
        if priority != "P0":
            priority = "P0"
        priority_reasons.append(f"persistent RED {pers_streak} weeks")
    if priority == "routine":
        if prod_tier == "RED":
            priority = "P1"; priority_reasons.append("RED tier")
        elif prod_tier == "AMBER":
            priority = "P2"; priority_reasons.append("AMBER tier")

    # Window evidence state selection
    if a2_fire:
        window_state = "A2_battery_cascade_fired"
    elif pers_end_fire and prod_tier == "RED":
        window_state = "persistence_terminal_AND_RED_tier"
    elif prod_tier == "RED":
        window_state = "RED_tier_no_channel_yet"
    elif prod_tier == "AMBER":
        window_state = "AMBER_tier_no_channel"
    elif sma_dead_badge and (prod_tier in ("RED","AMBER")):
        window_state = "SILENT_SMA_30d_while_RED_or_AMBER"
    else:
        window_state = "GREEN_tier_channel_fires_eventually"
    win = fw_by_state[window_state]

    # Drivers (linear attribution = coef_std × z-score)
    drivers = []
    for i, feat in enumerate(MODAL_FEATURES):
        raw_val  = float(X_imp.iloc[idx][feat])
        was_imputed = pd.isna(fm_full.iloc[idx][feat])
        # z-score
        z = float((raw_val - scaler.mean_[i]) / scaler.scale_[i])
        contribution = float(coefs_std[i] * z)
        direction = "toward failure" if contribution > 0 else "protective"
        # Fleet percentile (among all 34)
        pct = float(percentileofscore(fleet_vals[feat], raw_val, kind="rank"))
        # Plain-English gloss
        feat_label, feat_phys, feat_sign = PHYSICS_GLOSS[feat]
        # Build gloss
        if feat == "vsi_withinwk_std_ratio_30d_w":
            gloss = (f"within-week voltage noise is {raw_val:.2f}x own baseline — "
                     f"{'worst' if pct>=90 else 'elevated' if pct>=60 else 'moderate' if pct>=40 else 'low'} "
                     f"{pct:.0f}th fleet percentile; z={z:+.2f}")
        elif feat == "rest_vsi_p05_delta90":
            gloss = (f"rest-voltage floor delta = {raw_val:+.3f} V vs own baseline — "
                     f"{'strong sagging (battery cascade risk)' if raw_val < -1 else 'mild sagging' if raw_val < -0.2 else 'stable/rising' if raw_val >= 0 else 'slight decline'}; "
                     f"z={z:+.2f}, {pct:.0f}th fleet pctile")
        elif feat == "vsi_range_trend":
            gloss = (f"drive-voltage range trend = {raw_val:+.4f} V/wk — "
                     f"{'widening (risk direction univariately)' if raw_val > 0 else 'flat/narrowing'}; "
                     f"z={z:+.2f}, {pct:.0f}th fleet pctile; NOTE: multivariate suppressor (see coefficient table)")
        elif feat == "dip_depth_last90_delta":
            gloss = (f"crank dip depth delta = {raw_val:+.3f} V vs baseline — "
                     f"{'deepening dips (heavier load signature)' if raw_val > 0.2 else 'stable/shallow' if raw_val < 0.1 else 'borderline'}; "
                     f"z={z:+.2f}, {pct:.0f}th fleet pctile")
        else:
            gloss = f"z={z:+.2f}, {pct:.0f}th fleet pctile"

        drivers.append({
            "feature": feat,
            "raw_value": round(raw_val, 6),
            "imputed": bool(was_imputed),
            "z_score": round(z, 4),
            "fleet_percentile": round(pct, 1),
            "contribution_std": round(contribution, 6),
            "direction": direction,
            "gloss": gloss,
        })

    # Sort by |contribution| descending
    drivers.sort(key=lambda d: abs(d["contribution_std"]), reverse=True)

    # Counterfactual: top positive driver that can bring prod prob below 0.35
    # Linear: need decision_value s.t. platt gives prob < 0.35
    # platt: prob = sigmoid(a * dv + b), need dv s.t. prob < 0.35
    # dv_target = (logit(0.35) - platt.intercept_[0]) / platt.coef_[0][0]
    from scipy.special import logit as scipy_logit
    dv_target = (scipy_logit(0.35) - platt.intercept_[0]) / platt.coef_[0][0]
    delta_dv_needed = dv_target - dec_val  # how much decision value needs to change

    # Find top positive contributor
    pos_drivers = [d for d in drivers if d["direction"] == "toward failure"]
    if pos_drivers:
        top_pos = pos_drivers[0]
        feat_idx = MODAL_FEATURES.index(top_pos["feature"])
        c_std = coefs_std[feat_idx]
        if abs(c_std) > 1e-8:
            # delta_z needed to achieve delta_dv
            delta_z_needed = delta_dv_needed / c_std
            delta_raw_needed = delta_z_needed * scaler.scale_[feat_idx]
            new_raw = top_pos["raw_value"] + delta_raw_needed
            # plausibility check: is new_raw within reasonable range?
            feat_min = float(X_imp[top_pos["feature"]].min())
            feat_max = float(X_imp[top_pos["feature"]].max())
            plausible = feat_min <= new_raw <= feat_max * 3  # generous range
            if plausible:
                cfact_text = (
                    f"Reducing {top_pos['feature']} by {abs(delta_raw_needed):.3f} units "
                    f"(from {top_pos['raw_value']:.3f} to {new_raw:.3f}) would move production prob "
                    f"below 0.35 (GREEN threshold), all else equal. "
                    f"[delta_z = {delta_z_needed:+.3f}]"
                )
            else:
                cfact_text = (
                    f"Changing {top_pos['feature']} by {abs(delta_raw_needed):.3f} units "
                    f"(to {new_raw:.3f}) would theoretically cross the GREEN threshold, "
                    f"but this value is outside plausible fleet range [{feat_min:.3f}, {feat_max:.3f}]. "
                    f"Multiple drivers are concurrently elevated; single-feature counterfactual is not achievable."
                )
        else:
            cfact_text = "Counterfactual not computable — coefficient effectively zero."
    elif prod_prob < TIER_GREEN_MAX:
        cfact_text = "Already GREEN — no counterfactual needed."
    else:
        cfact_text = "No positive-direction drivers identified; production prob driven by suppressor/intercept interactions."

    # Assemble card dict
    card = {
        "vin_label": vin,
        "failed": failed,
        "config_version": CONFIG_VERSION,
        "generated": GEN_DATE,
        "model_hash_inputs": feat_str,
        "model_hash": model_hash,
        "validation_auroc_nested_lovo": NESTED_AUROC,
        "validation_ci": [NESTED_CI_LO, NESTED_CI_HI],
        "production_note": (
            "Production fit = post-validation standard refit on all-34. "
            "In-sample AUROC is expected to exceed validation-of-record (it sees all data). "
            f"In-sample AUROC = {insample_auroc:.4f}."
        ),
        "tier_production": prod_tier,
        "prob_production": round(prod_prob, 4),
        "prob_oof": round(oof_prob, 4) if not np.isnan(oof_prob) else None,
        "tier_oof": oof_tier,
        "decision_value_production": round(dec_val, 6),
        "priority": priority,
        "priority_reasons": priority_reasons,
        "archetype": archetype_key,
        "archetype_flags": archetype_flags,
        "physics_mode": physics_mode,
        "badges": {
            "sma_dead": sma_dead_badge,
            "watchlist": watchlist_badge,
        },
        "drivers": drivers,
        "channel_history": {
            "a1_fire": a1_fire,
            "a2_fire": a2_fire,
            "persistence_terminal_fire": pers_end_fire,
            "first_channel": first_channel,
            "first_fire_date": first_fire_date,
            "persistent_red_streak_weeks": pers_streak,
            "channel_fp_record": {
                "a2_nf_false_alarms": "0/20 NF (very clean channel)",
                "a1_nf_note": "A1 fires on 4 NF trucks (VIN15/16/17/4) — true alarm rate uncertain without JCO reference",
                "persistence_nf_fp": "4/20 NF end in persistence fire state",
            }
        },
        "window_evidence": {
            "state": window_state,
            "n": win["n"],
            "median_lead_d": win["median_lead_d"],
            "bootstrap_95ci_lo_d": win["ci_lo"],
            "bootstrap_95ci_hi_d": win["ci_hi"],
            "scheduling_window": win["scheduling_window"],
            "caveat": win["caveat"],
            "NOT_a_countdown_clock": True,
        },
        "counterfactual": cfact_text,
        "confidence_block": {
            "validation_of_record": f"nested LOVO AUROC {NESTED_AUROC} / CI [{NESTED_CI_LO}, {NESTED_CI_HI}]",
            "oof_tier_error_rates": {
                "RED_failed_n": 10, "RED_nf_n": 2, "RED_total_failed": 14, "RED_total_nf": 20,
                "AMBER_failed_n": 0, "AMBER_nf_n": 2,
                "GREEN_failed_n": 4, "GREEN_nf_n": 16,
            },
            "badges_applied": {
                "sma_dead": sma_dead_badge,
                "watchlist": watchlist_badge,
                "immature_na": False,
            },
            "sma_dead_note": (
                "SMA-dead badge: crank-channel data is absent (SMA always 0 or silent). "
                "VSI-based channels remain valid but A1 crank channel is masked."
            ) if sma_dead_badge else None,
            "watchlist_note": (
                "Watchlist badge: non-failed truck with elevated risk indicators; enhanced monitoring recommended."
            ) if watchlist_badge else None,
        },
    }
    all_cards.append(card)

# ── Generate Markdown cards ───────────────────────────────────────────────────
print("\nGenerating markdown cards...", flush=True)

TIER_EMOJI = {"GREEN": "🟢 GREEN", "AMBER": "🟡 AMBER", "RED": "🔴 RED"}

def tier_badge(t):
    return {"GREEN": "[GREEN]", "AMBER": "[AMBER]", "RED": "[RED]"}[t]

def fmt_prob(p):
    return f"{p:.4f}" if p is not None else "N/A"

for card in all_cards:
    vin = card["vin_label"]
    md_lines = []
    tb = tier_badge(card["tier_production"])
    oof_tb = tier_badge(card["tier_oof"]) if card["tier_oof"] not in ("N/A","") else "N/A"

    # (a) Header
    md_lines.append(f"# Evidence Card — {vin}")
    md_lines.append("")
    md_lines.append(f"| Field | Value |")
    md_lines.append(f"|---|---|")
    md_lines.append(f"| VIN | `{vin}` |")
    md_lines.append(f"| Tier (production prob) | **{tb}** |")
    md_lines.append(f"| Production probability | `{fmt_prob(card['prob_production'])}` |")
    md_lines.append(f"| OOF probability (honest) | `{fmt_prob(card['prob_oof'])}` ({oof_tb}) |")
    md_lines.append(f"| Failed | `{'Yes' if card['failed'] else 'No'}` |")
    md_lines.append(f"| Priority | **{card['priority']}** ({'; '.join(card['priority_reasons']) if card['priority_reasons'] else 'none'}) |")
    badges = []
    if card["badges"]["sma_dead"]: badges.append("SMA-DEAD")
    if card["badges"]["watchlist"]: badges.append("WATCHLIST")
    if badges:
        md_lines.append(f"| Badges | `{', '.join(badges)}` |")
    md_lines.append("")
    md_lines.append("> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).")
    md_lines.append("")

    # (b) Archetype
    md_lines.append("## (b) Archetype & Physics Mode")
    md_lines.append("")
    md_lines.append(f"- **Archetype:** `{card['archetype']}` — flags: `{card['archetype_flags']}`")
    md_lines.append(f"- **Physics mode:** {card['physics_mode']}")
    md_lines.append("")

    # (c) Drivers
    md_lines.append("## (c) Drivers (sorted by |contribution|)")
    md_lines.append("")
    md_lines.append("| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |")
    md_lines.append("|---|---|---|---|---|---|---|---|")
    for r, d in enumerate(card["drivers"], 1):
        contrib_str = f"`{d['contribution_std']:+.4f}`"
        imputed_flag = " *(imputed)*" if d["imputed"] else ""
        md_lines.append(
            f"| {r} | `{d['feature']}` | `{d['raw_value']:.4f}`{imputed_flag} | "
            f"`{d['fleet_percentile']:.1f}`th | `{d['z_score']:+.3f}` | "
            f"{contrib_str} | {d['direction']} | {d['gloss']} |"
        )
    md_lines.append("")
    md_lines.append("**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.")
    md_lines.append("")

    # (d) Channel history
    ch = card["channel_history"]
    md_lines.append("## (d) Channel History")
    md_lines.append("")
    md_lines.append(f"| Channel | Fired? | Notes |")
    md_lines.append(f"|---|---|---|")
    if card["badges"]["sma_dead"]:
        md_lines.append(f"| A1 (crank burst) | MASKED (SMA-dead) | Crank-event data absent; channel not evaluable |")
    else:
        md_lines.append(f"| A1 (crank burst) | `{ch['a1_fire']}` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |")
    md_lines.append(f"| A2 (battery cascade) | `{ch['a2_fire']}` | Validated FP record: 0/20 NF false alarms (clean channel) |")
    md_lines.append(f"| Persistence (RED >=3wk) | `{ch['persistence_terminal_fire']}` (terminal); streak=`{ch['persistent_red_streak_weeks']}` wk | Validated FP: 4/20 NF end in persistence fire state |")
    md_lines.append(f"| First channel / first fire date | `{ch['first_channel']}` / `{ch['first_fire_date']}` | — |")
    if card["badges"]["sma_dead"]:
        md_lines.append("")
        md_lines.append("> **SMA-DEAD:** Crank-event channels (A1) are not available for this truck. VSI persistence channel remains valid. If SMA is dead while tier is RED/AMBER, trigger manual inspection within 72 hours.")
    md_lines.append("")

    # (e) Window
    w = card["window_evidence"]
    md_lines.append("## (e) Evidence Window")
    md_lines.append("")
    md_lines.append(f"- **Evidence state:** `{w['state']}`")
    md_lines.append(f"- **Empirical n:** {w['n']} (retrospective fleet)")
    if w["median_lead_d"] is not None:
        md_lines.append(f"- **Median lead to failure:** {w['median_lead_d']:.0f} days")
        if w["bootstrap_95ci_lo_d"] is not None:
            md_lines.append(f"- **95% bootstrap CI:** [{w['bootstrap_95ci_lo_d']:.0f}d, {w['bootstrap_95ci_hi_d']:.0f}d]")
    else:
        md_lines.append(f"- **Median lead:** no empirical data (n=0 or SMA-dead special class)")
    md_lines.append(f"- **Scheduling window:** {w['scheduling_window']}")
    md_lines.append(f"- **Honest caveat:** {w['caveat']}")
    md_lines.append(f"- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.")
    md_lines.append("")

    # (f) Counterfactual
    md_lines.append("## (f) Counterfactual")
    md_lines.append("")
    md_lines.append(card["counterfactual"])
    md_lines.append("")

    # (g) Confidence block
    cb = card["confidence_block"]
    md_lines.append("## (g) Confidence Block")
    md_lines.append("")
    md_lines.append(f"- **Validation of record:** {cb['validation_of_record']}")
    md_lines.append(f"- **OOF tier error rates (n=34):**")
    oer = cb["oof_tier_error_rates"]
    md_lines.append(f"  - RED: {oer['RED_failed_n']}/14 failed correctly RED; {oer['RED_nf_n']}/20 NF false positives")
    md_lines.append(f"  - AMBER: {oer['AMBER_failed_n']}/14 failed scored AMBER; {oer['AMBER_nf_n']}/20 NF scored AMBER")
    md_lines.append(f"  - GREEN: {oer['GREEN_failed_n']}/14 failed missed (GREEN); {oer['GREEN_nf_n']}/20 NF correctly GREEN")
    if cb["sma_dead_note"]:
        md_lines.append(f"- **SMA-DEAD:** {cb['sma_dead_note']}")
    if cb["watchlist_note"]:
        md_lines.append(f"- **WATCHLIST:** {cb['watchlist_note']}")
    md_lines.append("")

    # (h) Footer
    md_lines.append("## (h) Model Provenance")
    md_lines.append("")
    md_lines.append(f"- **Features:** `{' | '.join(MODAL_FEATURES)}`")
    md_lines.append(f"- **Alpha:** {ALPHA}")
    md_lines.append(f"- **Model hash (feature+alpha SHA-256 prefix):** `{card['model_hash']}`")
    md_lines.append(f"- **Config version:** {CONFIG_VERSION}")
    md_lines.append(f"- **Generated:** {GEN_DATE}")
    md_lines.append(f"- **In-sample AUROC (production fit):** {insample_auroc:.4f} (labeled IN-SAMPLE — not validation; validation AUROC = {NESTED_AUROC})")
    md_lines.append("")

    # Write card
    out_path = f"{OUTDIR}/card_{vin}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

print(f"  Written {len(all_cards)} cards.", flush=True)

# ── cards.json ────────────────────────────────────────────────────────────────
print("Writing cards.json...", flush=True)
with open(f"{OUTDIR}/cards.json", "w", encoding="utf-8") as f:
    json.dump(all_cards, f, indent=2, ensure_ascii=False, default=str)

# ── fleet_ranking.md ──────────────────────────────────────────────────────────
print("Writing fleet_ranking.md...", flush=True)

# Sort: P0 first, then P1, P2, routine; within each by prod_prob desc
priority_order = {"P0": 0, "P1": 1, "P2": 2, "routine": 3}
all_cards_sorted = sorted(all_cards, key=lambda c: (priority_order[c["priority"]], -c["prob_production"]))

ranking_lines = []
ranking_lines.append("# Fleet Ranking — Starter Motor V2 Evidence Cards")
ranking_lines.append(f"*Generated {GEN_DATE} | Config {CONFIG_VERSION} | Validation AUROC {NESTED_AUROC} CI [{NESTED_CI_LO}, {NESTED_CI_HI}]*")
ranking_lines.append("")
ranking_lines.append(
    "| # | VIN | Tier | Prob (prod) | Prob (OOF) | Top Driver | Active Channels | Window | Badges | Priority |"
)
ranking_lines.append("|---|---|---|---|---|---|---|---|---|---|")

for rank_i, card in enumerate(all_cards_sorted, 1):
    vin = card["vin_label"]
    tb  = card["tier_production"]
    pp  = f"{card['prob_production']:.3f}"
    op  = f"{card['prob_oof']:.3f}" if card["prob_oof"] is not None else "N/A"
    top_d = card["drivers"][0] if card["drivers"] else {}
    top_driver_phrase = (
        f"{top_d['feature'].replace('_',' ')} ({'+' if top_d['direction']=='toward failure' else '-'}{abs(top_d['contribution_std']):.2f})"
        if top_d else "—"
    )
    # Active channels
    ch = card["channel_history"]
    active_ch = []
    if ch["a2_fire"]: active_ch.append("A2")
    if ch["a1_fire"] not in ("False", "n/a (SMA-dead)", "false"): active_ch.append("A1")
    if ch["persistence_terminal_fire"]: active_ch.append("pers")
    if ch["persistent_red_streak_weeks"] >= 3: active_ch.append(f"RED-{ch['persistent_red_streak_weeks']}wk")
    ch_str = ", ".join(active_ch) if active_ch else "none"

    # Window summary
    w = card["window_evidence"]
    if w["median_lead_d"] is not None:
        win_str = f"{w['state'].split('_')[0]} {w['median_lead_d']:.0f}d (n={w['n']})"
    else:
        win_str = f"{w['state'][:20]} n={w['n']}"

    # Badges
    badge_str = " ".join(b for b, v in [("SMA-DEAD", card["badges"]["sma_dead"]),
                                         ("WATCHLIST", card["badges"]["watchlist"])] if v)
    badge_str = badge_str or "—"

    ranking_lines.append(
        f"| {rank_i} | `{vin}` | {tb} | {pp} | {op} | {top_driver_phrase} | {ch_str} | {win_str} | {badge_str} | **{card['priority']}** |"
    )

ranking_lines.append("")
ranking_lines.append("### Legend")
ranking_lines.append("- Tier: GREEN < 0.35 <= AMBER < 0.55 <= RED (on production Platt-calibrated probability)")
ranking_lines.append("- Prob: production = in-sample Platt; OOF = honest nested-LOVO recalibrated probability")
ranking_lines.append("- Top Driver: signed standardized contribution (coef_std x z); positive = toward failure")
ranking_lines.append("- Active Channels: A2=battery cascade; A1=crank burst; pers=persistence terminal fire; RED-Nwk=persistent-RED streak")
ranking_lines.append("- Window: evidence state + median lead (NOT a countdown clock)")
ranking_lines.append("- Priority: P0=immediate (A2 fired or persistent-RED>=3wk); P1=RED tier; P2=AMBER; routine=GREEN")
ranking_lines.append(f"- OOF tier rates: RED 10/14F 2/20NF | AMBER 0/14F 2/20NF | GREEN 4/14F 16/20NF")

with open(f"{OUTDIR}/fleet_ranking.md", "w", encoding="utf-8") as f:
    f.write("\n".join(ranking_lines))

# ── cards_README.md ───────────────────────────────────────────────────────────
print("Writing cards_README.md...", flush=True)
readme_lines = [
    "# V2 Evidence Cards — README & Regeneration Guide",
    "",
    f"Config version: {CONFIG_VERSION} | Generated: {GEN_DATE}",
    "",
    "## Contents",
    "",
    "| File | Description |",
    "|---|---|",
    "| `card_{VIN}.md` (x34) | Per-truck evidence card in Markdown |",
    "| `cards.json` | Machine-readable equivalent of all 34 cards |",
    "| `fleet_ranking.md` | Planner-facing sorted fleet table |",
    "| `cards_README.md` | This file |",
    "| `generate_cards.py` | Regeneration script |",
    "",
    "## Production Fit vs Validation-of-Record",
    "",
    "**Validation of record** is the **nested LOVO (leave-one-VIN-out) cross-validation** result:",
    f"- AUROC = {NESTED_AUROC}, 95% CI [{NESTED_CI_LO}, {NESTED_CI_HI}] (n=34, bootstrapped)",
    "- This is the **honest estimate** of generalization performance.",
    "- The per-truck OOF (out-of-fold) probabilities shown on each card come from this procedure.",
    "",
    "**Production fit** is a **standard post-validation refit**:",
    "- Trained on all 34 trucks (median-imputed, StandardScaler, RidgeClassifier alpha=1.0, Platt calibration).",
    "- This is intentional: once validation confirms the model is trustworthy, the production model uses all available data.",
    f"- In-sample AUROC of the production fit = {insample_auroc:.4f} (labeled IN-SAMPLE throughout; expected to exceed {NESTED_AUROC}).",
    "- The production probability on each card comes from this fit.",
    "",
    "**Both are shown** because:",
    "1. Production prob = best current estimate for routing/prioritization.",
    "2. OOF prob = honest evaluation-era estimate; shows how the model behaved when it had NOT seen this truck.",
    "",
    "## Regeneration",
    "",
    "```bash",
    "cd D:/Daimler-starter_motor_alternator_battery",
    "py -3 'STARTER MOTOR/V2_program/v2_system/cards/generate_cards.py'",
    "```",
    "",
    "Dependencies: pandas, numpy, scikit-learn, scipy.",
    "",
    "## Features (modal 4)",
    "",
    "| Feature | Physics | Expected Sign |",
    "|---|---|---|",
    "| `vsi_withinwk_std_ratio_30d_w` | Within-week supply-voltage noise vs own 40-wk baseline | + |",
    "| `rest_vsi_p05_delta90` | Engine-off rest-voltage 5th-pctile delta vs baseline (last 90d) | - (down = risk) |",
    "| `vsi_range_trend` | Drive-voltage range trend (V/wk) over last 12 wks | + univariate; **SUPPRESSOR in multivariate** (r=+0.82 with noise ratio) |",
    "| `dip_depth_last90_delta` | Crank dip depth delta vs own baseline (last 90d) | + |",
    "",
    "## Tier Thresholds",
    "",
    "| Tier | Condition |",
    "|---|---|",
    "| GREEN | production prob < 0.35 |",
    "| AMBER | 0.35 <= production prob < 0.55 |",
    "| RED | production prob >= 0.55 |",
    "",
    "## Priority Logic",
    "",
    "| Priority | Condition |",
    "|---|---|",
    "| P0 | A2 channel fired, OR persistent RED >= 3 weeks (from walking_scores.csv) |",
    "| P1 | RED tier (no P0 condition) |",
    "| P2 | AMBER tier |",
    "| routine | GREEN tier, no channel fires |",
    "",
    "## SMA-Dead Cohort",
    "",
    "VINs: VIN8_F_SM, VIN9_F_SM, VIN10_NF_SM, VIN11_NF_SM, VIN12_NF_SM, VIN13_NF_SM, VIN20_NF_SM.",
    "A1 crank-burst channel is masked/not evaluable. VSI-based features and channels remain valid.",
    "",
    "## Watchlist NF VINs",
    "",
    "VINs: VIN2_NF_SM, VIN5_NF_SM, VIN8_NF_SM, VIN15_NF_SM.",
    "Non-failed trucks with elevated risk indicators — enhanced monitoring cadence recommended.",
]

with open(f"{OUTDIR}/cards_README.md", "w", encoding="utf-8") as f:
    f.write("\n".join(readme_lines))

# ── Final summary ─────────────────────────────────────────────────────────────
print("\n" + "="*70, flush=True)
print("GENERATION COMPLETE", flush=True)
print(f"  Cards: {len(all_cards)} (34 trucks)", flush=True)
print(f"  Output: {OUTDIR}", flush=True)
print(f"  In-sample AUROC: {insample_auroc:.4f}", flush=True)
print(f"  Validation AUROC: {NESTED_AUROC}", flush=True)
print(f"  Model hash: {model_hash}", flush=True)
print(f"  Files: {4 + len(all_cards)} total", flush=True)

# Coefficient summary
print("\nCoefficient summary:", flush=True)
for feat, c_std, c_raw in zip(MODAL_FEATURES, coefs_std, coefs_raw):
    phys_sign = PHYSICS_GLOSS[feat][2]
    actual_sign = "+" if c_std > 0 else "-"
    match = "OK" if actual_sign == phys_sign else "FLAGGED"
    if feat == "vsi_range_trend":
        match = "KNOWN-SUPPRESSOR"
    print(f"  {feat}: std={c_std:+.4f} raw={c_raw:+.6f} expected={phys_sign} actual={actual_sign} [{match}]")

# Spot checks
print("\nSpot checks:", flush=True)
for card in all_cards:
    if card["vin_label"] == "VIN6_F_SM":
        print(f"  VIN6_F_SM: tier={card['tier_production']} a2_fire={card['channel_history']['a2_fire']} archetype={card['archetype']}")
        print(f"    drivers[0]: {card['drivers'][0]['feature']} contrib={card['drivers'][0]['contribution_std']:.4f}")
        print(f"    drivers[1]: {card['drivers'][1]['feature']} contrib={card['drivers'][1]['contribution_std']:.4f}")
    if card["vin_label"] == "VIN9_F_SM":
        print(f"  VIN9_F_SM: tier={card['tier_production']} sma_dead={card['badges']['sma_dead']} a1={card['channel_history']['a1_fire']} a2={card['channel_history']['a2_fire']}")
