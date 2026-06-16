# V2 Evidence Cards — README & Regeneration Guide

Config version: 2.0.0-A | Generated: 2026-06-12

## Contents

| File | Description |
|---|---|
| `card_{VIN}.md` (x34) | Per-truck evidence card in Markdown |
| `cards.json` | Machine-readable equivalent of all 34 cards |
| `fleet_ranking.md` | Planner-facing sorted fleet table |
| `cards_README.md` | This file |
| `generate_cards.py` | Regeneration script |

## Production Fit vs Validation-of-Record

**Validation of record** is the **nested LOVO (leave-one-VIN-out) cross-validation** result:
- AUROC = 0.9321, 95% CI [0.811, 0.986] (n=34, bootstrapped)
- This is the **honest estimate** of generalization performance.
- The per-truck OOF (out-of-fold) probabilities shown on each card come from this procedure.

**Production fit** is a **standard post-validation refit**:
- Trained on all 34 trucks (median-imputed, StandardScaler, RidgeClassifier alpha=1.0, Platt calibration).
- This is intentional: once validation confirms the model is trustworthy, the production model uses all available data.
- In-sample AUROC of the production fit = 0.9571 (labeled IN-SAMPLE throughout; expected to exceed 0.9321).
- The production probability on each card comes from this fit.

**Both are shown** because:
1. Production prob = best current estimate for routing/prioritization.
2. OOF prob = honest evaluation-era estimate; shows how the model behaved when it had NOT seen this truck.

## Regeneration

```bash
cd D:/Daimler-starter_motor_alternator_battery
py -3 'STARTER MOTOR/V2_program/v2_system/cards/generate_cards.py'
```

Dependencies: pandas, numpy, scikit-learn, scipy.

## Features (modal 4)

| Feature | Physics | Expected Sign |
|---|---|---|
| `vsi_withinwk_std_ratio_30d_w` | Within-week supply-voltage noise vs own 40-wk baseline | + |
| `rest_vsi_p05_delta90` | Engine-off rest-voltage 5th-pctile delta vs baseline (last 90d) | - (down = risk) |
| `vsi_range_trend` | Drive-voltage range trend (V/wk) over last 12 wks | + univariate; **SUPPRESSOR in multivariate** (r=+0.82 with noise ratio) |
| `dip_depth_last90_delta` | Crank dip depth delta vs own baseline (last 90d) | + |

## Tier Thresholds

| Tier | Condition |
|---|---|
| GREEN | production prob < 0.35 |
| AMBER | 0.35 <= production prob < 0.55 |
| RED | production prob >= 0.55 |

## Priority Logic

| Priority | Condition |
|---|---|
| P0 | A2 channel fired, OR persistent RED >= 3 weeks (from walking_scores.csv) |
| P1 | RED tier (no P0 condition) |
| P2 | AMBER tier |
| routine | GREEN tier, no channel fires |

## SMA-Dead Cohort

VINs: VIN8_F_SM, VIN9_F_SM, VIN10_NF_SM, VIN11_NF_SM, VIN12_NF_SM, VIN13_NF_SM, VIN20_NF_SM.
A1 crank-burst channel is masked/not evaluable. VSI-based features and channels remain valid.

## Watchlist NF VINs

VINs: VIN2_NF_SM, VIN5_NF_SM, VIN8_NF_SM, VIN15_NF_SM.
Non-failed trucks with elevated risk indicators — enhanced monitoring cadence recommended.