# Evidence Card — VIN12_F_SM

| Field | Value |
|---|---|
| VIN | `VIN12_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9849` |
| OOF probability (honest) | `0.9549` ([RED]) |
| Failed | `Yes` |
| Priority | **P0** (persistent RED 5 weeks) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A3_vsi_volatility_only` — flags: `VSI_VOLATILITY`
- **Physics mode:** Electrical instability without dominant crank pattern; regulation or wiring intermittency mode

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `2.2059` | `91.2`th | `+1.584` | `+1.4034` | toward failure | within-week voltage noise is 2.21x own baseline — worst 91th fleet percentile; z=+1.58 |
| 2 | `vsi_range_trend` | `0.1000` | `88.2`th | `+1.083` | `-0.4483` | protective | drive-voltage range trend = +0.1000 V/wk — widening (risk direction univariately); z=+1.08, 88th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `dip_depth_last90_delta` | `-0.0553` | `26.5`th | `-0.350` | `-0.0493` | protective | crank dip depth delta = -0.055 V vs baseline — stable/shallow; z=-0.35, 26th fleet pctile |
| 4 | `rest_vsi_p05_delta90` | `-0.0924` | `44.1`th | `+0.137` | `-0.0370` | protective | rest-voltage floor delta = -0.092 V vs own baseline — slight decline; z=+0.14, 44th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `True` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`5` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `A1_crank_burst` / `2025-07-26` | — |

## (e) Evidence Window

- **Evidence state:** `persistence_terminal_AND_RED_tier`
- **Empirical n:** 10 (retrospective fleet)
- **Median lead to failure:** 206 days
- **95% bootstrap CI:** [126d, 284d]
- **Scheduling window:** 14–28 days
- **Honest caveat:** Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk).
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_withinwk_std_ratio_30d_w by 0.659 units (from 2.206 to 1.547) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -1.074]

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
