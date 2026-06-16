---
title: "V1.1 Starter Motor Fleet-Risk Model — Model Card"
status: "complete"
created: "2026-06-10"
---

# Model Card — V1.1 Starter Motor Fleet-Risk Classifier

All numbers sourced from: `V1.1/results/V1_1_SM_model_spec.json`, `V1_1_SM_gates.json`,
`V1_1_SM_nested_lovo_predictions.csv`, `V1_1_SM_feature_admissibility.csv`,
`V1_1_SM_explanations.json`, `V1.1/reports/V1_1_SM_experiment_results.md`,
`V1.1/discovery/G_sequence_representation.md`, `E_pattern_discovery.md`,
`V1.1/audit/D_failure_physics.md`.

---

## 1. Model summary

- **Model**: `RidgeClassifier(alpha=1.0)` on 4 standardized features (median impute →
  `StandardScaler`). Verified against a closed-form ridge replica to max |z diff| 1.6e-15.
- **Features** (modal winner subset, X2; production coefficients from X5 refit):

| feature | meaning | coef (std) | physics verdict |
|---|---|---|---|
| `vsi_withinwk_std_ratio_30d_w` | within-week VSI noise, last 4 wk / own 40-wk baseline | +0.8862 | matches physics (univariate AUROC 0.921) |
| `rest_vsi_p05_delta90` | engine-off rest-voltage floor delta vs own baseline, battery-step aware | −0.2704 | matches physics (univariate AUROC 0.243, oriented low-is-risk) |
| `vsi_range_trend` | weekly drive-VSI range (p95−p05) Theil-Sen slope, last 12 wk | −0.4139 | **suppressor — flagged**: univariate direction matches physics (AUROC 0.732, widening = risk); multivariate sign flipped by r = +0.82 collinearity with the noise ratio |
| `dip_depth_last90_delta` | crank dip-depth delta, last 90 d vs own baseline | +0.1409 | matches physics (univariate AUROC 0.739) |

- **Production refit**: trained on all 34 trucks (X5, 2026-06-10) for deployment and
  explanation only. Its resubstitution AUROC (0.9571) is **not** a performance claim;
  all validation numbers below are nested-LOVO out-of-fold.
- **Validation-time protocol** (X2, per fold): V1-faithful screening (MW p<0.10,
  AUROC≥0.60, |Spearman|<0.85 dedup, stability ≥27/33, pool cap 10), exhaustive
  subsets k=3–6, winner by inner 33-fold LOVO; per-fold inner-OOF Youden threshold
  (pre-registered) and **per-fold Platt recalibration** on inner-OOF decision values.
- **Tier rule** (pre-registered): GREEN < 0.35 ≤ AMBER < 0.55 ≤ RED on recalibrated
  probability.
- Explainability (X5): exact linear attribution (contribution = coef × z, equals SHAP
  for a linear model on standardized inputs), per-truck counterfactuals in raw units;
  see `V1_1_SM_explanation_cards.md` (34 cards) and `V1_1_SM_explanations.json`.

## 2. Intended use

- **Is**: fleet risk *prioritization* — a recalibrated probability that a truck's
  recent-window electrical pattern matches the failed-truck pattern, mapped to
  GREEN/AMBER/RED maintenance-window tiers for inspection scheduling and triage.
- **Is NOT**: a day-precision RUL estimate or a countdown to failure. The V1-program
  conclusion stands (alternator V10.6.2 and SM V1 both): per-truck day-level RUL is
  not supported by this telemetry. Detection is reliable only inside a ≤10-week
  pre-failure window (§7); outside it the score is uninformative by construction.
- Out of scope: mode-level diagnosis (solenoid vs brush vs bearing — physically
  collapsed at 5 s sampling, D §2), cross-fleet transfer, any cross-dataset VIN-level
  use (ALT and SM VINs are different physical trucks).

## 3. Training data

- **Fleet**: 34 SM trucks (14 failed / 20 non-failed), suffix `_SM`. ~106M raw 5-second
  telemetry rows (VSI/SMA/RPM/CSP/ANR/GED, ~0.2 V effective resolution; no current,
  temperature, or SoC) reduced to weekly aggregates (2,636 truck-weeks) plus 20,471
  crank events. One label per truck.
