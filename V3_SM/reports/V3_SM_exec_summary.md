---
title: "V3 Starter Motor — Executive Summary"
status: "complete"
created: "2026-07-01"
program: "SM V3"
---

# V3 Starter Motor — Executive Summary

## What Was Tested

V3 tested the one part of the feature space that prior iterations had left genuinely
untouched: **interaction / cross features** and **usage / probe features**.

Seven candidates were pre-registered and evaluated under the locked V1.1/V2.1 gate:

- **4 interaction features (F3):** multiplicative combinations of the voltage, crank-rate,
  and load signals — designed to capture the cumulative electrical stress-dose mechanics
  that a linear model on marginals cannot see: `dose_dip_x_starts`, `weakbat_cold_load`,
  `reg_instab_x_usage`, `sag_under_load`.

- **1 usage feature (F1):** rate of cold starts as a duty-cycle stressor —
  `cold_start_fraction_delta90`.

- **2 probe features (F4):** cross-system null-checks — GED alternator state as an SM
  covariate (`ged3_rate_delta90`); time-of-day start pattern as a usage signature
  (`night_start_fraction_delta90`).

Every candidate was pre-registered before any data was touched. The gate thresholds
(MW p ≤ 0.10, oriented AUROC ≥ 0.60, incremental Δ AUROC ≥ +0.01) were fixed in V1.1
and not adjusted.

---

## The Result

**All 7 candidates REJECTED. The data ceiling holds.**

| Metric | Value |
|---|---|
| Reconciliation — modal-4 non-nested LOVO AUROC | 0.9357 (reproduced exactly) |
| Frozen nested baseline | 0.9321 |
| Best univariate candidate (oriented AUROC) | reg_instab_x_usage — 0.6536; MW p = 0.1643 |
| Best incremental candidate (E2 Δ) | weakbat_cold_load — +0.0071; below +0.01 bar |
| BH-FDR smallest adjusted p (7 tests) | 0.7363 (weakbat_cold_load) |
| GBM model-class probe LOVO AUROC | 0.8429 — lower than linear Ridge 0.9321 |

No candidate cleared E1 (requires MW p ≤ 0.10 AND AUROC ≥ 0.60). No candidate cleared
E2 (requires Δ ≥ +0.01). E3 nested rerun was not triggered (no survivors).

After multiplicity correction (Benjamini–Hochberg, 7 tests), the smallest adjusted
p-value is 0.7363 — nothing approaches significance.

The GBM nonlinear model-class probe scored LOVO AUROC = 0.8429 on the full 11-feature
pool (modal-4 + all 7 V3 candidates). This is substantially below the linear Ridge on the
4-feature set (0.9321). The cap is the **data**, not the linear model class.

---

## Bottom Line

The starter motor failure-risk classifier is feature-complete at the current dataset.
The 4-feature modal set (vsi_withinwk_std_ratio_30d_w, rest_vsi_p05_delta90,
vsi_range_trend, dip_depth_last90_delta) achieves AUROC 0.9321 nested / 0.9357
non-nested. V3 has now tested the interaction/usage surface under the locked gate and
confirmed: **no additional feature from the existing 6-signal / 5-second frame carries
incremental predictive signal for SM failure at n = 34.**

This is the correct, expected result. It strengthens confidence in the frozen production
model by ruling out the last untested branch of the feature space.

---

## Single Most Valuable Next Step

The only path to higher performance is **new instrumentation**. The binding constraints
are the 5-second cadence (destroys sub-second crank waveform physics), the absence of a
current channel (no direct brush/solenoid health measurement), and the 34-truck sample
size (wide confidence intervals, one missed VIN = ~7 pp recall swing).

The highest-ROI intervention: **IBS / current-clamp instrumentation** to capture the
per-crank current waveform. This unlocks brush wear, solenoid contact degradation, and
battery internal resistance estimates that the voltage-only frame cannot reach. See
`appendix/new_data_roadmap.md` for the full three-path specification.

---

*All numbers cited from `V3_gate_summary.json` and `V3_validation.json`. Fleet: SM dataset,
n = 34 trucks (14 failed / 20 non-failed). SCREEN-GRADE caveat applies throughout.*
