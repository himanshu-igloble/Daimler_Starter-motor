---
title: "V1 Starter Motor — Final Report: Crank Catalog, Ridge Classifier, Lead-Time Verdict"
status: "complete"
created: "2026-06-10"
updated: "2026-06-10"
---

# V1 Starter Motor (SM) — Final Report

Pipeline: `V1_SM` | Fleet: 34 independent trucks (14 failed + 20 non-failed) | Generated: 2026-06-10 by `STARTER MOTOR/src/V1_SM_final_report.py` (all numbers recomputed from pipeline artifacts at generation time).

> **VIN independence reminder:** SM VINs are completely different physical trucks from the ALT fleet — the `_SM` suffix is mandatory and no cross-dataset VIN-level comparison is valid.

---

## 1. Executive Summary

**The classifier works; the lead-time channel does not.**

- **Ridge classifier (4 features, 34-fold LOVO): AUROC 0.9214**, bootstrap 95% CI [0.765, 1.000], label-permutation p = 0.001. Recall 13/14 failed trucks caught, specificity 18/20 non-failed cleared — goals G1/G1a/G1b/G1c all met (target AUROC >= 0.85, recall >= 11/14, specificity >= 18/20, <= 8 features).
- **No validated lead-time channel exists.** 12/14 failed VINs show "trending" signals in their final 90 days — but so do 18/20 non-failed control trucks (90% false-positive rate). The trend battery cannot distinguish degradation from ordinary fleet variation at this sampling resolution. This mirrors the ALT finding (no 3–4-week precursor); SM additionally lacks the GED=2 channel entirely.
- **KT's headline crank claims largely did not survive** the gap-aware event definition: failed-truck cranks are only +3% longer (not +48%), and the whole-life failed-crank-rate threshold (">5% critical") flags *both* cohorts. Only the **last-90-day** failed-crank rate discriminates (single-feature AUROC 0.74) — degradation is a late *change*, not a lifetime level.
- **Deployment deliverable is risk bands, not day-precision RUL** (per the V10.6.2 ALT lesson: per-truck RUL cannot beat the fleet clock). Current non-failed fleet: 11 GREEN, 9 AMBER, 0 RED.

Honest caveats up front: n = 34 trucks; the bootstrap CI is wide ([0.77, 1.00]); 5 failed VINs go silent 32–142 days before their recorded failure date; crank duration is quantized by 5-second sampling.

---

## 2. Fleet & Data-Quality Summary

| Metric | Failed (n=14) | Non-failed (n=20) |
|--------|------------------|--------------------|
| Telemetry rows | 30,925,573 | 75,519,588 |
| Mean active days | 371 | 616 |
| Mean observed weeks | 55 | 93 |
| Mean VSI null rate | 13.3% | 18.6% |
| Mean SMA null rate | 16.5% | 26.9% |

Total: 106,445,161 rows across both parquets. Per-VIN detail: `STARTER MOTOR/results/V1_SM_data_quality.csv`.

**Plan §2 preliminary findings — confirmed/updated by the full pipeline:**

| Prelim finding | Status after full pipeline |
|----------------|----------------------------|
| F1: Silent-failure gap — 5/14 failed VINs stop transmitting before JCOPENDATE | **Confirmed.** VIN1 (72d), VIN4 (97d), VIN5 (32d), VIN8 (37d), VIN9 (142d). All windows anchored on t_end throughout; gap flagged in every per-VIN output; gap itself excluded as a feature (label leakage). |
| F2: GED=2 does not transfer from ALT | **Confirmed.** Zero GED=2 in all 14 failed VINs; SM timing analysis ran on crank physics (SMA) instead. GED retained as data-quality covariate only. |
| F3: Naive crank durations artifact-contaminated | **Confirmed and handled.** Gap-aware definition (intra-event gap <= 10s) yields 20,471 events; 13 flagged as artifacts (dur > 60s, max 145s) — kept but excluded from all duration/dip statistics. |
| F4: Crank inventory rich enough | **Confirmed.** Every VIN has >= 79 events (median 407, max 4139); KT floor of 50/VIN met fleet-wide. |
| F5: Observation-length asymmetry (371 vs 616 active days) | **Confirmed — leakage guard enforced.** Only rates and trends admitted as features; no cumulative counts, no observation length, nothing from SALEDATE/JCOPENDATE. |

---

