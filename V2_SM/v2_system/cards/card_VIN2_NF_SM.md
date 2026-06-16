# Evidence Card — VIN2_NF_SM

| Field | Value |
|---|---|
| VIN | `VIN2_NF_SM` |
| Tier (production prob) | **[AMBER]** |
| Production probability | `0.3991` |
| OOF probability (honest) | `0.4517` ([AMBER]) |
| Failed | `No` |
| Priority | **P2** (AMBER tier) |
| Badges | `WATCHLIST` |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `NF` — flags: `—`
- **Physics mode:** Non-failed — no archetype assigned (archetype analysis for failed trucks only)

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_range_trend` | `-0.0122` | `8.8`th | `-0.640` | `+0.2651` | toward failure | drive-voltage range trend = -0.0122 V/wk — flat/narrowing; z=-0.64, 9th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 2 | `vsi_withinwk_std_ratio_30d_w` | `1.0752` | `55.9`th | `-0.260` | `-0.2304` | protective | within-week voltage noise is 1.08x own baseline — moderate 56th fleet percentile; z=-0.26 |
| 3 | `rest_vsi_p05_delta90` | `0.0198` | `50.0`th | `+0.272` | `-0.0734` | protective | rest-voltage floor delta = +0.020 V vs own baseline — stable/rising; z=+0.27, 50th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.2530` | `70.6`th | `-0.021` | `-0.0030` | protective | crank dip depth delta = +0.253 V vs baseline — deepening dips (heavier load signature); z=-0.02, 71th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `True` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-04-14` | — |

## (e) Evidence Window

- **Evidence state:** `AMBER_tier_no_channel`
- **Empirical n:** 0 (retrospective fleet)
- **Median lead:** no empirical data (n=0 or SMA-dead special class)
- **Scheduling window:** At next scheduled service (<=90 days)
- **Honest caveat:** 0 failed trucks scored AMBER in OOF — no empirical lead-time data. 2/20 NF scored AMBER.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_range_trend by 0.007 units (from -0.012 to -0.006) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = +0.101]

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
