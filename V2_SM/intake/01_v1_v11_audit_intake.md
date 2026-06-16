---
title: "V1 + V1.1 SM Program Audit Intake Document"
status: "complete"
created: "2026-06-12"
author: "Audit Intake Agent"
scope: "STARTER MOTOR V1 (git tag v1-sm) + V1.1 (2026-06-10 complete)"
---

# SM Predictive-Maintenance Program — V1 + V1.1 Audit Intake

> **VIN Independence:** SM VINs are completely independent from ALT VINs. Never cross-reference.
> SM fleet = 34 trucks: 14 failed (VIN1_F_SM–VIN14_F_SM), 20 non-failed (VIN1_NF_SM–VIN20_NF_SM).

Pre-read files (max one line each, per scope instructions):
- `V1.1/reports/V1_1_SM_experiment_results.md` — X2 nested-LOVO run record, AUROC 0.9321, gates, fold stats.
- `V1.1/results/V1_1_SM_gates.json` — machine-readable gate outcomes: G1 PASS, G4 FAIL (subset instability), G6 PASS.
- `V1.1/results/V1_1_SM_model_spec.json` — frozen V1.1 model: 4 features, nested AUROC 0.9321, permutation p=0.005.

---

## A. ARCHITECTURE MAP

### A1. Raw Data (canonical inputs)

| Key | Path | Rows | VINs |
|-----|------|------|------|
| sm_failed | `Data/processed/starter_motor_complete/2026-03-06-12-38-23-starter_motor_failed.parquet` | 30,925,573 | 14 |
| sm_nonfail | `Data/processed/starter_motor_complete/2026-03-06-12-39-14-starter_motor_non_failed.parquet` | 76,250,496 | 20 |

FACT: Failed file has 11 columns (incl. SALEDATE, JCOPENDATE, Failure_type); NF file has 8 (no sale/failure metadata). `Plan/V1_SM_plan.md §1.2`

### A2. V1 Pipeline (9 scripts under `STARTER MOTOR/src/`)

```
Raw parquets
  → V1_SM_build_weekly_cache.py  → cache/weekly/V1_SM_weekly_{VIN}.parquet (34 files)
                                 → results/V1_SM_data_quality.csv
  → V1_SM_crank_events.py        → cache/events/V1_SM_crank_events.parquet (20,471 events)
  → V1_SM_features.py            → results/V1_SM_feature_matrix.csv (34×23)
  → V1_SM_feature_selection.py   → results/V1_SM_feature_screening.csv (23→5 pool)
  → V1_SM_ridge_classifier.py    → results/V1_SM_elimination_results.csv (6 subsets)
                                 → results/V1_SM_lovo_predictions.csv (34 rows)
                                 → results/V1_SM_ridge_spec.json (frozen model)
  → V1_SM_lead_time.py           → results/V1_SM_lead_time_verdicts.csv (816 rows)
  → V1_SM_epoch_control.py       → results/V1_SM_epoch_control.json
  → V1_SM_production_graphs.py   → graphs/V1_SM_{VIN}_dashboard.png (34 files)
  → V1_SM_final_report.py        → reports/V1_SM_final_report.md
```

FACT: config constants at `src/V1_SM_config.py` (single source of truth for sentinels, seeds, GAP_VINS, crank thresholds). `reports/V1_SM_final_report.md §10`

### A3. V1.1 Pipeline (9 scripts under `STARTER MOTOR/V1.1/src/`)

```
V1 cache (read-only) + raw parquets
  → V1_1_SM_build_daily_cache.py   → V1.1 daily aggregates (daily crank features for A1 alarm)
  → V1_1_SM_features.py            → V1.1/results/V1_1_SM_feature_matrix.csv (34×10 clean pool)
                                   → V1.1/results/V1_1_SM_feature_admissibility.csv
                                   → V1.1/results/V1_1_SM_feature_matrix_L40control.csv
  → V1_1_SM_nested_ridge.py        → V1.1/results/V1_1_SM_nested_fold_winners.csv
                                   → V1.1/results/V1_1_SM_nested_lovo_predictions.csv
                                   → V1.1/results/V1_1_SM_model_spec.json
                                   → V1.1/results/V1_1_SM_gates.json
  → V1_1_SM_alerts.py              → V1.1/results/V1_1_SM_alert_validation.csv
                                   → V1.1/results/V1_1_SM_alert_sensitivity.csv
                                   → V1.1/results/V1_1_SM_alert_policy.csv
  → V1_1_SM_horizon.py             → V1.1/results/V1_1_SM_horizon_curve.csv
  → V1_1_SM_explainability.py      → V1.1/results/V1_1_SM_explanations.json
  → V1_1_SM_production_graphs.py   → V1.1 production dashboards
  → V1_1_SM_daily_risk_graphs.py   → daily-resolution risk graphs
  → V1_1_SM_vin_display_map.py     → V1.1/results/V1_1_SM_vin_naming_map.csv
```

Reports: `V1.1/reports/` — 10 files including experiment_results, alerts_horizon, model_card, comparison_report, executive_recommendation, explanation_cards, RESULTS_MASTER.
Presentations: `V1.1/presentation/` — 2 pptx files + 2 builder scripts.

### A4. Audit + Discovery Scripts

```
V1.1/audit/scripts/  (12 scripts) → V1.1/audit/out/*.csv + V1.1/audit/results/*.json
V1.1/discovery/scripts/ (12 scripts) → V1.1/discovery/out/*.{csv,parquet}
```

---

## B. RESULTS LEDGER

### B1. V1 Numbers (Original vs Restated)

