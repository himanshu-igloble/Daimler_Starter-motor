---
title: "V1.1 Starter Motor — Per-VIN Explanation Cards (X5, Layer 4)"
status: "complete"
created: "2026-06-10"
---

# V1.1 SM — Explanation Cards (all 34 trucks)

Model: **V1.1-SM RidgeClassifier(alpha=1.0), 4 features, production refit 2026-06-10**.
Attribution: exact linear decomposition `contribution_i = coef_i x z_i` on standardized
features — for a linear model this **is** the SHAP decomposition (phi_i = coef_i x
(z_i − E[z_i]) and E[z_i] = 0 after standardization); no SHAP library required.
**Shipped probability/tier = nested-LOVO out-of-fold recalibrated values (X2)**; the
production refit (all 34 trucks) is used only for attribution and counterfactuals, and
its resubstitution AUROC (0.957) is *not* a performance claim — the honest
number is nested OOF **0.9321**.
Counterfactuals: smallest single-feature change in **raw units** crossing the nearest
tier boundary, via a sigmoid bridge from production decision values to the OOF
recalibrated probability scale (Spearman 0.969, RMSE 0.069);
they are *ceteris paribus* statements, not repair prescriptions.
Tiers: GREEN < 0.35 <= AMBER < 0.55 <= RED.

## Global: coefficients & physics-direction check

| feature | meaning | coef (std) | coef (per raw unit) | expected sign (physics) | verdict |
|---|---|---|---|---|---|
| `vsi_withinwk_std_ratio_30d_w` | within-week VSI noise ratio (last 4 wk / own 40-wk baseline) | +0.8862 | +1.4450 | + (rising within-week electrical noise = volatility drift) | **matches physics** |
| `rest_vsi_p05_delta90` | rest-VSI floor delta, last ~90 d vs own baseline (battery-step aware) | -0.2704 | -0.3249 | - (falling engine-off rest-voltage floor = battery floor sagging vs own baseline) | **matches physics** |
| `vsi_range_trend` | weekly drive-VSI range (p95-p05) Theil-Sen slope, last 12 wk | -0.4139 | -6.3605 | + (widening weekly drive-voltage envelope = regulation instability / electrical degradation) | **suppressor — flagged** (univariate AUROC 0.732 matches physics; multivariate sign flipped by r=+0.82 collinearity with the noise ratio) |
| `dip_depth_last90_delta` | crank dip-depth delta, last 90 d vs own baseline | +0.1409 | +0.1503 | + (crank dips deepening vs own baseline = battery/cascade load signature) | **matches physics** |

All 4 features match physics direction **univariately** (raw AUROC vs failure);
3/4 multivariate coefficient signs also match. The exception,
`vsi_range_trend`, is a classic ridge **suppressor**: physics-consistent on its own
(widening envelope = risk) but r=+0.82 with the dominant noise-ratio feature, so the
model assigns it a corrective negative weight. Per-VIN glosses state the physical
value honestly and flag the model's suppressor use separately.
Intercept (std space): -0.1765. Imputation medians (production): `vsi_withinwk_std_ratio_30d_w`=1.000, `rest_vsi_p05_delta90`=0.021, `vsi_range_trend`=0.000, `dip_depth_last90_delta`=0.216.

### Pairwise feature correlation (Pearson, raw values, pairwise-complete)

| | `vsi_0` | `rest_1` | `vsi_2` | `dip_3` |
|---|---|---|---|---|
| `vsi_withinwk_std_ratio_30d_w` | +1.00 | -0.21 | +0.82 | +0.27 |
| `rest_vsi_p05_delta90` | -0.21 | +1.00 | -0.38 | -0.76 |
| `vsi_range_trend` | +0.82 | -0.38 | +1.00 | +0.49 |
| `dip_depth_last90_delta` | +0.27 | -0.76 | +0.49 | +1.00 |

(Spearman in the JSON. Max |off-diagonal Pearson| = 0.82 — the four features carry substantially independent information.)


---

## Per-VIN cards (ordered by recalibrated OOF probability, highest risk first)

