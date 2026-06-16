# Evidence Card — VIN14_F_SM

| Field | Value |
|---|---|
| VIN | `VIN14_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9987` |
| OOF probability (honest) | `0.9977` ([RED]) |
| Failed | `Yes` |
| Priority | **P0** (A2 battery-cascade fired; persistent RED 16 weeks) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A1+A2_mixed` — flags: `CRANK_BURST+BATTERY_DECLINE+VSI_VOLATILITY`
- **Physics mode:** Mixed: solenoid crank bursts + battery voltage floor decline; compound electro-mechanical degradation

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `2.5428` | `97.1`th | `+2.133` | `+1.8902` | toward failure | within-week voltage noise is 2.54x own baseline — worst 97th fleet percentile; z=+2.13 |
| 2 | `vsi_range_trend` | `0.2018` | `100.0`th | `+2.648` | `-1.0960` | protective | drive-voltage range trend = +0.2018 V/wk — widening (risk direction univariately); z=+2.65, 100th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `rest_vsi_p05_delta90` | `-1.6029` | `8.8`th | `-1.678` | `+0.4538` | toward failure | rest-voltage floor delta = -1.603 V vs own baseline — strong sagging (battery cascade risk); z=-1.68, 9th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.9857` | `88.2`th | `+0.761` | `+0.1072` | toward failure | crank dip depth delta = +0.986 V vs baseline — deepening dips (heavier load signature); z=+0.76, 88th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `True` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`16` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-03-17` | — |

## (e) Evidence Window

- **Evidence state:** `A2_battery_cascade_fired`
- **Empirical n:** 4 (retrospective fleet)
- **Median lead to failure:** 66 days
- **95% bootstrap CI:** [28d, 91d]
- **Scheduling window:** 14–30 days from alert
- **Honest caveat:** Retrospective n=4. NF false alarms: 0/20. Min lead 28d — tight; prioritize.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_withinwk_std_ratio_30d_w by 0.995 units (from 2.543 to 1.547) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -1.623]

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