| Metric | V1 Reported | Restated (honest nested) | Source |
|--------|-------------|--------------------------|--------|
| LOVO AUROC | **0.9214** | **0.8929** (optimism +0.0285) | `C_model_audit.md §1` |
| Bootstrap 95% CI | [0.765, 1.000] | [0.746, 1.000] | `C_model_audit.md §1` |
| Recall @ threshold | 13/14 (pooled post-hoc Youden) | **12/14** (per-fold Youden) | `C_model_audit.md §2` |
| Specificity | 18/20 | 18/20 | `C_model_audit.md §2` |
| Permutation p | 0.001 (N=1000) | — | `results/V1_SM_ridge_spec.json` |
| Youden threshold | 0.4382 (pooled post-hoc) | 0.4203–0.4929 per fold | `C_model_audit.md §2` |
| F1 / MCC | 0.8966 / 0.8213 | — | `results/V1_SM_ridge_spec.json` |
| Model class | RidgeClassifier(alpha=1.0) | confirmed best | `C_model_audit.md §4` |
| Feature pool → winner | 23→5→k=4 | — | `reports/V1_SM_final_report.md §4–5` |
| Winner features | vsi_std_ratio_30d, vsi_dominant_freq, failed_crank_rate_last90, vsi_range_trend | — | `results/V1_SM_ridge_spec.json` |

FACT (V1): VIN12_F_SM's TP at the pooled Youden threshold is an artifact — score (0.4382) equals the threshold exactly; honest operating point 12/14 recall. `C_model_audit.md §2`

FACT (V1): in-sample permutation importance of `failed_crank_rate_last90` = 0.0002 ± 0.011 — it contributes ~nothing to the model; dropped in 6/34 nested folds. `C_model_audit.md §1`

FACT (V1): epoch control (calendar truncation) — AUROC drop -0.0000 (PASS); but control only removes ≤7 trailing NF weeks, never equalizes history length. `results/V1_SM_epoch_control.json` + `B_feature_audit.md §1.3`

### B2. V1.1 Headline Metrics (Experiments X1–X6)

| Metric | Value | Source |
|--------|-------|--------|
| **Nested LOVO AUROC** | **0.9321** | `V1_1_SM_model_spec.json` |
| Non-nested (modal subset) | 0.9357 | `V1_1_SM_model_spec.json` |
| Optimism | 0.0036 | `V1_1_SM_model_spec.json comparisons` |
| Bootstrap 95% CI (N=200) | [0.8107, 0.9861] | `V1_1_SM_model_spec.json` |
| Permutation p | 0.005 (N=200, runtime-bounded from N=1000 target) | `V1_1_SM_model_spec.json` |
| Per-fold threshold: recall | 13/14 (0.929) | `V1_1_SM_model_spec.json headline` |
| Per-fold threshold: specificity | 15/20 (0.75) | `V1_1_SM_model_spec.json headline` |
| F1 / MCC | 0.8125 / 0.6691 | `V1_1_SM_model_spec.json` |
| Calibration slope | 0.86 (in [0.5, 2] → probabilities ship) | `V1_1_SM_gates.json G3` |
| Brier (recalibrated) | 0.124 vs 0.2422 reference | `V1_1_SM_gates.json G3` |
| Jackknife AUROC range | [0.9269, 0.9511] (std 0.007) | `V1_1_SM_gates.json G5` |
| L40 fixed-window control | 0.9357 → 0.9357 drop 0.0 (PASS) | `V1_1_SM_gates.json G1` |
| Gate G4 (winner stability) | **FAIL** — 3 distinct subsets, modal count 14/34 | `V1_1_SM_gates.json G4` |

INTERPRETATION: V1.1 modal winner 4-set (`vsi_withinwk_std_ratio_30d_w`, `rest_vsi_p05_delta90`, `vsi_range_trend`, `dip_depth_last90_delta`) wins 14/34 folds; two 3-feature subsets cover the other 20 — G4 FAIL indicates subset selection variability across folds, not model instability per se (jackknife std 0.007). `V1_1_SM_gates.json G4`

### B3. Audit A (Data Quality) Key Findings

- `Failure_type` = "Starter Motor" on ALL 30.9M rows — useless for mode separation. FACT: `A_data_quality_audit.md §1`
- **SMA-dead cohort**: VIN8_F, VIN9_F + VIN10/11/12/13/20_NF — SMA null 99.74–99.92%, event-triggered config, 10× event rates vs continuous-broadcast trucks. FACT: `A_data_quality_audit.md §2`
- Gap counts are pure observation-length leakage: NF mean 22.4 gaps vs failed 7.6; AUROC 0.875/0.868. FACT: `A_data_quality_audit.md §3`
- VSI quantized at 0.2 V; per-truck regulation setpoints range 27.6–28.2 V (≈1 quantization step); cross-VIN pooled VSI levels smear a calibration term as large as most degradation effects. FACT: `A_data_quality_audit.md §4`
- Stuck-value episodes: VIN7_NF longest run 42,133 samples (~58 h); 13 VINs have ≥10 runs over 30 min. Failed cohort does NOT have more stuckness (mean max-run 776 F vs 3,272 NF). FACT: `A_data_quality_audit.md §4`
- Leakage ceilings: n_weeks AUROC **0.952**, t_start ordinal **0.893**, active_days_total 0.946 — all above V1's 0.921. FACT: `A_data_quality_audit.md §6`
- 16/20 NF trucks end exactly at 2026-02-09/16 (extraction date wall). FACT: `A_data_quality_audit.md §6`
- Latent degradation: Δ(vsi_drive_std) last-8-wk AUROC **0.893**, calendar-matched control **0.889**. 9/14 failed VINs show Δ ≥ +0.15; 0 NF exceedances at this working point. FACT: `A_data_quality_audit.md §7`

### B4. Audit B (Feature) Key Findings

- `vsi_dominant_freq` is a **1/n_weeks artifact**: periodogram grid k/n; 17/34 VINs have dominant freq = 1/n_weeks; r(dominant_freq, 1/n_weeks) = +0.425; L40 control AUROC 0.525 (from 0.748, −0.223). BANNED from V1.1. FACT: `B_feature_audit.md §1.4`
- `vsi_std_ratio_30d` partial inflation: L40 AUROC 0.793 vs full-history 0.879 (drop −0.086). Survives but redefined on L40 basis in V1.1. FACT: `B_feature_audit.md §1.4`
- `failed_crank_rate_last90` and `vsi_range_trend` survive L40 control exactly (drop 0.000). FACT: `B_feature_audit.md §1.4`
- New V1.1 discovery: `vsi_withinwk_std_ratio_30d` (within-week supply-voltage noise) AUROC 0.9679, L40-windowed version survives at 0.9214, r(span)=0.60 — use `_w` (windowed) form. FACT: `B_feature_audit.md §2`
- B4 model variants: drop vsi_dominant_freq → AUROC 0.864; honest 3-feat (J: std_ratio_30d + withinwk_w + fcr_last90) → 0.9143, VIN8_F prob 0.447 (captured at cost of VIN1_F becoming miss + 5 NF FAs). FACT: `B_feature_audit.md §2 B4 table`
- VIN8_F_SM miss diagnosis: fcr_last90=0.006 (24th pctile), vsi_range_trend=−0.044 (3rd pctile), vsi_dominant_freq votes "healthy" (81 masked weeks, NF-like). Failure transient never telemetered (37d silent gap). FACT: `B_feature_audit.md §1.6`