### VIN6_F_SM — FAILED — **RED**, P(recal) = 0.998
- **Archetype**: A2 (A2_battery_cascade)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 2.067 | z = +1.36 | contribution +1.202 (toward failure): within-week voltage noise is 2.07x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.200 | z = +2.62 | contribution -1.084 (protective): weekly voltage range widening at +0.200 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -3.153 | z = -3.54 | contribution +0.957 (toward failure): engine-off rest-voltage floor moved -3.15 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 4.123 | z = +4.11 | contribution +0.579 (toward failure): crank voltage dips +4.12 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 1.06 x (ratio) (vsi_withinwk_std_ratio_30d_w: 2.07 -> 1.01), all else equal.

### VIN14_F_SM — FAILED — **RED**, P(recal) = 0.998
- **Archetype**: A1+A2 (A1+A2_mixed)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 2.543 | z = +2.13 | contribution +1.890 (toward failure): within-week voltage noise is 2.54x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.202 | z = +2.65 | contribution -1.096 (protective): weekly voltage range widening at +0.202 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -1.603 | z = -1.68 | contribution +0.454 (toward failure): engine-off rest-voltage floor moved -1.60 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.986 | z = +0.76 | contribution +0.107 (toward failure): crank voltage dips +0.99 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.85 x (ratio) (vsi_withinwk_std_ratio_30d_w: 2.54 -> 1.69), all else equal.

### VIN10_F_SM — FAILED — **RED**, P(recal) = 0.995
- **Archetype**: A1 (A1_solenoid_intermittency)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 2.534 | z = +2.12 | contribution +1.877 (toward failure): within-week voltage noise is 2.53x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.066 | z = +0.55 | contribution -0.229 (protective): weekly voltage range widening at +0.066 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.793 | z = -1.14 | contribution -0.160 (protective): crank dip depth -0.79 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = 0.185 | z = +0.47 | contribution -0.127 (protective): rest-voltage floor +0.18 V vs own baseline -- battery floor stable/recovering (protective)
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.85 x (ratio) (vsi_withinwk_std_ratio_30d_w: 2.53 -> 1.68), all else equal.

### VIN5_F_SM — FAILED — **RED**, P(recal) = 0.992
- **Archetype**: A4 (A4_silent_abrupt)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 3.066 | z = +2.99 | contribution +2.647 (toward failure): within-week voltage noise is 3.07x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.198 | z = +2.59 | contribution -1.072 (protective): weekly voltage range widening at +0.198 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.785 | z = +1.19 | contribution -0.322 (protective): rest-voltage floor +0.79 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.77 x (ratio) (vsi_withinwk_std_ratio_30d_w: 3.07 -> 2.29), all else equal.
- **Caveats**:
  - Zero crank events / no VSI in final 120 d window: dip_depth_last90_delta IMPUTED; card rests on weekly VSI only.
  - Silent gap of 32 d before failure: features describe the pre-silence state; the terminal period is untelemetered.

### VIN11_F_SM — FAILED — **RED**, P(recal) = 0.958
- **Archetype**: A3 (A3_vsi_volatility_only)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 2.046 | z = +1.32 | contribution +1.173 (toward failure): within-week voltage noise is 2.05x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.067 | z = +0.57 | contribution -0.236 (protective): weekly voltage range widening at +0.067 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 1.100 | z = +0.88 | contribution +0.124 (toward failure): crank voltage dips +1.10 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
  - `rest_vsi_p05_delta90` = 0.022 | z = +0.27 | contribution -0.074 (protective): rest-voltage floor +0.02 V vs own baseline -- battery floor stable/recovering (protective)
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.59 x (ratio) (vsi_withinwk_std_ratio_30d_w: 2.05 -> 1.45), all else equal.

### VIN5_NF_SM — **RED**, P(recal) = 0.958
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `rest_vsi_p05_delta90` = -1.190 | z = -1.18 | contribution +0.319 (toward failure): engine-off rest-voltage floor moved -1.19 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 1.107 | z = -0.21 | contribution -0.185 (protective): within-week voltage noise at 1.11x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `dip_depth_last90_delta` = 0.927 | z = +0.70 | contribution +0.098 (toward failure): crank voltage dips +0.93 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.20 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.11 -> 0.90), all else equal.
- **Caveats**:
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN12_F_SM — FAILED — **RED**, P(recal) = 0.955
- **Archetype**: A3 (A3_vsi_volatility_only)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 2.206 | z = +1.58 | contribution +1.403 (toward failure): within-week voltage noise is 2.21x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.100 | z = +1.08 | contribution -0.448 (protective): weekly voltage range widening at +0.100 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.055 | z = -0.35 | contribution -0.049 (protective): crank dip depth -0.06 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = -0.092 | z = +0.14 | contribution -0.037 (protective): rest-voltage floor -0.09 V vs own baseline -- battery floor stable/recovering (protective)
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.51 x (ratio) (vsi_withinwk_std_ratio_30d_w: 2.21 -> 1.69), all else equal.

