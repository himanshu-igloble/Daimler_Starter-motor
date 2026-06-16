---
title: "Starter Motor Program — Consolidated Results Master (V1 + V1.1)"
status: "complete"
created: "2026-06-10"
---

# STARTER MOTOR PROGRAM — CONSOLIDATED RESULTS (V1 + V1.1)

| Field       | Value                                                                                  |
|-------------|----------------------------------------------------------------------------------------|
| Program     | BharatBenz 5528T starter motor failure prediction (V1 baseline + V1.1 audited redesign) |
| Fleet       | 34 independent trucks: 14 failed + 20 non-failed (suffix `_SM`; no overlap with ALT)    |
| Data volume | 106.4M raw 5-second telemetry rows -> 2,636 truck-weeks + 20,471 crank events           |
| Signals     | VSI, SMA, RPM, CSP, ANR, GED (no current, no temperature, no battery SoC)               |
| Dates       | V1 complete 2026-06-10 (tag `v1-sm`); V1.1 audit + redesign complete 2026-06-10         |
| Status      | COMPLETE — ship recommendation issued (4-layer monitoring program)                      |

---

## 1. EXECUTIVE DASHBOARD
*The whole program in ten lines.*

1. Built: a 4-layer fleet-monitoring program — calibrated risk tiers, validated early-warning alerts,
   an honest maintenance-window statement instead of RUL, and per-truck explanations.