### B5. Audit C (Model) Key Findings

- Nested LOVO restated baseline: **AUROC 0.893**, recall 12/14, spec 18/20. `C_model_audit.md §1`
- Selection stability: 27/34 folds pick exactly the V1 winner 4-set; `vsi_std_ratio_30d` + `vsi_dominant_freq` in 34/34 folds. `C_model_audit.md §1`
- Model-class sweep (same 4 features): Ridge 0.9214 = RandomForest 0.9214 (but RF has 6 FPs, no interpretability gain); LogReg(C=1) 0.9143; all linear/smooth models 0.89–0.92; trees/boosting 0.67–0.78. Ridge confirmed. `C_model_audit.md §4`
- Calibration: recalibration slope **4.72** — severely compressed scores; tier labels valid, numeric probabilities invalid in V1. `C_model_audit.md §3`
- Brier V1 OOF: 0.1491 vs 0.2422 reference. `C_model_audit.md §3`
- V1.1 calibration (slope 0.86, in-range): probabilities ship. `V1_1_SM_gates.json G3`
- Jackknife: range [0.9154, 0.9731]; removing VIN8_F_SM lifts to 0.9731 (the miss, not a support truck). `C_model_audit.md §5`

### B6. Audit D (Physics) Key Findings

- Failure-mode taxonomy: 10 failure modes; solenoid contacts (Mode 1) is the canonical EOL path (Murugesan 2014: worn contacts 10–15 mΩ vs 0.02–0.05 mΩ new). `D_failure_physics.md §1`
- ADAC 2025: battery 45.4% of all breakdowns; starter+alternator+electrics ~10.6%. `D_failure_physics.md §3`
- 5-second sampling destroys: inrush transient, true dip shape, crank duration deltas <5 s, solenoid chatter, commutator dead-bar ripple. Preserves: event existence/count, retry clustering, failed starts, pre-crank resting VSI, post-start recovery. `D_failure_physics.md §2`
- Solenoid contacts: lead time days–weeks (partially observable via retry/failed-start bursts). Brush wear: 60–120 d physics horizon DESTROYED by 5 s sampling. Bearing seizure: zero warning. `D_failure_physics.md §2 table`
- Battery confound: all physical channels (deep dips, long cranks, retries) mimic modes 1/3/6/9 simultaneously; it is also a causal pathway (DICV A6 bidirectional cascade). `D_failure_physics.md §3`
- "No long lead time" is physically expected for the dominant modes at this instrument resolution. The 60–120 d channel exists in physics but is instrumentally invisible. `D_failure_physics.md §4c`
- Honest recall ceiling: ~10–11/14 for any lead-time claim (A4 silent/abrupt modes are irreducible). `D_failure_physics.md §6`
- Battery feature set for V1.1: first-crank-of-day probe, post-crank recovery/charge acceptance, pre-crank resting VSI (after ≥6 h rest). `D_failure_physics.md §5`

### B7. Discovery E (Patterns) Key Findings

- **E1 Clustering**: no global cluster structure separating failed from NF (spectral k=2/3 ARI ~0). PC1 = battery/rest-VSI block, PC2 = crank-quality block, PC4 = telematics config (r(sma_dead)=0.567). Ward k=2 4-cluster is ALL failed VINs {VIN2/3/6/13_F} but confounded with n_weeks (p=0.014) and t_start (p=0.0035). `E_pattern_discovery.md §1`
- **E2 Archetypes** (key deliverable):

| VIN | Archetype | Evidence summary |
|-----|-----------|------------------|
| VIN10_F | **A1 solenoid intermittency** | fcr 0.100→0.433 (4.3×), retry 0.038→0.283 (7.5×), 8 failed cranks/day, drive-VSI std ratio 2.56 |
| VIN14_F | **A1+A2 mixed** | fcr 0.252→0.449, retry 0.298, 12/day, rest-VSI −2.45 V + step −2.31 V, drive-VSI step +0.65 V, std ratio 5.36 |
| VIN1_F | **A1 then silent** | fcr 0.080→0.198 (2.5×), 9 failed cranks 2025-06-24, last crank failed; then 72 d gap |
| VIN2_F | **A2 battery cascade** | rest-VSI step −1.59 V, rest delta −0.73 V, 8/day, dip_depth +1.66 V |
| VIN3_F | **A2 battery cascade** | rest delta −1.00 V, rest step −1.70 V, drive step +0.47 V, std ratio 1.98 |
| VIN6_F | **A2 battery cascade** (strongest) | dip_depth +3.65 V, rest delta −2.12 V, rest step −2.71 V, drive step +0.67 V, std ratio 3.85 |
| VIN13_F | **A2 battery cascade** | rest delta −0.66 V, drive step +0.75 V, std ratio 2.80, dip_depth +1.09 V |
| VIN7_F | **A3 VSI-volatility only** | std ratio 2.57; fcr/retry/rest all NF-like |
| VIN11_F | **A3 VSI-volatility only** | std ratio 1.82; fcr improved (0.68×) |
| VIN12_F | **A3 VSI-volatility only** | std ratio 2.32; everything else NF-like |
| VIN4_F | **A4 silent/abrupt** | 97 d gap; std ratio 1.17 (marginal) |
| VIN5_F | **A4 silent/abrupt** | 32 d gap; 0 events and no VSI in final 120 d — card empty |
| VIN8_F | **A4 silent/abrupt** (V1 miss) | 37 d gap; fcr IMPROVED 0.103→0.005; std ratio 1.33 (mild) |
| VIN9_F | **A4 silent/abrupt** | 142 d gap; std ratio 1.02; all NF-like |

