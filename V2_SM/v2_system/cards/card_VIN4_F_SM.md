# Evidence Card — VIN4_F_SM

| Field | Value |
|---|---|
| VIN | `VIN4_F_SM` |
| Tier (production prob) | **[AMBER]** |
| Production probability | `0.3876` |
| OOF probability (honest) | `0.3393` ([GREEN]) |
| Failed | `Yes` |
| Priority | **P2** (AMBER tier) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A4_silent_abrupt` — flags: `VSI_VOLATILITY+SILENT_GAP_97d`
- **Physics mode:** Data silence (SMA dead) with/without prior VSI signals; abrupt failure with minimal observable precursor

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `1.0980` | `58.8`th | `-0.223` | `-0.1974` | protective | within-week voltage noise is 1.10x own baseline — moderate 59th fleet percentile; z=-0.22 |
| 2 | `vsi_range_trend` | `0.0000` | `39.7`th | `-0.454` | `+0.1877` | toward failure | drive-voltage range trend = +0.0000 V/wk — flat/narrowing; z=-0.45, 40th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `rest_vsi_p05_delta90` | `-0.1164` | `41.2`th | `+0.108` | `-0.0292` | protective | rest-voltage floor delta = -0.116 V vs own baseline — slight decline; z=+0.11, 41th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.1908` | `35.3`th | `-0.087` | `-0.0123` | protective | crank dip depth delta = +0.191 V vs baseline — borderline; z=-0.09, 35th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-06-30` | — |

## (e) Evidence Window

- **Evidence state:** `AMBER_tier_no_channel`
- **Empirical n:** 0 (retrospective fleet)
- **Median lead:** no empirical data (n=0 or SMA-dead special class)
- **Scheduling window:** At next scheduled service (<=90 days)
- **Honest caveat:** 0 failed trucks scored AMBER in OOF — no empirical lead-time data. 2/20 NF scored AMBER.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_range_trend by 0.005 units (from 0.000 to 0.005) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = +0.078]

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