### VIN7_F_SM — FAILED — **RED**, P(recal) = 0.906
- **Archetype**: A3 (A3_vsi_volatility_only)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 1.865 | z = +1.03 | contribution +0.911 (toward failure): within-week voltage noise is 1.86x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `vsi_range_trend` = 0.079 | z = +0.76 | contribution -0.316 (protective): weekly voltage range widening at +0.079 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -0.462 | z = -0.31 | contribution +0.083 (toward failure): engine-off rest-voltage floor moved -0.46 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.207 | z = -0.07 | contribution -0.010 (protective): crank dip depth +0.21 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.37 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.86 -> 1.49), all else equal.

### VIN2_F_SM — FAILED — **RED**, P(recal) = 0.904
- **Archetype**: A2 (A2_battery_cascade)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `rest_vsi_p05_delta90` = -1.657 | z = -1.74 | contribution +0.471 (toward failure): engine-off rest-voltage floor moved -1.66 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 1.577 | z = +1.39 | contribution +0.196 (toward failure): crank voltage dips +1.58 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 1.154 | z = -0.13 | contribution -0.116 (protective): within-week voltage noise at 1.15x own baseline -- quiet, fleet-typical electrical behaviour (protective)
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.42 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.15 -> 0.73), all else equal.

### VIN8_F_SM — FAILED — **RED**, P(recal) = 0.716
- **Archetype**: A4 (A4_silent_abrupt)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = -0.044 | z = -1.14 | contribution +0.470 (toward failure): weekly voltage range trend -0.044 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 1.140 | z = -0.15 | contribution -0.137 (protective): within-week voltage noise at 1.14x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = -0.389 | z = -0.22 | contribution +0.059 (toward failure): engine-off rest-voltage floor moved -0.39 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.18 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.14 -> 0.96), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.
  - Silent gap of 37 d before failure: features describe the pre-silence state; the terminal period is untelemetered.
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN13_F_SM — FAILED — **RED**, P(recal) = 0.654
- **Archetype**: A2 (A2_battery_cascade)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = -0.080 | z = -1.68 | contribution +0.697 (toward failure): weekly voltage range trend -0.080 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 0.936 | z = -0.49 | contribution -0.432 (protective): within-week voltage noise at 0.94x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = -0.655 | z = -0.54 | contribution +0.146 (toward failure): engine-off rest-voltage floor moved -0.66 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.582 | z = +0.33 | contribution +0.047 (toward failure): crank voltage dips +0.58 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would drop RED -> AMBER if within-week noise ratio fell by 0.23 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.94 -> 0.71), all else equal.