## 3. Crank-Event Catalog & KT Reconciliation

Catalog: `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` — **20,471 crank events** (20,458 non-artifact: 6,351 failed-cohort + 14,107 non-failed-cohort; 13 artifacts flagged). Prelim gap-naive grouping found 20,729; the gap-aware definition is canonical.

**KT claim reconciliation (gap-aware, non-artifact events):**

| Metric | Failed | Non-failed | KT claim (KT_startermotor_alternator.md §6.4) | Verdict |
|--------|-------:|-----------:|------------------------------------------------|---------|
| Mean crank duration | 5.51s | 5.35s | 3.2s vs 2.2s (+48%) | **Not reproduced.** Only +3.0% under the gap-aware definition; 5s sampling quantizes single-row events to a 5.0s floor (~93% of events), washing out absolute-duration contrast. |
| Mean dip depth (baseline − min VSI) | 4.67V | 4.60V | — (S4 channel) | **Direction only.** Failed cohort dips marginally deeper; not separable (single-feature AUROC 0.51). |
| Mean min-VSI during crank | 21.29V | 21.60V | 23.1V vs 24.0V | **Direction survives, magnitude does not.** Failed is lower by 0.31V (KT: 0.9V); absolute levels differ from KT's because 5s averaging smooths the true dip (S4, partially confirmed). |
| Failed-crank rate (whole life) | 9.7% | 15.9% | >5% critical | **Refuted as a lifetime threshold.** Both cohorts exceed 5%, and the non-failed cohort is *higher*. The discriminating form is the **last-90-day** rate (`failed_crank_rate_last90`, AUROC 0.74, winner feature) — a late change, not a level. |
| Multi-sample crank rate (>= 2 rows) | 7.1% | 6.0% | — (robust duration proxy) | **Weak, same direction.** Failed cranks span >= 2 samples slightly more often; not separable alone (AUROC 0.50). |

Net: the KT physics intuitions point the right way, but at 5-second sampling none of the absolute crank statistics separates the cohorts. What survives into the model is the *recent-window change* in crank success.

---

## 4. Feature Engineering & Screening (23 → 5)

Matrix: `STARTER MOTOR/results/V1_SM_feature_matrix.csv` — 34 rows x 23 features (13 Branch A crank-physics + 10 Branch B electrical/VSI weekly), rates and trends only, all last-N-day windows anchored on t_end.

Screening pipeline (Mann-Whitney p < 0.10 AND single-feature AUROC >= 0.60 → |Spearman r| < 0.85 → LOVO stability >= 80%) passed **5 of 23** into the candidate pool:

| Rank | Feature | Branch | AUROC | MW p | Cohen's d |
|------|---------|--------|-------|------|-----------|
| 1 | `vsi_std_ratio_30d` | B | 0.879 | 0.0002 | +1.43 |
| 2 | `vsi_dominant_freq` | B | 0.748 | 0.0157 | +0.91 |
| 3 | `failed_crank_rate_last90` | A | 0.740 | 0.0217 | +0.78 |
| 4 | `vsi_range_trend` | B | 0.732 | 0.0114 | +1.05 |
| 5 | `vsi_rest_p05_last90` | B | 0.704 | 0.0480 | -0.67 |

**Branch B (electrical/VSI weekly — the family that won for ALT) won again**: 4 of 5 pool features. The only crank-physics survivor is `failed_crank_rate_last90`. 18 features failed screening, including every absolute crank statistic (duration, dip depth, retry rate) — consistent with the §3 reconciliation.

---

## 5. Classifier Results

Exhaustive subset search (k = 4–5 from the 5-feature pool = 6 subsets x 34-fold LOVO; per fold: train-median imputation → StandardScaler → RidgeClassifier(alpha=1.0)):

