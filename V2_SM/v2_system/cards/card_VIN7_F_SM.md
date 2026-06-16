# Evidence Card — VIN7_F_SM

| Field | Value |
|---|---|
| VIN | `VIN7_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9595` |
| OOF probability (honest) | `0.9056` ([RED]) |
| Failed | `Yes` |
| Priority | **P0** (persistent RED 11 weeks) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A3_vsi_volatility_only` — flags: `VSI_VOLATILITY`
- **Physics mode:** Electrical instability without dominant crank pattern; regulation or wiring intermittency mode

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `1.8648` | `82.4`th | `+1.028` | `+0.9106` | toward failure | within-week voltage noise is 1.86x own baseline — elevated 82th fleet percentile; z=+1.03 |
| 2 | `vsi_range_trend` | `0.0793` | `85.3`th | `+0.764` | `-0.3164` | protective | drive-voltage range trend = +0.0793 V/wk — widening (risk direction univariately); z=+0.76, 85th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `rest_vsi_p05_delta90` | `-0.4621` | `26.5`th | `-0.307` | `+0.0831` | toward failure | rest-voltage floor delta = -0.462 V vs own baseline — mild sagging; z=-0.31, 26th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.2066` | `38.2`th | `-0.070` | `-0.0099` | protective | crank dip depth delta = +0.207 V vs baseline — deepening dips (heavier load signature); z=-0.07, 38th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`11` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-02-10` | — |

## (e) Evidence Window

- **Evidence state:** `persistence_terminal_AND_RED_tier`
- **Empirical n:** 10 (retrospective fleet)
- **Median lead to failure:** 206 days
- **95% bootstrap CI:** [126d, 284d]
- **Scheduling window:** 14–28 days
- **Honest caveat:** Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk).
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_withinwk_std_ratio_30d_w by 0.520 units (from 1.865 to 1.345) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -0.847]

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