### VIN20_NF_SM — **RED**, P(recal) = 0.623
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.183 | z = +0.47 | contribution -0.126 (protective): rest-voltage floor +0.18 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_withinwk_std_ratio_30d_w` = 1.261 | z = +0.04 | contribution +0.039 (toward failure): within-week voltage noise is 1.26x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would escalate AMBER -> RED if within-week noise ratio rose by 0.03 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.26 -> 1.29), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.
  - Production-refit tier (AMBER) differs from shipped OOF tier (RED); counterfactual is in production space.

### VIN2_NF_SM — **AMBER**, P(recal) = 0.452
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = -0.012 | z = -0.64 | contribution +0.265 (toward failure): weekly voltage range trend -0.012 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 1.075 | z = -0.26 | contribution -0.230 (protective): within-week voltage noise at 1.08x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.020 | z = +0.27 | contribution -0.073 (protective): rest-voltage floor +0.02 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.253 | z = -0.02 | contribution -0.003 (protective): crank dip depth +0.25 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would return to GREEN if within-week noise ratio fell by 0.05 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.08 -> 1.02), all else equal.

### VIN10_NF_SM — **AMBER**, P(recal) = 0.435
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.776 | z = -0.75 | contribution -0.662 (protective): within-week voltage noise at 0.78x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = -1.123 | z = -1.10 | contribution +0.298 (toward failure): engine-off rest-voltage floor moved -1.12 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.05 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.78 -> 0.83), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.
  - Production-refit tier (GREEN) differs from shipped OOF tier (AMBER); counterfactual is in production space.

### VIN4_F_SM — FAILED — **GREEN**, P(recal) = 0.339
- **Archetype**: A4 (A4_silent_abrupt)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 1.098 | z = -0.22 | contribution -0.197 (protective): within-week voltage noise at 1.10x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -0.116 | z = +0.11 | contribution -0.029 (protective): rest-voltage floor -0.12 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.191 | z = -0.09 | contribution -0.012 (protective): crank dip depth +0.19 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would return to GREEN if within-week noise ratio fell by 0.04 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.10 -> 1.05), all else equal.
- **Caveats**:
  - Silent gap of 97 d before failure: features describe the pre-silence state; the terminal period is untelemetered.
  - Production-refit tier (AMBER) differs from shipped OOF tier (GREEN); counterfactual is in production space.

### VIN3_F_SM — FAILED — **GREEN**, P(recal) = 0.338
- **Archetype**: A2 (A2_battery_cascade)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = 0.120 | z = +1.39 | contribution -0.573 (protective): weekly voltage range widening at +0.120 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -1.251 | z = -1.26 | contribution +0.339 (toward failure): engine-off rest-voltage floor moved -1.25 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `vsi_withinwk_std_ratio_30d_w` = 1.368 | z = +0.22 | contribution +0.192 (toward failure): within-week voltage noise is 1.37x its own 40-week baseline -- electrical volatility is drifting up (volatility-drift pathway)
  - `dip_depth_last90_delta` = 1.019 | z = +0.80 | contribution +0.112 (toward failure): crank voltage dips +1.02 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would escalate AMBER -> RED if within-week noise ratio rose by 0.04 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.37 -> 1.41), all else equal.
- **Caveats**:
  - Production-refit tier (AMBER) differs from shipped OOF tier (GREEN); counterfactual is in production space.

### VIN1_F_SM — FAILED — **GREEN**, P(recal) = 0.260
- **Archetype**: A1->silent (A1_solenoid_then_silent)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 1.012 | z = -0.36 | contribution -0.322 (protective): within-week voltage noise at 1.01x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.011 | z = -0.28 | contribution -0.039 (protective): crank dip depth +0.01 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = -0.288 | z = -0.10 | contribution +0.026 (toward failure): engine-off rest-voltage floor moved -0.29 V vs own baseline -- battery floor sagging, battery-cascade pathway
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.02 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.01 -> 1.04), all else equal.
- **Caveats**:
  - Silent gap of 72 d before failure: features describe the pre-silence state; the terminal period is untelemetered.

### VIN15_NF_SM — **GREEN**, P(recal) = 0.254
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.941 | z = -0.48 | contribution -0.424 (protective): within-week voltage noise at 0.94x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.571 | z = +0.93 | contribution -0.253 (protective): rest-voltage floor +0.57 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.246 | z = -0.03 | contribution -0.004 (protective): crank dip depth +0.25 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.26 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.94 -> 1.20), all else equal.

### VIN18_NF_SM — **GREEN**, P(recal) = 0.235
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.826 | z = -0.67 | contribution -0.590 (protective): within-week voltage noise at 0.83x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.904 | z = -1.26 | contribution -0.177 (protective): crank dip depth -0.90 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = -0.559 | z = -0.42 | contribution +0.115 (toward failure): engine-off rest-voltage floor moved -0.56 V vs own baseline -- battery floor sagging, battery-cascade pathway
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.24 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.83 -> 1.07), all else equal.
- **Caveats**:
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN9_F_SM — FAILED — **GREEN**, P(recal) = 0.224
- **Archetype**: A4 (A4_silent_abrupt)
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 1.134 | z = -0.16 | contribution -0.146 (protective): within-week voltage noise at 1.13x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.022 | z = +0.27 | contribution -0.074 (protective): rest-voltage floor +0.02 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.019 | z = -0.16 | contribution +0.066 (toward failure): weekly voltage range widening at +0.019 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.03 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.13 -> 1.17), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.
  - Silent gap of 142 d before failure: features describe the pre-silence state; the terminal period is untelemetered.
  - SOLE MISS of the nested model (OOF prob 0.401 vs fold thr 0.406). A4 silent/abrupt + SMA-dead + 142 d gap: physics audit classifies this failure as unobservable in 5 s telemetry.

### VIN19_NF_SM — **GREEN**, P(recal) = 0.197
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.988 | z = -0.40 | contribution -0.357 (protective): within-week voltage noise at 0.99x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.793 | z = -1.14 | contribution -0.160 (protective): crank dip depth -0.79 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = 0.076 | z = +0.34 | contribution -0.092 (protective): rest-voltage floor +0.08 V vs own baseline -- battery floor stable/recovering (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.21 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.99 -> 1.20), all else equal.

### VIN13_NF_SM — **GREEN**, P(recal) = 0.146
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_range_trend` = 0.071 | z = +0.63 | contribution -0.263 (protective): weekly voltage range widening at +0.071 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `vsi_withinwk_std_ratio_30d_w` = 1.171 | z = -0.10 | contribution -0.092 (protective): within-week voltage noise at 1.17x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = -0.008 | z = +0.24 | contribution -0.064 (protective): rest-voltage floor -0.01 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.22 x (ratio) (vsi_withinwk_std_ratio_30d_w: 1.17 -> 1.39), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.

