# Evidence Card — VIN5_F_SM

| Field | Value |
|---|---|
| VIN | `VIN5_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.9977` |
| OOF probability (honest) | `0.9918` ([RED]) |
| Failed | `Yes` |
| Priority | **P0** (persistent RED 27 weeks) |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A4_silent_abrupt` — flags: `SILENT_GAP_32d`
- **Physics mode:** Data silence (SMA dead) with/without prior VSI signals; abrupt failure with minimal observable precursor

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `3.0663` | `100.0`th | `+2.987` | `+2.6467` | toward failure | within-week voltage noise is 3.07x own baseline — worst 100th fleet percentile; z=+2.99 |
| 2 | `vsi_range_trend` | `0.1981` | `94.1`th | `+2.591` | `-1.0722` | protective | drive-voltage range trend = +0.1981 V/wk — widening (risk direction univariately); z=+2.59, 94th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 3 | `rest_vsi_p05_delta90` | `0.7854` | `97.1`th | `+1.192` | `-0.3222` | protective | rest-voltage floor delta = +0.785 V vs own baseline — stable/rising; z=+1.19, 97th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.2163` *(imputed)* | `51.5`th | `-0.060` | `-0.0085` | protective | crank dip depth delta = +0.216 V vs baseline — deepening dips (heavier load signature); z=-0.06, 51th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | `False` | Validated FP record: fires on 4/20 NF trucks (VIN15/16/17/4) |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`27` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2024-09-30` | — |

## (e) Evidence Window

- **Evidence state:** `persistence_terminal_AND_RED_tier`
- **Empirical n:** 10 (retrospective fleet)
- **Median lead to failure:** 206 days
- **95% bootstrap CI:** [126d, 284d]
- **Scheduling window:** 14–28 days
- **Honest caveat:** Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk).
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_withinwk_std_ratio_30d_w by 0.918 units (from 3.066 to 2.148) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -1.498]

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
