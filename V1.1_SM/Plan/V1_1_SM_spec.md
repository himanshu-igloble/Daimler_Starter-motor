---
title: "V1.1 Starter Motor — Architecture Specification (Evidence-Driven Redesign)"
status: "complete"
created: "2026-06-10"
updated: "2026-06-10"
---

# V1.1 Starter Motor — Architecture Specification

Synthesis of the Phase 1 audits (A: data quality, B: features, C: model, D: physics) and Phase 2 discovery (E: patterns/archetypes, F: survival, G: sequence/representation). All referenced evidence lives under `STARTER MOTOR/V1.1/audit/` and `STARTER MOTOR/V1.1/discovery/`.

## 0. What changed since V1 (binding evidence)

| # | Finding | Source | Consequence for V1.1 |
|---|---------|--------|----------------------|
| 1 | V1's honest baseline is **nested-LOVO AUROC 0.893** (reported 0.9214 carries +0.029 selection optimism; pooled Youden threshold bought 1 fake TP → honest recall 12/14) | C | V1.1 headline metric = fully nested LOVO; V1 restated in all comparisons |
| 2 | `vsi_dominant_freq` is a **1/n_weeks artifact** (r=+0.425 with 1/n; collapses 0.748→0.525 under fixed window) | B | Banned. Replaced by `vsi_withinwk_std_ratio_30d` (windowed; survives L40 control at 0.92) |
| 3 | Leakage ceilings: `n_weeks` AUROC 0.952, `t_start` 0.893, 16/20 NF end at extraction date | A | Mandatory gates: fixed-window (L40) control, n_weeks/t_start proxy audit on every feature and every model score |
| 4 | **SMA-dead config cohort**: 7 trucks (VIN8_F, VIN9_F + 5 NF) have SMA >99% null; event-triggered config yields 10× event rates | A | All crank/SMA features cohort-masked; never pooled raw |
| 5 | Per-truck VSI regulation setpoints span 27.6–28.2 V (≈ one 0.2 V quantization step) | A | All VSI features per-VIN-baselined (ratios/deltas vs own history), never absolute levels |
| 6 | Three observable failure pathways: A1 solenoid intermittency (VIN10,14,1_F), A2 battery cascade (VIN2,3,6,13_F +14), A3 volatility drift (VIN7,11,12_F); A4 silent/abrupt (VIN4,5,8,9_F) is unobservable | E, D | Archetype-aware alerting; honest recall ceiling ~10–11/14 for lead-time claims |
| 7 | Hazard/survival layer **loses** to both the static classifier (truck ranking 0.586 vs 0.893) and a constant RUL (MAE 576 d vs 44 d); calibration and day-precision RUL are mathematically incompatible at 14 events | F | No survival layer ships. `vsi_std_ratio` retained as the one temporal covariate (Cox HR 1.74) |
| 8 | Deep sequence/representation models out: minimal LSTM is 235× over the EPV budget; tiny-LSTM demo shows seed variance > signal; all probes saturate at the same ~0.89–0.92 single degree of freedom | G, C | None ship; documented in model card |
| 9 | **Detection horizon k\* ≈ 10 weeks (~70 d)**: prequential AUROC 0.836–0.921 for k=0..10 weeks before t_end, cliff to chance at k=11; decay proves signal is failure-locked, not epoch leak | G | Layer 2 ships weekly prequential scoring with a stated ≤10-week horizon; the k-curve is the leak disambiguation in the model card |
| 10 | Persistence rule (≥4 of last 12 weeks above NF p90 envelope of causal within-week VSI-std ratio): 13/14 failed vs 2/20 NF — in-sample screen | E | Promoted to Experiment E3 for LOVO validation; only validated numbers ship |
| 11 | Physics: no long lead time is *expected* (solenoid/engagement modes have days–weeks horizons; the 60–120 d brush channel is destroyed by 5 s sampling); battery is the best-observed channel and prime confound | D | Battery-vs-starter triage built into alerts (A2 triple detector → battery-first inspection routing) |
| 12 | Battery-replacement step signatures exist (rest-VSI step ≥ +0.5 V; 5 NF + VIN8_F) | E | Rest-VSI features must be segment-aware (post-step re-baseline) |
| 13 | `Failure_type` column is useless (single value "Starter Motor" on all rows) | A | No mode labels; archetypes remain data-derived |

## 1. Architecture (4 layers)

### Layer 1 — Fleet Risk Model (static, per-truck)
RidgeClassifier(alpha=1.0), per-fold impute→scale, **fully nested 34-fold LOVO** (screening + subset selection inside every fold). Feature pool (≤12 candidates, every one admissible under §2):

- Electrical (B-validated): `vsi_std_ratio_30d_L40` (fixed-basis redefinition), `vsi_withinwk_std_ratio_30d_w`, `vsi_range_trend`, `vsi_trend_persistence`.
- Crank physics (D-motivated, cohort-masked): `failed_crank_rate_last90`, `retry_burst_rate_last90` (≥2 SMA events ≤10 min without sustained RPM>600), `extended_crank_tail_rate_last90` (P(event ≥2 samples) last-90d minus lifetime), `first_crank_fail_rate_last90` (first crank after ≥6 h rest).
- Battery (E/D-motivated, segment-aware): `rest_vsi_p05_delta90` (vs post-step baseline), `dip_depth_last90_delta`.