### VIN7_NF_SM — **GREEN**, P(recal) = 0.143
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.980 | z = -0.42 | contribution -0.368 (protective): within-week voltage noise at 0.98x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.235 | z = +0.53 | contribution -0.143 (protective): rest-voltage floor +0.23 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = -0.322 | z = -0.63 | contribution -0.089 (protective): crank dip depth -0.32 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.21 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.98 -> 1.19), all else equal.

### VIN11_NF_SM — **GREEN**, P(recal) = 0.121
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.905 | z = -0.54 | contribution -0.476 (protective): within-week voltage noise at 0.91x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.313 | z = +0.62 | contribution -0.169 (protective): rest-voltage floor +0.31 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.24 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.91 -> 1.15), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.

### VIN4_NF_SM — **GREEN**, P(recal) = 0.118
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.914 | z = -0.52 | contribution -0.463 (protective): within-week voltage noise at 0.91x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.325 | z = +0.64 | contribution -0.173 (protective): rest-voltage floor +0.33 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.123 | z = -0.16 | contribution -0.023 (protective): crank dip depth +0.12 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.25 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.91 -> 1.16), all else equal.

### VIN17_NF_SM — **GREEN**, P(recal) = 0.096
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.754 | z = -0.78 | contribution -0.695 (protective): within-week voltage noise at 0.75x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -0.433 | z = -0.27 | contribution +0.074 (toward failure): engine-off rest-voltage floor moved -0.43 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.226 | z = -0.05 | contribution -0.007 (protective): crank dip depth +0.23 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.23 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.75 -> 0.98), all else equal.
- **Caveats**:
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN12_NF_SM — **GREEN**, P(recal) = 0.091
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.883 | z = -0.57 | contribution -0.508 (protective): within-week voltage noise at 0.88x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.464 | z = +0.81 | contribution -0.218 (protective): rest-voltage floor +0.46 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.216 *(imputed)* | z = -0.06 | contribution -0.008 (protective): crank dip depth +0.22 V vs own baseline -- dips not deepening (protective) [IMPUTED fleet median -- no crank events observable for this truck]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.30 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.88 -> 1.18), all else equal.
- **Caveats**:
  - SMA-dead telematics config: no crank events observable; dip_depth_last90_delta is fold-median IMPUTED, not measured.
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN9_NF_SM — **GREEN**, P(recal) = 0.082
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.979 | z = -0.42 | contribution -0.370 (protective): within-week voltage noise at 0.98x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `dip_depth_last90_delta` = -1.866 | z = -2.28 | contribution -0.321 (protective): crank dip depth -1.87 V vs own baseline -- dips not deepening (protective)
  - `rest_vsi_p05_delta90` = 0.348 | z = +0.67 | contribution -0.180 (protective): rest-voltage floor +0.35 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.019 | z = -0.16 | contribution +0.066 (toward failure): weekly voltage range widening at +0.019 V/wk over the last 12 weeks [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.48 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.98 -> 1.46), all else equal.