| Subset | k | AUROC | Recall | Specificity | MCC |
|--------|---|-------|--------|-------------|-----|
| vsi_std_ratio_30d + vsi_dominant_freq + failed_crank_rate_last90 + vsi_range_trend | 4 | 0.9214 | 0.929 | 0.900 | 0.821 |
| vsi_std_ratio_30d + vsi_dominant_freq + failed_crank_rate_last90 + vsi_range_trend + vsi_rest_p05_last90 | 5 | 0.9143 | 0.929 | 0.850 | 0.768 |
| vsi_std_ratio_30d + vsi_dominant_freq + vsi_range_trend + vsi_rest_p05_last90 | 4 | 0.9107 | 0.929 | 0.900 | 0.821 |
| vsi_std_ratio_30d + vsi_dominant_freq + failed_crank_rate_last90 + vsi_rest_p05_last90 | 4 | 0.9071 | 0.857 | 0.850 | 0.701 |
| vsi_std_ratio_30d + failed_crank_rate_last90 + vsi_range_trend + vsi_rest_p05_last90 | 4 | 0.8286 | 0.714 | 0.800 | 0.514 |
| vsi_dominant_freq + failed_crank_rate_last90 + vsi_range_trend + vsi_rest_p05_last90 | 4 | 0.7857 | 0.714 | 0.900 | 0.633 |

**Winner (k = 4): `vsi_std_ratio_30d` + `vsi_dominant_freq` + `failed_crank_rate_last90` + `vsi_range_trend`**

| Metric | Value |
|--------|-------|
| LOVO AUROC | **0.9214** |
| Bootstrap 95% CI (N=200, fixed LOVO preds) | [0.7651, 1.0000] |
| Label-permutation p (N=1000) | 0.0010 |
| Youden threshold (from pooled out-of-fold predictions) | 0.4382 |
| Recall | 13/14 (0.929) |
| Specificity | 18/20 (0.900) |
| F1 / MCC | 0.897 / 0.821 |

In-sample permutation importance (diagnostic only — not an out-of-fold estimate):

| Feature | AUROC drop (mean) | std |
|---------|------------------:|-----|
| `vsi_std_ratio_30d` | +0.1492 | 0.0508 |
| `vsi_dominant_freq` | +0.1137 | 0.0430 |
| `vsi_range_trend` | +0.0605 | 0.0292 |
| `failed_crank_rate_last90` | +0.0002 | 0.0113 |

**Methodological benchmark — ALT V10.5.3 (AUROC 0.927, 6 features, n=25):** the SM result (0.921, 4 features, n=34) was produced by the same recipe (weekly aggregation → screening → exhaustive subsets → LOVO Ridge) and lands in the same performance regime. **These numbers are NOT comparable** — different fleets, different components, different failure mechanisms; the comparison validates the *methodology*, nothing more. Both runs independently confirm the fewer-features lesson (4–6 features beat larger subsets at n <= 34).

### Per-VIN LOVO predictions

| VIN | Cohort | LOVO P(fail) | Tier | Predicted | Correct | Silent-gap |
|-----|--------|-------------:|------|-----------|---------|------------|
| VIN11_F_SM | Failed | 0.9457 | RED | FAIL | yes |  |
| VIN1_F_SM | Failed | 0.8789 | RED | FAIL | yes | yes (72d) |
| VIN3_F_SM | Failed | 0.7255 | RED | FAIL | yes |  |
| VIN5_F_SM | Failed | 0.7246 | RED | FAIL | yes | yes (32d) |
| VIN6_F_SM | Failed | 0.7010 | RED | FAIL | yes |  |
| VIN10_F_SM | Failed | 0.6976 | RED | FAIL | yes |  |
| VIN14_F_SM | Failed | 0.6736 | RED | FAIL | yes |  |
| VIN7_F_SM | Failed | 0.5138 | AMBER | FAIL | yes |  |
| VIN4_F_SM | Failed | 0.5045 | AMBER | FAIL | yes | yes (97d) |
| VIN9_F_SM | Failed | 0.4825 | AMBER | FAIL | yes | yes (142d) |
| VIN13_F_SM | Failed | 0.4784 | AMBER | FAIL | yes |  |
| VIN2_F_SM | Failed | 0.4748 | AMBER | FAIL | yes |  |
| VIN12_F_SM | Failed | 0.4382 | AMBER | FAIL | yes |  |
| VIN8_F_SM | Failed | 0.3031 | GREEN | OK | **MISS** | yes (37d) |
| VIN9_NF_SM | Non-failed | 0.5407 | AMBER | FAIL | **MISS** |  |
| VIN8_NF_SM | Non-failed | 0.4559 | AMBER | FAIL | **MISS** |  |
| VIN13_NF_SM | Non-failed | 0.4293 | AMBER | OK | yes |  |
| VIN20_NF_SM | Non-failed | 0.3959 | AMBER | OK | yes |  |
| VIN7_NF_SM | Non-failed | 0.3846 | AMBER | OK | yes |  |
| VIN18_NF_SM | Non-failed | 0.3743 | AMBER | OK | yes |  |
| VIN12_NF_SM | Non-failed | 0.3634 | AMBER | OK | yes |  |
| VIN5_NF_SM | Non-failed | 0.3546 | AMBER | OK | yes |  |
| VIN11_NF_SM | Non-failed | 0.3546 | AMBER | OK | yes |  |
| VIN14_NF_SM | Non-failed | 0.3485 | GREEN | OK | yes |  |
| VIN2_NF_SM | Non-failed | 0.3395 | GREEN | OK | yes |  |
| VIN4_NF_SM | Non-failed | 0.3357 | GREEN | OK | yes |  |
| VIN3_NF_SM | Non-failed | 0.3271 | GREEN | OK | yes |  |
| VIN10_NF_SM | Non-failed | 0.3199 | GREEN | OK | yes |  |
| VIN6_NF_SM | Non-failed | 0.3141 | GREEN | OK | yes |  |
| VIN17_NF_SM | Non-failed | 0.2777 | GREEN | OK | yes |  |
| VIN19_NF_SM | Non-failed | 0.2734 | GREEN | OK | yes |  |
| VIN15_NF_SM | Non-failed | 0.2630 | GREEN | OK | yes |  |
| VIN16_NF_SM | Non-failed | 0.2565 | GREEN | OK | yes |  |
| VIN1_NF_SM | Non-failed | 0.2410 | GREEN | OK | yes |  |