FACT: A1 definition = solenoid-contact intermittency prior (retry/failed-start bursts, days–weeks horizon). A2 = battery-cascade prior (resting-VSI decline + deeper dips + regulator pushing drive voltage up). A3 = regulation instability without crank/battery signature (could be early A2 or distinct mode). A4 = abrupt/no-precursor prior = silent-gap set minus VIN1_F. `E_pattern_discovery.md §2`

FACT: A2 corroboration by E5 step detection — the 4 largest negative rest-VSI steps in the whole fleet are VIN6_F/VIN14_F/VIN3_F/VIN2_F (−2.71/−2.31/−1.70/−1.59 V); the only 4 sustained drive-VSI up-steps ≥0.4 V are VIN13_F/VIN6_F/VIN14_F/VIN3_F. `E_pattern_discovery.md §2`

- **E3 Trajectories**: dominant failed trajectory is **gradual months-scale drift** (10/14 MONOTONE_DRIFT); 16/20 NF flat. Persistence rule (≥4-of-12 weeks above NF p90): **13/14 failed qualify** (miss: VIN9_F, 3 wks) vs **2/20 NF** — in-sample screen only. `E_pattern_discovery.md §3`
- **E4 Seasonality**: no month effect on vsi_drive_std levels (KW p=0.90) or rest VSI (p=0.95). NF trending flag IS seasonal (monsoon 9.1% vs winter 4.3%); but this cannot explain V1's 90% NF FP rate (17/20 NF end in February = winter). `E_pattern_discovery.md §4`
- **E5 Maintenance steps**: 5 NF trucks have battery-replacement rest-VSI step UP ≥0.5 V (VIN18_NF +1.40 V, VIN12_NF +0.70, VIN3_NF +0.61, VIN5_NF +0.61, VIN17_NF +0.59); VIN8_F has +0.60 V in 2024-06 (16 months pre-failure). Duty-cycle k=2 clusters show no failure alignment. `E_pattern_discovery.md §5`

### B8. Discovery F (Survival) Key Findings — F2/F3/F4

- **F2 Fleet clock**: KM median undefined (S(t) never crosses 0.5 with 14/34 events). Weibull: λ=133.3 wk, **ρ=2.03 (wear-out)**, median **111.3 wk (779 d)**, IQR 72.1–156.6 wk. Marginal weekly hazard 14/2,636 = **0.0053/wk**. `F_survival_analysis.md §2`
- **F2 Weibull LOVO conditional-median RUL MAE**: 28d eval → 485.5 d; 63d eval → 471.0 d; 91d eval → 460.5 d; last-26-wk trajectory → **461.9 d**. A constant 91-d prediction scores **44.4 d** (structural floor). `F_survival_analysis.md §2`
- **F3 Discrete-time hazard LOVO**: pooled weekly-hazard AUROC **0.747**; age-matched concordance **0.654**; P(fail≤30d) AUROC **0.744** (JCOPENDATE version 0.849); truck-level ranking AUROC **0.586** vs static model's 0.893. `F_survival_analysis.md §3`
- **F3 coefficient stability**: log_age +0.71±0.06; `vsi_std_ratio` +0.69±0.04 (workhorse); `crank_fail_rate` +0.40±0.45 (sign-unstable). `F_survival_analysis.md §3`
- **F3 Hazard model RUL MAE**: **576.1 d** (vs 44.4 d constant, 461.9 d Weibull fleet clock). `F_survival_analysis.md §5`
- **F4 Cox PH**: `vsi_std_ratio` HR **1.74** (coef 0.553, naive p=0.002); `rest_delta` HR 0.888 (p=0.33, NS); naive SEs anti-conservative under within-truck correlation. `F_survival_analysis.md §4`
- **VERDICT**: no survival layer ships. `F_survival_analysis.md §8`

### B9. Discovery G (Sequence) Key Findings — G3 + Horizon

- **G1 Parameter budget**: min LSTM (h=8) = 329 params = 235× over EPV-10 budget (14 events / 1.4 params). All deep architectures are 235×–6,275× over budget. Ridge is 4× over EPV-10. `G_sequence_representation.md §1`
- **G2 Probes**: PCA3(std+mean) + logistic AUROC **0.900** but dominant PC flagged (r(span)=0.55, r(n_weeks)=−0.52). Trend coeffs (std+mean) AUROC **0.925** but std_slope leak-flagged (r(n_weeks)=−0.56; G3 control shows correlation is label-mediated). All probes saturate at ~0.89–0.92. `G_sequence_representation.md §2`
- **G3 Prequential horizon** (frozen model, X4 validation): **k* = 10 weeks (~70 d)** — AUROC ≥ 0.836–0.921 for k=0..10, collapses to 0.536 at k=11. Decay confirmed: far-tail (k=23..26) mean 0.592, all tail CIs include 0.5. `V1_1_SM_alerts_horizon.md §5`
- Tiny-LSTM (h=2, 43 params) seed variance across seeds 0/1/2: AUROC **0.854/0.882/0.918** (spread 0.064) — seed variance alone > largest probe-vs-baseline difference. `G_sequence_representation.md §2e`

### B10. Alert Channel Validation (X3)

**Persistence rule** (≥4-of-12 weeks above training-fold NF p90):
- In-sample (E3): 13/14 recall, 2/20 NF FP. LOVO-validated: 13/14 recall, **4/20 NF FP** (FP rate doubled). `V1_1_SM_alerts_horizon.md §1`
- As deployed walking alarm: all 20/20 NF trucks enter fire state at least once (mean 31.4% of weeks in-fire). Only usable as terminal-state condition flag. `V1_1_SM_alerts_horizon.md §1`
- Median terminal-episode lead vs t_end: **168 d**. Minimum 28 d (VIN4_F). `V1_1_SM_alerts_horizon.md §1 table`

**A1 crank-burst alarm** (daily failed-cranks+retries, 7-d rolling sum > own-first-half mean+3σ ≥2 consecutive days):
- 4/12 applicable failed VINs fire (VIN10_F, VIN11_F, VIN12_F, VIN1_F). `V1_1_SM_alerts_horizon.md §2`
- NF false alarms: 8/15 applicable; **1.52 FP episodes/truck-year** — too noisy standalone. `V1_1_SM_alerts_horizon.md §2`
- Decision: ship only as tier-gated corroborator. `V1_1_SM_alerts_horizon.md §6`