- **Observation asymmetries** (the central leakage hazard): failed trucks have shorter
  histories *because they failed* — `n_weeks` alone classifies at AUROC 0.952,
  `t_start` at 0.893, and t_end month is nearly a label (failed ends Jun–Dec, NF ends
  pile at Feb). All features are therefore window-anchored (§6).
- **SMA-dead cohort** (telematics config, <1% SMA coverage): VIN8_F, VIN9_F,
  VIN10/11/12/13/20_NF — all 5 crank/event features are NaN and fold-internally
  median-imputed, never zero-filled. VIN5_F additionally has zero crank events and no
  VSI in its final 120 d.
- **Silent-gap VINs**: 5/14 failed trucks stop transmitting before failure (VIN1 72 d,
  VIN4 97 d, VIN5 32 d, VIN8 37 d, VIN9 142 d); features describe the pre-silence state.
- Battery-replacement steps (E5): rest-VSI baselines are re-anchored post-step for
  VIN8_F and 5 NF trucks (VIN3/5/12/17/18_NF).

## 4. Metrics (all nested-LOVO out-of-fold, n=34)

| quantity | value |
|---|---|
| **AUROC (headline)** | **0.9321**, bootstrap 95% CI [0.811, 0.986] (N=200, seed 42) |
| Permutation test | p = 0.005 (0/200 full-pipeline label shuffles ≥ 0.9321; floor at N=200) |
| Recall @ per-fold Youden | **13/14** (specificity 15/20; TP 13, FN 1, TN 15, FP 5) |
| RED-tier operating point | **10/14 recall @ 18/20 specificity** (RED: 10F+2NF; AMBER: 0F+2NF; GREEN: 4F+16NF) |
| Calibration (pooled recalibrated OOF) | Brier 0.124 (constant-ref 0.242), CITL −0.062, slope 0.86 ∈ [0.5, 2] → probabilities shippable |
| Nesting optimism | +0.0036 (non-nested 0.9357 vs nested 0.9321) |
| Jackknife stability (G5) | AUROC min 0.927 / max 0.951, std 0.007 |
| Ablation: nested protocol on V1-era 22 features (honest floor) | **0.8429** — the V1.1 gain comes from the new features, not the protocol |
| V1 restated baseline | 0.8929 (recall 12/14 @ 18/20) — V1.1 is +0.039 AUROC and +1 recall (catches V1's worst miss VIN8_F at recal 0.716, RED) |

Two pre-registered operating points exist: Youden (recall-greedy, 13/14 @ 15/20) and
RED-tier (10/14 @ 18/20). Choose per maintenance economics; both are honest.

## 5. Known failure modes & limitations

- **A4 silent/abrupt is a structural miss class** (4/14 failures ≈ 29%): no admissible
  feature sees these trucks. The sole nested miss, **VIN9_F_SM** (OOF prob 0.401 vs
  fold threshold 0.406; GREEN tier, recal 0.224), is A4 + SMA-dead + 142-day silent
  gap — the physics audit classifies this failure as unobservable in this telemetry.
  The honest recall ceiling for tier-RED alerting is ~10–11/14, as E/D predicted.
- **5 s sampling destroys the brush-wear channel**: the physically real 60–120 d
  declining-crank-voltage precursor lives in sub-sample dip shape and sub-second
  duration growth; at 5 s / 0.2 V it is invisible until the terminal weeks (D §2/§5).
  Bearing seizure has zero electrical precursor at any sampling rate.
- **n=34, 14 events**: the bootstrap CI is wide ([0.811, 0.986]); archetype counts are
  suggestive, not inferential; the calibration slope (0.86) is estimated on 34 points.
- G4 winner-stability **fails the strict criterion** (modal subset 14/34 folds) — a
  14/14 tie between the k=4 and k=3 nestings of the same core; substantively stable
  (core pair selected 34/34 folds, only 3 distinct subsets ever chosen).
- `vsi_range_trend` enters as a statistical suppressor (negative multivariate weight
  despite physics-positive direction); per-VIN glosses state the physical value and
  the model's suppressor use separately. Counterfactuals are *ceteris paribus*
  statements, not repair prescriptions.
- Youden operating point carries 5/20 NF false alarms; the RED tier reduces this to 2/20.

## 6. Leakage controls

- **Banned features**: `vsi_dominant_freq` — a 1/n_weeks artifact (0.748 → 0.525 under
  the fixed-window control); calendar/season features on end-anchored windows (t_end
  month ≈ label, E §4); any raw observation-length feature (leak AUROCs: `n_weeks`
  0.952, `t_start` 0.893). G6 token scan of selected features: 0 banned tokens.
- **L40 fixed-window control (G1)**: every feature is window-anchored by construction
  (last 40 masked weeks / last-90-d event windows); the L40-control matrix is
  bit-identical to production and the modal-subset rerun loses **0.0000 AUROC** —
  a length artifact would collapse, as `vsi_dominant_freq` did.
- **Prequential time-locking argument (G3)**: causal LOVO AUROC holds 0.836–0.921 for
  cuts k = 0..10 weeks before t_end and collapses to 0.536 at k = 11. The proxies
  (n_weeks/t_start/span) are constant per truck across k, so an epoch/length leak
  would yield a flat curve; decay-to-chance shows the score is **failure-locked, not
  epoch-locked**.
- **Disclosed OOF-score proxy correlations (G2)**: Spearman −0.640 vs n_weeks, +0.507
  vs t_start, −0.653 vs span — above the 0.5 tripwire, reported with justification:
  label-mediated (failed trucks have shorter telemetry because they failed), with the
  zero-drop L40 control and the G3 decay curve as the disambiguating evidence.
  Admissibility audit (X1): 10/10 candidates pass; 3 sit in the "watch" band on the
  same label-mediated grounds (`V1_1_SM_feature_admissibility.csv`).

## 7. Detection horizon

- **≤ 10 weeks (~70 days) before failure** (G3, `discovery/out/G3_horizon_curve.csv`):
  prequential AUROC 0.836–0.921 inside k = 0..10, chance (0.536) at k = 11. An
  isolated bump at k = 15–17 is not sustained and is not counted.
- There is **no earlier warning channel** in this telemetry — consistent with the
  Phase-1 lead-time verdict and the alternator finding that abrupt electrical modes
  do not telegraph.
- **X4 confirmation on the final 4-feature model** (`results/V1_1_SM_horizon_curve.csv`,
  `reports/V1_1_SM_alerts_horizon.md`): k = 0 AUROC 0.9357 decaying to 0.77 at k = 10,
  below 0.75 at k = 11, far-tail (k = 23–26) mean 0.592 with bootstrap CIs spanning 0.5 —
  **k\* = 10 weeks confirmed**, decay-to-chance verified (time-locked signal, not leakage).

## 8. Update cadence & governance

- **Scoring**: re-score the fleet at least monthly; weekly causal re-scoring is
  preferred (Agent G §5) given the ≤10-week horizon — monthly gives only ~2 reads
  inside the actionable window.
- **Refit**: only when new failure labels arrive, and only under the **full nested
  protocol** (34+ fold outer LOVO, per-fold screening/subset/threshold/recalibration,
  seeds documented) with all gates re-run (G1 L40 control, G2 proxy audit, G3
  calibration, G4 stability, G5 jackknife, G6 token scan) and the permutation test.
  No threshold or tier-boundary tuning outside that protocol.
- Recalibration check on each refit: if the slope leaves [0.5, 2], ship tiers only
  (spec 3.5).

## 9. Alert routing

- **Battery-first triage per DICV A6** for A2-pattern (battery-cascade) trucks: when
  the rest-VSI floor sags and dips deepen *together with* rising failed-start/retry
  rate, route the work order battery-first — the cascade is bidirectional (weak
  battery accelerates solenoid wear; long cranks drain and heat the battery). A rising
  crank-failure rate *with a clean battery block* is the highest-confidence
  starter-side signal this data can produce (D §3). In X3's channel run the A2
  detector fired on 4 failed trucks (VIN3/6/13/14_F) and 0 NF trucks.
- **Alert burden**: RED-tier alerting flags 12/34 trucks (10 failed, 2 NF — 2/20 NF
  false-alarm burden). The supplementary persistence/A1-burst channels fire at least
  once on 10/20 NF trucks over ~2-year histories (`V1_1_SM_alert_policy.csv`), so they
  are triage *context* attached to a RED/AMBER score, not standalone alarms.