### VIN6_NF_SM — **GREEN**, P(recal) = 0.070
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.614 | z = -1.01 | contribution -0.896 (protective): within-week voltage noise at 0.61x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = -0.430 | z = -0.27 | contribution +0.073 (toward failure): engine-off rest-voltage floor moved -0.43 V vs own baseline -- battery floor sagging, battery-cascade pathway
  - `dip_depth_last90_delta` = 0.566 | z = +0.31 | contribution +0.044 (toward failure): crank voltage dips +0.57 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.33 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.61 -> 0.95), all else equal.

### VIN1_NF_SM — **GREEN**, P(recal) = 0.066
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.755 | z = -0.78 | contribution -0.693 (protective): within-week voltage noise at 0.75x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.546 | z = +0.90 | contribution -0.245 (protective): rest-voltage floor +0.55 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.056 | z = -0.35 | contribution -0.049 (protective): crank dip depth -0.06 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.47 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.75 -> 1.23), all else equal.

### VIN3_NF_SM — **GREEN**, P(recal) = 0.056
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.892 | z = -0.56 | contribution -0.495 (protective): within-week voltage noise at 0.89x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.534 | z = +0.89 | contribution -0.241 (protective): rest-voltage floor +0.53 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.911 | z = -1.26 | contribution -0.178 (protective): crank dip depth -0.91 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.42 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.89 -> 1.32), all else equal.
- **Caveats**:
  - Battery-replacement step detected (E5): rest-VSI baseline re-anchored post-step; rest_vsi_p05_delta90 is step-aware.

### VIN8_NF_SM — **GREEN**, P(recal) = 0.048
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `rest_vsi_p05_delta90` = 1.235 | z = +1.73 | contribution -0.468 (protective): rest-voltage floor +1.24 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_withinwk_std_ratio_30d_w` = 0.987 | z = -0.40 | contribution -0.358 (protective): within-week voltage noise at 0.99x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = -0.235 | z = -0.54 | contribution -0.076 (protective): crank dip depth -0.24 V vs own baseline -- dips not deepening (protective)
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.42 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.99 -> 1.40), all else equal.

### VIN16_NF_SM — **GREEN**, P(recal) = 0.043
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.552 | z = -1.11 | contribution -0.987 (protective): within-week voltage noise at 0.55x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `rest_vsi_p05_delta90` = 0.105 | z = +0.37 | contribution -0.101 (protective): rest-voltage floor +0.11 V vs own baseline -- battery floor stable/recovering (protective)
  - `dip_depth_last90_delta` = 0.483 | z = +0.22 | contribution +0.032 (toward failure): crank voltage dips +0.48 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.52 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.55 -> 1.07), all else equal.

### VIN14_NF_SM — **GREEN**, P(recal) = 0.041
- **Archetype**: n/a
- **Drivers** (exact linear attribution, ranked by |contribution|):
  - `vsi_withinwk_std_ratio_30d_w` = 0.451 | z = -1.28 | contribution -1.132 (protective): within-week voltage noise at 0.45x own baseline -- quiet, fleet-typical electrical behaviour (protective)
  - `rest_vsi_p05_delta90` = 0.426 | z = +0.76 | contribution -0.205 (protective): rest-voltage floor +0.43 V vs own baseline -- battery floor stable/recovering (protective)
  - `vsi_range_trend` = 0.000 | z = -0.45 | contribution +0.188 (toward failure): weekly voltage range trend +0.000 V/wk -- envelope flat [model uses this term as a statistical suppressor for the correlated noise ratio (r=+0.82); its standalone physics direction is widening = risk -- see global coefficient table]
  - `dip_depth_last90_delta` = 0.861 | z = +0.63 | contribution +0.088 (toward failure): crank voltage dips +0.86 V deeper than own baseline in the last 90 d -- heavier cranking load / battery-cascade signature
- **Counterfactual**: would enter AMBER if within-week noise ratio rose by 0.66 x (ratio) (vsi_withinwk_std_ratio_30d_w: 0.45 -> 1.11), all else equal.
