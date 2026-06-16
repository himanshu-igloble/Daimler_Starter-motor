# Evidence Card — VIN8_NF_SM

| Field | Value |
|---|---|
| VIN | `VIN8_NF_SM` |
| Tier (production prob) | **[GREEN]** |
| Production probability | `0.0218` |
| OOF probability (honest) | `0.0484` ([GREEN]) |
| Failed | `No` |
| Priority | **routine** (none) |
| Badges | `WATCHLIST` |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `NF` — flags: `—`
- **Physics mode:** Non-failed — no archetype assigned (archetype analysis for failed trucks only)

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `rest_vsi_p05_delta90` | `1.2353` | `100.0`th | `+1.732` | `-0.4683` | protective | rest-voltage floor delta = +1.235 V vs own baseline — stable/rising; z=+1.73, 100th fleet pctile |
| 2 | `vsi_withinwk_std_ratio_30d_w` | `0.9870` | `47.1`th | `-0.404` | `-0.3578` | protective | within-week voltage noise is 0.99x own baseline — moderate 47th fleet percentile; z=-0.40 |
| 3 | `vsi_range_trend` | `0.0000` | `39.7`th | `-0.454` | `+0.1877` | toward failure | drive-voltage range trend = +0.0000 V/wk — flat/narrowing; z=-0.45, 40th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 4 | `dip_depth_last90_delta` | `-0.2353` | `20.6`th | `-0.542` | `-0.0764` | protective | crank dip depth delta = -0.235 V vs baseline — stable/shallow; z=-0.54, 21th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `True` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `A1_crank_burst` / `2025-06-15` | — |

## (e) Evidence Window

- **Evidence state:** `GREEN_tier_channel_fires_eventually`
- **Empirical n:** 3 (retrospective fleet)
- **Median lead to failure:** 160 days
- **95% bootstrap CI:** [28d, 168d]
- **Scheduling window:** Next scheduled service (50,000 km or 6 months)
- **Honest caveat:** 3/4 GREEN-failed trucks eventually fired a channel. 1 (VIN9_F) fired nothing — irreducible blind spot.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Changing vsi_range_trend by 0.099 units (to -0.099) would theoretically cross the GREEN threshold, but this value is outside plausible fleet range [-0.080, 0.202]. Multiple drivers are concurrently elevated; single-feature counterfactual is not achievable.

## (g) Confidence Block

- **Validation of record:** nested LOVO AUROC 0.9321 / CI [0.811, 0.986]
- **OOF tier error rates (n=34):**
  - RED: 10/14 failed correctly RED; 2/20 NF false positives
  - AMBER: 0/14 failed scored AMBER; 2/20 NF scored AMBER
  - GREEN: 4/14 failed missed (GREEN); 16/20 NF correctly GREEN
- **WATCHLIST:** Watchlist badge: non-failed truck with elevated risk indicators; enhanced monitoring recommended.

## (h) Model Provenance

- **Features:** `vsi_withinwk_std_ratio_30d_w | rest_vsi_p05_delta90 | vsi_range_trend | dip_depth_last90_delta`
- **Alpha:** 1.0
- **Model hash (feature+alpha SHA-256 prefix):** `4ab93265994f7d8d`
- **Config version:** 2.0.0-A
- **Generated:** 2026-06-12
- **In-sample AUROC (production fit):** 0.9571 (labeled IN-SAMPLE — not validation; validation AUROC = 0.9321)