Outputs: per-truck P(fail-pattern), tier (GREEN/AMBER/RED with pre-registered threshold rule §3.4), bootstrap CI, permutation p.

### Layer 2 — Failure Prediction with Horizon (weekly prequential)
Weekly re-scoring of the Layer-1 model on causal features (only data ≤ scoring week). Ships:
- **Persistence alert** (E3-validated parameters only): consecutive-weeks-above-envelope rule, envelope from training folds only.
- **Archetype-conditional alerts**: A1 crank-burst alarm (daily failed-crank/retry CUSUM vs own baseline — high precision, days–weeks horizon); A2 battery-cascade triple detector (rest-step down + drive-step up + dip-depth widening) → routes to *battery-first* inspection (DICV A6).
- Stated horizon: detection typically ≤10 weeks before failure (G3 curve); never quote dates.

### Layer 3 — RUL (honest)
No day-precision RUL, no hazard model (F verdict). Ships: (a) tier → maintenance-window mapping (RED: next depot visit 2–4 wks; AMBER: next scheduled service); (b) Weibull fleet-clock context (λ=133 wk, ρ=2.0, median 111 wk) as fleet-planning prior only; (c) the ≤10-week horizon statement on flagged trucks. The model card states why this is the ceiling (F: MAE table; D: physics).

### Layer 4 — Explainability
Linear model → exact decomposition: per-truck contribution = coef × (z-scored feature), reported as ranked drivers per VIN (SHAP for a linear model equals this; no library needed). Plus: archetype assignment with evidence card, counterfactual statement per flagged truck ("score returns to GREEN if last-90d failed-crank rate halves"), and the global model card (features, gates, horizon curve, known misses A4).

## 2. Feature admissibility rules (hard gates)
1. No observation-length, t_start/epoch, gap, SALEDATE/JCOPENDATE, cumulative counts.
2. Banned: `vsi_dominant_freq`, full-history-denominator ratios (use fixed L40 basis), calendar-month features on end-anchored windows (E4: t_end month ≈ label).
3. Every candidate reports: Spearman r vs n_weeks, t_start ordinal, span; AUROC under fixed-L40 control. |r|>0.5 with any proxy AND >0.05 AUROC drop under L40 ⇒ rejected (label-mediated correlation is acceptable only with a G3-style time-locking demonstration).
4. SMA/crank features: computed within config cohort; SMA-dead trucks get NaN + fold-internal imputation (F's approach), never zeros.
5. VSI features: per-VIN ratios/deltas only; rest-VSI features re-baselined after detected battery-replacement steps.

## 3. Validation protocol
1. **Nested LOVO** (screen + select inside each of 34 folds) = the headline number.
2. Non-nested LOVO reported only as "optimism-uncorrected" with the delta.
3. **Fixed-window control**: full rerun with every VIN clipped to last 40 masked weeks; drop >0.05 ⇒ fail.
4. **Pre-registered threshold rule** (before seeing OOF scores): per-fold inner-OOF Youden; tiers GREEN <0.35 ≤ AMBER <0.55 ≤ RED on recalibrated scores.
5. Calibration: per-fold Platt recalibration; report Brier, CITL, slope; if slope ∉ [0.5, 2], ship tiers only, not probabilities.
6. Permutation test (N=1000) on the nested pipeline; bootstrap CI (N=200).
7. Alert rules (Layer 2): envelope/thresholds from training folds; FP rate on NF reported per rule; prequential k-curve regenerated for the final model.
8. Stability: jackknife AUROC, per-fold winner-subset table.

## 4. Experiments (Phase 4)
| ID | Experiment | Success criterion |
|----|-----------|-------------------|
| X1 | Build V1.1 feature matrix (new physics + battery + windowed electrical; admissibility audit table) | All features pass §2 gates |
| X2 | Nested-LOVO Ridge + subset search + gates + calibration | Nested AUROC ≥ 0.893 (beat restated V1); all §3 gates pass |
| X3 | LOVO-validated persistence alert + archetype alerts | Validated recall/FP; honest verdict if rule degrades out-of-fold |
| X4 | Prequential horizon curve for final model | k\* confirmed; curve in model card |
| X5 | Explainability cards (34 VINs) + model card | Delivered |
| X6 | V1 vs V1.1 comparison + executive recommendation | Delivered, honest |

## 5. Explicit non-goals (evidence-closed)
Hazard/survival layer (F), deep sequence models (G/C), day-precision RUL (F + ALT V10.6.2), unsupervised anomaly track (ALT), GED channel (V1 §2.3), SSL pretraining on raw 5 s rows (defensible but shelved until n_failed ≥ 30–50; G §3).
