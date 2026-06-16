# Evidence Card — VIN1_F_SM

| Field | Value |
|---|---|
| VIN | `VIN1_F_SM` |
| Tier (production prob) | **[GREEN]** |
| Production probability | `0.2806` |
| OOF probability (honest) | `0.2596` ([GREEN]) |
| Failed | `Yes` |
| Priority | **routine** (none) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A1_solenoid_then_silent` — flags: `CRANK_BURST+SILENT_GAP_72d`
- **Physics mode:** Solenoid wear followed by data silence (SMA gap); progressive contact degradation then abrupt cutoff

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `1.0116` | `52.9`th | `-0.364` | `-0.3222` | protective | within-week voltage noise is 1.01x own baseline — moderate 53th fleet percentile; z=-0.36 |
| 2 | `vsi_range_trend` | `0.0000` | `39.7`th | `-0.454` | `+0.1877` | toward failure | drive-voltage range trend = +0.0000 V/wk — flat/narrowing; z=-0.45, 40th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `dip_depth_last90_delta` | `0.0115` | `29.4`th | `-0.279` | `-0.0393` | protective | crank dip depth delta = +0.011 V vs baseline — stable/shallow; z=-0.28, 29th fleet pctile |
| 4 | `rest_vsi_p05_delta90` | `-0.2877` | `38.2`th | `-0.098` | `+0.0265` | toward failure | rest-voltage floor delta = -0.288 V vs own baseline — mild sagging; z=-0.10, 38th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `True` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `A1_crank_burst` / `2025-04-08` | — |

## (e) Evidence Window

- **Evidence state:** `GREEN_tier_channel_fires_eventually`
- **Empirical n:** 3 (retrospective fleet)
- **Median lead to failure:** 160 days
- **95% bootstrap CI:** [28d, 168d]
- **Scheduling window:** Next scheduled service (50,000 km or 6 months)
- **Honest caveat:** 3/4 GREEN-failed trucks eventually fired a channel. 1 (VIN9_F) fired nothing — irreducible blind spot.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_range_trend by 0.010 units (from 0.000 to -0.010) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -0.155]

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