Misclassifications: **VIN8_F_SM** (P = 0.303, the one missed failure — also a 37-day silent-gap VIN whose final telemetry window predates the failure) and **VIN8_NF_SM, VIN9_NF_SM** (false alarms at the Youden cut; both sit in AMBER, not RED).

---

## 6. Lead-Time Analysis — No Validated Channel

Protocol: per VIN, Mann-Whitney of final-window (30/60/90d before t_end) weekly values vs that VIN's own baseline, for 8 signals (4 electrical + 4 crank-physics), plus Theil-Sen slope. The 20 non-failed trucks ran the **identical protocol as a false-positive control**.

**The control result is the headline: 18/20 non-failed trucks (90%) also test "trending."** A test battery that fires on 90% of healthy trucks provides no usable lead-time signal — the failed-cohort "trends" (12/14) are indistinguishable from ordinary fleet variation (seasonality, route changes, load changes). This is the SM analogue of the ALT lesson that long threshold-derived "lead times" are spurious.

### Failed VINs (n=14)

| VIN | Silent-gap | Verdict | Best signal | Lead vs t_end (d) | Lead vs JCOPENDATE (d) |
|-----|-----------|---------|-------------|------------------:|-----------------------:|
| VIN10_F_SM | - | trending | vsi_drive_std | 90 | 90 |
| VIN11_F_SM | - | trending | vsi_drive_range | 90 | 90 |
| VIN12_F_SM | - | trending | vsi_drive_std | 90 | 90 |
| VIN13_F_SM | - | trending | vsi_drive_std | 90 | 90 |
| VIN14_F_SM | - | trending | vsi_drive_range | 90 | 90 |
| VIN1_F_SM | 72d | flat | - | - | - |
| VIN2_F_SM | - | trending | vsi_drive_mean | 90 | 90 |
| VIN3_F_SM | - | trending | vsi_drive_mean | 90 | 90 |
| VIN4_F_SM | 97d | trending | vsi_drive_mean | 90 | 187 |
| VIN5_F_SM | 32d | insufficient-data | - | - | - |
| VIN6_F_SM | - | trending | vsi_drive_mean | 90 | 90 |
| VIN7_F_SM | - | trending | vsi_drive_std | 90 | 90 |
| VIN8_F_SM | 37d | trending | vsi_drive_std | 90 | 127 |
| VIN9_F_SM | 142d | trending | vsi_drive_range | 90 | 232 |

### Non-failed control (n=20) — verdict counts

| Verdict | Count |
|---------|-------|
| trending | 18 |
| late-spike | 1 |
| flat | 1 |
| insufficient-data | 0 |

**The one crank-specific signal:** VIN1_F_SM shows a failed-crank-rate spike in its final 90 days (MW p = 1.0e-04, direction up) — physically plausible solenoid-wear behaviour and the only crank-physics hit in the failed cohort. The protocol ruled it **insufficient-data** (30/60-day windows lacked the >= 3 weekly values required), so it does not count as a validated lead. It is the single candidate worth re-testing in V1.1 with daily aggregation.