**A2 battery-cascade triple detector** (rest-VSI step ≤ −0.5 V AND drive-VSI step ≥ +0.3 V within ±8 weeks AND dip-depth widening >1 V):
- 4/5 A2 battery VINs fire (VIN13/14/3/6_F). Miss: VIN2_F (cascade never produces qualifying paired drive-step). Median lead **66.5 d**. `V1_1_SM_alerts_horizon.md §3`
- **NF false alarms: 0/20.** Battery-replacement ups correctly rejected. `V1_1_SM_alerts_horizon.md §3`
- Decision: **SHIP**. `V1_1_SM_alerts_horizon.md §6`

**Combined policy**: 13/14 failed fire at least one channel (persistence first on 10, A1 first on 3). Full miss: VIN9_F (A4+SMA-dead+GREEN-tier). 3 GREEN-tier saves (VIN1/3/4_F). 10/20 NF completely clean. `V1_1_SM_alerts_horizon.md §4`

---

## C. ASSUMPTION REGISTER

| ID | Assumption | Defined at |
|----|-----------|-----------|
| C1 | `t_end = last telemetry timestamp` (NOT JCOPENDATE) — all features anchored here | `Plan/V1_SM_plan.md §2.2`, `src/V1_SM_config.py` |
| C2 | `t_fail = JCOPENDATE` — used only for lead-time dual-reporting, never for features | `Plan/V1_SM_plan.md §2.2` |
| C3 | GAP_VINS: VIN1_F (72d), VIN4_F (97d), VIN5_F (32d), VIN8_F (37d), VIN9_F (142d) — stop transmitting before JCOPENDATE | `src/V1_SM_config.py GAP_VINS` |
| C4 | SMA-dead cohort: VIN8_F, VIN9_F + VIN10/11/12/13/20_NF (SMA null >99%) — telematics configuration, not sensor degradation | `A_data_quality_audit.md §2`, `V1_1_SM_spec.md §0 finding 4` |
| C5 | Event definition: consecutive SMA=1 rows with intra-event Δt ≤ 10 s; duration = (last_ts − first_ts) + 5.0 s | `src/V1_SM_config.py CRANK_MAX_INTRA_GAP_S` |
| C6 | Artifact flag: crank duration > 60 s → `artifact=True` (kept, excluded from stats, never silently dropped) | `src/V1_SM_config.py CRANK_MAX_PLAUSIBLE_DUR_S` |
| C7 | Crank success: RPM ≥ 550 within event + 15 s | `src/V1_SM_config.py CRANK_SUCCESS_RPM` |
| C8 | Week construction: `group_by_dynamic(timestamp, every="1w")`; active-days denominator (not calendar) | `Plan/V1_SM_plan.md Task 2` |
| C9 | Admissibility: rates and trends only — no cumulative counts, no observation-length, no gap-days, no SALEDATE/JCOPENDATE | `Plan/V1_SM_plan.md §2.6`, `V1_1_SM_spec.md §2` |
| C10 | Median imputation (train-fold medians only); StandardScaler (train-fold stats only) — inside each LOVO fold | `Plan/V1_SM_plan.md §5`, `V1_1_SM_model_spec.json protocol` |
| C11 | SMA-dead feature masking: crank/SMA features set NaN for SMA-dead trucks → fold-internal mean imputation | `V1_1_SM_spec.md §2 rule 4`, `F_survival_analysis.md §1` |
| C12 | VSI per-VIN baseline correction (V1.1): all VSI features as ratios/deltas vs own history; rest-VSI re-baselined after detected battery-replacement steps | `V1_1_SM_spec.md §2 rule 5` |
| C13 | L40 fixed-window basis (V1.1): every feature computed on last 40 masked weeks only | `V1_1_SM_spec.md §3 rule 3`, `V1_1_SM_gates.json G1` |
| C14 | Youden threshold: per-fold inner-OOF (V1.1 pre-registered); V1 used pooled post-hoc (buying 1 TP) | `C_model_audit.md §2`, `V1_1_SM_model_spec.json protocol` |
| C15 | V1 crank-rate denominator: non-null-SMA observation time (not calendar time) | `Plan/V1_SM_plan.md §2.6` |
| C16 | Epoch control: failed-fleet calendar end = 2025-12-29 (VIN10_F_SM); 16/20 NF truncated in V1 control | `results/V1_SM_epoch_control.json cutoff_week` |

---

## D. ARTIFACT / LEAK REGISTER