2. Headline: nested-LOVO AUROC **0.9321** (95% CI [0.811, 0.986], permutation p = 0.005).
3. V1's reported 0.9214 was first restated to an honest **0.893** (selection optimism), then beaten.
4. Catches **13/14** failed trucks (incl. V1's miss VIN8_F); RED tier: 10/14 at 18/20 specificity.
5. Probabilities calibrated and shippable (slope 0.86, Brier 0.124); V1's were rank-only (slope 4.72).
6. Early warning now exists: 3 validated alert channels, median first-fire lead 168 days;
   the A2 battery-cascade detector has **zero** false alarms on 20 healthy trucks.
7. Validated detection horizon: a flagged truck is typically within **~10 weeks** of failure.
8. Operations: score weekly; RED -> inspect in 2-4 weeks; AMBER -> next service; A2 -> battery-first.
9. Day-precision RUL is proven impossible here (best survival model err 576 d vs 44 d for a constant).
10. Structural limit: **4/14 failures (silent/abrupt A4) are invisible** in this telemetry at any horizon.

---

## 2. ARCHITECTURE
*How raw truck data becomes a maintenance decision — four shipped layers.*

```
RAW PARQUETS                     PROCESSING                          FEATURES
failed.parquet    30.9M rows --> clean: sentinels, VSI x0.2     --> 10 candidates, all window-
nonfail.parquet   75.5M rows     scaling, SMA-dead cohort mask      anchored (last-40-wk / 90-d),
(VSI SMA RPM CSP ANR GED, 5s)         |                             per-VIN baselined, battery-
                                      v                             step re-baselined
                                 daily + weekly caches                   |
                                 (2,636 truck-weeks)                     |
                                      |                                  v
                                      v                          admissibility gates:
                                 crank-event catalog             leak-proxy audit + L40
                                 (20,471 gap-aware events)       fixed-window control
                                      |                                  |
                                      +----------------+----------------+
                                                       v
                                  NESTED 34-FOLD LOVO RIDGE (alpha=1.0)
                            screening + subset search + Youden threshold +
                            Platt recalibration ALL redone inside every fold
                                                       |
        +---------------------+------------------------+----------------------+
        v                     v                        v                      v
  L1 RISK TIERS         L2 ALERTS + HORIZON      L3 HONEST RUL-WINDOW   L4 EXPLAINABILITY
  GREEN/AMBER/RED       persistence flag,        tier -> maintenance    exact coef x z
  calibrated P,         A2 battery cascade,      window; "~10 wk to     attributions, 34
  AUROC 0.9321          A1 burst (gated);        failure if flagged";   explanation cards,
  weekly scoring        k* = 10-week horizon     NO dates, ever         archetypes, model card
```

---

## 3. COMPLETE WORKFLOW
*Every pipeline step: what goes in, what comes out, and why it exists.*

| Step | Input | Method | Output | Why (one-liner) |
|---|---|---|---|---|
| Ingest + clean | 106.4M raw rows | sentinel strip, VSI x0.2 | clean per-VIN frames | bad rows fake signal |
| Daily/weekly caches | clean frames | per-VIN regime aggregation | 2,636 truck-weeks | weeks = model unit |
| Crank catalog | SMA/VSI/RPM | gap-aware grouping <=10 s | 20,471 events, 13 flagged | tests KT claims |
| Feature engineering | caches + events | 10 window-anchored candidates | 34 x 10 matrix | change, not level |
| Admissibility gates | feature matrix | leak audit + L40 control | 10/10 pass, 0.0 drop | leak ceiling .952 |
| In-fold screening | train fold only | MW p<.10 + AUROC>=.60 | 5-8 feats/fold | V1 leaked +0.029 here |
| Nested LOVO Ridge | per-fold pools | k=3-6 subsets, inner pick | OOF preds, AUROC 0.9321 | honest headline |
| Calibration | inner-OOF scores | per-fold Platt recal | slope 0.86, Brier 0.124 | tiers need real probs |
| Alert validation | weekly causal data | LOVO-validate 3 rules | 13/14 fire; A2 0/20 | in-sample flatters |
| Horizon (X4) | cut-at-k features | prequential cut k=0..26 | k*=10 wk; chance @ k=11 | not a length leak |
| Explainability | frozen model | coef x z + counterfactuals | 34 cards + model card | unexplained = ignored |
| Graphs | all results | fleet risk visual | V1_1_SM_fleet_risk.png | depot review picture |

---

## 4. PERFORMANCE METRICS
*All validation numbers are out-of-fold (leave-one-vehicle-out); nothing here is in-sample.*

### 4a. V1 vs V1.1 headline metrics

| Metric | V1 (reported) | V1 (restated, honest) | V1.1 |
|---|---|---|---|
| AUROC | 0.9214 (non-nested) | **0.8929** (nested) | **0.9321** (nested) |
| Bootstrap 95% CI | [0.765, 1.000] | [0.746, 1.000] | [0.811, 0.986] |
| Permutation p | 0.001 (non-nested) | — | 0.005 (full nested pipeline) |
| Selection optimism | +0.0285 (hidden) | disclosed | +0.0036 |
| Recall @ honest threshold | 13/14 (post-hoc pooled) | 12/14 (per-fold) | **13/14** (per-fold) |
| Specificity @ same point | 18/20 | 18/20 | 15/20 (RED tier: 18/20) |
| Calibration slope / Brier | 4.72 / 0.149 (rank-only) | — | **0.86 / 0.124** (shippable) |
| Validated lead-time channel | none (NF FP 90%) | none | 3 channels, 13/14 covered |
| Detection horizon | not measured | not measured | **k* = 10 weeks**, verified |
| Features | 4 (1 artifact) | 3 sound | 4, all admissibility-audited |

Ablation: the nested protocol on V1's de-artifacted features scores **0.8429** — V1.1's gain (+0.089)
comes from new feature engineering, not from protocol arithmetic.

### 4b. Operating points (both pre-registered; choose per maintenance economics)

| Operating point | Recall | Specificity | Character |
|---|---|---|---|
| Per-fold Youden | 13/14 | 15/20 | recall-greedy; 5 NF false alarms |
| RED tier (recal P >= 0.55) | 10/14 | 18/20 | low false-alarm burden (2/20 NF) |
| V1 restated (reference) | 12/14 | 18/20 | honest baseline |

### 4c. Alert channels (all LOVO- or physics-validated; no in-sample numbers shipped)

| Channel | Recall | NF false alarms | Median lead | Verdict |
|---|---|---|---|---|
| Persistence >=4/12 wks over NF envelope | 13/14 | 4/20 terminal | 168 d | ship tier-gated flag only |
| A2 battery-cascade triple | 4/5 battery archetype | **0/20** | 66.5 d | ship; battery-first (A6) |
| A1 crank-burst | 4/12 applicable | 1.52 ep/truck-yr | 160 d | corroborator (saved VIN1_F) |
| Combined (any channel) | **13/14** | 10/20 NF fully clean | 168 d | sole miss VIN9_F (structural) |

### 4d. Per-VIN nested predictions (recalibrated P; tiers GREEN < 0.35 <= AMBER < 0.55 <= RED)

| VIN | Cohort | P_recal | Tier | Correct | Archetype | Note |
|---|---|---|---|---|---|---|
| VIN6_F  | F | 0.998 | RED   | yes | A2 battery   | strongest cascade (rest step -2.71 V) |
| VIN14_F | F | 0.998 | RED   | yes | A1+A2 mixed  | burst + cascade |
| VIN10_F | F | 0.995 | RED   | yes | A1 solenoid  | fcr 4.3x, retries 7.5x |
| VIN5_F  | F | 0.992 | RED   | yes | A4 silent    | 32-d gap; caught on pre-silence state |
| VIN11_F | F | 0.958 | RED   | yes | A3 volatility| |
| VIN12_F | F | 0.955 | RED   | yes | A3 volatility| |
| VIN7_F  | F | 0.906 | RED   | yes | A3 volatility| |
| VIN2_F  | F | 0.904 | RED   | yes | A2 battery   | |
| VIN8_F  | F | 0.716 | RED   | yes | A4 silent    | **V1's miss (0.303) — now caught**; 37-d gap |
| VIN13_F | F | 0.654 | RED   | yes | A2 battery   | |
| VIN4_F  | F | 0.339 | GREEN | yes | A4 silent    | caught at Youden, not RED; 97-d gap |
| VIN3_F  | F | 0.338 | GREEN | yes | A2 battery   | caught at Youden; persistence alert fires |
| VIN1_F  | F | 0.260 | GREEN | yes | A1-then-silent | caught at Youden; A1 alert rescue; 72-d gap |
| VIN9_F  | F | 0.224 | GREEN | **MISS** | A4 silent | 0.401 vs thr 0.406; SMA-dead + 142-d gap |
| VIN5_NF | NF | 0.958 | RED   | **FP** | — | 3 alert channels too — possible real degrader |
| VIN20_NF| NF | 0.623 | RED   | **FP** | — | SMA-dead cohort |
| VIN2_NF | NF | 0.452 | AMBER | **FP** | — | persistence 12/12 wks — possible degrader |
| VIN10_NF| NF | 0.435 | AMBER | **FP** | — | SMA-dead cohort |
| VIN15_NF| NF | 0.254 | GREEN | **FP** | — | FP at Youden only; persistence repeat offender |
| VIN18_NF| NF | 0.235 | GREEN | yes | — | |
| VIN19_NF| NF | 0.197 | GREEN | yes | — | |
| VIN13_NF| NF | 0.146 | GREEN | yes | — | |
| VIN7_NF | NF | 0.143 | GREEN | yes | — | |
| VIN11_NF| NF | 0.121 | GREEN | yes | — | |
| VIN4_NF | NF | 0.118 | GREEN | yes | — | |
| VIN17_NF| NF | 0.096 | GREEN | yes | — | |
| VIN12_NF| NF | 0.091 | GREEN | yes | — | |
| VIN9_NF | NF | 0.082 | GREEN | yes | — | |
| VIN6_NF | NF | 0.070 | GREEN | yes | — | |
| VIN1_NF | NF | 0.066 | GREEN | yes | — | |
| VIN3_NF | NF | 0.056 | GREEN | yes | — | |
| VIN8_NF | NF | 0.048 | GREEN | yes | — | |
| VIN16_NF| NF | 0.043 | GREEN | yes | — | |
| VIN14_NF| NF | 0.041 | GREEN | yes | — | |

Model: RidgeClassifier(alpha=1.0) on 4 features — `vsi_withinwk_std_ratio_30d_w` (coef +0.886,
the workhorse), `rest_vsi_p05_delta90` (battery-floor sag), `vsi_range_trend` (flagged suppressor),
`dip_depth_last90_delta` (crank dip widening). Core pair selected in 34/34 folds.

---

## 5. CRITICAL FINDINGS
*The twelve results that define what this program can and cannot claim.*

| # | Finding | Evidence | Consequence |
|---|---|---|---|
| 1 | V1 headline restated | 0.9214 -> 0.893 nested (+0.029 optimism, 1 fake TP) | stricter protocol adopted |
| 2 | vsi_dominant_freq artifact | 1/n_weeks proxy; 0.748 -> 0.525 fixed-window | banned + binding registry |
| 3 | Leak ceilings | n_weeks AUROC 0.952, t_start 0.893 | admissibility gates mandatory |
| 4 | SMA-dead cohort (7 trucks) | SMA null >99.7%; 10x event rates (config) | crank features cohort-masked |
| 5 | KT crank claims refuted | +48% -> +3.0%; >5% lifetime rule flags NF more | late change wins (0.74) |
| 6 | V1 lead-time channel void | trend tests fired on 18/20 healthy (90% FP) | replaced by V1.1 channels |
| 7 | 10-week horizon validated | AUROC>=0.75 to k=10; chance at k=11; tail 0.59 | 2.5-month claim provable |
| 8 | Archetypes A1-A4 | A1 x3, A2 x4-5, A3 x3, A4 silent x4 | recall ceiling ~10-11/14 |
| 9 | Survival/RUL negative | hazard MAE 576 d vs constant 44 d; rank 0.586 | no RUL ships — proof attached |
| 10 | Deep learning negative | 235x-6,275x over budget; seed var > signal | shelved until n_failed >= 30-50 |
| 11 | VIN9_F structural miss | SMA-dead + 142-d gap + abrupt mode | telemetry problem, not modeling |
| 12 | Battery confound | tops breakdowns (ADAC 45.4%); A2 0/20 NF | A6 battery-first triage built in |

---

## 6. BUSINESS TRANSLATION
*What each technical result means on the depot floor.*

| Technical result | What it means | Recommended action |
|---|---|---|
| RED tier: 10/14 recall @ 18/20 spec | matches failed-truck pattern | inspect starter+battery in 2-4 wks |
| AMBER tier (0.35-0.55) | elevated, not urgent | bundle check into next service |
| GREEN tier | normal electrical pattern | normal ops; keep scoring |
| A2 alert: 0/20 FP, ~9-wk lead | battery cascading into starter | battery-first work order (A6) |
| 10-wk detection horizon | flagged truck <=10 wks from failure | score weekly; clean = ~2.5 mo valid |
| No RUL (576 vs 44 d proof) | dates unpredictable from this data | never promise failure dates |
| A4 invisible (4/14) | some failures give no warning | telemetry silence = maintenance flag |
| 4 NF persistence flags | future failures or rule drift | track VIN2/5/8/15_NF either way |
| Data asks (section 7) | current sensors cap performance | instrument 1 Hz crank + current/SoC |

---

## 7. LIMITATIONS & DATA REQUESTS
*What this program honestly cannot do, and what would fix it.*

Limitations:
- n = 34 trucks, 14 failures: the CI floor is 0.811 and a handful of trucks decide every threshold.
- 4/14 failures (A4 silent/abrupt) are structurally invisible; alerting recall ceiling is ~10-11/14.
- 5-second / 0.2 V sampling destroys the one genuine 60-120-day precursor (brush wear) and dip physics.
- No operating point dominates V1 on every cell: Youden trades 3 specificity for +1 recall.
- Archetypes were derived in-sample — suggestive, not inferential.
- OOF scores correlate with observation-length proxies (|r| up to 0.65) — label-mediated, defended by
  the zero-drop L40 control and decay-to-chance curve; only a larger fleet is a definitive cure.

Data requests (ranked by value):
1. High-frequency crank logging (>= 1 Hz during SMA=1) — revives brush-wear prognosis; biggest unlock.
2. Cranking current or battery SoC/SoH — ends the battery-vs-starter ambiguity capping alert precision.
3. Maintenance/parts-replacement records — turns data-derived archetypes into supervised labels.
4. More failures (n_failed >= 30-50) — unlocks survival modeling and self-supervised pretraining.
5. Ambient temperature — cold-start conditioning.

---

## 8. ARTIFACT INDEX
*Where everything lives (paths relative to `STARTER MOTOR/`).*

| Artifact | Path |
|---|---|
| V1 final report (baseline, KT reconciliation) | `reports/V1_SM_final_report.md` |
| V1.1 deliverables index | `V1.1/README.md` |
| V1.1 architecture spec (evidence table) | `V1.1/Plan/V1_1_SM_spec.md` |
| Audits A-D | `V1.1/audit/` (A data quality, B features, C model, D physics) |
| Discovery E-G | `V1.1/discovery/` (E archetypes, F survival, G sequence) |
| Experiment results (features + nested model) | `V1.1/reports/V1_1_SM_experiment_results.md` |
| Alerts + horizon validation | `V1.1/reports/V1_1_SM_alerts_horizon.md` |
| Model card (governance, gates, banned features) | `V1.1/reports/V1_1_SM_model_card.md` |
| Explanation cards (34 VINs) | `V1.1/reports/V1_1_SM_explanation_cards.md` |
| V1 vs V1.1 comparison | `V1.1/reports/V1_1_SM_comparison_report.md` |
| Executive recommendation | `V1.1/reports/V1_1_SM_executive_recommendation.md` |
| Per-VIN nested predictions | `V1.1/results/V1_1_SM_nested_lovo_predictions.csv` |
| Frozen model spec / gates | `V1.1/results/V1_1_SM_model_spec.json`, `V1_1_SM_gates.json` |
| Alert policy + horizon curve | `V1.1/results/V1_1_SM_alert_policy.csv`, `V1_1_SM_horizon_curve.csv` |
| Fleet risk graph | `V1.1/graphs/V1_1_SM_fleet_risk.png` |
| Code | `V1.1/src/` (features, nested ridge, alerts, horizon, explainability) |

---

*Bottom line: V1.1 is the honest ceiling of this dataset — a calibrated risk ranking (AUROC 0.9321)*
*with a validated ~10-week warning window and physics-grounded battery-first triage, delivered with*
*its limits measured and stated. Reliable improvement beyond it requires new signals, not new models.*