**Conclusion: no validated lead-time channel exists for the SM fleet.** The classifier separates failed from non-failed trucks on their recent-window signatures, but nothing in this data reliably announces *when* a failing truck will fail. Deployment must therefore be risk-band-driven (§8), not countdown-driven.

---

## 7. Limitations

1. **n = 34 trucks.** Every statistic carries small-sample uncertainty; the bootstrap 95% CI on AUROC spans [0.77, 1.00]. The permutation test (p = 0.001) rules out chance, not optimism from pipeline choices.
2. **5 silent-gap VINs.** For VIN1/4/5/8/9 (_F_SM) the last 32–142 days before failure are unobserved. Their "final-window" features describe the truck *before* it went silent; the one missed failure (VIN8_F_SM) is a gap VIN.
3. **5-second sampling quantization.** ~93% of cranks land in a single sample; absolute duration and true dip depth are unresolved (KT S3/S4 stand partially). Crank features carry less information than they would at 1Hz.
4. **No GED channel.** ALT's only physics-based timing signal (GED=2) is absent from all 14 failed SM VINs — one fewer independent channel than the ALT pipeline had.
5. **In-sample feature importance is diagnostic only** (all-34 refit); it is not an out-of-fold effect-size estimate.
6. **Calendar-epoch asymmetry — measured (plan §5 control).** Failed trucks were observed on average 371 active days vs 616 for non-failed, over different calendar ranges. The calendar-truncation control (`V1_SM_epoch_control.py`) truncated all NF windows to the failed-fleet calendar end (cutoff 2025-12-29; 16/20 NF VINs truncated) and re-ran the winner-subset LOVO: AUROC 0.9214 → 0.9214 (drop -0.0000, threshold 0.05) — verdict **PASS**. No evidence the classifier exploits calendar-epoch differences.

---

## 8. Deployment Recommendation

**Deliverable: risk bands + maintenance windows — explicitly NOT day-precision RUL** (V10.6.2 ALT evidence: per-truck RUL MAE 142d vs 50d fleet-clock baseline; nothing in §6 suggests SM differs).

**Risk bands** (LOVO probability, Youden-anchored tiers: GREEN < 0.35 <= AMBER < 0.55 <= RED):

| Tier | Current non-failed fleet | Action |
|------|--------------------------|--------|
| RED (>= 0.55) | 0 trucks | Inspect starter/battery circuit at the next depot visit (target: within 2–4 weeks). Pull crank history; check battery health first (battery–starter cascade, DICV A6). |
| AMBER (0.35–0.55) | 9 trucks (VIN11_NF_SM, VIN12_NF_SM, VIN13_NF_SM, VIN18_NF_SM, VIN20_NF_SM, VIN5_NF_SM, VIN7_NF_SM, VIN8_NF_SM, VIN9_NF_SM) | No immediate action; re-score on the standard cadence and watch for tier escalation. Bundle a starter inspection into the next *scheduled* service. |
| GREEN (< 0.35) | 11 trucks | Normal operation. |

**Cadence:** re-score **monthly** (the winner features need 30–90-day windows to move; weekly re-scoring adds noise, not signal — though the weekly cache supports it if a truck enters RED and closer watch is wanted). Re-run: weekly cache update → features → score against the frozen `V1_SM_ridge_spec.json`.

**Maintenance-window guidance:** anchor on tier, not a predicted date. A RED truck warrants action within the next maintenance cycle; an AMBER truck warrants attention at the next scheduled service. Do not quote a days-to-failure number to operations — §6 shows the data cannot support one.

**What V1.1 could add:** daily-resolution re-test of the VIN1_F_SM failed-crank-rate spike; alert-on-tier-escalation (delta features) instead of static scoring; battery-health covariates from resting VSI; threshold re-tuning toward recall if the field cost of a missed failure exceeds ~9 false alarms.

---

## 9. Verification Gates — ALL PASS