| ID | Artifact | Program location | V1.1 mitigation | Residual risk |
|----|---------|-----------------|-----------------|---------------|
| D1 | `vsi_dominant_freq` = 1/n_weeks artifact (r=+0.425 with 1/n; L40 AUROC 0.525 from 0.748) | V1 winner feature | BANNED; replaced by `vsi_withinwk_std_ratio_30d_w` | None — removed entirely |
| D2 | Crank-duration artifacts: impossible cranks up to 25,234 s (VIN9_F), 71,656 s (VIN10_NF) from SMA=1 runs spanning gaps | V1 prelim + crank catalog | Gap-aware event definition (Δt ≤10 s split); `artifact=True` flag for >60 s | 13 remaining artifacts kept but excluded from all stats; "artifact excluded" in all downstream stats |
| D3 | Silent-failure gaps (5/14 failed VINs stop transmitting 32–142 d before JCOPENDATE) | V1 + V1.1 known | All windows anchored on t_end; GAP_VINS flagged in every output; gap itself excluded as feature | VIN9_F is structurally unobservable (SMA-dead + A4); VIN8_F partially recovered in V1.1 (prob 0.436–0.447) |
| D4 | SMA-dead config cohort (7 trucks, SMA null 99.7%+, 10× event rates) | V1 built features without distinction | All SMA/crank features cohort-masked (NaN) for SMA-dead trucks; fold-internal imputation | Cohort indicator NOT used as feature (would be a 4th covariate, partially label-correlated); pooling remains problematic if new features use raw SMA counts |
| D5 | Observation-length asymmetry (failed 371 vs NF 616 active days) — cumulative features = label proxy | V1 admissibility rules enforced (no counts) | L40 fixed window; mandatory L40 control gate G1 | n_weeks AUROC 0.952 remains the ceiling — any feature with r>0.5 vs n_weeks must justify via G3 time-locking evidence |
| D6 | `t_start` epoch leak: AUROC 0.893; failed trucks are systematically younger/later-sold (VIN2_F 2025-06, VIN3_F 2025-04); calendar-correlated features partially encode the label | V1 calendar-truncation control (too weak) | Mandatory L40 control + G3 time-locking disambiguation; G2 proxy audit reports r(OOF, t_start)=0.507 (above 0.5, justified by G3) | Label-mediated correlation confirmed as genuine by k-decay curve; residual risk: any future calendar/seasonal feature on end-anchored windows is banned |
| D7 | Pooled post-hoc Youden threshold (V1): buys 1 fake TP (VIN12_F_SM, score = threshold) | V1 reported 13/14 recall | V1.1 pre-registers per-fold inner-OOF Youden; V1 restated as 12/14 | None in V1.1 |
| D8 | V1 feature screening + subset selection on all 34 labels → selection optimism +0.029 AUROC | V1 non-nested pipeline | V1.1 fully nested LOVO (screen + select inside each fold) | V1.1 optimism = 0.0036 (much smaller); modal subset wins only 14/34 folds (G4 FAIL) |
| D9 | Battery-replacement step in rest-VSI (5 NF + VIN8_F) resets VSI baseline | Not handled in V1 | E5 step detection; rest-VSI features re-baselined post-step in V1.1 | VIN10_NF/VIN13_NF artifact-suspect negative steps (−3.0/−4.2 V at earliest split); not counted |
| D10 | VSI per-truck regulation setpoint offsets (27.6–28.2 V range ≈ 1 quantization step) — cross-VIN level features smear calibration terms | V1 used fleet-pooled absolute VSI levels | All V1.1 VSI features are per-VIN ratios/deltas vs own history | V1 `vsi_rest_p05_last90` (an absolute) dropped from V1.1 in favor of `rest_vsi_p05_delta90` |
| D11 | Density drift / telemetry taper before silence (VIN1_F 97.3% row-count drop, VIN5_F 88.7%) vs abrupt cutoff for VIN4/8/9_F | Informational only | Flagged in artifacts; not usable as feature (label leakage) | Remains descriptive insight only |
| D12 | `t_end` month ≈ label (failed ends scatter Jun–Dec, NF pile at Feb) — any calendar-month feature on end-anchored windows leaks | Identified in E4 | Calendar/season features on end-anchored windows banned in V1.1 | E4: NF trending-flag rate not seasonal at the magnitude needed to explain V1's 90% FP rate |

---

## E. WEAKNESS / GAP LIST

### E1. Tried and Refuted (with citations)

- **Per-truck day-precision RUL**: Weibull fleet-clock MAE 461.9 d, hazard MAE 576.1 d, vs constant 91-d at 44.4 d. `F_survival_analysis.md §5`. CLOSED.
- **Survival/hazard layer as risk score**: truck-level AUROC 0.586 vs static 0.893. `F_survival_analysis.md §3`. CLOSED.
- **Deep sequence models** (LSTM/BiLSTM/TCN/Transformer/TFT/Informer/PatchTST/TimeXer): 235×–6,275× over EPV-10 budget; 43-param LSTM seed-unstable (spread 0.064). `G_sequence_representation.md §1–2`. CLOSED.
- **Unsupervised anomaly detection standalone**: inherited from ALT program (80–100% FP at n=34). `Plan/V1_SM_plan.md §1.3`. CLOSED.
- **GED=2 channel**: absent from all 14 failed SM VINs; present only in 5 NF. `Plan/V1_SM_plan.md §2.3`. CLOSED.
- **KT +48% duration claim**: gap-aware definition yields only +3.0%; ~93% of cranks single-sample (5 s quantum). `reports/V1_SM_final_report.md §3`. REFUTED.
- **KT ">5% failed-crank rate is critical" as a lifetime threshold**: NF cohort mean 15.9% > failed 9.7%. `reports/V1_SM_final_report.md §3`. REFUTED.
- **Entropy/shape statistics**: vsi_weekly_entropy 0.525, vsi_spectral_entropy 0.539, dip_depth_skew 0.543, crank_dur_cv 0.639. `B_feature_audit.md §2`. CLOSED.
- **Gradient/acceleration features**: vsi_grad_last8 0.554, vsi_accel 0.593, vsi_drive_mean_last60_delta 0.554. `B_feature_audit.md §2`. CLOSED.
- **Health composites**: crank_health_last90 0.573 (p=0.50). `B_feature_audit.md §2`. CLOSED.
- **Duty/energy features**: sma_duty_last90 0.645 (p=0.16), sma_duty_ratio_90 0.611. `B_feature_audit.md §2`. CLOSED.
- **VSI dominant frequency** (spectral physics): AUROC 0.592 on fixed window — no real spectral signal. `B_feature_audit.md §1.4`. CLOSED.
- **V1 lead-time channel**: 12/14 failed "trending" but 18/20 NF also trending (90% FP). Not a validated lead-time channel. `reports/V1_SM_final_report.md §6`. CLOSED.

### E2. Never Tried / Open Gaps

