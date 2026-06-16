# Evidence Card — VIN8_F_SM

| Field | Value |
|---|---|
| VIN | `VIN8_F_SM` |
| Tier (production prob) | **[RED]** |
| Production probability | `0.8505` |
| OOF probability (honest) | `0.7163` ([RED]) |
| Failed | `Yes` |
| Priority | **P1** (RED tier) |
| Badges | `SMA-DEAD` |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A4_silent_abrupt` — flags: `VSI_VOLATILITY+SILENT_GAP_37d`
- **Physics mode:** Data silence (SMA dead) with/without prior VSI signals; abrupt failure with minimal observable precursor

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_range_trend` | `-0.0444` | `5.9`th | `-1.137` | `+0.4704` | toward failure | drive-voltage range trend = -0.0444 V/wk — flat/narrowing; z=-1.14, 6th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 2 | `vsi_withinwk_std_ratio_30d_w` | `1.1400` | `67.6`th | `-0.154` | `-0.1368` | protective | within-week voltage noise is 1.14x own baseline — elevated 68th fleet percentile; z=-0.15 |
| 3 | `rest_vsi_p05_delta90` | `-0.3886` | `35.3`th | `-0.219` | `+0.0592` | toward failure | rest-voltage floor delta = -0.389 V vs own baseline — mild sagging; z=-0.22, 35th fleet pctile |
| 4 | `dip_depth_last90_delta` | `0.2163` *(imputed)* | `51.5`th | `-0.060` | `-0.0085` | protective | crank dip depth delta = +0.216 V vs baseline — deepening dips (heavier load signature); z=-0.06, 51th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | MASKED (SMA-dead) | Crank-event data absent; channel not evaluable |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `True` (terminal); streak=`1` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `persistence` / `2025-07-14` | — |

> **SMA-DEAD:** Crank-event channels (A1) are not available for this truck. VSI persistence channel remains valid. If SMA is dead while tier is RED/AMBER, trigger manual inspection within 72 hours.

## (e) Evidence Window

- **Evidence state:** `persistence_terminal_AND_RED_tier`
- **Empirical n:** 10 (retrospective fleet)
- **Median lead to failure:** 206 days
- **95% bootstrap CI:** [126d, 284d]
- **Scheduling window:** 14–28 days
- **Honest caveat:** Long median lead (~months). Condition flag, NOT failure-imminent alarm. 4/20 NF also end in persistence (false alarm risk).
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_range_trend by 0.074 units (from -0.044 to 0.029) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = +1.130]

## (g) Confidence Block

- **Validation of record:** nested LOVO AUROC 0.9321 / CI [0.811, 0.986]
- **OOF tier error rates (n=34):**
  - RED: 10/14 failed correctly RED; 2/20 NF false positives
  - AMBER: 0/14 failed scored AMBER; 2/20 NF scored AMBER
  - GREEN: 4/14 failed missed (GREEN); 16/20 NF correctly GREEN
- **SMA-DEAD:** SMA-dead badge: crank-channel data is absent (SMA always 0 or silent). VSI-based channels remain valid but A1 crank channel is masked.

## (h) Model Provenance

- **Features:** `vsi_withinwk_std_ratio_30d_w | rest_vsi_p05_delta90 | vsi_range_trend | dip_depth_last90_delta`
- **Alpha:** 1.0
- **Model hash (feature+alpha SHA-256 prefix):** `4ab93265994f7d8d`
- **Config version:** 2.0.0-A
- **Generated:** 2026-06-12
- **In-sample AUROC (production fit):** 0.9571 (labeled IN-SAMPLE — not validation; validation AUROC = 0.9321)
