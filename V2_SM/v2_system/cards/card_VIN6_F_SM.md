# Evidence Card — VIN6_F_SM

| Field | Value |
|---|---|
| VIN | `VIN6_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9997` |
| OOF probability (honest) | `0.9980` ([RED]) |
| Failed | `Yes` |
| Priority | **P0** (A2 battery-cascade fired; persistent RED 22 weeks) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A2_battery_cascade` — flags: `BATTERY_DECLINE+VSI_VOLATILITY`
- **Physics mode:** Battery voltage floor sagging (rest VSI p05 decline) triggering cascade load on starter; battery-primary mode

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `2.0668` | `88.2`th | `+1.357` | `+1.2024` | toward failure | within-week voltage noise is 2.07x own baseline — elevated 88th fleet percentile; z=+1.36 |
| 2 | `vsi_range_trend` | `0.2000` | `97.1`th | `+2.620` | `-1.0844` | protective | drive-voltage range trend = +0.2000 V/wk — widening (risk direction univariately); z=+2.62, 97th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `rest_vsi_p05_delta90` | `-3.1528` | `2.9`th | `-3.541` | `+0.9573` | toward failure | rest-voltage floor delta = -3.153 V vs own baseline — strong sagging (battery cascade risk); z=-3.54, 3th fleet pctile |
| 4 | `dip_depth_last90_delta` | `4.1230` | `100.0`th | `+4.108` | `+0.5786` | toward failure | crank dip depth delta = +4.123 V vs baseline — deepening dips (heavier load signature); z=+4.11, 100th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `True` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`22` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-05-19` | — |

## (e) Evidence Window

- **Evidence state:** `A2_battery_cascade_fired`
- **Empirical n:** 4 (retrospective fleet)
- **Median lead to failure:** 66 days
- **95% bootstrap CI:** [28d, 91d]
- **Scheduling window:** 14–30 days from alert
- **Honest caveat:** Retrospective n=4. NF false alarms: 0/20. Min lead 28d — tight; prioritize.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_withinwk_std_ratio_30d_w by 1.202 units (from 2.067 to 0.864) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -1.960]

## (g) Confidence Block

- **Validation of record:** nested LOVO AUROC 0.9321 / CI [0.811, 0.986]
- **OOF tier error rates (n=34):**
  - RED: 10/14 failed correctly RED; 2/20 NF false positives
  - AMBER: 0/14 failed scored AMBER; 2/20 NF scored AMBER
  - GREEN: 4/14 failed missed (GREEN); 16/20 NF correctly GREEN

## (h) Model Provenance

- **Features:** `vsi_withinwk_std_ratio_30d_w | rest_vsi_p05_delta90 | vsi_range_trend | dip_depth_last90_delta`
- **Alpha:** 1.0
- **Model hash (feature+alpha SHA-256 prefix):** `4ab93265994f7d8d`
- **Config version:** 2.0.0-A
- **Generated:** 2026-06-12
- **In-sample AUROC (production fit):** 0.9571 (labeled IN-SAMPLE — not validation; validation AUROC = 0.9321)
