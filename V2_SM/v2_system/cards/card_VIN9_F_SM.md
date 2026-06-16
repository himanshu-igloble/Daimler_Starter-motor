# Evidence Card — VIN9_F_SM

| Field | Value |
|---|---|
| VIN | `VIN9_F_SM` |
| Tier (production prob) | **[GREEN]** |
| Production probability | `0.2653` |
| OOF probability (honest) | `0.2239` ([GREEN]) |
| Failed | `Yes` |
| Priority | **routine** (none) |
| Badges | `SMA-DEAD` |

> **Validation of record:** nested LOVO AUROC 0.9321, CI [0.811, 0.986] (production fit is post-validation standard refit on all-34; OOF prob above is the honest out-of-fold reference).

## (b) Archetype & Physics Mode

- **Archetype:** `A4_silent_abrupt` — flags: `SILENT_GAP_142d`
- **Physics mode:** Data silence (SMA dead) with/without prior VSI signals; abrupt failure with minimal observable precursor

## (c) Drivers (sorted by |contribution|)

| Rank | Feature | Raw Value | Fleet Pctile | z-score | Contribution (coef×z) | Direction | Plain-English |
|---|---|---|---|---|---|---|---|
| 1 | `vsi_withinwk_std_ratio_30d_w` | `1.1335` | `64.7`th | `-0.165` | `-0.1461` | protective | within-week voltage noise is 1.13x own baseline — elevated 65th fleet percentile; z=-0.16 |
| 2 | `rest_vsi_p05_delta90` | `0.0222` | `55.9`th | `+0.275` | `-0.0742` | protective | rest-voltage floor delta = +0.022 V vs own baseline — stable/rising; z=+0.27, 56th fleet pctile |
| 3 | `vsi_range_trend` | `0.0191` | `72.1`th | `-0.160` | `+0.0663` | toward failure | drive-voltage range trend = +0.0191 V/wk — widening (risk direction univariately); z=-0.16, 72th fleet pctile; NOTE: multivariate suppressor (see coefficient table) |
| 4 | `dip_depth_last90_delta` | `0.2163` *(imputed)* | `51.5`th | `-0.060` | `-0.0085` | protective | crank dip depth delta = +0.216 V vs baseline — deepening dips (heavier load signature); z=-0.06, 51th fleet pctile |

**Note on `vsi_range_trend` sign:** multivariate coefficient is negative (ridge suppressor effect, r=+0.82 with noise ratio). Univariate direction is positive = widening = risk. See global coefficient table. This is a known artifact, not a physics contradiction.

## (d) Channel History

| Channel | Fired? | Notes |
|---|---|---|
| A1 (crank burst) | MASKED (SMA-dead) | Crank-event data absent; channel not evaluable |
| A2 (battery cascade) | `False` | Validated FP record: 0/20 NF false alarms (clean channel) |
| Persistence (RED >=3wk) | `False` (terminal); streak=`0` wk | Validated FP: 4/20 NF end in persistence fire state |
| First channel / first fire date | `NONE` / `—` | — |

> **SMA-DEAD:** Crank-event channels (A1) are not available for this truck. VSI persistence channel remains valid. If SMA is dead while tier is RED/AMBER, trigger manual inspection within 72 hours.

## (e) Evidence Window

- **Evidence state:** `GREEN_tier_channel_fires_eventually`
- **Empirical n:** 3 (retrospective fleet)
- **Median lead to failure:** 160 days
- **95% bootstrap CI:** [28d, 168d]
- **Scheduling window:** Next scheduled service (50,000 km or 6 months)
- **Honest caveat:** 3/4 GREEN-failed trucks eventually fired a channel. 1 (VIN9_F) fired nothing — irreducible blind spot.
- **NOT a countdown clock.** This window is retrospective population data, not a per-truck timer.

## (f) Counterfactual

Reducing vsi_range_trend by 0.012 units (from 0.019 to 0.007) would move production prob below 0.35 (GREEN threshold), all else equal. [delta_z = -0.191]

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