- **Event-level signal exploitation at raw 5-second resolution**: SSL pretraining on ~106M SM rows (masked VSI reconstruction / next-window prediction → frozen encoder → ≤3-dim pooled head). The only defensible deep path. Requires n_failed ≥ 30–50 for meaningful benefit. `G_sequence_representation.md §3`
- **Cost model / alert economics**: no false-alarm cost vs missed-failure cost ratio analyzed. Tier thresholds (0.35/0.55) were chosen by Youden (sensitivity/specificity balance), not cost-optimized. Unaddressed at n=34.
- **Daily-aggregation re-test of the VIN1_F_SM failed-crank-rate spike**: weekly aggregation gave "insufficient-data" verdict (insufficient weekly points); daily aggregation would resolve this. Mentioned as V1.1 candidate but not executed in V1.1. `reports/V1_SM_final_report.md §6`
- **RPM-rise lag proxy** (samples from SMA onset until first RPM ≥ 550; season-conditioned): physics-motivated (D §5 rank 5), never screened in V1 or V1.1.
- **Extended crank tail rate (≥3 samples) with season conditioning**: V1.1 spec includes `extended_crank_tail_rate_last90` in pool; its season-conditioned version was not built (ambient/winter confound in RPM-rise time not addressed).
- **Free-spin discrimination** (unloaded spin vs loaded stall via dip depth): physically real for pinion/clutch vs contact faults; tested as low-expectation probe in D §5 but not implemented as a feature.
- **Post-crank charge acceptance** (VSI climb to ~28 V over 10–30 s after crank end): D §5 rank 6, KT §10.5 channel; not in V1 or V1.1 feature matrix.
- **First-crank-of-day battery probe** (resting VSI after ≥6 h, first-attempt success, retries-to-success): D §5 rank 3 (best battery-confound control), partially approximated by `rest_vsi_p05_delta90` in V1.1 but the controlled daily-experiment form was not built.
- **Discrete-time hazard on truck-weeks as calibrated weekly risk product** (not RUL): C audit §6a considered feasible (EPV≤3, ≤3 covariates, cluster-aware) and as the "highest expected value" model-class extension. Not implemented in V1.1 (F verdict killed it as RUL/ranking, but the calibrated-weekly-hazard use case was not fully explored).
- **Cross-validation with stratification on t_start**: the recruitment-epoch confound (t_start AUROC 0.893) has no stratified-fold mitigation yet; current LOVO randomly assigns folds.
- **Validation on a hold-out calendar period** (prospective testing): entire program is retrospective. No held-out time window exists.
- **Multiple-failure VINs or repeat-failure trucks**: program assumes single-event right-censoring; no data on whether any trucks had prior SM replacements (not available from the dataset).
- **Sub-5s inrush data or current sensing**: explicitly not available; noted as the instrument limit but a recommendation to DICV for future data collection has not been drafted.

---

## F. FAILED-VIN DOSSIER

| VIN | Archetype | Observable? | V1.1 tier | V1.1 recal. prob | V1 miss/FN? | Silent-gap (d) | Key evidence |
|-----|-----------|-------------|-----------|-------------------|-------------|----------------|--------------|
| VIN1_F_SM | A1 then silent | Partially (crank burst) | GREEN (AMBER via A1 alert) | 0.879 (V1 OOF) | No (V1 caught, GREEN-tier in V1.1) | fcr 2.5× rise, 9 bursts on 2025-06-24, then 72d gap; A1 alert fires 160d lead |
| VIN2_F_SM | A2 battery cascade | Yes (cascade detector) | RED | 0.475 (V1 OOF) | No | 0 | rest-VSI step −1.59V, dip_depth +1.66V; A2 detector misses (no paired drive step) |
| VIN3_F_SM | A2 battery cascade | Yes (cascade detector) | GREEN (AMBER via persistence) | 0.726 (V1 OOF) | No | 0 | rest step −1.70V, drive step +0.47V; A2 fires 91d; persistence fires 168d |
| VIN4_F_SM | A4 silent/abrupt | No | GREEN | 0.505 (V1 OOF) | No (AMBER V1 OOF) | 97 | std ratio 1.17 (marginal); persistence fires 28d vs t_end / 125d vs JCOPENDATE |
| VIN5_F_SM | A4 silent/abrupt | No (card empty) | RED | 0.725 (V1 OOF) | No | 32 | 0 events and no VSI in final 120d; persistence fires 392d (pre-gap); vsi_dominant_freq artifact voted RED |
| VIN6_F_SM | A2 battery cascade | Yes (cascade + persistence) | RED | 0.701 (V1 OOF) | No | 0 | Strongest A2 (dip +3.65V, rest step −2.71V); A2 fires 70d, persistence fires 168d |
| VIN7_F_SM | A3 VSI-volatility | Yes (persistence) | AMBER (V1); RED (V1.1) | 0.514 (V1 OOF) | No | 0 | std ratio 2.57; persistence fires 266d; no crank/rest signals |
| VIN8_F_SM | A4 silent/abrupt | No | **RED** (V1.1) | 0.303 (V1, GREEN miss) | **YES in V1** | 37 | fcr IMPROVED in final 90d; only std ratio 1.33; persistence fires 98d; V1.1 partial recovery via withinwk std |
| VIN9_F_SM | A4 silent/abrupt | **No on any layer** | GREEN | 0.483 (V1 OOF) | No (V1) | 142 | SMA-dead + std ratio 1.02 + all NF-like; permanent blind spot |
| VIN10_F_SM | A1 solenoid intermittency | Yes (A1 + persistence) | RED | 0.698 (V1 OOF) | No | 0 | fcr 4.3×, retry 7.5×, 8 cranks/day; A1 fires 160d, persistence fires 147d |
| VIN11_F_SM | A3 VSI-volatility | Yes (persistence + A1) | RED | 0.946 (V1 OOF) | No | 0 | std ratio 1.82; persistence fires 266d; A1 fires 179d |
| VIN12_F_SM | A3 VSI-volatility | Yes (persistence + A1) | AMBER (V1); RED (V1.1) | 0.438 (V1 OOF) | No | 0 | std ratio 2.32; persistence fires 126d; A1 fires 128d |
| VIN13_F_SM | A2 battery cascade | Yes (persistence + A2) | AMBER (V1); RED (V1.1) | 0.478 (V1 OOF) | No | 0 | rest delta −0.66V, drive step +0.75V; A2 fires 63d, persistence fires 301d |
| VIN14_F_SM | A1+A2 mixed | Yes (persistence, all channels) | RED | 0.674 (V1 OOF) | No | 0 | fcr 0.449, retry 0.298, rest step −2.31V, std ratio 5.36; persistence fires 245d |

FACT source for V1 OOF probabilities: `reports/V1_SM_final_report.md §5 per-VIN table`.
FACT source for archetypes: `E_pattern_discovery.md §2 + discovery/out/E2_failed_vin_archetypes.csv`.
FACT source for V1.1 tiers: `V1_1_SM_model_spec.json headline.tier_counts`.
FACT source for alert leads: `V1_1_SM_alerts_horizon.md §1-4`.