| Gate | Result | Evidence |
|------|--------|----------|
| No leakage | **PASS** | winner features ['vsi_std_ratio_30d', 'vsi_dominant_freq', 'failed_crank_rate_last90', 'vsi_range_trend'] contain no forbidden token (gap, jcopen, saledate, obs_len, ...); all in admissible matrix columns |
| Label integrity | **PASS** | matrix 34 rows = 14 F + 20 NF; every label matches its vin_label file-membership suffix (_F_SM / _NF_SM) |
| Threshold honesty | **PASS** | Youden recomputed from lovo_predictions.csv = 0.4382 matches spec 0.4382; confusion matrix reproduced {'tp': 13, 'fp': 2, 'fn': 1, 'tn': 18}; per-subset OOF thresholds vary (6 distinct); source documents OOF Youden |
| Gap handling | **PASS** | all 5 GAP_VINS flagged in lead-time CSV with correct gap_days; data-quality CSV agrees; lead_vs_jcopen = lead_vs_t_end + gap_days; days_before_t_end anchor recomputed from events == telemetry t_end (exactly gap_days before JCOPENDATE) for every gap VIN |
| Artifact handling | **PASS** | VIN14_F_SM (4 artifacts): matrix crank_dur_mean 7.4903s == artifact-excluded recompute 7.4903s, != artifact-included 8.0282s; 0 events with dur_s > 60s left unflagged |
| Reproducibility | **PASS** | ridge_spec config_snapshot pins seeds (random_state=42, bootstrap_seed=42, permutation_seed=43); V1_SM_feature_selection.py rerun via py -3 reproduced V1_SM_feature_screening.csv byte-identically |

---

## 10. Artifact Inventory

| Artifact | Path | Contents |
|----------|------|----------|
| Pipeline config | `STARTER MOTOR/src/V1_SM_config.py` | Constants, sentinels, GAP_VINS, seeds |
| Weekly cache builder | `STARTER MOTOR/src/V1_SM_build_weekly_cache.py` | → 34 parquets + data-quality CSV |
| Crank-event extractor | `STARTER MOTOR/src/V1_SM_crank_events.py` | → events parquet + KT reconciliation |
| Feature builder | `STARTER MOTOR/src/V1_SM_features.py` | → 34x25 feature matrix |
| Feature screening | `STARTER MOTOR/src/V1_SM_feature_selection.py` | → screening CSV (23 → 5 pool) |
| Ridge + subset search | `STARTER MOTOR/src/V1_SM_ridge_classifier.py` | → elimination CSV, LOVO predictions, spec JSON |
| Lead-time analysis | `STARTER MOTOR/src/V1_SM_lead_time.py` | → verdicts CSV (816 rows) |
| Production graphs | `STARTER MOTOR/src/V1_SM_production_graphs.py` | → 34 per-VIN dashboards |
| Final report generator | `STARTER MOTOR/src/V1_SM_final_report.py` | → this report + verification gates |
| Weekly cache | `STARTER MOTOR/cache/weekly/V1_SM_weekly_{VIN}.parquet` | 34 files |
| Crank-event catalog | `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` | 20,471 events, 16 cols |
| Data quality | `STARTER MOTOR/results/V1_SM_data_quality.csv` | 34 rows |
| Feature matrix | `STARTER MOTOR/results/V1_SM_feature_matrix.csv` | 34 x 25 |
| Feature screening | `STARTER MOTOR/results/V1_SM_feature_screening.csv` | 23 rows |
| Elimination results | `STARTER MOTOR/results/V1_SM_elimination_results.csv` | 6 subsets |
| LOVO predictions | `STARTER MOTOR/results/V1_SM_lovo_predictions.csv` | 34 rows |
| Ridge spec (frozen model) | `STARTER MOTOR/results/V1_SM_ridge_spec.json` | Winner spec + config snapshot |
| Lead-time verdicts | `STARTER MOTOR/results/V1_SM_lead_time_verdicts.csv` | 816 rows (34 VINs x 8 signals x 3 windows) |
| Epoch-leakage control | `STARTER MOTOR/src/V1_SM_epoch_control.py` | Plan §5 calendar-truncation control → result JSON |
| Epoch control result | `STARTER MOTOR/results/V1_SM_epoch_control.json` | cutoff 2025-12-29, AUROC drop -0.0000, verdict PASS |
| Dashboards | `STARTER MOTOR/graphs/V1_SM_{VIN}_dashboard.png` | 34 files |
| Final report | `STARTER MOTOR/reports/V1_SM_final_report.md` | This document |

*Plan: `STARTER MOTOR/Plan/V1_SM_plan.md` (+ prelim analysis). Canonical column reference: `docs/column_dictionary.md`.*
