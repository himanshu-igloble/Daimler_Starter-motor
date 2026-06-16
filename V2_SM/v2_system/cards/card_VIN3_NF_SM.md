# Evidence Card — VIN3_NF_SM

| Field | Value |
|---|---|
| VIN | `VIN3_NF_SM` |
| Tier (production prob) | **[GREEN]** |
| Production probability | `0.0206` |
| OOF probability (honest) | `0.0563` ([GREEN]) |
| Failed | `No` |
| Priority | **routine** (none) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `NF` — flags: `—`
- **Physics mode:** Non-failed — no archetype assigned (archetype analysis for failed trucks only)

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `0.8917` | `26.5`th | `-0.559` | `-0.4955` | protective | within-week voltage noise is 0.89x own baseline — low 26th fleet percentile; z=-0.56 |
| 2 | `rest_vsi_p05_delta90` | `0.5344` | `88.2`th | `+0.890` | `-0.2406` | protective | rest-voltage floor delta = +0.534 V vs own baseline — stable/rising; z=+0.89, 88th fleet pctile |
| 3 | `vsi_range_trend` | `0.0000` | `39.7`th | `-0.454` | `+0.1877` | toward failure | drive-voltage range trend = +0.0000 V/wk — flat/narrowing; z=-0.45, 40th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 4 | `dip_depth_last90_delta` | `-0.9112` | `5.9`th | `-1.263` | `-0.1779` | protective | crank dip depth delta = -0.911 V vs baseline — stable/shallow; z=-1.26, 6th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `False` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `NONE` / `—` | — |

## (e) Evidence Window

- **Evidence state:** `GREEN_tier_channel_fires_eventually`
- **Empirical n:** 3 (retrospective fleet)
- **Median lead to failure:** 160 days
- **95% bootstrap CI:** [28d, 168d]
- **Scheduling window:** Next scheduled service (50,000 km or 6 months)
- **Honest caveat:** 3/4 GREEN-failed trucks eventually fired a channel. 1 (VIN9_F) fired nothing — irreducible blind spot.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Changing vsi_range_trend by 0.101 units (to -0.101) would theoretically cross the GREEN threshold, but this value is outside plausible fleet range [-0.080, 0.202]. Multiple drivers are concurrently elevated; single-feature counterfactual is not achievable.

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