---

## G. METHODS INVENTORY (Audit + Discovery Scripts)

### Audit Scripts (`V1.1/audit/scripts/`)

| Script | What it implements |
|--------|-------------------|
| `probe1_labels.py` | Failure_type enumeration + JCOPENDATE/telemetry alignment per VIN |
| `probe2_null_structure.py` | SMA/VSI null rates by VIN×month×regime (engine on/off); SMA-dead cohort identification |
| `probe3_sampling_gaps.py` | Sampling cadence (dt_p99), gap structure, density drift near t_end, engine-off VSI decay across long gaps |
| `probe4_vsi_sensor.py` | VSI quantization histogram, stuck-value run detection, per-VIN calibration setpoint baseline |
| `probe5_rest_decay.py` | Engine-off rest-bout VSI decay slope (V/h) for bouts ≥3 h; battery self-discharge proxy |
| `probe6_signal_screen.py` | VIN-level single-feature AUROC screen (45 features) from weekly caches + events parquet; leakage features |
| `probe7_epoch_latent.py` | Epoch/extraction batch structure beyond calendar control; last-8-week Δ(vsi_drive_std) latent degradation with calendar-matched NF control |
| `B1_audit_existing.py` | Audit 23 V1 features: redundancy (Spearman clusters), jackknife AUROC stability, time-proxy correlation, VIN8_F miss profile |
| `B2_candidates.py` | Build + screen 24 new candidate features; vsi_dominant_freq 1/n mechanics check; incremental LOVO vs winner baseline |
| `B3_truncation_control.py` | Fixed-window (L40 masked weeks) history-length control: recompute V1 winner AUROC on equalized history basis |
| `B4_model_variants.py` | LOVO Ridge model variants A–J on artifact-fixed feature sets (drop domfreq, swap withinwk, all-windowed, honest 3-feat) |
| `C1_model_audit.py` | Adversarial audit: full nested LOVO rerun, pooled-vs-per-fold Youden comparison, calibration (Brier/CITL/slope), 9-model-class sweep, jackknife, seed invariance |

### Discovery Scripts (`V1.1/discovery/scripts/`)

| Script | What it implements |
|--------|-------------------|
| `E1_clustering.py` | PCA (loadings, leak check per PC), Ward hierarchical, DBSCAN, Spectral on 22 artifact-free features; PC vs label/proxy correlation |
| `E2_archetypes.py` | Per-VIN final-120-day signature cards vs own >120d baseline + NF reference; NF-quantile flags; archetype labeling (A1–A4) + hierarchical clustering of cards |
| `E3_trajectories.py` | Causal weekly vsi_std_ratio + rolling failed-crank rate aligned on last 40 weeks; trajectory shape classification; persistence-rule screen (m-of-12) |
| `E4_seasonality.py` | Month-of-year effects on vsi_drive_std, rest VSI, NF trend-flag rates; KW tests; season definition (winter/summer/monsoon/post-monsoon) |
| `E5_maintenance.py` | Rest-VSI step-change detection (battery replacement candidates); duty-cycle cluster analysis (cohort-conditioned k=2) |
| `F1_build_truck_week.py` | Causal truck-week table (2,636 rows × 34 trucks) with 1-week-lagged covariates; SMA-dead masking; gap-week exclusion |
| `F2_fleet_clock.py` | KM + Weibull fleet-clock baseline (LOVO conditional-median RUL MAE at multiple horizons); marginal weekly hazard |
| `F3_hazard_lovo.py` | Discrete-time logistic hazard model (truck-level LOVO); pooled weekly AUROC; age-matched concordance; P(fail≤H) at H=30/60/90d; median-RUL MAE |
| `F4_cox_weibull.py` | Cox PH time-varying (lifelines, 2 covariates); Weibull AFT (early-life static covariate); concordance; HR estimates |
| `G1_param_budget.py` | Formula-based parameter counts for 9 deep architectures vs EPV-10 budget; EPV overrun multiples |
| `G2_sequence_probes.py` | PCA/linear-AE probe; 2-coefficient trend-summary probe; Euclidean+Pearson 1-NN; kernel-PCA+logistic; tiny-LSTM (h=2, torch, 3 seeds); leak audits; 1,000-resample bootstrap |
| `G3_prequential_horizon.py` | Prequential earliest-detection: causal features at cut = t_end − 7k days for k=0..26; LOVO Ridge at each k; k-decay curve; G3 L20 control |

---

## ARTIFACT INVENTORY (Presentation / Graphs / Cache)

### V1 Artifacts
- `STARTER MOTOR/graphs/` — **34** production dashboards `V1_SM_{VIN}_dashboard.png` (4-panel: weekly VSI, crank physics, risk gauge, event strip)
- `STARTER MOTOR/cache/weekly/` — 34 weekly parquets `V1_SM_weekly_{VIN}.parquet`
- `STARTER MOTOR/cache/events/V1_SM_crank_events.parquet` — 20,471 events (13 artifact-flagged), 16 columns

### V1.1 Artifacts
- `STARTER MOTOR/V1.1/presentation/` — 2 pptx files (`SM_Predictive_Maintenance_V1.1.pptx`, `SM_Business_Summary_V1.1.pptx`) + 2 builder scripts
- `STARTER MOTOR/V1.1/audit/out/` — 8 CSV files (B1×4, B2×2, B3×1, B4×1)
- `STARTER MOTOR/V1.1/audit/` (root) — 13 CSV probe outputs (probe1–probe7)
- `STARTER MOTOR/V1.1/audit/results/` — 3 files (C1 JSON + 2 CSVs)
- `STARTER MOTOR/V1.1/discovery/out/` — 19 files (E1–E5, F, G1–G3 CSVs + F truck-week parquet + F hazard parquet)
- `STARTER MOTOR/V1.1/results/` — 14 files (feature matrices, nested predictions, model spec, gates JSON, alert CSVs, horizon curve, explanations)
- `STARTER MOTOR/V1.1/reports/` — 10 markdown reports

---

*Intake document generated 2026-06-12 from read-only audit of V1 + V1.1 artifacts.*
*Next step: V2 program scope definition. Refer to this document as the ground-truth baseline for all V2 design decisions.*
