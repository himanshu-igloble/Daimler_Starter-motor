# Evidence Card — VIN2_F_SM

| Field | Value |
|---|---|
| VIN | `VIN2_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9714` |
| OOF probability (honest) | `0.9042` ([RED]) |
| Failed | `Yes` |
| Priority | **P1** (RED tier) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A2_battery_cascade` — flags: `CRANK_BURST+BATTERY_DECLINE+VSI_VOLATILITY`
- **Physics mode:** Battery voltage floor sagging (rest VSI p05 decline) triggering cascade load on starter; battery-primary mode

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `rest_vsi_p05_delta90` | `-1.6567` | `5.9`th | `-1.743` | `+0.4712` | toward failure | rest-voltage floor delta = -1.657 V vs own baseline — strong sagging (battery cascade risk); z=-1.74, 6th fleet pctile |
| 2 | `dip_depth_last90_delta` | `1.5775` | `97.1`th | `+1.392` | `+0.1961` | toward failure | crank dip depth delta = +1.577 V vs baseline — deepening dips (heavier load signature); z=+1.39, 97th fleet pctile |
| 3 | `vsi_range_trend` | `0.0000` | `39.7`th | `-0.454` | `+0.1877` | toward failure | drive-voltage range trend = +0.0000 V/wk — flat/narrowing; z=-0.45, 40th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 4 | `vsi_withinwk_std_ratio_30d_w` | `1.1540` | `70.6`th | `-0.131` | `-0.1165` | protective | within-week voltage noise is 1.15x own baseline — elevated 71th fleet percentile; z=-0.13 |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`2` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-09-22` | — |

## (e) Evidence Window

- **Evidence state:** `persistence_terminal_AND_RED_tier`
- **Empirical n:** 10 (retrospective fleet)
- **Median lead to failure:** 206 days
- **95% bootstrap CI:** [126d, 284d]
- **Scheduling window:** 14–28 days
- **Honest caveat:** Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk).
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing rest_vsi_p05_delta90 by 2.530 units (from -1.657 to 0.873) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = +3.040]

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
